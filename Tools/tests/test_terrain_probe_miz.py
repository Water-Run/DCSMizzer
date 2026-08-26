from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.archive import inspect_miz  # noqa: E402
from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.lua import LuaTable, parse_lua_bytes  # noqa: E402
from dcsmizzer.mission import analyse_miz  # noqa: E402
from dcsmizzer.terrain_probe import generate_terrain_probe_script  # noqa: E402
from dcsmizzer.terrain_probe_miz import instrument_terrain_probe_miz  # noqa: E402


class TerrainProbeMizTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.mission = self.root / "source.miz"
        self.request = self.root / "request.json"
        self.script = self.root / "probe.lua"
        self.request.write_text(
            json.dumps(
                {
                    "schema": "dcsmizzer.terrain-probe-request/v1",
                    "terrain": "SinaiMap",
                    "sample_match_tolerance_m": 1.0,
                    "samples": [{"x": -7363.65, "y": -10783.41}],
                }
            ),
            encoding="utf-8",
        )
        self._write_miz(self.mission)
        with patch(
            "dcsmizzer.terrain_probe._installed_dcs_identity",
            return_value={
                "product_version": "2.9.28.26385",
                "steam_build_id": "24431605",
            },
        ):
            generate_terrain_probe_script(
                self.request,
                self.root,
                self.script,
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_instruments_exact_resource_and_preserves_entities(self) -> None:
        output = self.root / "instrumented.miz"
        source_analysis = analyse_miz(self.mission)

        report = instrument_terrain_probe_miz(
            self.mission,
            self.request,
            self.script,
            output,
        )
        analysis = analyse_miz(output)
        archive = inspect_miz(output)
        with zipfile.ZipFile(output) as miz:
            mission = parse_lua_bytes(miz.read("mission")).document.get("mission")
            map_resource = parse_lua_bytes(
                miz.read("l10n/DEFAULT/mapResource")
            ).document.get("mapResource")
            resource_member = report["probe"]["resource_member"]
            resource = miz.read(resource_member)

        self.assertTrue(report["validation"]["mission_entities_preserved"])
        self.assertTrue(archive.safe)
        self.assertEqual(archive.crc_status, "passed")
        self.assertEqual(analysis.stats.groups, source_analysis.stats.groups)
        self.assertEqual(analysis.stats.units, source_analysis.stats.units)
        self.assertEqual(
            analysis.stats.human_slots,
            source_analysis.stats.human_slots,
        )
        self.assertEqual(resource, self.script.read_bytes())
        self.assertIsInstance(mission, LuaTable)
        self.assertIsInstance(map_resource, LuaTable)
        index = report["probe"]["trigger_index"]
        rule = mission.get("trigrules").get(index)
        action = rule.get("actions").get(1)
        self.assertEqual(action.get("predicate"), "a_do_script_file")
        self.assertEqual(action.get("file"), report["probe"]["resource_key"])
        self.assertEqual(
            mission.get("trig").get("conditions").get(index),
            "return(true)",
        )
        self.assertIn(
            report["probe"]["resource_key"],
            mission.get("trig").get("actions").get(index),
        )
        self.assertIn(
            f"conditions[{index}]",
            mission.get("trig").get("funcStartup").get(index),
        )
        self.assertEqual(
            map_resource.get(report["probe"]["resource_key"]),
            Path(resource_member).name,
        )

    def test_output_is_deterministic_and_cli_writes_no_source(self) -> None:
        first = self.root / "first.miz"
        second = self.root / "second.miz"
        before = self.mission.read_bytes()
        stdout = io.StringIO()

        first_report = instrument_terrain_probe_miz(
            self.mission,
            self.request,
            self.script,
            first,
        )
        exit_code = main(
            [
                "terrain-probe-instrument",
                "--mission",
                str(self.mission),
                "--request",
                str(self.request),
                "--script",
                str(self.script),
                "--output",
                str(second),
            ],
            stdout=stdout,
        )
        second_report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(
            first_report["output"]["sha256"],
            second_report["output"]["sha256"],
        )
        self.assertEqual(self.mission.read_bytes(), before)

    def test_rejects_wrong_request_script_and_existing_output(self) -> None:
        wrong = json.loads(self.request.read_text(encoding="utf-8"))
        wrong["terrain"] = "Caucasus"
        self.request.write_text(json.dumps(wrong), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound|does not match"):
            instrument_terrain_probe_miz(
                self.mission,
                self.request,
                self.script,
                self.root / "wrong.miz",
            )

        self.request.write_text(
            json.dumps(
                {
                    "schema": "dcsmizzer.terrain-probe-request/v1",
                    "terrain": "SinaiMap",
                    "sample_match_tolerance_m": 1.0,
                    "samples": [{"x": -7363.65, "y": -10783.41}],
                }
            ),
            encoding="utf-8",
        )
        output = self.root / "existing.miz"
        output.write_bytes(b"user data")
        with self.assertRaisesRegex(ValueError, "already exists"):
            instrument_terrain_probe_miz(
                self.mission,
                self.request,
                self.script,
                output,
            )
        self.assertEqual(output.read_bytes(), b"user data")

    def test_force_never_replaces_source_or_hard_link_alias(self) -> None:
        before = self.mission.read_bytes()
        with self.assertRaisesRegex(ValueError, "differ from every input"):
            instrument_terrain_probe_miz(
                self.mission,
                self.request,
                self.script,
                self.mission,
                force=True,
            )
        self.assertEqual(self.mission.read_bytes(), before)

        alias = self.root / "source-hardlink.miz"
        try:
            alias.hardlink_to(self.mission)
        except OSError as error:
            self.skipTest(f"hard links unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "must not alias"):
            instrument_terrain_probe_miz(
                self.mission,
                self.request,
                self.script,
                alias,
                force=True,
            )
        self.assertEqual(self.mission.read_bytes(), before)

    @staticmethod
    def _write_miz(path: Path) -> None:
        mission = b'''mission = {
  ["version"] = 22,
  ["theatre"] = "SinaiMap",
  ["coalition"] = {
    ["blue"] = {
      ["country"] = {
        [1] = {
          ["id"] = 2,
          ["name"] = "USA",
          ["plane"] = {
            ["group"] = {
              [1] = {
                ["name"] = "Fixture flight",
                ["units"] = {
                  [1] = { ["type"] = "TF-51D", ["skill"] = "Player" },
                  [2] = { ["type"] = "TF-51D", ["skill"] = "Client" },
                },
              },
            },
          },
        },
      },
    },
  },
  ["trigrules"] = {},
  ["trig"] = {
    ["conditions"] = {},
    ["actions"] = {},
    ["funcStartup"] = {},
    ["func"] = {},
  },
}
'''
        members = {
            "mission": mission,
            "options": b"options = {}\n",
            "warehouses": b"warehouses = { airports = {}, warehouses = {} }\n",
            "l10n/DEFAULT/dictionary": b"dictionary = {}\n",
            "l10n/DEFAULT/mapResource": b"mapResource = {}\n",
            "theatre": b"SinaiMap",
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as miz:
            for name, payload in members.items():
                miz.writestr(name, payload)


if __name__ == "__main__":
    unittest.main()
