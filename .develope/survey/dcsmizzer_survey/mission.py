from __future__ import annotations

import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .archive import CORE_MEMBERS
from .lua import (
    LuaDataError,
    LuaLimits,
    LuaTable,
    parse_lua_bytes,
)


_CORE_GLOBALS: dict[str, str] = {
    "mission": "mission",
    "options": "options",
    "warehouses": "warehouses",
    "l10n/DEFAULT/dictionary": "dictionary",
    "l10n/DEFAULT/mapResource": "mapResource",
}
_CATEGORIES = ("plane", "helicopter", "vehicle", "ship", "static")
_BRIEFING_FIELDS = (
    "sortie",
    "descriptionText",
    "descriptionBlueTask",
    "descriptionRedTask",
    "descriptionNeutralsTask",
)
_MODERN_FIELDS = {
    "dynSpawnTemplate",
    "DTC",
    "dataCartridge",
    "datalinks",
    "coldAtStart",
}
_SCRIPT_ACTION = re.compile(
    r"\ba_do_script(?:_file)?(?:\s*\(|\s*$)"
)


@dataclass(frozen=True)
class LuaMemberObservation:
    name: str
    present: bool
    parsed: bool
    encoding: str | None = None
    error_code: str | None = None


@dataclass
class MissionStats:
    groups: dict[str, int] = field(default_factory=dict)
    units: dict[str, int] = field(default_factory=dict)
    waypoints: dict[str, int] = field(default_factory=dict)
    human_slots: dict[str, int] = field(default_factory=dict)
    pylon_assignments: int = 0
    pylons_with_clsid: int = 0
    payload_clsids: set[str] = field(default_factory=set)
    trigger_rules: int = 0
    trigger_conditions: int = 0
    trigger_actions: int = 0
    script_actions: int = 0
    goals: int = 0
    dictionary_entries: int = 0
    resource_mappings: int = 0
    briefing_characters: int = 0
    resource_extensions: dict[str, int] = field(default_factory=dict)
    missing_resource_members: int = 0
    referenced_missing_resources: int = 0
    unreferenced_missing_resources: int = 0
    warehouse_airports: int = 0
    warehouse_objects: int = 0
    late_activation_groups: int = 0
    uncontrolled_groups: int = 0
    uncontrollable_groups: int = 0
    modern_fields: dict[str, int] = field(default_factory=dict)
    waypoint_actions: dict[str, int] = field(default_factory=dict)
    waypoint_task_ids: dict[str, int] = field(default_factory=dict)
    top_level_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MizObservation:
    parse_valid: bool
    members: tuple[LuaMemberObservation, ...]
    mission_version: int | float | None
    theatre: str | None
    stats: MissionStats


def analyse_miz(
    path: Path,
    *,
    limits: LuaLimits | None = None,
) -> MizObservation:
    selected_limits = limits or LuaLimits()
    member_observations: list[LuaMemberObservation] = []
    values: dict[str, LuaTable] = {}

    try:
        with zipfile.ZipFile(path) as archive:
            infos_by_name: dict[str, list[zipfile.ZipInfo]] = {}
            for info in archive.infolist():
                infos_by_name.setdefault(info.filename, []).append(info)
            archive_names = set(infos_by_name)

            for name in CORE_MEMBERS:
                infos = infos_by_name.get(name)
                if not infos:
                    member_observations.append(
                        LuaMemberObservation(
                            name=name,
                            present=False,
                            parsed=False,
                            error_code="missing",
                        )
                    )
                    continue
                info = infos[-1]
                if info.file_size > selected_limits.max_input_bytes:
                    member_observations.append(
                        LuaMemberObservation(
                            name=name,
                            present=True,
                            parsed=False,
                            error_code="input_limit",
                        )
                    )
                    continue
                try:
                    with archive.open(info) as stream:
                        parsed = parse_lua_bytes(
                            stream.read(),
                            limits=selected_limits,
                        )
                    expected_global = _CORE_GLOBALS[name]
                    value = parsed.document.get(expected_global)
                    if value is None and isinstance(parsed.document.returned, LuaTable):
                        value = parsed.document.returned
                    if not isinstance(value, LuaTable):
                        member_observations.append(
                            LuaMemberObservation(
                                name=name,
                                present=True,
                                parsed=False,
                                encoding=parsed.encoding,
                                error_code="missing_global_table",
                            )
                        )
                        continue
                    values[name] = value
                    member_observations.append(
                        LuaMemberObservation(
                            name=name,
                            present=True,
                            parsed=True,
                            encoding=parsed.encoding,
                        )
                    )
                except LuaDataError as error:
                    member_observations.append(
                        LuaMemberObservation(
                            name=name,
                            present=True,
                            parsed=False,
                            error_code=type(error).__name__,
                        )
                    )
    except (OSError, zipfile.BadZipFile):
        return MizObservation(
            parse_valid=False,
            members=tuple(
                LuaMemberObservation(
                    name=name,
                    present=False,
                    parsed=False,
                    error_code="bad_zip",
                )
                for name in CORE_MEMBERS
            ),
            mission_version=None,
            theatre=None,
            stats=MissionStats(),
        )

    mission = values.get("mission")
    warehouses = values.get("warehouses")
    dictionary = values.get("l10n/DEFAULT/dictionary")
    map_resource = values.get("l10n/DEFAULT/mapResource")
    stats = _mission_stats(
        mission,
        warehouses,
        dictionary,
        map_resource,
        archive_names,
    )
    version = mission.get("version") if mission is not None else None
    if not isinstance(version, (int, float)) or isinstance(version, bool):
        version = None
    theatre = mission.get("theatre") if mission is not None else None
    if not isinstance(theatre, str):
        theatre = None
    parsed_by_name = {item.name: item.parsed for item in member_observations}
    return MizObservation(
        parse_valid=bool(
            parsed_by_name.get("mission")
            and parsed_by_name.get("warehouses")
        ),
        members=tuple(member_observations),
        mission_version=version,
        theatre=theatre,
        stats=stats,
    )


def _mission_stats(
    mission: LuaTable | None,
    warehouses: LuaTable | None,
    dictionary: LuaTable | None,
    map_resource: LuaTable | None,
    archive_names: set[str],
) -> MissionStats:
    stats = MissionStats()
    if mission is None:
        return stats

    stats.top_level_fields = tuple(
        field.key for field in mission.fields if isinstance(field.key, str)
    )
    group_counts: Counter[str] = Counter()
    unit_counts: Counter[str] = Counter()
    waypoint_counts: Counter[str] = Counter()
    human_slots: Counter[str] = Counter()
    waypoint_actions: Counter[str] = Counter()
    waypoint_task_ids: Counter[str] = Counter()

    coalition = _table(mission.get("coalition"))
    for side in _table_values(coalition):
        for country in _numeric_values(_table(side).get("country")):
            country_table = _table(country)
            for category in _CATEGORIES:
                category_table = _table(country_table.get(category))
                groups = _numeric_values(category_table.get("group"))
                for group_value in groups:
                    group = _table(group_value)
                    group_counts[category] += 1
                    if group.get("lateActivation") is True:
                        stats.late_activation_groups += 1
                    if group.get("uncontrolled") is True:
                        stats.uncontrolled_groups += 1
                    if group.get("uncontrollable") is True:
                        stats.uncontrollable_groups += 1

                    units = _numeric_values(group.get("units"))
                    unit_counts[category] += len(units)
                    for unit_value in units:
                        unit = _table(unit_value)
                        skill = unit.get("skill")
                        if skill in {"Player", "Client"}:
                            human_slots[skill] += 1
                        pylons = _numeric_values(
                            _table(unit.get("payload")).get("pylons")
                        )
                        stats.pylon_assignments += len(pylons)
                        for pylon_value in pylons:
                            pylon = _table(pylon_value)
                            clsid = pylon.get("CLSID")
                            if isinstance(clsid, str):
                                stats.pylons_with_clsid += 1
                                stats.payload_clsids.add(clsid)

                    points = _numeric_values(
                        _table(group.get("route")).get("points")
                    )
                    waypoint_counts[category] += len(points)
                    for point_value in points:
                        point = _table(point_value)
                        action = point.get("action")
                        if isinstance(action, str):
                            waypoint_actions[action] += 1
                        _collect_task_ids(
                            point.get("task"),
                            waypoint_task_ids,
                        )

    stats.groups = dict(group_counts)
    stats.units = dict(unit_counts)
    stats.waypoints = dict(waypoint_counts)
    stats.human_slots = dict(human_slots)
    stats.waypoint_actions = dict(waypoint_actions)
    stats.waypoint_task_ids = dict(waypoint_task_ids)

    rules = _numeric_values(mission.get("trigrules"))
    stats.trigger_rules = len(rules)
    for rule_value in rules:
        rule = _table(rule_value)
        stats.trigger_conditions += len(_numeric_values(rule.get("rules")))
        actions = _numeric_values(rule.get("actions"))
        stats.trigger_actions += len(actions)
        for action_value in actions:
            predicate = _table(action_value).get("predicate")
            if isinstance(predicate, str) and _SCRIPT_ACTION.search(predicate):
                stats.script_actions += 1
    stats.goals = len(_numeric_values(mission.get("goals")))

    if dictionary is not None:
        stats.dictionary_entries = len(dictionary.fields)
        briefing_keys = {
            value
            for name in _BRIEFING_FIELDS
            if isinstance((value := mission.get(name)), str)
        }
        stats.briefing_characters = sum(
            len(value)
            for key in briefing_keys
            if isinstance((value := dictionary.get(key)), str)
        )

    if map_resource is not None:
        stats.resource_mappings = len(map_resource.fields)
        extensions: Counter[str] = Counter()
        resource_keys = {
            field.key
            for field in map_resource.fields
            if isinstance(field.key, str)
        }
        referenced_keys: set[str] = set()
        _collect_matching_strings(mission, resource_keys, referenced_keys)
        for field in map_resource.fields:
            if not isinstance(field.value, str):
                continue
            normalized = field.value.replace("\\", "/")
            suffix = PurePosixPath(normalized).suffix.lower()
            if suffix:
                extensions[suffix] += 1
            candidates = {
                normalized,
                f"l10n/DEFAULT/{normalized}",
            }
            if not candidates.intersection(archive_names):
                stats.missing_resource_members += 1
                if field.key in referenced_keys:
                    stats.referenced_missing_resources += 1
                else:
                    stats.unreferenced_missing_resources += 1
        stats.resource_extensions = dict(extensions)

    if warehouses is not None:
        stats.warehouse_airports = len(
            _table(warehouses.get("airports")).fields
        )
        stats.warehouse_objects = len(
            _table(warehouses.get("warehouses")).fields
        )

    modern_counts: Counter[str] = Counter()
    _count_named_fields(mission, _MODERN_FIELDS, modern_counts)
    stats.modern_fields = dict(modern_counts)
    return stats


def _collect_task_ids(value: Any, counts: Counter[str]) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        if field.key == "id" and isinstance(field.value, str):
            counts[field.value] += 1
        if isinstance(field.value, LuaTable):
            _collect_task_ids(field.value, counts)


def _count_named_fields(
    value: Any,
    names: set[str],
    counts: Counter[str],
) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        if isinstance(field.key, str) and field.key in names:
            counts[field.key] += 1
        if isinstance(field.value, LuaTable):
            _count_named_fields(field.value, names, counts)


def _collect_matching_strings(
    value: Any,
    candidates: set[str],
    matches: set[str],
) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        if isinstance(field.value, str) and field.value in candidates:
            matches.add(field.value)
        elif isinstance(field.value, LuaTable):
            _collect_matching_strings(field.value, candidates, matches)


def _table(value: Any) -> LuaTable:
    return value if isinstance(value, LuaTable) else LuaTable(())


def _numeric_values(value: Any) -> list[Any]:
    return [field.value for field in _table(value).numeric_items()]


def _table_values(value: Any) -> list[LuaTable]:
    return [
        field.value
        for field in _table(value).fields
        if isinstance(field.value, LuaTable)
    ]
