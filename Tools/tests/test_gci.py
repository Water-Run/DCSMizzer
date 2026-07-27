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

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.gci import gci_evidence_report  # noqa: E402


MISSION = b"""
mission = {
  theatre = "FixtureMap",
  coalition = {
    red = {
      country = {
        [1] = {
          id = 0,
          vehicle = {
            group = {
              [1] = {
                route = {
                  points = {
                    [1] = {
                      task = {
                        id = "ComboTask",
                        params = {
                          tasks = {
                            [1] = {
                              id = "WrappedAction",
                              params = {
                                action = {
                                  id = "ActivateGCI",
                                  params = {
                                    unitId = 3,
                                    channel = 5,
                                    radius = 200000,
                                    x = 100,
                                    y = 200,
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
                units = {
                  [1] = {
                    unitId = 3,
                    type = "GCI_station_MiG29",
                  },
                  [2] = {
                    unitId = 4,
                    type = "1L13 EWR",
                  },
                },
              },
            },
          },
        },
      },
    },
  },
}
"""


class GciEvidenceTests(unittest.TestCase):
    def test_reports_current_static_training_and_manual_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = (
                root
                / "CoreMods"
                / "tech"
                / "Fixture"
                / "Database"
                / "GCI_station_MAZ.lua"
            )
            source.parent.mkdir(parents=True)
            source.write_text(
                """
                GT.Name = "GCI_station_MiG29";
                GT.Countries = {"Russia", "USSR"}
                """,
                encoding="utf-8",
            )
            training = (
                root
                / "Mods"
                / "aircraft"
                / "MiG-29-Fulcrum"
                / "Missions"
                / "Training"
            )
            training.mkdir(parents=True)
            with zipfile.ZipFile(training / "fixture.miz", "w") as archive:
                archive.writestr("mission", MISSION)
            manual = (
                root
                / "Mods"
                / "aircraft"
                / "MiG-29-Fulcrum"
                / "Doc"
                / "DCS MiG-29A Flight Manual EN.pdf"
            )
            manual.parent.mkdir(parents=True)
            manual.write_bytes(b"%PDF-fixture")

            report = gci_evidence_report(root)
            stdout = io.StringIO()
            exit_code = main(
                ["dcs-gci", "--dcs-root", str(root)],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            report["station_declarations"][0]["countries"],
            ["Russia", "USSR"],
        )
        observed = report["official_training_observations"]
        self.assertEqual(
            observed["task_chains"],
            [["ComboTask", "WrappedAction", "ActivateGCI"]],
        )
        self.assertEqual(observed["channels"], [5])
        self.assertEqual(observed["radii_m"], [200000])
        self.assertIn("1L13 EWR", observed["compatible_radar_types"])
        self.assertFalse(
            report["construction_requirements"]["ai_guidance_supported"]
        )
        self.assertNotIn(temp_dir, json.dumps(report))
        self.assertEqual(
            json.loads(stdout.getvalue())["schema"],
            "dcsmizzer.dcs-mig29-gci/v1",
        )


if __name__ == "__main__":
    unittest.main()
