from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.report_views import output_view  # noqa: E402
from dcsmizzer.weather import (  # noqa: E402
    cloud_preset_report,
    validate_weather_consistency,
    weather_constraints_report,
    weather_registry_report,
)


CLOUDS = """
cloudsPresets =
{
    RainyPreset1 =
    {
        visibleInGUI = true,
        readableNameShort = _("Overcast And Rain 1"),
        precipitationPower = 0.3,
        presetAltMin = 420,
        presetAltMax = 2940,
        thumbnailName = "rain.png",
        layers = {
            [1] = {},
        },
    },
    ClearPreset =
    {
        visibleInGUI = true,
        readableNameShort = _("Clear"),
        precipitationPower = 0,
        presetAltMin = 1000,
        presetAltMax = 5000,
        layers = {},
    },
}
"""

ME_WEATHER = """
local precptnsList = {
    _('NONE'),
    _('RAIN'),
    _('THUNDERSTORM'),
    _('SNOW'),
    _('SNOWSTORM'),
}

local precptns = {
    {
        name = _('NONE'),
    },
    {
        name = _('RAIN'),
        minDensity = 5,
        minTemp = 0,
    },
    {
        name = _('THUNDERSTORM'),
        minDensity = 9,
        minTemp = 0,
    },
    {
        name = _('SNOW'),
        minDensity = 5,
        maxTemp = 0,
    },
    {
        name = _('SNOWSTORM'),
        minDensity = 9,
        maxTemp = 0,
    },
}

local temperatures = {
    [1] = { min = -50, max = 50 },
    [2] = { min = -50, max = 50 },
    [3] = { min = -50, max = 50 },
    [4] = { min = -50, max = 50 },
}

function getPrecptns(season, density, temp)
    for k, v in pairs(precptns) do
        if (nil == v.minDensity) or (v.minDensity <= density) then
            if (nil == v.minTemp) or (v.minTemp <= temp) then
                if (nil == v.maxTemp) or (v.maxTemp >= temp) then
                end
            end
        end
    end
end

function updatePrecptns()
    local curPrecptns = precptnsList[vdata.clouds.iprecptns + 1]
end

function applyTempRestrictions()
    if Terrain.getTempratureRangeByDate then
    end
end

local function createFogPanel()
    item = ListBoxItem.new(cdata.off)
    item.modeId = 1
    item = ListBoxItem.new(cdata.auto)
    item.modeId = 2
    item = ListBoxItem.new(cdata.manual)
    item.modeId = 4
end

local function createDustPanel()
    function c_enable_dust:onChange()
        if (vdata.enable_dust == false) then
            vdata.dust_density = 0
        elseif vdata.dust_density < 300 then
            vdata.dust_density = 300
        end
    end
end

function fixFog(a_data)
    if a_data.fog2 and a_data.fog2.mode ~= 1 then
        a_data.enable_dust = false
    end
end
"""


def _preset_text(
    name: str,
    *,
    precipitation: int = 0,
    density: int = 0,
    temperature: int = 20,
    atmosphere_type: int = 0,
) -> str:
    cyclones = "    cyclones = {},\n" if atmosphere_type == 1 else ""
    return f"""
vdata = {{
    name = {json.dumps(name)},
    name_cn = "fixture",
    atmosphere_type = {atmosphere_type},
    season = {{ temperature = {temperature} }},
    clouds = {{
        base = 1000,
        thickness = 500,
        density = {density},
        iprecptns = {precipitation},
    }},
    wind = {{
        atGround = {{ speed = 0, dir = 0 }},
        at2000 = {{ speed = 0, dir = 0 }},
        at8000 = {{ speed = 0, dir = 0 }},
    }},
    groundTurbulence = 0,
    visibility = {{ distance = 80000 }},
    qnh = 760,
    fog2 = {{ mode = 1 }},
    enable_dust = false,
    dust_density = 0,
{cyclones}
}}
"""


def _weather_fixture(root: Path, *, preset_count: int = 17) -> None:
    modules = root / "MissionEditor" / "modules"
    modules.mkdir(parents=True)
    (modules / "me_weather.lua").write_text(ME_WEATHER, encoding="utf-8")
    presets = root / "MissionEditor" / "data" / "scripts" / "weather"
    dynamic = presets / "dynamic"
    dynamic.mkdir(parents=True)
    for index in range(preset_count - 1):
        (presets / f"Preset {index:02d}.lua").write_text(
            _preset_text(f"Fixture preset {index:02d}"),
            encoding="utf-8",
        )
    (dynamic / "default.lua").write_text(
        _preset_text("Fixture dynamic default", atmosphere_type=1),
        encoding="utf-8",
    )


class WeatherPresetTests(unittest.TestCase):
    def test_extracts_literal_current_install_preset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "Config" / "Effects"
            source.mkdir(parents=True)
            (source / "clouds.lua").write_text(CLOUDS, encoding="utf-8")

            report = cloud_preset_report(root, preset="RainyPreset1")

        self.assertEqual(report["coverage"]["literal_presets"], 2)
        self.assertEqual(report["coverage"]["matching_presets"], 1)
        self.assertEqual(
            report["presets"][0]["readable_name_short"],
            "Overcast And Rain 1",
        )
        self.assertEqual(report["presets"][0]["precipitation_power"], 0.3)
        self.assertEqual(
            report["presets"][0]["base_altitude_range"],
            {"minimum": 420, "maximum": 2940},
        )

    def test_cli_rejects_invented_preset_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "Config" / "Effects"
            source.mkdir(parents=True)
            (source / "clouds.lua").write_text(CLOUDS, encoding="utf-8")
            stdout = io.StringIO()

            exit_code = main(
                [
                    "dcs-cloud-presets",
                    "--dcs-root",
                    str(root),
                    "--preset",
                    "Rainy",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["coverage"]["matching_presets"], 0)
        self.assertEqual(report["presets"], [])


class WeatherRegistryTests(unittest.TestCase):
    def test_parses_seventeen_static_sources_without_executing_lua(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)

            report = weather_registry_report(root)

        self.assertEqual(report["schema"], "dcsmizzer.dcs-weather-presets/v1")
        self.assertFalse(report["dcs_started"])
        self.assertEqual(report["coverage"]["source_files"], 17)
        self.assertEqual(report["coverage"]["parsed_presets"], 17)
        self.assertEqual(report["coverage"]["parse_failures"], 0)
        self.assertEqual(report["coverage"]["returned_presets"], 17)
        self.assertEqual(report["coverage"]["dynamic_presets"], 1)
        self.assertEqual(report["coverage"]["static_presets"], 16)
        self.assertEqual(report["coverage"]["fields_complete_presets"], 17)
        self.assertEqual(report["coverage"]["fields_incomplete_presets"], 0)
        self.assertEqual(report["coverage"]["usable_presets"], 17)
        self.assertTrue(
            all(
                item["validation"]["fields_complete"]
                and item["validation"]["consistent"]
                for item in report["presets"]
            )
        )
        dynamic = next(
            item for item in report["presets"] if item["id"] == "dynamic/default"
        )
        self.assertEqual(dynamic["kind"], "dynamic")
        self.assertEqual(dynamic["weather"]["atmosphere_type"], 1)
        self.assertEqual(len(dynamic["source_sha256"]), 64)

    def test_filter_and_limit_are_exact_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)

            filtered = weather_registry_report(
                root,
                preset="dynamic/default",
            )
            limited = weather_registry_report(root, limit=3)

        self.assertEqual(filtered["coverage"]["matching_presets"], 1)
        self.assertEqual(
            [item["id"] for item in filtered["presets"]],
            ["dynamic/default"],
        )
        self.assertEqual(limited["coverage"]["returned_presets"], 3)
        self.assertTrue(limited["coverage"]["truncated"])

    def test_missing_supported_fields_make_preset_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root, preset_count=2)
            source = (
                root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "weather"
                / "Preset 00.lua"
            )
            source.write_text(
                'vdata = { name = "Incomplete", clouds = {} }',
                encoding="utf-8",
            )

            report = weather_registry_report(root, preset="Preset 00")

        validation = report["presets"][0]["validation"]
        self.assertFalse(validation["fields_complete"])
        self.assertTrue(validation["consistent"])
        self.assertIn("vdata.qnh", validation["missing_fields"])
        self.assertIn(
            "vdata.clouds.iprecptns",
            validation["missing_fields"],
        )
        self.assertEqual(report["coverage"]["fields_incomplete_presets"], 1)
        self.assertEqual(report["coverage"]["usable_presets"], 1)

    def test_unknown_field_and_cyclone_truncation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root, preset_count=2)
            source = (
                root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "weather"
                / "dynamic"
                / "default.lua"
            )
            cyclone = (
                "{ pressure_spread = 1, centerZ = 2, groupId = 3, "
                "ellipticity = 4, rotation = 5, pressure_excess = 6, "
                "centerX = 7 }"
            )
            source.write_text(
                _preset_text(
                    "Fixture dynamic default",
                    atmosphere_type=1,
                )
                .replace(
                    "    cyclones = {},",
                    "    cyclones = {"
                    + ", ".join(cyclone for _ in range(33))
                    + "},\n    future_weather_field = 1,",
                ),
                encoding="utf-8",
            )

            report = weather_registry_report(
                root,
                preset="dynamic/default",
            )

        validation = report["presets"][0]["validation"]
        self.assertFalse(validation["fields_complete"])
        self.assertEqual(
            validation["unsupported_fields"],
            ["vdata.future_weather_field"],
        )
        self.assertEqual(
            validation["truncated_fields"],
            ["vdata.cyclones"],
        )

    def test_executable_or_malformed_preset_is_reported_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)
            marker = root / "must-not-exist"
            source = (
                root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "weather"
                / "Executable.lua"
            )
            source.write_text(
                'os.execute("touch must-not-exist")',
                encoding="utf-8",
            )

            report = weather_registry_report(root)

            self.assertFalse(marker.exists())
        self.assertEqual(report["coverage"]["source_files"], 18)
        self.assertEqual(report["coverage"]["parsed_presets"], 17)
        self.assertEqual(report["coverage"]["parse_failures"], 1)
        self.assertEqual(
            report["parse_failures"],
            [
                {
                    "source": "Executable.lua",
                    "error_code": "lua_syntax_error",
                }
            ],
        )

    def test_constraints_are_extracted_from_me_weather_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)

            report = weather_constraints_report(root)

        precipitation = report["constraints"]["precipitation_types"]
        self.assertEqual(
            [(item["id"], item["name"]) for item in precipitation],
            [
                (0, "NONE"),
                (1, "RAIN"),
                (2, "THUNDERSTORM"),
                (3, "SNOW"),
                (4, "SNOWSTORM"),
            ],
        )
        self.assertEqual(precipitation[1]["minimum_density"], 5)
        self.assertEqual(precipitation[1]["minimum_temperature_c"], 0)
        self.assertEqual(precipitation[3]["maximum_temperature_c"], 0)
        self.assertEqual(
            report["constraints"]["fog_modes"],
            [
                {"id": 1, "name": "off"},
                {"id": 2, "name": "auto"},
                {"id": 4, "name": "manual"},
            ],
        )
        self.assertEqual(
            report["constraints"]["dust"]["minimum_density_when_enabled"],
            300,
        )
        self.assertTrue(
            report["constraints"]["temperature"][
                "terrain_date_override_available"
            ]
        )
        self.assertEqual(len(report["source_sha256"]), 64)

    def test_precipitation_boundary_and_fog_dust_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)
            constraints = weather_constraints_report(root)

            rain = validate_weather_consistency(
                {
                    "season": {"temperature": 0},
                    "clouds": {"density": 5, "iprecptns": 1},
                    "fog2": {"mode": 1},
                    "enable_dust": True,
                    "dust_density": 300,
                },
                constraints,
            )
            snow = validate_weather_consistency(
                {
                    "season": {"temperature": 0},
                    "clouds": {"density": 5, "iprecptns": 3},
                },
                constraints,
            )
            invalid = validate_weather_consistency(
                {
                    "season": {"temperature": 1},
                    "clouds": {"density": 8, "iprecptns": 4},
                    "fog2": {"mode": 4},
                    "enable_dust": True,
                    "dust_density": 299,
                },
                constraints,
            )

        self.assertTrue(rain["consistent"])
        self.assertTrue(snow["consistent"])
        self.assertFalse(invalid["consistent"])
        self.assertEqual(
            {item["code"] for item in invalid["errors"]},
            {
                "precipitation_density_below_minimum",
                "precipitation_temperature_above_maximum",
                "fog_dust_mutually_exclusive",
                "dust_density_below_minimum",
            },
        )

    def test_invalid_precipitation_and_fog_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)
            constraints = weather_constraints_report(root)

            report = validate_weather_consistency(
                {
                    "clouds": {"density": 10, "iprecptns": 5},
                    "fog2": {"mode": 3},
                },
                constraints,
            )

        self.assertFalse(report["consistent"])
        self.assertEqual(
            {item["code"] for item in report["errors"]},
            {"unknown_precipitation_type", "unknown_fog_mode"},
        )

    def test_constraint_source_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)
            source = root / "MissionEditor" / "modules" / "me_weather.lua"
            source.write_text(
                ME_WEATHER.replace(
                    "a_data.enable_dust = false",
                    "a_data.enable_dust = true",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "fog and dust exclusion",
            ):
                weather_constraints_report(root)

    def test_comments_and_strings_cannot_supply_weather_rules(self) -> None:
        decoys = (
            (
                "--[[ if a_data.fog2 and a_data.fog2.mode ~= 1 then "
                "a_data.enable_dust = false end ]]"
            ),
            (
                'local decoy = "if a_data.fog2 and '
                "a_data.fog2.mode ~= 1 then "
                'a_data.enable_dust = false end"'
            ),
        )
        for decoy in decoys:
            with self.subTest(decoy=decoy[:8]):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    _weather_fixture(root)
                    source = (
                        root
                        / "MissionEditor"
                        / "modules"
                        / "me_weather.lua"
                    )
                    source.write_text(
                        ME_WEATHER.replace(
                            "a_data.enable_dust = false",
                            "a_data.enable_dust = true",
                        )
                        + "\n"
                        + decoy,
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        ValueError,
                        "fog and dust exclusion",
                    ):
                        weather_constraints_report(root)

    def test_precipitation_id_list_must_match_constraint_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root)
            source = root / "MissionEditor" / "modules" / "me_weather.lua"
            source.write_text(
                ME_WEATHER.replace(
                    "    _('RAIN'),\n    _('THUNDERSTORM'),",
                    "    _('THUNDERSTORM'),\n    _('RAIN'),",
                    1,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "type and ID tables",
            ):
                weather_constraints_report(root)

    def test_search_covers_all_sources_before_view_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _weather_fixture(root, preset_count=101)

            report = weather_registry_report(root)
            view = output_view(
                "dcs-weather",
                report,
                search="Fixture preset 99",
            )

        self.assertEqual(report["coverage"]["parsed_presets"], 101)
        self.assertEqual(report["coverage"]["returned_presets"], 101)
        self.assertFalse(report["coverage"]["truncated"])
        self.assertTrue(view.query_matched)
        self.assertEqual(view.report["catalog"]["matching_items"], 1)


if __name__ == "__main__":
    unittest.main()
