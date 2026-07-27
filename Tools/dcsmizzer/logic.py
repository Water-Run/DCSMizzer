"""Finite, data-only compiler for common DCS trigger and goal logic."""

from __future__ import annotations

import math
import re
from typing import Any


LOGIC_SCHEMA = "dcsmizzer.miz-logic/v1"

_TRIGGER_KINDS: dict[str, str] = {
    "once": "triggerOnce",
    "continuous": "triggerContinious",
    "start": "triggerStart",
    "front": "triggerFront",
}
_CONDITION_FIELDS: dict[str, tuple[str, ...]] = {
    "c_time_after": ("seconds",),
    "c_flag_is_true": ("flag",),
    "c_flag_is_false": ("flag",),
    "c_flag_equals": ("flag", "value"),
    "c_unit_dead": ("unit",),
    "c_group_dead": ("group",),
    "c_unit_in_zone": ("unit", "zone"),
    "c_part_of_group_in_zone": ("group", "zone"),
}
_ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "a_set_flag": ("flag",),
    "a_set_flag_value": ("flag", "value"),
    "a_activate_group": ("group",),
    "a_out_text_delay": (
        "dictionary_key",
        "seconds",
        "clearview",
        "start_delay",
    ),
}
_IDENTIFIER_FIELDS = frozenset({"flag", "unit", "group", "zone"})
_GOAL_SIDES = frozenset({"RED", "BLUE", "OFFLINE"})
_DICTIONARY_KEY = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")


class LogicSpecError(ValueError):
    """The finite trigger/goal specification is invalid."""


def compile_logic(logic: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile the finite JSON vocabulary into DCS mission table fragments."""

    if not isinstance(logic, dict):
        raise LogicSpecError("logic must be a JSON object")
    if set(logic) != {"schema", "trigger_rules", "goals"}:
        raise LogicSpecError(
            "logic must contain exactly schema, trigger_rules, and goals"
        )
    if logic["schema"] != LOGIC_SCHEMA:
        raise LogicSpecError(f"logic.schema must be {LOGIC_SCHEMA!r}")
    trigger_inputs = logic["trigger_rules"]
    goal_inputs = logic["goals"]
    if not isinstance(trigger_inputs, list) or not trigger_inputs:
        raise LogicSpecError("logic.trigger_rules must be a nonempty array")
    if not isinstance(goal_inputs, list) or not goal_inputs:
        raise LogicSpecError("logic.goals must be a nonempty array")

    trigger_rules: list[dict[str, Any]] = []
    condition_strings: list[str] = []
    action_strings: list[str] = []
    functions: list[dict[str, Any]] = []
    startup_functions: list[dict[str, Any]] = []
    condition_predicates: set[str] = set()
    action_predicates: set[str] = set()
    for index, value in enumerate(trigger_inputs, start=1):
        path = f"logic.trigger_rules[{index - 1}]"
        rule = _trigger_rule(value, path=path)
        trigger_rules.append(rule)
        condition_strings.append(_condition_string(rule["rules"]))
        action_strings.append(
            _action_string(
                rule["actions"],
                trigger_index=index,
                once=rule["predicate"] == "triggerOnce",
            )
        )
        function = _trigger_function(rule["predicate"], index)
        target = startup_functions if rule["predicate"] == "triggerStart" else functions
        target.append({"key": index, "value": function})
        condition_predicates.update(item["predicate"] for item in rule["rules"])
        action_predicates.update(item["predicate"] for item in rule["actions"])

    goals: list[dict[str, Any]] = []
    result_by_side: dict[str, list[tuple[int, dict[str, Any]]]] = {
        "blue": [],
        "red": [],
        "offline": [],
    }
    goal_predicates: set[str] = set()
    for index, value in enumerate(goal_inputs, start=1):
        path = f"logic.goals[{index - 1}]"
        goal = _goal(value, path=path)
        goals.append(goal)
        side = goal["side"].lower()
        result_by_side[side].append((index, goal))
        goal_predicates.update(item["predicate"] for item in goal["rules"])

    result: dict[str, Any] = {"total": len(goals)}
    for side in ("blue", "red", "offline"):
        side_goals = result_by_side[side]
        result[side] = {
            "conditions": {
                "$fields": [
                    {
                        "key": index,
                        "value": _condition_string(goal["rules"]),
                    }
                    for index, goal in side_goals
                ]
            },
            "actions": {
                "$fields": [
                    {
                        "key": index,
                        "value": (
                            f"a_set_mission_result({_lua_number(goal['score'])})"
                        ),
                    }
                    for index, goal in side_goals
                ]
            },
            "func": {
                "$fields": [
                    {
                        "key": index,
                        "value": (
                            "if mission.result."
                            f"{side}.conditions[{index}]() then mission.result."
                            f"{side}.actions[{index}]() end"
                        ),
                    }
                    for index, _goal_value in side_goals
                ]
            },
        }

    compiled = {
        "trigrules": trigger_rules,
        "trig": {
            "conditions": condition_strings,
            "actions": action_strings,
            "func": {"$fields": functions},
            "funcStartup": {"$fields": startup_functions},
            "custom": {},
            "customStartup": {},
            "events": {},
            "flag": [True for _rule in trigger_rules],
        },
        "goals": goals,
        "result": result,
    }
    summary = {
        "schema": LOGIC_SCHEMA,
        "method": "finite_data_only_trigger_goal_compiler",
        "trigger_rules": len(trigger_rules),
        "trigger_conditions": sum(len(rule["rules"]) for rule in trigger_rules),
        "trigger_actions": sum(len(rule["actions"]) for rule in trigger_rules),
        "goals": len(goals),
        "condition_predicates": sorted(condition_predicates),
        "action_predicates": sorted(action_predicates),
        "goal_predicates": sorted(goal_predicates),
        "event_support": "NoEvent_only",
    }
    return compiled, summary


def _trigger_rule(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LogicSpecError(f"{path} must be an object")
    expected = {"kind", "comment", "conditions", "actions"}
    if set(value) != expected:
        raise LogicSpecError(f"{path} must contain exactly {sorted(expected)}")
    kind = value["kind"]
    if kind not in _TRIGGER_KINDS:
        raise LogicSpecError(f"{path}.kind must be one of {sorted(_TRIGGER_KINDS)}")
    comment = _nonempty_string(value["comment"], f"{path}.comment")
    conditions = _records(
        value["conditions"],
        path=f"{path}.conditions",
        signatures=_CONDITION_FIELDS,
        allow_empty=kind == "start",
    )
    actions = _records(
        value["actions"],
        path=f"{path}.actions",
        signatures=_ACTION_FIELDS,
        allow_empty=False,
    )
    return {
        "comment": comment,
        "colorItem": "0xffffffff",
        "eventlist": "",
        "predicate": _TRIGGER_KINDS[kind],
        "rules": conditions,
        "actions": actions,
    }


def _goal(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LogicSpecError(f"{path} must be an object")
    expected = {"side", "score", "comment", "conditions"}
    if set(value) != expected:
        raise LogicSpecError(f"{path} must contain exactly {sorted(expected)}")
    side = value["side"]
    if side not in _GOAL_SIDES:
        raise LogicSpecError(f"{path}.side must be RED, BLUE, or OFFLINE")
    score = value["score"]
    if (
        not isinstance(score, int)
        or isinstance(score, bool)
        or score < -100
        or score > 100
    ):
        raise LogicSpecError(f"{path}.score must be an integer from -100 to 100")
    return {
        "side": side,
        "score": score,
        "predicate": "score",
        "comment": _nonempty_string(value["comment"], f"{path}.comment"),
        "rules": _records(
            value["conditions"],
            path=f"{path}.conditions",
            signatures=_CONDITION_FIELDS,
            allow_empty=False,
        ),
    }


def _records(
    value: Any,
    *,
    path: str,
    signatures: dict[str, tuple[str, ...]],
    allow_empty: bool,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a nonempty array"
        raise LogicSpecError(f"{path} must be {qualifier}")
    result: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        record_path = f"{path}[{index}]"
        if not isinstance(record, dict):
            raise LogicSpecError(f"{record_path} must be an object")
        predicate = record.get("predicate")
        if predicate not in signatures:
            raise LogicSpecError(
                f"{record_path}.predicate must be one of {sorted(signatures)}"
            )
        fields = signatures[predicate]
        expected = {"predicate", *fields}
        if set(record) != expected:
            raise LogicSpecError(
                f"{record_path} must contain exactly {sorted(expected)}"
            )
        output = {"predicate": predicate}
        for field in fields:
            output[field] = _parameter(
                record[field],
                field=field,
                path=f"{record_path}.{field}",
            )
        if predicate == "a_out_text_delay":
            dictionary_key = output.pop("dictionary_key")
            output["text"] = dictionary_key
            output["KeyDict_text"] = dictionary_key
        result.append(output)
    return result


def _parameter(value: Any, *, field: str, path: str) -> Any:
    if field == "dictionary_key":
        if not isinstance(value, str) or _DICTIONARY_KEY.fullmatch(value) is None:
            raise LogicSpecError(
                f"{path} must be a safe 1-128 character dictionary key"
            )
        return value
    if field == "clearview":
        if not isinstance(value, bool):
            raise LogicSpecError(f"{path} must be a boolean")
        return value
    if not _is_number(value):
        raise LogicSpecError(f"{path} must be a finite number")
    if field in _IDENTIFIER_FIELDS and (not isinstance(value, int) or value <= 0):
        raise LogicSpecError(f"{path} must be a positive integer")
    if field in {"seconds", "start_delay"} and value < 0:
        raise LogicSpecError(f"{path} must be nonnegative")
    return value


def _condition_string(records: list[dict[str, Any]]) -> str:
    if not records:
        return "return(true)"
    calls = [_call(record) for record in records]
    return f"return({' and '.join(calls)} )"


def _action_string(
    records: list[dict[str, Any]],
    *,
    trigger_index: int,
    once: bool,
) -> str:
    value = ";".join(_call(record) for record in records) + ";"
    if once:
        value += f" mission.trig.func[{trigger_index}]=nil;"
    return value


def _trigger_function(predicate: str, index: int) -> str:
    if predicate == "triggerFront":
        return (
            f"if mission.trig.conditions[{index}]() then if not "
            f"mission.trig.flag[{index}] then mission.trig.actions[{index}](); "
            f"mission.trig.flag[{index}] = true;end; else mission.trig.flag"
            f"[{index}] = false; end;"
        )
    return (
        f"if mission.trig.conditions[{index}]() then "
        f"mission.trig.actions[{index}]() end"
    )


def _call(record: dict[str, Any]) -> str:
    predicate = record["predicate"]
    if predicate == "a_out_text_delay":
        key = record["KeyDict_text"]
        return (
            f'a_out_text_delay(getValueDictByKey("{key}"), '
            f"{_lua_number(record['seconds'])}, "
            f"{_lua_boolean(record['clearview'])}, "
            f"{_lua_number(record['start_delay'])})"
        )
    signatures = _CONDITION_FIELDS if predicate in _CONDITION_FIELDS else _ACTION_FIELDS
    arguments = ", ".join(_lua_number(record[field]) for field in signatures[predicate])
    return f"{predicate}({arguments})"


def _lua_boolean(value: bool) -> str:
    if not isinstance(value, bool):
        raise LogicSpecError("compiled logic contains a non-boolean value")
    return "true" if value else "false"


def _lua_number(value: int | float) -> str:
    if not _is_number(value):
        raise LogicSpecError("compiled logic contains a non-finite number")
    return str(value) if isinstance(value, int) else repr(value)


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LogicSpecError(f"{path} must be a nonempty string")
    if "\x00" in value:
        raise LogicSpecError(f"{path} contains a NUL character")
    return value


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )
