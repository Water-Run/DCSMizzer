from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.cli import main
from dcsmizzer_survey.dcs import (
    parse_steam_appmanifest,
    survey_dcs_installation,
)


class DcsInstallationSurveyTests(unittest.TestCase):
    def test_steam_manifest_parser_keeps_build_evidence_without_owner(self) -> None:
        # Would fail if personal Steam account metadata enters the baseline.
        manifest = parse_steam_appmanifest(
            '''
            "AppState"
            {
                "appid" "223750"
                "name" "DCS World Steam Edition"
                "buildid" "24331355"
                "LastOwner" "76561190000000000"
                "InstalledDepots"
                {
                    "223751"
                    {
                        "manifest" "123456"
                        "size" "789"
                    }
                }
            }
            '''
        )

        self.assertEqual(manifest["appid"], "223750")
        self.assertEqual(manifest["buildid"], "24331355")
        self.assertEqual(
            manifest["installed_depots"],
            [{"depot_id": "223751", "manifest": "123456", "size": "789"}],
        )
        self.assertNotIn("LastOwner", json.dumps(manifest))
        self.assertNotIn("76561190000000000", json.dumps(manifest))

    def test_survey_distinguishes_static_payloads_from_compatibility(self) -> None:
        # Would fail if presets are mislabeled as a complete pylon compatibility DB.
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            dcs_root = base / "DCSWorld"
            (dcs_root / "bin").mkdir(parents=True)
            (dcs_root / "bin" / "DCS.exe").write_bytes(b"fixture")
            database = dcs_root / "Scripts" / "Database"
            database.mkdir(parents=True)
            (database / "db_countries.lua").write_text(
                """
                country:add('USA', _('USA'), 'USA', 'USA')
                country:add('FRANCE', _('France'), 'France', 'FRA')
                """,
                encoding="utf-8",
            )
            payloads = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            payloads.mkdir(parents=True)
            (payloads / "Fixture.lua").write_text(
                """
                local unitPayloads = {
                  name = "Fixture",
                  payloads = {
                    [1] = {
                      pylons = {
                        [1] = { CLSID = "{A}", num = 2 },
                        [2] = { CLSID = "{B}", num = 1 },
                      },
                      tasks = { [1] = 11, [2] = 18 },
                    },
                  },
                }
                return unitPayloads
                """,
                encoding="utf-8",
            )
            aircraft = dcs_root / "Mods" / "aircraft" / "Fixture"
            aircraft.mkdir(parents=True)
            (aircraft / "entry.lua").write_text(
                """
                local self_ID = "Fixture Module"
                declare_plugin(self_ID, {
                  state = "installed",
                  update_id = "FIXTURE",
                })
                """,
                encoding="utf-8",
            )
            terrain = dcs_root / "Mods" / "terrains" / "FixtureMap"
            terrain.mkdir(parents=True)
            (terrain / "entry.lua").write_text(
                """
                local self_ID = "Fixture Terrain"
                declare_plugin(self_ID, { state = "installed" })
                """,
                encoding="utf-8",
            )
            steam_manifest = base / "appmanifest_223750.acf"
            steam_manifest.write_text(
                '"AppState" { "appid" "223750" "buildid" "42" }',
                encoding="utf-8",
            )

            report = survey_dcs_installation(
                dcs_root,
                steam_manifest,
                collected_at=datetime(2026, 7, 27, tzinfo=UTC),
                version_reader=lambda _path: "2.9.28.26283",
                official_release={
                    "version": "2.9.28.26283",
                    "release_date": "2026-07-22",
                    "url": (
                        "https://www.digitalcombatsimulator.com/"
                        "en/news/changelog/release/2.9.28.26283/"
                    ),
                },
            )

        self.assertEqual(report["dcs"]["product_version"], "2.9.28.26283")
        self.assertEqual(report["steam"]["buildid"], "42")
        self.assertEqual(report["countries"]["count"], 2)
        self.assertEqual(report["payload_presets"]["files"], 1)
        self.assertEqual(report["payload_presets"]["parsed"], 1)
        self.assertEqual(report["payload_presets"]["presets"], 1)
        self.assertEqual(report["payload_presets"]["pylon_assignments"], 2)
        self.assertEqual(report["payload_presets"]["unique_clsids"], 2)
        self.assertEqual(report["payload_presets"]["task_ids"], [11, 18])
        self.assertEqual(
            report["coverage"]["weapon_pylon_compatibility"]["status"],
            "runtime_registry_export_required",
        )
        self.assertEqual(
            report["coverage"]["weapon_pylon_compatibility"][
                "presets_are_compatibility"
            ],
            False,
        )
        self.assertEqual(
            report["coverage"]["airbases_runways_parking"]["status"],
            "per_terrain_runtime_export_required",
        )
        self.assertEqual(
            report["release_cross_check"]["status"],
            "matches_official_release",
        )
        self.assertNotIn(str(dcs_root), json.dumps(report))
        self.assertNotIn(str(steam_manifest), json.dumps(report))

    def test_cli_dcs_command_writes_machine_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            dcs_root = base / "DCSWorld"
            (dcs_root / "bin").mkdir(parents=True)
            (dcs_root / "bin" / "DCS.exe").write_bytes(b"fixture")
            (dcs_root / "Scripts" / "Database").mkdir(parents=True)
            (dcs_root / "Scripts" / "Database" / "db_countries.lua").write_text(
                "country:add('USA', _('USA'), 'USA', 'USA')\n",
                encoding="utf-8",
            )
            steam_manifest = base / "appmanifest.acf"
            steam_manifest.write_text(
                '"AppState" { "appid" "223750" "buildid" "42" }',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "dcs",
                    "--dcs-root",
                    str(dcs_root),
                    "--steam-manifest",
                    str(steam_manifest),
                    "--product-version",
                    "fixture-version",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            report["schema"],
            "dcsmizzer.dcs-installation-survey/v1",
        )
        self.assertEqual(report["dcs"]["product_version"], "fixture-version")


if __name__ == "__main__":
    unittest.main()
