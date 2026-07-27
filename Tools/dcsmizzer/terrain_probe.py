"""Generate and extract bounded DCS mission-scripting terrain probes.

The Python side never starts DCS.  The generated Lua is intended to be run
manually as a mission trigger on the requested theatre.  It uses only the
mission-scripting APIs and emits hex-framed JSON through ``env.info`` so the
default MissionScripting sandbox does not need to be weakened.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from .dcs_static import _windows_product_version
from .terrain_physical import (
    corridor_sample_points,
    placement_sample_points,
    validate_terrain_evidence,
)


REQUEST_SCHEMA = "dcsmizzer.terrain-probe-request/v1"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_LOG_BYTES = 128 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_SCRIPT_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_SAMPLE_POINTS = 50_000
MAX_PLACEMENT_QUERIES = 1_000
MAX_CORRIDOR_QUERIES = 100
MAX_OBJECT_SEARCHES = 100
MAX_OBJECTS = 10_000
MAX_SEARCH_RADIUS_M = 100_000.0
MAX_ABS_COORDINATE = 100_000_000.0
MIN_TOLERANCE_M = 0.001
MAX_TOLERANCE_M = 1.0
MAX_MARKER_CHUNKS = 100_000
OBJECT_SEARCH_MINIMUM_ALTITUDE_MSL = -100_000.0
OBJECT_SEARCH_MAXIMUM_ALTITUDE_MSL = 100_000.0

_HASH = rb"[0-9a-f]{64}"
_BEGIN = re.compile(
    rb"DCSMIZZER_TERRAIN_PROBE_BEGIN "
    rb"(?P<hash>" + _HASH + rb") (?P<total>[1-9][0-9]{0,5})"
)
_CHUNK = re.compile(
    rb"DCSMIZZER_TERRAIN_PROBE_CHUNK "
    rb"(?P<hash>" + _HASH + rb") "
    rb"(?P<index>[1-9][0-9]{0,5})/(?P<total>[1-9][0-9]{0,5}) "
    rb"(?P<data>[0-9a-f]+)"
)
_END = re.compile(
    rb"DCSMIZZER_TERRAIN_PROBE_END "
    rb"(?P<hash>" + _HASH + rb") (?P<total>[1-9][0-9]{0,5})"
)


def generate_terrain_probe_script(
    request_path: Path,
    dcs_root: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Generate a mission-scripting probe without launching DCS."""

    request, request_payload = _load_request(request_path)
    identity = _installed_dcs_identity(Path(dcs_root))
    script = _render_probe_script(
        request,
        request_sha256=hashlib.sha256(request_payload).hexdigest(),
        dcs_identity=identity,
    ).encode("utf-8")
    if len(script) > MAX_SCRIPT_BYTES:
        raise ValueError("generated terrain probe exceeds the script size limit")
    _write_output(Path(output_path), script, force=force)
    return {
        "schema": "dcsmizzer.terrain-probe-script/v1",
        "authority": "generated_from_bounded_request_and_current_install_identity",
        "dcs_started": False,
        "request": {
            "schema": request["schema"],
            "terrain": request["terrain"],
            "sha256": hashlib.sha256(request_payload).hexdigest(),
            "sample_points": len(request["samples"]),
            "placement_queries": request["placement_queries"],
            "corridor_queries": request["corridor_queries"],
            "object_searches": len(request["object_searches"]),
            "max_objects": request["max_objects"],
        },
        "dcs": {
            **identity,
            "identity_source": "probe_generation_install",
            "product_version_source": "probe_generation_install",
            "runtime_identity_attested": False,
        },
        "output": {
            "name": Path(output_path).name,
            "bytes": len(script),
            "sha256": hashlib.sha256(script).hexdigest(),
        },
        "validation": {
            "request_valid": True,
            "script_generated": True,
            "runtime_test_performed": False,
            "runtime_dcs_identity_attested": False,
        },
        "execution_contract": {
            "environment": "DCS mission scripting",
            "loaded_theatre_must_equal": request["terrain"],
            "output_channel": "env.info markers in dcs.log",
            "mission_scripting_desanitization_required": False,
            "automatic_dcs_start": False,
            "runtime_dcs_identity_attestation": "unavailable",
        },
        "limitations": [
            "The script was generated but not run; terrain and scenery results "
            "do not exist until a user explicitly executes it in the matching "
            "DCS mission.",
            "The product version and Steam build identify the DCS installation "
            "used to generate the script, not an identity independently "
            "attested by the mission-scripting runtime; the runtime script "
            "independently rejects only a mismatched mission theatre.",
            "Mission-scripting surface types distinguish WATER and "
            "SHALLOW_WATER, not sea, lake, and river.",
            "The mission-scripting API does not expose Mission Editor runway, "
            "parking, or taxi-roadnet geometry; this probe emits no airfields.",
            "BOX searches discover scenery records, but undocumented "
            "searchObjects selection semantics mean their negative results "
            "cannot prove ground-placement collision clearance.",
        ],
    }


def extract_terrain_probe(
    log_path: Path,
    request_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Extract the latest complete matching marker run from a DCS log."""

    request, request_payload = _load_request(request_path)
    request_hash = hashlib.sha256(request_payload).hexdigest()
    log_payload = _read_regular_file(Path(log_path), MAX_LOG_BYTES)
    evidence_payload, marker = _latest_complete_run(
        log_payload,
        request_hash,
    )
    evidence = _load_json_object(
        evidence_payload,
        source_name="terrain probe evidence",
    )
    validate_terrain_evidence(evidence)
    _validate_extracted_evidence(evidence, request, request_hash)
    rendered = (
        json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(rendered) > MAX_EVIDENCE_BYTES:
        raise ValueError("terrain probe evidence exceeds the output size limit")
    _write_output(Path(output_path), rendered, force=force)
    return {
        "schema": "dcsmizzer.terrain-probe-extraction/v1",
        "authority": "complete_hash_bound_dcs_log_marker_run",
        "dcs_started": False,
        "input": {
            "log_name": Path(log_path).name,
            "log_bytes": len(log_payload),
            "log_sha256": hashlib.sha256(log_payload).hexdigest(),
            "request_name": Path(request_path).name,
            "request_sha256": request_hash,
        },
        "marker_run": marker,
        "evidence": {
            "terrain": evidence["terrain"],
            "dcs": evidence["dcs"],
            "samples": len(evidence["samples"]),
            "objects": len(evidence["objects"]),
            "airfields": len(evidence["airfields"]),
            "object_search_complete": evidence["coverage"][
                "object_search_complete"
            ],
            "object_search_complete_for_ground_placement": evidence[
                "coverage"
            ]["object_search_complete_for_ground_placement"],
            "airfield_inventory_complete": evidence["coverage"][
                "airfield_inventory_complete"
            ],
            "sha256": hashlib.sha256(rendered).hexdigest(),
        },
        "output": {
            "name": Path(output_path).name,
            "bytes": len(rendered),
            "sha256": hashlib.sha256(rendered).hexdigest(),
        },
        "validation": {
            "complete_marker_run": True,
            "request_hash_matched": True,
            "terrain_matched": True,
            "requested_samples_complete": True,
            "object_search_coverage_matched": True,
            "object_search_complete": evidence["coverage"][
                "object_search_complete"
            ],
            "object_search_complete_for_ground_placement": evidence[
                "coverage"
            ]["object_search_complete_for_ground_placement"],
            "airfield_inventory_complete": False,
            "runtime_dcs_identity_attested": False,
            "evidence_valid": True,
        },
        "limitations": [
            "The extractor validates framing, request binding, schema, and "
            "requested sample completeness; log producer identity is not "
            "cryptographically attested.",
            "The evidence product version and Steam build come from the "
            "installation used to generate the probe; mission scripting does "
            "not independently attest the runtime DCS executable identity.",
            "Scenery-object completeness applies only to the declared search "
            "volumes and is false when the object limit was reached or any "
            "returned object lacked usable geometry.",
            "Mission scripting documents BOX min/max parameters but does not "
            "state whether searchObjects selects scenery by pivot or collision "
            "box intersection; mission-probe negative results therefore never "
            "prove ground-placement collision clearance.",
            "The mission-scripting probe does not export an airfield inventory; "
            "an empty airfields array does not prove airfield clearance.",
            "A complete log export proves only the queried points and returned "
            "scenery objects, not unsampled terrain or runtime mission validity.",
            "The extractor itself did not start DCS or Mission Editor.",
        ],
    }


def _load_request(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular_file(Path(path), MAX_REQUEST_BYTES)
    request = _load_json_object(payload, source_name="terrain probe request")
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("terrain probe request schema is not supported")
    terrain = _bounded_text(request.get("terrain"), "terrain", maximum=128)
    tolerance = _bounded_number(
        request.get("sample_match_tolerance_m"),
        "sample_match_tolerance_m",
        MIN_TOLERANCE_M,
        MAX_TOLERANCE_M,
    )
    sample_values = request.get("samples", [])
    if not isinstance(sample_values, list):
        raise ValueError("samples must be an array")
    if len(sample_values) > MAX_SAMPLE_POINTS:
        raise ValueError("samples exceeds the record limit")
    samples: list[dict[str, float]] = []
    sample_keys: set[tuple[float, float]] = set()
    for index, value in enumerate(sample_values):
        if not isinstance(value, dict):
            raise ValueError(f"samples[{index}] must be an object")
        point = {
            "x": _coordinate(value.get("x"), f"samples[{index}].x"),
            "y": _coordinate(value.get("y"), f"samples[{index}].y"),
        }
        key = (point["x"], point["y"])
        if key in sample_keys:
            raise ValueError("samples contains a duplicate coordinate")
        sample_keys.add(key)
        samples.append(point)

    placement_values = request.get("placements", [])
    if not isinstance(placement_values, list):
        raise ValueError("placements must be an array")
    if len(placement_values) > MAX_PLACEMENT_QUERIES:
        raise ValueError("placements exceeds the record limit")
    for index, value in enumerate(placement_values):
        if not isinstance(value, dict):
            raise ValueError(f"placements[{index}] must be an object")
        points = placement_sample_points(
            x=value.get("x"),
            y=value.get("y"),
            heading_deg=value.get("heading_deg"),
            length_m=value.get("length_m"),
            width_m=value.get("width_m"),
        )
        _extend_unique_samples(samples, sample_keys, points)

    corridor_values = request.get("corridors", [])
    if not isinstance(corridor_values, list):
        raise ValueError("corridors must be an array")
    if len(corridor_values) > MAX_CORRIDOR_QUERIES:
        raise ValueError("corridors exceeds the record limit")
    for index, value in enumerate(corridor_values):
        if not isinstance(value, dict):
            raise ValueError(f"corridors[{index}] must be an object")
        points = corridor_sample_points(
            route=value.get("route"),
            half_width_m=value.get("half_width_m"),
            step_m=value.get("step_m"),
        )
        _extend_unique_samples(samples, sample_keys, points)

    search_values = request.get("object_searches", [])
    if not isinstance(search_values, list):
        raise ValueError("object_searches must be an array")
    if len(search_values) > MAX_OBJECT_SEARCHES:
        raise ValueError("object_searches exceeds the record limit")
    searches: list[dict[str, float]] = []
    for index, value in enumerate(search_values):
        if not isinstance(value, dict):
            raise ValueError(f"object_searches[{index}] must be an object")
        searches.append(
            {
                "x": _coordinate(
                    value.get("x"),
                    f"object_searches[{index}].x",
                ),
                "y": _coordinate(
                    value.get("y"),
                    f"object_searches[{index}].y",
                ),
                "radius_m": _bounded_number(
                    value.get("radius_m"),
                    f"object_searches[{index}].radius_m",
                    0.1,
                    MAX_SEARCH_RADIUS_M,
                ),
                "volume_kind": "box_3d",
                "minimum_altitude_msl": (
                    OBJECT_SEARCH_MINIMUM_ALTITUDE_MSL
                ),
                "maximum_altitude_msl": (
                    OBJECT_SEARCH_MAXIMUM_ALTITUDE_MSL
                ),
                "complete_for_ground_placement": False,
            }
        )
    max_objects = request.get("max_objects", 1_000)
    if (
        isinstance(max_objects, bool)
        or not isinstance(max_objects, int)
        or not 1 <= max_objects <= MAX_OBJECTS
    ):
        raise ValueError(
            f"max_objects must be an integer from 1 to {MAX_OBJECTS}"
        )
    if not samples and not searches:
        raise ValueError("terrain probe request contains no queries")
    return (
        {
            "schema": REQUEST_SCHEMA,
            "terrain": terrain,
            "sample_match_tolerance_m": tolerance,
            "samples": samples,
            "placement_queries": len(placement_values),
            "corridor_queries": len(corridor_values),
            "object_searches": searches,
            "max_objects": max_objects,
        },
        payload,
    )


def _installed_dcs_identity(dcs_root: Path) -> dict[str, str | None]:
    executable = dcs_root / "bin" / "DCS.exe"
    try:
        status_result = executable.lstat()
    except OSError as error:
        raise ValueError("DCS executable is missing") from error
    if not stat.S_ISREG(status_result.st_mode) or _is_reparse(status_result):
        raise ValueError("DCS executable is not a safe regular file")
    try:
        product_version = _windows_product_version(executable)
    except OSError as error:
        raise ValueError("DCS product version could not be read") from error
    if not product_version:
        raise ValueError("DCS product version is unavailable")

    steam_build_id: str | None = None
    manifest = dcs_root.parent.parent / "appmanifest_223750.acf"
    if manifest.is_file():
        try:
            manifest_payload = _read_regular_file(manifest, 2 * 1024 * 1024)
            manifest_text = manifest_payload.decode("utf-8-sig")
        except (ValueError, UnicodeDecodeError):
            manifest_text = ""
        match = re.search(r'"buildid"\s*"(?P<build>[0-9]+)"', manifest_text)
        if match is not None:
            steam_build_id = match.group("build")
    return {
        "product_version": product_version,
        "steam_build_id": steam_build_id,
    }


def _render_probe_script(
    request: dict[str, Any],
    *,
    request_sha256: str,
    dcs_identity: dict[str, str | None],
) -> str:
    samples = "\n".join(
        (
            "    { x = "
            f"{_lua_number(item['x'])}, y = {_lua_number(item['y'])} }},"
        )
        for item in request["samples"]
    )
    searches = "\n".join(
        (
            "    { x = "
            f"{_lua_number(item['x'])}, y = {_lua_number(item['y'])}, "
            f"radius = {_lua_number(item['radius_m'])}, "
            "minimum_altitude_msl = "
            f"{_lua_number(item['minimum_altitude_msl'])}, "
            "maximum_altitude_msl = "
            f"{_lua_number(item['maximum_altitude_msl'])} }},"
        )
        for item in request["object_searches"]
    )
    build = dcs_identity.get("steam_build_id")
    build_json = (
        ",\\\"steam_build_id\\\":"
        + _lua_string(build)
        if build is not None
        else ""
    )
    replacements = {
        "@@EXPECTED_TERRAIN@@": _lua_string(request["terrain"]),
        "@@REQUEST_SHA256@@": _lua_string(request_sha256),
        "@@PRODUCT_VERSION@@": _lua_string(
            str(dcs_identity["product_version"])
        ),
        "@@STEAM_BUILD_JSON@@": build_json,
        "@@TOLERANCE@@": _lua_number(
            request["sample_match_tolerance_m"]
        ),
        "@@MAX_OBJECTS@@": str(request["max_objects"]),
        "@@SAMPLES@@": samples,
        "@@SEARCHES@@": searches,
    }
    rendered = _LUA_TEMPLATE
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    if "@@" in rendered:
        raise ValueError("terrain probe template rendering is incomplete")
    return rendered


def _latest_complete_run(
    log_payload: bytes,
    request_hash: str,
) -> tuple[bytes, dict[str, Any]]:
    wanted = request_hash.encode("ascii")
    current: dict[str, Any] | None = None
    complete: list[tuple[bytes, dict[str, Any]]] = []
    for line_number, line in enumerate(log_payload.splitlines(), start=1):
        begin = _BEGIN.search(line)
        if begin is not None:
            total = int(begin.group("total"))
            if total > MAX_MARKER_CHUNKS:
                raise ValueError("terrain probe marker chunk count is excessive")
            current = (
                {
                    "hash": begin.group("hash"),
                    "total": total,
                    "chunks": {},
                    "begin_line": line_number,
                }
                if begin.group("hash") == wanted
                else None
            )
            continue
        chunk = _CHUNK.search(line)
        if chunk is not None and current is not None:
            if (
                chunk.group("hash") != current["hash"]
                or int(chunk.group("total")) != current["total"]
            ):
                continue
            index = int(chunk.group("index"))
            if not 1 <= index <= current["total"]:
                raise ValueError("terrain probe marker chunk index is invalid")
            if index in current["chunks"]:
                raise ValueError("terrain probe marker contains a duplicate chunk")
            current["chunks"][index] = chunk.group("data")
            continue
        end = _END.search(line)
        if end is not None and current is not None:
            if (
                end.group("hash") != current["hash"]
                or int(end.group("total")) != current["total"]
            ):
                current = None
                continue
            if len(current["chunks"]) == current["total"] and all(
                index in current["chunks"]
                for index in range(1, current["total"] + 1)
            ):
                encoded = b"".join(
                    current["chunks"][index]
                    for index in range(1, current["total"] + 1)
                )
                if len(encoded) > MAX_EVIDENCE_BYTES * 2:
                    raise ValueError(
                        "terrain probe marker payload exceeds the size limit"
                    )
                try:
                    payload = bytes.fromhex(encoded.decode("ascii"))
                except (UnicodeDecodeError, ValueError) as error:
                    raise ValueError(
                        "terrain probe marker payload is not valid hex"
                    ) from error
                if len(payload) > MAX_EVIDENCE_BYTES:
                    raise ValueError(
                        "terrain probe evidence exceeds the size limit"
                    )
                complete.append(
                    (
                        payload,
                        {
                            "request_sha256": request_hash,
                            "chunks": current["total"],
                            "begin_line": current["begin_line"],
                            "end_line": line_number,
                            "encoded_bytes": len(encoded),
                            "decoded_bytes": len(payload),
                        },
                    )
                )
            current = None
    if not complete:
        raise ValueError(
            "DCS log contains no complete matching terrain probe marker run"
        )
    return complete[-1]


def _validate_extracted_evidence(
    evidence: dict[str, Any],
    request: dict[str, Any],
    request_hash: str,
) -> None:
    if evidence.get("terrain") != request["terrain"]:
        raise ValueError("terrain probe evidence theatre does not match request")
    export = evidence.get("export")
    if not isinstance(export, dict):
        raise ValueError("terrain probe evidence export metadata is missing")
    if export.get("kind") != "dcs_mission_scripting_runtime_export":
        raise ValueError("terrain probe evidence export kind is not supported")
    if export.get("runtime_initialized") is not True:
        raise ValueError("terrain probe evidence did not run against terrain")
    if export.get("request_sha256") != request_hash:
        raise ValueError("terrain probe evidence request hash does not match")
    if export.get("object_limit") != request["max_objects"]:
        raise ValueError("terrain probe evidence object limit does not match")
    object_limit_reached = export.get("object_limit_reached")
    if not isinstance(object_limit_reached, bool):
        raise ValueError(
            "terrain probe evidence object-limit status is missing"
        )
    skipped_objects = export.get("object_records_skipped_without_geometry")
    if (
        isinstance(skipped_objects, bool)
        or not isinstance(skipped_objects, int)
        or skipped_objects < 0
    ):
        raise ValueError(
            "terrain probe evidence skipped-object count is invalid"
        )
    object_count = len(evidence["objects"])
    if object_count > request["max_objects"] or (
        object_count >= request["max_objects"]
        and not object_limit_reached
    ):
        raise ValueError(
            "terrain probe evidence object-limit status is inconsistent"
        )
    if not request["object_searches"] and (
        object_count or object_limit_reached or skipped_objects
    ):
        raise ValueError(
            "terrain probe evidence contains unrequested scenery results"
        )
    dcs = evidence.get("dcs")
    if (
        not isinstance(dcs, dict)
        or dcs.get("identity_source") != "probe_generation_install"
        or dcs.get("product_version_source")
        != "probe_generation_install"
        or dcs.get("runtime_identity_attested") is not False
    ):
        raise ValueError(
            "terrain probe evidence DCS identity provenance is invalid"
        )
    expected = {(item["x"], item["y"]) for item in request["samples"]}
    observed = {
        (float(item["x"]), float(item["y"]))
        for item in evidence["samples"]
    }
    if observed != expected or len(evidence["samples"]) != len(expected):
        raise ValueError("terrain probe evidence requested samples are incomplete")
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict) or coverage.get(
        "sample_match_tolerance_m"
    ) != request["sample_match_tolerance_m"]:
        raise ValueError("terrain probe evidence sample tolerance does not match")
    if coverage.get("object_searches") != request["object_searches"]:
        raise ValueError(
            "terrain probe evidence object-search coverage does not match"
        )
    expected_search_complete = (
        not object_limit_reached and skipped_objects == 0
    )
    if (
        coverage.get("object_search_complete")
        is not expected_search_complete
    ):
        raise ValueError(
            "terrain probe evidence object-search completeness is inconsistent"
        )
    if (
        coverage.get("object_search_complete_for_ground_placement")
        is not False
    ):
        raise ValueError(
            "terrain probe evidence ground-placement completeness is "
            "inconsistent"
        )
    if coverage.get("airfield_inventory_complete") is not False:
        raise ValueError(
            "terrain probe evidence airfield coverage is inconsistent"
        )
    if evidence["airfields"]:
        raise ValueError(
            "terrain probe evidence unexpectedly contains airfield records"
        )


def _load_json_object(payload: bytes, *, source_name: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{source_name} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{source_name} contains a non-finite JSON number")

    try:
        value = json.loads(
            payload.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError(f"{source_name} is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{source_name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{source_name} root must be an object")
    _validate_json_graph(value, source_name)
    return value


def _validate_json_graph(value: Any, source_name: str) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"{source_name} exceeds the JSON depth limit")
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"{source_name} contains a non-finite JSON number")


def _read_regular_file(path: Path, maximum_bytes: int) -> bytes:
    try:
        path_before = path.lstat()
    except OSError as error:
        raise ValueError("input file cannot be inspected safely") from error
    if not stat.S_ISREG(path_before.st_mode) or _is_reparse(path_before):
        raise ValueError("input path is not a safe regular file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("input file cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _is_reparse(before):
            raise ValueError("input path is not a safe regular file")
        if (path_before.st_dev, path_before.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise ValueError("input file changed before it could be read")
        if before.st_size > maximum_bytes:
            raise ValueError("input file exceeds its byte limit")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(payload) > maximum_bytes:
            raise ValueError("input file exceeds its byte limit")
        try:
            path_after = path.lstat()
        except OSError as error:
            raise ValueError("input file changed while being read") from error
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
            raise ValueError("input file changed while being read")
        if (
            not stat.S_ISREG(path_after.st_mode)
            or _is_reparse(path_after)
            or (path_after.st_dev, path_after.st_ino)
            != (after.st_dev, after.st_ino)
        ):
            raise ValueError("input file changed while being read")
        if len(payload) != before.st_size:
            raise ValueError("input file could not be read completely")
        return payload
    finally:
        os.close(descriptor)


def _write_output(path: Path, payload: bytes, *, force: bool) -> None:
    if not isinstance(force, bool):
        raise ValueError("force must be boolean")
    parent = path.parent
    parent_identity = _safe_directory_identity(parent)

    if not force:
        _write_output_exclusive(
            path,
            payload,
            parent=parent,
            parent_identity=parent_identity,
        )
        return

    try:
        current = path.lstat()
    except FileNotFoundError:
        current = None
    except OSError as error:
        raise ValueError("output path cannot be inspected safely") from error
    if current is not None:
        if not stat.S_ISREG(current.st_mode) or _is_reparse(current):
            raise ValueError("output path is not a safe regular file")
    current_identity = (
        (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
        )
        if current is not None
        else None
    )

    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            temporary_status = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(temporary_status.st_mode)
                or _is_reparse(temporary_status)
            ):
                raise OSError("temporary output is not a safe regular file")
            temporary_identity = (
                temporary_status.st_dev,
                temporary_status.st_ino,
            )
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _assert_directory_identity(parent, parent_identity)
        if temporary_identity is None:
            raise ValueError("temporary output identity is unavailable")
        _assert_output_identity(
            Path(temporary_name),
            temporary_identity,
        )
        try:
            latest = path.lstat()
        except FileNotFoundError:
            latest = None
        if latest is not None and (
            not stat.S_ISREG(latest.st_mode) or _is_reparse(latest)
        ):
            raise ValueError("output path changed before replacement")
        latest_identity = (
            (
                latest.st_dev,
                latest.st_ino,
                latest.st_size,
                latest.st_mtime_ns,
            )
            if latest is not None
            else None
        )
        if latest_identity != current_identity:
            raise ValueError("output path changed before replacement")
        os.replace(temporary_name, path)
        temporary_name = None
        _assert_output_identity(path, temporary_identity)
        _assert_directory_identity(parent, parent_identity)
    except OSError as error:
        raise ValueError("output file could not be written safely") from error
    finally:
        if temporary_name is not None and temporary_identity is not None:
            _unlink_matching_output(
                Path(temporary_name),
                temporary_identity,
            )


def _write_output_exclusive(
    path: Path,
    payload: bytes,
    *,
    parent: Path,
    parent_identity: tuple[int, int],
) -> None:
    """Create ``path`` once without a check-then-replace race."""

    _assert_directory_identity(parent, parent_identity)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ValueError(
            "output already exists; use force to replace it"
        ) from error
    except OSError as error:
        raise ValueError("output file could not be created safely") from error

    identity: tuple[int, int] | None = None
    completed = False
    try:
        status_result = os.fstat(descriptor)
        if not stat.S_ISREG(status_result.st_mode) or _is_reparse(status_result):
            raise OSError("created output is not a safe regular file")
        identity = (status_result.st_dev, status_result.st_ino)
        _assert_directory_identity(parent, parent_identity)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("output write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        _assert_directory_identity(parent, parent_identity)
        _assert_output_identity(path, identity)
        completed = True
    except OSError as error:
        raise ValueError("output file could not be written safely") from error
    finally:
        try:
            os.close(descriptor)
        finally:
            if not completed and identity is not None:
                _unlink_matching_output(path, identity)


def _safe_directory_identity(path: Path) -> tuple[int, int]:
    try:
        status_result = path.lstat()
    except OSError as error:
        raise ValueError("output parent directory does not exist") from error
    if (
        not stat.S_ISDIR(status_result.st_mode)
        or _is_reparse(status_result)
    ):
        raise ValueError("output parent is not a safe directory")
    return status_result.st_dev, status_result.st_ino


def _assert_directory_identity(
    path: Path,
    expected: tuple[int, int],
) -> None:
    if _safe_directory_identity(path) != expected:
        raise ValueError("output parent directory changed during write")


def _assert_output_identity(
    path: Path,
    expected: tuple[int, int],
) -> None:
    try:
        status_result = path.lstat()
    except OSError as error:
        raise ValueError("output path changed during write") from error
    if (
        not stat.S_ISREG(status_result.st_mode)
        or _is_reparse(status_result)
        or (status_result.st_dev, status_result.st_ino) != expected
    ):
        raise ValueError("output path changed during write")


def _unlink_matching_output(
    path: Path,
    identity: tuple[int, int],
) -> None:
    """Remove only the failed exclusive output that this process created."""

    try:
        current = path.lstat()
        current_identity = (current.st_dev, current.st_ino)
        if (
            current_identity == identity
            and stat.S_ISREG(current.st_mode)
            and not _is_reparse(current)
        ):
            path.unlink()
    except OSError:
        pass


def _extend_unique_samples(
    target: list[dict[str, float]],
    keys: set[tuple[float, float]],
    values: list[dict[str, float]],
) -> None:
    for value in values:
        key = (value["x"], value["y"])
        if key in keys:
            continue
        keys.add(key)
        target.append(value)
        if len(target) > MAX_SAMPLE_POINTS:
            raise ValueError(
                "expanded terrain probe samples exceeds the record limit"
            )


def _coordinate(value: Any, path: str) -> float:
    return _bounded_number(
        value,
        path,
        -MAX_ABS_COORDINATE,
        MAX_ABS_COORDINATE,
    )


def _bounded_number(
    value: Any,
    path: str,
    minimum: float,
    maximum: float,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{path} must be a finite number")
    result = float(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{path} is outside its supported range")
    return result


def _bounded_text(value: Any, path: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ValueError(f"{path} must be a nonempty bounded text value")
    return value


def _lua_number(value: float) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("cannot render a non-finite Lua number")
    rendered = format(float(value), ".17g")
    return "0" if rendered == "-0" else rendered


def _lua_string(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("cannot render a non-string Lua value")
    return json.dumps(value, ensure_ascii=False)


def _is_reparse(status_result: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(attribute and file_attributes & attribute)


_LUA_TEMPLATE = r'''-- Generated by DCSMizzer. Run manually as a DCS mission script.
-- It does not need io, lfs, package loading, or a weakened MissionScripting sandbox.
local expected_terrain = @@EXPECTED_TERRAIN@@
local request_sha256 = @@REQUEST_SHA256@@
local product_version = @@PRODUCT_VERSION@@
local sample_tolerance = @@TOLERANCE@@
local maximum_objects = @@MAX_OBJECTS@@
local requested_samples = {
@@SAMPLES@@
}
local object_searches = {
@@SEARCHES@@
}

local function json_string(value)
    local result = { '"' }
    for index = 1, #value do
        local byte = string.byte(value, index)
        if byte == 34 then
            result[#result + 1] = '\\"'
        elseif byte == 92 then
            result[#result + 1] = '\\\\'
        elseif byte == 8 then
            result[#result + 1] = '\\b'
        elseif byte == 9 then
            result[#result + 1] = '\\t'
        elseif byte == 10 then
            result[#result + 1] = '\\n'
        elseif byte == 12 then
            result[#result + 1] = '\\f'
        elseif byte == 13 then
            result[#result + 1] = '\\r'
        elseif byte < 32 then
            result[#result + 1] = string.format('\\u%04x', byte)
        else
            result[#result + 1] = string.char(byte)
        end
    end
    result[#result + 1] = '"'
    return table.concat(result)
end

local function json_number(value)
    if type(value) ~= 'number' or value ~= value
       or value == math.huge or value == -math.huge then
        error('probe encountered a non-finite number')
    end
    return string.format('%.17g', value)
end

local function sample_json(value)
    return '{"height_msl":' .. json_number(value.height_msl)
        .. ',"surface":' .. json_string(value.surface)
        .. ',"x":' .. json_number(value.x)
        .. ',"y":' .. json_number(value.y) .. '}'
end

local function object_json(value)
    local parts = {
        '{"center":{"x":', json_number(value.center.x),
        ',"y":', json_number(value.center.y),
        '},"model":', json_string(value.model),
    }
    if value.name then
        parts[#parts + 1] = ',"name":'
        parts[#parts + 1] = json_string(value.name)
    end
    parts[#parts + 1] = ',"radius":'
    parts[#parts + 1] = json_number(value.radius)
    parts[#parts + 1] = '}'
    return table.concat(parts)
end

local function object_search_json(value)
    return '{"complete_for_ground_placement":false'
        .. ',"maximum_altitude_msl":'
        .. json_number(value.maximum_altitude_msl)
        .. ',"minimum_altitude_msl":'
        .. json_number(value.minimum_altitude_msl)
        .. ',"radius_m":' .. json_number(value.radius)
        .. ',"volume_kind":"box_3d"'
        .. ',"x":' .. json_number(value.x)
        .. ',"y":' .. json_number(value.y) .. '}'
end

local function array_json(values, encoder)
    local parts = {}
    for index, value in ipairs(values) do
        parts[index] = encoder(value)
    end
    return '[' .. table.concat(parts, ',') .. ']'
end

local function surface_name(identifier)
    local names = {}
    if land.SurfaceType.LAND ~= nil then
        names[land.SurfaceType.LAND] = 'land'
    end
    if land.SurfaceType.WATER ~= nil then
        names[land.SurfaceType.WATER] = 'water'
    end
    if land.SurfaceType.SHALLOW_WATER ~= nil then
        names[land.SurfaceType.SHALLOW_WATER] = 'shallow_water'
    end
    if land.SurfaceType.ROAD ~= nil then
        names[land.SurfaceType.ROAD] = 'road'
    end
    if land.SurfaceType.RUNWAY ~= nil then
        names[land.SurfaceType.RUNWAY] = 'runway'
    end
    local value = names[identifier]
    if not value then
        error('probe encountered an unknown land surface type')
    end
    return value
end

local function hex_encode(value)
    local parts = {}
    for index = 1, #value do
        parts[index] = string.format('%02x', string.byte(value, index))
    end
    return table.concat(parts)
end

local function emit(payload)
    local encoded = hex_encode(payload)
    local chunk_size = 3000
    local total = math.ceil(#encoded / chunk_size)
    env.info('DCSMIZZER_TERRAIN_PROBE_BEGIN '
        .. request_sha256 .. ' ' .. tostring(total))
    for index = 1, total do
        local first = (index - 1) * chunk_size + 1
        local chunk = string.sub(encoded, first, first + chunk_size - 1)
        env.info('DCSMIZZER_TERRAIN_PROBE_CHUNK '
            .. request_sha256 .. ' ' .. tostring(index) .. '/'
            .. tostring(total) .. ' ' .. chunk)
    end
    env.info('DCSMIZZER_TERRAIN_PROBE_END '
        .. request_sha256 .. ' ' .. tostring(total))
end

local ok, failure = pcall(function()
    if not env or not env.mission or env.mission.theatre ~= expected_terrain then
        error('loaded mission theatre does not match the probe request')
    end
    if not land or not land.getHeight or not land.getSurfaceType then
        error('DCS land API is unavailable')
    end

    local samples = {}
    for index, point in ipairs(requested_samples) do
        local vec2 = { x = point.x, y = point.y }
        samples[index] = {
            x = point.x,
            y = point.y,
            height_msl = land.getHeight(vec2),
            surface = surface_name(land.getSurfaceType(vec2)),
        }
    end

    local objects = {}
    local object_keys = {}
    local object_limit_reached = false
    local skipped_without_geometry = 0
    if #object_searches > 0 then
        if not world or not world.searchObjects or not Object
           or not Object.Category or Object.Category.SCENERY == nil
           or not world.VolumeType or world.VolumeType.BOX == nil then
            error('DCS scenery search API is unavailable')
        end
        local function visit(object)
            if #objects >= maximum_objects then
                object_limit_reached = true
                return false
            end
            local position_ok, position = pcall(function()
                return object:getPosition()
            end)
            local description_ok, description = pcall(function()
                return object:getDesc()
            end)
            local type_ok, model = pcall(function()
                return object:getTypeName()
            end)
            if not position_ok or not description_ok
               or not position or not position.p or not description then
                skipped_without_geometry = skipped_without_geometry + 1
                return true
            end
            if not type_ok or type(model) ~= 'string' or model == '' then
                model = description.typeName
            end
            local box = description.box
            local geometry_ok = type(model) == 'string' and model ~= ''
                and box and box.min and box.max
                and position.x and position.z
                and type(position.p.x) == 'number'
                and type(position.p.z) == 'number'
                and type(position.x.x) == 'number'
                and type(position.x.z) == 'number'
                and type(position.z.x) == 'number'
                and type(position.z.z) == 'number'
                and type(box.min.x) == 'number'
                and type(box.max.x) == 'number'
                and type(box.min.z) == 'number'
                and type(box.max.z) == 'number'
            if not geometry_ok then
                skipped_without_geometry = skipped_without_geometry + 1
                return true
            end
            local length = math.abs(box.max.x - box.min.x)
            local width = math.abs(box.max.z - box.min.z)
            if length <= 0 or width <= 0 then
                skipped_without_geometry = skipped_without_geometry + 1
                return true
            end
            local local_center_x = 0.5 * (box.min.x + box.max.x)
            local local_center_z = 0.5 * (box.min.z + box.max.z)
            local x = position.p.x
                + position.x.x * local_center_x
                + position.z.x * local_center_z
            local y = position.p.z
                + position.x.z * local_center_x
                + position.z.z * local_center_z
            local key = model .. '|'
                .. string.format('%.3f|%.3f', x, y)
            if not object_keys[key] then
                object_keys[key] = true
                objects[#objects + 1] = {
                    model = model,
                    name = (
                        type(description.displayName) == 'string'
                        and description.displayName or nil
                    ),
                    center = { x = x, y = y },
                    radius = 0.5 * math.sqrt(
                        length * length + width * width
                    ),
                }
                if #objects >= maximum_objects then
                    object_limit_reached = true
                end
            end
            return not object_limit_reached
        end
        for _, query in ipairs(object_searches) do
            if object_limit_reached then
                break
            end
            local volume = {
                id = world.VolumeType.BOX,
                params = {
                    min = {
                        x = query.x - query.radius,
                        y = query.minimum_altitude_msl,
                        z = query.y - query.radius,
                    },
                    max = {
                        x = query.x + query.radius,
                        y = query.maximum_altitude_msl,
                        z = query.y + query.radius,
                    },
                },
            }
            world.searchObjects(Object.Category.SCENERY, volume, visit)
        end
    end
    table.sort(objects, function(left, right)
        if left.model ~= right.model then
            return left.model < right.model
        end
        if left.center.x ~= right.center.x then
            return left.center.x < right.center.x
        end
        return left.center.y < right.center.y
    end)

    local payload = '{"airfields":[]'
        .. ',"coverage":{"airfield_inventory_complete":false'
        .. ',"object_search_complete":'
        .. tostring(
            not object_limit_reached and skipped_without_geometry == 0
        )
        .. ',"object_search_complete_for_ground_placement":false'
        .. ',"object_searches":'
        .. array_json(object_searches, object_search_json)
        .. ',"sample_match_tolerance_m":'
        .. json_number(sample_tolerance)
        .. ',"sampling_design":"explicit_query_points"}'
        .. ',"dcs":{"identity_source":"probe_generation_install"'
        .. ',"product_version":' .. json_string(product_version)
        .. ',"product_version_source":"probe_generation_install"'
        .. ',"runtime_identity_attested":false'
        .. '@@STEAM_BUILD_JSON@@}'
        .. ',"export":{"kind":"dcs_mission_scripting_runtime_export"'
        .. ',"object_limit":' .. tostring(maximum_objects)
        .. ',"object_limit_reached":' .. tostring(object_limit_reached)
        .. ',"object_records_skipped_without_geometry":'
        .. tostring(skipped_without_geometry)
        .. ',"request_sha256":' .. json_string(request_sha256)
        .. ',"runtime_initialized":true'
        .. ',"runtime_time_utc_available":false}'
        .. ',"objects":' .. array_json(objects, object_json)
        .. ',"samples":' .. array_json(samples, sample_json)
        .. ',"schema":"dcsmizzer.terrain-physical-evidence/v1"'
        .. ',"terrain":' .. json_string(expected_terrain) .. '}'
    emit(payload)
end)

if not ok then
    env.error('DCSMIZZER_TERRAIN_PROBE_ERROR '
        .. request_sha256 .. ' ' .. tostring(failure))
end
'''
