"""Bounded normalization and integrity checks for initialized DCS registries."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .path_safety import canonical_existing_file


REGISTRY_SCHEMA = "dcsmizzer.initialized-registry/v1"
REPORT_SCHEMA = "dcsmizzer.initialized-registry-validation/v1"
RUNTIME_RESULT_SCHEMA = "dcsmizzer.runtime-result/v1"
MAX_REGISTRY_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 250_000
MAX_RECORDS = 50_000
MAX_IDENTIFIER_CHARS = 4_096
MAX_SOURCE_PATHS = 64

STAGE_NAMES = (
    "countries",
    "tasks",
    "units",
    "weapons",
    "pylons",
    "unit_shells",
)
CATEGORY_NAMES = frozenset(
    {
        "ad_equipments",
        "animals",
        "cargos",
        "cars",
        "effects",
        "fortifications",
        "grass_airfields",
        "ground_objects",
        "helicopters",
        "heliports",
        "lta_vehicles",
        "personnel",
        "planes",
        "ships",
        "warehouses",
        "wwii_structures",
    }
)


@dataclass
class _JsonState:
    nodes: int = 0
    active: set[int] = field(default_factory=set)


def validate_initialized_registry_file(path: Path) -> dict[str, Any]:
    """Read and validate one path-safe initialized-registry JSON document."""

    value, payload, name = _read_registry_file(Path(path))
    return initialized_registry_report(
        value,
        source={
            "name": name,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )


def initialized_registry_report(
    value: Any,
    *,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a path-free structural and referential-integrity report."""

    source_record = dict(source or {})
    try:
        normalized = normalize_initialized_registry(value)
    except ValueError as error:
        return {
            "schema": REPORT_SCHEMA,
            "source": source_record,
            "declared_identity": None,
            "coverage": {
                "stages": [],
                "all_stages_complete": False,
            },
            "counts": {},
            "canonical_registry": None,
            "referential_integrity": {
                "errors": [],
                "error_count": 0,
                "unresolved_launcher_clsids": [],
                "unresolved_launcher_count": 0,
            },
            "validation": {
                "structural_valid": False,
                "referential_integrity_valid": False,
                "coverage_complete": False,
                "registry_valid": False,
                "runtime_attestation_verified": False,
                "usable_as_current_initialized_authority": False,
                "format_errors": [str(error)],
            },
            "authority": "caller_supplied_structure_only",
            "limitations": _limitations(),
        }

    canonical = _canonical_bytes(normalized)
    integrity = _referential_integrity(normalized)
    coverage_complete = all(
        stage["complete"] for stage in normalized["coverage"]["stages"]
    )
    integrity_valid = integrity["error_count"] == 0
    counts = {
        name: len(normalized[name])
        for name in (
            "countries",
            "tasks",
            "units",
            "weapons",
            "launchers",
            "pylon_edges",
            "unit_shells",
        )
    }
    return {
        "schema": REPORT_SCHEMA,
        "source": source_record,
        "declared_identity": normalized["identity"],
        "coverage": {
            "stages": normalized["coverage"]["stages"],
            "all_stages_complete": coverage_complete,
        },
        "counts": counts,
        "canonical_registry": {
            "schema": REGISTRY_SCHEMA,
            "size_bytes": len(canonical),
            "sha256": hashlib.sha256(canonical).hexdigest(),
        },
        "referential_integrity": integrity,
        "validation": {
            "structural_valid": True,
            "referential_integrity_valid": integrity_valid,
            "coverage_complete": coverage_complete,
            "registry_valid": integrity_valid,
            "runtime_attestation_verified": False,
            "usable_as_current_initialized_authority": False,
            "format_errors": [],
        },
        "authority": "caller_supplied_structure_only",
        "limitations": _limitations(),
    }


def normalize_initialized_registry(value: Any) -> dict[str, Any]:
    """Normalize a registry deterministically or reject its exact structure."""

    generic = _normalize_json(value, _JsonState(), 0, "$")
    root = _object(generic, "$registry")
    _keys(
        root,
        "$registry",
        required={
            "schema",
            "identity",
            "coverage",
            "countries",
            "tasks",
            "units",
            "weapons",
            "launchers",
            "pylon_edges",
            "unit_shells",
        },
        optional={"extensions"},
    )
    if root["schema"] != REGISTRY_SCHEMA:
        raise ValueError(f"registry schema must be {REGISTRY_SCHEMA}")

    normalized = {
        "schema": REGISTRY_SCHEMA,
        "identity": _identity(root["identity"]),
        "coverage": _coverage(root["coverage"]),
        "countries": _countries(root["countries"]),
        "tasks": _tasks(root["tasks"]),
        "units": _units(root["units"]),
        "weapons": _weapons(root["weapons"]),
        "launchers": _launchers(root["launchers"]),
        "pylon_edges": _pylon_edges(root["pylon_edges"]),
        "unit_shells": _unit_shells(root["unit_shells"]),
        "extensions": _extensions(root.get("extensions"), "$registry.extensions"),
    }
    canonical = _canonical_bytes(normalized)
    if len(canonical) > MAX_REGISTRY_BYTES:
        raise ValueError("normalized registry exceeds the byte limit")
    return normalized


def _identity(value: Any) -> dict[str, Any]:
    record = _object(value, "identity")
    _keys(
        record,
        "identity",
        required={"run_id", "product_version", "source_schema"},
        optional={"extensions"},
    )
    source_schema = _identifier(record["source_schema"], "identity.source_schema")
    if source_schema != RUNTIME_RESULT_SCHEMA:
        raise ValueError(
            f"identity.source_schema must be {RUNTIME_RESULT_SCHEMA}"
        )
    return {
        "run_id": _identifier(record["run_id"], "identity.run_id"),
        "product_version": _identifier(
            record["product_version"],
            "identity.product_version",
        ),
        "source_schema": source_schema,
        "extensions": _extensions(
            record.get("extensions"),
            "identity.extensions",
        ),
    }


def _coverage(value: Any) -> dict[str, Any]:
    record = _object(value, "coverage")
    _keys(record, "coverage", required={"stages"}, optional={"extensions"})
    stages = _records(record["stages"], "coverage.stages")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(stages):
        path = f"coverage.stages[{index}]"
        stage = _object(raw, path)
        _keys(
            stage,
            path,
            required={"name", "complete", "source_paths"},
            optional={"extensions"},
        )
        name = _identifier(stage["name"], f"{path}.name")
        if name not in STAGE_NAMES:
            raise ValueError(f"{path}.name is not a recognized stage")
        if name in seen:
            raise ValueError(f"coverage stage {name!r} is duplicated")
        seen.add(name)
        complete = stage["complete"]
        if not isinstance(complete, bool):
            raise ValueError(f"{path}.complete must be a Boolean")
        source_paths = _string_list(
            stage["source_paths"],
            f"{path}.source_paths",
            maximum=MAX_SOURCE_PATHS,
        )
        normalized.append(
            {
                "name": name,
                "complete": complete,
                "source_paths": source_paths,
                "extensions": _extensions(
                    stage.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    missing = sorted(set(STAGE_NAMES) - seen)
    if missing:
        raise ValueError("coverage is missing stages: " + ", ".join(missing))
    order = {name: index for index, name in enumerate(STAGE_NAMES)}
    normalized.sort(key=lambda item: order[item["name"]])
    return {
        "stages": normalized,
        "extensions": _extensions(record.get("extensions"), "coverage.extensions"),
    }


def _countries(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for index, raw in enumerate(_records(value, "countries")):
        path = f"countries[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"id", "name"},
            optional={"extensions"},
        )
        identifier = _nonnegative_integer(record["id"], f"{path}.id")
        name = _identifier(record["name"], f"{path}.name")
        _unique(identifier, seen_ids, f"country id {identifier}")
        _unique(name, seen_names, f"country name {name!r}")
        result.append(
            {
                "id": identifier,
                "name": name,
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: (item["id"], item["name"]))


def _tasks(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, raw in enumerate(_records(value, "tasks")):
        path = f"tasks[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"id", "name"},
            optional={"extensions"},
        )
        identifier = _nonnegative_integer(record["id"], f"{path}.id")
        _unique(identifier, seen, f"task id {identifier}")
        result.append(
            {
                "id": identifier,
                "name": _identifier(record["name"], f"{path}.name"),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: item["id"])


def _units(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_records(value, "units")):
        path = f"units[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={
                "type_name",
                "category",
                "country_ids",
                "task_ids",
                "default_task_id",
                "flyable",
                "attributes",
            },
            optional={"extensions"},
        )
        type_name = _identifier(record["type_name"], f"{path}.type_name")
        _unique(type_name, seen, f"unit type {type_name!r}")
        category = _identifier(record["category"], f"{path}.category")
        if category not in CATEGORY_NAMES:
            raise ValueError(f"{path}.category is not recognized")
        flyable = record["flyable"]
        if not isinstance(flyable, bool):
            raise ValueError(f"{path}.flyable must be a Boolean")
        result.append(
            {
                "type_name": type_name,
                "category": category,
                "country_ids": _integer_list(
                    record["country_ids"],
                    f"{path}.country_ids",
                ),
                "task_ids": _integer_list(
                    record["task_ids"],
                    f"{path}.task_ids",
                ),
                "default_task_id": _optional_nonnegative_integer(
                    record["default_task_id"],
                    f"{path}.default_task_id",
                ),
                "flyable": flyable,
                "attributes": _string_list(
                    record["attributes"],
                    f"{path}.attributes",
                ),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: item["type_name"])


def _weapons(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_records(value, "weapons")):
        path = f"weapons[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"clsid", "type_name"},
            optional={"extensions"},
        )
        clsid = _identifier(record["clsid"], f"{path}.clsid")
        _unique(clsid, seen, f"weapon CLSID {clsid!r}")
        result.append(
            {
                "clsid": clsid,
                "type_name": _identifier(record["type_name"], f"{path}.type_name"),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: item["clsid"])


def _launchers(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_records(value, "launchers")):
        path = f"launchers[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"clsid", "weapon_clsid", "settings"},
            optional={"extensions"},
        )
        clsid = _identifier(record["clsid"], f"{path}.clsid")
        _unique(clsid, seen, f"launcher CLSID {clsid!r}")
        weapon_clsid = record["weapon_clsid"]
        if weapon_clsid is not None:
            weapon_clsid = _identifier(weapon_clsid, f"{path}.weapon_clsid")
        result.append(
            {
                "clsid": clsid,
                "weapon_clsid": weapon_clsid,
                "settings": _object(record["settings"], f"{path}.settings"),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: item["clsid"])


def _pylon_edges(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for index, raw in enumerate(_records(value, "pylon_edges")):
        path = f"pylon_edges[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"unit_type", "station", "launcher_clsid", "settings"},
            optional={"extensions"},
        )
        unit_type = _identifier(record["unit_type"], f"{path}.unit_type")
        station = _positive_integer(record["station"], f"{path}.station")
        launcher = _identifier(
            record["launcher_clsid"],
            f"{path}.launcher_clsid",
        )
        key = (unit_type, station, launcher)
        _unique(key, seen, f"pylon edge {key!r}")
        result.append(
            {
                "unit_type": unit_type,
                "station": station,
                "launcher_clsid": launcher,
                "settings": _object(record["settings"], f"{path}.settings"),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            item["unit_type"],
            item["station"],
            item["launcher_clsid"],
        ),
    )


def _unit_shells(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_records(value, "unit_shells")):
        path = f"unit_shells[{index}]"
        record = _object(raw, path)
        _keys(
            record,
            path,
            required={"unit_type", "fields"},
            optional={"extensions"},
        )
        unit_type = _identifier(record["unit_type"], f"{path}.unit_type")
        _unique(unit_type, seen, f"unit shell {unit_type!r}")
        result.append(
            {
                "unit_type": unit_type,
                "fields": _object(record["fields"], f"{path}.fields"),
                "extensions": _extensions(
                    record.get("extensions"),
                    f"{path}.extensions",
                ),
            }
        )
    return sorted(result, key=lambda item: item["unit_type"])


def _referential_integrity(registry: dict[str, Any]) -> dict[str, Any]:
    countries = {record["id"] for record in registry["countries"]}
    tasks = {record["id"] for record in registry["tasks"]}
    units = {record["type_name"] for record in registry["units"]}
    weapons = {record["clsid"] for record in registry["weapons"]}
    launchers = {record["clsid"] for record in registry["launchers"]}
    errors: list[dict[str, Any]] = []
    unresolved_launchers: list[str] = []

    def add(code: str, path: str, target: Any) -> None:
        errors.append({"code": code, "path": path, "target": target})

    for index, unit in enumerate(registry["units"]):
        for country in unit["country_ids"]:
            if country not in countries:
                add("unit_country_missing", f"units[{index}].country_ids", country)
        for task in unit["task_ids"]:
            if task not in tasks:
                add("unit_task_missing", f"units[{index}].task_ids", task)
        default_task = unit["default_task_id"]
        if default_task is not None:
            if default_task not in tasks:
                add(
                    "unit_default_task_missing",
                    f"units[{index}].default_task_id",
                    default_task,
                )
            if default_task not in unit["task_ids"]:
                add(
                    "unit_default_task_not_supported",
                    f"units[{index}].default_task_id",
                    default_task,
                )

    for index, launcher in enumerate(registry["launchers"]):
        weapon = launcher["weapon_clsid"]
        if weapon is None or weapon not in weapons:
            unresolved_launchers.append(launcher["clsid"])
            add(
                "launcher_weapon_unresolved",
                f"launchers[{index}].weapon_clsid",
                weapon,
            )

    for index, edge in enumerate(registry["pylon_edges"]):
        if edge["unit_type"] not in units:
            add(
                "pylon_unit_missing",
                f"pylon_edges[{index}].unit_type",
                edge["unit_type"],
            )
        if edge["launcher_clsid"] not in launchers:
            add(
                "pylon_launcher_missing",
                f"pylon_edges[{index}].launcher_clsid",
                edge["launcher_clsid"],
            )

    for index, shell in enumerate(registry["unit_shells"]):
        if shell["unit_type"] not in units:
            add(
                "unit_shell_unit_missing",
                f"unit_shells[{index}].unit_type",
                shell["unit_type"],
            )

    return {
        "errors": errors,
        "error_count": len(errors),
        "unresolved_launcher_clsids": sorted(unresolved_launchers),
        "unresolved_launcher_count": len(unresolved_launchers),
    }


def _normalize_json(value: Any, state: _JsonState, depth: int, path: str) -> Any:
    state.nodes += 1
    if state.nodes > MAX_JSON_NODES:
        raise ValueError("registry exceeds the JSON node limit")
    if depth > MAX_JSON_DEPTH:
        raise ValueError("registry exceeds the JSON depth limit")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if not isinstance(value, (dict, list)):
        raise ValueError(f"{path} contains an unsupported JSON value")
    identity = id(value)
    if identity in state.active:
        raise ValueError(f"{path} contains a cycle")
    state.active.add(identity)
    try:
        if isinstance(value, list):
            return [
                _normalize_json(item, state, depth + 1, f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{path} contains a non-string object key")
        result: dict[str, Any] = {}
        for key in sorted(value):
            result[key] = _normalize_json(
                value[key],
                state,
                depth + 1,
                f"{path}.{key}",
            )
        return result
    finally:
        state.active.remove(identity)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return dict(value)


def _records(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    if len(value) > MAX_RECORDS:
        raise ValueError(f"{path} exceeds the record limit")
    return value


def _keys(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str],
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ValueError(f"{path} is missing keys: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{path} has unknown keys: {', '.join(unknown)}")


def _identifier(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDENTIFIER_CHARS
        or "\x00" in value
    ):
        raise ValueError(f"{path} must be a bounded non-empty string")
    return value


def _nonnegative_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a nonnegative integer")
    return value


def _positive_integer(value: Any, path: str) -> int:
    result = _nonnegative_integer(value, path)
    if result == 0:
        raise ValueError(f"{path} must be a positive integer")
    return result


def _optional_nonnegative_integer(value: Any, path: str) -> int | None:
    return None if value is None else _nonnegative_integer(value, path)


def _integer_list(value: Any, path: str) -> list[int]:
    values = _records(value, path)
    result = [
        _nonnegative_integer(item, f"{path}[{index}]")
        for index, item in enumerate(values)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{path} contains duplicate integers")
    return sorted(result)


def _string_list(
    value: Any,
    path: str,
    *,
    maximum: int = MAX_RECORDS,
) -> list[str]:
    values = _records(value, path)
    if len(values) > maximum:
        raise ValueError(f"{path} exceeds the item limit")
    result = [
        _identifier(item, f"{path}[{index}]")
        for index, item in enumerate(values)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{path} contains duplicate strings")
    return sorted(result)


def _extensions(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    return _object(value, path)


def _unique(value: Any, seen: set[Any], label: str) -> None:
    if value in seen:
        raise ValueError(f"duplicate {label}")
    seen.add(value)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("registry cannot be encoded canonically") from error


def _read_registry_file(path: Path) -> tuple[Any, bytes, str]:
    candidate = canonical_existing_file(path, "initialized registry")
    before = candidate.stat()
    if before.st_size > MAX_REGISTRY_BYTES:
        raise ValueError("initialized registry exceeds the byte limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(candidate, flags)
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("initialized registry changed before it was read")
        chunks: list[bytes] = []
        remaining = MAX_REGISTRY_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(payload) > MAX_REGISTRY_BYTES:
        raise ValueError("initialized registry exceeds the byte limit")
    if (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("initialized registry changed while it was read")
    final = candidate.stat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        final.st_dev,
        final.st_ino,
        final.st_size,
        final.st_mtime_ns,
    ):
        raise ValueError("initialized registry changed while it was read")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("initialized registry contains a duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("initialized registry contains a non-finite number")

    try:
        value = json.loads(
            payload.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError("initialized registry is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError("initialized registry is not valid JSON") from error
    return value, payload, candidate.name


def _limitations() -> list[str]:
    return [
        "This validator proves bounded schema and internal references only.",
        "A caller-supplied file is not a runtime-attested initialized export.",
        "Coverage flags describe the supplied slice and do not prove omitted data.",
        "Unknown launcher CLSIDs remain explicit and prevent integrity readiness.",
    ]
