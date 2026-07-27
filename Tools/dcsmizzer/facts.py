"""Reusable anonymous mission facts and build-contract evaluation."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .lua import LuaTable
from .mission import MissionStats


CATEGORIES: tuple[str, ...] = (
    "plane",
    "helicopter",
    "vehicle",
    "ship",
    "static",
)
BRIEFING_FIELDS: tuple[str, ...] = (
    "sortie",
    "descriptionText",
    "descriptionBlueTask",
    "descriptionRedTask",
    "descriptionNeutralsTask",
)
_DCS_PREDICATE = re.compile(r"\b(?P<name>[ac]_[A-Za-z][A-Za-z0-9_]*)\b")
COUNTER_FACTS: frozenset[str] = frozenset(
    {
        "groups",
        "units",
        "human_slots",
        "unit_types",
        "slots_by_type",
        "payload_clsids",
        "waypoint_actions",
        "waypoint_task_ids",
        "group_tasks",
        "start_modes",
        "trigger_condition_predicates",
        "trigger_action_predicates",
        "goal_predicates",
    }
)
SCALAR_FACTS: frozenset[str] = frozenset(
    {
        "pylon_assignments",
        "trigger_rules",
        "trigger_conditions",
        "trigger_actions",
        "goals",
        "dictionary_entries",
        "resource_mappings",
        "briefing_characters",
        "missing_resource_members",
        "referenced_missing_resources",
        "latest_waypoint_eta_seconds",
        "max_route_span_seconds",
    }
)
REQUIRED_FACTS: frozenset[str] = frozenset(
    {
        "unit_types",
        "payload_clsids",
        "waypoint_actions",
        "waypoint_task_ids",
        "group_tasks",
        "start_modes",
        "airdrome_ids",
        "briefing_fields",
        "trigger_condition_predicates",
        "trigger_action_predicates",
        "goal_predicates",
    }
)
ROLE_FIELDS = frozenset(
    {
        "role",
        "group_id",
        "side",
        "category",
        "group_task",
        "unit_types",
        "human_slots",
        "start_mode",
        "airdrome_id",
        "late_activation",
        "minimum_waypoints",
        "minimum_route_span_seconds",
        "required_waypoint_task_ids",
        "required_waypoint_actions",
        "required_task_group_ids",
    }
)
ROLE_OPTIONAL_FIELDS = frozenset(
    {
        "helipad_id",
        "link_unit",
        "mission_elapsed_start_seconds",
    }
)
START_MODE_PAIRS: dict[tuple[str, str], str] = {
    ("TakeOffParking", "From Parking Area"): "cold_parking",
    ("TakeOffParkingHot", "From Parking Area Hot"): "hot_parking",
    ("TakeOff", "From Runway"): "runway",
    ("TakeOffGround", "From Ground Area"): "cold_ground",
    ("TakeOffGroundHot", "From Ground Area Hot"): "hot_ground",
    ("Turning Point", "Turning Point"): "air",
    ("Turning Point", "Fly Over Point"): "air",
}
START_MODES = frozenset({*START_MODE_PAIRS.values(), "other"})
_START_MODE_TYPES = frozenset(point_type for point_type, _action in START_MODE_PAIRS)
_START_MODE_ACTIONS = frozenset(action for _point_type, action in START_MODE_PAIRS)
_MISSING = object()


def collect_mission_facts(
    mission: LuaTable,
    *,
    dictionary: LuaTable | None = None,
    stats: MissionStats | None = None,
) -> dict[str, Any]:
    """Collect identifiers and counts without names, text, or source paths."""

    counters = {name: Counter() for name in COUNTER_FACTS}
    airdrome_ids: set[int | float] = set()
    resolved_briefing_fields: set[str] = set()
    latest_waypoint_eta_seconds: int | float = 0
    max_route_span_seconds: int | float = 0
    groups_by_id: dict[int | float, dict[str, Any]] = {}

    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country_value in numeric_values(side.get("country")):
            country = table(country_value)
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group_value in numeric_values(category_table.get("group")):
                    group = table(group_value)
                    counters["groups"][category] += 1
                    group_task = group.get("task")
                    if isinstance(group_task, str):
                        counters["group_tasks"][group_task] += 1

                    points = numeric_tables(table(group.get("route")).get("points"))
                    role_task_ids: Counter[str] = Counter()
                    role_waypoint_actions: set[str] = set()
                    role_task_group_ids: set[int | float] = set()
                    if points:
                        mode = classify_start_mode(points[0])
                        counters["start_modes"][mode] += 1
                    else:
                        mode = "other"
                    point_etas = [
                        point.get("ETA")
                        for point in points
                        if _is_number(point.get("ETA"))
                    ]
                    if point_etas:
                        max_route_span_seconds = max(
                            max_route_span_seconds,
                            max(point_etas) - min(point_etas),
                        )
                    for point in points:
                        eta = point.get("ETA")
                        if _is_number(eta):
                            latest_waypoint_eta_seconds = max(
                                latest_waypoint_eta_seconds,
                                eta,
                            )
                        action = point.get("action")
                        if isinstance(action, str):
                            counters["waypoint_actions"][action] += 1
                            role_waypoint_actions.add(action)
                        airdrome_id = point.get("airdromeId")
                        if _is_number(airdrome_id):
                            airdrome_ids.add(airdrome_id)
                        _collect_task_ids(
                            point.get("task"),
                            counters["waypoint_task_ids"],
                        )
                        _collect_task_ids(
                            point.get("task"),
                            role_task_ids,
                        )
                        _collect_task_group_ids(
                            point.get("task"),
                            role_task_group_ids,
                        )

                    role_unit_types: Counter[str] = Counter()
                    role_human_slots: Counter[str] = Counter()
                    for unit_value in numeric_values(group.get("units")):
                        unit = table(unit_value)
                        counters["units"][category] += 1
                        unit_type = unit.get("type")
                        if isinstance(unit_type, str):
                            counters["unit_types"][unit_type] += 1
                            role_unit_types[unit_type] += 1
                        skill = unit.get("skill")
                        if (
                            category in {"plane", "helicopter"}
                            and isinstance(skill, str)
                            and skill in {"Player", "Client"}
                        ):
                            counters["human_slots"][skill] += 1
                            role_human_slots[skill] += 1
                            if isinstance(unit_type, str):
                                counters["slots_by_type"][unit_type] += 1
                        for pylon in numeric_tables(
                            table(unit.get("payload")).get("pylons")
                        ):
                            clsid = pylon.get("CLSID")
                            if isinstance(clsid, str):
                                counters["payload_clsids"][clsid] += 1
                    group_id = group.get("groupId")
                    if _is_number(group_id):
                        first_airdrome = points[0].get("airdromeId") if points else None
                        first_helipad = points[0].get("helipadId") if points else None
                        first_link_unit = points[0].get("linkUnit") if points else None
                        groups_by_id[group_id] = {
                            "side": str(side_field.key),
                            "category": category,
                            "group_task": group_task,
                            "unit_types": dict(role_unit_types),
                            "human_slots": {
                                "Player": role_human_slots.get("Player", 0),
                                "Client": role_human_slots.get("Client", 0),
                            },
                            "start_mode": mode,
                            "airdrome_id": (
                                first_airdrome if _is_number(first_airdrome) else None
                            ),
                            "helipad_id": (
                                first_helipad if _is_number(first_helipad) else None
                            ),
                            "link_unit": (
                                first_link_unit if _is_number(first_link_unit) else None
                            ),
                            "late_activation": (group.get("lateActivation") is True),
                            "mission_elapsed_start_seconds": (
                                group.get("start_time")
                                if _is_number(group.get("start_time"))
                                else None
                            ),
                            "waypoints": len(points),
                            "route_span_seconds": (
                                max(point_etas) - min(point_etas) if point_etas else 0
                            ),
                            "waypoint_task_ids": set(role_task_ids),
                            "waypoint_actions": role_waypoint_actions,
                            "task_group_ids": role_task_group_ids,
                        }

    for rule in numeric_tables(mission.get("trigrules")):
        for condition in numeric_tables(rule.get("rules")):
            _collect_predicate_names(
                condition.get("predicate"),
                counters["trigger_condition_predicates"],
            )
        for action in numeric_tables(rule.get("actions")):
            _collect_predicate_names(
                action.get("predicate"),
                counters["trigger_action_predicates"],
            )
    for goal in numeric_tables(mission.get("goals")):
        _collect_predicate_names(
            goal.get("predicate"),
            counters["goal_predicates"],
        )
        for condition in numeric_tables(goal.get("rules")):
            _collect_predicate_names(
                condition.get("predicate"),
                counters["goal_predicates"],
            )

    if dictionary is not None:
        for field_name in BRIEFING_FIELDS:
            dictionary_key = mission.get(field_name)
            if not isinstance(dictionary_key, str):
                continue
            text = dictionary.get(dictionary_key)
            if isinstance(text, str) and text.strip():
                resolved_briefing_fields.add(field_name)

    selected_stats = stats or MissionStats()
    scalars = {
        "pylon_assignments": selected_stats.pylon_assignments,
        "trigger_rules": selected_stats.trigger_rules,
        "trigger_conditions": selected_stats.trigger_conditions,
        "trigger_actions": selected_stats.trigger_actions,
        "goals": selected_stats.goals,
        "dictionary_entries": selected_stats.dictionary_entries,
        "resource_mappings": selected_stats.resource_mappings,
        "briefing_characters": selected_stats.briefing_characters,
        "missing_resource_members": selected_stats.missing_resource_members,
        "referenced_missing_resources": (selected_stats.referenced_missing_resources),
        "latest_waypoint_eta_seconds": latest_waypoint_eta_seconds,
        "max_route_span_seconds": max_route_span_seconds,
    }
    return {
        "theatre": mission.get("theatre"),
        "mission_version": mission.get("version"),
        "counters": counters,
        "scalars": scalars,
        "sets": {
            "airdrome_ids": airdrome_ids,
            "briefing_fields": resolved_briefing_fields,
            **{
                name: set(counter)
                for name, counter in counters.items()
                if name in REQUIRED_FACTS
            },
        },
        "_mission": mission,
        "_groups_by_id": groups_by_id,
    }


def evaluate_expectations(
    expectations: dict[str, Any],
    facts: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    """Evaluate the finite build-contract vocabulary."""

    validate_expectations(expectations)
    checks: list[dict[str, Any]] = []
    for name in ("theatre", "mission_version"):
        if name not in expectations:
            continue
        expected = expectations[name]
        actual = facts[name]
        checks.append(
            {
                "id": name,
                "operator": "equals",
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )

    for operator in ("minimum", "exact"):
        section = expectations.get(operator, {})
        for fact_name, expected in section.items():
            if fact_name in COUNTER_FACTS:
                actual_counter = facts["counters"][fact_name]
                for key, expected_count in expected.items():
                    actual_count = actual_counter.get(key, 0)
                    passed = (
                        actual_count >= expected_count
                        if operator == "minimum"
                        else actual_count == expected_count
                    )
                    checks.append(
                        {
                            "id": f"{operator}.{fact_name}.{key}",
                            "operator": "at_least"
                            if operator == "minimum"
                            else "equals",
                            "expected": expected_count,
                            "actual": actual_count,
                            "passed": passed,
                        }
                    )
            else:
                actual_value = facts["scalars"][fact_name]
                passed = (
                    actual_value >= expected
                    if operator == "minimum"
                    else actual_value == expected
                )
                checks.append(
                    {
                        "id": f"{operator}.{fact_name}",
                        "operator": "at_least" if operator == "minimum" else "equals",
                        "expected": expected,
                        "actual": actual_value,
                        "passed": passed,
                    }
                )

    for fact_name, expected_values in expectations.get("required", {}).items():
        actual_values = facts["sets"][fact_name]
        for expected in expected_values:
            passed = expected in actual_values
            checks.append(
                {
                    "id": f"required.{fact_name}.{expected}",
                    "operator": "contains",
                    "expected": expected,
                    "actual": expected if passed else None,
                    "passed": passed,
                }
            )

    mission = facts["_mission"]
    for index, assertion in enumerate(expectations.get("exact_values", [])):
        path = assertion["path"]
        expected = assertion["value"]
        actual = _resolve_path(mission, path)
        found = actual is not _MISSING
        passed = found and _scalar_equal(actual, expected)
        checks.append(
            {
                "id": f"exact_values[{index}].{_display_path(path)}",
                "operator": "equals",
                "expected": expected,
                "actual": actual if _is_scalar(actual) else None,
                "actual_type": (_scalar_type(actual) if found else "missing"),
                "passed": passed,
            }
        )

    for index, role in enumerate(expectations.get("roles", [])):
        actual = facts["_groups_by_id"].get(role["group_id"])
        prefix = f"roles[{index}].{role['role']}"
        checks.append(
            {
                "id": f"{prefix}.group_id",
                "operator": "resolves_unique_group",
                "expected": role["group_id"],
                "actual": role["group_id"] if actual is not None else None,
                "passed": actual is not None,
            }
        )
        if actual is None:
            continue
        for field_name in (
            "side",
            "category",
            "group_task",
            "unit_types",
            "human_slots",
            "start_mode",
            "airdrome_id",
            "late_activation",
        ):
            checks.append(
                {
                    "id": f"{prefix}.{field_name}",
                    "operator": "equals",
                    "expected": role[field_name],
                    "actual": actual[field_name],
                    "passed": actual[field_name] == role[field_name],
                }
            )
        for field_name in sorted(ROLE_OPTIONAL_FIELDS):
            if field_name not in role:
                continue
            checks.append(
                {
                    "id": f"{prefix}.{field_name}",
                    "operator": "equals",
                    "expected": role[field_name],
                    "actual": actual[field_name],
                    "passed": actual[field_name] == role[field_name],
                }
            )
        for field_name, actual_name in (
            ("minimum_waypoints", "waypoints"),
            ("minimum_route_span_seconds", "route_span_seconds"),
        ):
            checks.append(
                {
                    "id": f"{prefix}.{field_name}",
                    "operator": "at_least",
                    "expected": role[field_name],
                    "actual": actual[actual_name],
                    "passed": actual[actual_name] >= role[field_name],
                }
            )
        for field_name, actual_name in (
            ("required_waypoint_task_ids", "waypoint_task_ids"),
            ("required_waypoint_actions", "waypoint_actions"),
            ("required_task_group_ids", "task_group_ids"),
        ):
            for expected in role[field_name]:
                checks.append(
                    {
                        "id": f"{prefix}.{field_name}.{expected}",
                        "operator": "contains",
                        "expected": expected,
                        "actual": expected if expected in actual[actual_name] else None,
                        "passed": expected in actual[actual_name],
                    }
                )

    return checks, all(check["passed"] for check in checks)


def expectation_coverage_warnings(
    expectations: dict[str, Any],
    facts: dict[str, Any],
    *,
    require_role_coverage: bool = False,
) -> list[str]:
    """Identify common post-build facts omitted from the caller contract."""

    warnings: list[str] = []
    minimum = expectations.get("minimum", {})
    exact = expectations.get("exact", {})
    required = expectations.get("required", {})
    exact_paths = {
        tuple(assertion["path"]) for assertion in expectations.get("exact_values", [])
    }

    if "theatre" not in expectations:
        warnings.append("theatre_unasserted")
    if "mission_version" not in expectations:
        warnings.append("mission_version_unasserted")

    mission = facts["_mission"]
    date = mission.get("date")
    if isinstance(date, LuaTable):
        date_paths = {
            ("date", field_name)
            for field_name in ("Year", "Month", "Day")
            if date.has(field_name)
        }
        if not date_paths.issubset(exact_paths):
            warnings.append("date_fields_not_exactly_asserted")
    if mission.has("start_time") and ("start_time",) not in exact_paths:
        warnings.append("start_time_not_exactly_asserted")
    if isinstance(mission.get("weather"), LuaTable) and not any(
        path and path[0] == "weather" for path in exact_paths
    ):
        warnings.append("weather_not_exactly_asserted")

    for fact_name in ("groups", "units", "unit_types"):
        actual = set(facts["counters"][fact_name])
        declared = set(exact.get(fact_name, {}))
        if actual and not actual.issubset(declared):
            warnings.append(f"{fact_name}_not_exactly_asserted")

    if sum(facts["counters"]["human_slots"].values()) > 0:
        if not {"Player", "Client"}.issubset(set(exact.get("human_slots", {}))):
            warnings.append("human_slot_counts_not_exactly_asserted")
        actual_slot_types = set(facts["counters"]["slots_by_type"])
        if not actual_slot_types.issubset(set(exact.get("slots_by_type", {}))):
            warnings.append("human_slot_types_not_exactly_asserted")

    for fact_name in (
        "payload_clsids",
        "waypoint_actions",
        "waypoint_task_ids",
        "group_tasks",
        "start_modes",
        "trigger_condition_predicates",
        "trigger_action_predicates",
        "goal_predicates",
    ):
        actual = set(facts["counters"][fact_name])
        declared = set(required.get(fact_name, []))
        if actual and not actual.issubset(declared):
            warnings.append(f"{fact_name}_not_all_required")

    for fact_name in ("airdrome_ids", "briefing_fields"):
        actual = set(facts["sets"][fact_name])
        declared = set(required.get(fact_name, []))
        if actual and not actual.issubset(declared):
            warnings.append(f"{fact_name}_not_all_required")

    for fact_name in (
        "trigger_rules",
        "trigger_conditions",
        "trigger_actions",
        "goals",
        "latest_waypoint_eta_seconds",
        "max_route_span_seconds",
    ):
        actual = facts["scalars"][fact_name]
        if actual and fact_name not in minimum and fact_name not in exact:
            warnings.append(f"{fact_name}_unasserted")

    for fact_name in (
        "trigger_rules",
        "trigger_conditions",
        "trigger_actions",
        "goals",
    ):
        if facts["scalars"][fact_name] == 0:
            warnings.append(f"{fact_name}_absent")

    for fact_name in (
        "missing_resource_members",
        "referenced_missing_resources",
    ):
        if exact.get(fact_name) != 0:
            warnings.append(f"{fact_name}_zero_not_asserted")

    if require_role_coverage:
        actual_group_ids = set(facts["_groups_by_id"])
        roles = expectations.get("roles", [])
        declared_group_ids = {role["group_id"] for role in roles}
        if actual_group_ids != declared_group_ids:
            warnings.append("groups_not_fully_role_bound")
        if any("mission_elapsed_start_seconds" not in role for role in roles):
            warnings.append("role_elapsed_starts_not_exactly_asserted")

    return warnings


def validate_expectations(expectations: Any) -> None:
    if not isinstance(expectations, dict):
        raise ValueError("expect must be a JSON object")
    allowed_top = {
        "theatre",
        "mission_version",
        "minimum",
        "exact",
        "required",
        "exact_values",
        "roles",
    }
    unknown_top = set(expectations) - allowed_top
    if unknown_top:
        raise ValueError(f"expect contains unknown keys: {sorted(unknown_top)}")
    if "theatre" in expectations and not isinstance(
        expectations["theatre"],
        str,
    ):
        raise ValueError("expect.theatre must be a string")
    if "mission_version" in expectations and not _is_number(
        expectations["mission_version"]
    ):
        raise ValueError("expect.mission_version must be a number")

    for section_name in ("minimum", "exact"):
        section = expectations.get(section_name, {})
        if not isinstance(section, dict):
            raise ValueError(f"expect.{section_name} must be an object")
        unknown = set(section) - COUNTER_FACTS - SCALAR_FACTS
        if unknown:
            raise ValueError(
                f"expect.{section_name} contains unknown facts: {sorted(unknown)}"
            )
        for fact_name, expected in section.items():
            if fact_name in COUNTER_FACTS:
                if not isinstance(expected, dict):
                    raise ValueError(
                        f"expect.{section_name}.{fact_name} must be an object"
                    )
                for key, count in expected.items():
                    if not isinstance(key, str) or not _is_nonnegative_int(count):
                        raise ValueError(
                            f"expect.{section_name}.{fact_name} must map "
                            "strings to nonnegative integers"
                        )
            elif not _is_nonnegative_int(expected):
                raise ValueError(
                    f"expect.{section_name}.{fact_name} must be a nonnegative integer"
                )

    required = expectations.get("required", {})
    if not isinstance(required, dict):
        raise ValueError("expect.required must be an object")
    unknown_required = set(required) - REQUIRED_FACTS
    if unknown_required:
        raise ValueError(
            f"expect.required contains unknown facts: {sorted(unknown_required)}"
        )
    for fact_name, values in required.items():
        if not isinstance(values, list):
            raise ValueError(f"expect.required.{fact_name} must be an array")
        for value in values:
            if fact_name == "airdrome_ids":
                valid = _is_number(value)
            else:
                valid = isinstance(value, str)
            if not valid:
                raise ValueError(
                    f"expect.required.{fact_name} contains an invalid value"
                )

    exact_values = expectations.get("exact_values", [])
    if not isinstance(exact_values, list):
        raise ValueError("expect.exact_values must be an array")
    seen_paths: set[tuple[str | int | float, ...]] = set()
    for index, assertion in enumerate(exact_values):
        prefix = f"expect.exact_values[{index}]"
        if not isinstance(assertion, dict) or set(assertion) != {
            "path",
            "value",
        }:
            raise ValueError(f"{prefix} must contain exactly path and value")
        path = assertion["path"]
        if not isinstance(path, list) or not path:
            raise ValueError(f"{prefix}.path must be a nonempty array")
        normalized: list[str | int | float] = []
        for segment in path:
            if isinstance(segment, str) and segment:
                normalized.append(segment)
            elif _is_number(segment) and not (
                isinstance(segment, float) and not math.isfinite(segment)
            ):
                normalized.append(segment)
            else:
                raise ValueError(f"{prefix}.path contains an invalid segment")
        normalized_path = tuple(normalized)
        if normalized_path in seen_paths:
            raise ValueError(f"{prefix}.path duplicates an earlier path")
        seen_paths.add(normalized_path)
        if not _is_scalar(assertion["value"]):
            raise ValueError(f"{prefix}.value must be a finite scalar")

    roles = expectations.get("roles", [])
    if not isinstance(roles, list):
        raise ValueError("expect.roles must be an array")
    role_names: set[str] = set()
    role_group_ids: set[int | float] = set()
    for index, role in enumerate(roles):
        prefix = f"expect.roles[{index}]"
        role_fields = set(role) if isinstance(role, dict) else set()
        if (
            not isinstance(role, dict)
            or not ROLE_FIELDS.issubset(role_fields)
            or role_fields - ROLE_FIELDS - ROLE_OPTIONAL_FIELDS
        ):
            raise ValueError(
                f"{prefix} must contain required fields "
                f"{sorted(ROLE_FIELDS)} and only optional fields "
                f"{sorted(ROLE_OPTIONAL_FIELDS)}"
            )
        role_name = role["role"]
        if not isinstance(role_name, str) or not role_name.strip():
            raise ValueError(f"{prefix}.role must be a nonempty string")
        if role_name in role_names:
            raise ValueError(f"{prefix}.role duplicates an earlier role")
        role_names.add(role_name)
        group_id = role["group_id"]
        if not _is_number(group_id) or group_id <= 0:
            raise ValueError(f"{prefix}.group_id must be a positive number")
        if group_id in role_group_ids:
            raise ValueError(f"{prefix}.group_id duplicates an earlier role")
        role_group_ids.add(group_id)
        if role["side"] not in {"red", "blue", "neutrals"}:
            raise ValueError(f"{prefix}.side is invalid")
        if role["category"] not in CATEGORIES:
            raise ValueError(f"{prefix}.category is invalid")
        if role["group_task"] is not None and not isinstance(
            role["group_task"],
            str,
        ):
            raise ValueError(f"{prefix}.group_task must be a string or null")
        _validate_role_counts(
            role["unit_types"],
            path=f"{prefix}.unit_types",
            required_keys=None,
        )
        _validate_role_counts(
            role["human_slots"],
            path=f"{prefix}.human_slots",
            required_keys={"Player", "Client"},
        )
        if role["start_mode"] not in START_MODES:
            raise ValueError(f"{prefix}.start_mode is invalid")
        if role["airdrome_id"] is not None and not _is_number(role["airdrome_id"]):
            raise ValueError(f"{prefix}.airdrome_id must be a number or null")
        for field_name in sorted(ROLE_OPTIONAL_FIELDS):
            if (
                field_name in role
                and role[field_name] is not None
                and not _is_number(role[field_name])
            ):
                raise ValueError(f"{prefix}.{field_name} must be a number or null")
        elapsed_start = role.get("mission_elapsed_start_seconds")
        if elapsed_start is not None and (
            not _is_number(elapsed_start) or elapsed_start < 0
        ):
            raise ValueError(
                f"{prefix}.mission_elapsed_start_seconds must be a "
                "nonnegative number or null"
            )
        if not isinstance(role["late_activation"], bool):
            raise ValueError(f"{prefix}.late_activation must be a boolean")
        for field_name in (
            "minimum_waypoints",
            "minimum_route_span_seconds",
        ):
            if not _is_nonnegative_int(role[field_name]):
                raise ValueError(f"{prefix}.{field_name} must be a nonnegative integer")
        _validate_role_list(
            role["required_waypoint_task_ids"],
            path=f"{prefix}.required_waypoint_task_ids",
            value_type=str,
        )
        _validate_role_list(
            role["required_waypoint_actions"],
            path=f"{prefix}.required_waypoint_actions",
            value_type=str,
        )
        _validate_role_list(
            role["required_task_group_ids"],
            path=f"{prefix}.required_task_group_ids",
            value_type=int,
        )


def classify_start_mode(first_point: LuaTable) -> str:
    point_type = first_point.get("type")
    action = first_point.get("action")
    return START_MODE_PAIRS.get((point_type, action), "other")


def has_invalid_start_mode_pair(first_point: LuaTable) -> bool:
    """Return whether one known start marker is paired with another value."""

    point_type = first_point.get("type")
    action = first_point.get("action")
    return (point_type in _START_MODE_TYPES or action in _START_MODE_ACTIONS) and (
        point_type,
        action,
    ) not in START_MODE_PAIRS


def table(value: Any) -> LuaTable:
    return value if isinstance(value, LuaTable) else LuaTable(())


def numeric_values(value: Any) -> list[Any]:
    return [field.value for field in table(value).numeric_items()]


def numeric_tables(value: Any) -> list[LuaTable]:
    return [
        field.value
        for field in table(value).numeric_items()
        if isinstance(field.value, LuaTable)
    ]


def string_fields(value: LuaTable) -> tuple[str, ...]:
    return tuple(field.key for field in value.fields if isinstance(field.key, str))


def _collect_task_ids(value: Any, counts: Counter[str]) -> None:
    if not isinstance(value, LuaTable):
        return
    for field in value.fields:
        if field.key == "id" and isinstance(field.value, str):
            counts[field.value] += 1
        if isinstance(field.value, LuaTable):
            _collect_task_ids(field.value, counts)


def _collect_task_group_ids(
    value: Any,
    identifiers: set[int | float],
) -> None:
    if not isinstance(value, LuaTable):
        return
    group_id = value.get("groupId")
    if _is_number(group_id):
        identifiers.add(group_id)
    for field in value.fields:
        if isinstance(field.value, LuaTable):
            _collect_task_group_ids(field.value, identifiers)


def _collect_predicate_names(value: Any, counts: Counter[str]) -> None:
    if not isinstance(value, str):
        return
    for match in _DCS_PREDICATE.finditer(value):
        counts[match.group("name")] += 1


def _resolve_path(
    root: LuaTable,
    path: list[str | int | float],
) -> Any:
    value: Any = root
    for segment in path:
        if not isinstance(value, LuaTable) or not value.has(segment):
            return _MISSING
        value = value.get(segment)
    return value


def _display_path(path: list[str | int | float]) -> str:
    result = "$"
    for segment in path:
        if isinstance(segment, str):
            result += f".{segment}"
        else:
            result += f"[{segment}]"
    return result


def _scalar_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if _is_number(expected):
        return _is_number(actual) and actual == expected
    return isinstance(actual, str) and actual == expected


def _is_scalar(value: Any) -> bool:
    return isinstance(value, bool | str) or (
        _is_number(value)
        and not (isinstance(value, float) and not math.isfinite(value))
    )


def _scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if _is_number(value):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_role_counts(
    value: Any,
    *,
    path: str,
    required_keys: set[str] | None,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    if required_keys is not None and set(value) != required_keys:
        raise ValueError(f"{path} must contain exactly {sorted(required_keys)}")
    if any(
        not isinstance(key, str) or not key or not _is_nonnegative_int(count)
        for key, count in value.items()
    ):
        raise ValueError(f"{path} must map nonempty strings to nonnegative integers")


def _validate_role_list(
    value: Any,
    *,
    path: str,
    value_type: type,
) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    if value_type is str:
        valid = all(isinstance(item, str) and item for item in value)
    else:
        valid = all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in value
        )
    if not valid or len(value) != len(set(value)):
        raise ValueError(
            f"{path} must contain unique valid {value_type.__name__} values"
        )
