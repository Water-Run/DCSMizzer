from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.dcs_static import (  # noqa: E402
    airbase_beacon_report,
    module_index_report,
    payload_index_report,
    payload_report,
)


PAYLOAD = """
local unitPayloads = {
  name = "Fixture Plane",
  payloads = {
    [1] = {
      name = "Intercept",
      displayName = _("Intercept"),
      pylons = {
        [1] = { CLSID = "{ONE}", num = 1 },
        [2] = { CLSID = "{TANK}", num = 4 },
      },
      tasks = { [1] = 11, },
    },
  },
}
return unitPayloads
"""

BEACONS = """
dofile('ignored.lua')
beacons = {
  {
    display_name = _('Fixture Airbase');
    beaconId = 'airfield7_0';
    type = BEACON_TYPE_ILS_LOCALIZER;
    callsign = 'FIX';
    frequency = 108300000;
    position = { 1000, 50, 2000 };
    direction = 90;
    positionGeo = { latitude = 52.5, longitude = 13.4 };
  };
  {
    display_name = _('Fixture Airbase');
    beaconId = 'airfield7_1';
    type = BEACON_TYPE_ILS_GLIDESLOPE;
    callsign = 'FXG';
    position = { 1100, 55, 2100 };
    direction = 90;
    positionGeo = { latitude = 52.51, longitude = 13.41 };
  };
  {
    display_name = _('Other Airbase');
    beaconId = 'airfield8_0';
    type = BEACON_TYPE_TACAN;
    callsign = 'OTH';
    channel = 44;
    position = { 3000, 60, 4000 };
    positionGeo = { latitude = 53, longitude = 14 };
  };
}
"""

RADIO = """
radios = {
  {
    -- Fixture Airbase
    radioId = 'airfield7_0';
    callsign = {{["common"] = {_("FIXTURE"), "FIXTURE"}}};
  };
  {
    -- Radio Only
    radioId = 'airfield9_0';
    callsign = {{["common"] = {_("RADIO"), "RADIO"}}};
  };
}
"""


class CurrentDcsStaticTests(unittest.TestCase):
    def test_module_index_links_plugin_flyable_and_payload_literals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            module = dcs_root / "Mods" / "aircraft" / "Fixture"
            payloads = module / "UnitPayloads"
            payloads.mkdir(parents=True)
            (module / "entry.lua").write_text(
                """
                local self_ID = "Fixture Plugin"
                local flyable_ID = 'Fixture Plane'
                declare_plugin(self_ID, {})
                -- make_flyable("Commented Type")
                make_flyable(flyable_ID, "Cockpit")
                """,
                encoding="utf-8",
            )
            (payloads / "Fixture.lua").write_text(
                PAYLOAD,
                encoding="utf-8",
            )
            (module / "Fixture Plane.lua").write_text(
                'declare_service_life("Fixture Plane", "Fixtureland", '
                "1984, 2001)\n",
                encoding="utf-8",
            )

            report = module_index_report(
                dcs_root,
                unit_type="Fixture Plane",
                service_country="fixtureland",
                service_year=1988,
            )
            mismatch = module_index_report(
                dcs_root,
                unit_type="Fixture Plane",
                service_country="Elsewhere",
                service_year=1988,
            )

        self.assertEqual(report["coverage"]["matching_modules"], 1)
        record = report["modules"][0]
        self.assertEqual(record["plugin_ids"], ["Fixture Plugin"])
        self.assertEqual(record["flyable_types"], ["Fixture Plane"])
        self.assertEqual(
            record["default_payload_unit_types"],
            ["Fixture Plane"],
        )
        self.assertTrue(report["unit_type_resolution"]["flyable_declared"])
        self.assertEqual(
            report["unit_type_resolution"][
                "declared_plugin_ids_in_matching_modules"
            ],
            ["Fixture Plugin"],
        )
        self.assertEqual(
            report["unit_type_resolution"]["flyable_plugin_ids"],
            ["Fixture Plugin"],
        )
        self.assertEqual(
            report["unit_type_resolution"]["service_life_records"][0][
                "country"
            ],
            "Fixtureland",
        )
        self.assertTrue(
            report["unit_type_resolution"]["service_life_query"]["matched"]
        )
        self.assertEqual(
            report["coverage"]["matching_service_life_records"],
            1,
        )
        self.assertFalse(
            mismatch["unit_type_resolution"]["service_life_query"]["matched"]
        )
        self.assertNotIn("Commented Type", json.dumps(report))
        self.assertNotIn(temp_dir, json.dumps(report))

    def test_payload_lookup_includes_coremods_unitpayload_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            central = (
                dcs_root / "MissionEditor" / "data" / "scripts" / "UnitPayloads"
            )
            module = (
                dcs_root
                / "CoreMods"
                / "aircraft"
                / "Fixture"
                / "UnitPayloads"
            )
            central.mkdir(parents=True)
            module.mkdir(parents=True)
            (central / "Legacy.lua").write_text(
                PAYLOAD.replace("Fixture Plane", "Legacy Plane"),
                encoding="utf-8",
            )
            (module / "Fixture.lua").write_text(PAYLOAD, encoding="utf-8")

            report = payload_report(dcs_root, "Fixture Plane")
            index = payload_index_report(dcs_root)

        self.assertEqual(report["files_scanned"], 2)
        self.assertEqual(report["presets"][0]["pylons"][1]["num"], 4)
        self.assertEqual(
            report["unit_type_sources"][0]["source"],
            "CoreMods/aircraft/Fixture/UnitPayloads/Fixture.lua",
        )
        self.assertEqual(
            [record["unit_type"] for record in index["unit_types"]],
            ["Fixture Plane", "Legacy Plane"],
        )
        self.assertEqual(
            index["coverage"],
            {
                "source_files_discovered": 2,
                "source_files_parsed": 2,
                "unit_types": 2,
                "presets": 2,
                "pylon_assignments": 4,
                "unique_clsids": 2,
                "task_ids": [11],
            },
        )
        encoded = json.dumps(index)
        self.assertNotIn(temp_dir, encoded)

    def test_airbase_beacons_map_static_airfield_ids_without_overclaiming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            terrain = dcs_root / "Mods" / "terrains" / "FixtureTerrain"
            terrain.mkdir(parents=True)
            (terrain / "beacons.lua").write_text(BEACONS, encoding="utf-8")
            (terrain / "radio.lua").write_text(RADIO, encoding="utf-8")

            index = airbase_beacon_report(dcs_root, "FixtureTerrain")
            detail = airbase_beacon_report(
                dcs_root,
                "fixtureterrain",
                airdrome_id=7,
            )

        self.assertFalse(index["coverage_complete"])
        self.assertEqual(index["airfield_ids_with_beacons"], 2)
        self.assertEqual(index["airfield_ids_with_radio"], 2)
        self.assertEqual(index["airfield_ids_union"], 3)
        self.assertNotIn("beacons", index["airbases"][0])
        self.assertEqual(detail["airbases"][0]["airdrome_id"], 7)
        self.assertEqual(detail["airbases"][0]["names"], ["Fixture Airbase"])
        self.assertEqual(len(detail["airbases"][0]["beacons"]), 2)
        self.assertEqual(detail["airbases"][0]["radio_count"], 1)
        self.assertEqual(
            detail["airbases"][0]["callsigns"],
            ["FIX", "FIXTURE", "FXG"],
        )
        self.assertEqual(
            detail["airbases"][0]["map_position_bounds"]["x"],
            [1000.0, 1100.0],
        )


if __name__ == "__main__":
    unittest.main()
