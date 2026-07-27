"""Conservative structural checks for caller-authored mission tables."""

from __future__ import annotations

import math
from typing import Any

from .facts import (
    BRIEFING_FIELDS,
    CATEGORIES,
    classify_start_mode,
    has_invalid_start_mode_pair,
)
from .gci import (
    GCI_ACTION_ID,
    GCI_COMPATIBLE_RADARS,
    GCI_RADAR_LINK_RADIUS_METERS,
    GCI_STATION_TYPE,
)
from .lua import LuaTable


_TRIGGER_PREDICATES = frozenset(
    {
        "triggerOnce",
        "triggerContinious",
        "triggerStart",
        "triggerFront",
    }
)
_GOAL_SIDES = frozenset({"RED", "BLUE", "OFFLINE"})
_MISPLACED_LOGIC_FIELDS = ("trigrules", "trig", "goals", "result")
_AIR_MAIN_TASKS = frozenset(
    {
        "Nothing",
        "AFAC",
        "AWACS",
        "Antiship Strike",
        "CAS",
        "CAP",
        "Escort",
        "Fighter Sweep",
        "Ground Attack",
        "Intercept",
        "Pinpoint Strike",
        "Reconnaissance",
        "Refueling",
        "Runway Attack",
        "SEAD",
        "Transport",
    }
)
_COMPLETE_COMBAT_TASKS: dict[str, frozenset[str]] = {
    "CAP": frozenset({"AttackGroup", "EngageTargets", "EngageTargetsInZone"}),
    "Fighter Sweep": frozenset({"AttackGroup", "EngageTargets", "EngageTargetsInZone"}),
    "Intercept": frozenset({"AttackGroup", "EngageTargets", "EngageTargetsInZone"}),
    "Escort": frozenset({"Escort"}),
    "Ground Attack": frozenset({"AttackGroup", "AttackMapObject", "Bombing"}),
    "CAS": frozenset({"AttackGroup", "EngageTargets", "EngageTargetsInZone"}),
    "Pinpoint Strike": frozenset({"AttackGroup", "AttackMapObject", "Bombing"}),
    "Runway Attack": frozenset({"Bombing", "BombingRunway"}),
    "SEAD": frozenset({"AttackGroup", "EngageTargets", "EngageTargetsInZone"}),
    "Antiship Strike": frozenset(
        {"AttackGroup", "EngageTargets", "EngageTargetsInZone"}
    ),
}
_SEMANTIC_WAYPOINT_TASKS = frozenset(
    {
        "AttackGroup",
        "AttackMapObject",
        "Bombing",
        "BombingRunway",
        "EngageTargets",
        "EngageTargetsInZone",
        "Escort",
    }
)
_TASK_EXPEND_VALUES = frozenset(
    {"All", "Auto", "Four", "Half", "One", "Quarter", "Two"}
)
_COMPLETE_RUNTIME_TABLES = (
    "coalitions",
    "failures",
    "forcedOptions",
    "groundControl",
    "map",
    "pictureFileNameB",
    "pictureFileNameR",
)
_GROUND_CONTROL_ROLES = (
    "artillery_commander",
    "forward_observer",
    "instructor",
    "observer",
)
_MAX_COMPLETE_BOMBING_ACTIVATION_DISTANCE_M = 200_000
_MAX_COMPLETE_AIR_START_HEADING_ERROR_RAD = math.radians(5)


def validate_mission_structure(
    mission: LuaTable,
    *,
    dictionary: LuaTable | None = None,
    profile: str = "technical_fixture",
) -> dict[str, Any]:
    """Return limited static consistency diagnostics without running DCS."""

    if profile not in {"technical_fixture", "complete_scenario"}:
        raise ValueError("unknown mission structure profile")
    diagnostics: list[dict[str, str]] = []
    group_ids: set[int | float] = set()
    unit_ids: set[int | float] = set()
    country_ids: set[int | float] = set()
    group_names: set[str] = set()
    unit_names: set[str] = set()
    late_group_paths: dict[int | float, str] = {}
    occupied_parking: set[tuple[str, int | float, str | int | float]] = set()

    _check_mission_sequences(mission, diagnostics)
    coalition_value = mission.get("coalition")
    if not isinstance(coalition_value, LuaTable):
        _add(diagnostics, "missing_coalition_table", "error", "$.coalition")
    else:
        for side_field in coalition_value.fields:
            if not isinstance(side_field.value, LuaTable):
                continue
            country_table = side_field.value.get("country")
            if not isinstance(country_table, LuaTable):
                continue
            _check_sequence(
                country_table,
                f"$.coalition.{side_field.key}.country",
                diagnostics,
                table_items=True,
            )
            for country_field in country_table.numeric_items():
                country_path = (
                    f"$.coalition.{side_field.key}.country[{country_field.key}]"
                )
                country = _required_table(
                    country_field.value,
                    diagnostics,
                    "invalid_country_table",
                    country_path,
                )
                if country is None:
                    continue
                country_id = country.get("id")
                if not _is_number(country_id):
                    _add(
                        diagnostics,
                        "missing_country_id",
                        "error",
                        f"{country_path}.id",
                    )
                elif country_id in country_ids:
                    _add(
                        diagnostics,
                        "duplicate_country_id",
                        "error",
                        f"{country_path}.id",
                    )
                else:
                    country_ids.add(country_id)
                for category in CATEGORIES:
                    category_value = country.get(category)
                    if not isinstance(category_value, LuaTable):
                        continue
                    groups_value = category_value.get("group")
                    if not isinstance(groups_value, LuaTable):
                        continue
                    _check_sequence(
                        groups_value,
                        f"{country_path}.{category}.group",
                        diagnostics,
                        table_items=True,
                    )
                    for group_field in groups_value.numeric_items():
                        group_path = (
                            f"{country_path}.{category}.group[{group_field.key}]"
                        )
                        group = _required_table(
                            group_field.value,
                            diagnostics,
                            "invalid_group_table",
                            group_path,
                        )
                        if group is None:
                            continue
                        _check_identity(
                            group,
                            id_field="groupId",
                            name_field="name",
                            ids=group_ids,
                            names=group_names,
                            kind="group",
                            path=group_path,
                            diagnostics=diagnostics,
                        )
                        _check_group_task(
                            group,
                            category=category,
                            path=group_path,
                            diagnostics=diagnostics,
                        )
                        _check_sequence(
                            group.get("tasks"),
                            f"{group_path}.tasks",
                            diagnostics,
                            table_items=True,
                        )
                        if group.get("lateActivation") is True and _is_number(
                            group.get("groupId")
                        ):
                            late_group_paths[group.get("groupId")] = group_path
                        points = _check_route(
                            group,
                            category=category,
                            path=group_path,
                            diagnostics=diagnostics,
                        )
                        _check_units(
                            group,
                            category=category,
                            points=points,
                            path=group_path,
                            unit_ids=unit_ids,
                            unit_names=unit_names,
                            occupied_parking=occupied_parking,
                            diagnostics=diagnostics,
                        )

    _check_air_start_references(
        mission,
        diagnostics=diagnostics,
    )
    _check_logic_structure(
        mission,
        group_ids=group_ids,
        unit_ids=unit_ids,
        dictionary=dictionary,
        diagnostics=diagnostics,
    )
    actionable_tasks_by_group = _check_waypoint_task_semantics(
        mission,
        profile=profile,
        diagnostics=diagnostics,
    )
    _check_gci_structure(mission, diagnostics)
    _check_late_activation_links(
        mission,
        late_group_paths,
        diagnostics,
    )
    if dictionary is not None:
        _check_briefing_references(mission, dictionary, diagnostics)
    if profile == "complete_scenario":
        _check_complete_mission(
            mission,
            dictionary=dictionary,
            actionable_tasks_by_group=actionable_tasks_by_group,
            diagnostics=diagnostics,
        )

    error_count = sum(item["severity"] == "error" for item in diagnostics)
    warning_count = sum(item["severity"] == "warning" for item in diagnostics)
    return {
        "scope": [
            "coalition table",
            "numeric keys and table items in known DCS sequences",
            "country/group/unit identity fields",
            "group routes and waypoint coordinates",
            "air group task names and waypoint task tables",
            "air waypoint ComboTask wrappers, common combat task schemas, "
            "and group references",
            "unit coordinates and payload station uniqueness",
            "distinct coordinates for units in an airborne group",
            "air-start airfield/linked-facility references and parking occupancy",
            "top-level trigger, compiled trigger, goal, and result linkage",
            "common trigger references to existing group/unit/zone IDs",
            "MiG-29 GCI station activation and compatible-radar linkage",
            "static links for late-activation groups",
            "briefing dictionary references",
            "observed current official mission runtime-shell tables, "
            "coalition-side shapes, country membership, complete-scenario "
            "route, radio, payload, briefing, and AI actionability fields"
            if profile == "complete_scenario"
            else "technical-fixture baseline",
        ],
        "profile": profile,
        "valid": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "diagnostics": diagnostics,
        "runtime_validity_implied": False,
    }


def _check_identity(
    value: LuaTable,
    *,
    id_field: str,
    name_field: str,
    ids: set[int | float],
    names: set[str],
    kind: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    identifier = value.get(id_field)
    if not _is_number(identifier):
        _add(
            diagnostics,
            f"missing_{kind}_id",
            "error",
            f"{path}.{id_field}",
        )
    elif identifier in ids:
        _add(
            diagnostics,
            f"duplicate_{kind}_id",
            "error",
            f"{path}.{id_field}",
        )
    else:
        ids.add(identifier)

    name = value.get(name_field)
    if not isinstance(name, str) or not name:
        _add(
            diagnostics,
            f"missing_{kind}_name",
            "error",
            f"{path}.{name_field}",
        )
    elif name in names:
        _add(
            diagnostics,
            f"duplicate_{kind}_name",
            "error",
            f"{path}.{name_field}",
        )
    else:
        names.add(name)


def _check_route(
    group: LuaTable,
    *,
    category: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> list[LuaTable]:
    route = group.get("route")
    points_value = route.get("points") if isinstance(route, LuaTable) else None
    _check_sequence(
        points_value,
        f"{path}.route.points",
        diagnostics,
        table_items=True,
    )
    points = _numeric_tables(points_value)
    if category != "static" and not points:
        _add(
            diagnostics,
            "missing_group_route_points",
            "error",
            f"{path}.route.points",
        )
        return []
    for index, point in enumerate(points, start=1):
        point_path = f"{path}.route.points[{index}]"
        for coordinate in ("x", "y"):
            if not _is_number(point.get(coordinate)):
                _add(
                    diagnostics,
                    "missing_waypoint_coordinate",
                    "error",
                    f"{point_path}.{coordinate}",
                )
        if category != "static":
            for field_name in ("type", "action"):
                value = point.get(field_name)
                if not isinstance(value, str) or not value:
                    _add(
                        diagnostics,
                        "missing_waypoint_mode",
                        "error",
                        f"{point_path}.{field_name}",
                    )
        if (
            category in {"plane", "helicopter"}
            and index == 1
            and has_invalid_start_mode_pair(point)
        ):
            _add(
                diagnostics,
                "invalid_air_start_mode_pair",
                "error",
                point_path,
            )
        if category in {"plane", "helicopter"}:
            task = point.get("task")
            if not isinstance(task, LuaTable):
                _add(
                    diagnostics,
                    "missing_air_waypoint_task",
                    "error",
                    f"{point_path}.task",
                )
            else:
                task_id = task.get("id")
                if not isinstance(task_id, str) or not task_id:
                    _add(
                        diagnostics,
                        "missing_air_waypoint_task_id",
                        "error",
                        f"{point_path}.task.id",
                    )
                if not isinstance(task.get("params"), LuaTable):
                    _add(
                        diagnostics,
                        "missing_air_waypoint_task_params",
                        "error",
                        f"{point_path}.task.params",
                    )
        _check_task_tree(
            point.get("task"),
            f"{point_path}.task",
            diagnostics,
        )
    return points


def _check_units(
    group: LuaTable,
    *,
    category: str,
    points: list[LuaTable],
    path: str,
    unit_ids: set[int | float],
    unit_names: set[str],
    occupied_parking: set[tuple[str, int | float, str | int | float]],
    diagnostics: list[dict[str, str]],
) -> None:
    units_value = group.get("units")
    _check_sequence(
        units_value,
        f"{path}.units",
        diagnostics,
        table_items=True,
    )
    units = _numeric_tables(units_value)
    if not units:
        _add(
            diagnostics,
            "missing_group_units",
            "error",
            f"{path}.units",
        )
        return

    first_point = points[0] if points else None
    start_mode = (
        classify_start_mode(first_point) if first_point is not None else "other"
    )
    parking_start = start_mode in {"cold_parking", "hot_parking"}
    airborne_start = start_mode == "air"
    airborne_positions: set[tuple[int | float, int | float, int | float]] = set()
    start_facility = (
        _air_start_facility(first_point) if first_point is not None else None
    )

    for index, unit in enumerate(units, start=1):
        unit_path = f"{path}.units[{index}]"
        _check_identity(
            unit,
            id_field="unitId",
            name_field="name",
            ids=unit_ids,
            names=unit_names,
            kind="unit",
            path=unit_path,
            diagnostics=diagnostics,
        )
        unit_type = unit.get("type")
        if not isinstance(unit_type, str) or not unit_type:
            _add(
                diagnostics,
                "missing_unit_type",
                "error",
                f"{unit_path}.type",
            )
        skill = unit.get("skill")
        if category in {"plane", "helicopter"} and (
            not isinstance(skill, str) or not skill
        ):
            _add(
                diagnostics,
                "missing_unit_skill",
                "error",
                f"{unit_path}.skill",
            )
        for coordinate in ("x", "y", "heading"):
            if not _is_number(unit.get(coordinate)):
                _add(
                    diagnostics,
                    "missing_unit_coordinate",
                    "error",
                    f"{unit_path}.{coordinate}",
                )
        if category in {"plane", "helicopter"} and not _is_number(unit.get("alt")):
            _add(
                diagnostics,
                "missing_air_unit_altitude",
                "error",
                f"{unit_path}.alt",
            )
        if airborne_start:
            x = unit.get("x")
            y = unit.get("y")
            altitude = unit.get("alt")
            if _is_number(x) and _is_number(y) and _is_number(altitude):
                position = (x, y, altitude)
                if position in airborne_positions:
                    _add(
                        diagnostics,
                        "duplicate_airborne_unit_position",
                        "error",
                        unit_path,
                    )
                else:
                    airborne_positions.add(position)
        _check_callsign_keys(unit, unit_path, diagnostics)
        _check_pylons(unit, unit_path, diagnostics)

        if (
            not parking_start
            or start_facility is None
            or start_facility[0] == "linked"
            and not unit.has("parking")
        ):
            continue
        parking = unit.get("parking")
        if not _is_parking_token(parking):
            _add(
                diagnostics,
                "parking_start_missing_parking",
                "error",
                f"{unit_path}.parking",
            )
        else:
            occupancy = (*start_facility, parking)
            if occupancy in occupied_parking:
                _add(
                    diagnostics,
                    (
                        "duplicate_airdrome_parking"
                        if start_facility[0] == "airdrome"
                        else "duplicate_linked_parking"
                    ),
                    "error",
                    f"{unit_path}.parking",
                )
            else:
                occupied_parking.add(occupancy)
        parking_id = unit.get("parking_id")
        if not isinstance(parking_id, str) or not parking_id:
            _add(
                diagnostics,
                "parking_start_missing_parking_id",
                "warning",
                f"{unit_path}.parking_id",
            )


def _check_air_start_references(
    mission: LuaTable,
    *,
    diagnostics: list[dict[str, str]],
) -> None:
    groups, _ = _task_group_records(mission)
    unit_index: dict[int | float, dict[str, str]] = {}
    for record in groups:
        for unit in _numeric_tables(record["group"].get("units")):
            unit_id = unit.get("unitId")
            if _is_number(unit_id) and unit_id not in unit_index:
                unit_index[unit_id] = {
                    "category": record["category"],
                    "side": record["side"],
                }
    for record in groups:
        if record["category"] not in {"plane", "helicopter"}:
            continue
        point_fields = record["points"].numeric_items()
        if not point_fields:
            continue
        first_field = point_fields[0]
        first_point = first_field.value
        if not isinstance(first_point, LuaTable):
            continue
        if classify_start_mode(first_point) not in {
            "cold_parking",
            "hot_parking",
            "runway",
        }:
            continue
        point_path = f"{record['path']}.route.points[{first_field.key}]"
        facility = _air_start_facility(first_point)
        if facility is None:
            _add(
                diagnostics,
                "invalid_air_start_facility_reference",
                "error",
                point_path,
            )
            continue
        if facility[0] != "linked":
            continue
        target = unit_index.get(facility[1])
        if target is None:
            _add(
                diagnostics,
                "air_start_link_unit_not_found",
                "error",
                f"{point_path}.linkUnit",
            )
            continue
        if target["category"] not in {"ship", "static"}:
            _add(
                diagnostics,
                "air_start_link_target_not_facility",
                "error",
                f"{point_path}.linkUnit",
            )
        if target["side"] != record["side"]:
            _add(
                diagnostics,
                "air_start_link_target_not_same_coalition",
                "error",
                f"{point_path}.linkUnit",
            )


def _air_start_facility(
    point: LuaTable,
) -> tuple[str, int | float] | None:
    airdrome_id = point.get("airdromeId")
    helipad_id = point.get("helipadId")
    link_unit = point.get("linkUnit")
    has_airdrome = point.has("airdromeId")
    has_helipad = point.has("helipadId")
    has_link = point.has("linkUnit")
    airfield_valid = (
        has_airdrome
        and not has_helipad
        and not has_link
        and _is_positive_integer_number(airdrome_id)
    )
    linked_valid = (
        not has_airdrome
        and has_helipad
        and has_link
        and _is_positive_integer_number(helipad_id)
        and _is_positive_integer_number(link_unit)
        and helipad_id == link_unit
    )
    if airfield_valid:
        return "airdrome", airdrome_id
    if linked_valid:
        return "linked", link_unit
    return None


def _check_group_task(
    group: LuaTable,
    *,
    category: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    if category not in {"plane", "helicopter"}:
        return
    task = group.get("task")
    if task not in _AIR_MAIN_TASKS:
        _add(
            diagnostics,
            "invalid_air_group_task",
            "error",
            f"{path}.task",
        )


def _check_pylons(
    unit: LuaTable,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    payload = unit.get("payload")
    pylons_value = payload.get("pylons") if isinstance(payload, LuaTable) else None
    _check_sequence(
        pylons_value,
        f"{path}.payload.pylons",
        diagnostics,
        table_items=True,
        dense=False,
    )
    pylons = pylons_value.numeric_items() if isinstance(pylons_value, LuaTable) else ()
    stations: set[int | float] = set()
    for pylon_field in pylons:
        pylon_path = f"{path}.payload.pylons[{pylon_field.key}]"
        pylon = _required_table(
            pylon_field.value,
            diagnostics,
            "invalid_pylon_table",
            pylon_path,
        )
        if pylon is None:
            continue
        station = pylon.get("num")
        if not _is_number(station):
            station = pylon_field.key
        if station in stations:
            _add(
                diagnostics,
                "duplicate_pylon_station",
                "error",
                pylon_path,
            )
        else:
            stations.add(station)
        clsid = pylon.get("CLSID")
        if not isinstance(clsid, str) or not clsid:
            _add(
                diagnostics,
                "missing_pylon_clsid",
                "error",
                f"{pylon_path}.CLSID",
            )


def _check_callsign_keys(
    unit: LuaTable,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    callsign = unit.get("callsign")
    if not isinstance(callsign, LuaTable):
        return
    for field in callsign.fields:
        if isinstance(field.key, str) and field.key.isdecimal():
            _add(
                diagnostics,
                "stringified_numeric_callsign_key",
                "error",
                f"{path}.callsign[{field.key!r}]",
            )


def _check_briefing_references(
    mission: LuaTable,
    dictionary: LuaTable,
    diagnostics: list[dict[str, str]],
) -> None:
    for field_name in BRIEFING_FIELDS:
        key = mission.get(field_name)
        if key is None:
            continue
        if isinstance(key, str) and not key.strip():
            _add(
                diagnostics,
                "empty_briefing_dictionary_key",
                "warning",
                f"$.{field_name}",
            )
            continue
        if not isinstance(key, str) or not dictionary.has(key):
            _add(
                diagnostics,
                "unresolved_briefing_dictionary_key",
                "error",
                f"$.{field_name}",
            )
            continue
        text = dictionary.get(key)
        if not isinstance(text, str):
            _add(
                diagnostics,
                "invalid_briefing_dictionary_value",
                "error",
                f"$.{field_name}",
            )
        elif not text.strip():
            _add(
                diagnostics,
                "empty_briefing_dictionary_value",
                "warning",
                f"$.{field_name}",
            )


def _check_complete_mission(
    mission: LuaTable,
    *,
    dictionary: LuaTable | None,
    actionable_tasks_by_group: dict[str, set[str]],
    diagnostics: list[dict[str, str]],
) -> None:
    _check_complete_runtime_shell(mission, diagnostics)
    for field_name in BRIEFING_FIELDS:
        if not mission.has(field_name):
            _add(
                diagnostics,
                "complete_missing_briefing_field",
                "error",
                f"$.{field_name}",
            )
    if dictionary is None:
        _add(
            diagnostics,
            "complete_dictionary_not_checked",
            "error",
            "$.briefing",
        )

    coalition = mission.get("coalition")
    if not isinstance(coalition, LuaTable):
        return
    for side_field in coalition.fields:
        side = side_field.value
        if not isinstance(side, LuaTable):
            continue
        countries = side.get("country")
        if not isinstance(countries, LuaTable):
            continue
        for country_field in countries.numeric_items():
            country = country_field.value
            if not isinstance(country, LuaTable):
                continue
            country_path = f"$.coalition.{side_field.key}.country[{country_field.key}]"
            for category in ("plane", "helicopter"):
                category_table = country.get(category)
                if not isinstance(category_table, LuaTable):
                    continue
                groups = category_table.get("group")
                if not isinstance(groups, LuaTable):
                    continue
                for group_field in groups.numeric_items():
                    group = group_field.value
                    if not isinstance(group, LuaTable):
                        continue
                    group_path = f"{country_path}.{category}.group[{group_field.key}]"
                    _check_complete_air_group(
                        group,
                        path=group_path,
                        actionable_task_ids=actionable_tasks_by_group.get(
                            group_path,
                            set(),
                        ),
                        diagnostics=diagnostics,
                    )


def _check_complete_runtime_shell(
    mission: LuaTable,
    diagnostics: list[dict[str, str]],
) -> None:
    """Check the core shell present in every accepted current official sample."""

    runtime_tables: dict[str, LuaTable] = {}
    for field_name in _COMPLETE_RUNTIME_TABLES:
        value = mission.get(field_name)
        if not isinstance(value, LuaTable):
            _add(
                diagnostics,
                "complete_missing_observed_runtime_table",
                "error",
                f"$.{field_name}",
            )
            continue
        runtime_tables[field_name] = value

    for field_name in ("currentKey", "maxDictId"):
        if not _is_nonnegative_integer_number(mission.get(field_name)):
            _add(
                diagnostics,
                "complete_invalid_observed_runtime_integer",
                "error",
                f"$.{field_name}",
            )

    map_table = runtime_tables.get("map")
    if map_table is not None:
        for field_name in ("centerX", "centerY"):
            if not _is_finite_number(map_table.get(field_name)):
                _add(
                    diagnostics,
                    "complete_invalid_map_field",
                    "error",
                    f"$.map.{field_name}",
                )
        if not _is_positive_finite_number(map_table.get("zoom")):
            _add(
                diagnostics,
                "complete_invalid_map_field",
                "error",
                "$.map.zoom",
            )

    ground_control = runtime_tables.get("groundControl")
    if ground_control is not None:
        if not isinstance(
            ground_control.get("isPilotControlVehicles"),
            bool,
        ):
            _add(
                diagnostics,
                "complete_invalid_ground_control_field",
                "error",
                "$.groundControl.isPilotControlVehicles",
            )
        roles = ground_control.get("roles")
        if not isinstance(roles, LuaTable):
            _add(
                diagnostics,
                "complete_missing_ground_control_roles",
                "error",
                "$.groundControl.roles",
            )
        else:
            for role_name in _GROUND_CONTROL_ROLES:
                role = roles.get(role_name)
                role_path = f"$.groundControl.roles.{role_name}"
                if not isinstance(role, LuaTable):
                    _add(
                        diagnostics,
                        "complete_missing_ground_control_role",
                        "error",
                        role_path,
                    )
                    continue
                for side_name in ("blue", "red"):
                    if not isinstance(role.get(side_name), LuaTable):
                        _add(
                            diagnostics,
                            "complete_missing_ground_control_role_side",
                            "error",
                            f"{role_path}.{side_name}",
                        )

    coalition = mission.get("coalition")
    coalitions = runtime_tables.get("coalitions")
    country_ids_by_side: dict[str, set[int | float]] = {}
    side_names = ("blue", "red", "neutrals")
    for side_name in side_names:
        required = side_name in {"blue", "red"}
        side = coalition.get(side_name) if isinstance(coalition, LuaTable) else None
        if not isinstance(side, LuaTable):
            if required:
                _add(
                    diagnostics,
                    "complete_missing_coalition_side",
                    "error",
                    f"$.coalition.{side_name}",
                )
            continue
        side_path = f"$.coalition.{side_name}"
        if side.get("name") != side_name:
            _add(
                diagnostics,
                "complete_invalid_coalition_side_name",
                "error",
                f"{side_path}.name",
            )
        bullseye = side.get("bullseye")
        if not isinstance(bullseye, LuaTable):
            _add(
                diagnostics,
                "complete_missing_coalition_side_table",
                "error",
                f"{side_path}.bullseye",
            )
        else:
            for coordinate in ("x", "y"):
                if not _is_finite_number(bullseye.get(coordinate)):
                    _add(
                        diagnostics,
                        "complete_invalid_bullseye_coordinate",
                        "error",
                        f"{side_path}.bullseye.{coordinate}",
                    )
        if not isinstance(side.get("nav_points"), LuaTable):
            _add(
                diagnostics,
                "complete_missing_coalition_side_table",
                "error",
                f"{side_path}.nav_points",
            )
        countries = side.get("country")
        if not isinstance(countries, LuaTable):
            _add(
                diagnostics,
                "complete_missing_coalition_side_table",
                "error",
                f"{side_path}.country",
            )
            continue
        country_ids_by_side[side_name] = {
            field.value.get("id")
            for field in countries.numeric_items()
            if isinstance(field.value, LuaTable)
            and _is_nonnegative_integer_number(field.value.get("id"))
        }

    membership_by_side: dict[str, set[int | float]] = {}
    if coalitions is not None:
        for side_name in side_names:
            required = side_name in {"blue", "red"} or bool(
                country_ids_by_side.get(side_name)
            )
            membership = coalitions.get(side_name)
            if not isinstance(membership, LuaTable):
                if required:
                    _add(
                        diagnostics,
                        "complete_missing_coalition_membership",
                        "error",
                        f"$.coalitions.{side_name}",
                    )
                continue
            fields = membership.numeric_items()
            keys = sorted(field.key for field in fields)
            if len(fields) != len(membership.fields) or keys != list(
                range(1, len(keys) + 1)
            ):
                _add(
                    diagnostics,
                    "complete_invalid_coalition_membership_sequence",
                    "error",
                    f"$.coalitions.{side_name}",
                )
            values: set[int | float] = set()
            for field in fields:
                if not _is_nonnegative_integer_number(field.value):
                    _add(
                        diagnostics,
                        "complete_invalid_coalition_membership_id",
                        "error",
                        f"$.coalitions.{side_name}[{field.key}]",
                    )
                    continue
                if field.value in values:
                    _add(
                        diagnostics,
                        "complete_duplicate_coalition_membership_id",
                        "error",
                        f"$.coalitions.{side_name}[{field.key}]",
                    )
                values.add(field.value)
            membership_by_side[side_name] = values
            missing_ids = country_ids_by_side.get(side_name, set()) - values
            if missing_ids:
                _add(
                    diagnostics,
                    "complete_country_missing_from_coalition_membership",
                    "error",
                    f"$.coalitions.{side_name}",
                )

        claimed_sides: dict[int | float, str] = {}
        for side_name, values in membership_by_side.items():
            for country_id in values:
                previous_side = claimed_sides.get(country_id)
                if previous_side is not None and previous_side != side_name:
                    _add(
                        diagnostics,
                        "complete_country_in_multiple_coalitions",
                        "error",
                        f"$.coalitions.{side_name}",
                    )
                else:
                    claimed_sides[country_id] = side_name


def _check_complete_air_group(
    group: LuaTable,
    *,
    path: str,
    actionable_task_ids: set[str],
    diagnostics: list[dict[str, str]],
) -> None:
    if not isinstance(group.get("communication"), bool):
        _add(
            diagnostics,
            "complete_missing_group_communication",
            "error",
            f"{path}.communication",
        )
    for field_name in ("frequency", "modulation"):
        if not _is_number(group.get(field_name)):
            _add(
                diagnostics,
                "complete_missing_group_radio_field",
                "error",
                f"{path}.{field_name}",
            )
    if group.has("radioSet") and not isinstance(group.get("radioSet"), bool):
        _add(
            diagnostics,
            "complete_invalid_group_radio_set",
            "error",
            f"{path}.radioSet",
        )

    points = _numeric_tables(
        group.get("route").get("points")
        if isinstance(group.get("route"), LuaTable)
        else None
    )
    for index, point in enumerate(points, start=1):
        point_path = f"{path}.route.points[{index}]"
        for field_name in ("alt", "speed", "ETA"):
            if not _is_finite_number(point.get(field_name)):
                _add(
                    diagnostics,
                    "complete_missing_waypoint_number",
                    "error",
                    f"{point_path}.{field_name}",
                )
        for field_name in ("x", "y"):
            if not _is_finite_number(point.get(field_name)):
                _add(
                    diagnostics,
                    "complete_invalid_waypoint_coordinate",
                    "error",
                    f"{point_path}.{field_name}",
                )
        if _is_finite_number(point.get("ETA")) and point.get("ETA") < 0:
            _add(
                diagnostics,
                "complete_negative_waypoint_eta",
                "error",
                f"{point_path}.ETA",
            )
        if _is_finite_number(point.get("speed")) and point.get("speed") < 0:
            _add(
                diagnostics,
                "complete_negative_waypoint_speed",
                "error",
                f"{point_path}.speed",
            )
        for field_name in ("alt_type", "type", "action"):
            value = point.get(field_name)
            if not isinstance(value, str) or not value:
                _add(
                    diagnostics,
                    "complete_missing_waypoint_string",
                    "error",
                    f"{point_path}.{field_name}",
                )
        for field_name in ("ETA_locked", "speed_locked"):
            if not isinstance(point.get(field_name), bool):
                _add(
                    diagnostics,
                    "complete_missing_waypoint_lock",
                    "error",
                    f"{point_path}.{field_name}",
                )
        eta_locked = point.get("ETA_locked")
        speed_locked = point.get("speed_locked")
        if index == 1:
            if eta_locked is not True or speed_locked is not True:
                _add(
                    diagnostics,
                    "complete_invalid_first_waypoint_locks",
                    "error",
                    point_path,
                )
        elif eta_locked is True and speed_locked is True:
            _add(
                diagnostics,
                "complete_conflicting_waypoint_locks",
                "error",
                point_path,
            )
        landing_marker = point.get("type") == "Land" or point.get("action") == "Landing"
        if landing_marker:
            if point.get("type") != "Land" or point.get("action") != "Landing":
                _add(
                    diagnostics,
                    "complete_invalid_landing_mode",
                    "error",
                    point_path,
                )
            airfield = _is_number(point.get("airdromeId"))
            linked = _is_number(point.get("helipadId")) and _is_number(
                point.get("linkUnit")
            )
            if airfield == linked:
                _add(
                    diagnostics,
                    "complete_invalid_landing_reference",
                    "error",
                    point_path,
                )
        elif index > 1 and _is_number(point.get("speed")) and point.get("speed") == 0:
            _add(
                diagnostics,
                "complete_zero_enroute_waypoint_speed",
                "error",
                f"{point_path}.speed",
            )

    if points:
        start_time = group.get("start_time")
        first_eta = points[0].get("ETA")
        if (
            not _is_finite_number(start_time)
            or not _is_finite_number(first_eta)
            or start_time != first_eta
        ):
            _add(
                diagnostics,
                "complete_group_start_time_mismatch",
                "error",
                f"{path}.start_time",
            )
        if _is_finite_number(start_time) and start_time < 0:
            _add(
                diagnostics,
                "complete_negative_group_start_time",
                "error",
                f"{path}.start_time",
            )

    units = _numeric_tables(group.get("units"))
    has_human_slot = any(unit.get("skill") in {"Player", "Client"} for unit in units)
    if group.has("lateActivation") and not isinstance(
        group.get("lateActivation"),
        bool,
    ):
        _add(
            diagnostics,
            "complete_invalid_late_activation",
            "error",
            f"{path}.lateActivation",
        )
    if has_human_slot and points and points[0].get("ETA") != 0:
        _add(
            diagnostics,
            "complete_human_start_not_zero",
            "error",
            f"{path}.route.points[1].ETA",
        )
    if has_human_slot and group.get("lateActivation") is True:
        _add(
            diagnostics,
            "complete_human_late_activation",
            "error",
            f"{path}.lateActivation",
        )
    for index, unit in enumerate(units, start=1):
        unit_path = f"{path}.units[{index}]"
        for field_name in ("alt", "speed"):
            if not _is_finite_number(unit.get(field_name)):
                _add(
                    diagnostics,
                    "complete_missing_air_unit_number",
                    "error",
                    f"{unit_path}.{field_name}",
                )
        for field_name in ("x", "y", "heading"):
            if not _is_finite_number(unit.get(field_name)):
                _add(
                    diagnostics,
                    "complete_invalid_air_unit_geometry",
                    "error",
                    f"{unit_path}.{field_name}",
                )
        if _is_finite_number(unit.get("speed")) and unit.get("speed") < 0:
            _add(
                diagnostics,
                "complete_negative_air_unit_speed",
                "error",
                f"{unit_path}.speed",
            )
        if not isinstance(unit.get("alt_type"), str):
            _add(
                diagnostics,
                "complete_missing_air_unit_alt_type",
                "error",
                f"{unit_path}.alt_type",
            )
        callsign = unit.get("callsign")
        if not isinstance(callsign, LuaTable) and not _is_number(callsign):
            _add(
                diagnostics,
                "complete_missing_air_unit_callsign",
                "error",
                f"{unit_path}.callsign",
            )
        onboard = unit.get("onboard_num")
        if not isinstance(onboard, str) and not _is_number(onboard):
            _add(
                diagnostics,
                "complete_missing_air_unit_onboard_number",
                "error",
                f"{unit_path}.onboard_num",
            )
        payload = unit.get("payload")
        if not isinstance(payload, LuaTable):
            _add(
                diagnostics,
                "complete_missing_air_unit_payload",
                "error",
                f"{unit_path}.payload",
            )
            continue
        if not isinstance(payload.get("pylons"), LuaTable):
            _add(
                diagnostics,
                "complete_missing_payload_pylons",
                "error",
                f"{unit_path}.payload.pylons",
            )
        fuel = payload.get("fuel")
        if not _is_number(fuel) and not _is_numeric_string(fuel):
            _add(
                diagnostics,
                "complete_invalid_payload_fuel",
                "error",
                f"{unit_path}.payload.fuel",
            )
        for field_name in ("chaff", "flare", "gun"):
            if not _is_number(payload.get(field_name)):
                _add(
                    diagnostics,
                    "complete_missing_payload_consumable",
                    "error",
                    f"{unit_path}.payload.{field_name}",
                )

    if points and units and classify_start_mode(points[0]) == "air":
        if _is_finite_number(points[0].get("speed")) and points[0].get("speed") <= 0:
            _add(
                diagnostics,
                "complete_nonpositive_air_start_speed",
                "error",
                f"{path}.route.points[1].speed",
            )
        for index, unit in enumerate(units, start=1):
            if _is_finite_number(unit.get("speed")) and unit.get("speed") <= 0:
                _add(
                    diagnostics,
                    "complete_nonpositive_air_start_speed",
                    "error",
                    f"{path}.units[{index}].speed",
                )
        if len(points) >= 2:
            first_x = points[0].get("x")
            first_y = points[0].get("y")
            second_x = points[1].get("x")
            second_y = points[1].get("y")
            heading = units[0].get("heading")
            converted = tuple(
                _finite_float(value)
                for value in (
                    first_x,
                    first_y,
                    second_x,
                    second_y,
                    heading,
                )
            )
            if all(value is not None for value in converted):
                (
                    first_x_float,
                    first_y_float,
                    second_x_float,
                    second_y_float,
                    heading_float,
                ) = converted
                assert first_x_float is not None
                assert first_y_float is not None
                assert second_x_float is not None
                assert second_y_float is not None
                assert heading_float is not None
                delta_x = second_x_float - first_x_float
                delta_y = second_y_float - first_y_float
                if not math.isfinite(delta_x) or not math.isfinite(delta_y):
                    _add(
                        diagnostics,
                        "complete_air_start_geometry_out_of_range",
                        "error",
                        f"{path}.route.points[2]",
                    )
                elif math.hypot(delta_x, delta_y) > 1:
                    route_heading = math.atan2(delta_y, delta_x)
                    heading_error = abs(
                        (heading_float - route_heading + math.pi) % math.tau - math.pi
                    )
                    if heading_error > _MAX_COMPLETE_AIR_START_HEADING_ERROR_RAD:
                        _add(
                            diagnostics,
                            "complete_air_start_heading_route_mismatch",
                            "error",
                            f"{path}.units[1].heading",
                        )

    if units and all(unit.get("skill") not in {"Player", "Client"} for unit in units):
        main_task = group.get("task")
        required_tasks = _COMPLETE_COMBAT_TASKS.get(main_task)
        if required_tasks is not None:
            if actionable_task_ids.isdisjoint(required_tasks):
                _add(
                    diagnostics,
                    "complete_ai_group_has_no_actionable_task",
                    "error",
                    f"{path}.route",
                )


def _is_numeric_string(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = float(value)
    except ValueError:
        return False
    return math.isfinite(parsed)


def _required_table(
    value: Any,
    diagnostics: list[dict[str, str]],
    code: str,
    path: str,
) -> LuaTable | None:
    if isinstance(value, LuaTable):
        return value
    _add(diagnostics, code, "error", path)
    return None


def _check_mission_sequences(
    mission: LuaTable,
    diagnostics: list[dict[str, str]],
) -> None:
    coalitions = mission.get("coalitions")
    if isinstance(coalitions, LuaTable):
        for side in coalitions.fields:
            _check_sequence(
                side.value,
                f"$.coalitions.{side.key}",
                diagnostics,
                table_items=False,
            )

    triggers = mission.get("triggers")
    if isinstance(triggers, LuaTable):
        _check_sequence(
            triggers.get("zones"),
            "$.triggers.zones",
            diagnostics,
            table_items=True,
        )

    rules_value = mission.get("trigrules")
    _check_sequence(
        rules_value,
        "$.trigrules",
        diagnostics,
        table_items=True,
    )
    for rule_field in (
        rules_value.numeric_items() if isinstance(rules_value, LuaTable) else ()
    ):
        if not isinstance(rule_field.value, LuaTable):
            continue
        for field_name in ("rules", "actions"):
            _check_sequence(
                rule_field.value.get(field_name),
                f"$.trigrules[{rule_field.key}].{field_name}",
                diagnostics,
                table_items=True,
            )

    goals_value = mission.get("goals")
    _check_sequence(
        goals_value,
        "$.goals",
        diagnostics,
        table_items=True,
    )
    for goal_field in (
        goals_value.numeric_items() if isinstance(goals_value, LuaTable) else ()
    ):
        if not isinstance(goal_field.value, LuaTable):
            continue
        _check_sequence(
            goal_field.value.get("rules"),
            f"$.goals[{goal_field.key}].rules",
            diagnostics,
            table_items=True,
        )


def _check_task_tree(
    value: Any,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        child_path = f"{path}.{field.key}"
        if field.key == "tasks":
            _check_sequence(
                field.value,
                child_path,
                diagnostics,
                table_items=True,
            )
        if isinstance(field.value, LuaTable):
            _check_task_tree(field.value, child_path, diagnostics)


def _check_waypoint_task_semantics(
    mission: LuaTable,
    *,
    profile: str,
    diagnostics: list[dict[str, str]],
) -> dict[str, set[str]]:
    groups, groups_by_id = _task_group_records(mission)
    actionable_tasks_by_group: dict[str, set[str]] = {
        source["path"]: set() for source in groups
    }
    for source in groups:
        if source["category"] not in {"plane", "helicopter"}:
            continue
        points_are_dense = _is_dense_sequence(
            source["points"],
            table_items=True,
        )
        for point_field in source["points"].numeric_items():
            point = point_field.value
            if not isinstance(point, LuaTable):
                continue
            root_path = f"{source['path']}.route.points[{point_field.key}].task"
            root = point.get("task")
            if not isinstance(root, LuaTable):
                continue
            root_is_combo = root.get("id") == "ComboTask"
            if not root_is_combo:
                _add(
                    diagnostics,
                    "invalid_air_waypoint_root_task",
                    "error",
                    f"{root_path}.id",
                )
            params = root.get("params")
            if not isinstance(params, LuaTable):
                continue
            tasks = params.get("tasks")
            if not isinstance(tasks, LuaTable):
                _add(
                    diagnostics,
                    "missing_combo_task_children",
                    "error",
                    f"{root_path}.params.tasks",
                )
                continue
            tasks_are_dense = _is_dense_sequence(
                tasks,
                table_items=True,
            )
            for task_field in tasks.fields:
                task_path = f"{root_path}.params.tasks[{task_field.key!r}]"
                task = task_field.value
                if not isinstance(task, LuaTable):
                    continue
                actionable = _check_direct_waypoint_task(
                    task,
                    sequence_key=task_field.key,
                    waypoint=point,
                    source=source,
                    groups_by_id=groups_by_id,
                    profile=profile,
                    path=task_path,
                    diagnostics=diagnostics,
                )
                if root_is_combo and points_are_dense and tasks_are_dense:
                    actionable_tasks_by_group[source["path"]].update(actionable)
    return actionable_tasks_by_group


def _task_group_records(
    mission: LuaTable,
) -> tuple[list[dict[str, Any]], dict[int | float, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    by_id: dict[int | float, dict[str, Any]] = {}
    coalition = mission.get("coalition")
    if not isinstance(coalition, LuaTable):
        return records, by_id
    for side_field in coalition.fields:
        side = side_field.value
        if not isinstance(side, LuaTable):
            continue
        countries = side.get("country")
        if not isinstance(countries, LuaTable):
            continue
        for country_field in countries.numeric_items():
            country = country_field.value
            if not isinstance(country, LuaTable):
                continue
            country_path = f"$.coalition.{side_field.key}.country[{country_field.key}]"
            for category in CATEGORIES:
                category_table = country.get(category)
                if not isinstance(category_table, LuaTable):
                    continue
                groups = category_table.get("group")
                if not isinstance(groups, LuaTable):
                    continue
                for group_field in groups.numeric_items():
                    group = group_field.value
                    if not isinstance(group, LuaTable):
                        continue
                    route = group.get("route")
                    points = (
                        route.get("points") if isinstance(route, LuaTable) else None
                    )
                    record = {
                        "category": category,
                        "group": group,
                        "group_id": group.get("groupId"),
                        "path": (f"{country_path}.{category}.group[{group_field.key}]"),
                        "points": (
                            points if isinstance(points, LuaTable) else LuaTable(())
                        ),
                        "side": str(side_field.key),
                    }
                    records.append(record)
                    group_id = record["group_id"]
                    if _is_number(group_id) and group_id not in by_id:
                        by_id[group_id] = record
    return records, by_id


def _check_direct_waypoint_task(
    task: LuaTable,
    *,
    sequence_key: str | int | float,
    waypoint: LuaTable,
    source: dict[str, Any],
    groups_by_id: dict[int | float, dict[str, Any]],
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> set[str]:
    diagnostics_start = len(diagnostics)
    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id:
        _add(
            diagnostics,
            "invalid_direct_task_wrapper",
            "error",
            f"{path}.id",
        )
    if not isinstance(task.get("params"), LuaTable):
        _add(
            diagnostics,
            "invalid_direct_task_wrapper",
            "error",
            f"{path}.params",
        )
    number = task.get("number")
    if not _is_positive_integer_number(number):
        _add(
            diagnostics,
            "invalid_direct_task_wrapper",
            "error",
            f"{path}.number",
        )
    elif _is_number(sequence_key) and number != sequence_key:
        _add(
            diagnostics,
            "direct_task_number_mismatch",
            "error" if profile == "complete_scenario" else "warning",
            f"{path}.number",
        )
    for field_name in ("auto", "enabled"):
        if not isinstance(task.get(field_name), bool):
            _add(
                diagnostics,
                "invalid_direct_task_wrapper",
                "error",
                f"{path}.{field_name}",
            )
    semantic_task_ids = _check_waypoint_task_node(
        task,
        source=source,
        groups_by_id=groups_by_id,
        profile=profile,
        path=path,
        diagnostics=diagnostics,
    )
    _check_waypoint_task_activation_distance(
        task,
        waypoint=waypoint,
        profile=profile,
        path=path,
        diagnostics=diagnostics,
    )
    new_errors = any(
        item["severity"] == "error" for item in diagnostics[diagnostics_start:]
    )
    if task.get("enabled") is not True or new_errors:
        return set()
    return semantic_task_ids


def _check_waypoint_task_activation_distance(
    task: LuaTable,
    *,
    waypoint: LuaTable,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    if profile != "complete_scenario":
        return
    task_id = task.get("id")
    params = task.get("params")
    if not isinstance(params, LuaTable):
        return
    if task_id == "ControlledTask":
        nested = params.get("task")
        if isinstance(nested, LuaTable):
            _check_waypoint_task_activation_distance(
                nested,
                waypoint=waypoint,
                profile=profile,
                path=f"{path}.params.task",
                diagnostics=diagnostics,
            )
        return
    if task_id != "Bombing":
        return
    point_x = waypoint.get("x")
    point_y = waypoint.get("y")
    target_x = params.get("x")
    target_y = params.get("y")
    converted = tuple(
        _finite_float(value) for value in (point_x, point_y, target_x, target_y)
    )
    if any(value is None for value in converted):
        return
    point_x_float, point_y_float, target_x_float, target_y_float = converted
    assert point_x_float is not None
    assert point_y_float is not None
    assert target_x_float is not None
    assert target_y_float is not None
    delta_x = target_x_float - point_x_float
    delta_y = target_y_float - point_y_float
    distance = (
        math.inf
        if not math.isfinite(delta_x) or not math.isfinite(delta_y)
        else math.hypot(delta_x, delta_y)
    )
    if distance > _MAX_COMPLETE_BOMBING_ACTIVATION_DISTANCE_M:
        _add(
            diagnostics,
            "complete_bombing_activation_too_far_from_target",
            "error",
            f"{path}.params",
        )


def _check_waypoint_task_node(
    task: LuaTable,
    *,
    source: dict[str, Any],
    groups_by_id: dict[int | float, dict[str, Any]],
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> set[str]:
    task_id = task.get("id")
    params = task.get("params")
    if not isinstance(task_id, str) or not isinstance(params, LuaTable):
        return set()
    semantic_task_ids: set[str] = set()
    if task_id in _SEMANTIC_WAYPOINT_TASKS:
        _check_combat_task_params(
            task_id,
            params,
            source=source,
            groups_by_id=groups_by_id,
            profile=profile,
            path=f"{path}.params",
            diagnostics=diagnostics,
        )
        semantic_task_ids.add(task_id)
    if task_id != "ControlledTask":
        return semantic_task_ids
    nested = params.get("task")
    if not isinstance(nested, LuaTable):
        _add(
            diagnostics,
            "invalid_controlled_task_child",
            "error",
            f"{path}.params.task",
        )
        return set()
    nested_id = nested.get("id")
    nested_params = nested.get("params")
    if not isinstance(nested_id, str) or not nested_id:
        _add(
            diagnostics,
            "invalid_controlled_task_child",
            "error",
            f"{path}.params.task.id",
        )
        return set()
    if not isinstance(nested_params, LuaTable):
        _add(
            diagnostics,
            "invalid_controlled_task_child",
            "error",
            f"{path}.params.task.params",
        )
        return set()
    return _check_waypoint_task_node(
        nested,
        source=source,
        groups_by_id=groups_by_id,
        profile=profile,
        path=f"{path}.params.task",
        diagnostics=diagnostics,
    )


def _check_combat_task_params(
    task_id: str,
    params: LuaTable,
    *,
    source: dict[str, Any],
    groups_by_id: dict[int | float, dict[str, Any]],
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    if task_id == "AttackGroup":
        _check_attack_group_params(
            params,
            source=source,
            groups_by_id=groups_by_id,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "AttackMapObject":
        _check_attack_map_object_params(
            params,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "Bombing":
        _check_bombing_params(
            params,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "BombingRunway":
        _check_bombing_runway_params(
            params,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "EngageTargets":
        _check_engage_targets_params(
            params,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "EngageTargetsInZone":
        _check_engage_targets_in_zone_params(
            params,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )
    elif task_id == "Escort":
        _check_escort_params(
            params,
            source=source,
            groups_by_id=groups_by_id,
            profile=profile,
            path=path,
            diagnostics=diagnostics,
        )


def _check_attack_group_params(
    params: LuaTable,
    *,
    source: dict[str, Any],
    groups_by_id: dict[int | float, dict[str, Any]],
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "groupId": _is_positive_integer_number,
        "weaponType": _is_nonnegative_integer_number,
        "groupAttack": lambda value: isinstance(value, bool),
        "attackQtyLimit": lambda value: isinstance(value, bool),
        "attackQty": _is_positive_integer_number,
        "altitudeEnabled": lambda value: isinstance(value, bool),
        "altitude": _is_finite_number,
        "directionEnabled": lambda value: isinstance(value, bool),
        "direction": _is_finite_number,
        "expend": _is_nonempty_string,
    }
    required = {"weaponType"}
    if profile == "complete_scenario":
        required.update(specs)
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=required - {"weaponType"},
        path=path,
        diagnostics=diagnostics,
    )
    expend = values.get("expend")
    if (
        profile == "complete_scenario"
        and isinstance(expend, str)
        and expend not in _TASK_EXPEND_VALUES
    ):
        _add(
            diagnostics,
            "invalid_task_parameter",
            "error",
            f"{path}.expend",
        )
    group_id = values.get("groupId")
    if _is_positive_integer_number(group_id):
        target = groups_by_id.get(group_id)
        if target is None:
            _add(
                diagnostics,
                "task_target_group_not_found",
                "error",
                f"{path}.groupId",
            )
        else:
            if target["side"] == source["side"]:
                _add(
                    diagnostics,
                    "attack_group_target_not_hostile",
                    "error",
                    f"{path}.groupId",
                )
            if target["category"] == "static":
                _add(
                    diagnostics,
                    "attack_group_target_static",
                    "error",
                    f"{path}.groupId",
                )


def _check_attack_map_object_params(
    params: LuaTable,
    *,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "x": _is_finite_number,
        "y": _is_finite_number,
        "altitude": _is_finite_number,
        "altitudeEdited": lambda value: isinstance(value, bool),
        "altitudeEnabled": lambda value: isinstance(value, bool),
        "attackQty": _is_positive_integer_number,
        "attackQtyLimit": lambda value: isinstance(value, bool),
        "direction": _is_finite_number,
        "directionEnabled": lambda value: isinstance(value, bool),
        "expend": _is_nonempty_string,
        "groupAttack": lambda value: isinstance(value, bool),
        "weaponType": _is_nonnegative_integer_number,
    }
    required = {"x", "y", "weaponType"}
    complete_required: set[str] = set()
    if profile == "complete_scenario":
        complete_required = {
            "altitude",
            "altitudeEnabled",
            "attackQty",
            "attackQtyLimit",
            "direction",
            "directionEnabled",
            "expend",
            "groupAttack",
        }
        required.update(complete_required)
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=complete_required,
        path=path,
        diagnostics=diagnostics,
    )
    _check_task_expend(
        values,
        profile=profile,
        path=path,
        diagnostics=diagnostics,
    )


def _check_bombing_params(
    params: LuaTable,
    *,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "x": _is_finite_number,
        "y": _is_finite_number,
        "altitude": _is_finite_number,
        "altitudeEnabled": lambda value: isinstance(value, bool),
        "attackQty": _is_positive_integer_number,
        "attackQtyLimit": lambda value: isinstance(value, bool),
        "direction": _is_finite_number,
        "directionEnabled": lambda value: isinstance(value, bool),
        "expend": _is_nonempty_string,
        "groupAttack": lambda value: isinstance(value, bool),
        "weaponType": _is_nonnegative_integer_number,
        "altitudeEdited": lambda value: isinstance(value, bool),
        "attackType": _is_nonempty_string,
    }
    required = {
        "x",
        "y",
        "altitude",
        "altitudeEnabled",
        "attackQty",
        "direction",
        "directionEnabled",
        "expend",
        "weaponType",
    }
    complete_required: set[str] = set()
    if profile == "complete_scenario":
        complete_required = {"attackQtyLimit", "groupAttack"}
        required.update(complete_required)
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=complete_required,
        path=path,
        diagnostics=diagnostics,
    )
    _check_task_expend(
        values,
        profile=profile,
        path=path,
        diagnostics=diagnostics,
    )


def _check_bombing_runway_params(
    params: LuaTable,
    *,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "runwayId": _is_positive_integer_number,
        "x": _is_finite_number,
        "y": _is_finite_number,
        "altitude": _is_finite_number,
        "altitudeEdited": lambda value: isinstance(value, bool),
        "altitudeEnabled": lambda value: isinstance(value, bool),
        "attackQty": _is_positive_integer_number,
        "attackQtyLimit": lambda value: isinstance(value, bool),
        "direction": _is_finite_number,
        "directionEnabled": lambda value: isinstance(value, bool),
        "expend": _is_nonempty_string,
        "groupAttack": lambda value: isinstance(value, bool),
        "weaponType": _is_nonnegative_integer_number,
    }
    required = {"runwayId", "weaponType"}
    complete_required: set[str] = set()
    if profile == "complete_scenario":
        complete_required = {
            "altitude",
            "altitudeEnabled",
            "attackQty",
            "attackQtyLimit",
            "direction",
            "directionEnabled",
            "expend",
            "groupAttack",
        }
        required.update(complete_required)
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=complete_required,
        path=path,
        diagnostics=diagnostics,
    )
    _check_task_expend(
        values,
        profile=profile,
        path=path,
        diagnostics=diagnostics,
    )


def _check_task_expend(
    values: dict[str, Any],
    *,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    expend = values.get("expend")
    if (
        profile == "complete_scenario"
        and isinstance(expend, str)
        and expend not in _TASK_EXPEND_VALUES
    ):
        _add(
            diagnostics,
            "invalid_task_parameter",
            "error",
            f"{path}.expend",
        )


def _check_engage_targets_params(
    params: LuaTable,
    *,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "targetTypes": lambda value: isinstance(value, LuaTable),
        "priority": _is_finite_number,
        "maxDist": _is_positive_finite_number,
        "maxDistEnabled": lambda value: isinstance(value, bool),
        "noTargetTypes": lambda value: isinstance(value, LuaTable),
        "value": lambda value: isinstance(value, str),
    }
    values = _check_task_parameters(
        params,
        specs=specs,
        required={"targetTypes", "priority"},
        complete_required=set(),
        path=path,
        diagnostics=diagnostics,
    )
    target_types = values.get("targetTypes")
    if isinstance(target_types, LuaTable):
        _check_string_sequence(
            target_types,
            allow_empty=False,
            code="invalid_task_target_types",
            path=f"{path}.targetTypes",
            diagnostics=diagnostics,
        )
    no_target_types = values.get("noTargetTypes")
    if isinstance(no_target_types, LuaTable):
        _check_string_sequence(
            no_target_types,
            allow_empty=True,
            code="invalid_task_no_target_types",
            path=f"{path}.noTargetTypes",
            diagnostics=diagnostics,
        )
    if params.has("maxDist") and not params.has("maxDistEnabled"):
        _add(
            diagnostics,
            "missing_task_parameter",
            "error",
            f"{path}.maxDistEnabled",
        )
    if params.get("maxDistEnabled") is True and not params.has("maxDist"):
        _add(
            diagnostics,
            "missing_task_parameter",
            "error",
            f"{path}.maxDist",
        )


def _check_engage_targets_in_zone_params(
    params: LuaTable,
    *,
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "targetTypes": lambda value: isinstance(value, LuaTable),
        "priority": _is_finite_number,
        "x": _is_finite_number,
        "y": _is_finite_number,
        "zoneRadius": _is_positive_finite_number,
        "noTargetTypes": lambda value: isinstance(value, LuaTable),
        "value": lambda value: isinstance(value, str),
    }
    required = {"targetTypes", "x", "y", "zoneRadius"}
    complete_required: set[str] = set()
    if profile == "complete_scenario":
        required.add("priority")
        complete_required.add("priority")
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=complete_required,
        path=path,
        diagnostics=diagnostics,
    )
    target_types = values.get("targetTypes")
    if isinstance(target_types, LuaTable):
        _check_string_sequence(
            target_types,
            allow_empty=False,
            code="invalid_task_target_types",
            path=f"{path}.targetTypes",
            diagnostics=diagnostics,
        )
    no_target_types = values.get("noTargetTypes")
    if isinstance(no_target_types, LuaTable):
        _check_string_sequence(
            no_target_types,
            allow_empty=True,
            code="invalid_task_no_target_types",
            path=f"{path}.noTargetTypes",
            diagnostics=diagnostics,
        )


def _check_escort_params(
    params: LuaTable,
    *,
    source: dict[str, Any],
    groups_by_id: dict[int | float, dict[str, Any]],
    profile: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    specs = {
        "engagementDistMax": _is_positive_finite_number,
        "groupId": _is_positive_integer_number,
        "lastWptIndex": _is_positive_integer_number,
        "lastWptIndexFlag": lambda value: isinstance(value, bool),
        "lastWptIndexFlagChangedManually": (lambda value: isinstance(value, bool)),
        "pos": lambda value: isinstance(value, LuaTable),
        "targetTypes": lambda value: isinstance(value, LuaTable),
        "noTargetTypes": lambda value: isinstance(value, LuaTable),
        "value": lambda value: isinstance(value, str),
        "x": _is_finite_number,
        "y": _is_finite_number,
    }
    required = {
        "engagementDistMax",
        "groupId",
        "lastWptIndex",
        "pos",
        "targetTypes",
    }
    complete_required: set[str] = set()
    if profile == "complete_scenario":
        complete_required = {
            "lastWptIndexFlag",
            "lastWptIndexFlagChangedManually",
        }
        required.update(complete_required)
    values = _check_task_parameters(
        params,
        specs=specs,
        required=required,
        complete_required=complete_required,
        path=path,
        diagnostics=diagnostics,
    )
    target_types = values.get("targetTypes")
    if isinstance(target_types, LuaTable):
        _check_string_sequence(
            target_types,
            allow_empty=False,
            code="invalid_task_target_types",
            path=f"{path}.targetTypes",
            diagnostics=diagnostics,
        )
    no_target_types = values.get("noTargetTypes")
    if isinstance(no_target_types, LuaTable):
        _check_string_sequence(
            no_target_types,
            allow_empty=True,
            code="invalid_task_no_target_types",
            path=f"{path}.noTargetTypes",
            diagnostics=diagnostics,
        )
    position = values.get("pos")
    if isinstance(position, LuaTable):
        _check_task_parameters(
            position,
            specs={
                "x": _is_finite_number,
                "y": _is_finite_number,
                "z": _is_finite_number,
            },
            required={"x", "y", "z"},
            complete_required=set(),
            path=f"{path}.pos",
            diagnostics=diagnostics,
        )
    group_id = values.get("groupId")
    if not _is_positive_integer_number(group_id):
        return
    if group_id == source["group_id"]:
        _add(
            diagnostics,
            "escort_target_is_source_group",
            "error",
            f"{path}.groupId",
        )
    target = groups_by_id.get(group_id)
    if target is None:
        _add(
            diagnostics,
            "task_target_group_not_found",
            "error",
            f"{path}.groupId",
        )
        return
    if target["side"] != source["side"]:
        _add(
            diagnostics,
            "escort_target_not_friendly",
            "error",
            f"{path}.groupId",
        )
    if target["category"] != "plane":
        _add(
            diagnostics,
            "escort_target_not_plane",
            "error",
            f"{path}.groupId",
        )
    last_waypoint = values.get("lastWptIndex")
    if _is_positive_integer_number(last_waypoint) and last_waypoint > len(
        target["points"].numeric_items()
    ):
        _add(
            diagnostics,
            "escort_last_waypoint_out_of_range",
            "error",
            f"{path}.lastWptIndex",
        )


def _check_task_parameters(
    params: LuaTable,
    *,
    specs: dict[str, Any],
    required: set[str],
    complete_required: set[str],
    path: str,
    diagnostics: list[dict[str, str]],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, check in specs.items():
        if not params.has(name):
            if name in required:
                _add(
                    diagnostics,
                    (
                        "complete_missing_task_parameter"
                        if name in complete_required
                        else "missing_task_parameter"
                    ),
                    "error",
                    f"{path}.{name}",
                )
            continue
        value = params.get(name)
        values[name] = value
        if not check(value):
            _add(
                diagnostics,
                "invalid_task_parameter",
                "error",
                f"{path}.{name}",
            )
    return values


def _check_string_sequence(
    value: LuaTable,
    *,
    allow_empty: bool,
    code: str,
    path: str,
    diagnostics: list[dict[str, str]],
) -> None:
    keys = sorted(field.key for field in value.fields if _is_positive_int(field.key))
    dense = len(keys) == len(value.fields) and keys == list(range(1, len(keys) + 1))
    strings = all(
        isinstance(field.value, str) and bool(field.value) for field in value.fields
    )
    if (not allow_empty and not value.fields) or not dense or not strings:
        _add(diagnostics, code, "error", path)


def _check_gci_structure(
    mission: LuaTable,
    diagnostics: list[dict[str, str]],
) -> None:
    units: list[dict[str, Any]] = []
    task_roots: list[tuple[LuaTable, str]] = []
    coalition = mission.get("coalition")
    if not isinstance(coalition, LuaTable):
        return
    for side_field in coalition.fields:
        side = side_field.value
        if not isinstance(side, LuaTable):
            continue
        countries = side.get("country")
        if not isinstance(countries, LuaTable):
            continue
        for country_field in countries.numeric_items():
            country = country_field.value
            if not isinstance(country, LuaTable):
                continue
            country_path = f"$.coalition.{side_field.key}.country[{country_field.key}]"
            for category in CATEGORIES:
                category_table = country.get(category)
                if not isinstance(category_table, LuaTable):
                    continue
                groups = category_table.get("group")
                if not isinstance(groups, LuaTable):
                    continue
                for group_field in groups.numeric_items():
                    group = group_field.value
                    if not isinstance(group, LuaTable):
                        continue
                    group_path = f"{country_path}.{category}.group[{group_field.key}]"
                    for unit_index, unit in enumerate(
                        _numeric_tables(group.get("units")),
                        start=1,
                    ):
                        units.append(
                            {
                                "side": str(side_field.key),
                                "category": category,
                                "path": (f"{group_path}.units[{unit_index}]"),
                                "unit_id": unit.get("unitId"),
                                "unit_type": unit.get("type"),
                                "x": unit.get("x"),
                                "y": unit.get("y"),
                            }
                        )
                    route = group.get("route")
                    points = (
                        _numeric_tables(route.get("points"))
                        if isinstance(route, LuaTable)
                        else []
                    )
                    for point_index, point in enumerate(points, start=1):
                        task = point.get("task")
                        if isinstance(task, LuaTable):
                            task_roots.append(
                                (
                                    task,
                                    (f"{group_path}.route.points[{point_index}].task"),
                                )
                            )

    stations = [unit for unit in units if unit["unit_type"] == GCI_STATION_TYPE]
    actions: list[dict[str, Any]] = []
    for task, path in task_roots:
        _collect_task_nodes(
            task,
            path=path,
            chain=(),
            output=actions,
        )
    actions = [
        action for action in actions if action["node"].get("id") == GCI_ACTION_ID
    ]
    if not stations and not actions:
        return

    station_by_id = {
        station["unit_id"]: station
        for station in stations
        if _is_number(station["unit_id"])
    }
    activated_station_ids: set[int | float] = set()
    for action in actions:
        node = action["node"]
        path = action["path"]
        chain = action["chain"]
        if tuple(chain[-3:]) != (
            "ComboTask",
            "WrappedAction",
            GCI_ACTION_ID,
        ):
            _add(
                diagnostics,
                "invalid_gci_task_chain",
                "error",
                path,
            )
        params = node.get("params")
        if not isinstance(params, LuaTable):
            _add(
                diagnostics,
                "missing_gci_action_params",
                "error",
                f"{path}.params",
            )
            continue
        unit_id = params.get("unitId")
        station = station_by_id.get(unit_id)
        if station is None:
            _add(
                diagnostics,
                "gci_action_not_linked_to_station",
                "error",
                f"{path}.params.unitId",
            )
            continue
        activated_station_ids.add(unit_id)
        if station["category"] != "vehicle":
            _add(
                diagnostics,
                "gci_station_not_vehicle",
                "error",
                station["path"],
            )
        channel = params.get("channel")
        if not _is_positive_int(channel):
            _add(
                diagnostics,
                "invalid_gci_channel",
                "error",
                f"{path}.params.channel",
            )
        radius = params.get("radius")
        if not _is_finite_number(radius) or radius <= 0:
            _add(
                diagnostics,
                "invalid_gci_responsibility_radius",
                "error",
                f"{path}.params.radius",
            )
        for coordinate in ("x", "y"):
            if not _is_finite_number(params.get(coordinate)):
                _add(
                    diagnostics,
                    "invalid_gci_responsibility_coordinate",
                    "error",
                    f"{path}.params.{coordinate}",
                )

        linked_radars = [
            unit
            for unit in units
            if (
                unit["side"] == station["side"]
                and unit["unit_type"] in GCI_COMPATIBLE_RADARS
                and _unit_distance(station, unit) <= GCI_RADAR_LINK_RADIUS_METERS
            )
        ]
        if not linked_radars:
            _add(
                diagnostics,
                "gci_no_compatible_radar_in_link_range",
                "error",
                path,
            )

    for station in stations:
        unit_id = station["unit_id"]
        if _is_number(unit_id) and unit_id not in activated_station_ids:
            _add(
                diagnostics,
                "gci_station_not_activated",
                "error",
                station["path"],
            )


def _collect_task_nodes(
    value: LuaTable,
    *,
    path: str,
    chain: tuple[str, ...],
    output: list[dict[str, Any]],
) -> None:
    task_id = value.get("id")
    next_chain = (*chain, task_id) if isinstance(task_id, str) else chain
    output.append(
        {
            "node": value,
            "path": path,
            "chain": next_chain,
        }
    )
    for field in value.fields:
        if isinstance(field.value, LuaTable):
            _collect_task_nodes(
                field.value,
                path=f"{path}.{field.key}",
                chain=next_chain,
                output=output,
            )


def _unit_distance(
    left: dict[str, Any],
    right: dict[str, Any],
) -> float:
    values = tuple(
        _finite_float(value) for value in (left["x"], left["y"], right["x"], right["y"])
    )
    if any(value is None for value in values):
        return math.inf
    left_x, left_y, right_x, right_y = values
    assert left_x is not None
    assert left_y is not None
    assert right_x is not None
    assert right_y is not None
    return math.hypot(right_x - left_x, right_y - left_y)


def _check_logic_structure(
    mission: LuaTable,
    *,
    group_ids: set[int | float],
    unit_ids: set[int | float],
    dictionary: LuaTable | None,
    diagnostics: list[dict[str, str]],
) -> None:
    triggers = mission.get("triggers")
    zone_ids: set[int | float] = set()
    if isinstance(triggers, LuaTable):
        for field_name in _MISPLACED_LOGIC_FIELDS:
            if triggers.has(field_name):
                _add(
                    diagnostics,
                    "misplaced_mission_logic_field",
                    "error",
                    f"$.triggers.{field_name}",
                )
        for index, zone in enumerate(
            _numeric_tables(triggers.get("zones")),
            start=1,
        ):
            zone_id = zone.get("zoneId")
            if not _is_number(zone_id):
                continue
            if zone_id in zone_ids:
                _add(
                    diagnostics,
                    "duplicate_trigger_zone_id",
                    "error",
                    f"$.triggers.zones[{index}].zoneId",
                )
            zone_ids.add(zone_id)

    rules = _numeric_tables(mission.get("trigrules"))
    for index, rule in enumerate(rules, start=1):
        path = f"$.trigrules[{index}]"
        predicate = rule.get("predicate")
        if predicate not in _TRIGGER_PREDICATES:
            _add(
                diagnostics,
                "invalid_trigger_rule_predicate",
                "error",
                f"{path}.predicate",
            )
        if not isinstance(rule.get("eventlist"), str):
            _add(
                diagnostics,
                "invalid_trigger_eventlist",
                "error",
                f"{path}.eventlist",
            )
        if not isinstance(rule.get("comment"), str):
            _add(
                diagnostics,
                "invalid_trigger_comment",
                "error",
                f"{path}.comment",
            )
        conditions = _logic_items(
            rule.get("rules"),
            path=f"{path}.rules",
            prefix="c_",
            diagnostics=diagnostics,
        )
        actions = _logic_items(
            rule.get("actions"),
            path=f"{path}.actions",
            prefix="a_",
            diagnostics=diagnostics,
        )
        if predicate != "triggerStart" and not conditions:
            _add(
                diagnostics,
                "trigger_rule_has_no_conditions",
                "warning",
                f"{path}.rules",
            )
        if not actions:
            _add(
                diagnostics,
                "trigger_rule_has_no_actions",
                "error",
                f"{path}.actions",
            )
        for condition_index, condition in enumerate(conditions, start=1):
            _check_logic_references(
                condition,
                path=f"{path}.rules[{condition_index}]",
                group_ids=group_ids,
                unit_ids=unit_ids,
                zone_ids=zone_ids,
                dictionary=dictionary,
                diagnostics=diagnostics,
            )
        for action_index, action in enumerate(actions, start=1):
            _check_logic_references(
                action,
                path=f"{path}.actions[{action_index}]",
                group_ids=group_ids,
                unit_ids=unit_ids,
                zone_ids=zone_ids,
                dictionary=dictionary,
                diagnostics=diagnostics,
            )

    if rules:
        trig = mission.get("trig")
        if not isinstance(trig, LuaTable):
            _add(
                diagnostics,
                "missing_compiled_trigger_table",
                "error",
                "$.trig",
            )
        else:
            for field_name in (
                "conditions",
                "actions",
                "func",
                "funcStartup",
                "customStartup",
                "events",
                "flag",
            ):
                if not isinstance(trig.get(field_name), LuaTable):
                    _add(
                        diagnostics,
                        "missing_compiled_trigger_field",
                        "error",
                        f"$.trig.{field_name}",
                    )
            _check_compiled_strings(
                trig.get("conditions"),
                path="$.trig.conditions",
                expected=len(rules),
                diagnostics=diagnostics,
            )
            _check_compiled_strings(
                trig.get("actions"),
                path="$.trig.actions",
                expected=len(rules),
                diagnostics=diagnostics,
            )

    goals_value = mission.get("goals")
    goal_fields = (
        tuple(
            field
            for field in goals_value.numeric_items()
            if isinstance(field.value, LuaTable)
        )
        if isinstance(goals_value, LuaTable)
        else ()
    )
    goals = [field.value for field in goal_fields]
    side_keys: dict[str, set[int]] = {side: set() for side in _GOAL_SIDES}
    for goal_field in goal_fields:
        goal = goal_field.value
        path = f"$.goals[{goal_field.key}]"
        diagnostic_start = len(diagnostics)
        side = goal.get("side")
        if side not in _GOAL_SIDES:
            _add(
                diagnostics,
                "invalid_goal_side",
                "error",
                f"{path}.side",
            )
        if goal.get("predicate") != "score":
            _add(
                diagnostics,
                "invalid_goal_predicate",
                "error",
                f"{path}.predicate",
            )
        if not _is_number(goal.get("score")):
            _add(
                diagnostics,
                "invalid_goal_score",
                "error",
                f"{path}.score",
            )
        if not isinstance(goal.get("comment"), str):
            _add(
                diagnostics,
                "invalid_goal_comment",
                "error",
                f"{path}.comment",
            )
        conditions = _logic_items(
            goal.get("rules"),
            path=f"{path}.rules",
            prefix="c_",
            diagnostics=diagnostics,
        )
        if not conditions:
            _add(
                diagnostics,
                "goal_has_no_conditions",
                "error",
                f"{path}.rules",
            )
        for condition_index, condition in enumerate(conditions, start=1):
            _check_logic_references(
                condition,
                path=f"{path}.rules[{condition_index}]",
                group_ids=group_ids,
                unit_ids=unit_ids,
                zone_ids=zone_ids,
                dictionary=dictionary,
                diagnostics=diagnostics,
            )
        new_errors = any(
            item["severity"] == "error" for item in diagnostics[diagnostic_start:]
        )
        if (
            side in _GOAL_SIDES
            and conditions
            and not new_errors
            and _is_positive_int(goal_field.key)
        ):
            side_keys[side].add(goal_field.key)

    if goals:
        result = mission.get("result")
        if not isinstance(result, LuaTable):
            _add(
                diagnostics,
                "missing_compiled_goal_result",
                "error",
                "$.result",
            )
        else:
            if result.get("total") != len(goals):
                _add(
                    diagnostics,
                    "compiled_goal_total_mismatch",
                    "error",
                    "$.result.total",
                )
            for side in ("RED", "BLUE", "OFFLINE"):
                side_path = f"$.result.{side.lower()}"
                side_result = result.get(side.lower())
                if not isinstance(side_result, LuaTable):
                    _add(
                        diagnostics,
                        "missing_compiled_goal_side",
                        "error",
                        side_path,
                    )
                    continue
                expected_keys = side_keys[side]
                for field_name in ("conditions", "actions", "func"):
                    _check_compiled_goal_strings(
                        side_result.get(field_name),
                        path=f"{side_path}.{field_name}",
                        expected_keys=expected_keys,
                        diagnostics=diagnostics,
                    )


def _logic_items(
    value: Any,
    *,
    path: str,
    prefix: str,
    diagnostics: list[dict[str, str]],
) -> list[LuaTable]:
    if not isinstance(value, LuaTable):
        _add(diagnostics, "invalid_logic_sequence", "error", path)
        return []
    result = _numeric_tables(value)
    for index, item in enumerate(result, start=1):
        predicate = item.get("predicate")
        valid = isinstance(predicate, str) and (
            predicate.startswith(prefix) or predicate == "or"
        )
        if not valid:
            _add(
                diagnostics,
                "invalid_logic_item_predicate",
                "error",
                f"{path}[{index}].predicate",
            )
    return result


def _check_logic_references(
    item: LuaTable,
    *,
    path: str,
    group_ids: set[int | float],
    unit_ids: set[int | float],
    zone_ids: set[int | float],
    dictionary: LuaTable | None,
    diagnostics: list[dict[str, str]],
) -> None:
    predicate = item.get("predicate")
    reference: tuple[str, set[int | float]] | None = None
    if predicate in {"c_unit_dead", "c_unit_in_zone"}:
        reference = ("unit", unit_ids)
    elif predicate in {
        "c_group_dead",
        "c_part_of_group_in_zone",
        "a_activate_group",
    }:
        reference = ("group", group_ids)
    if reference is not None:
        field_name, identifiers = reference
        value = item.get(field_name)
        if not _is_number(value) or value not in identifiers:
            _add(
                diagnostics,
                f"unknown_logic_{field_name}_reference",
                "error",
                f"{path}.{field_name}",
            )
    if predicate in {"c_unit_in_zone", "c_part_of_group_in_zone"}:
        zone = item.get("zone")
        if not _is_number(zone) or zone not in zone_ids:
            _add(
                diagnostics,
                "unknown_logic_zone_reference",
                "error",
                f"{path}.zone",
            )
    if predicate == "a_out_text_delay":
        _check_out_text_action(
            item,
            path=path,
            dictionary=dictionary,
            diagnostics=diagnostics,
        )


def _check_out_text_action(
    item: LuaTable,
    *,
    path: str,
    dictionary: LuaTable | None,
    diagnostics: list[dict[str, str]],
) -> None:
    key = item.get("KeyDict_text")
    if not isinstance(key, str) or not key or item.get("text") != key:
        _add(
            diagnostics,
            "invalid_out_text_dictionary_key",
            "error",
            f"{path}.KeyDict_text",
        )
        return
    for field_name in ("seconds", "start_delay"):
        value = item.get(field_name)
        if not _is_number(value) or value < 0:
            _add(
                diagnostics,
                "invalid_out_text_timing",
                "error",
                f"{path}.{field_name}",
            )
    if not isinstance(item.get("clearview"), bool):
        _add(
            diagnostics,
            "invalid_out_text_clearview",
            "error",
            f"{path}.clearview",
        )
    if dictionary is None:
        _add(
            diagnostics,
            "out_text_dictionary_not_supplied",
            "warning",
            f"{path}.KeyDict_text",
        )
        return
    if not dictionary.has(key):
        _add(
            diagnostics,
            "unresolved_out_text_dictionary_key",
            "error",
            f"{path}.KeyDict_text",
        )
        return
    text = dictionary.get(key)
    if not isinstance(text, str) or not text.strip():
        _add(
            diagnostics,
            "invalid_out_text_dictionary_value",
            "error",
            f"{path}.KeyDict_text",
        )


def _check_compiled_strings(
    value: Any,
    *,
    path: str,
    expected: int,
    diagnostics: list[dict[str, str]],
) -> None:
    if not isinstance(value, LuaTable):
        _add(diagnostics, "invalid_compiled_logic_table", "error", path)
        return
    _check_sequence(
        value,
        path,
        diagnostics,
        table_items=False,
    )
    fields = value.numeric_items()
    if len(fields) != expected:
        _add(
            diagnostics,
            "compiled_logic_count_mismatch",
            "error",
            path,
        )
    for field in fields:
        if not isinstance(field.value, str) or not field.value.strip():
            _add(
                diagnostics,
                "invalid_compiled_logic_string",
                "error",
                f"{path}[{field.key}]",
            )


def _check_compiled_goal_strings(
    value: Any,
    *,
    path: str,
    expected_keys: set[int],
    diagnostics: list[dict[str, str]],
) -> None:
    if not isinstance(value, LuaTable):
        _add(diagnostics, "invalid_compiled_logic_table", "error", path)
        return
    _check_sequence(
        value,
        path,
        diagnostics,
        table_items=False,
        dense=False,
    )
    fields = value.numeric_items()
    actual_keys = [field.key for field in fields]
    if len(actual_keys) != len(expected_keys) or set(actual_keys) != expected_keys:
        _add(
            diagnostics,
            "compiled_goal_key_mismatch",
            "error",
            path,
        )
    for field in fields:
        if not isinstance(field.value, str) or not field.value.strip():
            _add(
                diagnostics,
                "invalid_compiled_logic_string",
                "error",
                f"{path}[{field.key}]",
            )


def _check_late_activation_links(
    mission: LuaTable,
    late_group_paths: dict[int | float, str],
    diagnostics: list[dict[str, str]],
) -> None:
    activation_targets: set[int | float] = set()
    for rule in _numeric_tables(mission.get("trigrules")):
        for action in _numeric_tables(rule.get("actions")):
            if action.get("predicate") != "a_activate_group":
                continue
            target = action.get("group")
            if not _is_number(target):
                target = action.get("groupId")
            if _is_number(target):
                activation_targets.add(target)
    for group_id, path in late_group_paths.items():
        if group_id not in activation_targets:
            _add(
                diagnostics,
                "late_activation_not_statically_linked",
                "warning",
                f"{path}.lateActivation",
            )


def _check_sequence(
    value: Any,
    path: str,
    diagnostics: list[dict[str, str]],
    *,
    table_items: bool,
    dense: bool = True,
) -> None:
    if value is None:
        return
    if not isinstance(value, LuaTable):
        _add(
            diagnostics,
            "invalid_sequence_table",
            "error",
            path,
        )
        return
    for field in value.fields:
        item_path = f"{path}[{field.key!r}]"
        if not _is_positive_int(field.key):
            _add(
                diagnostics,
                "nonnumeric_sequence_key",
                "error",
                item_path,
            )
        if table_items and not isinstance(field.value, LuaTable):
            _add(
                diagnostics,
                "invalid_sequence_item",
                "error",
                item_path,
            )
    if dense and not _is_dense_sequence(value, table_items=table_items):
        if all(_is_positive_int(field.key) for field in value.fields):
            _add(
                diagnostics,
                "noncontiguous_sequence_keys",
                "error",
                path,
            )


def _is_dense_sequence(
    value: LuaTable,
    *,
    table_items: bool,
) -> bool:
    keys = sorted(field.key for field in value.fields if _is_positive_int(field.key))
    if len(keys) != len(value.fields):
        return False
    if keys != list(range(1, len(keys) + 1)):
        return False
    return not table_items or all(
        isinstance(field.value, LuaTable) for field in value.fields
    )


def _numeric_tables(value: Any) -> list[LuaTable]:
    if not isinstance(value, LuaTable):
        return []
    return [
        field.value
        for field in value.numeric_items()
        if isinstance(field.value, LuaTable)
    ]


def _add(
    diagnostics: list[dict[str, str]],
    code: str,
    severity: str,
    path: str,
) -> None:
    diagnostics.append(
        {
            "code": code,
            "severity": severity,
            "path": path,
        }
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _finite_float(value) is not None


def _finite_float(value: Any) -> float | None:
    if not _is_number(value):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _is_positive_finite_number(value: Any) -> bool:
    return _is_finite_number(value) and value > 0


def _is_positive_integer_number(value: Any) -> bool:
    return (
        _is_finite_number(value)
        and value > 0
        and (isinstance(value, int) or value.is_integer())
    )


def _is_nonnegative_integer_number(value: Any) -> bool:
    return (
        _is_finite_number(value)
        and value >= 0
        and (isinstance(value, int) or value.is_integer())
    )


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_parking_token(value: Any) -> bool:
    return _is_number(value) or isinstance(value, str) and bool(value.strip())


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
