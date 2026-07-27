from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.lua_write import json_to_lua  # noqa: E402
from dcsmizzer.facts import (  # noqa: E402
    classify_start_mode,
    collect_mission_facts,
    evaluate_expectations,
    has_invalid_start_mode_pair,
    validate_expectations,
)
from dcsmizzer.structure import validate_mission_structure  # noqa: E402


def _direct_task(
    task_id: str,
    params: dict[str, object],
    number: int,
) -> dict[str, object]:
    return {
        "id": task_id,
        "params": params,
        "number": number,
        "auto": False,
        "enabled": True,
    }


def _empty_combo_task() -> dict[str, object]:
    return {"id": "ComboTask", "params": {"tasks": []}}


def _semantic_mission() -> dict[str, object]:
    tasks = [
        _direct_task(
            "AttackGroup",
            {
                "groupId": 3,
                "weaponType": 9663676414,
                "groupAttack": False,
                "attackQtyLimit": False,
                "attackQty": 1,
                "altitudeEnabled": False,
                "altitude": 0,
                "directionEnabled": False,
                "direction": 0,
                "expend": "Auto",
            },
            1,
        ),
        _direct_task(
            "Bombing",
            {
                "x": 1000,
                "y": 2000,
                "altitude": 0,
                "altitudeEnabled": False,
                "attackQty": 1,
                "attackQtyLimit": False,
                "direction": 0,
                "directionEnabled": False,
                "expend": "Auto",
                "groupAttack": False,
                "weaponType": 9663676414,
            },
            2,
        ),
        _direct_task(
            "EngageTargets",
            {
                "targetTypes": ["Air"],
                "priority": 0,
            },
            3,
        ),
        _direct_task(
            "EngageTargetsInZone",
            {
                "targetTypes": ["Planes"],
                "priority": 0,
                "x": 1000,
                "y": 2000,
                "zoneRadius": 10000,
            },
            4,
        ),
        _direct_task(
            "Escort",
            {
                "engagementDistMax": 60000,
                "groupId": 2,
                "lastWptIndex": 1,
                "lastWptIndexFlag": True,
                "lastWptIndexFlagChangedManually": True,
                "pos": {"x": -200, "y": -100, "z": -500},
                "targetTypes": ["Planes"],
            },
            5,
        ),
        _direct_task(
            "ControlledTask",
            {
                "task": {
                    "id": "AttackGroup",
                    "params": {
                        "groupId": 3,
                        "weaponType": 9663676414,
                        "groupAttack": False,
                        "attackQtyLimit": False,
                        "attackQty": 1,
                        "altitudeEnabled": False,
                        "altitude": 0,
                        "directionEnabled": False,
                        "direction": 0,
                        "expend": "Auto",
                    },
                }
            },
            6,
        ),
    ]
    return {
        "coalition": {
            "blue": {
                "country": [
                    {
                        "id": 2,
                        "plane": {
                            "group": [
                                {
                                    "groupId": 1,
                                    "name": "Mission flight",
                                    "task": "Escort",
                                    "route": {
                                        "points": [
                                            {
                                                "x": 0,
                                                "y": 0,
                                                "type": "Turning Point",
                                                "action": "Turning Point",
                                                "task": {
                                                    "id": "ComboTask",
                                                    "params": {"tasks": tasks},
                                                },
                                            }
                                        ]
                                    },
                                    "units": [
                                        {
                                            "unitId": 1,
                                            "name": "Mission lead",
                                            "type": "Fixture Plane",
                                            "skill": "Player",
                                            "x": 0,
                                            "y": 0,
                                            "alt": 1000,
                                            "heading": 0,
                                            "payload": {"pylons": []},
                                        }
                                    ],
                                },
                                {
                                    "groupId": 2,
                                    "name": "Escort target",
                                    "task": "CAP",
                                    "route": {
                                        "points": [
                                            {
                                                "x": 100,
                                                "y": 100,
                                                "type": "Turning Point",
                                                "action": "Turning Point",
                                                "task": _empty_combo_task(),
                                            }
                                        ]
                                    },
                                    "units": [
                                        {
                                            "unitId": 2,
                                            "name": "Escort lead",
                                            "type": "Fixture Plane",
                                            "skill": "Excellent",
                                            "x": 100,
                                            "y": 100,
                                            "alt": 1000,
                                            "heading": 0,
                                            "payload": {"pylons": []},
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ]
            },
            "red": {
                "country": [
                    {
                        "id": 68,
                        "vehicle": {
                            "group": [
                                {
                                    "groupId": 3,
                                    "name": "Hostile target",
                                    "route": {
                                        "points": [
                                            {
                                                "x": 1000,
                                                "y": 2000,
                                                "type": "Turning Point",
                                                "action": "Off Road",
                                            }
                                        ]
                                    },
                                    "units": [
                                        {
                                            "unitId": 3,
                                            "name": "Hostile unit",
                                            "type": "Fixture Vehicle",
                                            "skill": "Excellent",
                                            "x": 1000,
                                            "y": 2000,
                                            "heading": 0,
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ]
            },
        }
    }


def _add_observed_runtime_shell(
    mission: dict[str, object],
) -> dict[str, object]:
    coalition = mission["coalition"]
    coalitions: dict[str, list[int]] = {}
    for side_name, side in coalition.items():
        side["name"] = side_name
        side["bullseye"] = {"x": 0, "y": 0}
        side["nav_points"] = []
        coalitions[side_name] = [country["id"] for country in side.get("country", [])]
    mission.update(
        {
            "coalitions": coalitions,
            "currentKey": 100,
            "failures": {},
            "forcedOptions": {},
            "groundControl": {
                "isPilotControlVehicles": False,
                "roles": {
                    role_name: {"blue": [], "red": []}
                    for role_name in (
                        "artillery_commander",
                        "forward_observer",
                        "instructor",
                        "observer",
                    )
                },
            },
            "map": {"centerX": 0, "centerY": 0, "zoom": 100000},
            "maxDictId": 5,
            "pictureFileNameB": {},
            "pictureFileNameR": {},
        }
    )
    return mission


def _linked_helicopter_start_mission() -> dict[str, object]:
    return {
        "coalition": {
            "blue": {
                "country": [
                    {
                        "id": 2,
                        "helicopter": {
                            "group": [
                                {
                                    "groupId": 1,
                                    "name": "FARP flight",
                                    "task": "Transport",
                                    "route": {
                                        "points": [
                                            {
                                                "x": 0,
                                                "y": 0,
                                                "type": "TakeOffParking",
                                                "action": "From Parking Area",
                                                "helipadId": 50,
                                                "linkUnit": 50,
                                                "task": _empty_combo_task(),
                                            }
                                        ]
                                    },
                                    "units": [
                                        {
                                            "unitId": 1,
                                            "name": "FARP helicopter",
                                            "type": "Fixture Helicopter",
                                            "skill": "Player",
                                            "x": 0,
                                            "y": 0,
                                            "alt": 0,
                                            "heading": 0,
                                            "payload": {"pylons": []},
                                        }
                                    ],
                                }
                            ]
                        },
                        "static": {
                            "group": [
                                {
                                    "groupId": 50,
                                    "name": "FARP facility",
                                    "route": {"points": [{"x": 0, "y": 0}]},
                                    "units": [
                                        {
                                            "unitId": 50,
                                            "name": "FARP unit",
                                            "type": "FARP",
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
        }
    }


def _role_expectation() -> dict[str, object]:
    return {
        "role": "player_flight",
        "group_id": 1,
        "side": "blue",
        "category": "helicopter",
        "group_task": "Transport",
        "unit_types": {"Fixture Helicopter": 1},
        "human_slots": {"Player": 1, "Client": 0},
        "start_mode": "cold_parking",
        "airdrome_id": None,
        "late_activation": False,
        "minimum_waypoints": 1,
        "minimum_route_span_seconds": 0,
        "required_waypoint_task_ids": ["ComboTask"],
        "required_waypoint_actions": ["From Parking Area"],
        "required_task_group_ids": [],
    }


class MissionStructureTests(unittest.TestCase):
    def test_static_placeholder_route_and_empty_briefing_are_not_errors(
        self,
    ) -> None:
        mission = json_to_lua(
            {
                "descriptionBlueTask": "DictKey_blue",
                "coalition": {
                    "blue": {
                        "country": [
                            {
                                "id": 2,
                                "static": {
                                    "group": [
                                        {
                                            "groupId": 1,
                                            "name": "Static group",
                                            "route": {
                                                "points": [
                                                    {
                                                        "x": 100,
                                                        "y": 200,
                                                    }
                                                ]
                                            },
                                            "units": [
                                                {
                                                    "unitId": 1,
                                                    "name": "Static unit",
                                                    "type": "Fixture static",
                                                    "x": 100,
                                                    "y": 200,
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
            }
        )
        dictionary = json_to_lua({"DictKey_blue": ""})

        report = validate_mission_structure(
            mission,
            dictionary=dictionary,
        )

        self.assertTrue(report["valid"])
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["warning_count"], 1)
        self.assertEqual(
            report["diagnostics"][0]["code"],
            "empty_briefing_dictionary_value",
        )

    def test_rejects_internal_task_name_missing_waypoint_task_and_overlap(
        self,
    ) -> None:
        mission_data = {
            "coalition": {
                "blue": {
                    "country": [
                        {
                            "id": 2,
                            "plane": {
                                "group": [
                                    {
                                        "groupId": 1,
                                        "name": "Air group",
                                        "task": "GroundAttack",
                                        "route": {
                                            "points": [
                                                {
                                                    "x": 100,
                                                    "y": 200,
                                                    "type": "Turning Point",
                                                    "action": "Turning Point",
                                                }
                                            ]
                                        },
                                        "units": [
                                            {
                                                "unitId": 1,
                                                "name": "Lead",
                                                "type": "Fixture Plane",
                                                "skill": "Excellent",
                                                "x": 100,
                                                "y": 200,
                                                "alt": 1000,
                                                "heading": 0,
                                                "payload": {"pylons": []},
                                            },
                                            {
                                                "unitId": 2,
                                                "name": "Wing",
                                                "type": "Fixture Plane",
                                                "skill": "Good",
                                                "x": 100,
                                                "y": 200,
                                                "alt": 1000,
                                                "heading": 0,
                                                "payload": {"pylons": []},
                                            },
                                        ],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        }

        report = validate_mission_structure(json_to_lua(mission_data))

        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("invalid_air_group_task", codes)
        self.assertIn("missing_air_waypoint_task", codes)
        self.assertIn("duplicate_airborne_unit_position", codes)

    def test_validates_native_mig29_gci_station_and_radar_link(self) -> None:
        station_task = {
            "id": "ComboTask",
            "params": {
                "tasks": [
                    {
                        "number": 1,
                        "auto": True,
                        "id": "WrappedAction",
                        "enabled": True,
                        "params": {
                            "action": {
                                "id": "ActivateGCI",
                                "params": {
                                    "unitId": 10,
                                    "channel": 5,
                                    "radius": 200000,
                                    "x": 50000,
                                    "y": 60000,
                                },
                            }
                        },
                    }
                ]
            },
        }
        mission_data = {
            "coalition": {
                "red": {
                    "country": [
                        {
                            "id": 68,
                            "vehicle": {
                                "group": [
                                    {
                                        "groupId": 10,
                                        "name": "GCI group",
                                        "route": {
                                            "points": [
                                                {
                                                    "x": 0,
                                                    "y": 0,
                                                    "type": "Turning Point",
                                                    "action": "Off Road",
                                                    "task": station_task,
                                                }
                                            ]
                                        },
                                        "units": [
                                            {
                                                "unitId": 10,
                                                "name": "GCI station",
                                                "type": "GCI_station_MiG29",
                                                "x": 0,
                                                "y": 0,
                                                "heading": 0,
                                            }
                                        ],
                                    },
                                    {
                                        "groupId": 11,
                                        "name": "Radar group",
                                        "route": {
                                            "points": [
                                                {
                                                    "x": 100000,
                                                    "y": 0,
                                                    "type": "Turning Point",
                                                    "action": "Off Road",
                                                }
                                            ]
                                        },
                                        "units": [
                                            {
                                                "unitId": 11,
                                                "name": "Radar",
                                                "type": "1L13 EWR",
                                                "x": 100000,
                                                "y": 0,
                                                "heading": 0,
                                            }
                                        ],
                                    },
                                ]
                            },
                        }
                    ]
                }
            }
        }

        report = validate_mission_structure(json_to_lua(mission_data))
        self.assertTrue(report["valid"])

        radar = mission_data["coalition"]["red"]["country"][0]["vehicle"]["group"][1]
        radar["units"][0]["x"] = 300000
        radar["route"]["points"][0]["x"] = 300000
        invalid = validate_mission_structure(json_to_lua(mission_data))
        codes = {item["code"] for item in invalid["diagnostics"]}
        self.assertIn("gci_no_compatible_radar_in_link_range", codes)

    def test_validates_combat_waypoint_task_schemas_and_references(
        self,
    ) -> None:
        report = validate_mission_structure(json_to_lua(_semantic_mission()))

        self.assertTrue(report["valid"])
        self.assertEqual(report["error_count"], 0)

    def test_task_number_drift_is_profile_sensitive(self) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        tasks[0]["number"] = 7

        technical = validate_mission_structure(json_to_lua(mission))
        complete = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )

        technical_items = [
            item
            for item in technical["diagnostics"]
            if item["code"] == "direct_task_number_mismatch"
        ]
        complete_items = [
            item
            for item in complete["diagnostics"]
            if item["code"] == "direct_task_number_mismatch"
        ]
        self.assertEqual(
            [item["severity"] for item in technical_items],
            ["warning"],
        )
        self.assertEqual(
            [item["severity"] for item in complete_items],
            ["error"],
        )

    def test_complete_profile_requires_observed_runtime_shell(self) -> None:
        incomplete = validate_mission_structure(
            json_to_lua(_semantic_mission()),
            profile="complete_scenario",
        )
        incomplete_codes = {item["code"] for item in incomplete["diagnostics"]}
        self.assertIn(
            "complete_missing_observed_runtime_table",
            incomplete_codes,
        )
        self.assertIn(
            "complete_invalid_observed_runtime_integer",
            incomplete_codes,
        )
        self.assertIn(
            "complete_invalid_coalition_side_name",
            incomplete_codes,
        )
        self.assertIn(
            "complete_missing_coalition_side_table",
            incomplete_codes,
        )

        complete = validate_mission_structure(
            json_to_lua(_add_observed_runtime_shell(_semantic_mission())),
            profile="complete_scenario",
        )
        runtime_codes = {
            item["code"]
            for item in complete["diagnostics"]
            if (
                "observed_runtime" in item["code"]
                or "coalition_side" in item["code"]
                or "coalition_membership" in item["code"]
                or "ground_control" in item["code"]
                or item["code"]
                in {
                    "complete_invalid_map_field",
                    "complete_invalid_bullseye_coordinate",
                    "complete_country_in_multiple_coalitions",
                }
            )
        }
        self.assertEqual(runtime_codes, set())

    def test_complete_runtime_shell_rejects_semantic_mismatches(self) -> None:
        cases = (
            (
                "map_zoom",
                lambda mission: mission["map"].update({"zoom": 0}),
                "complete_invalid_map_field",
            ),
            (
                "ground_role_side",
                lambda mission: mission["groundControl"]["roles"]["observer"].update(
                    {"red": "not-a-table"}
                ),
                "complete_missing_ground_control_role_side",
            ),
            (
                "membership_coverage",
                lambda mission: mission["coalitions"].update({"blue": []}),
                "complete_country_missing_from_coalition_membership",
            ),
            (
                "side_name",
                lambda mission: mission["coalition"]["red"].update({"name": "blue"}),
                "complete_invalid_coalition_side_name",
            ),
            (
                "multiple_coalitions",
                lambda mission: mission["coalitions"]["blue"].append(68),
                "complete_country_in_multiple_coalitions",
            ),
        )
        for case_name, mutate, expected_code in cases:
            with self.subTest(case=case_name):
                mission = _add_observed_runtime_shell(_semantic_mission())
                mutate(mission)
                report = validate_mission_structure(
                    json_to_lua(mission),
                    profile="complete_scenario",
                )
                codes = {item["code"] for item in report["diagnostics"]}
                self.assertIn(expected_code, codes)

    def test_rejects_invalid_combo_root_and_direct_task_wrapper(
        self,
    ) -> None:
        mission = _semantic_mission()
        groups = mission["coalition"]["blue"]["country"][0]["plane"]["group"]
        root = groups[0]["route"]["points"][0]["task"]
        tasks = root["params"]["tasks"]
        root["id"] = "Orbit"
        del tasks[0]["enabled"]
        tasks[1]["number"] = "2"
        tasks[2]["auto"] = 0
        tasks[3]["params"] = "not-a-table"
        del groups[1]["route"]["points"][0]["task"]["params"]["tasks"]

        report = validate_mission_structure(json_to_lua(mission))

        codes = [item["code"] for item in report["diagnostics"]]
        self.assertIn("invalid_air_waypoint_root_task", codes)
        self.assertIn("missing_combo_task_children", codes)
        self.assertEqual(codes.count("invalid_direct_task_wrapper"), 4)

    def test_complete_profile_requires_current_task_fields(self) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        del tasks[0]["params"]["groupAttack"]
        del tasks[1]["params"]["attackQtyLimit"]
        del tasks[3]["params"]["priority"]
        del tasks[4]["params"]["lastWptIndexFlag"]

        technical = validate_mission_structure(json_to_lua(mission))
        complete = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )

        technical_codes = {item["code"] for item in technical["diagnostics"]}
        complete_missing = [
            item
            for item in complete["diagnostics"]
            if item["code"] == "complete_missing_task_parameter"
        ]
        self.assertNotIn("complete_missing_task_parameter", technical_codes)
        self.assertEqual(len(complete_missing), 4)

    def test_rejects_invalid_combat_task_types_and_group_semantics(
        self,
    ) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        tasks[0]["params"]["groupId"] = 2
        tasks[1]["params"]["weaponType"] = -1
        tasks[2]["params"]["maxDistEnabled"] = True
        tasks[3]["params"]["targetTypes"] = {"$fields": [{"key": 2, "value": "Planes"}]}
        tasks[4]["params"]["groupId"] = 3
        tasks[4]["params"]["lastWptIndex"] = 2

        report = validate_mission_structure(json_to_lua(mission))

        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("attack_group_target_not_hostile", codes)
        self.assertIn("invalid_task_parameter", codes)
        self.assertIn("missing_task_parameter", codes)
        self.assertIn("invalid_task_target_types", codes)
        self.assertIn("escort_target_not_friendly", codes)
        self.assertIn("escort_target_not_plane", codes)
        self.assertIn("escort_last_waypoint_out_of_range", codes)

    def test_complete_rejects_bombing_activated_over_200km_away(
        self,
    ) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        tasks[1]["params"]["x"] = 500_000
        tasks[1]["params"]["y"] = 0

        technical = validate_mission_structure(json_to_lua(mission))
        complete = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )

        technical_codes = {item["code"] for item in technical["diagnostics"]}
        complete_codes = {item["code"] for item in complete["diagnostics"]}
        self.assertNotIn(
            "complete_bombing_activation_too_far_from_target",
            technical_codes,
        )
        self.assertIn(
            "complete_bombing_activation_too_far_from_target",
            complete_codes,
        )

    def test_complete_rejects_extreme_bombing_geometry_without_overflow(
        self,
    ) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        tasks = group["route"]["points"][0]["task"]["params"]["tasks"]
        tasks[1]["params"]["x"] = 10**400

        huge_integer = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        huge_integer_codes = {item["code"] for item in huge_integer["diagnostics"]}
        self.assertIn("invalid_task_parameter", huge_integer_codes)

        group["route"]["points"][0]["x"] = 1e308
        tasks[1]["params"]["x"] = -1e308
        finite_extremes = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        finite_extreme_codes = {item["code"] for item in finite_extremes["diagnostics"]}
        self.assertIn(
            "complete_bombing_activation_too_far_from_target",
            finite_extreme_codes,
        )

    def test_complete_binds_air_start_heading_to_first_route_leg(
        self,
    ) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        group["route"]["points"].append(
            {
                "x": 0,
                "y": 1000,
                "type": "Turning Point",
                "action": "Turning Point",
                "task": _empty_combo_task(),
            }
        )
        group["units"][0]["heading"] = 0

        mismatched = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        mismatch_codes = {item["code"] for item in mismatched["diagnostics"]}
        self.assertIn(
            "complete_air_start_heading_route_mismatch",
            mismatch_codes,
        )

        group["units"][0]["heading"] = math.pi / 2
        aligned = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        aligned_codes = {item["code"] for item in aligned["diagnostics"]}
        self.assertNotIn(
            "complete_air_start_heading_route_mismatch",
            aligned_codes,
        )

    def test_complete_rejects_extreme_air_start_leg_without_overflow(
        self,
    ) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        group["route"]["points"][0]["x"] = 1e308
        group["route"]["points"].append(
            {
                "x": -1e308,
                "y": 0,
                "type": "Turning Point",
                "action": "Turning Point",
                "task": _empty_combo_task(),
            }
        )

        report = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        codes = {item["code"] for item in report["diagnostics"]}

        self.assertIn("complete_air_start_geometry_out_of_range", codes)

    def test_complete_requires_positive_air_start_and_enroute_speeds(
        self,
    ) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        first = group["route"]["points"][0]
        first["speed"] = 0
        group["units"][0]["speed"] = 0
        group["route"]["points"].append(
            {
                "x": 1000,
                "y": 0,
                "speed": 0,
                "type": "Turning Point",
                "action": "Turning Point",
                "task": _empty_combo_task(),
            }
        )

        report = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        codes = [item["code"] for item in report["diagnostics"]]

        self.assertGreaterEqual(
            codes.count("complete_nonpositive_air_start_speed"),
            2,
        )
        self.assertIn("complete_zero_enroute_waypoint_speed", codes)

    def test_complete_requires_positive_single_point_air_start_speeds(
        self,
    ) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        group["route"]["points"][0]["speed"] = 0
        group["units"][0]["speed"] = 0

        report = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        codes = [item["code"] for item in report["diagnostics"]]

        self.assertEqual(
            codes.count("complete_nonpositive_air_start_speed"),
            2,
        )

    def test_escort_cannot_target_its_own_source_group(self) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        tasks[4]["params"]["groupId"] = 1

        report = validate_mission_structure(json_to_lua(mission))

        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("escort_target_is_source_group", codes)
        self.assertNotIn("escort_target_not_friendly", codes)
        self.assertNotIn("escort_target_not_plane", codes)

    def test_known_sequences_are_dense_but_pylons_remain_sparse(self) -> None:
        mission = _semantic_mission()
        first_group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        tasks = first_group["route"]["points"][0]["task"]["params"]["tasks"]
        first_group["route"]["points"][0]["task"]["params"]["tasks"] = {
            "$fields": [
                {"key": 1, "value": tasks[0]},
                {"key": 3, "value": tasks[1]},
            ]
        }
        first_group["units"][0]["payload"]["pylons"] = {
            "$fields": [
                {
                    "key": 7,
                    "value": {"num": 7, "CLSID": "{FIXTURE-STORE}"},
                }
            ]
        }

        report = validate_mission_structure(json_to_lua(mission))

        sparse = [
            item
            for item in report["diagnostics"]
            if item["code"] == "noncontiguous_sequence_keys"
        ]
        self.assertEqual(len(sparse), 1)
        self.assertIn(".task.params.tasks", sparse[0]["path"])
        self.assertNotIn("pylons", sparse[0]["path"])

    def test_accepts_linked_farp_start_without_parking_fields(self) -> None:
        mission = _linked_helicopter_start_mission()

        report = validate_mission_structure(json_to_lua(mission))

        self.assertTrue(report["valid"])
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertNotIn("parking_start_missing_parking", codes)
        self.assertNotIn("parking_start_missing_airdrome_id", codes)

    def test_recognizes_only_observed_air_start_mode_pairs(self) -> None:
        valid_pairs = {
            ("TakeOffParking", "From Parking Area"): "cold_parking",
            (
                "TakeOffParkingHot",
                "From Parking Area Hot",
            ): "hot_parking",
            ("TakeOff", "From Runway"): "runway",
            ("TakeOffGround", "From Ground Area"): "cold_ground",
            (
                "TakeOffGroundHot",
                "From Ground Area Hot",
            ): "hot_ground",
            ("Turning Point", "Turning Point"): "air",
            ("Turning Point", "Fly Over Point"): "air",
        }
        for (point_type, action), expected_mode in valid_pairs.items():
            with self.subTest(point_type=point_type, action=action):
                mission = _semantic_mission()
                group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
                point = group["route"]["points"][0]
                point["type"] = point_type
                point["action"] = action
                if expected_mode in {
                    "cold_parking",
                    "hot_parking",
                    "runway",
                }:
                    point["airdromeId"] = 7
                if expected_mode in {"cold_parking", "hot_parking"}:
                    group["units"][0].update({"parking": 2, "parking_id": "02"})

                first_point = json_to_lua(point)
                self.assertEqual(
                    classify_start_mode(first_point),
                    expected_mode,
                )
                self.assertFalse(has_invalid_start_mode_pair(first_point))
                report = validate_mission_structure(json_to_lua(mission))
                codes = {item["code"] for item in report["diagnostics"]}
                self.assertNotIn("invalid_air_start_mode_pair", codes)
                facts = collect_mission_facts(json_to_lua(mission))
                self.assertEqual(
                    facts["_groups_by_id"][1]["start_mode"],
                    expected_mode,
                )

        known_types = {point_type for point_type, _action in valid_pairs}
        known_actions = {action for _point_type, action in valid_pairs}
        for point_type in known_types:
            for action in known_actions:
                if (point_type, action) in valid_pairs:
                    continue
                point = json_to_lua({"type": point_type, "action": action})
                self.assertEqual(classify_start_mode(point), "other")
                self.assertTrue(has_invalid_start_mode_pair(point))

        mission = _semantic_mission()
        point = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]
        point["type"] = "TakeOffParking"
        point["action"] = "From Runway"
        report = validate_mission_structure(json_to_lua(mission))
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn("invalid_air_start_mode_pair", codes)

        for mode in ("cold_ground", "hot_ground"):
            role = _role_expectation()
            role["start_mode"] = mode
            validate_expectations({"roles": [role]})

    def test_rejects_malformed_or_unresolved_air_start_reference(self) -> None:
        cases = (
            (
                "missing_pair",
                50,
                None,
                "invalid_air_start_facility_reference",
            ),
            (
                "unequal_pair",
                50,
                51,
                "invalid_air_start_facility_reference",
            ),
            (
                "unresolved_pair",
                99,
                99,
                "air_start_link_unit_not_found",
            ),
            (
                "linked_aircraft",
                1,
                1,
                "air_start_link_target_not_facility",
            ),
        )
        for case, helipad_id, link_unit, expected_code in cases:
            with self.subTest(case=case):
                mission = _linked_helicopter_start_mission()
                point = mission["coalition"]["blue"]["country"][0]["helicopter"][
                    "group"
                ][0]["route"]["points"][0]
                if link_unit is None:
                    del point["linkUnit"]
                else:
                    point["helipadId"] = helipad_id
                    point["linkUnit"] = link_unit
                report = validate_mission_structure(json_to_lua(mission))
                codes = {item["code"] for item in report["diagnostics"]}
                self.assertIn(expected_code, codes)

    def test_linked_air_start_target_must_share_coalition(self) -> None:
        mission = _linked_helicopter_start_mission()
        blue_country = mission["coalition"]["blue"]["country"][0]
        static_category = blue_country.pop("static")
        mission["coalition"]["red"] = {
            "country": [{"id": 0, "static": static_category}]
        }

        report = validate_mission_structure(json_to_lua(mission))

        codes = {item["code"] for item in report["diagnostics"]}
        self.assertIn(
            "air_start_link_target_not_same_coalition",
            codes,
        )
        self.assertNotIn("air_start_link_target_not_facility", codes)

    def test_airdrome_parking_start_requires_valid_reference(self) -> None:
        mission = _semantic_mission()
        group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
        point = group["route"]["points"][0]
        point.update(
            {
                "type": "TakeOffParking",
                "action": "From Parking Area",
                "airdromeId": 7,
            }
        )
        group["units"][0].update({"parking": 2, "parking_id": "02"})

        valid = validate_mission_structure(json_to_lua(mission))
        self.assertTrue(valid["valid"])

        del point["airdromeId"]
        invalid = validate_mission_structure(json_to_lua(mission))
        codes = {item["code"] for item in invalid["diagnostics"]}
        self.assertIn("invalid_air_start_facility_reference", codes)

    def test_only_enabled_semantically_valid_tasks_are_actionable(self) -> None:
        def report_for(
            *,
            enabled: bool = True,
            valid_params: bool = True,
            valid_root: bool = True,
        ) -> dict[str, object]:
            mission = _semantic_mission()
            ai_group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][1]
            params: dict[str, object] = {
                "targetTypes": ["Air"],
                "priority": 0 if valid_params else "invalid",
            }
            task = _direct_task("EngageTargets", params, 1)
            task["enabled"] = enabled
            ai_group["route"]["points"][0]["task"] = {
                "id": "ComboTask" if valid_root else "Orbit",
                "params": {"tasks": [task]},
            }
            return validate_mission_structure(
                json_to_lua(mission),
                profile="complete_scenario",
            )

        valid_codes = {item["code"] for item in report_for()["diagnostics"]}
        self.assertNotIn(
            "complete_ai_group_has_no_actionable_task",
            valid_codes,
        )

        for case, kwargs in (
            ("disabled", {"enabled": False}),
            ("invalid_params", {"valid_params": False}),
            ("invalid_root", {"valid_root": False}),
        ):
            with self.subTest(case=case):
                codes = {item["code"] for item in report_for(**kwargs)["diagnostics"]}
                self.assertIn(
                    "complete_ai_group_has_no_actionable_task",
                    codes,
                )

    def test_validates_attack_map_object_and_bombing_runway_contracts(
        self,
    ) -> None:
        mission = _semantic_mission()
        tasks = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
            "route"
        ]["points"][0]["task"]["params"]["tasks"]
        common = {
            "altitude": 0,
            "altitudeEnabled": False,
            "attackQty": 1,
            "attackQtyLimit": False,
            "direction": 0,
            "directionEnabled": False,
            "expend": "Auto",
            "groupAttack": False,
            "weaponType": 9663676414,
        }
        tasks.append(
            _direct_task(
                "AttackMapObject",
                {"x": 1000, "y": 2000, **common},
                7,
            )
        )
        tasks.append(
            _direct_task(
                "BombingRunway",
                {"runwayId": 7, **common},
                8,
            )
        )

        report = validate_mission_structure(json_to_lua(mission))
        self.assertTrue(report["valid"])

        del tasks[6]["params"]["attackQtyLimit"]
        del tasks[7]["params"]["groupAttack"]
        complete = validate_mission_structure(
            json_to_lua(mission),
            profile="complete_scenario",
        )
        missing_paths = {
            item["path"]
            for item in complete["diagnostics"]
            if item["code"] == "complete_missing_task_parameter"
        }
        self.assertTrue(
            any(
                path.endswith("tasks[7].params.attackQtyLimit")
                for path in missing_paths
            )
        )
        self.assertTrue(
            any(path.endswith("tasks[8].params.groupAttack") for path in missing_paths)
        )

        tasks[7]["params"]["runwayId"] = 0
        invalid = validate_mission_structure(json_to_lua(mission))
        codes = {item["code"] for item in invalid["diagnostics"]}
        self.assertIn("invalid_task_parameter", codes)

    def test_role_contract_optionally_asserts_linked_start_ids(self) -> None:
        facts = collect_mission_facts(json_to_lua(_linked_helicopter_start_mission()))
        legacy_role = _role_expectation()

        _, legacy_passed = evaluate_expectations(
            {"roles": [legacy_role]},
            facts,
        )
        self.assertTrue(legacy_passed)

        linked_role = {
            **legacy_role,
            "helipad_id": 50,
            "link_unit": 50,
        }
        checks, linked_passed = evaluate_expectations(
            {"roles": [linked_role]},
            facts,
        )
        self.assertTrue(linked_passed)
        self.assertTrue(any(check["id"].endswith(".helipad_id") for check in checks))
        self.assertTrue(any(check["id"].endswith(".link_unit") for check in checks))

        linked_role["link_unit"] = 51
        _, mismatch_passed = evaluate_expectations(
            {"roles": [linked_role]},
            facts,
        )
        self.assertFalse(mismatch_passed)

    def test_compiled_goal_tables_use_exact_global_goal_keys(self) -> None:
        def goal(
            side: str,
            score: int,
            rules: list[dict[str, object]],
        ) -> dict[str, object]:
            return {
                "side": side,
                "score": score,
                "predicate": "score",
                "comment": f"{side} goal",
                "rules": rules,
            }

        mission = {
            "coalition": {},
            "goals": [
                goal(
                    "OFFLINE",
                    100,
                    [{"predicate": "c_flag_is_true", "flag": 1}],
                ),
                goal("RED", -100, []),
                goal(
                    "BLUE",
                    50,
                    [{"predicate": "c_flag_is_true", "flag": 2}],
                ),
            ],
            "result": {
                "total": 3,
                "offline": {
                    "conditions": {"$fields": [{"key": 1, "value": "return(true)"}]},
                    "actions": {
                        "$fields": [
                            {
                                "key": 1,
                                "value": "a_set_mission_result(100)",
                            }
                        ]
                    },
                    "func": {"$fields": [{"key": 1, "value": "offline func"}]},
                },
                "red": {
                    "conditions": {"$fields": []},
                    "actions": {"$fields": []},
                    "func": {"$fields": []},
                },
                "blue": {
                    "conditions": {"$fields": [{"key": 3, "value": "return(true)"}]},
                    "actions": {
                        "$fields": [
                            {
                                "key": 3,
                                "value": "a_set_mission_result(50)",
                            }
                        ]
                    },
                    "func": {"$fields": [{"key": 3, "value": "blue func"}]},
                },
            },
        }

        report = validate_mission_structure(json_to_lua(mission))

        codes = [item["code"] for item in report["diagnostics"]]
        self.assertEqual(codes.count("goal_has_no_conditions"), 1)
        self.assertNotIn("compiled_goal_key_mismatch", codes)
        self.assertNotIn("noncontiguous_sequence_keys", codes)
        self.assertNotIn("compiled_goal_total_mismatch", codes)

        mission["result"]["blue"]["conditions"]["$fields"][0]["key"] = 2
        invalid = validate_mission_structure(json_to_lua(mission))
        invalid_codes = {item["code"] for item in invalid["diagnostics"]}
        self.assertIn("compiled_goal_key_mismatch", invalid_codes)


if __name__ == "__main__":
    unittest.main()
