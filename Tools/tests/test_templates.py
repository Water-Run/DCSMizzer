from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from Tools.dcsmizzer.cli import main
from Tools.dcsmizzer.templates import (
    options_template_report,
    warehouse_template_report,
)


OPTIONS = """
options = {
  VR = { enable = false },
  difficulty = {
    easyCommunication = true,
    easyFlight = false,
    fuel = false,
    immortal = false,
    labels = 1,
    padlock = true,
    radio = false,
    weapons = false,
  },
  format = 1,
  graphics = {},
  miscellaneous = {},
  plugins = {},
  sound = {
    hp_output = "{PRIVATE-HEADSET}",
    main_output = "{PRIVATE-SPEAKER}",
    main_layout = "private-layout",
    voice_chat_output = "{PRIVATE-VOICE-OUT}",
    voice_chat_input = "{PRIVATE-MIC}",
  },
  views = {},
}
"""

WAREHOUSE = """
function fillWarehouse()
  tmpAirportEquipment.unlimitedAircrafts = true
  tmpAirportEquipment.unlimitedFuel = true
  tmpAirportEquipment.unlimitedMunitions = true
  tmpAirportEquipment.dynamicSpawn = false
  tmpAirportEquipment.allowHotStart = false
  tmpAirportEquipment.speed = 16.666666
  tmpAirportEquipment.periodicity = 30
  tmpAirportEquipment.size = 100
  tmpAirportEquipment.jet_fuel.InitFuel = 100
  tmpAirportEquipment.gasoline.InitFuel = 100
  tmpAirportEquipment.methanol_mixture.InitFuel = 100
  tmpAirportEquipment.diesel.InitFuel = 100
  tmpAirportEquipment.OperatingLevel_Eqp = 10
  tmpAirportEquipment.OperatingLevel_Air = 10
  tmpAirportEquipment.OperatingLevel_Fuel = 10
  tmpAirportEquipment.dynamicCargo = true
end
"""


class CurrentInstallTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        options = (
            self.root
            / "MissionEditor"
            / "data"
            / "scripts"
            / "options.lua"
        )
        options.parent.mkdir(parents=True)
        options.write_text(OPTIONS, encoding="utf-8")
        warehouse = (
            self.root
            / "MissionEditor"
            / "modules"
            / "me_mission.lua"
        )
        warehouse.parent.mkdir(parents=True)
        warehouse.write_text(WAREHOUSE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_options_template_sanitizes_devices_and_applies_named_policy(
        self,
    ) -> None:
        report = options_template_report(
            self.root,
            player_name="Fixture pilot",
            full_sim=True,
        )

        options = report["options"]
        self.assertEqual(options["playerName"], "Fixture pilot")
        self.assertFalse(options["difficulty"]["easyCommunication"])
        self.assertEqual(options["difficulty"]["labels"], 0)
        self.assertEqual(
            set(report["policy"]["source_audio_fields_sanitized"]),
            {
                "hp_output",
                "main_output",
                "main_layout",
                "voice_chat_output",
                "voice_chat_input",
            },
        )
        self.assertTrue(
            all(
                options["sound"][field] == ""
                for field in report["policy"][
                    "audio_device_fields_forced_blank"
                ]
            )
        )

    def test_warehouse_template_uses_explicit_numeric_airport_fields(
        self,
    ) -> None:
        report = warehouse_template_report(
            self.root,
            [7, 12, 7],
        )

        fields = report["warehouses"]["airports"]["$fields"]
        self.assertEqual([field["key"] for field in fields], [7, 12])
        self.assertTrue(fields[0]["value"]["unlimitedAircrafts"])
        self.assertEqual(
            fields[0]["value"]["aircrafts"],
            {"planes": {}, "helicopters": {}},
        )
        self.assertFalse(report["source_code_executed"])

    def test_warehouse_template_rejects_unknown_coalition(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be one of"):
            warehouse_template_report(
                self.root,
                [7],
                coalition="blue",
            )

    def test_warehouse_template_has_complete_unlimited_substructure(
        self,
    ) -> None:
        report = warehouse_template_report(
            self.root,
            [7],
            coalition="BLUE",
        )

        warehouse = report["warehouses"]["airports"]["$fields"][0]["value"]
        self.assertEqual(warehouse["coalition"], "BLUE")
        self.assertEqual(
            set(warehouse["aircrafts"]),
            {"planes", "helicopters"},
        )
        self.assertTrue(
            all(
                warehouse[fuel]["InitFuel"] >= 0
                for fuel in (
                    "diesel",
                    "gasoline",
                    "jet_fuel",
                    "methanol_mixture",
                )
            )
        )

    def test_template_cli_returns_copy_ready_json(self) -> None:
        stdout = io.StringIO()
        exit_code = main(
            [
                "dcs-warehouse-template",
                "--dcs-root",
                str(self.root),
                "--airdrome-id",
                "7",
            ],
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(
            report["warehouses"]["airports"]["$fields"][0]["key"],
            7,
        )


if __name__ == "__main__":
    unittest.main()
