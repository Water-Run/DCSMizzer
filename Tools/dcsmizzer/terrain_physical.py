"""Bounded consumers for version-bound physical-terrain evidence exports."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from .br_static import br_airbase_report


EVIDENCE_SCHEMA = "dcsmizzer.terrain-physical-evidence/v1"
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_SAMPLES = 1_000_000
MAX_OBJECTS = 100_000
MAX_OBJECT_SEARCHES = 10_000
MAX_AIRFIELDS = 5_000
MAX_ROUTE_POINTS = 1_000
MAX_CORRIDOR_SAMPLE_QUERIES = 100_000
MIN_SAMPLE_TOLERANCE_M = 0.001
MAX_SAMPLE_TOLERANCE_M = 1.0
MAX_TEXT = 512
MAX_ABS_COORDINATE = 100_000_000.0
_PHYSICAL_EXPORT_KINDS = frozenset(
    {
        "dcs_terrain_api_runtime_export",
        "dcs_mission_editor_terrain_api_export",
        "dcs_mission_scripting_runtime_export",
    }
)
_SURFACES = frozenset(
    {
        "land",
        "water",
        "shallow_water",
        "sea",
        "lake",
        "river",
        "road",
        "runway",
    }
)


def validate_terrain_evidence(data: Any) -> None:
    """Validate a decoded evidence object without granting producer trust."""

    _validate_json_graph(data)
    _validate_evidence(data)


def placement_sample_points(
    *,
    x: float,
    y: float,
    heading_deg: float,
    length_m: float,
    width_m: float,
) -> list[dict[str, float]]:
    """Return the exact center/corner samples used by placement validation."""

    center = (_coordinate(x, "x"), _coordinate(y, "y"))
    heading = _heading(heading_deg)
    length = _positive(length_m, "length_m")
    width = _positive(width_m, "width_m")
    return [
        {"x": point_x, "y": point_y}
        for point_x, point_y in (
            center,
            *_rectangle_corners(center, heading, length, width),
        )
    ]


def corridor_sample_points(
    *,
    route: list[dict[str, Any]],
    half_width_m: float,
    step_m: float,
) -> list[dict[str, float]]:
    """Return the exact terrain coordinates used by corridor validation."""

    if not isinstance(route, list) or len(route) < 2:
        raise ValueError("route must contain at least two points")
    if len(route) > MAX_ROUTE_POINTS:
        raise ValueError(
            f"route exceeds the {MAX_ROUTE_POINTS}-point limit"
        )
    route_points = [_route_point(item, index) for index, item in enumerate(route)]
    half_width = _nonnegative(half_width_m, "half_width_m")
    step = _positive(step_m, "step_m")
    return [
        {"x": float(item["x"]), "y": float(item["y"])}
        for item in _corridor_queries(route_points, half_width, step)
    ]


def physical_point_report(
    evidence_path: Path,
    x: float,
    y: float,
    *,
    terrain: str | None = None,
    dcs_version: str | None = None,
    tolerance_m: float | None = None,
) -> dict[str, Any]:
    """Resolve one terrain sample without implying unsampled surroundings."""

    evidence, provenance = _load_evidence(
        evidence_path,
        terrain=terrain,
        dcs_version=dcs_version,
    )
    x_value = _coordinate(x, "x")
    y_value = _coordinate(y, "y")
    tolerance = _sample_tolerance(evidence, tolerance_m)
    sample_index = _SampleIndex(evidence["samples"], tolerance)
    sample, distance = sample_index.nearest(x_value, y_value)
    reasons: list[str] = []
    if sample is None:
        reasons.append("no_sample_within_tolerance")
    if not provenance["physical_authority"]:
        reasons.append("physical_authority_required")
    return {
        "schema": "dcsmizzer.terrain-point/v1",
        "authority": provenance["authority"],
        "dcs_started": False,
        "query": {
            "x": x_value,
            "y": y_value,
            "tolerance_m": tolerance,
        },
        "evidence": provenance,
        "validation": {
            "evidence_usable": not reasons,
            "failure_reasons": reasons,
        },
        "point": (
            {
                **sample,
                "sample_distance_m": distance,
            }
            if sample is not None
            else None
        ),
        "limitations": _common_limitations()
        + [
            "One sample does not establish slope, formation clearance, object "
            "collision, road access, or route-corridor safety.",
        ],
    }


def placement_report(
    evidence_path: Path,
    *,
    x: float,
    y: float,
    heading_deg: float,
    length_m: float,
    width_m: float,
    required_surface: str = "land",
    max_slope_deg: float = 5.0,
    clearance_m: float = 0.0,
    avoid_airfields: bool = True,
    taxi_buffer_m: float = 15.0,
    terrain: str | None = None,
    dcs_version: str | None = None,
) -> dict[str, Any]:
    """Check one oriented footprint against sampled terrain and obstacles."""

    evidence, provenance = _load_evidence(
        evidence_path,
        terrain=terrain,
        dcs_version=dcs_version,
    )
    center = (_coordinate(x, "x"), _coordinate(y, "y"))
    heading = _heading(heading_deg)
    length = _positive(length_m, "length_m")
    width = _positive(width_m, "width_m")
    clearance = _nonnegative(clearance_m, "clearance_m")
    taxi_buffer = _positive(taxi_buffer_m, "taxi_buffer_m")
    slope_limit = _bounded_number(max_slope_deg, "max_slope_deg", 0.0, 90.0)
    if not isinstance(required_surface, str) or required_surface not in _SURFACES:
        raise ValueError("required_surface is not a recognized terrain surface")

    tolerance = _sample_tolerance(evidence, None)
    sample_index = _SampleIndex(evidence["samples"], tolerance)
    footprint_points = [
        center,
        *_rectangle_corners(center, heading, length, width),
    ]
    resolved_samples: list[dict[str, Any]] = []
    missing_points: list[dict[str, float]] = []
    for point_x, point_y in footprint_points:
        sample, distance = sample_index.nearest(point_x, point_y)
        if sample is None:
            missing_points.append({"x": point_x, "y": point_y})
        else:
            resolved_samples.append(
                {
                    **sample,
                    "query_x": point_x,
                    "query_y": point_y,
                    "sample_distance_m": distance,
                }
            )

    reasons: list[str] = []
    if not provenance["physical_authority"]:
        reasons.append("physical_authority_required")
    if missing_points:
        reasons.append("footprint_samples_incomplete")
    samples_distinct = _samples_distinct_for_query_points(
        resolved_samples,
    )
    if not samples_distinct:
        reasons.append("footprint_samples_not_distinct")
    slope = _maximum_pairwise_sampled_slope(resolved_samples)
    object_coverage = _object_coverage_contains_footprint(
        evidence,
        center=center,
        radius_m=math.hypot(
            length / 2.0 + clearance,
            width / 2.0 + clearance,
        ),
    )
    if not object_coverage:
        reasons.append("object_search_coverage_incomplete")
    airfield_inventory_complete = (
        evidence["coverage"].get("airfield_inventory_complete") is True
    )
    airfield_geometry_complete = all(
        item.get("geometry_complete") is True
        for item in evidence["airfields"]
    )
    airfield_coverage = (
        airfield_inventory_complete and airfield_geometry_complete
    )
    if avoid_airfields and not airfield_coverage:
        if not airfield_inventory_complete:
            reasons.append("airfield_inventory_incomplete")
        if not airfield_geometry_complete:
            reasons.append("airfield_geometry_incomplete")
    surfaces_valid = (
        len(resolved_samples) == len(footprint_points)
        and all(
            sample.get("surface") == required_surface
            for sample in resolved_samples
        )
    )
    slope_valid = slope is not None and slope <= slope_limit

    footprint = _rectangle(
        center,
        heading,
        length + 2 * clearance,
        width + 2 * clearance,
    )
    collisions = _object_collisions(evidence["objects"], footprint)
    airfield_conflicts = (
        _airfield_collisions(
            evidence["airfields"],
            footprint,
            taxi_buffer_m=taxi_buffer,
        )
        if avoid_airfields
        else []
    )
    available = not reasons
    sampled_placement_valid = (
        surfaces_valid
        and slope_valid
        and not collisions
        and not airfield_conflicts
        if available
        else None
    )
    placement_valid = (
        False if sampled_placement_valid is False else None
    )
    return {
        "schema": "dcsmizzer.terrain-placement/v1",
        "authority": provenance["authority"],
        "dcs_started": False,
        "query": {
            "x": center[0],
            "y": center[1],
            "heading_deg": heading,
            "length_m": length,
            "width_m": width,
            "clearance_m": clearance,
            "required_surface": required_surface,
            "max_slope_deg": slope_limit,
            "avoid_airfields": avoid_airfields,
            "taxi_buffer_m": taxi_buffer,
        },
        "evidence": provenance,
        "coverage": {
            "required_samples": len(footprint_points),
            "resolved_samples": len(resolved_samples),
            "missing_samples": len(missing_points),
            "samples_distinct_for_query_points": samples_distinct,
            "object_search_covers_footprint": object_coverage,
            "airfield_inventory_complete": airfield_inventory_complete,
            "airfield_records_geometry_complete": airfield_geometry_complete,
            "airfield_collision_coverage_complete": airfield_coverage,
        },
        "validation": {
            "placement_valid": placement_valid,
            "sampled_placement_valid": sampled_placement_valid,
            "continuous_surface_proven": False,
            "failure_reasons": reasons,
            "surface_valid": surfaces_valid if available else None,
            "slope_valid": slope_valid if available else None,
            "maximum_sampled_slope_deg": slope,
            "object_clear": (
                not collisions
                if provenance["physical_authority"] and object_coverage
                else None
            ),
            "airfield_clear": (
                not airfield_conflicts
                if (
                    provenance["physical_authority"]
                    and avoid_airfields
                    and airfield_coverage
                )
                else None
            ),
            "airfield_check_waived": not avoid_airfields,
        },
        "missing_sample_points": missing_points[:20],
        "collisions": collisions[:20],
        "airfield_conflicts": airfield_conflicts[:20],
        "limitations": _common_limitations()
        + [
            "The result covers only the supplied oriented rectangle and "
            "declared clearance. Formation spacing and tactical suitability "
            "remain separate.",
            "Airport conflicts use exported runway/parking geometry, not an "
            "official airport boundary polygon; exported taxi routes use the "
            "reported conservative buffer.",
            "Object clearance is available only when a complete exported "
            "object search fully contains the footprint and clearance.",
            "Disabling the airfield gate explicitly waives airport-overlap "
            "coverage; it does not prove the placement is outside an airport.",
            "Surface and slope checks cover only the center and four corners; "
            "terrain between those samples is not proven continuous or clear.",
            "sampled_placement_valid is the positive sampled result; the "
            "unqualified placement_valid field is never true.",
        ],
    }


def terrain_corridor_report(
    evidence_path: Path,
    *,
    route: list[dict[str, Any]],
    half_width_m: float,
    step_m: float,
    minimum_clearance_m: float,
    limit: int = 20,
    terrain: str | None = None,
    dcs_version: str | None = None,
) -> dict[str, Any]:
    """Sample a route centerline and lateral edges against terrain height."""

    evidence, provenance = _load_evidence(
        evidence_path,
        terrain=terrain,
        dcs_version=dcs_version,
    )
    if not isinstance(route, list) or len(route) < 2:
        raise ValueError("route must contain at least two points")
    if len(route) > MAX_ROUTE_POINTS:
        raise ValueError(
            f"route exceeds the {MAX_ROUTE_POINTS}-point limit"
        )
    route_points = [_route_point(item, index) for index, item in enumerate(route)]
    half_width = _nonnegative(half_width_m, "half_width_m")
    step = _positive(step_m, "step_m")
    minimum_clearance = _nonnegative(
        minimum_clearance_m,
        "minimum_clearance_m",
    )
    query_limit = _limit(limit)
    expected = _corridor_queries(route_points, half_width, step)
    tolerance = _sample_tolerance(evidence, None)
    sample_index = _SampleIndex(evidence["samples"], tolerance)
    resolved: list[dict[str, Any]] = []
    missing: list[dict[str, float]] = []
    for query in expected:
        sample, distance = sample_index.nearest(query["x"], query["y"])
        if sample is None or not _is_number(sample.get("height_msl")):
            missing.append(
                {
                    "x": query["x"],
                    "y": query["y"],
                }
            )
            continue
        clearance = query["altitude_msl"] - sample["height_msl"]
        resolved.append(
            {
                **query,
                "terrain_height_msl": sample["height_msl"],
                "surface": sample["surface"],
                "sample_x": sample["x"],
                "sample_y": sample["y"],
                "sample_distance_m": distance,
                "clearance_m": clearance,
            }
        )
    reasons: list[str] = []
    if not provenance["physical_authority"]:
        reasons.append("physical_authority_required")
    if missing:
        reasons.append("corridor_samples_incomplete")
    samples_distinct = _samples_distinct_for_query_points(
        resolved,
        sample_x_field="sample_x",
        sample_y_field="sample_y",
        query_x_field="x",
        query_y_field="y",
    )
    if not samples_distinct:
        reasons.append("corridor_samples_not_distinct")
    available = not reasons
    hazards_all = sorted(
        [
            item
            for item in resolved
            if item["clearance_m"] < minimum_clearance
        ],
        key=lambda item: (
            item["clearance_m"],
            item["segment_index"],
            item["along_fraction"],
            item["lateral_offset_m"],
        ),
    )
    minimum_observed = (
        min(item["clearance_m"] for item in resolved) if resolved else None
    )
    return {
        "schema": "dcsmizzer.terrain-corridor/v1",
        "authority": provenance["authority"],
        "dcs_started": False,
        "query": {
            "route_points": route_points,
            "half_width_m": half_width,
            "step_m": step,
            "minimum_clearance_m": minimum_clearance,
            "limit": query_limit,
            "altitude_semantics": "MSL",
        },
        "evidence": provenance,
        "coverage": {
            "expected_sample_points": len(expected),
            "resolved_sample_points": len(resolved),
            "missing_sample_points": len(missing),
            "samples_distinct_for_query_points": samples_distinct,
            "hazards": len(hazards_all),
            "returned_hazards": min(len(hazards_all), query_limit),
            "hazards_output_truncated": len(hazards_all) > query_limit,
        },
        "validation": {
            "corridor_clear": (
                False if available and hazards_all else None
            ),
            "sampled_corridor_clear": not hazards_all if available else None,
            "continuous_corridor_proven": False,
            "minimum_observed_clearance_m": minimum_observed,
            "failure_reasons": reasons,
        },
        "hazards": hazards_all[:query_limit],
        "missing_samples": missing[:20],
        "limitations": _common_limitations()
        + [
            "The check samples three lateral traces at the requested step; "
            "terrain or scenery between samples is not covered.",
            "sampled_corridor_clear is the positive sampled result; the "
            "unqualified corridor_clear field is never true.",
            "Aircraft performance, bank angle, navigation error, weather, "
            "trees, wires, bridges, and AI path following remain separate.",
        ],
    }


def landmark_report(
    evidence_path: Path,
    *,
    query: str,
    near_x: float | None = None,
    near_y: float | None = None,
    radius_m: float | None = None,
    limit: int = 20,
    terrain: str | None = None,
    dcs_version: str | None = None,
) -> dict[str, Any]:
    """Search exported scenery-object instances by model or display name."""

    evidence, provenance = _load_evidence(
        evidence_path,
        terrain=terrain,
        dcs_version=dcs_version,
    )
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_TEXT:
        raise ValueError("query must be a nonempty bounded string")
    query_limit = _limit(limit)
    if (near_x is None) != (near_y is None):
        raise ValueError("near_x and near_y must be provided together")
    near = (
        (_coordinate(near_x, "near_x"), _coordinate(near_y, "near_y"))
        if near_x is not None and near_y is not None
        else None
    )
    radius = (
        _positive(radius_m, "radius_m") if radius_m is not None else None
    )
    if radius is not None and near is None:
        raise ValueError("radius_m requires near_x and near_y")
    folded = query.casefold()
    matches: list[dict[str, Any]] = []
    for item in evidence["objects"]:
        if folded not in item["model"].casefold() and folded not in (
            item.get("name") or ""
        ).casefold():
            continue
        distance = (
            math.hypot(
                item["center"]["x"] - near[0],
                item["center"]["y"] - near[1],
            )
            if near is not None
            else None
        )
        if radius is not None and distance is not None and distance > radius:
            continue
        matches.append(
            {
                **item,
                "distance_m": distance,
            }
        )
    matches.sort(
        key=lambda item: (
            item["distance_m"] if item["distance_m"] is not None else 0.0,
            item["model"].casefold(),
            item["center"]["x"],
            item["center"]["y"],
        )
    )
    query_coverage_complete = _landmark_query_coverage_complete(
        evidence,
        near=near,
        radius_m=radius,
    )
    exact_query_usable = provenance["physical_authority"] and bool(matches)
    failure_reasons: list[str] = []
    if not provenance["physical_authority"]:
        failure_reasons.append("physical_authority_required")
    elif not matches:
        failure_reasons.append(
            "no_matching_scenery_object"
            if query_coverage_complete
            else "object_search_coverage_incomplete"
        )
    return {
        "schema": "dcsmizzer.terrain-landmarks/v1",
        "authority": provenance["authority"],
        "dcs_started": False,
        "query": {
            "query": query,
            "near_x": near[0] if near else None,
            "near_y": near[1] if near else None,
            "radius_m": radius,
            "limit": query_limit,
        },
        "evidence": provenance,
        "coverage": {
            "matching_objects": len(matches),
            "returned_objects": min(len(matches), query_limit),
            "output_truncated": len(matches) > query_limit,
            "query_volume_covered": query_coverage_complete,
            "enumeration_complete": query_coverage_complete,
        },
        "validation": {
            "exact_query_usable": exact_query_usable,
            "absence_proven": (
                not matches
                and provenance["physical_authority"]
                and query_coverage_complete
            ),
            "failure_reasons": failure_reasons,
        },
        "landmarks": matches[:query_limit],
        "limitations": _common_limitations()
        + [
            "A matching model instance establishes DCS scenery identity and "
            "geometry only; historical naming and tactical suitability need "
            "separate evidence.",
            "A zero-result query proves absence only when a complete declared "
            "object inventory or one complete covering search volume exists.",
        ],
    }


def airfield_footprint_report(
    evidence_path: Path,
    *,
    airfield: str,
    taxi_buffer_m: float = 15.0,
    terrain: str | None = None,
    dcs_version: str | None = None,
) -> dict[str, Any]:
    """Derive bounded operational geometry without inventing an official border."""

    evidence, provenance = _load_evidence(
        evidence_path,
        terrain=terrain,
        dcs_version=dcs_version,
    )
    if not isinstance(airfield, str) or not airfield or len(airfield) > MAX_TEXT:
        raise ValueError("airfield must be a nonempty bounded string")
    taxi_buffer = _positive(taxi_buffer_m, "taxi_buffer_m")
    folded = airfield.casefold()
    matches = [
        item
        for item in evidence["airfields"]
        if folded == item["name"].casefold()
        or folded == str(item.get("airdrome_id", "")).casefold()
    ]
    inventory_complete = (
        evidence["coverage"].get("airfield_inventory_complete") is True
    )
    record_geometry_complete = (
        len(matches) == 1 and matches[0].get("geometry_complete") is True
    )
    usable = (
        provenance["physical_authority"]
        and inventory_complete
        and record_geometry_complete
        and len(matches) == 1
    )
    footprint = None
    if len(matches) == 1:
        item = matches[0]
        runway_polygons = [
            _polygon_record(
                runway["center"],
                runway["heading_deg"],
                runway["length"],
                runway["width"],
            )
            for runway in item["runways"]
        ]
        parking_polygons = [
            _parking_polygon_record(parking)
            for parking in item["parking"]
        ]
        taxi_corridors: list[dict[str, Any]] = []
        for route_index, route in enumerate(item["taxi_routes"]):
            for segment_index, (start, end) in enumerate(zip(route, route[1:])):
                dx = end["x"] - start["x"]
                dy = end["y"] - start["y"]
                segment_length = math.hypot(dx, dy)
                if segment_length <= 0:
                    raise ValueError(
                        "airfield taxi route contains a zero-length segment"
                    )
                center = {
                    "x": (start["x"] + end["x"]) / 2.0,
                    "y": (start["y"] + end["y"]) / 2.0,
                }
                taxi_corridors.append(
                    {
                        "route_index": route_index,
                        "segment_index": segment_index,
                        **_polygon_record(
                            center,
                            math.degrees(math.atan2(dy, dx)),
                            segment_length + taxi_buffer * 2,
                            taxi_buffer * 2,
                        ),
                    }
                )
        footprint = {
            "authority": "derived_geometry",
            "official_airport_boundary": False,
            "airdrome_id": item.get("airdrome_id"),
            "name": item["name"],
            "runway_polygons": runway_polygons,
            "parking_polygons": parking_polygons,
            "taxi_corridors": taxi_corridors,
            "envelope": _geometry_envelope(
                runway_polygons + parking_polygons + taxi_corridors
            ),
        }
    reasons: list[str] = []
    if not provenance["physical_authority"]:
        reasons.append("physical_authority_required")
    if not inventory_complete:
        reasons.append("airfield_inventory_incomplete")
    if len(matches) == 0:
        reasons.append("airfield_not_found")
    elif len(matches) > 1:
        reasons.append("airfield_query_ambiguous")
    elif not record_geometry_complete:
        reasons.append("airfield_geometry_incomplete")
    return {
        "schema": "dcsmizzer.airfield-footprint/v1",
        "authority": provenance["authority"],
        "dcs_started": False,
        "query": {
            "airfield": airfield,
            "taxi_buffer_m": taxi_buffer,
        },
        "evidence": provenance,
        "validation": {
            "exact_airfield_usable": usable,
            "matching_airfields": len(matches),
            "airfield_inventory_complete": inventory_complete,
            "airfield_geometry_complete": record_geometry_complete,
            "failure_reasons": reasons,
        },
        "footprint": footprint,
        "limitations": _common_limitations()
        + [
            "The envelope is a derived union envelope of exported runways, "
            "parking rectangles, and buffered taxi segments. It is not an "
            "official airport boundary, property line, or universal no-spawn "
            "zone.",
        ],
    }


def br_airfield_footprint_report(
    br_root: Path,
    terrain: str,
    airfield: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Derive a planning envelope from a commit-bound BR airbase export."""

    query_limit = _limit(limit)
    source = br_airbase_report(
        Path(br_root),
        terrain,
        airport=airfield,
        limit=None,
    )
    airbases = source.get("airbases")
    records = airbases if isinstance(airbases, list) else []
    coverage = source.get("coverage")
    source_coverage = coverage if isinstance(coverage, dict) else {}
    source_query_usable = (
        len(records) == 1
        and source_coverage.get("exact_airbase_query_usable") is True
        and source_coverage.get("airbase_parse_failures") == 0
    )
    usable = False
    footprint: dict[str, Any] | None = None
    skipped_runways = 0
    skipped_parking = 0
    if len(records) == 1:
        record = _mapping(records[0], "airbase")
        runway_polygons: list[dict[str, Any]] = []
        for runway_value in record.get("runways", []):
            try:
                runway = _mapping(runway_value, "runway")
                position = _mapping(runway.get("position"), "runway.position")
                center = {
                    "x": _coordinate(position.get("x"), "runway.position.x"),
                    "y": _coordinate(position.get("z"), "runway.position.z"),
                }
                course = _finite(
                    runway.get("course_raw_radians"),
                    "runway.course_raw_radians",
                )
                length = _positive(runway.get("length"), "runway.length")
                width = _positive(runway.get("width"), "runway.width")
            except ValueError:
                skipped_runways += 1
                continue
            runway_polygons.append(
                {
                    "runway_id": runway.get("id"),
                    **_polygon_record(
                        center,
                        math.degrees(course) % 360.0,
                        length,
                        width,
                    ),
                }
            )

        parking_circles: list[dict[str, Any]] = []
        for parking_value in record.get("parking", []):
            try:
                parking = _mapping(parking_value, "parking")
                position = _mapping(parking.get("position"), "parking.position")
                dimensions = _mapping(
                    parking.get("dimensions"),
                    "parking.dimensions",
                )
                center = {
                    "x": _coordinate(position.get("x"), "parking.position.x"),
                    "y": _coordinate(position.get("y"), "parking.position.y"),
                }
                length = _positive(
                    dimensions.get("length"),
                    "parking.dimensions.length",
                )
                width = _positive(
                    dimensions.get("width"),
                    "parking.dimensions.width",
                )
            except ValueError:
                skipped_parking += 1
                continue
            parking_circles.append(
                {
                    "slot_name": parking.get("slot_name"),
                    "center": center,
                    "radius": math.hypot(length, width) / 2.0,
                    "source_dimensions": {
                        "length": length,
                        "width": width,
                    },
                    "method": "conservative_circle_due_missing_heading",
                }
            )
        envelope = _planning_airfield_envelope(
            runway_polygons,
            parking_circles,
        )
        usable = (
            source_query_usable
            and skipped_runways == 0
            and skipped_parking == 0
            and bool(runway_polygons or parking_circles)
        )
        footprint = {
            "authority": "derived_from_commit_bound_upstream_geometry",
            "official_airport_boundary": False,
            "physical_terrain_validated": False,
            "name": record.get("name"),
            "airdrome_id": record.get("airdrome_id"),
            "runway_polygons": runway_polygons,
            "parking_clearance_circles": parking_circles[:query_limit],
            "parking_clearance_circle_count": len(parking_circles),
            "parking_output_truncated": len(parking_circles) > query_limit,
            "envelope": envelope,
        }
    reasons: list[str] = []
    if len(records) == 0:
        reasons.append("airfield_not_found")
    elif len(records) > 1:
        reasons.append("airfield_query_ambiguous")
    if source_coverage.get("airbase_parse_failures", 0) != 0:
        reasons.append("upstream_airbase_parse_incomplete")
    if len(records) == 1 and source_coverage.get(
        "exact_airbase_query_usable"
    ) is not True:
        reasons.append("upstream_exact_airbase_query_unusable")
    if skipped_runways:
        reasons.append("runway_geometry_incomplete")
    if skipped_parking:
        reasons.append("parking_geometry_incomplete")
    if (
        len(records) == 1
        and not skipped_runways
        and not skipped_parking
        and footprint is not None
        and footprint["envelope"] is None
    ):
        reasons.append("airfield_geometry_empty")
    return {
        "schema": "dcsmizzer.br-airfield-footprint/v1",
        "authority": "commit_bound_upstream_planning_geometry",
        "dcs_started": False,
        "query": {
            "terrain": terrain,
            "airfield": airfield,
            "limit": query_limit,
        },
        "source": {
            "schema": source.get("schema"),
            "authority": source.get("authority"),
            "source": source.get("source"),
            "source_sha256": source.get("source_sha256"),
            "upstream": source.get("upstream"),
            "upstream_project_version": source.get(
                "upstream_project_version"
            ),
        },
        "coverage": {
            "matching_airfields": len(records),
            "skipped_runways": skipped_runways,
            "skipped_parking": skipped_parking,
        },
        "validation": {
            "planning_footprint_usable": usable,
            "physical_validation": False,
            "failure_reasons": reasons,
        },
        "footprint": footprint,
        "limitations": [
            "This planning envelope uses a commit-bound BriefingRoom export; "
            "it is not current initialized DCS terrain evidence.",
            "Runway rectangles convert the exported DCS runway course from "
            "radians. Parking headings are absent, so each stand uses a "
            "conservative half-diagonal circle.",
            "The envelope is not an official airport boundary, taxiway map, "
            "property line, universal no-spawn zone, or surface/collision "
            "validation.",
            "Use a matching initialized Mission Editor terrain export when "
            "physical runway, parking, taxi, or obstacle validity matters.",
            "No DCS, Mission Editor, or upstream code was executed.",
        ],
    }


def _load_evidence(
    path: Path,
    *,
    terrain: str | None,
    dcs_version: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(terrain, str) or not terrain:
        raise ValueError(
            "terrain is required to bind physical evidence to the task"
        )
    if not isinstance(dcs_version, str) or not dcs_version:
        raise ValueError(
            "dcs_version is required to bind physical evidence to the task"
        )
    payload, identity = _read_bounded_file(path)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {_bounded_text(key)}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    try:
        data = json.loads(
            payload.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError("terrain evidence is not valid UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise ValueError("terrain evidence is not valid JSON") from error
    _validate_json_graph(data)
    _validate_evidence(data)
    if data["terrain"].casefold() != terrain.casefold():
        raise ValueError(
            "terrain evidence terrain does not match the requested terrain"
        )
    product_version = data["dcs"]["product_version"]
    if product_version != dcs_version:
        raise ValueError(
            "terrain evidence DCS version does not match the requested version"
        )
    export = data["export"]
    physical_authority = (
        export["kind"] in _PHYSICAL_EXPORT_KINDS
        and export["runtime_initialized"] is True
    )
    version_basis = data["dcs"].get(
        "product_version_basis",
        data["dcs"].get("product_version_source", "unspecified"),
    )
    version_runtime_attested = data["dcs"].get(
        "runtime_identity_attested",
        version_basis == "runtime_attested",
    ) is True
    authority = (
        (
            "version_bound_initialized_dcs_terrain_api_export"
            if version_runtime_attested
            else "initialized_dcs_terrain_api_export_with_declared_version"
        )
        if physical_authority
        else "nonphysical_planning_or_uninitialized_evidence"
    )
    provenance = {
        "path_name": Path(path).name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "file_identity": identity,
        "schema": data["schema"],
        "terrain": data["terrain"],
        "dcs": data["dcs"],
        "export": data["export"],
        "coverage": {
            "sampling_design": data["coverage"].get("sampling_design"),
            "sample_spacing_m": data["coverage"].get("sample_spacing_m"),
            "sample_match_tolerance_m": data["coverage"][
                "sample_match_tolerance_m"
            ],
            "object_inventory_complete": data["coverage"].get(
                "object_inventory_complete",
                False,
            ),
            "object_search_complete": data["coverage"].get(
                "object_search_complete",
                False,
            ),
            "object_search_complete_for_ground_placement": data[
                "coverage"
            ].get(
                "object_search_complete_for_ground_placement",
                False,
            ),
            "object_search_count": len(
                data["coverage"].get("object_searches", [])
            ),
            "airfield_inventory_complete": data["coverage"].get(
                "airfield_inventory_complete",
                False,
            ),
        },
        "authority": authority,
        "physical_authority": physical_authority,
        "product_version_basis": version_basis,
        "runtime_version_attested": version_runtime_attested,
        "identity_source": data["dcs"].get("identity_source"),
    }
    return data, provenance


def _read_bounded_file(path: Path) -> tuple[bytes, dict[str, Any]]:
    candidate = Path(path)
    try:
        path_before = candidate.lstat()
    except OSError as error:
        raise ValueError("cannot inspect terrain evidence file") from error
    if (
        not stat.S_ISREG(path_before.st_mode)
        or _status_is_reparse_point(path_before)
    ):
        raise ValueError(
            "terrain evidence path is not a safe regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise ValueError("cannot open terrain evidence file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("terrain evidence path is not a regular file")
        if _status_is_reparse_point(before):
            raise ValueError("terrain evidence path is a reparse point")
        if (path_before.st_dev, path_before.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise ValueError(
                "terrain evidence changed before it could be read"
            )
        if before.st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("terrain evidence exceeds the size limit")
        chunks: list[bytes] = []
        remaining = MAX_EVIDENCE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_EVIDENCE_BYTES:
            raise ValueError("terrain evidence exceeds the size limit")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("terrain evidence changed while being read")
        try:
            path_after = candidate.lstat()
        except OSError as error:
            raise ValueError(
                "terrain evidence changed while being read"
            ) from error
        if (
            not stat.S_ISREG(path_after.st_mode)
            or _status_is_reparse_point(path_after)
            or (path_after.st_dev, path_after.st_ino)
            != (after.st_dev, after.st_ino)
        ):
            raise ValueError("terrain evidence changed while being read")
        if len(payload) != before.st_size:
            raise ValueError("terrain evidence could not be read completely")
        return payload, {
            "size_bytes": before.st_size,
            "device": before.st_dev,
            "inode": before.st_ino,
            "mtime_ns": before.st_mtime_ns,
        }
    finally:
        os.close(descriptor)


def _validate_json_graph(root: Any) -> None:
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("terrain evidence exceeds the JSON depth limit")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number is forbidden")


def _validate_evidence(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("terrain evidence root must be an object")
    if data.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("terrain evidence schema is not supported")
    _text(data.get("terrain"), "terrain")
    dcs = _mapping(data.get("dcs"), "dcs")
    _text(dcs.get("product_version"), "dcs.product_version")
    if dcs.get("product_version_basis") is not None:
        _text(
            dcs.get("product_version_basis"),
            "dcs.product_version_basis",
        )
    for field in ("identity_source", "product_version_source"):
        if dcs.get(field) is not None:
            _text(dcs.get(field), f"dcs.{field}")
    if dcs.get("runtime_identity_attested") is not None and not isinstance(
        dcs.get("runtime_identity_attested"),
        bool,
    ):
        raise ValueError("dcs.runtime_identity_attested must be boolean")
    build = dcs.get("steam_build_id")
    if build is not None:
        _text(build, "dcs.steam_build_id")
    export = _mapping(data.get("export"), "export")
    _text(export.get("kind"), "export.kind")
    if not isinstance(export.get("runtime_initialized"), bool):
        raise ValueError("export.runtime_initialized must be boolean")
    if export.get("created_utc") is not None:
        _text(export.get("created_utc"), "export.created_utc")
    coverage = _mapping(data.get("coverage"), "coverage")
    if coverage.get("sample_spacing_m") is not None:
        _positive(
            coverage.get("sample_spacing_m"),
            "coverage.sample_spacing_m",
        )
    _bounded_number(
        coverage.get("sample_match_tolerance_m"),
        "coverage.sample_match_tolerance_m",
        MIN_SAMPLE_TOLERANCE_M,
        MAX_SAMPLE_TOLERANCE_M,
    )
    for field in (
        "object_inventory_complete",
        "object_search_complete",
        "object_search_complete_for_ground_placement",
        "airfield_inventory_complete",
    ):
        if coverage.get(field) is not None and not isinstance(
            coverage.get(field),
            bool,
        ):
            raise ValueError(f"coverage.{field} must be boolean")
    object_searches = _bounded_list(
        coverage.get("object_searches", []),
        "coverage.object_searches",
        MAX_OBJECT_SEARCHES,
    )
    for index, search_value in enumerate(object_searches):
        search = _mapping(
            search_value,
            f"coverage.object_searches[{index}]",
        )
        _coordinate(
            search.get("x"),
            f"coverage.object_searches[{index}].x",
        )
        _coordinate(
            search.get("y"),
            f"coverage.object_searches[{index}].y",
        )
        _positive(
            search.get("radius_m"),
            f"coverage.object_searches[{index}].radius_m",
        )
        volume_kind = search.get("volume_kind")
        if volume_kind is not None:
            _text(
                volume_kind,
                f"coverage.object_searches[{index}].volume_kind",
            )
        for field in ("minimum_altitude_msl", "maximum_altitude_msl"):
            if search.get(field) is not None:
                _finite(
                    search.get(field),
                    f"coverage.object_searches[{index}].{field}",
                )
        minimum_altitude = search.get("minimum_altitude_msl")
        maximum_altitude = search.get("maximum_altitude_msl")
        if (
            minimum_altitude is not None
            and maximum_altitude is not None
            and float(minimum_altitude) >= float(maximum_altitude)
        ):
            raise ValueError(
                "object-search vertical range must increase"
            )
        if search.get("complete_for_ground_placement") is not None and not (
            isinstance(search.get("complete_for_ground_placement"), bool)
        ):
            raise ValueError(
                "object-search ground-placement completeness must be boolean"
            )
    samples = _bounded_list(data.get("samples"), "samples", MAX_SAMPLES)
    duplicate_samples: dict[tuple[float, float], tuple[Any, Any]] = {}
    for index, sample_value in enumerate(samples):
        sample = _mapping(sample_value, f"samples[{index}]")
        x = _coordinate(sample.get("x"), f"samples[{index}].x")
        y = _coordinate(sample.get("y"), f"samples[{index}].y")
        height = _finite(sample.get("height_msl"), f"samples[{index}].height_msl")
        surface = sample.get("surface")
        if surface not in _SURFACES:
            raise ValueError(f"samples[{index}].surface is not recognized")
        signature = (height, surface)
        key = (x, y)
        if key in duplicate_samples and duplicate_samples[key] != signature:
            raise ValueError("terrain evidence has conflicting duplicate samples")
        duplicate_samples[key] = signature
    objects = _bounded_list(data.get("objects"), "objects", MAX_OBJECTS)
    for index, object_value in enumerate(objects):
        item = _mapping(object_value, f"objects[{index}]")
        _text(item.get("model"), f"objects[{index}].model")
        if item.get("name") is not None:
            _text(item["name"], f"objects[{index}].name")
        _point(item.get("center"), f"objects[{index}].center")
        if item.get("heading_deg") is not None:
            _heading(item.get("heading_deg"))
        if item.get("radius") is not None:
            _positive(item["radius"], f"objects[{index}].radius")
        size = item.get("size_obb")
        if size is not None:
            if item.get("heading_deg") is None:
                raise ValueError(
                    "terrain object size_obb requires heading_deg"
                )
            size_map = _mapping(size, f"objects[{index}].size_obb")
            _positive(size_map.get("length"), f"objects[{index}].size_obb.length")
            _positive(size_map.get("width"), f"objects[{index}].size_obb.width")
        if size is None and item.get("radius") is None:
            raise ValueError("terrain object requires size_obb or radius")
    airfields = _bounded_list(data.get("airfields"), "airfields", MAX_AIRFIELDS)
    for index, airfield_value in enumerate(airfields):
        item = _mapping(airfield_value, f"airfields[{index}]")
        _text(item.get("name"), f"airfields[{index}].name")
        if item.get("geometry_complete") is not None and not isinstance(
            item.get("geometry_complete"),
            bool,
        ):
            raise ValueError("airfield geometry_complete must be boolean")
        if item.get("airdrome_id") is not None and (
            isinstance(item["airdrome_id"], bool)
            or not isinstance(item["airdrome_id"], (int, str))
        ):
            raise ValueError("airfield airdrome_id must be an integer or string")
        runways = _bounded_list(
            item.get("runways"),
            f"airfields[{index}].runways",
            100,
        )
        for runway_index, runway_value in enumerate(runways):
            runway = _mapping(
                runway_value,
                f"airfields[{index}].runways[{runway_index}]",
            )
            _point(runway.get("center"), "runway.center")
            _heading(runway.get("heading_deg"))
            _positive(runway.get("length"), "runway.length")
            _positive(runway.get("width"), "runway.width")
        parking = _bounded_list(
            item.get("parking"),
            f"airfields[{index}].parking",
            10_000,
        )
        for parking_index, parking_value in enumerate(parking):
            parking_item = _mapping(
                parking_value,
                f"airfields[{index}].parking[{parking_index}]",
            )
            _point(parking_item.get("position"), "parking.position")
            if parking_item.get("heading_deg") is not None:
                _heading(parking_item.get("heading_deg"))
            _positive(parking_item.get("length"), "parking.length")
            _positive(parking_item.get("width"), "parking.width")
        routes = _bounded_list(
            item.get("taxi_routes"),
            f"airfields[{index}].taxi_routes",
            10_000,
        )
        for route_index, route_value in enumerate(routes):
            route = _bounded_list(
                route_value,
                f"airfields[{index}].taxi_routes[{route_index}]",
                100_000,
            )
            if len(route) < 2:
                raise ValueError("taxi route must contain at least two points")
            previous: dict[str, float] | None = None
            for point_index, point_value in enumerate(route):
                point = _point(
                    point_value,
                    (
                        f"airfields[{index}].taxi_routes[{route_index}]"
                        f"[{point_index}]"
                    ),
                )
                if previous is not None and (
                    point["x"] == previous["x"]
                    and point["y"] == previous["y"]
                ):
                    raise ValueError(
                        "taxi route contains a zero-length segment"
                    )
                previous = point
        if (
            item.get("geometry_complete") is True
            and not runways
            and not parking
            and not routes
        ):
            raise ValueError(
                "complete airfield geometry must contain at least one record"
            )


class _SampleIndex:
    """Tolerance-sized spatial buckets with deterministic nearest ties."""

    def __init__(
        self,
        samples: list[dict[str, Any]],
        tolerance: float,
    ) -> None:
        self._tolerance = tolerance
        self._buckets: dict[
            tuple[int, int],
            list[tuple[int, dict[str, Any]]],
        ] = {}
        for index, sample in enumerate(samples):
            key = self._cell(sample["x"], sample["y"])
            self._buckets.setdefault(key, []).append((index, sample))

    def nearest(
        self,
        x: float,
        y: float,
    ) -> tuple[dict[str, Any] | None, float | None]:
        cell_x, cell_y = self._cell(x, y)
        best: dict[str, Any] | None = None
        best_key = (math.inf, math.inf)
        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                for index, sample in self._buckets.get(
                    (cell_x + offset_x, cell_y + offset_y),
                    (),
                ):
                    distance = math.hypot(sample["x"] - x, sample["y"] - y)
                    candidate_key = (distance, index)
                    if candidate_key < best_key:
                        best = sample
                        best_key = candidate_key
        if best is None or best_key[0] > self._tolerance:
            return None, None
        return dict(best), best_key[0]

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return (
            math.floor(x / self._tolerance),
            math.floor(y / self._tolerance),
        )


def _sample_tolerance(
    evidence: dict[str, Any],
    requested: float | None,
) -> float:
    evidence_tolerance = _bounded_number(
        evidence["coverage"]["sample_match_tolerance_m"],
        "coverage.sample_match_tolerance_m",
        MIN_SAMPLE_TOLERANCE_M,
        MAX_SAMPLE_TOLERANCE_M,
    )
    if requested is None:
        return evidence_tolerance
    requested_tolerance = _bounded_number(
        requested,
        "tolerance_m",
        MIN_SAMPLE_TOLERANCE_M,
        MAX_SAMPLE_TOLERANCE_M,
    )
    if requested_tolerance > evidence_tolerance:
        raise ValueError(
            "tolerance_m cannot exceed the evidence-declared tolerance"
        )
    return requested_tolerance


def _samples_distinct_for_query_points(
    records: list[dict[str, Any]],
    *,
    sample_x_field: str = "x",
    sample_y_field: str = "y",
    query_x_field: str = "query_x",
    query_y_field: str = "query_y",
) -> bool:
    bindings: dict[
        tuple[float, float],
        set[tuple[float, float]],
    ] = {}
    for item in records:
        sample_key = (
            float(item[sample_x_field]),
            float(item[sample_y_field]),
        )
        query_key = (
            float(item[query_x_field]),
            float(item[query_y_field]),
        )
        bindings.setdefault(sample_key, set()).add(query_key)
    return all(len(query_points) == 1 for query_points in bindings.values())


def _maximum_pairwise_sampled_slope(
    samples: list[dict[str, Any]],
) -> float | None:
    maximum: float | None = None
    for index, left in enumerate(samples):
        for right in samples[index + 1 :]:
            distance = math.hypot(
                right["x"] - left["x"],
                right["y"] - left["y"],
            )
            if distance <= 0:
                continue
            slope = math.degrees(
                math.atan(
                    abs(right["height_msl"] - left["height_msl"])
                    / distance
                )
            )
            maximum = slope if maximum is None else max(maximum, slope)
    return maximum


def _object_coverage_contains_footprint(
    evidence: dict[str, Any],
    *,
    center: tuple[float, float],
    radius_m: float,
) -> bool:
    coverage = evidence["coverage"]
    if coverage.get("object_inventory_complete") is True:
        return True
    if (
        coverage.get("object_search_complete") is not True
        or coverage.get(
            "object_search_complete_for_ground_placement"
        )
        is not True
    ):
        return False
    for search_value in coverage.get("object_searches", []):
        search = _mapping(search_value, "coverage.object_searches")
        if _box_search_contains_circle(
            search,
            center=center,
            radius_m=radius_m,
        ):
            return True
    return False


def _landmark_query_coverage_complete(
    evidence: dict[str, Any],
    *,
    near: tuple[float, float] | None,
    radius_m: float | None,
) -> bool:
    coverage = evidence["coverage"]
    if coverage.get("object_inventory_complete") is True:
        return True
    if near is None:
        return False
    if radius_m is None:
        return False
    if coverage.get("object_search_complete") is not True:
        return False
    return any(
        _box_search_contains_circle(
            _mapping(value, "coverage.object_searches"),
            center=near,
            radius_m=radius_m,
        )
        for value in coverage.get("object_searches", [])
    )


def _box_search_contains_circle(
    search: dict[str, Any],
    *,
    center: tuple[float, float],
    radius_m: float,
) -> bool:
    return (
        search.get("volume_kind") == "box_3d"
        and search.get("complete_for_ground_placement") is True
        and _is_number(search.get("minimum_altitude_msl"))
        and _is_number(search.get("maximum_altitude_msl"))
        and abs(search["x"] - center[0]) + radius_m
        <= search["radius_m"]
        and abs(search["y"] - center[1]) + radius_m
        <= search["radius_m"]
    )


def _rectangle(
    center: tuple[float, float],
    heading_deg: float,
    length: float,
    width: float,
) -> dict[str, Any]:
    return {
        "center": center,
        "heading_deg": heading_deg,
        "half_length": length / 2.0,
        "half_width": width / 2.0,
    }


def _rectangle_corners(
    center: tuple[float, float],
    heading_deg: float,
    length: float,
    width: float,
) -> list[tuple[float, float]]:
    angle = math.radians(heading_deg)
    forward = (math.cos(angle), math.sin(angle))
    right = (-math.sin(angle), math.cos(angle))
    half_length = length / 2.0
    half_width = width / 2.0
    return [
        (
            center[0] + forward[0] * sx * half_length + right[0] * sy * half_width,
            center[1] + forward[1] * sx * half_length + right[1] * sy * half_width,
        )
        for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))
    ]


def _rectangles_intersect(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_axes = _rectangle_axes(left["heading_deg"])
    right_axes = _rectangle_axes(right["heading_deg"])
    delta = (
        right["center"][0] - left["center"][0],
        right["center"][1] - left["center"][1],
    )
    for axis in (*left_axes, *right_axes):
        distance = abs(delta[0] * axis[0] + delta[1] * axis[1])
        left_radius = _projection_radius(left, axis)
        right_radius = _projection_radius(right, axis)
        if distance > left_radius + right_radius:
            return False
    return True


def _rectangle_axes(heading_deg: float) -> tuple[tuple[float, float], ...]:
    angle = math.radians(heading_deg)
    return (
        (math.cos(angle), math.sin(angle)),
        (-math.sin(angle), math.cos(angle)),
    )


def _projection_radius(rectangle: dict[str, Any], axis: tuple[float, float]) -> float:
    forward, right = _rectangle_axes(rectangle["heading_deg"])
    return (
        rectangle["half_length"]
        * abs(forward[0] * axis[0] + forward[1] * axis[1])
        + rectangle["half_width"]
        * abs(right[0] * axis[0] + right[1] * axis[1])
    )


def _object_collisions(
    objects: list[dict[str, Any]],
    footprint: dict[str, Any],
) -> list[dict[str, Any]]:
    collisions: list[dict[str, Any]] = []
    for item in objects:
        center = (item["center"]["x"], item["center"]["y"])
        size = item.get("size_obb")
        methods: list[str] = []
        collides = False
        if size is not None:
            obstacle = _rectangle(
                center,
                item["heading_deg"],
                size["length"],
                size["width"],
            )
            if _rectangles_intersect(footprint, obstacle):
                collides = True
                methods.append("oriented_bounding_box")
        if item.get("radius") is not None:
            radius = item["radius"]
            footprint_radius = math.hypot(
                footprint["half_length"],
                footprint["half_width"],
            )
            if (
                math.hypot(
                    center[0] - footprint["center"][0],
                    center[1] - footprint["center"][1],
                )
                <= radius + footprint_radius
            ):
                collides = True
                methods.append("conservative_bounding_circle")
        if collides:
            collisions.append(
                {
                    "model": item["model"],
                    "name": item.get("name"),
                    "center": item["center"],
                    "method": "_or_".join(methods),
                }
            )
    return sorted(
        collisions,
        key=lambda item: (
            item["model"].casefold(),
            item["center"]["x"],
            item["center"]["y"],
        ),
    )


def _airfield_collisions(
    airfields: list[dict[str, Any]],
    footprint: dict[str, Any],
    *,
    taxi_buffer_m: float,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for item in airfields:
        for index, record in enumerate(item["runways"]):
            center = record["center"]
            obstacle = _rectangle(
                (center["x"], center["y"]),
                record["heading_deg"],
                record["length"],
                record["width"],
            )
            if _rectangles_intersect(footprint, obstacle):
                conflicts.append(
                    _airfield_conflict(item, "runway", index)
                )
        for index, record in enumerate(item["parking"]):
            center = record["position"]
            heading = record.get("heading_deg")
            if heading is None:
                parking_radius = math.hypot(
                    record["length"],
                    record["width"],
                ) / 2.0
                footprint_radius = math.hypot(
                    footprint["half_length"],
                    footprint["half_width"],
                )
                collides = (
                    math.hypot(
                        center["x"] - footprint["center"][0],
                        center["y"] - footprint["center"][1],
                    )
                    <= parking_radius + footprint_radius
                )
                method = "conservative_bounding_circle"
            else:
                obstacle = _rectangle(
                    (center["x"], center["y"]),
                    heading,
                    record["length"],
                    record["width"],
                )
                collides = _rectangles_intersect(footprint, obstacle)
                method = "oriented_bounding_box"
            if collides:
                conflict = _airfield_conflict(item, "parking", index)
                conflict["method"] = method
                conflicts.append(conflict)
        for route_index, route in enumerate(item["taxi_routes"]):
            for segment_index, (start, end) in enumerate(
                zip(route, route[1:])
            ):
                dx = end["x"] - start["x"]
                dy = end["y"] - start["y"]
                length = math.hypot(dx, dy)
                if length <= 0:
                    raise ValueError(
                        "airfield taxi route contains a zero-length segment"
                    )
                obstacle = _rectangle(
                    (
                        (start["x"] + end["x"]) / 2.0,
                        (start["y"] + end["y"]) / 2.0,
                    ),
                    math.degrees(math.atan2(dy, dx)),
                    length + 2.0 * taxi_buffer_m,
                    2.0 * taxi_buffer_m,
                )
                if _rectangles_intersect(footprint, obstacle):
                    conflicts.append(
                        {
                            **_airfield_conflict(
                                item,
                                "taxi_route",
                                route_index,
                            ),
                            "segment_index": segment_index,
                            "method": "buffered_segment_rectangle",
                        }
                    )
    return conflicts


def _airfield_conflict(
    airfield: dict[str, Any],
    geometry: str,
    index: int,
) -> dict[str, Any]:
    return {
        "airfield": airfield["name"],
        "airdrome_id": airfield.get("airdrome_id"),
        "geometry": geometry,
        "index": index,
    }


def _corridor_queries(
    route: list[dict[str, float]],
    half_width: float,
    step: float,
) -> list[dict[str, float | int]]:
    result: list[dict[str, float | int]] = []
    lateral_offsets = (
        (-half_width, 0.0, half_width) if half_width > 0 else (0.0,)
    )
    seen: set[tuple[int, int, int]] = set()
    query_upper_bound = 0
    for segment_index, (start, end) in enumerate(zip(route, route[1:])):
        dx = end["x"] - start["x"]
        dy = end["y"] - start["y"]
        distance = math.hypot(dx, dy)
        if distance <= 0:
            raise ValueError("route contains a zero-length segment")
        sample_ratio = distance / step
        lateral_count = len(lateral_offsets)
        if (
            not math.isfinite(sample_ratio)
            or sample_ratio
            > MAX_CORRIDOR_SAMPLE_QUERIES / lateral_count
        ):
            raise ValueError("terrain corridor exceeds the sample-query limit")
        sample_count = max(1, math.ceil(sample_ratio))
        query_upper_bound += (sample_count + 1) * lateral_count
        if query_upper_bound > MAX_CORRIDOR_SAMPLE_QUERIES:
            raise ValueError("terrain corridor exceeds the sample-query limit")
        right = (-dy / distance, dx / distance)
        for sample_index in range(sample_count + 1):
            fraction = sample_index / sample_count
            center_x = start["x"] + dx * fraction
            center_y = start["y"] + dy * fraction
            altitude = start["altitude_msl"] + (
                end["altitude_msl"] - start["altitude_msl"]
            ) * fraction
            for lateral in lateral_offsets:
                x = center_x + right[0] * lateral
                y = center_y + right[1] * lateral
                key = (round(x * 1000), round(y * 1000), round(altitude * 1000))
                if key in seen:
                    continue
                seen.add(key)
                result.append(
                    {
                        "segment_index": segment_index,
                        "along_fraction": fraction,
                        "lateral_offset_m": lateral,
                        "x": x,
                        "y": y,
                        "altitude_msl": altitude,
                    }
                )
    return result


def _route_point(value: Any, index: int) -> dict[str, float]:
    item = _mapping(value, f"route[{index}]")
    return {
        "x": _coordinate(item.get("x"), f"route[{index}].x"),
        "y": _coordinate(item.get("y"), f"route[{index}].y"),
        "altitude_msl": _finite(
            item.get("altitude_msl"),
            f"route[{index}].altitude_msl",
        ),
    }


def _polygon_record(
    center: dict[str, float],
    heading_deg: float,
    length: float,
    width: float,
) -> dict[str, Any]:
    corners = _rectangle_corners(
        (center["x"], center["y"]),
        heading_deg,
        length,
        width,
    )
    return {
        "center": dict(center),
        "heading_deg": heading_deg,
        "length": length,
        "width": width,
        "polygon": [
            {"x": x, "y": y} for x, y in (*corners, corners[0])
        ],
    }


def _parking_polygon_record(parking: dict[str, Any]) -> dict[str, Any]:
    heading = parking.get("heading_deg")
    if heading is not None:
        return {
            **_polygon_record(
                parking["position"],
                heading,
                parking["length"],
                parking["width"],
            ),
            "method": "oriented_bounding_box",
        }
    diameter = math.hypot(
        parking["length"],
        parking["width"],
    )
    return {
        **_polygon_record(
            parking["position"],
            0.0,
            diameter,
            diameter,
        ),
        "method": "conservative_square_due_missing_heading",
    }


def _geometry_envelope(records: Iterable[dict[str, Any]]) -> dict[str, float] | None:
    points = [
        point
        for record in records
        for point in record.get("polygon", [])
    ]
    if not points:
        return None
    return {
        "minimum_x": min(point["x"] for point in points),
        "maximum_x": max(point["x"] for point in points),
        "minimum_y": min(point["y"] for point in points),
        "maximum_y": max(point["y"] for point in points),
    }


def _planning_airfield_envelope(
    runway_polygons: list[dict[str, Any]],
    parking_circles: list[dict[str, Any]],
) -> dict[str, float] | None:
    bounds: list[tuple[float, float, float, float]] = []
    for runway in runway_polygons:
        polygon = runway.get("polygon")
        if not isinstance(polygon, list) or not polygon:
            continue
        points = [
            point
            for point in polygon
            if isinstance(point, dict)
            and _is_number(point.get("x"))
            and _is_number(point.get("y"))
        ]
        if points:
            bounds.append(
                (
                    min(point["x"] for point in points),
                    max(point["x"] for point in points),
                    min(point["y"] for point in points),
                    max(point["y"] for point in points),
                )
            )
    for parking in parking_circles:
        center = parking["center"]
        radius = parking["radius"]
        bounds.append(
            (
                center["x"] - radius,
                center["x"] + radius,
                center["y"] - radius,
                center["y"] + radius,
            )
        )
    if not bounds:
        return None
    return {
        "minimum_x": min(item[0] for item in bounds),
        "maximum_x": max(item[1] for item in bounds),
        "minimum_y": min(item[2] for item in bounds),
        "maximum_y": max(item[3] for item in bounds),
    }


def _common_limitations() -> list[str]:
    return [
        "The command consumes a supplied evidence export and does not start "
        "DCS or Mission Editor.",
        "Physical conclusions require an initialized DCS terrain-API export "
        "whose exact terrain and DCS version match the requested task.",
        "Planning snapshots, public GIS data, projections, and nearby observed "
        "mission points remain candidates and cannot pass physical validation.",
        "The evidence file is bounded and hashed, but its producer identity "
        "and authenticity are not cryptographically attested.",
    ]


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _bounded_list(value: Any, path: str, maximum: int) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    if len(value) > maximum:
        raise ValueError(f"{path} exceeds its record limit")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise ValueError(f"{path} must be a nonempty bounded string")
    return value


def _bounded_text(value: Any) -> str:
    return str(value)[:128]


def _point(value: Any, path: str) -> dict[str, float]:
    item = _mapping(value, path)
    _coordinate(item.get("x"), f"{path}.x")
    _coordinate(item.get("y"), f"{path}.y")
    return item


def _finite(value: Any, path: str) -> float:
    if not _is_number(value) or not math.isfinite(float(value)):
        raise ValueError(f"{path} must be a finite number")
    return float(value)


def _coordinate(value: Any, path: str) -> float:
    result = _finite(value, path)
    if abs(result) > MAX_ABS_COORDINATE:
        raise ValueError(f"{path} is outside the supported coordinate range")
    return result


def _positive(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result <= 0:
        raise ValueError(f"{path} must be positive")
    return result


def _nonnegative(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result < 0:
        raise ValueError(f"{path} must be nonnegative")
    return result


def _bounded_number(value: Any, path: str, minimum: float, maximum: float) -> float:
    result = _finite(value, path)
    if result < minimum or result > maximum:
        raise ValueError(f"{path} must be from {minimum} to {maximum}")
    return result


def _heading(value: Any) -> float:
    result = _finite(value, "heading_deg")
    if result < -360.0 or result > 360.0:
        raise ValueError("heading_deg must be from -360 to 360")
    return result % 360.0


def _limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _status_is_reparse_point(status_result: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(attribute and file_attributes & attribute)
