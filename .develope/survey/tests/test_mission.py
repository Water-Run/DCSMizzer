from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.mission import analyse_miz

from ._fixtures import write_miz


MISSION = r'''
mission = {
    version = 23,
    theatre = "FixtureMap",
    sortie = "DictKey_sortie",
    descriptionText = "DictKey_description",
    coalition = {
        blue = {
            country = {
                [1] = {
                    plane = {
                        group = {
                            [1] = {
                                lateActivation = true,
                                uncontrolled = true,
                                dynSpawnTemplate = true,
                                units = {
                                    [1] = {
                                        skill = "Player",
                                        DTC = {},
                                        datalinks = {},
                                        payload = {
                                            pylons = {
                                                [1] = { CLSID = "{ONE}" },
                                                [2] = { CLSID = "{TWO}" },
                                                [3] = { settings = {} },
                                            },
                                        },
                                    },
                                    [2] = { skill = "High" },
                                },
                                route = {
                                    points = {
                                        [1] = {
                                            action = "From Parking",
                                            task = {
                                                params = {
                                                    tasks = {
                                                        [1] = {
                                                            id = "WrappedAction",
                                                            params = {
                                                                action = {
                                                                    id = "Orbit",
                                                                },
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                        [2] = { action = "Turning Point" },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        red = {
            country = {
                [1] = {
                    vehicle = {
                        group = {
                            [1] = {
                                uncontrollable = true,
                                units = {
                                    [1] = { skill = "Average" },
                                },
                                route = {
                                    points = {
                                        [1] = { action = "Off Road" },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
    trigrules = {
        [1] = {
            rules = {
                [1] = { predicate = "c_time_after(10)" },
                [2] = { predicate = "c_flag_is_true(1)" },
            },
            actions = {
                [1] = { predicate = "a_out_text_delay('safe')" },
                [2] = { predicate = "a_do_script", text = "not executed" },
                [3] = { predicate = "a_set_flag(1)" },
            },
        },
    },
    goals = {
        [1] = { score = 100 },
    },
}
'''

OPTIONS = "options = {}\n"
WAREHOUSES = r'''
warehouses = {
    airports = { [1] = {}, [2] = {} },
    warehouses = { [100] = {} },
}
'''
DICTIONARY = r'''
dictionary = {
    DictKey_sortie = "Title",
    DictKey_description = "Brief",
}
'''
MAP_RESOURCE = r'''
mapResource = {
    ResKey_voice = "voice.ogg",
    ResKey_image = "image.PNG",
}
'''


class MizAnalysisTests(unittest.TestCase):
    def test_miz_core_tables_and_mission_semantics_are_aggregated(self) -> None:
        # Would fail if the analyzer counts static structure but loses mission meaning.
        members = {
            "mission": MISSION.encode(),
            "options": OPTIONS.encode(),
            "warehouses": WAREHOUSES.encode(),
            "l10n/DEFAULT/dictionary": DICTIONARY.encode(),
            "l10n/DEFAULT/mapResource": MAP_RESOURCE.encode(),
            "l10n/DEFAULT/voice.ogg": b"voice",
            "l10n/DEFAULT/image.PNG": b"image",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fixture.miz"
            write_miz(path, members=members)

            observation = analyse_miz(path)

        self.assertTrue(observation.parse_valid)
        self.assertEqual(observation.mission_version, 23)
        self.assertEqual(observation.theatre, "FixtureMap")
        self.assertEqual(
            {
                member.name: (member.present, member.parsed, member.encoding)
                for member in observation.members
            },
            {
                "mission": (True, True, "utf-8"),
                "options": (True, True, "utf-8"),
                "warehouses": (True, True, "utf-8"),
                "l10n/DEFAULT/dictionary": (True, True, "utf-8"),
                "l10n/DEFAULT/mapResource": (True, True, "utf-8"),
            },
        )
        stats = observation.stats
        self.assertEqual(stats.groups, {"plane": 1, "vehicle": 1})
        self.assertEqual(stats.units, {"plane": 2, "vehicle": 1})
        self.assertEqual(stats.waypoints, {"plane": 2, "vehicle": 1})
        self.assertEqual(stats.human_slots, {"Player": 1})
        self.assertEqual(stats.pylon_assignments, 3)
        self.assertEqual(stats.pylons_with_clsid, 2)
        self.assertEqual(stats.payload_clsids, {"{ONE}", "{TWO}"})
        self.assertEqual(stats.trigger_rules, 1)
        self.assertEqual(stats.trigger_conditions, 2)
        self.assertEqual(stats.trigger_actions, 3)
        self.assertEqual(stats.script_actions, 1)
        self.assertEqual(stats.goals, 1)
        self.assertEqual(stats.dictionary_entries, 2)
        self.assertEqual(stats.resource_mappings, 2)
        self.assertEqual(stats.missing_resource_members, 0)
        self.assertEqual(stats.briefing_characters, 10)
        self.assertEqual(stats.resource_extensions, {".ogg": 1, ".png": 1})
        self.assertEqual(stats.warehouse_airports, 2)
        self.assertEqual(stats.warehouse_objects, 1)
        self.assertEqual(stats.late_activation_groups, 1)
        self.assertEqual(stats.uncontrolled_groups, 1)
        self.assertEqual(stats.uncontrollable_groups, 1)
        self.assertEqual(stats.modern_fields["dynSpawnTemplate"], 1)
        self.assertEqual(stats.modern_fields["DTC"], 1)
        self.assertEqual(stats.modern_fields["datalinks"], 1)
        self.assertEqual(
            stats.waypoint_actions,
            {"From Parking": 1, "Turning Point": 1, "Off Road": 1},
        )
        self.assertEqual(
            stats.waypoint_task_ids,
            {"WrappedAction": 1, "Orbit": 1},
        )

    def test_missing_historical_core_members_are_recorded_not_synthesized(self) -> None:
        # Would fail if old-format missing files are invented or treated as parsed.
        members = {
            "mission": b"mission = { version = 6, theatre = 'FixtureMap' }",
            "warehouses": b"warehouses = {}",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "old.miz"
            write_miz(path, members=members)

            observation = analyse_miz(path)

        by_name = {member.name: member for member in observation.members}
        self.assertTrue(observation.parse_valid)
        self.assertFalse(by_name["options"].present)
        self.assertFalse(by_name["options"].parsed)
        self.assertFalse(by_name["l10n/DEFAULT/dictionary"].present)
        self.assertFalse(by_name["l10n/DEFAULT/mapResource"].present)
        self.assertEqual(observation.stats.dictionary_entries, 0)
        self.assertEqual(observation.stats.resource_mappings, 0)

    def test_missing_resource_distinguishes_referenced_and_stale_mapping(self) -> None:
        # Would fail if every stale mapResource entry is treated as an active break.
        members = {
            "mission": b'''
                mission = {
                    version = 23,
                    theatre = "FixtureMap",
                    pictureFileNameB = "ResKey_missing",
                    coalition = {},
                }
            ''',
            "options": b"options = {}",
            "warehouses": b"warehouses = {}",
            "l10n/DEFAULT/dictionary": b"dictionary = {}",
            "l10n/DEFAULT/mapResource": b'''
                mapResource = {
                    ResKey_missing = "missing.ogg",
                    ResKey_stale = "stale.png",
                }
            ''',
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing-resource.miz"
            write_miz(path, members=members)

            observation = analyse_miz(path)

        self.assertEqual(observation.stats.missing_resource_members, 2)
        self.assertEqual(observation.stats.referenced_missing_resources, 1)
        self.assertEqual(observation.stats.unreferenced_missing_resources, 1)


if __name__ == "__main__":
    unittest.main()
