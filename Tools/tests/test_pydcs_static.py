from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.pydcs_static import (  # noqa: E402
    _git_state,
    _sanitize_git_remote,
    pydcs_aircraft_report,
    pydcs_airport_report,
    pydcs_terrain_report,
    pydcs_unit_report,
)


AIRPORTS = """
class Fixture(Airport):
    id = 7
    name = "Fixture Airbase"
    civilian = False
    slot_version = 2

    def __init__(self):
        self.position = Point(1000.5, 2000.25)
        self.runways = [Runway(id=1, name="09-27")]
        self.parking_slots = [
            ParkingSlot(
                crossroad_idx=46,
                position=Point(1010.5, 2020.25),
                large=False,
                heli=True,
                airplanes=True,
                slot_name="01",
                length=40,
                width=20,
                height=8,
                shelter=False,
            ),
            ParkingSlot(
                crossroad_idx=47,
                position=Point(1030.5, 2040.25),
                large=False,
                heli=True,
                airplanes=True,
                slot_name="02",
                length=40,
                width=20,
                height=8,
                shelter=False,
            ),
        ]
        self.beacons = [AirportBeacon(id="fixture_beacon")]
"""

PLANES = """
class FixturePlane(PlaneType):
    id = "Fixture Plane"
    flyable = True
    pylons = {1, 2}
    tasks = [task.CAP, task.Intercept]
    task_default = task.CAP

    class Pylon1:
        Fixture = (1, Weapons.Fixture_Store)

    class Pylon2:
        Unknown = (2, OtherWeapons.Unknown)
"""

WEAPONS = """
class Weapons:
    Fixture_Store = {
        "clsid": "{FIXTURE}",
        "name": "Fixture store",
        "weight": 123,
    }
"""

TASKS = """
class MainTask:
    pass

class CAP(MainTask):
    id = 11
    name = "CAP"
    internal_name = "CAP"

class Intercept(MainTask):
    id = 10
    name = "Intercept"
    internal_name = "Intercept"

class GroundAttack(MainTask):
    id = 32
    name = "Ground Attack"
    internal_name = "GroundAttack"
"""

PROJECTION = """
PARAMETERS = TransverseMercator(
    central_meridian=0,
    false_easting=0.0,
    false_northing=0.0,
    scale_factor=0.9996,
)
"""

TERRAIN = """
class FixtureTerrain(Terrain):
    center = {"lat": 0.01, "long": 0.01}

    def __init__(self):
        bounds = mapping.Rectangle(4000, 0, 0, 4000, self)
        super().__init__(
            "FixtureMap",
            PARAMETERS,
            bounds=bounds,
            map_view_default=None,
            utc_offset=None,
        )
"""

VEHICLES = """
class AirDefence:
    class FixtureRadar(unittype.VehicleType):
        id = "Fixture Radar"
        name = "Fixture search radar"
        detection_range = 100000
        threat_range = 0
        air_weapon_dist = 0
"""


class PydcsStaticTests(unittest.TestCase):
    def test_clean_wrong_remote_or_commit_is_not_commit_bound(self) -> None:
        for reason in ("remote_mismatch", "commit_mismatch"):
            with self.subTest(reason=reason):
                source_lock = {
                    "schema": (
                        "dcsmizzer.acknowledged-upstream-source-lock/v1"
                    ),
                    "source": "pydcs",
                    "acknowledged": False,
                    "actual": {
                        "exact_checkout_root": True,
                        "head": "1" * 40,
                        "branch": "master",
                        "detached": False,
                        "clean": True,
                        "remote": "https://example.invalid/wrong.git",
                    },
                    "validation": {"usable": False},
                    "failure_reasons": [reason],
                    "errors": [],
                }
                with patch(
                    "dcsmizzer.pydcs_static.upstream_source_lock_status",
                    return_value=source_lock,
                ):
                    state = _git_state(Path("ignored-by-patched-lock"))

                self.assertFalse(state["acknowledged"])
                self.assertEqual(
                    state["provenance"],
                    "clean_unacknowledged_snapshot",
                )
                self.assertEqual(
                    state["source_lock"]["failure_reasons"],
                    [reason],
                )

    def test_git_remote_credentials_and_local_paths_are_redacted(self) -> None:
        self.assertEqual(
            _sanitize_git_remote(
                "ssh://git:private-token@example.com/team/repo.git?token=query-secret"
            ),
            "ssh://example.com/team/repo.git",
        )
        self.assertEqual(
            _sanitize_git_remote("token@example.com:team/repo.git"),
            "example.com:team/repo.git",
        )
        self.assertEqual(
            _sanitize_git_remote("/srv/private/pydcs"),
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

    def test_queries_commit_bound_airport_parking_and_aircraft_pylons(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (root / "dcs" / "planes.py").write_text(PLANES, encoding="utf-8")
            (root / "dcs" / "weapons_data.py").write_text(
                WEAPONS,
                encoding="utf-8",
            )
            (root / "dcs" / "task.py").write_text(TASKS, encoding="utf-8")

            airport = pydcs_airport_report(
                root,
                "FIXTURE",
                airdrome_id=7,
                parking="01",
            )
            aircraft = pydcs_aircraft_report(
                root,
                "Fixture Plane",
                station=1,
                clsid="{FIXTURE}",
            )

        self.assertEqual(airport["coverage"]["matching_airports"], 1)
        self.assertEqual(airport["coverage"]["matching_parking_slots"], 1)
        slot = airport["airports"][0]["parking"][0]
        self.assertEqual(slot["crossroad_idx"], 46)
        self.assertEqual(slot["slot_name"], "01")
        self.assertTrue(aircraft["compatibility_query"]["matched"])
        self.assertEqual(
            aircraft["aircraft"]["pylon_assignments"][0]["CLSID"],
            "{FIXTURE}",
        )
        self.assertEqual(
            aircraft["coverage"]["unresolved_pylon_assignments"],
            1,
        )
        self.assertEqual(
            aircraft["aircraft"]["tasks"][0]["mission_group_task"],
            "CAP",
        )
        self.assertEqual(
            aircraft["aircraft"]["tasks"][0]["payload_internal_name"],
            "CAP",
        )
        self.assertEqual(aircraft["schema"], "dcsmizzer.pydcs-aircraft/v2")
        self.assertNotIn(temp_dir, json.dumps(airport))
        self.assertNotIn(temp_dir, json.dumps(aircraft))

    def test_cli_returns_nonzero_for_missing_exact_parking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            stdout = io.StringIO()

            exit_code = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "fixture",
                    "--airdrome-id",
                    "7",
                    "--parking",
                    "99",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["coverage"]["matching_airports"], 1)
        self.assertEqual(report["coverage"]["matching_parking_slots"], 0)

    def test_airplane_limit_returns_small_complete_slot_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            stdout = io.StringIO()

            exit_code = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "fixture",
                    "--airdrome-id",
                    "7",
                    "--airplane-only",
                    "--limit",
                    "1",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["coverage"]["matching_parking_slots"], 2)
        self.assertEqual(report["coverage"]["returned_parking_slots"], 1)
        self.assertTrue(report["coverage"]["parking_output_truncated"])
        slot = report["airports"][0]["parking"][0]
        self.assertEqual(
            (slot["crossroad_idx"], slot["slot_name"]),
            (46, "01"),
        )

    def test_catalogs_uninstalled_terrain_and_converts_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(TERRAIN, encoding="utf-8")

            report = pydcs_terrain_report(root)
            converted = pydcs_terrain_report(
                root,
                terrain="FixtureMap",
                latitude=0.01,
                longitude=0.01,
            )

        self.assertEqual(
            report["coverage"]["terrain_packages_discovered"],
            1,
        )
        self.assertEqual(report["coverage"]["terrain_packages_parsed"], 1)
        record = report["terrains"][0]
        self.assertEqual(record["terrain_package"], "fixture")
        self.assertEqual(record["miz_theatre_name"], "FixtureMap")
        self.assertEqual(record["airport_summary"]["airports_parsed"], 1)
        self.assertEqual(record["airport_summary"]["parking_slots"], 2)
        consistency = record["declared_bounds_consistency"]
        self.assertEqual(consistency["status"], "consistent")
        self.assertTrue(consistency["hard_coordinate_rejection_allowed"])
        self.assertEqual(consistency["airport_centers_parsed"], 1)
        self.assertEqual(consistency["obviously_outside"], 0)
        self.assertTrue(record["declared_center_diagnostic"]["within_declared_bounds"])
        self.assertFalse(record["declared_center_diagnostic"]["independently_verified"])
        self.assertIn("mission_origin_wgs84", record["projection"])
        self.assertEqual(converted["coverage"]["matching_terrains"], 1)
        self.assertEqual(
            converted["conversion"]["direction"],
            "WGS84_to_mission_local",
        )
        self.assertTrue(converted["conversion"]["within_upstream_bounds"])
        self.assertFalse(
            converted["conversion"]["independently_validated_against_current_install"]
        )
        self.assertNotIn(temp_dir, json.dumps(report))

    def test_extreme_inverse_coordinate_fails_cleanly_at_cli_boundary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(TERRAIN, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "pydcs-terrains",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "FixtureMap",
                    "--x",
                    "1e308",
                    "--y",
                    "1e308",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("supported numeric range", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_bounds_consistency_exposes_realistic_internal_counterexample(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(
                TERRAIN.replace(
                    "mapping.Rectangle(4000, 0, 0, 4000, self)",
                    "mapping.Rectangle(100, 0, 0, 100, self)",
                ),
                encoding="utf-8",
            )

            report = pydcs_terrain_report(root, terrain="FixtureMap")

        consistency = report["terrains"][0]["declared_bounds_consistency"]
        self.assertEqual(consistency["status"], "inconsistent")
        self.assertFalse(consistency["hard_coordinate_rejection_allowed"])
        self.assertEqual(consistency["tolerance_m"], 1000.0)
        self.assertEqual(consistency["obviously_outside"], 1)
        self.assertEqual(
            consistency["obviously_outside_airports"][0]["airdrome_id"],
            7,
        )

    def test_airport_query_accepts_package_class_and_miz_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(TERRAIN, encoding="utf-8")

            reports = [
                pydcs_airport_report(root, query, airdrome_id=7)
                for query in ("fixture", "FixtureTerrain", "FixtureMap")
            ]

        self.assertTrue(
            all(
                report["filters"]["terrain_package"] == "fixture"
                and report["coverage"]["exact_airport_query_usable"]
                for report in reports
            )
        )

    def test_missing_slot_version_normalizes_to_upstream_default_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(
                AIRPORTS.replace("    slot_version = 2\n", ""),
                encoding="utf-8",
            )

            report = pydcs_airport_report(
                root,
                "fixture",
                airdrome_id=7,
            )

        self.assertEqual(report["airports"][0]["slot_version"], 1)

    def test_invalid_airport_class_fails_closed_for_exact_and_aggregate_cli(
        self,
    ) -> None:
        hidden_duplicate = """
class HiddenDuplicate(Airport):
    id = 7
    name = None

    def __init__(self):
        self.position = Point(0, 0)
        self.runways = []
        self.parking_slots = []
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(
                AIRPORTS + hidden_duplicate,
                encoding="utf-8",
            )
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(
                TERRAIN,
                encoding="utf-8",
            )

            report = pydcs_airport_report(
                root,
                "fixture",
                airdrome_id=7,
            )
            exact_stdout = io.StringIO()
            aggregate_airport_stdout = io.StringIO()
            aggregate_terrain_stdout = io.StringIO()
            exact_exit = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "fixture",
                    "--airdrome-id",
                    "7",
                ],
                stdout=exact_stdout,
            )
            aggregate_airport_exit = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "fixture",
                ],
                stdout=aggregate_airport_stdout,
            )
            aggregate_terrain_exit = main(
                [
                    "pydcs-terrains",
                    "--pydcs-root",
                    str(root),
                ],
                stdout=aggregate_terrain_stdout,
            )

        self.assertEqual(report["coverage"]["airport_parse_failures"], 1)
        self.assertFalse(report["coverage"]["source_parse_complete"])
        self.assertFalse(report["coverage"]["exact_airport_query_usable"])
        self.assertEqual(exact_exit, 1)
        self.assertEqual(aggregate_airport_exit, 1)
        self.assertEqual(aggregate_terrain_exit, 1)

    def test_exact_airport_query_fails_closed_on_source_parse_gap(
        self,
    ) -> None:
        broken = """
class Broken(Airport):
    id = 8
    name = "Broken"
    def __init__(self):
        self.position = Point(0, 0)
        self.parking_slots = [ParkingSlot()]
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(
                AIRPORTS + broken,
                encoding="utf-8",
            )
            report = pydcs_airport_report(
                root,
                "fixture",
                airdrome_id=7,
            )

        self.assertEqual(report["coverage"]["airport_parse_failures"], 1)
        self.assertFalse(report["coverage"]["source_parse_complete"])
        self.assertFalse(report["coverage"]["exact_airport_query_usable"])

    def test_exact_terrain_query_rejects_duplicate_miz_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for package_name in ("fixture", "duplicate"):
                terrain = root / "dcs" / "terrain" / package_name
                terrain.mkdir(parents=True)
                (terrain / "airports.py").write_text(
                    AIRPORTS,
                    encoding="utf-8",
                )
                (terrain / "projection.py").write_text(
                    PROJECTION,
                    encoding="utf-8",
                )
                (terrain / f"{package_name}.py").write_text(
                    TERRAIN.replace(
                        "FixtureTerrain",
                        f"{package_name.title()}Terrain",
                    ),
                    encoding="utf-8",
                )
            stdout = io.StringIO()
            exit_code = main(
                [
                    "pydcs-terrains",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "FixtureMap",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["coverage"]["matching_terrains"], 2)
        self.assertFalse(report["coverage"]["exact_query_usable"])

    def test_nested_directory_does_not_inherit_parent_git_provenance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path.cwd(),
            prefix="pydcs-provenance-",
        ) as temp_dir:
            root = Path(temp_dir)
            (root / "dcs").mkdir()

            state = _git_state(root)

        self.assertFalse(state["git_available"])
        self.assertFalse(state["exact_checkout_root"])
        self.assertEqual(state["provenance"], "unversioned_snapshot")

    def test_report_rejects_symlinked_checkout_root_before_source_reads(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            target = parent / "real-pydcs"
            (target / "dcs").mkdir(parents=True)
            alias = parent / "pydcs-alias"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

            with self.assertRaisesRegex(
                ValueError,
                "symbolic link|reparse",
            ):
                pydcs_terrain_report(alias)

    def test_terrain_cli_returns_nonzero_for_missing_exact_map(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            terrain = root / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(TERRAIN, encoding="utf-8")
            stdout = io.StringIO()

            exit_code = main(
                [
                    "pydcs-terrains",
                    "--pydcs-root",
                    str(root),
                    "--terrain",
                    "missing",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["coverage"]["matching_terrains"], 0)

    def test_queries_exact_ground_and_flying_unit_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dcs").mkdir()
            (root / "dcs" / "vehicles.py").write_text(
                VEHICLES,
                encoding="utf-8",
            )
            (root / "dcs" / "planes.py").write_text(
                PLANES,
                encoding="utf-8",
            )
            (root / "dcs" / "weapons_data.py").write_text(
                WEAPONS,
                encoding="utf-8",
            )
            (root / "dcs" / "task.py").write_text(TASKS, encoding="utf-8")

            vehicle = pydcs_unit_report(
                root,
                unit_type="Fixture Radar",
                category="vehicle",
            )
            plane = pydcs_unit_report(
                root,
                unit_type="Fixture Plane",
                category="plane",
            )
            search = pydcs_unit_report(
                root,
                category="vehicle",
                search="radar",
                limit=1,
            )
            wrong_case = pydcs_unit_report(
                root,
                unit_type="fixture radar",
                category="vehicle",
            )

        self.assertEqual(vehicle["coverage"]["matching_units"], 1)
        self.assertEqual(
            vehicle["units"][0]["python_declaration"],
            "AirDefence.FixtureRadar",
        )
        self.assertEqual(
            vehicle["units"][0]["declared"]["detection_range"],
            100000,
        )
        self.assertEqual(
            plane["units"][0]["flying_unit"]["tasks"][1]["mission_group_task"],
            "Intercept",
        )
        self.assertEqual(
            plane["units"][0]["flying_unit"]["pylon_assignments"][0]["CLSID"],
            "{FIXTURE}",
        )
        self.assertEqual(search["coverage"]["matching_units"], 1)
        self.assertEqual(search["coverage"]["returned_units"], 1)
        self.assertEqual(wrong_case["coverage"]["matching_units"], 0)
        self.assertEqual(
            wrong_case["coverage"]["case_only_near_matches"],
            [{"category": "vehicle", "id": "Fixture Radar"}],
        )


if __name__ == "__main__":
    unittest.main()
