"""Privacy-preserving registries derived from explicitly supplied MIZ roots."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .archive import ArchivePolicy, inspect_miz
from .facts import (
    CATEGORIES,
    classify_start_mode,
    numeric_tables,
    numeric_values,
    string_fields,
    table,
)
from .lua import LuaDataError, LuaLimits, LuaTable, parse_lua_bytes


_SAFE_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_DCS_PREDICATE = re.compile(
    r"\b(?P<name>[ac]_[A-Za-z][A-Za-z0-9_]*)\b"
)
_READ_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ObservedRoot:
    """A caller-chosen public label and a private local evidence location."""

    label: str
    path: Path

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("observed root label must be nonempty")


@dataclass(frozen=True)
class _ParsedMission:
    mission: LuaTable
    theatre: str
    options: LuaTable | None
    warehouses: LuaTable | None
    optional_core_errors: tuple[str, ...]


@dataclass(frozen=True)
class _ContentOutcome:
    archive_valid: bool
    parsed: _ParsedMission | None
    error_code: str | None


@dataclass(frozen=True)
class _ReadOutcome:
    content_hash: str | None
    content: _ContentOutcome
    cache_hit: bool


class _DiscoveredFileChangedError(Exception):
    """A discovered path stopped naming the same regular non-link file."""


class _PathLinkError(Exception):
    """A path component is a symbolic link, junction, or reparse point."""


@dataclass(frozen=True)
class _PathComponentSnapshot:
    path: Path
    identity: tuple[int, int]
    file_type: int


@dataclass(frozen=True)
class _RootSnapshot:
    path: Path
    resolved: Path
    is_file: bool
    components: tuple[_PathComponentSnapshot, ...]


@dataclass(frozen=True)
class _DiscoveredFile:
    path: Path
    components: tuple[_PathComponentSnapshot, ...]
    identity: tuple[int, int]
    size: int
    modified_ns: int


def build_observed_registry(
    roots: tuple[ObservedRoot, ...],
    *,
    theatre: str | None = None,
    unit_type: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Scan local MIZ files and emit linked facts without file-level identity."""

    if not roots:
        raise ValueError("at least one observed root is required")
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"unsupported mission category: {category!r}")
    labels = [root.label for root in roots]
    invalid_labels = [
        label for label in labels if _SAFE_LABEL.fullmatch(label) is None
    ]
    if invalid_labels:
        raise ValueError(
            "observed root labels must be anonymous ASCII tokens"
        )
    if len(set(labels)) != len(labels):
        raise ValueError("observed root labels must be unique")
    root_snapshots: list[_RootSnapshot] = []
    for root in roots:
        root_snapshots.append(_snapshot_root(root))

    cache: dict[str, _ContentOutcome] = {}
    source_reports: list[dict[str, Any]] = []
    parsed_hashes: set[str] = set()
    duplicate_instances = 0

    unit_records: dict[str, dict[str, Any]] = {}
    payload_records: dict[tuple[Any, ...], dict[str, Any]] = {}
    airbase_records: dict[tuple[str, int | float], dict[str, Any]] = {}
    group_structures: dict[str, Counter[tuple[str, ...]]] = {
        category: Counter() for category in CATEGORIES
    }
    waypoint_structures: dict[str, Counter[tuple[str, ...]]] = {
        category: Counter() for category in CATEGORIES
    }
    theatres: Counter[str] = Counter()
    matching_missions = 0
    environment = _new_environment_record()
    core_tables = _new_core_table_record()

    for root, root_snapshot in zip(roots, root_snapshots, strict=True):
        source = {
            "label": root.label,
            "files_seen": 0,
            "archive_valid_instances": 0,
            "parse_valid_instances": 0,
            "unique_content_contributed": 0,
            "duplicate_instances": 0,
            "errors": Counter(),
        }
        discovery_errors: Counter[str] = source["errors"]
        for discovered in _discover_miz(root_snapshot, discovery_errors):
            source["files_seen"] += 1
            try:
                read = _read_discovered_file(
                    discovered,
                    root_snapshot,
                    cache,
                )
            except OSError:
                discovery_errors["read_error"] += 1
                continue
            except _DiscoveredFileChangedError:
                discovery_errors["discovery_file_changed_skipped"] += 1
                continue
            content_hash = read.content_hash
            outcome = read.content
            if content_hash is None:
                if outcome.error_code is not None:
                    discovery_errors[outcome.error_code] += 1
                continue
            if read.cache_hit:
                duplicate_instances += 1
                source["duplicate_instances"] += 1
            else:
                source["unique_content_contributed"] += 1
            if outcome.archive_valid:
                source["archive_valid_instances"] += 1
            if outcome.parsed is None:
                if outcome.error_code is not None:
                    discovery_errors[outcome.error_code] += 1
                continue
            source["parse_valid_instances"] += 1
            if content_hash in parsed_hashes:
                continue
            parsed_hashes.add(content_hash)
            if _aggregate_mission(
                outcome.parsed,
                content_hash,
                theatre_filter=theatre,
                unit_type_filter=unit_type,
                category_filter=category,
                unit_records=unit_records,
                payload_records=payload_records,
                airbase_records=airbase_records,
                group_structures=group_structures,
                waypoint_structures=waypoint_structures,
            ):
                matching_missions += 1
                theatres[outcome.parsed.theatre] += 1
                _aggregate_environment(
                    outcome.parsed.mission,
                    content_hash,
                    environment,
                )
                _aggregate_core_tables(
                    outcome.parsed,
                    content_hash,
                    core_tables,
                )

        source["errors"] = dict(sorted(discovery_errors.items()))
        source_reports.append(source)

    theatre_refs = _identity_refs(
        theatres,
        prefix="observed-theatre",
        exact_filter=theatre,
    )
    unit_refs = _identity_refs(
        unit_records,
        prefix="observed-unit-type",
        exact_filter=unit_type,
    )
    store_refs = _identity_refs(
        {
            assignment["CLSID"]
            for record in payload_records.values()
            for assignment in record["assignments"]
        },
        prefix="observed-store",
    )
    return {
        "schema": "dcsmizzer.observed-miz-registry/v1",
        "authority": "parsed_local_missions_observed",
        "dcs_started": False,
        "filters": {
            "theatre": theatre,
            "unit_type": unit_type,
            "category": category,
        },
        "coverage": {
            "sources": source_reports,
            "file_instances": sum(item["files_seen"] for item in source_reports),
            "unique_contents_seen": len(cache),
            "unique_missions": len(parsed_hashes),
            "duplicate_instances": duplicate_instances,
            "missions_matching_filters": matching_missions,
            "content_identity_returned": False,
        },
        "theatres": [
            {
                "theatre_ref": theatre_refs[name],
                "identity_source": (
                    "caller_exact_filter"
                    if theatre is not None
                    else "anonymous_observation"
                ),
                "missions": count,
            }
            for name, count in sorted(theatres.items())
        ],
        "unit_types": _unit_report(
            unit_records,
            unit_refs,
            exact_filter=unit_type,
        ),
        "payloads": _payload_report(
            payload_records,
            unit_refs,
            store_refs,
        ),
        "airbases": _airbase_report(
            airbase_records,
            theatre_refs,
            unit_refs,
        ),
        "environment": _environment_report(environment),
        "core_tables": _core_table_report(core_tables),
        "structures": {
            "group_field_sets": _structure_report(group_structures),
            "waypoint_field_sets": _structure_report(waypoint_structures),
        },
        "privacy": {
            "omitted": [
                "absolute source paths",
                "mission filenames",
                "mission titles and briefing text",
                "group and unit names",
                "per-file hashes",
                "unfiltered observed technical identity strings",
            ]
        },
        "limitations": [
            "Every fact is observed in the supplied MIZ corpus, not a complete "
            "initialized DCS registry.",
            "Observed payload assignments do not prove every legal "
            "store-to-station combination.",
            "Observed airbase and parking facts cover only starts/routes present "
            "in the supplied missions.",
            "Observed environment schemas and scalar ranges are examples, not "
            "the complete set of values accepted by DCS.",
            "Options and warehouse reports expose only anonymous field shapes, "
            "types, counts, and reference coverage; authored device IDs and "
            "player names are never returned.",
            "No Lua code was executed and no DCS or Mission Editor process was "
            "started.",
        ],
    }


def _parse_content(
    stream: BinaryIO,
    archive: Any,
) -> _ContentOutcome:
    archive_valid = _archive_is_valid(archive)
    if not archive_valid:
        return _ContentOutcome(
            False,
            None,
            _archive_failure_code(archive),
    )
    limits = LuaLimits()
    try:
        stream.seek(0)
        with zipfile.ZipFile(stream) as miz:
            info = miz.getinfo("mission")
            if info.file_size > limits.max_input_bytes:
                return _ContentOutcome(True, None, "mission_input_limit")
            parsed = parse_lua_bytes(miz.read(info), limits=limits)
            options, options_error = _optional_core_table(
                miz,
                member="options",
                global_name="options",
                limits=limits,
            )
            warehouses, warehouses_error = _optional_core_table(
                miz,
                member="warehouses",
                global_name="warehouses",
                limits=limits,
            )
    except KeyError:
        return _ContentOutcome(True, None, "mission_missing")
    except (OSError, zipfile.BadZipFile):
        return _ContentOutcome(False, None, "archive_read_error")
    except LuaDataError as error:
        return _ContentOutcome(True, None, type(error).__name__)
    mission = parsed.document.get("mission")
    if mission is None and isinstance(parsed.document.returned, LuaTable):
        mission = parsed.document.returned
    if not isinstance(mission, LuaTable):
        return _ContentOutcome(True, None, "mission_table_missing")
    theatre = mission.get("theatre")
    if not isinstance(theatre, str):
        return _ContentOutcome(True, None, "theatre_missing")
    optional_errors = tuple(
        error
        for error in (options_error, warehouses_error)
        if error is not None
    )
    return _ContentOutcome(
        True,
        _ParsedMission(
            mission,
            theatre,
            options,
            warehouses,
            optional_errors,
        ),
        None,
    )


def _archive_is_valid(archive: Any) -> bool:
    return bool(
        archive.valid_zip
        and archive.safe
        and archive.crc_status == "passed"
        and archive.duplicate_member_extras == 0
    )


def _optional_core_table(
    archive: zipfile.ZipFile,
    *,
    member: str,
    global_name: str,
    limits: LuaLimits,
) -> tuple[LuaTable | None, str | None]:
    try:
        info = archive.getinfo(member)
    except KeyError:
        return None, f"{member}_missing"
    if info.file_size > limits.max_input_bytes:
        return None, f"{member}_input_limit"
    try:
        parsed = parse_lua_bytes(archive.read(info), limits=limits)
    except (OSError, LuaDataError) as error:
        return None, f"{member}_{type(error).__name__}"
    value = parsed.document.get(global_name)
    if value is None and isinstance(parsed.document.returned, LuaTable):
        value = parsed.document.returned
    if not isinstance(value, LuaTable):
        return None, f"{member}_table_missing"
    return value, None


def _archive_failure_code(archive: Any) -> str:
    if not archive.valid_zip:
        return "archive_bad_zip"
    if archive.duplicate_member_extras:
        return "archive_duplicate_members"
    if archive.crc_status == "failed":
        return "archive_crc_failed"
    error_codes = sorted(
        {
            diagnostic.code
            for diagnostic in archive.diagnostics
            if diagnostic.severity == "error"
        }
    )
    if error_codes:
        return f"archive_policy_{error_codes[0]}"
    return "archive_invalid"


def _aggregate_mission(
    parsed: _ParsedMission,
    content_hash: str,
    *,
    theatre_filter: str | None,
    unit_type_filter: str | None,
    category_filter: str | None,
    unit_records: dict[str, dict[str, Any]],
    payload_records: dict[tuple[Any, ...], dict[str, Any]],
    airbase_records: dict[tuple[str, int | float], dict[str, Any]],
    group_structures: dict[str, Counter[tuple[str, ...]]],
    waypoint_structures: dict[str, Counter[tuple[str, ...]]],
) -> bool:
    if theatre_filter is not None and parsed.theatre != theatre_filter:
        return False
    mission_matches = unit_type_filter is None and category_filter is None
    coalition = table(parsed.mission.get("coalition"))
    for side_field in coalition.fields:
        side_name = str(side_field.key)
        side = table(side_field.value)
        for country_value in numeric_values(side.get("country")):
            country = table(country_value)
            country_id = country.get("id")
            for category in CATEGORIES:
                if category_filter is not None and category != category_filter:
                    continue
                category_table = table(country.get(category))
                for group_value in numeric_values(category_table.get("group")):
                    group = table(group_value)
                    all_units = numeric_tables(group.get("units"))
                    units = [
                        unit
                        for unit in all_units
                        if (
                            unit_type_filter is None
                            or unit.get("type") == unit_type_filter
                        )
                    ]
                    if not units:
                        continue
                    mission_matches = True
                    group_structures[category][
                        tuple(sorted(string_fields(group)))
                    ] += 1
                    points = numeric_tables(table(group.get("route")).get("points"))
                    for point in points:
                        waypoint_structures[category][
                            tuple(sorted(string_fields(point)))
                        ] += 1
                    _aggregate_group(
                        parsed.theatre,
                        content_hash,
                        side_name,
                        country_id,
                        category,
                        group,
                        points,
                        units,
                        unit_records,
                        payload_records,
                        airbase_records,
                    )
    return mission_matches


def _new_environment_record() -> dict[str, Any]:
    return {
        "missions": set(),
        "mission_field_sets": Counter(),
        "weather_present": 0,
        "weather_missing": 0,
        "weather_table_field_sets": defaultdict(Counter),
        "weather_scalars": {},
        "metadata_scalars": {},
        "logic": {
            "zone_field_sets": Counter(),
            "trigger_rule_field_sets": Counter(),
            "condition_field_sets": Counter(),
            "action_field_sets": Counter(),
            "goal_field_sets": Counter(),
            "goal_condition_field_sets": Counter(),
            "condition_predicates": Counter(),
            "action_predicates": Counter(),
            "goal_predicates": Counter(),
        },
    }


def _new_core_table_record() -> dict[str, Any]:
    return {
        "missions": set(),
        "optional_core_errors": Counter(),
        "required_modules": {
            "present": 0,
            "missing": 0,
            "empty": 0,
            "nonempty": 0,
            "entries": Counter(),
            "invalid_shape": 0,
        },
        "options": {
            "present": 0,
            "missing": 0,
            "top_field_sets": Counter(),
            "known_table_field_sets": defaultdict(Counter),
            "player_name_present": 0,
            "player_name_nonempty": 0,
            "plugin_entry_counts": Counter(),
            "nonempty_audio_device_fields": Counter(),
        },
        "warehouses": {
            "present": 0,
            "missing": 0,
            "top_field_sets": Counter(),
            "airport_counts": Counter(),
            "warehouse_object_counts": Counter(),
            "airport_entry_field_sets": Counter(),
            "airport_numeric_keys": 0,
            "airport_nonnumeric_keys": 0,
            "route_airdrome_references": 0,
            "route_airdrome_references_resolved": 0,
            "route_airdrome_references_missing": 0,
        },
    }


def _aggregate_core_tables(
    parsed: _ParsedMission,
    content_hash: str,
    record: dict[str, Any],
) -> None:
    record["missions"].add(content_hash)
    record["optional_core_errors"].update(parsed.optional_core_errors)
    required = parsed.mission.get("requiredModules")
    required_record = record["required_modules"]
    if not isinstance(required, LuaTable):
        required_record["missing"] += 1
    else:
        required_record["present"] += 1
        count = len(required.fields)
        required_record["entries"][count] += 1
        required_record["empty" if count == 0 else "nonempty"] += 1
        if any(
            not isinstance(field.key, str)
            or not isinstance(field.value, str)
            or field.key != field.value
            for field in required.fields
        ):
            required_record["invalid_shape"] += 1

    options_record = record["options"]
    options = parsed.options
    if not isinstance(options, LuaTable):
        options_record["missing"] += 1
    else:
        options_record["present"] += 1
        options_record["top_field_sets"][
            tuple(sorted(string_fields(options)))
        ] += 1
        for field_name in (
            "VR",
            "difficulty",
            "graphics",
            "miscellaneous",
            "sound",
            "views",
        ):
            child = options.get(field_name)
            if isinstance(child, LuaTable):
                options_record["known_table_field_sets"][field_name][
                    tuple(sorted(string_fields(child)))
                ] += 1
        player_name = options.get("playerName")
        if isinstance(player_name, str):
            options_record["player_name_present"] += 1
            if player_name.strip():
                options_record["player_name_nonempty"] += 1
        plugins = options.get("plugins")
        if isinstance(plugins, LuaTable):
            options_record["plugin_entry_counts"][len(plugins.fields)] += 1
        sound = options.get("sound")
        if isinstance(sound, LuaTable):
            for field_name in (
                "hp_output",
                "main_output",
                "main_layout",
                "voice_chat_output",
                "voice_chat_input",
            ):
                value = sound.get(field_name)
                if isinstance(value, str) and value:
                    options_record["nonempty_audio_device_fields"][
                        field_name
                    ] += 1

    warehouses_record = record["warehouses"]
    warehouses = parsed.warehouses
    if not isinstance(warehouses, LuaTable):
        warehouses_record["missing"] += 1
        return
    warehouses_record["present"] += 1
    warehouses_record["top_field_sets"][
        tuple(sorted(string_fields(warehouses)))
    ] += 1
    airports = warehouses.get("airports")
    warehouse_objects = warehouses.get("warehouses")
    airport_table = table(airports)
    object_table = table(warehouse_objects)
    warehouses_record["airport_counts"][len(airport_table.fields)] += 1
    warehouses_record["warehouse_object_counts"][
        len(object_table.fields)
    ] += 1
    for field in airport_table.fields:
        if _is_number(field.key):
            warehouses_record["airport_numeric_keys"] += 1
        else:
            warehouses_record["airport_nonnumeric_keys"] += 1
        if isinstance(field.value, LuaTable):
            warehouses_record["airport_entry_field_sets"][
                tuple(sorted(string_fields(field.value)))
            ] += 1

    airdrome_ids: set[int | float] = set()
    coalition = table(parsed.mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country in numeric_tables(side.get("country")):
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group in numeric_tables(category_table.get("group")):
                    for point in numeric_tables(
                        table(group.get("route")).get("points")
                    ):
                        identifier = point.get("airdromeId")
                        if _is_number(identifier):
                            airdrome_ids.add(identifier)
    warehouses_record["route_airdrome_references"] += len(airdrome_ids)
    resolved = sum(airport_table.has(identifier) for identifier in airdrome_ids)
    warehouses_record["route_airdrome_references_resolved"] += resolved
    warehouses_record["route_airdrome_references_missing"] += (
        len(airdrome_ids) - resolved
    )


def _core_table_report(record: dict[str, Any]) -> dict[str, Any]:
    required = record["required_modules"]
    options = record["options"]
    warehouses = record["warehouses"]
    return {
        "missions_observed": len(record["missions"]),
        "optional_core_parse_errors": dict(
            sorted(record["optional_core_errors"].items())
        ),
        "required_modules": {
            "missions_present": required["present"],
            "missions_missing": required["missing"],
            "missions_empty": required["empty"],
            "missions_nonempty": required["nonempty"],
            "entry_count_distribution": _count_distribution(
                required["entries"]
            ),
            "invalid_string_identity_map_shape": required["invalid_shape"],
        },
        "options": {
            "missions_present": options["present"],
            "missions_missing": options["missing"],
            "top_field_sets": _field_set_report(options["top_field_sets"]),
            "known_table_field_sets": [
                {
                    "field": field_name,
                    "variants": _field_set_report(counts),
                }
                for field_name, counts in sorted(
                    options["known_table_field_sets"].items()
                )
            ],
            "player_name_present": options["player_name_present"],
            "player_name_nonempty": options["player_name_nonempty"],
            "plugin_entry_count_distribution": _count_distribution(
                options["plugin_entry_counts"]
            ),
            "nonempty_audio_device_field_counts": dict(
                sorted(
                    options["nonempty_audio_device_fields"].items()
                )
            ),
            "private_values_returned": False,
        },
        "warehouses": {
            "missions_present": warehouses["present"],
            "missions_missing": warehouses["missing"],
            "top_field_sets": _field_set_report(
                warehouses["top_field_sets"]
            ),
            "airport_count_distribution": _count_distribution(
                warehouses["airport_counts"]
            ),
            "warehouse_object_count_distribution": _count_distribution(
                warehouses["warehouse_object_counts"]
            ),
            "airport_entry_field_sets": _field_set_report(
                warehouses["airport_entry_field_sets"]
            ),
            "airport_numeric_keys": warehouses["airport_numeric_keys"],
            "airport_nonnumeric_keys": warehouses[
                "airport_nonnumeric_keys"
            ],
            "route_airdrome_references": warehouses[
                "route_airdrome_references"
            ],
            "route_airdrome_references_resolved": warehouses[
                "route_airdrome_references_resolved"
            ],
            "route_airdrome_references_missing": warehouses[
                "route_airdrome_references_missing"
            ],
        },
    }


def _count_distribution(counts: Counter[int]) -> list[dict[str, int]]:
    return [
        {"value": value, "missions": missions}
        for value, missions in sorted(counts.items())
    ]


def _aggregate_environment(
    mission: LuaTable,
    content_hash: str,
    record: dict[str, Any],
) -> None:
    record["missions"].add(content_hash)
    record["mission_field_sets"][
        tuple(sorted(string_fields(mission)))
    ] += 1
    for field_name in ("version", "start_time"):
        _collect_scalar(
            record["metadata_scalars"],
            f"$.{field_name}",
            mission.get(field_name),
        )
    date = mission.get("date")
    if isinstance(date, LuaTable):
        for field_name in ("Year", "Month", "Day"):
            _collect_scalar(
                record["metadata_scalars"],
                f"$.date.{field_name}",
                date.get(field_name),
            )

    weather = mission.get("weather")
    if not isinstance(weather, LuaTable):
        record["weather_missing"] += 1
    else:
        record["weather_present"] += 1
        _collect_table_schema(
            weather,
            "$.weather",
            record["weather_table_field_sets"],
            record["weather_scalars"],
        )
    _aggregate_logic(mission, record["logic"])


def _aggregate_logic(
    mission: LuaTable,
    record: dict[str, Any],
) -> None:
    triggers = mission.get("triggers")
    zones = (
        triggers.get("zones")
        if isinstance(triggers, LuaTable)
        else None
    )
    for zone in numeric_tables(zones):
        record["zone_field_sets"][
            tuple(sorted(string_fields(zone)))
        ] += 1

    for rule in numeric_tables(mission.get("trigrules")):
        record["trigger_rule_field_sets"][
            tuple(sorted(string_fields(rule)))
        ] += 1
        for condition in numeric_tables(rule.get("rules")):
            record["condition_field_sets"][
                tuple(sorted(string_fields(condition)))
            ] += 1
            _collect_predicate_names(
                condition.get("predicate"),
                record["condition_predicates"],
            )
        for action in numeric_tables(rule.get("actions")):
            record["action_field_sets"][
                tuple(sorted(string_fields(action)))
            ] += 1
            _collect_predicate_names(
                action.get("predicate"),
                record["action_predicates"],
            )

    for goal in numeric_tables(mission.get("goals")):
        record["goal_field_sets"][
            tuple(sorted(string_fields(goal)))
        ] += 1
        _collect_predicate_names(
            goal.get("predicate"),
            record["goal_predicates"],
        )
        for condition in numeric_tables(goal.get("rules")):
            record["goal_condition_field_sets"][
                tuple(sorted(string_fields(condition)))
            ] += 1
            _collect_predicate_names(
                condition.get("predicate"),
                record["goal_predicates"],
            )


def _collect_predicate_names(
    value: Any,
    counts: Counter[str],
) -> None:
    if not isinstance(value, str):
        return
    for match in _DCS_PREDICATE.finditer(value):
        counts[match.group("name")] += 1


def _collect_table_schema(
    value: LuaTable,
    path: str,
    table_field_sets: dict[str, Counter[tuple[str, ...]]],
    scalars: dict[str, dict[str, Any]],
) -> None:
    table_field_sets[path][tuple(sorted(string_fields(value)))] += 1
    for field in value.fields:
        child_path = (
            f"{path}.{field.key}"
            if isinstance(field.key, str)
            else f"{path}[]"
        )
        if isinstance(field.value, LuaTable):
            _collect_table_schema(
                field.value,
                child_path,
                table_field_sets,
                scalars,
            )
        else:
            _collect_scalar(scalars, child_path, field.value)


def _collect_scalar(
    scalars: dict[str, dict[str, Any]],
    path: str,
    value: Any,
) -> None:
    record = scalars.setdefault(
        path,
        {
            "types": Counter(),
            "numbers": set(),
            "booleans": Counter(),
            "strings": set(),
        },
    )
    if isinstance(value, bool):
        record["types"]["boolean"] += 1
        record["booleans"][value] += 1
    elif _is_number(value):
        record["types"]["number"] += 1
        record["numbers"].add(value)
    elif isinstance(value, str):
        record["types"]["string"] += 1
        record["strings"].add(value)
    elif value is None:
        record["types"]["nil"] += 1
    else:
        record["types"][type(value).__name__] += 1


def _environment_report(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "missions_observed": len(record["missions"]),
        "mission_field_sets": _field_set_report(
            record["mission_field_sets"]
        ),
        "metadata_scalars": _scalar_reports(record["metadata_scalars"]),
        "weather": {
            "missions_present": record["weather_present"],
            "missions_missing": record["weather_missing"],
            "table_field_sets": [
                {
                    "path_ref": f"weather-table-{index}",
                    "path_depth": _path_depth(path),
                    "variants": _field_set_report(counts),
                }
                for index, (path, counts) in enumerate(
                    sorted(record["weather_table_field_sets"].items()),
                    start=1,
                )
            ],
            "scalars": _scalar_reports(
                record["weather_scalars"],
                prefix="weather-scalar",
            ),
        },
        "logic": _logic_report(record["logic"]),
    }


def _logic_report(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "zone_field_sets": _field_set_report(record["zone_field_sets"]),
        "trigger_rule_field_sets": _field_set_report(
            record["trigger_rule_field_sets"]
        ),
        "condition_field_sets": _field_set_report(
            record["condition_field_sets"]
        ),
        "action_field_sets": _field_set_report(record["action_field_sets"]),
        "goal_field_sets": _field_set_report(record["goal_field_sets"]),
        "goal_condition_field_sets": _field_set_report(
            record["goal_condition_field_sets"]
        ),
        "condition_predicate_functions": _anonymous_counter_report(
            record["condition_predicates"]
        ),
        "action_predicate_functions": _anonymous_counter_report(
            record["action_predicates"]
        ),
        "goal_predicate_functions": _anonymous_counter_report(
            record["goal_predicates"]
        ),
    }


def _scalar_reports(
    records: dict[str, dict[str, Any]],
    *,
    prefix: str = "scalar",
) -> list[dict[str, Any]]:
    return [
        _scalar_report(
            path,
            record,
            path_ref=f"{prefix}-{index}",
        )
        for index, (path, record) in enumerate(
            sorted(records.items()),
            start=1,
        )
    ]


def _scalar_report(
    path: str,
    record: dict[str, Any],
    *,
    path_ref: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path_ref": path_ref,
        "path_depth": _path_depth(path),
        "types": dict(sorted(record["types"].items())),
    }
    numbers = sorted(record["numbers"])
    if numbers:
        result["number_range"] = {
            "minimum": numbers[0],
            "maximum": numbers[-1],
            "distinct": len(numbers),
        }
        if len(numbers) <= 16:
            result["observed_numbers"] = numbers
    if record["booleans"]:
        result["observed_booleans"] = {
            str(value).lower(): count
            for value, count in sorted(record["booleans"].items())
        }
    strings = sorted(record["strings"])
    if strings:
        result["string_values"] = {
            "distinct": len(strings),
            "values_returned": False,
        }
    return result


def _path_depth(path: str) -> int:
    return path.count(".") + path.count("[]")


def _aggregate_group(
    theatre: str,
    content_hash: str,
    side_name: str,
    country_id: Any,
    category: str,
    group: LuaTable,
    points: list[LuaTable],
    units: list[LuaTable],
    unit_records: dict[str, dict[str, Any]],
    payload_records: dict[tuple[Any, ...], dict[str, Any]],
    airbase_records: dict[tuple[str, int | float], dict[str, Any]],
) -> None:
    point_actions = Counter(
        action
        for point in points
        if (
            isinstance((action := point.get("action")), str)
            and action.strip()
        )
    )
    task_ids: Counter[str] = Counter()
    for point in points:
        _collect_task_ids(point.get("task"), task_ids)
    first_point = points[0] if points else LuaTable(())
    start_mode = classify_start_mode(first_point) if points else "other"
    group_task = group.get("task")
    selected_types = {
        value
        for unit in units
        if isinstance((value := unit.get("type")), str)
    }

    for selected_type in selected_types:
        record = unit_records.setdefault(
            selected_type,
            _new_unit_record(selected_type),
        )
        record["groups_observed"] += 1
        record["missions"].add(content_hash)
        record["categories"][category] += 1
        record["sides"][side_name] += 1
        if _is_number(country_id):
            record["country_ids"][country_id] += 1
        if isinstance(group_task, str) and group_task.strip():
            record["group_tasks"][group_task] += 1
        record["waypoint_actions"].update(point_actions)
        record["waypoint_task_ids"].update(task_ids)
        record["start_modes"][start_mode] += 1

    for unit in units:
        selected_type = unit.get("type")
        if not isinstance(selected_type, str):
            continue
        record = unit_records.setdefault(
            selected_type,
            _new_unit_record(selected_type),
        )
        record["units_observed"] += 1
        record["missions"].add(content_hash)
        skill = unit.get("skill")
        if isinstance(skill, str) and skill.strip():
            record["skills"][skill] += 1
        record["unit_field_sets"][
            tuple(sorted(string_fields(unit)))
        ] += 1
        payload = table(unit.get("payload"))
        record["payload_field_sets"][
            tuple(sorted(string_fields(payload)))
        ] += 1
        assignments = _payload_assignments(payload)
        if assignments:
            signature = (
                selected_type,
                tuple(
                    (
                        assignment["station"],
                        assignment["station_evidence"],
                        assignment["CLSID"],
                    )
                    for assignment in assignments
                ),
            )
            payload_record = payload_records.setdefault(
                signature,
                {
                    "unit_type": selected_type,
                    "assignments": assignments,
                    "units_observed": 0,
                    "missions": set(),
                    "group_tasks": Counter(),
                    "parameter_variants": Counter(),
                },
            )
            payload_record["units_observed"] += 1
            payload_record["missions"].add(content_hash)
            if isinstance(group_task, str) and group_task.strip():
                payload_record["group_tasks"][group_task] += 1
            parameters = _payload_parameters(payload)
            if parameters:
                payload_record["parameter_variants"][parameters] += 1

    airdrome_id = first_point.get("airdromeId")
    if not _is_number(airdrome_id):
        return
    airbase = airbase_records.setdefault(
        (theatre, airdrome_id),
        {
            "theatre": theatre,
            "airdrome_id": airdrome_id,
            "missions": set(),
            "start_modes": Counter(),
            "unit_types": Counter(),
            "start_points": Counter(),
            "parkings": {},
        },
    )
    airbase["missions"].add(content_hash)
    airbase["start_modes"][start_mode] += 1
    point_variant = tuple(
        (name, first_point.get(name))
        for name in ("type", "action", "x", "y", "alt")
        if first_point.has(name)
    )
    airbase["start_points"][point_variant] += 1
    for unit in units:
        selected_type = unit.get("type")
        if isinstance(selected_type, str):
            airbase["unit_types"][selected_type] += 1
        parking = unit.get("parking")
        parking_id = unit.get("parking_id")
        if parking is None and parking_id is None:
            continue
        parking_key = (
            type(parking).__name__,
            parking,
            type(parking_id).__name__,
            parking_id,
        )
        parking_record = airbase["parkings"].setdefault(
            parking_key,
            {
                "parking": parking,
                "parking_id": parking_id,
                "observations": 0,
                "unit_types": Counter(),
                "coordinate_variants": Counter(),
            },
        )
        parking_record["observations"] += 1
        if isinstance(selected_type, str):
            parking_record["unit_types"][selected_type] += 1
        coordinate_variant = tuple(
            (name, unit.get(name))
            for name in ("x", "y", "alt", "heading")
            if unit.has(name)
        )
        if coordinate_variant:
            parking_record["coordinate_variants"][coordinate_variant] += 1


def _unit_report(
    records: dict[str, dict[str, Any]],
    unit_refs: dict[str, str],
    *,
    exact_filter: str | None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for unit_type, record in sorted(records.items()):
        result.append(
            {
                "unit_type_ref": unit_refs[unit_type],
                "identity_source": (
                    "caller_exact_filter"
                    if exact_filter is not None
                    else "anonymous_observation"
                ),
                "units_observed": record["units_observed"],
                "groups_observed": record["groups_observed"],
                "missions_observed": len(record["missions"]),
                "categories": dict(sorted(record["categories"].items())),
                "sides": _anonymous_counter_report(record["sides"]),
                "country_ids": [
                    {"id": key, "groups": value}
                    for key, value in sorted(
                        record["country_ids"].items(),
                        key=lambda item: (float(item[0]), item[1]),
                    )
                ],
                "skills": _anonymous_counter_report(record["skills"]),
                "group_tasks": _anonymous_counter_report(
                    record["group_tasks"]
                ),
                "waypoint_actions": _anonymous_counter_report(
                    record["waypoint_actions"]
                ),
                "waypoint_task_ids": _anonymous_counter_report(
                    record["waypoint_task_ids"]
                ),
                "start_modes": dict(sorted(record["start_modes"].items())),
                "unit_field_sets": _field_set_report(
                    record["unit_field_sets"]
                ),
                "payload_field_sets": _field_set_report(
                    record["payload_field_sets"]
                ),
            }
        )
    return result


def _payload_report(
    records: dict[tuple[Any, ...], dict[str, Any]],
    unit_refs: dict[str, str],
    store_refs: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for _signature, record in sorted(
        records.items(),
        key=lambda item: repr(item[0]),
    ):
        result.append(
            {
                "unit_type_ref": unit_refs[record["unit_type"]],
                "assignments": [
                    {
                        "station": assignment["station"],
                        "station_evidence": assignment[
                            "station_evidence"
                        ],
                        "store_ref": store_refs[assignment["CLSID"]],
                        "store_identity_source": "anonymous_observation",
                    }
                    for assignment in record["assignments"]
                ],
                "units_observed": record["units_observed"],
                "missions_observed": len(record["missions"]),
                "group_tasks": _anonymous_counter_report(
                    record["group_tasks"]
                ),
                "parameter_variants": {
                    "distinct": len(record["parameter_variants"]),
                    "observations": sum(
                        record["parameter_variants"].values()
                    ),
                    "values_returned": False,
                },
            }
        )
    return result


def _airbase_report(
    records: dict[tuple[str, int | float], dict[str, Any]],
    theatre_refs: dict[str, str],
    unit_refs: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for (_theatre, _airdrome_id), record in sorted(
        records.items(),
        key=lambda item: (item[0][0], float(item[0][1])),
    ):
        parkings = []
        for parking in sorted(
            record["parkings"].values(),
            key=lambda item: (
                repr(item["parking"]),
                repr(item["parking_id"]),
            ),
        ):
            parkings.append(
                {
                    "parking": _public_scalar(parking["parking"]),
                    "parking_id": _public_scalar(parking["parking_id"]),
                    "observations": parking["observations"],
                    "unit_types": _referenced_counter_report(
                        parking["unit_types"],
                        unit_refs,
                    ),
                    "coordinate_variants": [
                        {
                            **{
                                key: _public_scalar(value)
                                for key, value in variant
                            },
                            "observations": count,
                        }
                        for variant, count in sorted(
                            parking["coordinate_variants"].items(),
                            key=lambda item: repr(item[0]),
                        )
                    ],
                }
            )
        result.append(
            {
                "theatre_ref": theatre_refs[record["theatre"]],
                "airdrome_id": record["airdrome_id"],
                "missions_observed": len(record["missions"]),
                "start_modes": dict(sorted(record["start_modes"].items())),
                "unit_types": _referenced_counter_report(
                    record["unit_types"],
                    unit_refs,
                ),
                "start_point_variants": [
                    {
                        **{
                            key: _public_scalar(value)
                            for key, value in variant
                        },
                        "observations": count,
                    }
                    for variant, count in sorted(
                        record["start_points"].items(),
                        key=lambda item: repr(item[0]),
                    )
                ],
                "parkings": parkings,
            }
        )
    return result


def _structure_report(
    structures: dict[str, Counter[tuple[str, ...]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        category: _field_set_report(counts)
        for category, counts in sorted(structures.items())
        if counts
    }


def _field_set_report(
    counts: Counter[tuple[str, ...]],
) -> list[dict[str, Any]]:
    by_size: dict[int, dict[str, int]] = {}
    for fields, observations in counts.items():
        item = by_size.setdefault(
            len(fields),
            {"field_count": len(fields), "variants": 0, "observations": 0},
        )
        item["variants"] += 1
        item["observations"] += observations
    return [
        by_size[field_count]
        for field_count in sorted(by_size)
    ]


def _new_unit_record(unit_type: str) -> dict[str, Any]:
    return {
        "unit_type": unit_type,
        "units_observed": 0,
        "groups_observed": 0,
        "missions": set(),
        "categories": Counter(),
        "sides": Counter(),
        "country_ids": Counter(),
        "skills": Counter(),
        "group_tasks": Counter(),
        "waypoint_actions": Counter(),
        "waypoint_task_ids": Counter(),
        "start_modes": Counter(),
        "unit_field_sets": Counter(),
        "payload_field_sets": Counter(),
    }


def _payload_assignments(payload: LuaTable) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    pylons = table(payload.get("pylons"))
    for field in pylons.numeric_items():
        pylon = table(field.value)
        clsid = pylon.get("CLSID")
        if not isinstance(clsid, str):
            continue
        station = pylon.get("num")
        station_evidence = "num_field"
        if not _is_number(station):
            station = field.key
            station_evidence = "table_key"
        assignments.append(
            {
                "station": station,
                "station_evidence": station_evidence,
                "CLSID": clsid,
            }
        )
    assignments.sort(
        key=lambda item: (
            float(item["station"]),
            item["station_evidence"],
            item["CLSID"],
        )
    )
    return assignments


def _payload_parameters(payload: LuaTable) -> tuple[tuple[str, Any], ...]:
    allowed = {"fuel", "flare", "chaff", "gun", "ammo_type"}
    return tuple(
        sorted(
            (
                field.key,
                field.value,
            )
            for field in payload.fields
            if (
                isinstance(field.key, str)
                and field.key in allowed
                and isinstance(field.value, str | int | float | bool)
            )
        )
    )


def _collect_task_ids(value: Any, counts: Counter[str]) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        if (
            field.key == "id"
            and isinstance(field.value, str)
            and field.value.strip()
        ):
            counts[field.value] += 1
        if isinstance(field.value, LuaTable):
            _collect_task_ids(field.value, counts)


def _identity_refs(
    values: Any,
    *,
    prefix: str,
    exact_filter: str | None = None,
) -> dict[str, str]:
    identities = sorted(str(value) for value in values)
    if exact_filter is not None:
        return {value: exact_filter for value in identities}
    return {
        value: f"{prefix}-{index}"
        for index, value in enumerate(identities, start=1)
    }


def _anonymous_counter_report(counts: Counter[str]) -> dict[str, Any]:
    frequencies = Counter(counts.values())
    return {
        "distinct": len(counts),
        "occurrences": sum(counts.values()),
        "frequency_distribution": [
            {
                "occurrences_per_identity": occurrence_count,
                "identities": identity_count,
            }
            for occurrence_count, identity_count in sorted(
                frequencies.items()
            )
        ],
        "identities_returned": False,
    }


def _referenced_counter_report(
    counts: Counter[str],
    references: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        {
            "unit_type_ref": references[value],
            "observations": count,
        }
        for value, count in sorted(counts.items())
    ]


def _public_scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool) or _is_number(value):
        return value
    return {
        "type": "string" if isinstance(value, str) else type(value).__name__,
        "value_returned": False,
    }


def _snapshot_root(root: ObservedRoot) -> _RootSnapshot:
    path = Path(os.path.abspath(os.fspath(root.path)))
    try:
        first = _capture_absolute_chain(path)
    except _PathLinkError as error:
        raise ValueError(
            "observed root paths must not contain symbolic links, junctions, "
            "or reparse points"
        ) from error
    except FileNotFoundError as error:
        raise ValueError(
            f"observed root {root.label!r} does not exist"
        ) from error
    except OSError as error:
        raise ValueError(
            f"observed root {root.label!r} cannot be inspected"
        ) from error
    final = first[-1]
    is_file = final.file_type == stat.S_IFREG
    if not is_file and final.file_type != stat.S_IFDIR:
        raise ValueError(
            f"observed root {root.label!r} must be a regular file or directory"
        )
    if is_file and path.suffix.casefold() != ".miz":
        raise ValueError(
            f"observed root {root.label!r} file must use .miz extension"
        )
    try:
        resolved = path.resolve(strict=True)
        resolved_components = _capture_absolute_chain(resolved)
        second = _capture_absolute_chain(path)
    except _PathLinkError as error:
        raise ValueError(
            "observed root paths must not contain symbolic links, junctions, "
            "or reparse points"
        ) from error
    except OSError as error:
        raise ValueError(
            "observed root changed while it was being inspected"
        ) from error
    if (
        not _same_component_chain(first, second)
        or not _same_component_chain(first, resolved_components)
    ):
        raise ValueError("observed root changed while it was being inspected")
    return _RootSnapshot(path, resolved, is_file, first)


def _capture_absolute_chain(path: Path) -> tuple[_PathComponentSnapshot, ...]:
    if not path.is_absolute():
        raise OSError("absolute path required")
    parts = path.parts
    if not parts:
        raise OSError("empty path")
    current = Path(parts[0])
    result = [_snapshot_path_component(current)]
    for part in parts[1:]:
        current /= part
        result.append(_snapshot_path_component(current))
    return tuple(result)


def _capture_relative_chain(
    path: Path,
    root: Path,
) -> tuple[_PathComponentSnapshot, ...]:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise _DiscoveredFileChangedError from error
    current = root
    result: list[_PathComponentSnapshot] = []
    for part in relative.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise _DiscoveredFileChangedError
        current /= part
        try:
            result.append(_snapshot_path_component(current))
        except _PathLinkError as error:
            raise _DiscoveredFileChangedError from error
        except OSError as error:
            raise _DiscoveredFileChangedError from error
    return tuple(result)


def _snapshot_path_component(path: Path) -> _PathComponentSnapshot:
    value = path.lstat()
    if _stat_is_link_or_reparse(value):
        raise _PathLinkError
    return _PathComponentSnapshot(
        path,
        _file_identity(value),
        stat.S_IFMT(value.st_mode),
    )


def _same_component_chain(
    left: tuple[_PathComponentSnapshot, ...],
    right: tuple[_PathComponentSnapshot, ...],
) -> bool:
    return [
        (item.identity, item.file_type)
        for item in left
    ] == [
        (item.identity, item.file_type)
        for item in right
    ]


def _stat_is_link_or_reparse(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(value, "st_file_attributes", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and file_attributes & reparse_flag
    )


def _is_link(path: Path) -> bool:
    try:
        return _stat_is_link_or_reparse(path.lstat())
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _discover_miz(
    root: _RootSnapshot,
    errors: Counter[str],
) -> list[_DiscoveredFile]:
    try:
        _verify_root_snapshot(root)
    except _DiscoveredFileChangedError:
        errors["discovery_root_changed"] += 1
        return []
    if root.is_file:
        try:
            return [_snapshot_discovered_file(root.resolved, root)]
        except _DiscoveredFileChangedError:
            errors["discovery_file_changed_skipped"] += 1
            return []
    paths: list[_DiscoveredFile] = []

    def on_error(_error: OSError) -> None:
        errors["discovery_error"] += 1

    for directory, names, filenames in os.walk(
        root.resolved,
        topdown=True,
        onerror=on_error,
        followlinks=False,
    ):
        directory_path = Path(directory)
        try:
            _verify_root_snapshot(root)
            _capture_relative_chain(directory_path, root.resolved)
            resolved_directory = directory_path.resolve(strict=True)
        except _DiscoveredFileChangedError:
            errors["discovery_root_changed"] += 1
            return []
        except OSError:
            errors["discovery_resolution_error"] += 1
            names[:] = []
            continue
        if not _is_within(resolved_directory, root.resolved):
            errors["discovery_outside_root_skipped"] += 1
            names[:] = []
            continue
        names.sort(key=str.casefold)
        retained_names: list[str] = []
        for name in names:
            child = directory_path / name
            if _is_link(child):
                errors["discovery_directory_link_skipped"] += 1
                continue
            try:
                resolved_child = child.resolve(strict=True)
            except OSError:
                errors["discovery_resolution_error"] += 1
                continue
            if not _is_within(resolved_child, root.resolved):
                errors["discovery_outside_root_skipped"] += 1
                continue
            retained_names.append(name)
        names[:] = retained_names
        for filename in sorted(filenames, key=str.casefold):
            candidate = directory_path / filename
            if candidate.suffix.casefold() != ".miz":
                continue
            if _is_link(candidate):
                errors["discovery_file_link_skipped"] += 1
                continue
            try:
                resolved_candidate = candidate.resolve(strict=True)
            except OSError:
                errors["discovery_resolution_error"] += 1
                continue
            if not _is_within(resolved_candidate, root.resolved):
                errors["discovery_outside_root_skipped"] += 1
                continue
            if not resolved_candidate.is_file():
                errors["discovery_nonfile_skipped"] += 1
                continue
            try:
                paths.append(
                    _snapshot_discovered_file(resolved_candidate, root)
                )
            except _DiscoveredFileChangedError:
                errors["discovery_file_changed_skipped"] += 1
    return paths


def _snapshot_discovered_file(
    path: Path,
    root: _RootSnapshot,
) -> _DiscoveredFile:
    _verify_root_snapshot(root)
    path = Path(os.path.abspath(os.fspath(path)))
    if not _is_within(path, root.resolved):
        raise _DiscoveredFileChangedError
    first = _capture_relative_chain(path, root.resolved)
    before = path.lstat()
    if _stat_is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise _DiscoveredFileChangedError
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise _DiscoveredFileChangedError from error
    if not _is_within(resolved, root.resolved):
        raise _DiscoveredFileChangedError
    resolved_chain = _capture_relative_chain(resolved, root.resolved)
    second = _capture_relative_chain(path, root.resolved)
    _verify_root_snapshot(root)
    if (
        not _same_component_chain(first, second)
        or not _same_component_chain(first, resolved_chain)
        or (
            first
            and first[-1].identity != _file_identity(before)
        )
        or (
            not first
            and root.components[-1].identity != _file_identity(before)
        )
    ):
        raise _DiscoveredFileChangedError
    return _DiscoveredFile(
        path,
        first,
        _file_identity(before),
        before.st_size,
        _modified_ns(before),
    )


def _verify_root_snapshot(root: _RootSnapshot) -> None:
    try:
        current = _capture_absolute_chain(root.path)
        resolved = root.path.resolve(strict=True)
        resolved_components = _capture_absolute_chain(resolved)
    except (_PathLinkError, OSError) as error:
        raise _DiscoveredFileChangedError from error
    if (
        not _same_component_chain(root.components, current)
        or not _same_component_chain(root.components, resolved_components)
        or (
            root.is_file
            and current[-1].file_type != stat.S_IFREG
        )
        or (
            not root.is_file
            and current[-1].file_type != stat.S_IFDIR
        )
    ):
        raise _DiscoveredFileChangedError


def _verify_discovered_file(
    discovered: _DiscoveredFile,
    root: _RootSnapshot,
) -> None:
    _verify_root_snapshot(root)
    current = _capture_relative_chain(discovered.path, root.resolved)
    try:
        resolved = discovered.path.resolve(strict=True)
    except OSError as error:
        raise _DiscoveredFileChangedError from error
    if not _is_within(resolved, root.resolved):
        raise _DiscoveredFileChangedError
    resolved_chain = _capture_relative_chain(resolved, root.resolved)
    if (
        not _same_component_chain(discovered.components, current)
        or not _same_component_chain(discovered.components, resolved_chain)
    ):
        raise _DiscoveredFileChangedError
    try:
        value = discovered.path.lstat()
    except OSError as error:
        raise _DiscoveredFileChangedError from error
    if (
        _stat_is_link_or_reparse(value)
        or not stat.S_ISREG(value.st_mode)
        or _file_identity(value) != discovered.identity
        or value.st_size != discovered.size
        or _modified_ns(value) != discovered.modified_ns
    ):
        raise _DiscoveredFileChangedError
    _verify_root_snapshot(root)


def _read_discovered_file(
    discovered: _DiscoveredFile,
    root: _RootSnapshot,
    cache: dict[str, _ContentOutcome],
) -> _ReadOutcome:
    _verify_discovered_file(discovered, root)
    policy = ArchivePolicy()
    if discovered.size > policy.max_total_uncompressed:
        return _ReadOutcome(
            None,
            _ContentOutcome(
                False,
                None,
                "archive_policy_input_size_limit",
            ),
            False,
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(discovered.path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or _file_identity(opened) != discovered.identity
            or opened.st_size != discovered.size
            or _modified_ns(opened) != discovered.modified_ns
        ):
            raise _DiscoveredFileChangedError
        if opened.st_size > policy.max_total_uncompressed:
            raise _DiscoveredFileChangedError
        archive = inspect_miz(
            stream,
            policy=policy,
            verify_crc=False,
        )
        if not archive.valid_zip or not archive.safe:
            result = _ReadOutcome(
                None,
                _ContentOutcome(
                    False,
                    None,
                    _archive_failure_code(archive),
                ),
                False,
            )
        else:
            with tempfile.TemporaryFile(mode="w+b") as snapshot:
                content_hash = _snapshot_and_hash_bound_stream(
                    stream,
                    snapshot,
                    opened.st_size,
                )
                snapshot_archive = inspect_miz(
                    snapshot,
                    policy=policy,
                    verify_crc=True,
                )
                outcome = cache.get(content_hash)
                cache_hit = outcome is not None
                if outcome is None:
                    outcome = _parse_content(snapshot, snapshot_archive)
                    cache[content_hash] = outcome
                result = _ReadOutcome(content_hash, outcome, cache_hit)
        after_read = os.fstat(stream.fileno())
    if (
        _file_identity(after_read) != discovered.identity
        or after_read.st_size != discovered.size
        or _modified_ns(after_read) != discovered.modified_ns
    ):
        raise _DiscoveredFileChangedError
    _verify_discovered_file(discovered, root)
    return result


def _snapshot_and_hash_bound_stream(
    source: BinaryIO,
    snapshot: BinaryIO,
    expected_size: int,
) -> str:
    source.seek(0)
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        requested = min(_READ_CHUNK_BYTES, remaining)
        chunk = source.read(requested)
        if not chunk or len(chunk) > requested:
            raise _DiscoveredFileChangedError
        snapshot.write(chunk)
        digest.update(chunk)
        remaining -= len(chunk)
    if source.read(1):
        raise _DiscoveredFileChangedError
    snapshot.flush()
    snapshot.seek(0)
    return digest.hexdigest()


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _modified_ns(value: os.stat_result) -> int:
    return getattr(value, "st_mtime_ns", int(value.st_mtime * 1_000_000_000))


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
