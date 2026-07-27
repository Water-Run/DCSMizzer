from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main


MISSION = b"""
mission = {
  version = 23,
  theatre = "FixtureMap",
  coalition = {
    blue = {
      country = {
        [1] = {
          plane = {
            group = {
              [1] = {
                task = "CAP",
                units = {
                  [1] = {
                    type = "Fixture Plane",
                    skill = "Client",
                    payload = {
                      pylons = {
                        [1] = { CLSID = "{FIXTURE}", },
                      },
                    },
                  },
                },
                route = {
                  points = {
                    [1] = {
                      action = "From Parking Area",
                      task = { id = "ComboTask", params = { tasks = {}, }, },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  },
  triggers = { zones = {}, },
  trigrules = {},
  goals = {},
}
"""


def write_miz(path: Path, *, unsafe: bool = False) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mission", MISSION)
        archive.writestr("options", b"options = {}")
        archive.writestr("warehouses", b"warehouses = { airports = {} }")
        archive.writestr(
            "l10n/DEFAULT/dictionary",
            b"dictionary = {}",
        )
        archive.writestr(
            "l10n/DEFAULT/mapResource",
            b"mapResource = {}",
        )
        if unsafe:
            archive.writestr("../escape.lua", b"return {}")


class ToolCliTests(unittest.TestCase):
    def test_tools_tree_contains_only_python_sources(self) -> None:
        non_python_files = sorted(
            str(path.relative_to(TOOLS_ROOT))
            for path in TOOLS_ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".py"
        )

        self.assertEqual(non_python_files, [])

    def test_capabilities_are_truthful_about_unimplemented_generation(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(["capabilities"], stdout=stdout, stderr=stderr)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(report["mission_generation"]["status"], "not_implemented")
        self.assertEqual(report["dcs_launch"]["status"], "not_implemented")
        self.assertEqual(report["inspect_miz"]["status"], "implemented")

    def test_inspect_miz_reports_separate_validation_levels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fixture.miz"
            write_miz(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["inspect", str(path)],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(report["validation"]["archive_valid"])
        self.assertTrue(report["validation"]["parse_valid"])
        self.assertIsNone(report["validation"]["runtime_valid"])
        self.assertEqual(report["mission"]["theatre"], "FixtureMap")
        self.assertEqual(report["mission"]["stats"]["human_slots"], {"Client": 1})
        self.assertEqual(report["mission"]["stats"]["payload_unique_clsids"], 1)

    def test_inspect_rejects_unsafe_archive_member_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsafe.miz"
            write_miz(path, unsafe=True)
            stdout = io.StringIO()

            exit_code = main(["inspect", str(path)], stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(report["validation"]["archive_valid"])
        self.assertFalse(report["archive"]["safe"])
        self.assertIn(
            "unsafe_member_path",
            [item["code"] for item in report["archive"]["diagnostics"]],
        )

    def test_inspect_cmp_checks_relative_mission_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "stage.miz").write_bytes(b"fixture")
            campaign = root / "fixture.cmp"
            campaign.write_text(
                """
                campaign = {
                  version = 1,
                  startStage = 1,
                  stages = {
                    [1] = {
                      missions = {
                        [1] = {
                          file = "stage.miz",
                          interval = { [1] = 0, [2] = 100 },
                        },
                      },
                    },
                  },
                }
                """,
                encoding="utf-8",
            )
            stdout = io.StringIO()

            exit_code = main(["inspect", str(campaign)], stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(report["validation"]["parse_valid"])
        self.assertTrue(report["validation"]["static_reference_valid"])
        self.assertIsNone(report["validation"]["runtime_valid"])
        self.assertEqual(report["campaign"]["resolved_references"], 1)

    def test_current_static_country_and_payload_lookup_are_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            database = dcs_root / "Scripts" / "Database"
            database.mkdir(parents=True)
            (database / "db_countries.lua").write_text(
                """
                country:add('USA', _('USA'), 'USA', 'USA')
                country:add('FRANCE', _('France'), 'France', 'FRA')
                """,
                encoding="utf-8",
            )
            payload_root = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            payload_root.mkdir(parents=True)
            (payload_root / "Fixture.lua").write_text(
                """
                local unitPayloads = {
                  name = "Fixture Plane",
                  payloads = {
                    [1] = {
                      name = "CAP",
                      pylons = {
                        [1] = { CLSID = "{A}", num = 2 },
                      },
                      tasks = { [1] = 11 },
                    },
                  },
                }
                return unitPayloads
                """,
                encoding="utf-8",
            )
            countries_out = io.StringIO()
            payloads_out = io.StringIO()

            countries_exit = main(
                ["dcs-countries", "--dcs-root", str(dcs_root)],
                stdout=countries_out,
            )
            payloads_exit = main(
                [
                    "dcs-payloads",
                    "--dcs-root",
                    str(dcs_root),
                    "--unit-type",
                    "Fixture Plane",
                ],
                stdout=payloads_out,
            )

        countries = json.loads(countries_out.getvalue())
        payloads = json.loads(payloads_out.getvalue())
        self.assertEqual(countries_exit, 0)
        self.assertEqual(countries["identifiers"], ["USA", "FRANCE"])
        self.assertEqual(countries["authority"], "current_install_static_source")
        self.assertEqual(payloads_exit, 0)
        self.assertFalse(payloads["compatibility_complete"])
        self.assertEqual(payloads["presets"][0]["pylons"][0]["CLSID"], "{A}")
        self.assertEqual(payloads["presets"][0]["tasks"], [11])


if __name__ == "__main__":
    unittest.main()
