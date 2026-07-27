from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.dcsmizzer.cli import main
from Tools.dcsmizzer.terrain_coverage import combined_terrain_report
from Tools.tests.test_pydcs_static import (
    AIRPORTS,
    PROJECTION,
    TERRAIN,
)


class CombinedTerrainCoverageTests(unittest.TestCase):
    def test_rejects_duplicate_cross_source_identity_claims_without_merge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pydcs = root / "pydcs"
            for package_name in ("fixture", "duplicate"):
                package = pydcs / "dcs" / "terrain" / package_name
                package.mkdir(parents=True)
                (package / "airports.py").write_text(
                    AIRPORTS,
                    encoding="utf-8",
                )
                (package / "projection.py").write_text(
                    PROJECTION,
                    encoding="utf-8",
                )
                (package / f"{package_name}.py").write_text(
                    TERRAIN,
                    encoding="utf-8",
                )
            br = root / "briefing-room"
            self._write_br_sources(br)
            (br / "Database" / "Theaters" / "FixtureAlias.ini").write_text(
                "[GUI]\n"
                "DisplayName=Fixture alias\n\n"
                "[Theater]\n"
                "DCSID=FixtureMap\n"
                "DefaultMapCenter=0,0\n",
                encoding="utf-8",
            )

            report = combined_terrain_report(pydcs, br)
            exact = combined_terrain_report(
                pydcs,
                br,
                terrain="FixtureMap",
            )

        self.assertGreaterEqual(
            report["coverage"]["identity_mappings_rejected"],
            3,
        )
        self.assertEqual(report["coverage"]["dual_source_theatres"], 0)
        self.assertEqual(exact["coverage"]["matching_theatres"], 0)
        self.assertGreater(
            exact["coverage"]["matching_records_including_rejected"],
            0,
        )
        self.assertFalse(exact["coverage"]["exact_query_usable"])
        self.assertTrue(
            all(
                not (
                    record["pydcs"] is not None
                    and record["briefingroom"] is not None
                )
                for record in report["terrains"]
            )
        )
        conflict_codes = {
            item["code"] for item in report["identity_conflicts"]
        }
        self.assertIn(
            "duplicate_briefingroom_dcs_id",
            conflict_codes,
        )
        self.assertIn("duplicate_pydcs_miz_theatre_name", conflict_codes)
        self.assertTrue(
            all(
                record["selected_parking_authority"] is None
                for record in report["terrains"]
                if record["dcs_theatre"] == "FixtureMap"
            )
        )

    def test_rejects_duplicate_briefingroom_display_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pydcs = root / "pydcs"
            terrain = pydcs / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(
                AIRPORTS,
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
            br = root / "briefing-room"
            self._write_br_sources(br)
            (br / "Database" / "Theaters" / "Remote.ini").write_text(
                "[GUI]\n"
                "DisplayName=Fixture map\n\n"
                "[Theater]\n"
                "DCSID=RemoteMap\n"
                "DefaultMapCenter=0,0\n",
                encoding="utf-8",
            )

            report = combined_terrain_report(pydcs, br)

        self.assertIn(
            "duplicate_briefingroom_display_name",
            {item["code"] for item in report["identity_conflicts"]},
        )
        self.assertEqual(report["coverage"]["matching_theatres"], 0)
        self.assertTrue(
            all(
                record["identity_resolution"]["status"] == "rejected"
                and record["selected_parking_authority"] is None
                for record in report["terrains"]
            )
        )

    def test_rejects_duplicate_pydcs_terrain_classes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pydcs = root / "pydcs"
            for package_name, miz_name in (
                ("first", "FirstMap"),
                ("second", "SecondMap"),
            ):
                terrain = pydcs / "dcs" / "terrain" / package_name
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
                    TERRAIN.replace("FixtureMap", miz_name),
                    encoding="utf-8",
                )
            br = root / "briefing-room"
            self._write_br_sources(br)

            report = combined_terrain_report(pydcs, br)

        self.assertIn(
            "duplicate_pydcs_terrain_class",
            {item["code"] for item in report["identity_conflicts"]},
        )
        pydcs_records = [
            record
            for record in report["terrains"]
            if record["pydcs"] is not None
        ]
        self.assertEqual(len(pydcs_records), 2)
        self.assertTrue(
            all(
                record["identity_resolution"]["status"] == "rejected"
                and record["selected_parking_authority"] is None
                for record in pydcs_records
            )
        )

    def test_propagates_source_parse_and_unresolved_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pydcs = root / "pydcs"
            terrain = pydcs / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(TERRAIN, encoding="utf-8")
            broken = pydcs / "dcs" / "terrain" / "broken"
            broken.mkdir(parents=True)
            (broken / "airports.py").write_text(
                "this is not valid Python !!!",
                encoding="utf-8",
            )
            (broken / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            br = root / "briefing-room"
            self._write_br_sources(br)
            (br / "Database" / "Theaters" / "NoBounds.ini").write_text(
                "[GUI]\n"
                "DisplayName=No bounds\n\n"
                "[Theater]\n"
                "DCSID=NoBounds\n"
                "DefaultMapCenter=0,0\n",
                encoding="utf-8",
            )

            report = combined_terrain_report(pydcs, br)
            stdout = io.StringIO()
            exit_code = main(
                [
                    "terrain-coverage",
                    "--pydcs-root",
                    str(pydcs),
                    "--br-root",
                    str(br),
                ],
                stdout=stdout,
            )

        self.assertEqual(
            report["source_coverage"]["pydcs"][
                "terrain_packages_unresolved"
            ],
            ["broken"],
        )
        self.assertEqual(
            report["source_coverage"]["briefingroom"][
                "terrain_bounds_unresolved"
            ],
            ["NoBounds"],
        )
        self.assertTrue(report["coverage"]["source_parse_incomplete"])
        self.assertEqual(exit_code, 1)
        self.assertTrue(
            json.loads(stdout.getvalue())["coverage"][
                "source_parse_incomplete"
            ]
        )

    def test_accepts_lexical_parent_components_in_source_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = root / "release-copy"
            runner.mkdir()
            pydcs = root / "pydcs"
            terrain = pydcs / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(
                AIRPORTS,
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
            br = root / "briefing-room"
            self._write_br_sources(br)

            report = combined_terrain_report(
                runner / ".." / "pydcs",
                runner / ".." / "briefing-room",
                terrain="FixtureMap",
            )

        self.assertEqual(report["coverage"]["matching_theatres"], 1)
        self.assertEqual(
            report["source_coverage"]["briefingroom"][
                "terrain_bounds_unresolved"
            ],
            [],
        )

    def test_keeps_dual_and_single_source_theatres_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pydcs = root / "pydcs"
            terrain = pydcs / "dcs" / "terrain" / "fixture"
            terrain.mkdir(parents=True)
            (terrain / "airports.py").write_text(AIRPORTS, encoding="utf-8")
            (terrain / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (terrain / "fixture.py").write_text(
                TERRAIN,
                encoding="utf-8",
            )
            br = root / "briefing-room"
            self._write_br_sources(br)

            report = combined_terrain_report(pydcs, br)
            exact = combined_terrain_report(
                pydcs,
                br,
                terrain="fixture",
            )
            acknowledged_lock = {
                "schema": (
                    "dcsmizzer.acknowledged-upstream-source-lock/v1"
                ),
                "source": "fixture",
                "acknowledged": True,
                "actual": {
                    "exact_checkout_root": True,
                    "head": "1" * 40,
                    "branch": "main",
                    "detached": False,
                    "clean": True,
                    "remote": "https://example.invalid/fixture.git",
                },
                "validation": {"usable": True},
                "failure_reasons": [],
                "errors": [],
            }
            with (
                patch(
                    "Tools.dcsmizzer.pydcs_static.upstream_source_lock_status",
                    return_value=acknowledged_lock,
                ),
                patch(
                    "Tools.dcsmizzer.br_static.upstream_source_lock_status",
                    return_value=acknowledged_lock,
                ),
            ):
                acknowledged_exact = combined_terrain_report(
                    pydcs,
                    br,
                    terrain="fixture",
                )

        self.assertEqual(report["coverage"]["dcs_theatres"], 2)
        self.assertEqual(report["coverage"]["dual_source_theatres"], 1)
        self.assertEqual(
            report["coverage"]["briefingroom_only_theatres"],
            1,
        )
        self.assertEqual(exact["coverage"]["matching_theatres"], 1)
        self.assertFalse(exact["coverage"]["exact_query_usable"])
        self.assertFalse(
            exact["source_lock"]["all_sources_commit_bound"]
        )
        self.assertEqual(
            {
                failure["source"]
                for failure in exact["source_lock"]["failure_reasons"]
            },
            {"pydcs", "briefingroom"},
        )
        self.assertNotEqual(
            exact["authority"],
            "explicit_multi_source_commit_bound_catalog",
        )
        self.assertTrue(
            acknowledged_exact["coverage"]["exact_query_usable"]
        )
        self.assertTrue(
            acknowledged_exact["source_lock"]["all_sources_commit_bound"]
        )
        self.assertEqual(
            acknowledged_exact["authority"],
            "explicit_multi_source_commit_bound_catalog",
        )
        self.assertEqual(exact["terrains"][0]["dcs_theatre"], "FixtureMap")
        self.assertEqual(
            exact["terrains"][0]["selected_parking_authority"],
            "pydcs",
        )

    @staticmethod
    def _write_br_sources(root: Path) -> None:
        theatres = root / "Database" / "Theaters"
        bounds = root / "DatabaseJSON" / "TheaterTerrainBounds"
        theatres.mkdir(parents=True)
        bounds.mkdir(parents=True)
        for declaration, dcs_id, display in (
            ("Fixture", "FixtureMap", "Fixture map"),
            ("Remote", "RemoteMap", "Remote map"),
        ):
            (theatres / f"{declaration}.ini").write_text(
                "[GUI]\n"
                f"DisplayName={display}\n\n"
                "[Theater]\n"
                f"DCSID={dcs_id}\n"
                "DefaultMapCenter=0,0\n",
                encoding="utf-8",
            )
            (bounds / f"{dcs_id}.json").write_text(
                json.dumps(
                    {
                        "landMasses": [[[0, 0], [10, 0], [10, 10]]],
                        "waters": [],
                    }
                ),
                encoding="utf-8",
            )
        (root / "DatabaseJSON" / "TheatersAirbases.json").write_text(
            json.dumps(
                [
                    {
                        "theatre": "FixtureMap",
                        "ID": 7,
                        "displayName": "Fixture Airbase",
                        "typeName": "Fixture Airbase",
                        "code": "FIX",
                        "pos": {
                            "DCS": {"x": 1000, "z": 2000},
                            "World": {
                                "alt": 50,
                                "lat": 52.5,
                                "lon": 13.4,
                            },
                        },
                        "runways": [],
                        "stands": [],
                        "parking": [],
                        "airdromeData": {
                            "ATC": [],
                            "TACAN": [],
                            "ILS": [],
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
