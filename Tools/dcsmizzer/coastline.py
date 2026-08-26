"""Commit-qualified planning offsets from BriefingRoom sea-mask geometry."""

from __future__ import annotations

import configparser
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from .br_static import (
    _contained_source,
    _git_state,
    _resolve_unique_theatre_id,
    _theatre_entries,
    _validated_root,
)
from .terrain_probe import _read_regular_file


SCHEMA = "dcsmizzer.br-coastline/v1"
MAX_BOUNDS_BYTES = 16 * 1024 * 1024
MAX_THEATRE_DECLARATION_BYTES = 1024 * 1024
MAX_POLYGONS = 4096
MAX_VERTICES = 500_000
MAX_ABSOLUTE_COORDINATE = 100_000_000.0
MAX_OFFSET_DISTANCE_M = 2_000_000.0
_REGULAR_GIT_BLOB_MODES = frozenset({"100644", "100755"})
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40,64}\Z")


def br_coastline_report(
    br_root: Path,
    terrain: str,
    *,
    map_x: float,
    map_y: float,
    offset_distance_m: float | None = None,
    target_side: str = "water",
) -> dict[str, Any]:
    """Measure or construct an offset from a planning land-mass boundary."""

    x = _bounded_number(
        map_x,
        "x",
        -MAX_ABSOLUTE_COORDINATE,
        MAX_ABSOLUTE_COORDINATE,
    )
    y = _bounded_number(
        map_y,
        "y",
        -MAX_ABSOLUTE_COORDINATE,
        MAX_ABSOLUTE_COORDINATE,
    )
    if target_side not in {"water", "land"}:
        raise ValueError("target side must be water or land")
    distance = None
    if offset_distance_m is not None:
        distance = _bounded_number(
            offset_distance_m,
            "offset distance",
            0.001,
            MAX_OFFSET_DISTANCE_M,
        )

    root = _validated_root(Path(br_root))
    upstream = _git_state(root)
    entries = _theatre_entries(root)
    selected_terrain = _resolve_unique_theatre_id(entries, terrain)
    selected_entries = [
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
    if len(selected_entries) != 1:
        raise ValueError("requested BriefingRoom theatre identity is ambiguous")
    selected_entry = selected_entries[0]
    theatre_source = _contained_source(
        root,
        root / "Database" / "Theaters",
        f"{selected_entry['declaration_id']}.ini",
    )
    theatre_worktree_payload = _read_regular_file(
        theatre_source,
        MAX_THEATRE_DECLARATION_BYTES,
    )
    theatre_payload, theatre_binding = _git_source_payload(
        root,
        theatre_source,
        theatre_worktree_payload,
        upstream,
        maximum_bytes=MAX_THEATRE_DECLARATION_BYTES,
    )
    _validate_theatre_declaration(theatre_payload, selected_entry)
    source = _contained_source(
        root,
        root / "DatabaseJSON" / "TheaterTerrainBounds",
        f"{selected_terrain}.json",
    )
    worktree_payload = _read_regular_file(source, MAX_BOUNDS_BYTES)
    payload, geometry_binding = _git_source_payload(
        root,
        source,
        worktree_payload,
        upstream,
        maximum_bytes=MAX_BOUNDS_BYTES,
    )
    geometry = _load_geometry(payload)
    point = (x, y)
    nearest = _nearest_boundary(point, geometry["landMasses"])
    anchor_mask = _mask_classification(point, geometry)
    offset = (
        _offset_from_boundary(
            nearest,
            geometry,
            distance,
            target_side,
        )
        if distance is not None
        else None
    )
    all_sources_bound = bool(
        theatre_binding["bound_to_head"] is True
        and geometry_binding["bound_to_head"] is True
    )
    commit_bound = bool(
        upstream.get("acknowledged") is True
        and all_sources_bound
    )
    source_manifest = hashlib.sha256()
    for relative, source_payload in sorted(
        (
            (theatre_binding["relative_path"], theatre_payload),
            (geometry_binding["relative_path"], payload),
        )
    ):
        source_manifest.update(relative.encode("utf-8"))
        source_manifest.update(b"\0")
        source_manifest.update(hashlib.sha256(source_payload).hexdigest().encode("ascii"))
        source_manifest.update(b"\0")
    decision_source_binding = {
        "basis": (
            "the exact Git commit blob bytes for the selected theatre "
            "declaration and terrain bounds are parsed and hashed; each "
            "worktree path must separately be a safe regular file"
        ),
        "head_commit": upstream.get("commit"),
        "required_sources": 2,
        "parsed_from_head_blobs": sum(
            binding["parsed_from"] == "git_HEAD_blob"
            for binding in (theatre_binding, geometry_binding)
        ),
        "all_required_sources_bound_to_head": all_sources_bound,
        "bound_to_head": all_sources_bound,
        "parsed_source_manifest_sha256": source_manifest.hexdigest(),
        "sources": {
            "theatre_declaration": theatre_binding,
            "terrain_bounds": geometry_binding,
        },
    }
    return {
        "schema": SCHEMA,
        "authority": (
            "derived_commit_bound_br_sea_mask_planning_geometry"
            if commit_bound
            else "derived_unacknowledged_br_sea_mask_planning_geometry"
        ),
        "dcs_started": False,
        "terrain": selected_terrain,
        "upstream": upstream,
        "source": {
            "relative_path": source.relative_to(root).as_posix(),
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "sha256_scope": f"{geometry_binding['parsed_from']}_bytes",
            "worktree_sha256": hashlib.sha256(worktree_payload).hexdigest(),
            "worktree_matches_parsed_source": payload == worktree_payload,
        },
        "theatre_declaration_source": {
            "relative_path": theatre_source.relative_to(root).as_posix(),
            "size_bytes": len(theatre_payload),
            "sha256": hashlib.sha256(theatre_payload).hexdigest(),
            "sha256_scope": f"{theatre_binding['parsed_from']}_bytes",
            "worktree_sha256": hashlib.sha256(
                theatre_worktree_payload
            ).hexdigest(),
            "worktree_matches_parsed_source": (
                theatre_payload == theatre_worktree_payload
            ),
        },
        "decision_source_binding": decision_source_binding,
        "geometry": {
            "semantics": {
                "waters": "water inclusion polygons",
                "landMasses": "water exclusion polygons and selected planning boundary",
            },
            "water_polygons": len(geometry["waters"]),
            "land_mass_polygons": len(geometry["landMasses"]),
            "vertices": sum(
                len(polygon)
                for name in ("waters", "landMasses")
                for polygon in geometry[name]
            ),
        },
        "input": {
            "x": x,
            "y": y,
            "mask_classification": anchor_mask,
        },
        "nearest_planning_land_mass_boundary": _boundary_record(nearest),
        "offset": offset,
        "validation": {
            "source_commit_bound": commit_bound,
            "geometry_parsed": True,
            "minimum_distance_computed": True,
            "offset_requested": distance is not None,
            "offset_satisfied": (
                offset["satisfied"] if offset is not None else None
            ),
            "usable_for_generation": (
                commit_bound
                and (offset is None or offset["satisfied"] is True)
            ),
        },
        "limitations": [
            "This is commit-bound BriefingRoom sea-mask planning geometry, not "
            "an initialized current-DCS coastline, surface, or collision query.",
            "The selected boundary is the nearest water-exclusion landMasses "
            "segment; source polygons can be simplified or contain planning edges.",
            "A requested offset passes only when one perpendicular candidate is "
            "on the requested mask side and its global minimum land-boundary "
            "distance matches the request.",
            "Use a version-matched DCS physical surface query at the destination "
            "before treating it as playable water or land.",
            "No upstream code was executed and no DCS or Mission Editor process "
            "was started.",
        ],
    }


def _git_source_payload(
    root: Path,
    source: Path,
    worktree_payload: bytes,
    upstream: dict[str, Any],
    *,
    maximum_bytes: int,
) -> tuple[bytes, dict[str, Any]]:
    relative = source.relative_to(root).as_posix()
    commit = upstream.get("commit")
    binding: dict[str, Any] = {
        "basis": (
            "source is parsed from the exact Git commit blob; the worktree path "
            "must separately materialize as a safe regular file"
        ),
        "head_commit": commit if isinstance(commit, str) else None,
        "relative_path": relative,
        "git_tree_read": False,
        "git_mode": None,
        "git_blob_oid": None,
        "worktree_regular_file": True,
        "parsed_from": "unbound_worktree_file",
        "bound_to_head": False,
    }
    if upstream.get("acknowledged") is not True or not isinstance(commit, str):
        return worktree_payload, binding

    try:
        tree = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-z", commit, "--", relative],
            check=False,
            capture_output=True,
            timeout=15,
        )
        if tree.returncode != 0:
            return worktree_payload, binding
        records = [item for item in tree.stdout.split(b"\0") if item]
        if len(records) != 1:
            return worktree_payload, binding
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
        tree_relative = raw_path.decode("utf-8", errors="strict")
        binding.update(
            {
                "git_tree_read": True,
                "git_mode": mode,
                "git_blob_oid": object_id,
            }
        )
        if (
            tree_relative != relative
            or mode not in _REGULAR_GIT_BLOB_MODES
            or object_type != "blob"
            or _GIT_OBJECT_ID.fullmatch(object_id) is None
        ):
            return worktree_payload, binding
        size_result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-s", object_id],
            check=False,
            capture_output=True,
            timeout=15,
        )
        if size_result.returncode != 0:
            return worktree_payload, binding
        size = int(size_result.stdout.strip())
        if not 0 <= size <= maximum_bytes:
            return worktree_payload, binding
        blob = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", object_id],
            check=False,
            capture_output=True,
            timeout=30,
        )
        if blob.returncode != 0 or len(blob.stdout) != size:
            return worktree_payload, binding
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.TimeoutExpired,
    ):
        return worktree_payload, binding

    binding.update(
        {
            "parsed_from": "git_HEAD_blob",
            "bound_to_head": True,
        }
    )
    return blob.stdout, binding


def _validate_theatre_declaration(
    payload: bytes,
    selected_entry: dict[str, Any],
) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(payload.decode("utf-8-sig"))
        dcs_id = parser["Theater"]["DCSID"].strip()
        display_name = parser["GUI"]["DisplayName"].strip()
    except (
        UnicodeDecodeError,
        KeyError,
        configparser.Error,
    ) as error:
        raise ValueError(
            "cannot parse bound BriefingRoom theatre declaration"
        ) from error
    if (
        dcs_id != selected_entry["dcs_id"]
        or display_name != selected_entry["display_name"]
    ):
        raise ValueError(
            "worktree theatre identity differs from its bound Git declaration"
        )


def _load_geometry(payload: bytes) -> dict[str, list[list[tuple[float, float]]]]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("terrain bounds contain a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("terrain bounds contain a non-finite number")

    try:
        value = json.loads(
            payload.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError("terrain bounds are not valid UTF-8") from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("terrain bounds are not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("terrain bounds root must be an object")

    parsed: dict[str, list[list[tuple[float, float]]]] = {}
    total_polygons = 0
    total_vertices = 0
    for name in ("waters", "landMasses"):
        raw_polygons = value.get(name)
        if not isinstance(raw_polygons, list):
            raise ValueError(f"terrain bounds {name} must be an array")
        total_polygons += len(raw_polygons)
        if total_polygons > MAX_POLYGONS:
            raise ValueError("terrain bounds exceed the polygon limit")
        polygons: list[list[tuple[float, float]]] = []
        for polygon_index, raw_polygon in enumerate(raw_polygons):
            if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
                raise ValueError(
                    f"terrain bounds {name}[{polygon_index}] is not a polygon"
                )
            polygon: list[tuple[float, float]] = []
            for vertex_index, raw_point in enumerate(raw_polygon):
                if not isinstance(raw_point, list) or len(raw_point) != 2:
                    raise ValueError(
                        f"terrain bounds {name}[{polygon_index}]"
                        f"[{vertex_index}] is not an x/y pair"
                    )
                point_x = _bounded_number(
                    raw_point[0],
                    "terrain bounds x",
                    -MAX_ABSOLUTE_COORDINATE,
                    MAX_ABSOLUTE_COORDINATE,
                )
                point_y = _bounded_number(
                    raw_point[1],
                    "terrain bounds y",
                    -MAX_ABSOLUTE_COORDINATE,
                    MAX_ABSOLUTE_COORDINATE,
                )
                polygon.append((point_x, point_y))
                total_vertices += 1
                if total_vertices > MAX_VERTICES:
                    raise ValueError("terrain bounds exceed the vertex limit")
            if len(set(polygon)) < 3:
                raise ValueError(
                    f"terrain bounds {name}[{polygon_index}] is degenerate"
                )
            polygons.append(polygon)
        parsed[name] = polygons
    if not parsed["landMasses"]:
        raise ValueError("terrain bounds contain no land-mass planning boundary")
    return parsed


def _offset_from_boundary(
    origin: dict[str, Any],
    geometry: dict[str, list[list[tuple[float, float]]]],
    distance_m: float,
    target_side: str,
) -> dict[str, Any]:
    first = origin["segment_start"]
    second = origin["segment_end"]
    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]
    length = math.hypot(delta_x, delta_y)
    if length == 0.0:
        raise ValueError("nearest planning boundary segment is degenerate")
    normal = (-delta_y / length, delta_x / length)
    tolerance = max(1e-6, distance_m * 1e-9)
    candidates: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for direction in (1.0, -1.0):
        destination = (
            origin["nearest_point"][0] + direction * normal[0] * distance_m,
            origin["nearest_point"][1] + direction * normal[1] * distance_m,
        )
        mask = _mask_classification(destination, geometry)
        minimum = _nearest_boundary(destination, geometry["landMasses"])
        residual = abs(minimum["distance_m"] - distance_m)
        record = {
            "normal_direction": int(direction),
            "destination": {"x": destination[0], "y": destination[1]},
            "mask_classification": mask,
            "minimum_distance_m": minimum["distance_m"],
            "distance_residual_m": residual,
        }
        evaluated.append(record)
        if mask == target_side and residual <= tolerance:
            candidates.append(record)
    if len(candidates) != 1:
        raise ValueError(
            "requested planning coastline offset has no unique exact candidate; "
            "choose a less ambiguous anchor or distance"
        )
    selected = candidates[0]
    return {
        "requested_distance_m": distance_m,
        "target_side": target_side,
        "origin": {
            "x": origin["nearest_point"][0],
            "y": origin["nearest_point"][1],
        },
        **selected,
        "distance_tolerance_m": tolerance,
        "candidates_evaluated": evaluated,
        "satisfied": True,
    }


def _nearest_boundary(
    point: tuple[float, float],
    polygons: list[list[tuple[float, float]]],
) -> dict[str, Any]:
    best: (
        tuple[
            float,
            int,
            int,
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
        ]
        | None
    ) = None
    for polygon_index, polygon in enumerate(polygons):
        for segment_index, first in enumerate(polygon):
            second = polygon[(segment_index + 1) % len(polygon)]
            # Exported planning polygons can repeat a vertex.  A zero-length
            # edge carries no normal and must not win a distance tie over an
            # adjacent usable segment.
            if first == second:
                continue
            nearest, distance = _nearest_point_on_segment(point, first, second)
            candidate = (
                distance,
                polygon_index,
                segment_index,
                nearest,
                first,
                second,
            )
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        raise ValueError("terrain bounds contain no usable boundary segment")
    return {
        "distance_m": best[0],
        "polygon_index": best[1],
        "segment_index": best[2],
        "nearest_point": best[3],
        "segment_start": best[4],
        "segment_end": best[5],
    }


def _nearest_point_on_segment(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> tuple[tuple[float, float], float]:
    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]
    denominator = delta_x**2 + delta_y**2
    if denominator == 0.0:
        nearest = first
    else:
        fraction = (
            (point[0] - first[0]) * delta_x
            + (point[1] - first[1]) * delta_y
        ) / denominator
        fraction = min(1.0, max(0.0, fraction))
        nearest = (
            first[0] + fraction * delta_x,
            first[1] + fraction * delta_y,
        )
    return nearest, math.hypot(point[0] - nearest[0], point[1] - nearest[1])


def _mask_classification(
    point: tuple[float, float],
    geometry: dict[str, list[list[tuple[float, float]]]],
) -> str:
    water_states = [_point_in_polygon(point, polygon) for polygon in geometry["waters"]]
    land_states = [
        _point_in_polygon(point, polygon) for polygon in geometry["landMasses"]
    ]
    if "boundary" in water_states or "boundary" in land_states:
        return "boundary"
    if "inside" in land_states:
        return "land"
    if "inside" in water_states:
        return "water"
    return "outside_planning_mask"


def _point_in_polygon(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> str:
    inside = False
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        nearest, distance = _nearest_point_on_segment(point, first, second)
        segment_scale = max(
            1.0,
            abs(first[0]),
            abs(first[1]),
            abs(second[0]),
            abs(second[1]),
            abs(nearest[0]),
            abs(nearest[1]),
        )
        if distance <= segment_scale * 1e-12:
            return "boundary"
        if (first[1] > point[1]) != (second[1] > point[1]):
            crossing_x = first[0] + (
                (point[1] - first[1])
                * (second[0] - first[0])
                / (second[1] - first[1])
            )
            if point[0] < crossing_x:
                inside = not inside
    return "inside" if inside else "outside"


def _boundary_record(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "minimum_distance_m": value["distance_m"],
        "polygon_index": value["polygon_index"],
        "segment_index": value["segment_index"],
        "nearest_point": {
            "x": value["nearest_point"][0],
            "y": value["nearest_point"][1],
        },
        "segment_start": {
            "x": value["segment_start"][0],
            "y": value["segment_start"][1],
        },
        "segment_end": {
            "x": value["segment_end"][0],
            "y": value["segment_end"][1],
        },
    }


def _bounded_number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            f"{label} must be between {minimum} and {maximum}"
        ) from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result
