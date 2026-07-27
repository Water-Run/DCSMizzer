from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.logic import LogicSpecError, compile_logic  # noqa: E402
from dcsmizzer.lua_write import json_to_lua  # noqa: E402
from dcsmizzer.structure import validate_mission_structure  # noqa: E402


def logic_fixture() -> dict[str, object]:
    return {
        "schema": "dcsmizzer.miz-logic/v1",
        "trigger_rules": [
            {
                "kind": "once",
                "comment": "Activate reserve",
                "conditions": [
                    {"predicate": "c_unit_dead", "unit": 1},
                    {"predicate": "c_flag_is_false", "flag": 2},
                ],
                "actions": [
                    {"predicate": "a_activate_group", "group": 2},
                    {
                        "predicate": "a_set_flag_value",
                        "flag": 3,
                        "value": 7,
                    },
                ],
            }
        ],
        "goals": [
            {
                "side": "OFFLINE",
                "score": 100,
                "comment": "Reserve activated",
                "conditions": [
                    {
                        "predicate": "c_flag_equals",
                        "flag": 3,
                        "value": 7,
                    }
                ],
            }
        ],
    }


class LogicCompilerTests(unittest.TestCase):
    def test_compiles_separate_dcs_logic_tables(self) -> None:
        compiled, summary = compile_logic(logic_fixture())

        self.assertEqual(set(compiled), {"trigrules", "trig", "goals", "result"})
        self.assertEqual(
            compiled["trigrules"][0]["predicate"],
            "triggerOnce",
        )
        self.assertEqual(
            compiled["trig"]["conditions"][0],
            "return(c_unit_dead(1) and c_flag_is_false(2) )",
        )
        self.assertIn(
            "mission.trig.func[1]=nil",
            compiled["trig"]["actions"][0],
        )
        self.assertEqual(compiled["result"]["total"], 1)
        self.assertEqual(
            compiled["result"]["offline"]["actions"]["$fields"],
            [{"key": 1, "value": "a_set_mission_result(100)"}],
        )
        self.assertEqual(compiled["trig"]["custom"], {})
        self.assertEqual(summary["trigger_conditions"], 2)
        self.assertEqual(summary["goals"], 1)

    def test_goal_result_tables_keep_global_goal_keys(self) -> None:
        source = logic_fixture()
        source["goals"].extend(
            [
                {
                    "side": "BLUE",
                    "score": -50,
                    "comment": "Failure",
                    "conditions": [{"predicate": "c_flag_is_true", "flag": 4}],
                },
                {
                    "side": "OFFLINE",
                    "score": 50,
                    "comment": "Partial success",
                    "conditions": [{"predicate": "c_flag_is_true", "flag": 5}],
                },
            ]
        )

        compiled, _summary = compile_logic(source)

        self.assertEqual(
            compiled["result"]["offline"]["conditions"]["$fields"],
            [
                {
                    "key": 1,
                    "value": "return(c_flag_equals(3, 7) )",
                },
                {
                    "key": 3,
                    "value": "return(c_flag_is_true(5) )",
                },
            ],
        )
        self.assertEqual(
            compiled["result"]["blue"]["actions"]["$fields"],
            [{"key": 2, "value": "a_set_mission_result(-50)"}],
        )
        self.assertIn(
            "offline.conditions[3]()",
            compiled["result"]["offline"]["func"]["$fields"][1]["value"],
        )

    def test_rejects_unknown_predicates_and_nonpositive_references(self) -> None:
        unknown = logic_fixture()
        unknown["trigger_rules"][0]["conditions"][0]["predicate"] = "c_lua"
        with self.assertRaisesRegex(LogicSpecError, "predicate"):
            compile_logic(unknown)

        invalid_reference = logic_fixture()
        invalid_reference["trigger_rules"][0]["actions"][0]["group"] = 0
        with self.assertRaisesRegex(LogicSpecError, "positive integer"):
            compile_logic(invalid_reference)

    def test_compiles_group_in_zone_and_checks_both_references(self) -> None:
        source = logic_fixture()
        source["trigger_rules"][0]["conditions"] = [
            {
                "predicate": "c_part_of_group_in_zone",
                "group": 2,
                "zone": 9,
            }
        ]

        compiled, summary = compile_logic(source)

        self.assertEqual(
            compiled["trig"]["conditions"][0],
            "return(c_part_of_group_in_zone(2, 9) )",
        )
        self.assertIn(
            "c_part_of_group_in_zone",
            summary["condition_predicates"],
        )

        mission = json_to_lua(
            {
                "coalition": {
                    "blue": {
                        "country": [
                            {
                                "id": 2,
                                "vehicle": {
                                    "group": [
                                        {
                                            "groupId": 2,
                                            "name": "Fixture group",
                                            "route": {
                                                "points": [
                                                    {
                                                        "x": 0,
                                                        "y": 0,
                                                        "type": "Turning Point",
                                                        "action": "Off Road",
                                                    }
                                                ]
                                            },
                                            "units": [
                                                {
                                                    "unitId": 2,
                                                    "name": "Fixture unit",
                                                    "type": "Fixture",
                                                    "x": 0,
                                                    "y": 0,
                                                    "heading": 0,
                                                }
                                            ],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
                "triggers": {
                    "zones": [
                        {
                            "zoneId": 9,
                            "name": "Fixture zone",
                            "x": 0,
                            "y": 0,
                            "radius": 100,
                        }
                    ]
                },
                **compiled,
            }
        )
        report = validate_mission_structure(mission)
        self.assertTrue(report["valid"])

        missing_group = json_to_lua(
            {
                "coalition": {},
                "triggers": {"zones": [{"zoneId": 9, "x": 0, "y": 0, "radius": 100}]},
                **compiled,
            }
        )
        missing = validate_mission_structure(missing_group)
        codes = {item["code"] for item in missing["diagnostics"]}
        self.assertIn("unknown_logic_group_reference", codes)

    def test_compiles_dictionary_backed_guidance_text(self) -> None:
        source = logic_fixture()
        source["trigger_rules"][0]["conditions"] = [
            {"predicate": "c_time_after", "seconds": 60}
        ]
        source["trigger_rules"][0]["actions"] = [
            {
                "predicate": "a_out_text_delay",
                "dictionary_key": "DictKey_GCI_01",
                "seconds": 12,
                "clearview": False,
                "start_delay": 2,
            }
        ]

        compiled, summary = compile_logic(source)
        action = compiled["trigrules"][0]["actions"][0]
        self.assertEqual(action["KeyDict_text"], "DictKey_GCI_01")
        self.assertEqual(action["text"], "DictKey_GCI_01")
        self.assertIn(
            'a_out_text_delay(getValueDictByKey("DictKey_GCI_01"), 12, false, 2)',
            compiled["trig"]["actions"][0],
        )
        self.assertIn("a_out_text_delay", summary["action_predicates"])

        mission = json_to_lua(
            {
                "coalition": {},
                "triggers": {"zones": []},
                **compiled,
            }
        )
        dictionary = json_to_lua({"DictKey_GCI_01": "Turn north. Contact bearing 340."})
        report = validate_mission_structure(
            mission,
            dictionary=dictionary,
        )
        self.assertTrue(report["valid"])

        missing = validate_mission_structure(
            mission,
            dictionary=json_to_lua({}),
        )
        codes = {item["code"] for item in missing["diagnostics"]}
        self.assertIn("unresolved_out_text_dictionary_key", codes)

    def test_structure_rejects_misplaced_or_uncompiled_logic(self) -> None:
        misplaced = json_to_lua(
            {
                "coalition": {},
                "triggers": {
                    "zones": [],
                    "trigrules": [],
                    "goals": [],
                },
            }
        )
        report = validate_mission_structure(misplaced)
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("misplaced_mission_logic_field", codes)

        uncompiled = json_to_lua(
            {
                "coalition": {},
                "trigrules": [
                    {
                        "predicate": "triggerOnce",
                        "eventlist": "",
                        "comment": "Missing compiled table",
                        "rules": [{"predicate": "c_time_after", "seconds": 1}],
                        "actions": [{"predicate": "a_set_flag", "flag": 1}],
                    }
                ],
            }
        )
        report = validate_mission_structure(uncompiled)
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("missing_compiled_trigger_table", codes)


if __name__ == "__main__":
    unittest.main()
