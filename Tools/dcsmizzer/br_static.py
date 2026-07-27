"""Safe, commit-bound terrain queries over a BriefingRoom checkout.

BriefingRoom's exported JSON extends map coverage beyond the current pydcs
terrain set.  These readers never execute upstream code and intentionally
return bounded records instead of copying the large source databases.
"""

from __future__ import annotations

import configparser
import gzip
import hashlib
import heapq
import ipaddress
import json
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

from .upstream_cache import upstream_source_lock_status


_SPAWN_CHUNK_CHARS = 1024 * 1024
_TERMINAL_CAPABILITIES = {
    "OpenAirSpawn": (True, True),
    "HardenedAirShelter": (True, False),
    "AirplaneOnly": (True, False),
    "SmallAirplane": (True, False),
    "HelicopterOnly": (False, True),
}


def br_terrain_report(
    br_root: Path,
    *,
    terrain: str | None = None,
) -> dict[str, Any]:
    """Catalog every exported BriefingRoom theatre and bounded map geometry."""

    root = _validated_root(br_root)
    upstream = _git_state(root)
    entries = _theatre_entries(root)
    airbases, airbase_source = _load_airbases(root)
    airbase_counts = Counter(
        item.get("theatre")
        for item in airbases
        if isinstance(item.get("theatre"), str)
    )
    selected_entries = [
        entry
        for entry in entries
        if terrain is None
        or entry["dcs_id"].casefold() == terrain.casefold()
        or entry["declaration_id"].casefold() == terrain.casefold()
        or entry["display_name"].casefold() == terrain.casefold()
    ]

    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    dcs_id_counts = Counter(
        entry["dcs_id"].casefold() for entry in entries
    )
    duplicate_dcs_ids = sorted(
        {
            entry["dcs_id"]
            for entry in entries
            if dcs_id_counts[entry["dcs_id"].casefold()] > 1
        },
        key=str.casefold,
    )
    for entry in selected_entries:
        bounds_source = _contained_source(
            root,
            root / "DatabaseJSON" / "TheaterTerrainBounds",
            f"{entry['dcs_id']}.json",
        )
        try:
            bounds = _bounds_summary(bounds_source)
        except ValueError:
            unresolved.append(entry["dcs_id"])
            continue
        records.append(
            {
                **entry,
                "airbases": airbase_counts[entry["dcs_id"]],
                "sea_mask_planning_geometry": bounds,
                "sources": [
                    {
                        "kind": "theatre_declaration",
                        "source": entry["source"],
                        "source_sha256": entry["source_sha256"],
                    },
                    {
                        "kind": "terrain_bounds",
                        "source": bounds_source.relative_to(root).as_posix(),
                        "source_sha256": _sha256(bounds_source),
                    },
                ],
            }
        )

    exact_query_usable = (
        terrain is None
        or (
            len(selected_entries) == 1
            and len(records) == 1
            and not unresolved
            and selected_entries[0]["dcs_id"].casefold()
            not in {
                value.casefold()
                for value in duplicate_dcs_ids
            }
        )
    )
    return {
        "schema": "dcsmizzer.br-terrains/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_exported_terrain_database",
        ),
        "dcs_started": False,
        "filters": {"terrain": terrain},
        "upstream": upstream,
        "upstream_project_version": _project_version_evidence(root),
        "airbase_source": {
            "source": airbase_source.relative_to(root).as_posix(),
            "source_sha256": _sha256(airbase_source),
        },
        "coverage": {
            "theatre_declarations": len(entries),
            "matching_theatres": len(selected_entries),
            "theatres_parsed": len(records),
            "terrain_bounds_unresolved": unresolved,
            "duplicate_dcs_ids": duplicate_dcs_ids,
            "airbases_indexed": len(airbases),
            "exact_query_usable": exact_query_usable,
        },
        "terrains": records,
        "limitations": [
            "The report covers exported data in the reported BriefingRoom "
            "source snapshot; it is not the initialized registry of the user's current "
            "DCS version.",
            "The exported landMasses/waters polygons are BriefingRoom sea-mask "
            "planning geometry, not rectangular map bounds or proof of current "
            "terrain height, collision, land class, or placement validity.",
            "The project-level targeted DCS version does not prove that every "
            "bounds or spawn-point file was regenerated for that version.",
            "The official public terrain catalog may contain products which "
            "share one DCS theatre ID; product names are not inferred here.",
            "No upstream C#, JavaScript, Lua, or other code was executed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def br_airbase_report(
    br_root: Path,
    terrain: str,
    *,
    airport: str | None = None,
    airdrome_id: int | None = None,
    parking: str | None = None,
    airplane_only: bool = False,
    helicopter_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Query exact exported airbase, runway, and parking-stand records."""

    root = _validated_root(br_root)
    upstream = _git_state(root)
    entries = _theatre_entries(root)
    selected_theatre = _resolve_unique_theatre_id(entries, terrain)
    if airplane_only and helicopter_only:
        raise ValueError("choose either --airplane-only or --helicopter-only")
    exact_airport = airport is not None or airdrome_id is not None
    if (
        (parking is not None or airplane_only or helicopter_only or limit is not None)
        and not exact_airport
    ):
        raise ValueError(
            "parking/capability/limit filters require --airport or "
            "--airdrome-id"
        )
    if (
        limit is not None
        and (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 100
        )
    ):
        raise ValueError("--limit must be an integer from 1 to 100")

    all_airbases, source = _load_airbases(root)
    terrain_airbases = [
        item for item in all_airbases if item.get("theatre") == selected_theatre
    ]
    selected = [
        item
        for item in terrain_airbases
        if (
            (
                airport is None
                or any(
                    isinstance(value, str)
                    and value.casefold() == airport.casefold()
                    for value in (
                        item.get("displayName"),
                        item.get("typeName"),
                        item.get("code"),
                    )
                )
            )
            and (airdrome_id is None or item.get("ID") == airdrome_id)
        )
    ]

    output_airbases: list[dict[str, Any]] = []
    matching_parking = 0
    returned_parking = 0
    unresolved_airbases = 0
    airbase_name_fallbacks = 0
    for item in selected:
        try:
            record = _airbase_record(item)
        except ValueError:
            unresolved_airbases += 1
            continue
        if record["name_source"] != "displayName":
            airbase_name_fallbacks += 1
        if exact_airport:
            spots = [
                spot
                for spot in record["parking"]
                if (
                    (
                        parking is None
                        or str(spot["crossroad_idx"]) == parking
                        or spot["slot_name"] == parking
                    )
                    and (not airplane_only or spot["airplanes"] is True)
                    and (not helicopter_only or spot["helicopters"] is True)
                )
            ]
            matching_parking += len(spots)
            if limit is not None:
                spots = spots[:limit]
            record["parking"] = spots
            returned_parking += len(spots)
        else:
            record.pop("parking")
        output_airbases.append(record)

    exact_airbase_usable = (
        not exact_airport
        or (
            len(selected) == 1
            and len(output_airbases) == 1
            and unresolved_airbases == 0
        )
    )
    exact_parking_usable = (
        parking is None
        or (exact_airbase_usable and matching_parking == 1)
    )
    return {
        "schema": "dcsmizzer.br-airbases/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_exported_airbase_database",
        ),
        "dcs_started": False,
        "source": source.relative_to(root).as_posix(),
        "source_sha256": _sha256(source),
        "upstream": upstream,
        "upstream_project_version": _project_version_evidence(root),
        "filters": {
            "terrain": selected_theatre,
            "airport": airport,
            "airdrome_id": airdrome_id,
            "parking": parking,
            "airplane_only": airplane_only,
            "helicopter_only": helicopter_only,
            "limit": limit,
        },
        "coverage": {
            "airbases_in_terrain": len(terrain_airbases),
            "matching_airbases": len(selected),
            "airbase_parse_failures": unresolved_airbases,
            "airbase_name_fallbacks": airbase_name_fallbacks,
            "matching_parking_slots": matching_parking,
            "returned_parking_slots": returned_parking,
            "parking_output_truncated": returned_parking < matching_parking,
            "exact_airbase_query_usable": exact_airbase_usable,
            "exact_parking_query_usable": exact_parking_usable,
        },
        "airbases": output_airbases,
        "limitations": [
            "The report parses an exported BriefingRoom database in the "
            "reported source snapshot; it is not a current installed DCS registry.",
            "Stand crossroad_index/name and x/y match the upstream generator's "
            "mission parking fields, but parking heading is not exported.",
            "Stand elevation is not exported. The airbase center elevation is "
            "reported separately and must not be presented as a measured "
            "per-stand elevation.",
            "Terminal fallback records retain Term_Index as the mission "
            "parking ID and exact exported elevation, but have no exported "
            "slot name, heading, or dimensions.",
            "Cross-check current installed or parsed real-MIZ evidence whenever "
            "the target terrain is locally available.",
            "No upstream code was executed and no DCS or Mission Editor "
            "process was started.",
        ],
    }


def br_spawnpoint_report(
    br_root: Path,
    terrain: str,
    *,
    spawn_type: str | None = None,
    near_x: float | None = None,
    near_y: float | None = None,
    radius_m: float | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Stream a bounded nearest-point query over generated/manual map points."""

    root = _validated_root(br_root)
    upstream = _git_state(root)
    entries = _theatre_entries(root)
    selected_theatre = _resolve_unique_theatre_id(entries, terrain)
    if (near_x is None) != (near_y is None):
        raise ValueError("--x and --y must be supplied together")
    if radius_m is not None and near_x is None:
        raise ValueError("--radius requires --x and --y")
    for name, value in (("x", near_x), ("y", near_y), ("radius", radius_m)):
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if radius_m is not None and radius_m <= 0:
        raise ValueError("--radius must be greater than zero")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("--limit must be an integer from 1 to 100")
    if spawn_type is not None and not spawn_type.strip():
        raise ValueError("--type must not be empty")

    source_root = root / "DatabaseJSON" / "TheaterSpawnPoints"
    sources = [
        _contained_source(
            root,
            source_root,
            f"{selected_theatre}.json.gz",
        ),
        _contained_source(
            root,
            source_root,
            f"{selected_theatre}_Manual.json.gz",
        ),
    ]
    missing = [path.name for path in sources if not path.is_file()]
    if missing:
        raise ValueError("BriefingRoom spawn-point source is incomplete")

    types: Counter[str] = Counter()
    parsed = 0
    malformed = 0
    matched = 0
    retained: list[tuple[float, int, dict[str, Any]]] = []
    serial = 0
    for source in sources:
        source_kind = (
            "manual" if source.stem.endswith("_Manual.json") else "generated"
        )
        for item in _iter_gzip_json_array(source):
            parsed += 1
            normalized = _spawnpoint(
                item,
                selected_theatre,
                source_kind=source_kind,
            )
            if normalized is None:
                malformed += 1
                continue
            types[normalized["type"]] += 1
            if spawn_type is not None and normalized["type"] != spawn_type:
                continue
            distance_m: float | None = None
            if near_x is not None and near_y is not None:
                distance_m = math.hypot(
                    normalized["x"] - near_x,
                    normalized["y"] - near_y,
                )
                if radius_m is not None and distance_m > radius_m:
                    continue
            matched += 1
            output = {
                **normalized,
                "distance_m": distance_m,
            }
            if near_x is None:
                if len(retained) < limit:
                    retained.append((float(serial), serial, output))
            else:
                score = distance_m if distance_m is not None else 0.0
                candidate = (-score, -serial, output)
                if len(retained) < limit:
                    heapq.heappush(retained, candidate)
                elif candidate > retained[0]:
                    heapq.heapreplace(retained, candidate)
            serial += 1

    if near_x is None:
        points = [item[2] for item in retained]
    else:
        points = sorted(
            (item[2] for item in retained),
            key=lambda item: (
                item["distance_m"],
                item["x"],
                item["y"],
                (
                    item["altitude_msl"] is None,
                    item["altitude_msl"]
                    if item["altitude_msl"] is not None
                    else 0.0,
                ),
            ),
        )
    return {
        "schema": "dcsmizzer.br-spawnpoints/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_exported_spawn_point_database",
        ),
        "dcs_started": False,
        "upstream": upstream,
        "upstream_project_version": _project_version_evidence(root),
        "sources": [
            {
                "source": source.relative_to(root).as_posix(),
                "source_sha256": _sha256(source),
            }
            for source in sources
        ],
        "filters": {
            "terrain": selected_theatre,
            "type": spawn_type,
            "x": near_x,
            "y": near_y,
            "radius_m": radius_m,
            "limit": limit,
        },
        "coverage": {
            "points_parsed": parsed,
            "points_malformed": malformed,
            "point_types": dict(sorted(types.items())),
            "matching_points": matched,
            "returned_points": len(points),
            "output_truncated": len(points) < matched,
        },
        "points": points,
        "limitations": [
            "BRtype is an upstream planning classification, not a current DCS "
            "terrain-surface or collision query.",
            "Altitude is exported point data but does not prove that a chosen "
            "unit, formation, or route is safe at the point.",
            "Manual points with only two coordinates have altitude_msl=null; "
            "no terrain elevation was inferred.",
            "Nearest-point selection is deterministic for the recorded source "
            "order and filters.",
            "Spawn-point and bounds files have mixed per-file provenance; the "
            "project-level targeted DCS version is not a per-file version "
            "guarantee.",
            "No upstream code was executed and no DCS or Mission Editor "
            "process was started.",
        ],
    }


def _theatre_entries(root: Path) -> list[dict[str, Any]]:
    directory = root / "Database" / "Theaters"
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.ini"), key=lambda item: item.name.casefold()):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read(path, encoding="utf-8-sig")
            dcs_id = parser["Theater"]["DCSID"].strip()
            display_name = parser["GUI"]["DisplayName"].strip()
        except (OSError, KeyError, configparser.Error) as error:
            raise ValueError("cannot parse BriefingRoom theatre declaration") from error
        if not _is_safe_component(dcs_id) or not display_name:
            raise ValueError("BriefingRoom theatre declaration is incomplete")
        records.append(
            {
                "declaration_id": path.stem,
                "dcs_id": dcs_id,
                "display_name": display_name,
                "default_map_center": parser["Theater"].get(
                    "DefaultMapCenter"
                ),
                "magnetic_declination": _optional_float(
                    parser["Theater"].get("MagneticDeclination")
                ),
                "source": path.relative_to(root).as_posix(),
                "source_sha256": _sha256(path),
            }
        )
    return records


def _resolve_unique_theatre_id(
    entries: list[dict[str, Any]],
    terrain: str,
) -> str:
    matches = [
        entry
        for entry in entries
        if any(
            value.casefold() == terrain.casefold()
            for value in (
                entry["dcs_id"],
                entry["declaration_id"],
                entry["display_name"],
            )
        )
    ]
    if not matches:
        raise ValueError("requested BriefingRoom DCS theatre does not exist")
    if len(matches) > 1:
        raise ValueError(
            "requested BriefingRoom DCS theatre identity is ambiguous"
        )
    selected = matches[0]["dcs_id"]
    if (
        sum(
            entry["dcs_id"].casefold() == selected.casefold()
            for entry in entries
        )
        != 1
    ):
        raise ValueError(
            "requested BriefingRoom DCS theatre identity is ambiguous"
        )
    return selected


def _bounds_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot parse BriefingRoom terrain bounds") from error
    if not isinstance(data, dict):
        raise ValueError("BriefingRoom terrain bounds root is not an object")
    all_points: list[tuple[float, float]] = []
    summaries: dict[str, Any] = {}
    for field in ("landMasses", "waters"):
        polygons = data.get(field)
        if not isinstance(polygons, list):
            raise ValueError("BriefingRoom terrain bounds polygon set is invalid")
        vertices = 0
        for polygon in polygons:
            if not isinstance(polygon, list):
                raise ValueError("BriefingRoom terrain polygon is invalid")
            for point in polygon:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or not all(_is_number(value) for value in point)
                ):
                    raise ValueError("BriefingRoom terrain vertex is invalid")
                x, y = float(point[0]), float(point[1])
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("BriefingRoom terrain vertex is non-finite")
                all_points.append((x, y))
                vertices += 1
        summaries[field] = {
            "polygons": len(polygons),
            "vertices": vertices,
        }
    envelope = (
        {
            "minimum_x": min(point[0] for point in all_points),
            "maximum_x": max(point[0] for point in all_points),
            "minimum_y": min(point[1] for point in all_points),
            "maximum_y": max(point[1] for point in all_points),
        }
        if all_points
        else None
    )
    return {
        "source_fields": summaries,
        "semantics": {
            "waters": "water inclusion polygons",
            "landMasses": "water exclusion polygons",
        },
        "vertex_envelope": envelope,
    }


def _load_airbases(root: Path) -> tuple[list[dict[str, Any]], Path]:
    source = root / "DatabaseJSON" / "TheatersAirbases.json"
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot parse BriefingRoom airbase export") from error
    if not isinstance(data, list):
        raise ValueError("BriefingRoom airbase export root is not an array")
    records = [item for item in data if isinstance(item, dict)]
    if len(records) != len(data):
        raise ValueError("BriefingRoom airbase export has non-object records")
    return records, source


def _airbase_record(item: dict[str, Any]) -> dict[str, Any]:
    identifier = item.get("ID")
    theatre = item.get("theatre")
    display_name = item.get("displayName")
    type_name = item.get("typeName")
    position = _dcs_world_position(item.get("pos"))
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or not isinstance(theatre, str)
        or not isinstance(display_name, str)
        or position is None
    ):
        raise ValueError("BriefingRoom airbase record is incomplete")
    if display_name.strip():
        name = display_name.strip()
        name_source = "displayName"
    elif isinstance(type_name, str) and type_name.strip():
        name = type_name.strip()
        name_source = "typeName_fallback_for_blank_displayName"
    else:
        raise ValueError("BriefingRoom airbase has no usable name")
    stands = item.get("stands")
    parking = item.get("parking")
    if isinstance(stands, list) and stands:
        spots = [_stand_record(stand, position["altitude_msl"]) for stand in stands]
        parking_source = "stands"
    elif isinstance(parking, list):
        spots = [_terminal_record(terminal) for terminal in parking]
        parking_source = "terminal_fallback"
    else:
        raise ValueError("BriefingRoom airbase has no parking array")
    raw_runways = item.get("runways", [])
    if not isinstance(raw_runways, list):
        raise ValueError("BriefingRoom airbase runways are not an array")
    runways = [_runway_record(runway) for runway in raw_runways]
    airdrome = item.get("airdromeData")
    return {
        "airdrome_id": identifier,
        "theatre": theatre,
        "name": name,
        "name_source": name_source,
        "display_name": display_name,
        "type_name": type_name,
        "icao": item.get("code"),
        "center": position,
        "runways": runways,
        "runway_designators": (
            airdrome.get("runways", [])
            if isinstance(airdrome, dict)
            and isinstance(airdrome.get("runways"), list)
            else []
        ),
        "radio": {
            field: airdrome.get(field, [])
            for field in ("ATC", "TACAN", "ILS")
        }
        if isinstance(airdrome, dict)
        else None,
        "radio_units": {
            "ATC": "Hz",
            "ILS": "Hz",
            "TACAN": "channel",
        },
        "parking_source": parking_source,
        "parking_slot_count": len(spots),
        "airplane_parking_slots": sum(
            spot["airplanes"] is True for spot in spots
        ),
        "helicopter_parking_slots": sum(
            spot["helicopters"] is True for spot in spots
        ),
        "parking": sorted(
            spots,
            key=lambda spot: (
                spot["crossroad_idx"],
                str(spot["slot_name"]),
            ),
        ),
    }


def _stand_record(item: Any, airbase_elevation: float) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("BriefingRoom stand is not an object")
    params = item.get("params")
    if not isinstance(params, dict):
        raise ValueError("BriefingRoom stand has no params")
    crossroad = item.get("crossroad_index")
    slot_name = item.get("name")
    x = item.get("x")
    y = item.get("y")
    if (
        not isinstance(crossroad, int)
        or isinstance(crossroad, bool)
        or not isinstance(slot_name, str)
        or not _is_number(x)
        or not _is_number(y)
    ):
        raise ValueError("BriefingRoom stand identifiers are invalid")
    return {
        "crossroad_idx": crossroad,
        "slot_name": slot_name,
        "position": {"x": x, "y": y},
        "elevation_msl": None,
        "airbase_reference_elevation_msl": airbase_elevation,
        "heading": None,
        "airplanes": params.get("FOR_AIRPLANES") == "1",
        "helicopters": params.get("FOR_HELICOPTERS") == "1",
        "shelter": params.get("SHELTER") == "1",
        "dimensions": {
            "length": _nullable_float(params.get("LENGTH")),
            "width": _nullable_float(params.get("WIDTH")),
            "height": _nullable_float(params.get("HEIGHT")),
        },
        "source_kind": "stand",
    }


def _terminal_record(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("BriefingRoom terminal is not an object")
    identifier = item.get("Term_Index")
    terminal_type = item.get("Term_Type_Name")
    position = _dcs_world_position(item.get("pos"))
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or not isinstance(terminal_type, str)
        or position is None
    ):
        raise ValueError("BriefingRoom terminal record is invalid")
    airplanes, helicopters = _TERMINAL_CAPABILITIES.get(
        terminal_type,
        (None, None),
    )
    return {
        "crossroad_idx": identifier,
        "slot_name": None,
        "position": {"x": position["x"], "y": position["y"]},
        "elevation_msl": position["altitude_msl"],
        "airbase_reference_elevation_msl": None,
        "heading": None,
        "airplanes": airplanes,
        "helicopters": helicopters,
        "shelter": terminal_type == "HardenedAirShelter",
        "dimensions": None,
        "terminal_type": terminal_type,
        "source_kind": "terminal_fallback",
    }


def _runway_record(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("BriefingRoom runway is not an object")
    identifier = item.get("id")
    designator = item.get("name", item.get("Name"))
    course = item.get("course")
    length = item.get("length")
    width = item.get("width")
    position = item.get("position")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or not (
            isinstance(designator, int | str)
            and not isinstance(designator, bool)
            and (not isinstance(designator, str) or designator.strip())
        )
        or not _is_finite_number(course)
        or not _is_finite_number(length)
        or length <= 0
        or not _is_finite_number(width)
        or width <= 0
        or not isinstance(position, dict)
        or not all(
            _is_finite_number(position.get(axis))
            for axis in ("x", "y", "z")
        )
    ):
        raise ValueError("BriefingRoom runway record is incomplete")
    result = {
        "id": identifier,
        "designator_index": designator,
        "course_raw_radians": course,
        "length": length,
        "width": width,
        "position": {
            name: position[name] for name in ("x", "y", "z")
        },
    }
    return result


def _dcs_world_position(item: Any) -> dict[str, float] | None:
    if not isinstance(item, dict):
        return None
    dcs = item.get("DCS")
    world = item.get("World")
    if not isinstance(dcs, dict) or not isinstance(world, dict):
        return None
    values = (
        dcs.get("x"),
        dcs.get("z"),
        world.get("alt"),
        world.get("lat"),
        world.get("lon"),
    )
    if not all(_is_number(value) and math.isfinite(float(value)) for value in values):
        return None
    return {
        "x": float(values[0]),
        "y": float(values[1]),
        "altitude_msl": float(values[2]),
        "latitude": float(values[3]),
        "longitude": float(values[4]),
    }


def _spawnpoint(
    item: Any,
    theatre: str,
    *,
    source_kind: str,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    declared_theatre = item.get("theatre")
    if declared_theatre not in {None, theatre}:
        return None
    if declared_theatre is None and source_kind != "manual":
        return None
    spawn_type = item.get("BRtype")
    coordinates = item.get("coords")
    if (
        not isinstance(spawn_type, str)
        or not spawn_type
        or not isinstance(coordinates, list)
        or len(coordinates) not in {2, 3}
        or not all(
            _is_number(value) and math.isfinite(float(value))
            for value in coordinates
        )
    ):
        return None
    return {
        "type": spawn_type,
        "x": float(coordinates[0]),
        "y": float(coordinates[1]),
        "altitude_msl": (
            float(coordinates[2]) if len(coordinates) == 3 else None
        ),
        "source_kind": source_kind,
    }


def _iter_gzip_json_array(path: Path) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    with gzip.open(path, mode="rt", encoding="utf-8-sig", newline="") as stream:
        buffer = ""
        position = 0
        started = False
        eof = False
        while True:
            if position > _SPAWN_CHUNK_CHARS:
                buffer = buffer[position:]
                position = 0
            while position >= len(buffer) and not eof:
                chunk = stream.read(_SPAWN_CHUNK_CHARS)
                if chunk:
                    buffer += chunk
                else:
                    eof = True
            while position < len(buffer) and (
                buffer[position].isspace() or buffer[position] == ","
            ):
                position += 1
            if not started:
                if position >= len(buffer) and not eof:
                    continue
                if position >= len(buffer) or buffer[position] != "[":
                    raise ValueError("spawn-point JSON root is not an array")
                started = True
                position += 1
                continue
            while position < len(buffer) and (
                buffer[position].isspace() or buffer[position] == ","
            ):
                position += 1
            if position < len(buffer) and buffer[position] == "]":
                return
            if position >= len(buffer):
                if eof:
                    raise ValueError("spawn-point JSON array is incomplete")
                continue
            try:
                item, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError as error:
                if eof:
                    raise ValueError("cannot parse spawn-point JSON") from error
                chunk = stream.read(_SPAWN_CHUNK_CHARS)
                if chunk:
                    buffer += chunk
                else:
                    eof = True
                continue
            position = end
            yield item


def _validated_root(path: Path) -> Path:
    # Collapse lexical "."/".." components without resolving symlinks.  The
    # latter must remain visible to the strict upstream provenance checks.
    root = Path(os.path.abspath(os.fspath(path)))
    if not (root / "Database" / "Theaters").is_dir():
        raise ValueError("BriefingRoom root has no Database/Theaters")
    if not (root / "DatabaseJSON" / "TheatersAirbases.json").is_file():
        raise ValueError("BriefingRoom root has no exported airbase database")
    return root


def _is_safe_component(value: str) -> bool:
    return bool(
        value
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)
    )


def _contained_source(root: Path, directory: Path, filename: str) -> Path:
    if not _is_safe_component(filename):
        raise ValueError("BriefingRoom source identity is not a safe component")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        resolved_directory.relative_to(resolved_root)
        candidate = directory / filename
        resolved_candidate = candidate.resolve(strict=False)
        resolved_candidate.relative_to(resolved_directory)
        resolved_candidate.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise ValueError(
            "BriefingRoom source path escapes its checkout database directory"
        ) from error
    return resolved_candidate


def _git_state(root: Path) -> dict[str, Any]:
    source_lock = upstream_source_lock_status(root, "BriefingRoom")
    actual = source_lock["actual"]
    exact_checkout_root = actual["exact_checkout_root"] is True
    if not exact_checkout_root:
        return {
            "remote": None,
            "remote_scope": "not_read_without_exact_checkout_root",
            "branch": None,
            "commit": None,
            "clean": None,
            "git_available": False,
            "exact_checkout_root": False,
            "provenance": "unversioned_snapshot",
            "source_lock": source_lock,
            "acknowledged": False,
        }
    commit = actual["head"]
    clean = actual["clean"]
    acknowledged = source_lock["acknowledged"] is True
    if acknowledged:
        provenance = "commit_bound"
    elif commit is not None and clean is True:
        provenance = "clean_unacknowledged_snapshot"
    else:
        provenance = "dirty_worktree_snapshot"
    branch = actual["branch"]
    if branch is None and actual["detached"] is True:
        branch = ""
    return {
        "remote": actual["remote"],
        "remote_scope": "sanitized_no_userinfo_query_or_fragment",
        "branch": branch,
        "commit": commit,
        "clean": clean,
        "git_available": commit is not None,
        "exact_checkout_root": True,
        "provenance": provenance,
        "source_lock": source_lock,
        "acknowledged": acknowledged,
    }


def _project_version_evidence(root: Path) -> dict[str, Any] | None:
    source = root / "src" / "BriefingRoom" / "BriefingRoom.cs"
    if not source.is_file():
        return None
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    match = re.search(
        r'\bTARGETED_DCS_WORLD_VERSION\s*=\s*"(?P<version>[^"]+)"',
        text,
    )
    return {
        "targeted_dcs_world_version": (
            match.group("version") if match is not None else None
        ),
        "scope": "project_level_not_per_export_file",
        "source": source.relative_to(root).as_posix(),
        "source_sha256": _sha256(source),
    }


def _git(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _sanitize_git_remote(remote: str | None) -> str | None:
    """Return traceable public remote syntax without credentials or local paths."""

    if remote is None:
        return None
    value = remote.strip()
    if not value:
        return None
    if _looks_like_local_path(value):
        return "<redacted-local-remote>"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-local-or-unrecognized-remote>"
    if parsed.scheme:
        if parsed.scheme.casefold() == "file":
            return "file://<redacted-local-remote>"
        try:
            hostname = parsed.hostname
        except ValueError:
            return "<redacted-local-or-unrecognized-remote>"
        if _is_local_host(hostname) or _contains_windows_or_unc_path(
            parsed.path
        ):
            return "<redacted-local-remote>"
        public_netloc = parsed.netloc.rsplit("@", 1)[-1]
        if not public_netloc:
            return f"{parsed.scheme}://<redacted-invalid-remote>"
        return urlunsplit(
            (
                parsed.scheme,
                public_netloc,
                parsed.path,
                "",
                "",
            )
        )
    scp_match = re.fullmatch(
        r"(?:[^@\s/:]+@)?(?P<host>[^@\s/:]+):"
        r"(?P<path>[^?#\s]+)(?:[?#].*)?",
        value,
    )
    if scp_match is not None:
        host = scp_match.group("host")
        path = scp_match.group("path")
        if _is_local_host(host) or _contains_windows_or_unc_path(path):
            return "<redacted-local-remote>"
        return f"{host}:{path}"
    public_path = re.fullmatch(
        r"(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})/"
        r"(?P<path>[^?#\s]+)(?:[?#].*)?",
        value,
    )
    if public_path is not None:
        host = public_path.group("host")
        path = public_path.group("path")
        if _is_local_host(host) or _contains_windows_or_unc_path(path):
            return "<redacted-local-remote>"
        return f"{host}/{path}"
    return "<redacted-local-or-unrecognized-remote>"


def _snapshot_authority(
    upstream: dict[str, Any],
    subject: str,
) -> str:
    provenance = upstream.get("provenance")
    if provenance == "commit_bound":
        return f"commit_bound_{subject}"
    if provenance == "dirty_worktree_snapshot":
        return f"dirty_worktree_snapshot_{subject}"
    if provenance == "clean_unacknowledged_snapshot":
        return f"clean_unacknowledged_snapshot_{subject}"
    return f"unversioned_snapshot_{subject}"


def _looks_like_local_path(value: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
        or value.startswith(("/", "\\", ".", "~"))
    )


def _is_local_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.rstrip(".").casefold()
    if (
        normalized == "localhost"
        or normalized == "localhost.localdomain"
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
        or "." not in normalized
    ):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
    )


def _contains_windows_or_unc_path(value: str) -> bool:
    normalized = value.replace("%5c", "\\").replace("%5C", "\\")
    normalized = normalized.replace("%2f", "/").replace("%2F", "/")
    normalized = normalized.replace("%3a", ":").replace("%3A", ":")
    return bool(
        normalized.startswith(("\\\\", "//"))
        or re.search(r"(?:^|[\\/])[A-Za-z]:[\\/]", normalized)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value.strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _nullable_float(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("BriefingRoom numeric field is invalid") from error
    if not math.isfinite(number):
        raise ValueError("BriefingRoom numeric field is non-finite")
    return number


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))
