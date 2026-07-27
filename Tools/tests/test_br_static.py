from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from Tools.dcsmizzer.br_static import (
    _git_state,
    _sanitize_git_remote,
    br_airbase_report,
    br_spawnpoint_report,
    br_terrain_report,
)
from Tools.dcsmizzer.cli import main


class BriefingRoomStaticTests(unittest.TestCase):
    def test_git_remote_credentials_and_local_paths_are_redacted(self) -> None:
        self.assertEqual(
            _sanitize_git_remote(
                "https://pilot:secret-token@github.com/org/repo.git"
                "?access_token=also-secret#fragment"
            ),
            "https://github.com/org/repo.git",
        )
        self.assertEqual(
            _sanitize_git_remote("git@github.com:org/repo.git"),
            "github.com:org/repo.git",
        )
        self.assertEqual(
            _sanitize_git_remote(r"C:\Users\Pilot\private-repo"),
            "<redacted-local-remote>",
        )
        for remote in (
            "ssh://localhost/C:/Users/pilot/private",
            "ssh://127.0.0.1/private/repo",
            "ssh://0.0.0.0/C:/Users/pilot/private",
            "ssh://10.20.30.40/private/repo",
            "ssh://localhost.localdomain/private/repo",
            "ssh://example.com/C:/Users/pilot/private",
            "git@192.168.1.20:/srv/private/repo",
            r"\\localhost\private\repo",
        ):
            self.assertEqual(
                _sanitize_git_remote(remote),
                "<redacted-local-remote>",
            )
        self.assertEqual(
            _sanitize_git_remote("https://[::1"),
            "<redacted-local-or-unrecognized-remote>",
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        theatre_dir = self.root / "Database" / "Theaters"
        bounds_dir = self.root / "DatabaseJSON" / "TheaterTerrainBounds"
        spawn_dir = self.root / "DatabaseJSON" / "TheaterSpawnPoints"
        theatre_dir.mkdir(parents=True)
        bounds_dir.mkdir(parents=True)
        spawn_dir.mkdir(parents=True)

        (theatre_dir / "Fixture.ini").write_text(
            "[GUI]\n"
            "DisplayName=Fixture terrain\n\n"
            "[Theater]\n"
            "DCSID=FixtureMap\n"
            "DefaultMapCenter=10,20\n"
            "MagneticDeclination=3.5\n",
            encoding="utf-8",
        )
        (bounds_dir / "FixtureMap.json").write_text(
            json.dumps(
                {
                    "landMasses": [[[0, 0], [100, 0], [100, 100]]],
                    "waters": [[[20, 20], [30, 20], [30, 30]]],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "DatabaseJSON" / "TheatersAirbases.json").write_text(
            json.dumps([self._airbase()]),
            encoding="utf-8",
        )
        self._write_gzip(
            spawn_dir / "FixtureMap.json.gz",
            [
                {
                    "BRtype": "LandLarge",
                    "coords": [0, 0, 15],
                    "theatre": "FixtureMap",
                },
                {
                    "BRtype": "LandSmall",
                    "coords": [100, 0, 20],
                    "theatre": "FixtureMap",
                },
            ],
        )
        self._write_gzip(
            spawn_dir / "FixtureMap_Manual.json.gz",
            [
                {"BRtype": "LandLarge", "coords": [3, 4]},
                {"BRtype": "LandLarge", "coords": [50, 50, 9]},
            ],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_catalogs_declared_terrain_and_geometry(self) -> None:
        report = br_terrain_report(self.root, terrain="FixtureMap")

        self.assertEqual(report["coverage"]["theatre_declarations"], 1)
        self.assertEqual(report["coverage"]["matching_theatres"], 1)
        self.assertEqual(report["terrains"][0]["airbases"], 1)
        self.assertEqual(
            report["terrains"][0]["sea_mask_planning_geometry"][
                "source_fields"
            ]["landMasses"]["vertices"],
            3,
        )

    def test_queries_exact_airbase_and_preserves_unknown_stand_fields(self) -> None:
        report = br_airbase_report(
            self.root,
            "FixtureMap",
            airdrome_id=7,
            parking="A01",
            airplane_only=True,
        )

        self.assertEqual(report["coverage"]["matching_airbases"], 1)
        self.assertEqual(report["coverage"]["matching_parking_slots"], 1)
        airbase = report["airbases"][0]
        self.assertEqual(airbase["runways"][0]["designator_index"], 18)
        stand = airbase["parking"][0]
        self.assertEqual(stand["crossroad_idx"], 12)
        self.assertIsNone(stand["heading"])
        self.assertIsNone(stand["elevation_msl"])
        self.assertIsNone(stand["dimensions"]["height"])
        self.assertEqual(stand["airbase_reference_elevation_msl"], 41.0)

    def test_streams_nearest_generated_and_two_coordinate_manual_points(
        self,
    ) -> None:
        report = br_spawnpoint_report(
            self.root,
            "FixtureMap",
            spawn_type="LandLarge",
            near_x=0,
            near_y=0,
            limit=3,
        )

        self.assertEqual(report["coverage"]["points_parsed"], 4)
        self.assertEqual(report["coverage"]["points_malformed"], 0)
        self.assertEqual(report["coverage"]["matching_points"], 3)
        self.assertEqual(
            [point["distance_m"] for point in report["points"]],
            [0.0, 5.0, 50 * 2**0.5],
        )
        self.assertEqual(report["points"][1]["source_kind"], "manual")
        self.assertIsNone(report["points"][1]["altitude_msl"])

    def test_cli_uses_nonzero_for_missing_exact_queries(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = main(
            [
                "br-airbases",
                "--br-root",
                str(self.root),
                "--terrain",
                "FixtureMap",
                "--airdrome-id",
                "999",
            ],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            json.loads(stdout.getvalue())["coverage"]["matching_airbases"],
            0,
        )

    def test_blank_display_name_uses_labeled_type_name_fallback(self) -> None:
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        blank = self._airbase()
        blank.update(
            {
                "ID": 30,
                "displayName": "",
                "typeName": "Fallback_Airbase",
                "code": "FBK",
            }
        )
        records.append(blank)
        source.write_text(json.dumps(records), encoding="utf-8")

        report = br_airbase_report(
            self.root,
            "FixtureMap",
            airdrome_id=30,
        )

        self.assertTrue(report["coverage"]["exact_airbase_query_usable"])
        self.assertEqual(report["coverage"]["airbase_parse_failures"], 0)
        self.assertEqual(report["coverage"]["airbase_name_fallbacks"], 1)
        self.assertEqual(report["airbases"][0]["name"], "Fallback_Airbase")
        self.assertEqual(
            report["airbases"][0]["name_source"],
            "typeName_fallback_for_blank_displayName",
        )

    def test_rejects_unsafe_dcsid_before_constructing_database_path(
        self,
    ) -> None:
        declaration = self.root / "Database" / "Theaters" / "Fixture.ini"
        declaration.write_text(
            "[GUI]\nDisplayName=Unsafe\n\n"
            "[Theater]\nDCSID=../../../secret\nDefaultMapCenter=0,0\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "incomplete"):
            br_terrain_report(self.root)

    def test_rejects_checkout_external_bounds_and_spawn_directories(
        self,
    ) -> None:
        database_json = self.root / "DatabaseJSON"
        bounds = database_json / "TheaterTerrainBounds"
        spawn = database_json / "TheaterSpawnPoints"
        bounds.rename(database_json / "TheaterTerrainBounds-original")
        spawn.rename(database_json / "TheaterSpawnPoints-original")
        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir)
            external_bounds = external / "bounds"
            external_spawn = external / "spawn"
            external_bounds.mkdir()
            external_spawn.mkdir()
            (external_bounds / "FixtureMap.json").write_text(
                json.dumps({"landMasses": [], "waters": []}),
                encoding="utf-8",
            )
            self._write_gzip(
                external_spawn / "FixtureMap.json.gz",
                [],
            )
            self._write_gzip(
                external_spawn / "FixtureMap_Manual.json.gz",
                [],
            )
            try:
                os.symlink(
                    external_bounds,
                    bounds,
                    target_is_directory=True,
                )
                os.symlink(
                    external_spawn,
                    spawn,
                    target_is_directory=True,
                )
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "checkout"):
                br_terrain_report(self.root, terrain="FixtureMap")
            with self.assertRaisesRegex(ValueError, "checkout"):
                br_spawnpoint_report(self.root, "FixtureMap")

    def test_runway_null_or_empty_object_fails_closed_without_cli_traceback(
        self,
    ) -> None:
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        original = json.loads(source.read_text(encoding="utf-8"))
        for raw_runways in (None, [{}]):
            with self.subTest(raw_runways=raw_runways):
                records = json.loads(json.dumps(original))
                records[0]["runways"] = raw_runways
                source.write_text(json.dumps(records), encoding="utf-8")

                report = br_airbase_report(
                    self.root,
                    "FixtureMap",
                    airdrome_id=7,
                )
                stdout = StringIO()
                stderr = StringIO()
                exit_code = main(
                    [
                        "br-airbases",
                        "--br-root",
                        str(self.root),
                        "--terrain",
                        "FixtureMap",
                        "--airdrome-id",
                        "7",
                    ],
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(
                    report["coverage"]["airbase_parse_failures"],
                    1,
                )
                self.assertFalse(
                    report["coverage"]["exact_airbase_query_usable"]
                )
                self.assertEqual(exit_code, 1)
                self.assertEqual(stderr.getvalue(), "")

    def test_aggregate_cli_returns_one_for_partial_br_sources(self) -> None:
        bounds = (
            self.root
            / "DatabaseJSON"
            / "TheaterTerrainBounds"
            / "FixtureMap.json"
        )
        bounds.rename(bounds.with_suffix(".missing"))
        terrain_stdout = StringIO()
        terrain_exit = main(
            [
                "br-terrains",
                "--br-root",
                str(self.root),
            ],
            stdout=terrain_stdout,
        )

        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        records[0]["pos"] = None
        source.write_text(json.dumps(records), encoding="utf-8")
        airbase_stdout = StringIO()
        airbase_exit = main(
            [
                "br-airbases",
                "--br-root",
                str(self.root),
                "--terrain",
                "FixtureMap",
            ],
            stdout=airbase_stdout,
        )

        self.assertEqual(terrain_exit, 1)
        self.assertEqual(
            json.loads(terrain_stdout.getvalue())["coverage"][
                "terrain_bounds_unresolved"
            ],
            ["FixtureMap"],
        )
        self.assertEqual(airbase_exit, 1)
        self.assertEqual(
            json.loads(airbase_stdout.getvalue())["coverage"][
                "airbase_parse_failures"
            ],
            1,
        )

    def test_exact_airbase_query_rejects_duplicate_or_unparsed_record(
        self,
    ) -> None:
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        duplicate = self._airbase()
        duplicate["displayName"] = "Duplicate Airbase"
        records.append(duplicate)
        malformed = self._airbase()
        malformed.update({"ID": 8, "displayName": "Malformed", "pos": None})
        records.append(malformed)
        source.write_text(json.dumps(records), encoding="utf-8")

        duplicate_report = br_airbase_report(
            self.root,
            "FixtureMap",
            airdrome_id=7,
        )
        malformed_report = br_airbase_report(
            self.root,
            "FixtureMap",
            airdrome_id=8,
        )

        self.assertEqual(
            duplicate_report["coverage"]["matching_airbases"],
            2,
        )
        self.assertFalse(
            duplicate_report["coverage"]["exact_airbase_query_usable"]
        )
        self.assertEqual(
            malformed_report["coverage"]["airbase_parse_failures"],
            1,
        )
        self.assertFalse(
            malformed_report["coverage"]["exact_airbase_query_usable"]
        )

    def test_exact_terrain_query_rejects_duplicate_identity(self) -> None:
        duplicate = self.root / "Database" / "Theaters" / "Duplicate.ini"
        duplicate.write_text(
            "[GUI]\nDisplayName=Duplicate\n\n"
            "[Theater]\nDCSID=FixtureMap\nDefaultMapCenter=0,0\n",
            encoding="utf-8",
        )
        stdout = StringIO()

        exit_code = main(
            [
                "br-terrains",
                "--br-root",
                str(self.root),
                "--terrain",
                "FixtureMap",
            ],
            stdout=stdout,
        )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["coverage"]["matching_theatres"], 2)
        self.assertFalse(report["coverage"]["exact_query_usable"])

    def test_nested_directory_does_not_inherit_parent_git_provenance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path.cwd(),
            prefix="br-provenance-",
        ) as temp_dir:
            root = Path(temp_dir)
            (root / "Database" / "Theaters").mkdir(parents=True)
            (root / "DatabaseJSON").mkdir()
            (root / "DatabaseJSON" / "TheatersAirbases.json").write_text(
                "[]",
                encoding="utf-8",
            )

            state = _git_state(root)

        self.assertFalse(state["git_available"])
        self.assertFalse(state["exact_checkout_root"])
        self.assertEqual(state["provenance"], "unversioned_snapshot")

    @staticmethod
    def _write_gzip(path: Path, value: object) -> None:
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            json.dump(value, stream)

    @staticmethod
    def _airbase() -> dict[str, object]:
        return {
            "theatre": "FixtureMap",
            "ID": 7,
            "displayName": "Fixture Air Base",
            "typeName": "Fixture_Air_Base",
            "code": "FXTR",
            "pos": {
                "DCS": {"x": 10, "z": 20},
                "World": {"alt": 41, "lat": 52.0, "lon": 13.0},
            },
            "runways": [
                {
                    "Name": 18,
                    "course": 1.0,
                    "id": 1,
                    "length": 2500,
                    "position": {"x": 10, "y": 41, "z": 20},
                    "width": 45,
                }
            ],
            "stands": [
                {
                    "crossroad_index": 12,
                    "flag": 64,
                    "name": "A01",
                    "params": {
                        "FOR_AIRPLANES": "1",
                        "FOR_HELICOPTERS": "1",
                        "HEIGHT": "",
                        "LENGTH": "26",
                        "SHELTER": "0",
                        "WIDTH": "24",
                    },
                    "x": 11,
                    "y": 21,
                }
            ],
            "parking": [],
            "airdromeData": {
                "ATC": [250000000],
                "TACAN": [],
                "ILS": [],
            },
        }


if __name__ == "__main__":
    unittest.main()
