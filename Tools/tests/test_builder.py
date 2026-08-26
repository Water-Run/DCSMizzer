from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.builder import (  # noqa: E402
    BuildSpecError,
    build_miz,
    load_build_spec,
    verify_miz,
)
from dcsmizzer import builder as builder_module  # noqa: E402
from dcsmizzer.cli import main  # noqa: E402


def fixture_spec() -> dict[str, object]:
    return {
        "schema": "dcsmizzer.miz-build-spec/v1",
        "seed": 19880728,
        "provenance": {
            "unit_type": "test fixture",
            "payload": "test fixture",
            "airbase": "test fixture",
        },
        "mission": {
            "version": 23,
            "theatre": "FixtureMap",
            "date": {"Year": 1988, "Month": 7, "Day": 28},
            "start_time": 50400,
            "weather": {
                "atmosphere_type": 0,
                "clouds": {
                    "base": 500,
                    "density": 9,
                    "preset": "FixtureRain",
                    "thickness": 1200,
                },
                "wind": {
                    "atGround": {"dir": 240, "speed": 15},
                },
            },
            "sortie": "DictKey_sortie",
            "descriptionText": "DictKey_descriptionText",
            "descriptionBlueTask": "DictKey_descriptionBlueTask",
            "descriptionRedTask": "DictKey_descriptionRedTask",
            "descriptionNeutralsTask": "DictKey_descriptionNeutralsTask",
            "coalition": {
                "blue": {
                    "country": [
                        {
                            "id": 2,
                            "name": "Fixture Country",
                            "plane": {
                                "group": [
                                    {
                                        "groupId": 1,
                                        "name": "Fixture Group",
                                        "task": "CAP",
                                        "route": {
                                            "points": [
                                                {
                                                    "type": "TakeOffParking",
                                                    "action": "From Parking Area",
                                                    "airdromeId": 7,
                                                    "ETA": 4200,
                                                    "x": 1000.0,
                                                    "y": 2000.0,
                                                    "alt": 50,
                                                    "speed": 140,
                                                    "task": {
                                                        "id": "ComboTask",
                                                        "params": {"tasks": []},
                                                    },
                                                }
                                            ]
                                        },
                                        "units": [
                                            {
                                                "unitId": 1,
                                                "name": "Fixture Lead",
                                                "type": "Fixture Plane",
                                                "skill": "Player",
                                                "parking": "12",
                                                "parking_id": "36",
                                                "x": 1000.0,
                                                "y": 2000.0,
                                                "alt": 50,
                                                "heading": 1.5,
                                                "payload": {
                                                    "pylons": {
                                                        "$fields": [
                                                            {
                                                                "key": 1,
                                                                "value": {
                                                                    "CLSID": "{FIXTURE}"
                                                                },
                                                            }
                                                        ]
                                                    }
                                                },
                                            },
                                            {
                                                "unitId": 2,
                                                "name": "Fixture Wingman",
                                                "type": "Fixture Plane",
                                                "skill": "Excellent",
                                                "parking": "13",
                                                "parking_id": "37",
                                                "x": 1010.0,
                                                "y": 2010.0,
                                                "alt": 50,
                                                "heading": 1.5,
                                                "payload": {
                                                    "pylons": {
                                                        "$fields": [
                                                            {
                                                                "key": 1,
                                                                "value": {
                                                                    "CLSID": "{FIXTURE}"
                                                                },
                                                            }
                                                        ]
                                                    }
                                                },
                                            },
                                        ],
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
            "triggers": {"zones": []},
        },
        "logic": {
            "schema": "dcsmizzer.miz-logic/v1",
            "trigger_rules": [
                {
                    "kind": "once",
                    "comment": "Fixture checkpoint",
                    "conditions": [
                        {
                            "predicate": "c_time_after",
                            "seconds": 60,
                        }
                    ],
                    "actions": [
                        {
                            "predicate": "a_set_flag",
                            "flag": 1,
                        }
                    ],
                }
            ],
            "goals": [
                {
                    "side": "OFFLINE",
                    "score": 100,
                    "comment": "Fixture success",
                    "conditions": [
                        {
                            "predicate": "c_flag_is_true",
                            "flag": 1,
                        }
                    ],
                }
            ],
        },
        "options": {},
        "warehouses": {"airports": {}, "warehouses": {}},
        "dictionary": {
            "DictKey_sortie": "Fixture sortie",
            "DictKey_descriptionText": "Fixture narrative",
            "DictKey_descriptionBlueTask": "Fixture blue task",
            "DictKey_descriptionRedTask": "Fixture red task",
            "DictKey_descriptionNeutralsTask": "Fixture neutral task",
        },
        "mapResource": {},
        "resources": [],
        "expect": {
            "theatre": "FixtureMap",
            "mission_version": 23,
            "minimum": {
                "groups": {"plane": 1},
                "units": {"plane": 2},
                "human_slots": {"Player": 1},
                "unit_types": {"Fixture Plane": 2},
                "slots_by_type": {"Fixture Plane": 1},
                "payload_clsids": {"{FIXTURE}": 2},
                "waypoint_actions": {"From Parking Area": 1},
                "start_modes": {"cold_parking": 1},
                "trigger_rules": 1,
                "trigger_conditions": 1,
                "trigger_actions": 1,
                "goals": 1,
                "dictionary_entries": 5,
                "briefing_characters": 20,
                "latest_waypoint_eta_seconds": 4200,
            },
            "exact": {
                "groups": {"plane": 1},
                "units": {"plane": 2},
                "human_slots": {"Player": 1, "Client": 0},
                "unit_types": {"Fixture Plane": 2},
                "slots_by_type": {"Fixture Plane": 1},
                "missing_resource_members": 0,
                "referenced_missing_resources": 0,
            },
            "required": {
                "unit_types": ["Fixture Plane"],
                "payload_clsids": ["{FIXTURE}"],
                "waypoint_actions": ["From Parking Area"],
                "waypoint_task_ids": ["ComboTask"],
                "group_tasks": ["CAP"],
                "start_modes": ["cold_parking"],
                "airdrome_ids": [7],
                "trigger_condition_predicates": ["c_time_after"],
                "trigger_action_predicates": ["a_set_flag"],
                "goal_predicates": ["c_flag_is_true"],
                "briefing_fields": [
                    "sortie",
                    "descriptionText",
                    "descriptionBlueTask",
                    "descriptionRedTask",
                    "descriptionNeutralsTask",
                ],
            },
            "exact_values": [
                {"path": ["date", "Year"], "value": 1988},
                {"path": ["date", "Month"], "value": 7},
                {"path": ["date", "Day"], "value": 28},
                {"path": ["start_time"], "value": 50400},
                {
                    "path": ["weather", "clouds", "preset"],
                    "value": "FixtureRain",
                },
                {
                    "path": [
                        "coalition",
                        "blue",
                        "country",
                        1,
                        "plane",
                        "group",
                        1,
                        "units",
                        1,
                        "type",
                    ],
                    "value": "Fixture Plane",
                },
                {
                    "path": [
                        "coalition",
                        "blue",
                        "country",
                        1,
                        "plane",
                        "group",
                        1,
                        "units",
                        1,
                        "parking",
                    ],
                    "value": "12",
                },
            ],
        },
    }


def complete_fixture_spec() -> dict[str, object]:
    spec = fixture_spec()
    spec["quality"] = {"profile": "complete_scenario"}
    mission = spec["mission"]
    mission["requiredModules"] = {}
    blue = mission["coalition"]["blue"]
    blue.update(
        {
            "name": "blue",
            "bullseye": {"x": 0, "y": 0},
            "nav_points": [],
        }
    )
    mission["coalition"].update(
        {
            "red": {
                "name": "red",
                "bullseye": {"x": 0, "y": 0},
                "country": [],
                "nav_points": [],
            },
            "neutrals": {
                "name": "neutrals",
                "bullseye": {"x": 0, "y": 0},
                "country": [],
                "nav_points": [],
            },
        }
    )
    mission.update(
        {
            "coalitions": {
                "blue": [2],
                "red": [],
                "neutrals": [],
            },
            "currentKey": 100,
            "failures": {},
            "forcedOptions": {},
            "groundControl": {
                "isPilotControlVehicles": False,
                "roles": {
                    role: {"blue": {}, "red": {}}
                    for role in (
                        "artillery_commander",
                        "forward_observer",
                        "instructor",
                        "observer",
                    )
                },
            },
            "map": {
                "centerX": 0,
                "centerY": 0,
                "zoom": 100000,
            },
            "maxDictId": 5,
            "pictureFileNameB": {},
            "pictureFileNameR": {},
        }
    )
    mission["weather"]["wind"].update(
        {
            "at2000": {"dir": 245, "speed": 20},
            "at8000": {"dir": 250, "speed": 30},
        }
    )
    group = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0]
    group.update(
        {
            "communication": True,
            "frequency": 251,
            "modulation": 0,
            "radioSet": False,
            "start_time": 0,
        }
    )
    point = group["route"]["points"][0]
    point.update(
        {
            "alt_type": "BARO",
            "ETA": 0,
            "ETA_locked": True,
            "speed_locked": True,
        }
    )
    spec["expect"]["minimum"]["latest_waypoint_eta_seconds"] = 0
    for index, unit in enumerate(group["units"], start=1):
        unit.update(
            {
                "alt_type": "BARO",
                "speed": 0,
                "callsign": index,
                "onboard_num": f"0{index}",
            }
        )
        unit["payload"].update(
            {
                "fuel": 1000,
                "chaff": 30,
                "flare": 30,
                "gun": 100,
            }
        )
    spec["logic"]["trigger_rules"].append(
        {
            "kind": "once",
            "comment": "Fixture failure checkpoint",
            "conditions": [
                {
                    "predicate": "c_time_after",
                    "seconds": 4200,
                },
                {
                    "predicate": "c_flag_is_false",
                    "flag": 1,
                },
            ],
            "actions": [
                {
                    "predicate": "a_set_flag",
                    "flag": 2,
                }
            ],
        }
    )
    spec["logic"]["trigger_rules"][0]["conditions"].append(
        {
            "predicate": "c_flag_is_false",
            "flag": 2,
        }
    )
    spec["logic"]["trigger_rules"].reverse()
    spec["expect"]["required"]["trigger_condition_predicates"].append("c_flag_is_false")
    spec["logic"]["goals"].append(
        {
            "side": "OFFLINE",
            "score": -100,
            "comment": "Fixture failure",
            "conditions": [
                {
                    "predicate": "c_flag_is_true",
                    "flag": 2,
                }
            ],
        }
    )
    spec["options"] = {
        "VR": {
            "bloom": True,
            "box_mouse_cursor": True,
            "enable": False,
            "mirror_crop": False,
            "mirror_source": 0,
            "mirror_use_DCS_resolution": False,
            "msaaMaskSize": 0.42,
            "pixel_density": 1,
            "use_mouse": True,
        },
        "difficulty": {
            "birds": 0,
            "easyCommunication": False,
            "easyFlight": False,
            "externalViews": True,
            "fuel": False,
            "geffect": "realistic",
            "immortal": False,
            "labels": 0,
            "map": True,
            "optionsView": "optview_all",
            "padlock": False,
            "permitCrash": True,
            "radio": False,
            "spectatorExternalViews": True,
            "tips": False,
            "units": "imperial",
            "userMarks": True,
            "weapons": False,
        },
        "format": 1,
        "graphics": {
            "ScreenshotExt": "jpg",
            "clouds": 1,
            "defaultFOV": 78,
            "fullScreen": False,
            "multiMonitorSetup": "1camera",
            "outputGamma": 2.2,
            "preloadRadius": 150000,
            "shadows": 2,
            "sync": False,
            "terrainTextures": "min",
            "textures": 0,
            "visibRange": "High",
            "water": 2,
        },
        "miscellaneous": {
            "Coordinate_Display": "Lat Long",
            "F2_view_effects": 1,
            "accidental_failures": False,
            "f10_awacs": True,
            "force_feedback_enabled": True,
            "headmove": False,
        },
        "playerName": "DCSMizzer",
        "plugins": {},
        "sound": {
            "cockpit": 100,
            "gui": 100,
            "headphones": 100,
            "hp_output": "",
            "main_output": "",
            "main_layout": "",
            "microphone_use": 2,
            "music": 60,
            "play_audio_while_minimized": False,
            "radioSpeech": True,
            "subtitles": True,
            "switches": 100,
            "voiceChatInSensitivity": -50,
            "voiceChatInVolume": 50,
            "voice_chat": True,
            "voice_chat_output": "",
            "voice_chat_input": "",
            "volume": 80,
            "world": 100,
        },
        "views": {
            "cockpit": {
                "avionics": 1,
                "avionicsMFDEveryFrame": False,
                "mirrors": False,
                "mirrorsEveryFrame": False,
                "mirrorsResolution": 1,
                "mirrorsSequentialRendering": True,
            }
        },
    }
    warehouse = {
        "OperatingLevel_Air": 10,
        "OperatingLevel_Eqp": 10,
        "OperatingLevel_Fuel": 10,
        "aircrafts": {"planes": {}, "helicopters": {}},
        "allowHotStart": False,
        "coalition": "NEUTRAL",
        "diesel": {"InitFuel": 100},
        "dynamicCargo": True,
        "dynamicSpawn": False,
        "gasoline": {"InitFuel": 100},
        "jet_fuel": {"InitFuel": 100},
        "methanol_mixture": {"InitFuel": 100},
        "periodicity": 30,
        "size": 100,
        "speed": 16.666666,
        "suppliers": {},
        "unlimitedAircrafts": True,
        "unlimitedFuel": True,
        "unlimitedMunitions": True,
        "weapons": {},
    }
    spec["warehouses"] = {
        "airports": {
            "$fields": [
                {
                    "key": 7,
                    "value": warehouse,
                }
            ]
        },
        "warehouses": {},
    }
    spec["expect"]["roles"] = [
        {
            "role": "player_flight",
            "group_id": 1,
            "side": "blue",
            "category": "plane",
            "group_task": "CAP",
            "unit_types": {"Fixture Plane": 2},
            "human_slots": {"Player": 1, "Client": 0},
            "start_mode": "cold_parking",
            "airdrome_id": 7,
            "late_activation": False,
            "mission_elapsed_start_seconds": 0,
            "minimum_waypoints": 1,
            "minimum_route_span_seconds": 0,
            "required_waypoint_task_ids": ["ComboTask"],
            "required_waypoint_actions": ["From Parking Area"],
            "required_task_group_ids": [],
        }
    ]
    return spec


class MizBuilderTests(unittest.TestCase):
    def _assert_cli_spec_input_rejected(
        self,
        root: Path,
        spec_path: Path,
        message: str,
    ) -> None:
        new_output = root / "new-output.miz"
        existing_output = root / "existing-output.miz"
        existing_bytes = b"existing output must survive"
        existing_output.write_bytes(existing_bytes)
        artifact = root / "artifact.miz"
        artifact_bytes = b"verification input must survive"
        artifact.write_bytes(artifact_bytes)
        cases = (
            (
                "build-new",
                ["build-miz", str(spec_path), str(new_output)],
            ),
            (
                "build-force",
                [
                    "build-miz",
                    str(spec_path),
                    str(existing_output),
                    "--force",
                ],
            ),
            (
                "audit",
                [
                    "audit-spec",
                    str(spec_path),
                    "--dcs-root",
                    str(root / "dcs"),
                    "--pydcs-root",
                    str(root / "pydcs"),
                ],
            ),
            (
                "verify",
                [
                    "verify-miz",
                    str(artifact),
                    "--spec",
                    str(spec_path),
                ],
            ),
        )
        for name, argv in cases:
            with self.subTest(command=name):
                stdout = io.StringIO()
                stderr = io.StringIO()
                exit_code = main(argv, stdout=stdout, stderr=stderr)
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(message, stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse(new_output.exists())
        self.assertEqual(existing_output.read_bytes(), existing_bytes)
        self.assertEqual(artifact.read_bytes(), artifact_bytes)

    def test_builder_writes_deterministic_archive_and_verifies_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            first = root / "first.miz"
            second = root / "second.miz"
            spec_path.write_text(
                json.dumps(fixture_spec(), ensure_ascii=False),
                encoding="utf-8",
            )

            first_report, first_ok = build_miz(spec_path, first)
            second_report, second_ok = build_miz(spec_path, second)

            self.assertTrue(first_ok)
            self.assertTrue(second_ok)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertTrue(first_report["validation"]["archive_valid"])
            self.assertTrue(first_report["validation"]["all_core_tables_equal"])
            self.assertTrue(first_report["validation"]["contract_valid"])
            self.assertTrue(first_report["validation"]["review_warnings_clear"])
            self.assertEqual(
                first_report["contract"]["coverage_warnings"],
                [],
            )
            self.assertTrue(first_report["limited_structure"]["valid"])
            self.assertIsNone(first_report["validation"]["runtime_valid"])
            self.assertFalse(first_report["replaced_existing_output"])
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.read("theatre"), b"FixtureMap")
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "mission",
                        "options",
                        "warehouses",
                        "l10n/DEFAULT/dictionary",
                        "l10n/DEFAULT/mapResource",
                        "theatre",
                    },
                )

    def test_verify_detects_artifact_that_no_longer_matches_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            _report, ok = build_miz(spec_path, output)
            self.assertTrue(ok)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(output, "a") as archive:
                    archive.writestr(
                        "mission",
                        b'mission = { version = 23, theatre = "WrongMap" }',
                    )

            report, verified = verify_miz(output, spec_path)

            self.assertFalse(verified)
            self.assertFalse(report["validation"]["all_core_tables_equal"])
            self.assertFalse(report["validation"]["contract_valid"])

    def test_verify_rejects_member_not_declared_by_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            _report, ok = build_miz(spec_path, output)
            self.assertTrue(ok)
            with zipfile.ZipFile(output, "a") as archive:
                archive.writestr("unexpected.bin", b"not declared")

            report, verified = verify_miz(output, spec_path)

        self.assertFalse(verified)
        self.assertFalse(report["validation"]["exact_member_set"])
        self.assertEqual(report["unexpected_members"], ["unexpected.bin"])

    def test_verify_archive_error_never_reads_member_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            _report, built = build_miz(spec_path, output)
            self.assertTrue(built)
            with zipfile.ZipFile(output, "a") as archive:
                archive.writestr("../escape.bin", b"unsafe")

            with mock.patch(
                "dcsmizzer.builder.analyse_miz",
                side_effect=AssertionError("member reads must be blocked"),
            ) as analyse:
                report, verified = verify_miz(output, spec_path)

        self.assertFalse(verified)
        self.assertTrue(report["validation"]["archive_content_read_blocked"])
        analyse.assert_not_called()

    def test_builder_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            output.write_bytes(b"keep")

            with self.assertRaises(BuildSpecError):
                build_miz(spec_path, output)

            self.assertEqual(output.read_bytes(), b"keep")

    def test_builder_rejects_live_and_dangling_output_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            target = root / "target.miz"
            target.write_bytes(b"target must not change")
            live_link = root / "live.miz"
            dangling_link = root / "dangling.miz"
            try:
                os.symlink(
                    target,
                    live_link,
                    target_is_directory=False,
                )
                os.symlink(
                    root / "missing-target.miz",
                    dangling_link,
                    target_is_directory=False,
                )
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

            self.assertTrue(live_link.is_symlink())
            self.assertTrue(dangling_link.is_symlink())
            self.assertFalse(dangling_link.exists())
            for output in (live_link, dangling_link):
                with self.subTest(output=output.name):
                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "must not be a symbolic link",
                    ) as captured:
                        build_miz(spec_path, output, force=True)
                    self.assertNotIn(str(root), str(captured.exception))

            self.assertEqual(target.read_bytes(), b"target must not change")
            self.assertTrue(live_link.is_symlink())
            self.assertTrue(dangling_link.is_symlink())

    def test_candidate_handle_stays_open_through_bound_verification(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            original_verify = builder_module._verify
            observations: list[tuple[bool, bool]] = []

            def observe_verify(
                miz_file: object,
                *args: object,
                **kwargs: object,
            ) -> tuple[dict[str, object], bool]:
                descriptor = miz_file.fileno()
                opened = os.fstat(descriptor)
                candidates = list(root.glob(f".{output.name}.*.tmp"))
                observations.append(
                    (
                        not miz_file.closed,
                        len(candidates) == 1
                        and os.path.samestat(
                            opened,
                            candidates[0].lstat(),
                        ),
                    )
                )
                return original_verify(miz_file, *args, **kwargs)

            with mock.patch(
                "dcsmizzer.builder._verify",
                side_effect=observe_verify,
            ):
                report, valid = build_miz(spec_path, output)

        self.assertTrue(valid)
        self.assertEqual(observations, [(True, True)])
        self.assertTrue(report["candidate"]["validated_from_original_open_handle"])
        self.assertTrue(
            report["publication"]["candidate_identity_bound_to_open_handle"]
        )
        self.assertFalse(report["publication"]["atomic"])
        self.assertTrue(report["publication"]["filesystem_path_update_atomic"])
        self.assertTrue(report["publication"]["trusted_directory_required"])

    def test_concurrent_staging_symlink_swap_cannot_publish_victim(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            victim = root / "victim.bin"
            original_output = b"existing output"
            victim_bytes = b"victim must not change"
            output.write_bytes(original_output)
            victim.write_bytes(victim_bytes)
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            original_link = os.link
            staging_ready = threading.Event()
            staging_swapped = threading.Event()
            attacker_errors: list[BaseException] = []

            def racing_link(
                source: str | os.PathLike[str],
                destination: str | os.PathLike[str],
                *args: object,
                **kwargs: object,
            ) -> None:
                original_link(source, destination, *args, **kwargs)
                if str(destination).endswith(".publish"):
                    staging_ready.set()
                    if not staging_swapped.wait(timeout=5):
                        raise AssertionError("staging attacker did not finish")

            def attacker() -> None:
                try:
                    if not staging_ready.wait(timeout=5):
                        raise AssertionError("publication staging was not created")
                    staging = next(root.glob("*.publish"))
                    staging.unlink()
                    os.symlink(
                        victim,
                        staging,
                        target_is_directory=False,
                    )
                except BaseException as error:
                    attacker_errors.append(error)
                finally:
                    staging_swapped.set()

            attacker_thread = threading.Thread(target=attacker)
            attacker_thread.start()
            try:
                with mock.patch(
                    "dcsmizzer.builder.os.link",
                    side_effect=racing_link,
                ):
                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "publication staging path does not identify",
                    ) as captured:
                        build_miz(spec_path, output, force=True)
            finally:
                staging_swapped.set()
                attacker_thread.join(timeout=5)

            self.assertFalse(attacker_thread.is_alive())
            self.assertEqual(attacker_errors, [])
            self.assertNotIn(str(root), str(captured.exception))
            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(victim.read_bytes(), victim_bytes)

    def test_postcheck_staging_swap_rolls_back_previous_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            original_output = b"existing output"
            attacker_payload = b"attacker-controlled publication"
            output.write_bytes(original_output)
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            original_require = builder_module._require_regular_identity
            staging_checks = 0

            def swap_after_final_staging_check(
                path: Path,
                expected: os.stat_result,
                message: str,
            ) -> os.stat_result:
                nonlocal staging_checks
                result = original_require(path, expected, message)
                if path.name.endswith(".publish"):
                    staging_checks += 1
                    if staging_checks == 2:
                        path.unlink()
                        path.write_bytes(attacker_payload)
                return result

            with mock.patch(
                "dcsmizzer.builder._require_regular_identity",
                side_effect=swap_after_final_staging_check,
            ):
                with self.assertRaisesRegex(
                    BuildSpecError,
                    "published path does not identify",
                ):
                    build_miz(spec_path, output, force=True)

            self.assertEqual(staging_checks, 2)
            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(
                list(root.glob(f".{output.name}.*")),
                [],
            )

    def test_postpublication_output_swap_rolls_back_without_touching_victim(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            victim = root / "victim.bin"
            original_output = b"existing output"
            victim_bytes = b"victim must not change"
            output.write_bytes(original_output)
            victim.write_bytes(victim_bytes)
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            original_replace = os.replace

            def swap_published_output(
                source: str | os.PathLike[str],
                destination: str | os.PathLike[str],
            ) -> None:
                original_replace(source, destination)
                if str(source).endswith(".publish"):
                    Path(destination).unlink()
                    os.symlink(
                        victim,
                        destination,
                        target_is_directory=False,
                    )

            try:
                with mock.patch(
                    "dcsmizzer.builder.os.replace",
                    side_effect=swap_published_output,
                ):
                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "published path does not identify",
                    ):
                        build_miz(spec_path, output, force=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(victim.read_bytes(), victim_bytes)
            self.assertFalse(output.is_symlink())

    @unittest.skipIf(
        os.name == "nt",
        "Windows denies replacement of the open mkstemp path",
    )
    def test_concurrent_candidate_symlink_swap_fails_before_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            victim = root / "victim.bin"
            original_output = b"existing output"
            victim_bytes = b"victim must not change"
            output.write_bytes(original_output)
            victim.write_bytes(victim_bytes)
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            original_verify = builder_module._verify
            verification_done = threading.Event()
            candidate_swapped = threading.Event()
            attacker_errors: list[BaseException] = []

            def pause_after_verify(
                *args: object,
                **kwargs: object,
            ) -> tuple[dict[str, object], bool]:
                result = original_verify(*args, **kwargs)
                verification_done.set()
                if not candidate_swapped.wait(timeout=5):
                    raise AssertionError("candidate attacker did not finish")
                return result

            def attacker() -> None:
                try:
                    if not verification_done.wait(timeout=5):
                        raise AssertionError("candidate was not verified")
                    candidate = next(root.glob(f".{output.name}.*.tmp"))
                    candidate.unlink()
                    os.symlink(
                        victim,
                        candidate,
                        target_is_directory=False,
                    )
                except BaseException as error:
                    attacker_errors.append(error)
                finally:
                    candidate_swapped.set()

            attacker_thread = threading.Thread(target=attacker)
            attacker_thread.start()
            try:
                with mock.patch(
                    "dcsmizzer.builder._verify",
                    side_effect=pause_after_verify,
                ):
                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "artifact path changed",
                    ):
                        build_miz(spec_path, output, force=True)
            finally:
                candidate_swapped.set()
                attacker_thread.join(timeout=5)

            self.assertFalse(attacker_thread.is_alive())
            self.assertEqual(attacker_errors, [])
            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(victim.read_bytes(), victim_bytes)

    def test_builder_collision_and_os_errors_do_not_leak_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collision = root / "collision.miz"
            collision_bytes = json.dumps(fixture_spec()).encode("utf-8")
            collision.write_bytes(collision_bytes)

            with self.assertRaisesRegex(
                BuildSpecError,
                "cannot overwrite the build specification",
            ) as collision_error:
                build_miz(collision, collision, force=True)
            self.assertNotIn(str(root), str(collision_error.exception))
            self.assertEqual(collision.read_bytes(), collision_bytes)

            spec_path = root / "mission.json"
            output = root / "mission.miz"
            output.write_bytes(b"old")
            spec_path.write_text(
                json.dumps(complete_fixture_spec()),
                encoding="utf-8",
            )
            private_os_error = OSError(str(root / ".mission.miz.private.tmp"))
            with mock.patch(
                "dcsmizzer.builder.os.replace",
                side_effect=private_os_error,
            ):
                with self.assertRaisesRegex(
                    BuildSpecError,
                    "candidate construction or guarded publication failed",
                ) as publication_error:
                    build_miz(spec_path, output, force=True)
            self.assertNotIn(str(root), str(publication_error.exception))
            self.assertEqual(output.read_bytes(), b"old")

            private_read_error = OSError(str(root / "private-spec-location.json"))
            with mock.patch(
                "dcsmizzer.builder.os.open",
                side_effect=private_read_error,
            ):
                with self.assertRaisesRegex(
                    BuildSpecError,
                    "cannot read the build specification",
                ) as read_error:
                    load_build_spec(
                        spec_path,
                        require_resource_files=True,
                    )
            self.assertNotIn(str(root), str(read_error.exception))

    def test_build_spec_reader_rejects_linked_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.json"
            linked = root / "linked.json"
            target.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            try:
                linked.symlink_to(target)
            except OSError as error:
                self.skipTest(f"file symlinks unavailable: {type(error).__name__}")

            with self.assertRaisesRegex(
                BuildSpecError,
                "safe regular file",
            ):
                load_build_spec(linked, require_resource_files=True)

    @unittest.skipUnless(os.name == "nt", "Windows ADS regression")
    def test_build_spec_reader_rejects_windows_alternate_data_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = root / "host.json"
            host.write_text("host", encoding="utf-8")
            stream = Path(f"{host}:spec")
            try:
                stream.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            except OSError as error:
                self.skipTest(
                    "alternate data streams unavailable: "
                    f"{type(error).__name__}"
                )

            with self.assertRaisesRegex(BuildSpecError, "safe regular file"):
                load_build_spec(stream, require_resource_files=True)

    def test_builder_rejects_spec_change_after_candidate_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            original_bytes = json.dumps(fixture_spec()).encode("utf-8")
            changed_bytes = original_bytes + b" "
            spec_path.write_bytes(original_bytes)
            original_verify = builder_module._verify

            def verify_then_change_spec(*args: object, **kwargs: object) -> object:
                result = original_verify(*args, **kwargs)
                spec_path.write_bytes(changed_bytes)
                return result

            with (
                mock.patch(
                    "dcsmizzer.builder._verify",
                    side_effect=verify_then_change_spec,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "build specification changed after it was loaded",
                ),
            ):
                build_miz(spec_path, output)

            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_verify_rejects_spec_change_during_artifact_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            original_bytes = json.dumps(fixture_spec()).encode("utf-8")
            spec_path.write_bytes(original_bytes)
            _report, built = build_miz(spec_path, output)
            self.assertTrue(built)
            artifact_bytes = output.read_bytes()
            original_verify = builder_module._verify

            def verify_then_change_spec(*args: object, **kwargs: object) -> object:
                result = original_verify(*args, **kwargs)
                spec_path.write_bytes(original_bytes + b" ")
                return result

            with (
                mock.patch(
                    "dcsmizzer.builder._verify",
                    side_effect=verify_then_change_spec,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "build specification changed after it was loaded",
                ),
            ):
                verify_miz(output, spec_path)

            self.assertEqual(output.read_bytes(), artifact_bytes)

    def test_deep_json_is_rejected_before_all_spec_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "deep.json"
            depth = 10_000
            spec_path.write_text(
                '{"nested":' * depth + "null" + "}" * depth,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BuildSpecError,
                "JSON nesting depth limit",
            ):
                load_build_spec(
                    spec_path,
                    require_resource_files=True,
                )
            self._assert_cli_spec_input_rejected(
                root,
                spec_path,
                "JSON nesting depth limit",
            )

    def test_oversized_json_is_rejected_before_all_spec_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "oversized.json"
            with spec_path.open("wb") as stream:
                stream.truncate(builder_module.MAX_BUILD_SPEC_BYTES + 1)

            with self.assertRaisesRegex(
                BuildSpecError,
                "byte input limit",
            ):
                load_build_spec(
                    spec_path,
                    require_resource_files=True,
                )
            self._assert_cli_spec_input_rejected(
                root,
                spec_path,
                "byte input limit",
            )

    def test_recursion_error_is_normalized_to_build_spec_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec_path = Path(temp_dir) / "mission.json"
            spec_path.write_text(
                json.dumps(fixture_spec()),
                encoding="utf-8",
            )
            with mock.patch.object(
                builder_module.json,
                "loads",
                side_effect=RecursionError("synthetic parser recursion"),
            ):
                with self.assertRaisesRegex(
                    BuildSpecError,
                    "safe processing depth",
                ):
                    load_build_spec(
                        spec_path,
                        require_resource_files=True,
                    )

    def test_extreme_integer_is_rejected_before_all_spec_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "extreme-integer.json"
            spec_path.write_text(
                '{"schema":"dcsmizzer.miz-build-spec/v1","seed":' + "9" * 5000 + "}",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BuildSpecError,
                "finite numeric range",
            ):
                load_build_spec(
                    spec_path,
                    require_resource_files=True,
                )
            self._assert_cli_spec_input_rejected(
                root,
                spec_path,
                "finite numeric range",
            )

    def test_long_duplicate_and_unknown_keys_have_bounded_errors(self) -> None:
        long_key = "x" * 1_000_000
        sources = (
            (
                "duplicate",
                '{"schema":"dcsmizzer.miz-build-spec/v1","'
                + long_key
                + '":0,"'
                + long_key
                + '":1}',
                "duplicate JSON key",
            ),
            (
                "unknown",
                '{"schema":"dcsmizzer.miz-build-spec/v1","' + long_key + '":0}',
                "unknown key",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name, source, expected in sources:
                with self.subTest(name=name):
                    spec_path = root / f"{name}.json"
                    spec_path.write_text(source, encoding="utf-8")

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        expected,
                    ) as caught:
                        load_build_spec(
                            spec_path,
                            require_resource_files=True,
                        )

                    message = str(caught.exception)
                    self.assertLessEqual(len(message), 512)
                    self.assertIn("truncated", message)

    def test_json_depth_prescan_ignores_syntax_inside_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = fixture_spec()
            literal = '[{"quoted": "\\\\\\""}]' * 256
            spec["provenance"]["json_syntax_literal"] = literal
            spec_path = Path(temp_dir) / "mission.json"
            spec_path.write_text(
                json.dumps(spec),
                encoding="utf-8",
            )

            loaded = load_build_spec(
                spec_path,
                require_resource_files=True,
            )

        self.assertEqual(
            loaded.provenance["json_syntax_literal"],
            literal,
        )

    def test_non_finite_json_overflow_is_rejected_before_publication(
        self,
    ) -> None:
        source = json.dumps(fixture_spec())
        marker = '"unit_type": "test fixture"'
        self.assertIn(marker, source)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for token in ("1e999", "-1e999"):
                with self.subTest(token=token):
                    spec_path = root / f"overflow-{token[0]}.json"
                    output = root / f"overflow-{token[0]}.miz"
                    spec_path.write_text(
                        source.replace(
                            marker,
                            f'"unit_type": {token}',
                            1,
                        ),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "non-finite JSON number",
                    ):
                        load_build_spec(
                            spec_path,
                            require_resource_files=True,
                        )

                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    exit_code = main(
                        ["build-miz", str(spec_path), str(output)],
                        stdout=stdout,
                        stderr=stderr,
                    )

                    self.assertEqual(exit_code, 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertIn(
                        "non-finite JSON number",
                        stderr.getvalue(),
                    )
                    self.assertFalse(output.exists())

    def test_builder_rejects_duplicate_unit_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            groups = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ]
            groups[0]["units"][1]["unitId"] = 1
            spec_path = root / "mission.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "duplicate_unit_id",
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_builder_rejects_string_keys_in_dcs_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            point = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["route"]["points"][0]
            point["task"]["params"]["tasks"] = {
                "1": {
                    "id": "WrappedAction",
                    "enabled": True,
                }
            }
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(spec),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BuildSpecError,
                "nonnumeric_sequence_key",
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_route_rejects_conflicting_post_start_locks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            points = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["route"]["points"]
            second = json.loads(json.dumps(points[0]))
            second.update(
                {
                    "type": "Turning Point",
                    "action": "Turning Point",
                    "ETA": 4800,
                    "x": 3000,
                    "y": 4000,
                    "ETA_locked": True,
                    "speed_locked": True,
                }
            )
            points.append(second)
            spec_path = root / "conflicting-locks.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                (
                    r"complete_conflicting_waypoint_locks@"
                    r"\$\.coalition\.blue.*route\.points\[2\]"
                ),
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_route_requires_both_first_waypoint_locks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            point = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["route"]["points"][0]
            point["ETA_locked"] = False
            spec_path = root / "first-locks.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                (
                    r"complete_invalid_first_waypoint_locks@"
                    r"\$\.coalition\.blue.*route\.points\[1\]"
                ),
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_human_route_starts_at_mission_elapsed_zero(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["start_time"] = 50400
            group["route"]["points"][0]["ETA"] = 50400
            spec["expect"]["roles"][0]["mission_elapsed_start_seconds"] = 50400
            spec_path = root / "absolute-clock-route.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                (
                    r"complete_human_start_not_zero@"
                    r"\$\.coalition\.blue.*route\.points\[1\]\.ETA"
                ),
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_human_group_cannot_be_late_activated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["lateActivation"] = True
            spec["expect"]["roles"][0]["late_activation"] = True
            spec["logic"]["trigger_rules"][0]["actions"].append(
                {
                    "predicate": "a_activate_group",
                    "group": 1,
                }
            )
            spec_path = root / "late-human.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                (
                    r"complete_human_late_activation@"
                    r"\$\.coalition\.blue.*lateActivation"
                ),
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_late_activation_requires_a_boolean(self) -> None:
        for invalid in (1, "true"):
            with self.subTest(invalid=invalid):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                        "group"
                    ][0]
                    group["lateActivation"] = invalid
                    spec_path = root / "invalid-late-activation.json"
                    spec_path.write_text(
                        json.dumps(spec),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        (
                            r"complete_invalid_late_activation@"
                            r"\$\.coalition\.blue.*lateActivation"
                        ),
                    ):
                        build_miz(spec_path, root / "mission.miz")

    def test_complete_extreme_bombing_coordinate_fails_cleanly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            tasks = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["route"]["points"][0]["task"]["params"]["tasks"]
            tasks.append(
                {
                    "id": "Bombing",
                    "number": 1,
                    "auto": False,
                    "enabled": True,
                    "params": {
                        "x": 10**400,
                        "y": 2000,
                        "altitude": 1000,
                        "altitudeEnabled": False,
                        "attackQty": 1,
                        "attackQtyLimit": False,
                        "direction": 0,
                        "directionEnabled": False,
                        "expend": "Auto",
                        "groupAttack": False,
                        "weaponType": 9663676414,
                    },
                }
            )
            spec_path = root / "extreme-bombing.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "JSON integer exceeds the finite numeric range",
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_extreme_second_waypoint_fails_cleanly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            first = group["route"]["points"][0]
            first["type"] = "Turning Point"
            first["action"] = "Turning Point"
            first.pop("airdromeId")
            first["speed"] = 140
            for unit in group["units"]:
                unit["speed"] = 140
            group["route"]["points"].append(
                {
                    "x": 10**400,
                    "y": 2000,
                    "alt": 1000,
                    "speed": 140,
                    "ETA": 60,
                    "alt_type": "BARO",
                    "type": "Turning Point",
                    "action": "Turning Point",
                    "ETA_locked": False,
                    "speed_locked": True,
                    "task": {
                        "id": "ComboTask",
                        "params": {"tasks": []},
                    },
                }
            )
            spec_path = root / "extreme-waypoint.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "JSON integer exceeds the finite numeric range",
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_complete_roles_bind_mission_elapsed_start_offsets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            del spec["expect"]["roles"][0]["mission_elapsed_start_seconds"]
            spec_path = root / "missing-role-start-offset.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(
                spec_path,
                root / "mission.miz",
            )

        self.assertFalse(valid)
        self.assertIn(
            "role_elapsed_starts_not_exactly_asserted",
            report["contract"]["coverage_warnings"],
        )

    def test_builder_warns_for_unlinked_late_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["lateActivation"] = True
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(spec),
                encoding="utf-8",
            )

            report, valid = build_miz(
                spec_path,
                root / "mission.miz",
            )

        self.assertTrue(valid)
        self.assertFalse(report["validation"]["review_warnings_clear"])
        self.assertIn(
            "late_activation_not_statically_linked",
            {item["code"] for item in report["limited_structure"]["diagnostics"]},
        )

    def test_builder_reports_sparse_contract_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["expect"] = {}
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(spec),
                encoding="utf-8",
            )

            report, valid = build_miz(
                spec_path,
                root / "mission.miz",
            )

        self.assertTrue(valid)
        self.assertFalse(report["validation"]["review_warnings_clear"])
        self.assertIn(
            "human_slot_types_not_exactly_asserted",
            report["contract"]["coverage_warnings"],
        )
        self.assertIn(
            "weather_not_exactly_asserted",
            report["contract"]["coverage_warnings"],
        )

    def test_empty_trigger_and_goal_tables_never_clear_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec.pop("logic")
            spec["expect"] = {}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(spec_path, root / "mission.miz")

        self.assertTrue(valid)
        self.assertFalse(report["validation"]["review_warnings_clear"])
        for warning in (
            "trigger_rules_absent",
            "trigger_conditions_absent",
            "trigger_actions_absent",
            "goals_absent",
        ):
            self.assertIn(
                warning,
                report["contract"]["coverage_warnings"],
            )

    def test_builder_rejects_stringified_callsign_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            unit = spec["mission"]["coalition"]["blue"]["country"][0]["plane"]["group"][
                0
            ]["units"][0]
            unit["callsign"] = {
                "1": 1,
                "2": 1,
                "3": 1,
                "name": "Fixture 1-1",
            }
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(spec),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BuildSpecError,
                "stringified_numeric_callsign_key",
            ):
                build_miz(spec_path, root / "mission.miz")

    def test_builder_rejects_logic_conflicts_and_unknown_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mission"]["trigrules"] = []
            conflict_path = root / "conflict.json"
            conflict_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(BuildSpecError, "cannot be combined"):
                build_miz(conflict_path, root / "conflict.miz")

            spec = fixture_spec()
            spec["logic"]["trigger_rules"][0]["conditions"].append(
                {"predicate": "c_unit_dead", "unit": 999}
            )
            reference_path = root / "reference.json"
            reference_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "unknown_logic_unit_reference",
            ):
                build_miz(reference_path, root / "reference.miz")

    def test_builder_requires_both_warehouse_registries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["warehouses"] = {"airports": {}}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "warehouses.warehouses",
            ):
                build_miz(spec_path, root / "fixture.miz")

    def test_builder_rejects_missing_or_unsafe_resource(self) -> None:
        for member in ("../escape.lua", "mission"):
            with self.subTest(member=member):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = fixture_spec()
                    spec["resources"] = [{"member": member, "source": "missing.bin"}]
                    spec_path = root / "mission.json"
                    spec_path.write_text(json.dumps(spec), encoding="utf-8")

                    with self.assertRaises(BuildSpecError):
                        build_miz(spec_path, root / "mission.miz")

    def test_verify_compares_packaged_resource_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            resource.write_bytes(b"original resource")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, built = build_miz(spec_path, output)
            resource.write_bytes(b"changed resource")
            changed_report, verified = verify_miz(output, spec_path)

        self.assertTrue(built)
        self.assertTrue(report["validation"]["all_resources_equal"])
        self.assertTrue(
            report["validation"]["resource_inputs_identity_bound_to_open_handles"]
        )
        self.assertTrue(report["validation"]["resource_inputs_content_bound_to_sha256"])
        self.assertEqual(
            report["resource_inputs"],
            [
                {
                    "member": "briefing.bin",
                    "size_bytes": len(b"original resource"),
                    "sha256": hashlib.sha256(b"original resource").hexdigest(),
                }
            ],
        )
        self.assertFalse(verified)
        self.assertFalse(changed_report["validation"]["all_resources_equal"])
        self.assertEqual(
            changed_report["resource_inputs"][0]["sha256"],
            hashlib.sha256(b"changed resource").hexdigest(),
        )
        self.assertFalse(changed_report["resource_equality"]["briefing.bin"])

    def test_builder_rejects_same_size_resource_hardlink_identity_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            attacker_source = root / "attacker-source.bin"
            attacker_hardlink = root / "attacker-hardlink.bin"
            trusted_bytes = b"trusted-resource"
            attacker_bytes = b"hostile-resource"
            self.assertEqual(len(trusted_bytes), len(attacker_bytes))
            resource.write_bytes(trusted_bytes)
            attacker_source.write_bytes(attacker_bytes)
            try:
                os.link(attacker_source, attacker_hardlink)
            except OSError as error:
                self.skipTest(f"hard links unavailable: {type(error).__name__}")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            canonical_resource = resource.resolve()
            original_write = builder_module._write_miz
            original_lstat_optional = builder_module._lstat_optional
            swap_visible = False

            def expose_swap_before_write(
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal swap_visible
                # Windows denies unlinking this open resource path. Returning
                # the attacker's same-size hardlink identity models the same
                # post-open namespace swap without relying on that operation.
                swap_visible = True
                original_write(*args, **kwargs)

            def swapped_path_identity(path: Path) -> os.stat_result | None:
                if swap_visible and path == canonical_resource:
                    return attacker_hardlink.lstat()
                return original_lstat_optional(path)

            with (
                mock.patch(
                    "dcsmizzer.builder._write_miz",
                    side_effect=expose_swap_before_write,
                ),
                mock.patch(
                    "dcsmizzer.builder._lstat_optional",
                    side_effect=swapped_path_identity,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "path changed after its file handle was opened",
                ),
            ):
                build_miz(spec_path, output)

            self.assertTrue(swap_visible)
            self.assertFalse(output.exists())
            self.assertEqual(
                list(root.glob(f".{output.name}.*")),
                [],
            )

    def test_builder_rejects_same_size_bound_resource_content_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            resource_alias = root / "briefing-alias.bin"
            trusted_bytes = b"trusted-resource"
            changed_bytes = b"changed-resource"
            self.assertEqual(len(trusted_bytes), len(changed_bytes))
            resource.write_bytes(trusted_bytes)
            try:
                os.link(resource, resource_alias)
            except OSError as error:
                self.skipTest(f"hard links unavailable: {type(error).__name__}")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            original_write = builder_module._write_miz
            content_changed = False

            def write_then_change_content(
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal content_changed
                original_write(*args, **kwargs)
                resource_alias.write_bytes(changed_bytes)
                content_changed = True

            with (
                mock.patch(
                    "dcsmizzer.builder._write_miz",
                    side_effect=write_then_change_content,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "content changed after it was bound",
                ),
            ):
                build_miz(spec_path, output)

            self.assertTrue(content_changed)
            self.assertFalse(output.exists())
            self.assertEqual(
                list(root.glob(f".{output.name}.*")),
                [],
            )

    def test_builder_rejects_same_size_resource_change_after_verify(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            resource_alias = root / "briefing-alias.bin"
            trusted_bytes = b"trusted-resource"
            changed_bytes = b"changed-resource"
            self.assertEqual(len(trusted_bytes), len(changed_bytes))
            resource.write_bytes(trusted_bytes)
            try:
                os.link(resource, resource_alias)
            except OSError as error:
                self.skipTest(f"hard links unavailable: {type(error).__name__}")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            original_verify = builder_module._verify
            content_changed = False

            def verify_then_change_content(
                *args: object,
                **kwargs: object,
            ) -> tuple[dict[str, object], bool]:
                nonlocal content_changed
                result = original_verify(*args, **kwargs)
                resource_alias.write_bytes(changed_bytes)
                content_changed = True
                return result

            with (
                mock.patch(
                    "dcsmizzer.builder._verify",
                    side_effect=verify_then_change_content,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "content changed after it was bound",
                ),
            ):
                build_miz(spec_path, output)

            self.assertTrue(content_changed)
            self.assertFalse(output.exists())
            self.assertEqual(
                list(root.glob(f".{output.name}.*")),
                [],
            )

    def test_resource_handle_stays_open_through_verify_then_closes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            resource.write_bytes(b"bound resource")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            original_open = builder_module._open_bound_resource_input
            original_verify = builder_module._verify
            bindings: list[object] = []
            observations: list[tuple[bool, bool]] = []

            def track_binding(*args: object, **kwargs: object) -> object:
                binding = original_open(*args, **kwargs)
                bindings.append(binding)
                return binding

            def observe_verify(
                miz_file: object,
                build_spec: object,
                *,
                resources: tuple[object, ...],
                schema: str,
                artifact_name: str,
            ) -> tuple[dict[str, object], bool]:
                binding = resources[0]
                observations.append(
                    (
                        not binding.stream.closed,
                        os.path.samestat(
                            os.fstat(binding.stream.fileno()),
                            resource.lstat(),
                        ),
                    )
                )
                return original_verify(
                    miz_file,
                    build_spec,
                    resources=resources,
                    schema=schema,
                    artifact_name=artifact_name,
                )

            with (
                mock.patch(
                    "dcsmizzer.builder._open_bound_resource_input",
                    side_effect=track_binding,
                ),
                mock.patch(
                    "dcsmizzer.builder._verify",
                    side_effect=observe_verify,
                ),
            ):
                _report, valid = build_miz(spec_path, output)

            self.assertTrue(valid)
            self.assertEqual(observations, [(True, True)])
            self.assertEqual(len(bindings), 1)
            self.assertTrue(bindings[0].stream.closed)

    def test_verify_rejects_resource_identity_swap_after_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["mapResource"] = {"briefing": "briefing.bin"}
            spec["resources"] = [{"member": "briefing.bin", "source": "briefing.bin"}]
            spec["expect"]["minimum"]["resource_mappings"] = 1
            resource = root / "briefing.bin"
            attacker_source = root / "attacker-source.bin"
            attacker_hardlink = root / "attacker-hardlink.bin"
            resource.write_bytes(b"trusted-resource")
            attacker_source.write_bytes(b"hostile-resource")
            try:
                os.link(attacker_source, attacker_hardlink)
            except OSError as error:
                self.skipTest(f"hard links unavailable: {type(error).__name__}")
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            _report, built = build_miz(spec_path, output)
            self.assertTrue(built)
            canonical_resource = resource.resolve()
            original_open_artifact = builder_module._open_bound_regular_file
            original_lstat_optional = builder_module._lstat_optional
            swap_visible = False

            def open_artifact_then_expose_swap(
                path: Path,
            ) -> tuple[int, os.stat_result]:
                nonlocal swap_visible
                result = original_open_artifact(path)
                swap_visible = True
                return result

            def swapped_path_identity(path: Path) -> os.stat_result | None:
                if swap_visible and path == canonical_resource:
                    return attacker_hardlink.lstat()
                return original_lstat_optional(path)

            with (
                mock.patch(
                    "dcsmizzer.builder._open_bound_regular_file",
                    side_effect=open_artifact_then_expose_swap,
                ),
                mock.patch(
                    "dcsmizzer.builder._lstat_optional",
                    side_effect=swapped_path_identity,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "path changed after its file handle was opened",
                ),
            ):
                verify_miz(output, spec_path)

            self.assertTrue(swap_visible)
            self.assertTrue(output.is_file())

    def test_cli_build_and_verify_commands_return_machine_readable_results(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "mission.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            build_out = io.StringIO()
            verify_out = io.StringIO()

            build_exit = main(
                ["build-miz", str(spec_path), str(output)],
                stdout=build_out,
            )
            verify_exit = main(
                ["verify-miz", str(output), "--spec", str(spec_path)],
                stdout=verify_out,
            )

        build_report = json.loads(build_out.getvalue())
        verify_report = json.loads(verify_out.getvalue())
        self.assertEqual(build_exit, 0)
        self.assertEqual(verify_exit, 0)
        self.assertTrue(build_report["validation"]["available_checks_passed"])
        self.assertTrue(verify_report["validation"]["available_checks_passed"])

    def test_complete_profile_passes_only_with_complete_scenario_tables(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "complete.json"
            output = root / "complete.miz"
            spec_path.write_text(
                json.dumps(complete_fixture_spec()),
                encoding="utf-8",
            )

            report, valid = build_miz(spec_path, output)

        self.assertTrue(valid)
        self.assertEqual(report["quality"]["profile"], "complete_scenario")
        self.assertTrue(report["validation"]["quality_gate_passed"])
        self.assertTrue(report["validation"]["review_warnings_clear"])
        flag_flow = report["generation"]["logic_compilation"]["flag_dataflow"]
        self.assertEqual(flag_flow["read_without_writer"], [])
        self.assertFalse(flag_flow["temporal_reachability_proved"])
        outcome_flow = report["generation"]["logic_compilation"][
            "terminal_outcome_dataflow"
        ]
        self.assertTrue(outcome_flow["applicable"])
        self.assertTrue(outcome_flow["guard_order_contract_passed"])
        self.assertTrue(outcome_flow["failure_writers_precede_success"])
        self.assertEqual(outcome_flow["startup_terminal_writers"], [])
        self.assertEqual(outcome_flow["unsupported_terminal_writes"], [])
        self.assertFalse(outcome_flow["runtime_mutual_exclusion_proved"])
        self.assertFalse(outcome_flow["temporal_reachability_proved"])

    def test_complete_profile_rejects_mixed_terminal_outcome_races(
        self,
    ) -> None:
        mutations = (
            (
                "success failure guard",
                lambda spec: spec["logic"]["trigger_rules"][1]["conditions"].pop(),
                "success writers must guard every failure flag",
            ),
            (
                "failure success guard",
                lambda spec: spec["logic"]["trigger_rules"][0]["conditions"].pop(),
                "failure writers must guard every success flag",
            ),
            (
                "terminal rule order",
                lambda spec: spec["logic"]["trigger_rules"].reverse(),
                "failure writers must precede success writers",
            ),
            (
                "startup phase terminal writer",
                lambda spec: spec["logic"]["trigger_rules"][1].__setitem__(
                    "kind",
                    "start",
                ),
                "terminal flags must not be written by start rules",
            ),
            (
                "terminal flag reset",
                lambda spec: spec["logic"]["trigger_rules"][1]["actions"].append(
                    {
                        "predicate": "a_set_flag_value",
                        "flag": 1,
                        "value": 0,
                    }
                ),
                "resets and other values are forbidden",
            ),
            (
                "unbacked terminal goal",
                lambda spec: spec["logic"]["goals"][0].__setitem__(
                    "conditions",
                    [{"predicate": "c_group_dead", "group": 1}],
                ),
                "terminal goals must each include a c_flag_is_true",
            ),
            (
                "shared terminal flag",
                lambda spec: spec["logic"]["goals"][1].__setitem__(
                    "conditions",
                    [
                        {"predicate": "c_flag_is_true", "flag": 1},
                        {"predicate": "c_time_after", "seconds": 1},
                    ],
                ),
                "terminal goals must use distinct flags",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    mutate(spec)
                    spec_path = root / "invalid.json"
                    spec_path.write_text(
                        json.dumps(spec),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(BuildSpecError, message):
                        build_miz(spec_path, root / "invalid.miz")

    def test_complete_profile_requires_observed_runtime_skeleton(
        self,
    ) -> None:
        def remove_side_field(
            spec: dict[str, object],
            side: str,
            field: str,
        ) -> None:
            spec["mission"]["coalition"][side].pop(field)

        mutations = (
            (
                "coalitions",
                lambda spec: spec["mission"].pop("coalitions"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "currentKey",
                lambda spec: spec["mission"].pop("currentKey"),
                "complete_invalid_observed_runtime_integer",
            ),
            (
                "failures",
                lambda spec: spec["mission"].pop("failures"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "forcedOptions",
                lambda spec: spec["mission"].pop("forcedOptions"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "groundControl",
                lambda spec: spec["mission"].pop("groundControl"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "map",
                lambda spec: spec["mission"].pop("map"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "maxDictId",
                lambda spec: spec["mission"].pop("maxDictId"),
                "complete_invalid_observed_runtime_integer",
            ),
            (
                "pictureFileNameB",
                lambda spec: spec["mission"].pop("pictureFileNameB"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "pictureFileNameR",
                lambda spec: spec["mission"].pop("pictureFileNameR"),
                "complete_missing_observed_runtime_table",
            ),
            (
                "red side",
                lambda spec: spec["mission"]["coalition"].pop("red"),
                "complete_missing_coalition_side",
            ),
            (
                "blue bullseye",
                lambda spec: remove_side_field(spec, "blue", "bullseye"),
                "complete_missing_coalition_side_table",
            ),
            (
                "red country",
                lambda spec: remove_side_field(spec, "red", "country"),
                "complete_missing_coalition_side_table",
            ),
            (
                "neutral nav points",
                lambda spec: remove_side_field(
                    spec,
                    "neutrals",
                    "nav_points",
                ),
                "complete_missing_coalition_side_table",
            ),
            (
                "coalition membership coverage",
                lambda spec: spec["mission"]["coalitions"].update({"blue": []}),
                "complete_country_missing_from_coalition_membership",
            ),
            (
                "dense coalition membership",
                lambda spec: spec["mission"]["coalitions"].update(
                    {
                        "blue": {
                            "$fields": [
                                {
                                    "key": 2,
                                    "value": 2,
                                }
                            ]
                        }
                    }
                ),
                "complete_invalid_coalition_membership_sequence",
            ),
            (
                "integer coalition membership",
                lambda spec: spec["mission"]["coalitions"].update({"blue": ["2"]}),
                "complete_invalid_coalition_membership_id",
            ),
            (
                "four ground roles",
                lambda spec: spec["mission"]["groundControl"]["roles"].pop("observer"),
                "complete_missing_ground_control_role",
            ),
            (
                "ground role red table",
                lambda spec: spec["mission"]["groundControl"]["roles"]["observer"].pop(
                    "red"
                ),
                "complete_missing_ground_control_role_side",
            ),
        )
        for name, mutate, diagnostic in mutations:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    mutate(spec)
                    spec_path = root / "invalid.json"
                    spec_path.write_text(
                        json.dumps(spec),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        diagnostic,
                    ):
                        build_miz(spec_path, root / "invalid.miz")

    def test_complete_profile_type_checks_optional_picture_tables(self) -> None:
        for field_name in ("pictureFileNameN", "pictureFileNameServer"):
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    spec["mission"][field_name] = "not-a-table"
                    spec_path = root / "invalid.json"
                    spec_path.write_text(
                        json.dumps(spec),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        f"mission.{field_name} must be a table",
                    ):
                        build_miz(spec_path, root / "invalid.miz")

    def test_complete_profile_rejects_missing_payload_and_private_device(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            unit = spec["mission"]["coalition"]["blue"]["country"][0]["plane"]["group"][
                0
            ]["units"][0]
            unit["payload"].pop("fuel")
            missing_path = root / "missing.json"
            missing_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "complete_invalid_payload_fuel",
            ):
                build_miz(missing_path, root / "missing.miz")

            spec = complete_fixture_spec()
            spec["options"]["sound"]["main_output"] = "{LOCAL-DEVICE-GUID}"
            private_path = root / "private.json"
            private_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(
                BuildSpecError,
                "local audio device identifiers",
            ):
                build_miz(private_path, root / "private.miz")

    def test_complete_profile_makes_contract_coverage_warnings_fatal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            spec["expect"]["required"].pop("group_tasks")
            spec_path = root / "incomplete-contract.json"
            output = root / "incomplete-contract.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(spec_path, output)
            output_created = output.is_file()

        self.assertFalse(valid)
        self.assertFalse(output_created)
        self.assertIsNone(report["artifact"])
        self.assertFalse(report["publication"]["published"])
        self.assertTrue(report["publication"]["new_output_absent"])
        self.assertFalse(report["validation"]["quality_gate_passed"])
        self.assertIn(
            "group_tasks_not_all_required",
            report["contract"]["coverage_warnings"],
        )

    def test_failed_force_build_preserves_existing_output_and_cli_reports_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            spec["expect"]["required"].pop("group_tasks")
            spec_path = root / "invalid-complete.json"
            output = root / "mission.miz"
            original = b"existing artifact must survive"
            output.write_bytes(original)
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(spec_path, output, force=True)
            stdout = io.StringIO()
            stderr = io.StringIO()
            cli_output = root / "cli.miz"
            exit_code = main(
                [
                    "build-miz",
                    str(spec_path),
                    str(cli_output),
                    "--force",
                ],
                stdout=stdout,
                stderr=stderr,
            )

            self.assertFalse(valid)
            self.assertEqual(output.read_bytes(), original)
            self.assertFalse(report["publication"]["published"])
            self.assertTrue(report["publication"]["existing_output_preserved"])
            self.assertFalse(report["replaced_existing_output"])
            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertFalse(cli_output.exists())
            cli_report = json.loads(stdout.getvalue())
            self.assertFalse(cli_report["validation"]["available_checks_passed"])
            self.assertEqual(
                cli_report["publication"]["reason"],
                "candidate_failed_available_checks",
            )
            self.assertEqual(
                list(root.glob(f".{output.name}.*.tmp")),
                [],
            )

    def test_successful_force_build_uses_guarded_path_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "complete.json"
            output = root / "mission.miz"
            output.write_bytes(b"old artifact")
            spec_path.write_text(
                json.dumps(complete_fixture_spec()),
                encoding="utf-8",
            )

            report, valid = build_miz(spec_path, output, force=True)

            self.assertTrue(valid)
            self.assertNotEqual(output.read_bytes(), b"old artifact")
            self.assertTrue(report["publication"]["published"])
            self.assertTrue(report["publication"]["replaced_existing_output"])
            self.assertTrue(report["replaced_existing_output"])
            self.assertEqual(
                report["publication"]["reason"],
                "available_checks_passed",
            )
            self.assertEqual(
                list(root.glob(f".{output.name}.*.tmp")),
                [],
            )

    def test_complete_profile_requires_mission_content_human_role_and_core(
        self,
    ) -> None:
        def make_ai_only(spec: dict[str, object]) -> None:
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["task"] = "Nothing"
            for unit in group["units"]:
                unit["skill"] = "Excellent"

        mutations = {
            "actual mission group": lambda spec: spec["mission"]["coalition"][
                "blue"
            ].update({"country": []}),
            "Player or Client": make_ai_only,
            "nonempty expect.roles": lambda spec: spec["expect"].update({"roles": []}),
            "mission.date": lambda spec: spec["mission"].pop("date"),
            "mission.start_time": lambda spec: spec["mission"].pop("start_time"),
            "mission.weather": lambda spec: spec["mission"].pop("weather"),
        }
        for message, mutate in mutations.items():
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    mutate(spec)
                    spec_path = root / "invalid.json"
                    spec_path.write_text(json.dumps(spec), encoding="utf-8")

                    with self.assertRaisesRegex(BuildSpecError, message):
                        build_miz(spec_path, root / "invalid.miz")

    def test_static_player_skill_does_not_satisfy_human_slot_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            country = spec["mission"]["coalition"]["blue"]["country"][0]
            flying_group = country["plane"]["group"][0]
            flying_group["task"] = "Nothing"
            for unit in flying_group["units"]:
                unit["skill"] = "Excellent"
            country["static"] = {
                "group": [
                    {
                        "groupId": 99,
                        "name": "Fake human static group",
                        "route": {"points": [{"x": 1, "y": 2}]},
                        "units": [
                            {
                                "unitId": 99,
                                "name": "Fake human static",
                                "type": "Fixture static",
                                "skill": "Player",
                                "x": 1,
                                "y": 2,
                                "heading": 0,
                            }
                        ],
                    }
                ]
            }
            spec_path = root / "static-player.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "at least one Player or Client unit",
            ):
                build_miz(spec_path, root / "static-player.miz")

    def test_goal_condition_comparison_is_numeric_set_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            spec["logic"]["goals"][0]["conditions"] = [
                {"predicate": "c_time_after", "seconds": 60},
                {"predicate": "c_group_dead", "group": 1},
            ]
            spec["logic"]["goals"][1]["conditions"] = [
                {"predicate": "c_group_dead", "group": 1},
                {"predicate": "c_time_after", "seconds": 60.0},
                {"predicate": "c_time_after", "seconds": 60.0},
            ]
            spec_path = root / "same-semantic-goals.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                "must not use identical conditions",
            ):
                build_miz(spec_path, root / "same-semantic-goals.miz")

    def test_complete_logic_requires_a_writer_for_every_read_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            spec["logic"]["goals"][0]["conditions"][0]["flag"] = 99
            spec_path = root / "unset-flag.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(
                BuildSpecError,
                r"reads flags without any setter: \[99\]",
            ):
                build_miz(spec_path, root / "unset-flag.miz")

    def test_complete_profile_rejects_identical_outcomes_and_hollow_tables(
        self,
    ) -> None:
        mutations = {
            "identical conditions": lambda spec: spec["logic"]["goals"][1][
                "conditions"
            ].__setitem__(
                0,
                {"predicate": "c_flag_is_true", "flag": 1},
            ),
            "options.graphics is missing fields": lambda spec: spec["options"].update(
                {"graphics": {}}
            ),
            "aircrafts is missing fields": lambda spec: spec["warehouses"]["airports"][
                "$fields"
            ][0]["value"].update({"aircrafts": {}}),
            "coalition must be one of": lambda spec: spec["warehouses"]["airports"][
                "$fields"
            ][0]["value"].update({"coalition": "ALLIES"}),
            "InitFuel must be a nonnegative": lambda spec: spec["warehouses"][
                "airports"
            ]["$fields"][0]["value"]["jet_fuel"].update({"InitFuel": -1}),
        }
        for message, mutate in mutations.items():
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    spec = complete_fixture_spec()
                    mutate(spec)
                    spec_path = root / "invalid.json"
                    spec_path.write_text(json.dumps(spec), encoding="utf-8")

                    with self.assertRaisesRegex(BuildSpecError, message):
                        build_miz(spec_path, root / "invalid.miz")

    def test_builder_reports_use_basename_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "private-spec.json"
            output = root / "private-output.miz"
            spec_path.write_text(
                json.dumps(complete_fixture_spec()),
                encoding="utf-8",
            )

            build_report, built = build_miz(spec_path, output)
            verify_report, verified = verify_miz(output, spec_path)

            self.assertTrue(built)
            self.assertTrue(verified)
            self.assertEqual(build_report["path_scope"], "basename_only")
            self.assertEqual(build_report["artifact"], output.name)
            self.assertEqual(build_report["input_spec"], spec_path.name)
            self.assertEqual(verify_report["artifact"], output.name)
            self.assertEqual(verify_report["input_spec"], spec_path.name)
            self.assertNotIn(
                str(root),
                json.dumps(
                    {"build": build_report, "verify": verify_report},
                    ensure_ascii=False,
                ),
            )

    def test_builder_recursively_redacts_local_paths_from_provenance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = fixture_spec()
            spec["provenance"] = {
                "public_remote": "https://github.com/example/project.git",
                "public_ssh": "ssh://git@github.com/example/project.git",
                "public_scp": "git@github.com:/example/project.git",
                    "relative_reference": "evidence/catalog.json",
                "nested": [
                    "C:\\Users\\Private\\source.json",
                    "\\\\private-server\\share\\source.json",
                    "/home/private/source.json",
                    "file:///C:/Users/Private/source.json",
                    "ssh://localhost/C:/Users/Private/source.json",
                    "git@localhost:/home/private/source.json",
                    "trace:C:\\Users\\Embedded\\source.json",
                    "trace:/home/embedded/source.json",
                    "trace:\\\\private-host\\share\\source.json",
                    "trace:file:///C:/Users/Embedded/source.json",
                    "trace:ssh://localhost/C:/Users/Embedded/source.json",
                    "trace:user@private-host:/srv/embedded/source.json",
                    {
                        "source=/srv/private/source.json": (
                            "checked /opt/private/source.json"
                        )
                    },
                ],
            }
            spec_path = root / "spec.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(spec_path, output)

        self.assertTrue(valid)
        provenance = report["generation"]["provenance"]
        serialized = json.dumps(provenance, ensure_ascii=False)
        self.assertEqual(
            provenance["public_remote"],
            "https://github.com/example/project.git",
        )
        self.assertEqual(
            provenance["public_ssh"],
            "ssh://git@github.com/example/project.git",
        )
        self.assertEqual(
            provenance["public_scp"],
            "git@github.com:/example/project.git",
        )
        self.assertEqual(
            provenance["relative_reference"],
            "evidence/catalog.json",
        )
        for private_fragment in (
            "C:\\",
            "\\\\private-server",
            "/home/private",
            "file:",
            "localhost",
            "/srv/private",
            "/opt/private",
            "Embedded",
            "/home/embedded",
            "private-host",
            "/srv/embedded",
        ):
            self.assertNotIn(private_fragment, serialized)
        self.assertIn("<local-path-redacted>", serialized)
        self.assertEqual(
            report["generation"]["provenance_path_policy"],
            "recursive_local_paths_redacted",
        )

    def test_verify_uses_one_open_regular_file_handle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "spec.json"
            output = root / "mission.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            _report, built = build_miz(spec_path, output)
            self.assertTrue(built)
            observed_handles: list[int] = []
            original_inspect = builder_module.inspect_miz

            def observe_inspection(
                source: object,
                *args: object,
                **kwargs: object,
            ) -> object:
                observed_handles.append(source.fileno())
                self.assertTrue(
                    os.path.samestat(
                        os.fstat(source.fileno()),
                        output.lstat(),
                    )
                )
                return original_inspect(source, *args, **kwargs)

            with mock.patch(
                "dcsmizzer.builder.inspect_miz",
                side_effect=observe_inspection,
            ):
                report, verified = verify_miz(output, spec_path)

        self.assertTrue(verified)
        self.assertEqual(len(observed_handles), 1)
        self.assertTrue(report["validation"]["artifact_identity_bound_to_open_handle"])

    def test_verify_rejects_artifact_symlink_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "spec.json"
            output = root / "mission.miz"
            link = root / "linked.miz"
            spec_path.write_text(json.dumps(fixture_spec()), encoding="utf-8")
            _report, built = build_miz(spec_path, output)
            self.assertTrue(built)
            original = output.read_bytes()
            try:
                os.symlink(
                    output,
                    link,
                    target_is_directory=False,
                )
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

            with self.assertRaisesRegex(
                BuildSpecError,
                "must not be a symbolic link",
            ):
                verify_miz(link, spec_path)

            self.assertEqual(output.read_bytes(), original)
            self.assertTrue(link.is_symlink())

    def test_role_manifest_binds_constraints_to_one_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = complete_fixture_spec()
            spec["expect"]["roles"][0]["group_task"] = "Escort"
            spec_path = root / "wrong-role.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = build_miz(
                spec_path,
                root / "wrong-role.miz",
            )

        self.assertFalse(valid)
        failed = {
            check["id"] for check in report["contract"]["checks"] if not check["passed"]
        }
        self.assertIn("roles[0].player_flight.group_task", failed)


if __name__ == "__main__":
    unittest.main()
