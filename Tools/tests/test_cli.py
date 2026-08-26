from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import MAX_CLI_ERROR_BYTES, _build_parser, main  # noqa: E402


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


def write_miz(
    path: Path,
    *,
    mission: bytes = MISSION,
    unsafe: bool = False,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mission", mission)
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


def mark_zip_entries_encrypted(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    for signature, flag_offset in (
        (b"PK\x03\x04", 6),
        (b"PK\x01\x02", 8),
    ):
        start = 0
        while True:
            index = payload.find(signature, start)
            if index < 0:
                break
            flags_at = index + flag_offset
            flags = int.from_bytes(
                payload[flags_at : flags_at + 2],
                "little",
            )
            payload[flags_at : flags_at + 2] = (flags | 1).to_bytes(
                2,
                "little",
            )
            start = index + len(signature)
    path.write_bytes(payload)


class ToolCliTests(unittest.TestCase):
    def test_argument_errors_use_only_injected_bounded_stderr(self) -> None:
        huge = "x" * 1_000_000
        cases = (
            [huge],
            [
                "br-coordinates",
                "--br-root",
                ".",
                "--terrain",
                "GermanyCW",
                "--x",
                huge,
                "--y",
                "0",
            ],
        )
        for argv in cases:
            with self.subTest(command=argv[0][:32]):
                stdout = io.StringIO()
                stderr = io.StringIO()
                process_stderr = io.StringIO()

                with redirect_stderr(process_stderr):
                    exit_code = main(
                        argv,
                        stdout=stdout,
                        stderr=stderr,
                    )

                rendered = stderr.getvalue()
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(process_stderr.getvalue(), "")
                self.assertLessEqual(
                    len(rendered.encode("utf-8")),
                    MAX_CLI_ERROR_BYTES,
                )
                self.assertEqual(rendered.count("\n"), 1)
                self.assertTrue(rendered.endswith("… [truncated]\n"))

    def test_error_output_is_single_line_and_byte_bounded(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "dcsmizzer.cli.capabilities_report",
            side_effect=ValueError(("x" * 1_000_000) + "\nsecond line"),
        ):
            exit_code = main(
                ["capabilities", "--details"],
                stdout=stdout,
                stderr=stderr,
            )

        rendered = stderr.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertLessEqual(
            len(rendered.encode("utf-8")),
            MAX_CLI_ERROR_BYTES,
        )
        self.assertEqual(rendered.count("\n"), 1)
        self.assertTrue(rendered.endswith("… [truncated]\n"))

    def test_error_output_escapes_surrogates_and_terminal_controls(
        self,
    ) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        unsafe = "\ud800\x00\t\x7f\u0085\u2028\u2029" + "😀" * 1000

        with patch(
            "dcsmizzer.cli.capabilities_report",
            side_effect=ValueError(unsafe),
        ):
            exit_code = main(
                ["capabilities", "--details"],
                stdout=stdout,
                stderr=stderr,
            )

        rendered = stderr.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertLessEqual(
            len(rendered.encode("utf-8")),
            MAX_CLI_ERROR_BYTES,
        )
        self.assertEqual(rendered.count("\n"), 1)
        for escaped in (
            "\\ud800",
            "\\x00",
            "\\t",
            "\\x7f",
            "\\u0085",
            "\\u2028",
            "\\u2029",
        ):
            self.assertIn(escaped, rendered)
        self.assertTrue(rendered.endswith("… [truncated]\n"))

    def test_json_output_rejects_non_finite_values(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "dcsmizzer.cli.capabilities_report",
            return_value={"unsafe": float("inf")},
        ):
            exit_code = main(
                ["capabilities", "--details"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("JSON compliant", stderr.getvalue())

    def test_top_level_help_exposes_workflow_and_exit_contract(self) -> None:
        help_text = _build_parser().format_help()

        self.assertIn(
            "capabilities -> evidence queries -> audit-spec -> build-miz -> verify-miz",
            help_text,
        )
        self.assertIn("0  Query succeeded", help_text)
        self.assertIn("1  Input was read", help_text)
        self.assertIn("2  Usage, path", help_text)
        self.assertIn("dcs-options-template", help_text)
        self.assertIn("dcs-warehouse-template", help_text)
        self.assertIn("dcs-weather", help_text)
        self.assertIn("dcs-payload-match", help_text)
        self.assertIn("br-spawnpoints", help_text)
        self.assertIn("terrain-catalog", help_text)
        self.assertIn("terrain-point", help_text)
        self.assertIn("placement-check", help_text)
        self.assertIn("terrain-corridor", help_text)
        self.assertIn("landmark-search", help_text)
        self.assertIn("airfield-footprint", help_text)
        self.assertIn("br-airfield-footprint", help_text)
        self.assertIn("terrain-probe-script", help_text)
        self.assertIn("terrain-probe-extract", help_text)
        self.assertIn("terrain-coverage", help_text)
        self.assertIn("report-summary", help_text)

    def test_every_subcommand_help_states_its_authority(self) -> None:
        commands = (
            "capabilities",
            "report-summary",
            "inspect",
            "dcs-static",
            "dcs-countries",
            "dcs-payloads",
            "dcs-payload-index",
            "dcs-payload-match",
            "dcs-modules",
            "dcs-cloud-presets",
            "dcs-weather",
            "dcs-airbases",
            "dcs-coordinates",
            "dcs-gci",
            "dcs-options-template",
            "dcs-warehouse-template",
            "pydcs-terrains",
            "pydcs-units",
            "pydcs-airports",
            "pydcs-aircraft",
            "br-terrains",
            "br-coordinates",
            "br-airbases",
            "br-spawnpoints",
            "terrain-catalog",
            "terrain-point",
            "placement-check",
            "terrain-corridor",
            "landmark-search",
            "airfield-footprint",
            "br-airfield-footprint",
            "terrain-probe-script",
            "terrain-probe-extract",
            "terrain-coverage",
            "audit-spec",
            "miz-registry",
            "build-miz",
            "verify-miz",
        )

        for command in commands:
            with self.subTest(command=command):
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = main([command, "--help"])

                help_text = output.getvalue()
                self.assertEqual(exit_code, 0)
                self.assertIn(f"usage: dcsmizzer.py {command}", help_text)
                self.assertIn("Authority:", help_text)

    def test_key_command_help_explains_evidence_inputs(self) -> None:
        expected_help = {
            "dcs-options-template": (
                "--full-sim",
                "Mission Editor default",
            ),
            "dcs-warehouse-template": (
                "--airdrome-id",
                "repeat for multiple airports",
            ),
            "dcs-weather": (
                "--preset",
                "--details",
                "Mission Editor weather",
            ),
            "dcs-payload-match": (
                "--pylon STATION=CLSID",
                "--preset-name",
                "--details",
                "complete payload",
            ),
            "pydcs-terrains": (
                "--latitude",
                "without importing or executing upstream Python",
            ),
            "br-airbases": (
                "--parking",
                "provenance-gated BriefingRoom database",
            ),
            "br-coordinates": (
                "--latitude",
                "commit-bound exported coordinate pairs",
            ),
            "terrain-coverage": (
                "--pydcs-root",
                "--br-root",
                "two provenance-gated upstream snapshots",
            ),
            "terrain-point": (
                "--evidence",
                "--dcs-version",
                "initialized DCS terrain API export",
            ),
            "placement-check": (
                "--length",
                "--max-slope",
                "oriented footprint",
            ),
            "terrain-corridor": (
                "--point X,Y,ALT_MSL",
                "--minimum-clearance",
                "three lateral traces",
            ),
            "landmark-search": (
                "--query",
                "--radius",
                "scenery-object instances",
            ),
            "airfield-footprint": (
                "--airfield",
                "--taxi-buffer",
                "derived operational geometry",
            ),
            "br-airfield-footprint": (
                "--br-root",
                "--airfield",
                "planning envelope",
            ),
            "terrain-probe-script": (
                "--request",
                "--output",
                "does not start DCS",
            ),
            "terrain-probe-extract": (
                "--log",
                "--request",
                "complete matching marker run",
            ),
            "audit-spec": (
                "--br-root",
                "defaults to mission.theatre",
            ),
            "miz-registry": (
                "LABEL=PATH",
                "private paths or mission titles",
            ),
            "build-miz": (
                "--force",
                "no DCS runtime validation",
            ),
            "verify-miz": (
                "--spec",
                "artifact/spec comparison",
            ),
        }

        for command, fragments in expected_help.items():
            with self.subTest(command=command):
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = main([command, "--help"])

                help_text = " ".join(output.getvalue().split())
                self.assertEqual(exit_code, 0)
                for fragment in fragments:
                    self.assertIn(fragment, help_text)

    def test_physical_terrain_commands_dispatch_and_fail_closed(self) -> None:
        evidence = Path("terrain-evidence.json")
        cases = (
            (
                "terrain-point",
                [
                    "terrain-point",
                    "--evidence",
                    str(evidence),
                    "--x",
                    "1",
                    "--y",
                    "2",
                    "--terrain",
                    "SinaiMap",
                    "--dcs-version",
                    "2.9.28.26385",
                    "--tolerance",
                    "0.5",
                ],
                "dcsmizzer.cli.physical_point_report",
                {
                    "schema": "dcsmizzer.terrain-point/v1",
                    "validation": {"evidence_usable": False},
                },
                1,
                (
                    (evidence, 1.0, 2.0),
                    {
                        "terrain": "SinaiMap",
                        "dcs_version": "2.9.28.26385",
                        "tolerance_m": 0.5,
                    },
                ),
            ),
            (
                "placement-check",
                [
                    "placement-check",
                    "--evidence",
                    str(evidence),
                    "--x",
                    "10",
                    "--y",
                    "20",
                    "--heading",
                    "90",
                    "--length",
                    "12",
                    "--width",
                    "5",
                    "--max-slope",
                    "4",
                    "--clearance",
                    "2",
                    "--allow-airfield",
                    "--terrain",
                    "SinaiMap",
                    "--dcs-version",
                    "2.9.28.26385",
                ],
                "dcsmizzer.cli.placement_report",
                {
                    "schema": "dcsmizzer.terrain-placement/v1",
                    "validation": {
                        "placement_valid": None,
                        "sampled_placement_valid": True,
                    },
                },
                0,
                (
                    (evidence,),
                    {
                        "x": 10.0,
                        "y": 20.0,
                        "heading_deg": 90.0,
                        "length_m": 12.0,
                        "width_m": 5.0,
                        "required_surface": "land",
                        "max_slope_deg": 4.0,
                        "clearance_m": 2.0,
                        "avoid_airfields": False,
                        "taxi_buffer_m": 15.0,
                        "terrain": "SinaiMap",
                        "dcs_version": "2.9.28.26385",
                    },
                ),
            ),
            (
                "terrain-corridor",
                [
                    "terrain-corridor",
                    "--evidence",
                    str(evidence),
                    "--point",
                    "0,0,300",
                    "--point",
                    "100,50,400",
                    "--half-width",
                    "25",
                    "--step",
                    "10",
                    "--minimum-clearance",
                    "150",
                    "--limit",
                    "7",
                    "--terrain",
                    "SinaiMap",
                    "--dcs-version",
                    "2.9.28.26385",
                ],
                "dcsmizzer.cli.terrain_corridor_report",
                {
                    "schema": "dcsmizzer.terrain-corridor/v1",
                    "validation": {
                        "corridor_clear": False,
                        "sampled_corridor_clear": False,
                    },
                },
                1,
                (
                    (evidence,),
                    {
                        "route": [
                            {"x": 0.0, "y": 0.0, "altitude_msl": 300.0},
                            {"x": 100.0, "y": 50.0, "altitude_msl": 400.0},
                        ],
                        "half_width_m": 25.0,
                        "step_m": 10.0,
                        "minimum_clearance_m": 150.0,
                        "limit": 7,
                        "terrain": "SinaiMap",
                        "dcs_version": "2.9.28.26385",
                    },
                ),
            ),
            (
                "landmark-search",
                [
                    "landmark-search",
                    "--evidence",
                    str(evidence),
                    "--query",
                    "pyramid",
                    "--near-x",
                    "10",
                    "--near-y",
                    "20",
                    "--radius",
                    "500",
                    "--limit",
                    "2",
                    "--terrain",
                    "SinaiMap",
                    "--dcs-version",
                    "2.9.28.26385",
                ],
                "dcsmizzer.cli.landmark_report",
                {
                    "schema": "dcsmizzer.terrain-landmarks/v1",
                    "validation": {"exact_query_usable": True},
                },
                0,
                (
                    (evidence,),
                    {
                        "query": "pyramid",
                        "near_x": 10.0,
                        "near_y": 20.0,
                        "radius_m": 500.0,
                        "limit": 2,
                        "terrain": "SinaiMap",
                        "dcs_version": "2.9.28.26385",
                    },
                ),
            ),
            (
                "airfield-footprint",
                [
                    "airfield-footprint",
                    "--evidence",
                    str(evidence),
                    "--airfield",
                    "Cairo West",
                    "--taxi-buffer",
                    "18",
                    "--terrain",
                    "SinaiMap",
                    "--dcs-version",
                    "2.9.28.26385",
                ],
                "dcsmizzer.cli.airfield_footprint_report",
                {
                    "schema": "dcsmizzer.airfield-footprint/v1",
                    "validation": {"exact_airfield_usable": False},
                },
                1,
                (
                    (evidence,),
                    {
                        "airfield": "Cairo West",
                        "taxi_buffer_m": 18.0,
                        "terrain": "SinaiMap",
                        "dcs_version": "2.9.28.26385",
                    },
                ),
            ),
        )

        for command, argv, target, report, expected_exit, call in cases:
            with self.subTest(command=command):
                stdout = io.StringIO()
                with patch(target, return_value=report) as query:
                    exit_code = main(argv, stdout=stdout)

                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(json.loads(stdout.getvalue()), report)
                query.assert_called_once_with(*call[0], **call[1])

    def test_terrain_catalog_distinguishes_products_and_theatres(self) -> None:
        report = {
            "schema": "dcsmizzer.terrain-catalog/v1",
            "coverage": {
                "matching_theatres": 0,
                "exact_query_usable": False,
            },
            "theatres": [],
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.terrain_catalog_report",
            return_value=report,
        ) as catalog:
            exit_code = main(
                [
                    "terrain-catalog",
                    "--product",
                    "Missing product",
                    "--limit",
                    "3",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        catalog.assert_called_once_with(
            terrain=None,
            product="Missing product",
            search=None,
            limit=3,
        )

    def test_physical_cli_requires_task_terrain_and_version_binding(
        self,
    ) -> None:
        stderr = io.StringIO()

        exit_code = main(
            [
                "terrain-point",
                "--evidence",
                "evidence.json",
                "--x",
                "0",
                "--y",
                "0",
            ],
            stderr=stderr,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("--terrain", stderr.getvalue())
        self.assertIn("--dcs-version", stderr.getvalue())

    def test_terrain_probe_commands_never_start_dcs(self) -> None:
        script_report = {
            "schema": "dcsmizzer.terrain-probe-script/v1",
            "dcs_started": False,
            "validation": {"script_generated": True},
        }
        extract_report = {
            "schema": "dcsmizzer.terrain-probe-extraction/v1",
            "dcs_started": False,
            "validation": {"evidence_valid": True},
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.generate_terrain_probe_script",
            return_value=script_report,
        ) as generate:
            exit_code = main(
                [
                    "terrain-probe-script",
                    "--request",
                    "request.json",
                    "--dcs-root",
                    "DCSWorld",
                    "--output",
                    "probe.lua",
                    "--force",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), script_report)
        generate.assert_called_once_with(
            Path("request.json"),
            Path("DCSWorld"),
            Path("probe.lua"),
            force=True,
        )

        stdout = io.StringIO()
        with patch(
            "dcsmizzer.cli.extract_terrain_probe",
            return_value=extract_report,
        ) as extract:
            exit_code = main(
                [
                    "terrain-probe-extract",
                    "--log",
                    "dcs.log",
                    "--request",
                    "request.json",
                    "--output",
                    "evidence.json",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), extract_report)
        extract.assert_called_once_with(
            Path("dcs.log"),
            Path("request.json"),
            Path("evidence.json"),
            force=False,
        )

    def test_weather_registry_cli_fails_on_incomplete_static_evidence(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.dcs-weather-presets/v1",
            "coverage": {
                "matching_presets": 1,
                "parse_failures": 1,
            },
            "filter": {"preset": "Summer. Thunderstorm"},
            "presets": [
                {
                    "id": "Summer. Thunderstorm",
                    "validation": {"consistent": True},
                }
            ],
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.weather_registry_report",
            return_value=report,
        ) as registry:
            exit_code = main(
                [
                    "dcs-weather",
                    "--dcs-root",
                    "DCSWorld",
                    "--preset",
                    "Summer. Thunderstorm",
                    "--details",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["presets"], report["presets"])
        registry.assert_called_once_with(
            Path("DCSWorld"),
            preset="Summer. Thunderstorm",
        )

    def test_weather_registry_cli_rejects_field_incomplete_exact_preset(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.dcs-weather-presets/v1",
            "coverage": {
                "matching_presets": 1,
                "parse_failures": 0,
            },
            "filter": {"preset": "Incomplete"},
            "presets": [
                {
                    "id": "Incomplete",
                    "validation": {
                        "fields_complete": False,
                        "consistent": True,
                        "missing_fields": ["vdata.qnh"],
                    },
                }
            ],
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.weather_registry_report",
            return_value=report,
        ):
            exit_code = main(
                [
                    "dcs-weather",
                    "--dcs-root",
                    "DCSWorld",
                    "--preset",
                    "Incomplete",
                    "--details",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 1)
        self.assertFalse(
            json.loads(stdout.getvalue())["presets"][0]["validation"][
                "fields_complete"
            ]
        )

    def test_payload_match_cli_parses_complete_query_and_is_strict(self) -> None:
        report = {
            "schema": "dcsmizzer.dcs-payload-match/v1",
            "verified_exact_observed_preset": True,
            "classification": "exact_observed_preset",
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.payload_match_report",
            return_value=report,
        ) as matcher:
            exit_code = main(
                [
                    "dcs-payload-match",
                    "--dcs-root",
                    "DCSWorld",
                    "--unit-type",
                    "Fixture Plane",
                    "--pylon",
                    "2={B}",
                    "--pylon",
                    "1={A}",
                    "--task",
                    "11",
                    "--preset-name",
                    "Intercept",
                    "--category",
                    "Air-to-Air",
                    "--details",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        matcher.assert_called_once_with(
            Path("DCSWorld"),
            "Fixture Plane",
            [
                {"num": 2, "CLSID": "{B}"},
                {"num": 1, "CLSID": "{A}"},
            ],
            tasks=[11],
            preset_name="Intercept",
            display_name=None,
            category="Air-to-Air",
        )

    def test_payload_match_cli_accepts_an_empty_complete_payload(self) -> None:
        report = {
            "schema": "dcsmizzer.dcs-payload-match/v1",
            "verified_exact_observed_preset": False,
            "classification": "custom_composition_only",
        }

        with patch(
            "dcsmizzer.cli.payload_match_report",
            return_value=report,
        ) as matcher:
            exit_code = main(
                [
                    "dcs-payload-match",
                    "--dcs-root",
                    "DCSWorld",
                    "--unit-type",
                    "Fixture Plane",
                    "--empty",
                    "--details",
                ],
                stdout=io.StringIO(),
            )

        self.assertEqual(exit_code, 1)
        matcher.assert_called_once_with(
            Path("DCSWorld"),
            "Fixture Plane",
            [],
            tasks=None,
            preset_name=None,
            display_name=None,
            category=None,
        )

    def test_payload_match_cli_rejects_incomplete_candidate_scope(self) -> None:
        report = {
            "schema": "dcsmizzer.dcs-payload-match/v1",
            "verified_exact_observed_preset": False,
            "classification": "source_evidence_incomplete",
            "exact_match_count": 1,
            "source_binding": {
                "candidate_enumeration_complete": False,
            },
        }

        with patch(
            "dcsmizzer.cli.payload_match_report",
            return_value=report,
        ):
            exit_code = main(
                [
                    "dcs-payload-match",
                    "--dcs-root",
                    "DCSWorld",
                    "--unit-type",
                    "Fixture Plane",
                    "--empty",
                    "--details",
                ],
                stdout=io.StringIO(),
            )

        self.assertEqual(exit_code, 1)

    def test_br_airfield_footprint_cli_preserves_planning_authority(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.br-airfield-footprint/v1",
            "validation": {
                "planning_footprint_usable": True,
                "physical_validation": False,
            },
        }
        stdout = io.StringIO()

        with patch(
            "dcsmizzer.cli.br_airfield_footprint_report",
            return_value=report,
        ) as footprint:
            exit_code = main(
                [
                    "br-airfield-footprint",
                    "--br-root",
                    "briefing-room",
                    "--terrain",
                    "SinaiMap",
                    "--airfield",
                    "Cairo West",
                    "--limit",
                    "4",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        footprint.assert_called_once_with(
            Path("briefing-room"),
            "SinaiMap",
            "Cairo West",
            limit=4,
        )

    def test_corridor_point_argument_is_bounded_and_explicit(self) -> None:
        stderr = io.StringIO()

        exit_code = main(
            [
                "terrain-corridor",
                "--evidence",
                "evidence.json",
                "--terrain",
                "SinaiMap",
                "--dcs-version",
                "2.9.28.26385",
                "--point",
                "not-a-point",
                "--point",
                "1,2,3",
                "--half-width",
                "0",
                "--step",
                "10",
                "--minimum-clearance",
                "100",
            ],
            stderr=stderr,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("X,Y,ALT_MSL", stderr.getvalue())

    def test_terrain_coverage_exact_miss_returns_one(self) -> None:
        stdout = io.StringIO()
        report = {
            "schema": "dcsmizzer.terrain-coverage/v1",
            "coverage": {
                "matching_theatres": 0,
                "exact_query_usable": False,
            },
            "terrains": [],
        }

        with patch(
            "dcsmizzer.cli.combined_terrain_report",
            return_value=report,
        ) as combined:
            exit_code = main(
                [
                    "terrain-coverage",
                    "--pydcs-root",
                    "pydcs",
                    "--br-root",
                    "briefing-room",
                    "--terrain",
                    "MissingTheatre",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 1)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["schema"], "dcsmizzer.cli-summary/v1")
        self.assertEqual(output["source_schema"], report["schema"])
        self.assertEqual(output["terrains"], [])
        self.assertEqual(output["catalog"]["matching_items"], 0)
        combined.assert_called_once_with(
            Path("pydcs"),
            Path("briefing-room"),
            terrain="MissingTheatre",
        )

    def test_br_coordinates_returns_one_when_fit_is_not_validated(
        self,
    ) -> None:
        stdout = io.StringIO()
        report = {
            "schema": "dcsmizzer.br-coordinate-conversion/v1",
            "validation": {
                "validated": False,
                "failure_reasons": ["fixture_failure"],
            },
        }

        with patch(
            "dcsmizzer.cli.br_coordinate_report",
            return_value=report,
        ) as coordinate:
            exit_code = main(
                [
                    "br-coordinates",
                    "--br-root",
                    "briefing-room",
                    "--terrain",
                    "Kola",
                    "--latitude",
                    "69.0",
                    "--longitude",
                    "30.0",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        coordinate.assert_called_once_with(
            Path("briefing-room"),
            "Kola",
            latitude=69.0,
            longitude=30.0,
            map_x=None,
            map_y=None,
        )

    def test_exact_airport_queries_bound_parking_unless_details_requested(
        self,
    ) -> None:
        pydcs_report = {
            "schema": "dcsmizzer.pydcs-airports/v1",
            "authority": "fixture",
            "dcs_started": False,
            "filters": {
                "airport": "Fixture",
                "airdrome_id": None,
                "parking": None,
            },
            "coverage": {
                "exact_airport_query_usable": True,
                "source_parse_complete": True,
            },
            "airports": [],
        }
        with patch(
            "dcsmizzer.cli.pydcs_airport_report",
            return_value=pydcs_report,
        ) as airport_report:
            default_exit = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    "pydcs",
                    "--terrain",
                    "FixtureMap",
                    "--airport",
                    "Fixture",
                ],
                stdout=io.StringIO(),
            )
            default_limit = airport_report.call_args.kwargs["limit"]
            details_exit = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    "pydcs",
                    "--terrain",
                    "FixtureMap",
                    "--airport",
                    "Fixture",
                    "--details",
                ],
                stdout=io.StringIO(),
            )
            details_limit = airport_report.call_args.kwargs["limit"]

        br_report = {
            "schema": "dcsmizzer.br-airbases/v1",
            "authority": "fixture",
            "dcs_started": False,
            "filters": {
                "airport": "Fixture",
                "airdrome_id": None,
                "parking": None,
            },
            "coverage": {
                "exact_airbase_query_usable": True,
                "matching_parking_slots": 1,
                "airbase_parse_failures": 0,
            },
            "airbases": [],
        }
        with patch(
            "dcsmizzer.cli.br_airbase_report",
            return_value=br_report,
        ) as airbase_report:
            br_exit = main(
                [
                    "br-airbases",
                    "--br-root",
                    "briefing-room",
                    "--terrain",
                    "FixtureMap",
                    "--airport",
                    "Fixture",
                ],
                stdout=io.StringIO(),
            )
            br_limit = airbase_report.call_args.kwargs["limit"]

        invalid_stderr = io.StringIO()
        with patch(
            "dcsmizzer.cli.pydcs_airport_report",
            side_effect=ValueError("limit requires exact airport"),
        ) as invalid_report:
            invalid_exit = main(
                [
                    "pydcs-airports",
                    "--pydcs-root",
                    "pydcs",
                    "--terrain",
                    "FixtureMap",
                    "--limit",
                    "1",
                ],
                stdout=io.StringIO(),
                stderr=invalid_stderr,
            )
            invalid_limit = invalid_report.call_args.kwargs["limit"]

        self.assertEqual(default_exit, 0)
        self.assertEqual(default_limit, 8)
        self.assertEqual(details_exit, 0)
        self.assertIsNone(details_limit)
        self.assertEqual(br_exit, 0)
        self.assertEqual(br_limit, 8)
        self.assertEqual(invalid_exit, 2)
        self.assertEqual(invalid_limit, 1)
        self.assertIn("limit requires exact airport", invalid_stderr.getvalue())

    def test_tools_tree_contains_only_python_sources_and_runtime_resource(
        self,
    ) -> None:
        allowed_resources = {
            Path("dcsmizzer/resources/runtime_hook.lua"),
        }
        non_python_files = sorted(
            str(path.relative_to(TOOLS_ROOT))
            for path in TOOLS_ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".py"
            and path.relative_to(TOOLS_ROOT) not in allowed_resources
        )

        self.assertEqual(non_python_files, [])
        self.assertTrue(
            all((TOOLS_ROOT / relative).is_file() for relative in allowed_resources)
        )

    def test_script_entrypoint_emits_utf8_json_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            database = dcs_root / "Scripts" / "Database"
            database.mkdir(parents=True)
            (database / "db_countries.lua").write_text(
                "country = { next_index = 0 }\n"
                "country:add('测试', _('Test'), 'Test', 'TST')\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "dcsmizzer.py"),
                    "dcs-countries",
                    "--dcs-root",
                    str(dcs_root),
                ],
                check=False,
                capture_output=True,
            )

        decoded = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(decoded["identifiers"], ["测试"])

    def test_capabilities_separate_low_level_build_from_runtime(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(["capabilities"], stdout=stdout, stderr=stderr)

        summary = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(summary["schema"], "dcsmizzer.cli-summary/v1")
        self.assertEqual(
            summary["capabilities"]["mission_generation"]["status"],
            "implemented_low_level",
        )
        self.assertLessEqual(
            len(stdout.getvalue().encode("utf-8")),
            12 * 1024,
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = main(
            ["capabilities", "--details"],
            stdout=stdout,
            stderr=stderr,
        )
        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            report["mission_generation"]["status"],
            "implemented_low_level",
        )
        self.assertEqual(
            report["dcs_launch"]["status"],
            "implemented_explicit_opt_in_dcs_only",
        )
        self.assertEqual(report["inspect_miz"]["status"], "implemented")
        self.assertEqual(
            report["complete_unit_registry"]["status"],
            "requires_version_matched_runtime_export",
        )
        self.assertEqual(
            report["terrain_coordinate_conversion"]["status"],
            "implemented_tiered",
        )
        self.assertEqual(
            report["terrain_coordinate_conversion"]["briefingroom_fit_coverage"][
                "validated_theatres"
            ],
            13,
        )
        self.assertEqual(
            report["model_context_interfaces"]["status"],
            "implemented",
        )
        self.assertEqual(
            report["official_terrain_catalog"]["status"],
            "implemented_dated_snapshot",
        )
        self.assertEqual(
            report["terrain_physical_evidence"]["status"],
            "implemented_probe_and_bounded_consumers",
        )
        self.assertEqual(
            report["terrain_physical_evidence"][
                "current_runtime_exports_committed"
            ],
            0,
        )
        self.assertEqual(
            report["airbase_runway_parking"]["status"],
            "implemented_commit_bound_planning_all_14_theatres",
        )
        self.assertIn(
            "survey_install_snapshot",
            report["weather_registry"],
        )
        self.assertNotIn(
            "observed_current_install",
            report["weather_registry"],
        )

    def test_filesystem_errors_do_not_expose_private_paths(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        private_path = r"C:\private\mission\source.miz"

        with patch(
            "dcsmizzer.cli.capabilities_report",
            side_effect=PermissionError(13, "denied", private_path),
        ):
            exit_code = main(
                ["capabilities"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("PermissionError, errno=13", stderr.getvalue())
        self.assertNotIn(private_path, stderr.getvalue())

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
        self.assertFalse(report["validation"]["limited_structure_checked"])
        self.assertIsNone(report["validation"]["limited_structure_valid"])
        self.assertIsNone(report["validation"]["runtime_valid"])
        self.assertEqual(report["input"], "fixture.miz")
        self.assertNotIn(temp_dir, json.dumps(report))
        self.assertEqual(report["mission"]["theatre"], "FixtureMap")
        self.assertEqual(report["mission"]["stats"]["human_slots"], {"Client": 1})
        self.assertEqual(report["mission"]["stats"]["payload_unique_clsids"], 1)

    def test_inspect_rejects_non_finite_lua_without_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "non-finite.miz"
            write_miz(path, mission=b"mission = { version = 1e999 }")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["inspect", str(path)],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(
            stdout.getvalue(),
            parse_constant=lambda value: self.fail(
                f"nonstandard JSON constant emitted: {value}"
            ),
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertFalse(report["validation"]["parse_valid"])
        mission_member = next(
            item
            for item in report["mission"]["core_members"]
            if item["name"] == "mission"
        )
        self.assertFalse(mission_member["parsed"])
        self.assertEqual(mission_member["error_code"], "LuaSyntaxError")

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

    def test_inspect_rejects_duplicate_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate.miz"
            write_miz(path)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "a") as archive:
                    archive.writestr("mission", MISSION)
            stdout = io.StringIO()

            exit_code = main(["inspect", str(path)], stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(report["validation"]["archive_valid"])
        self.assertFalse(report["archive"]["safe"])
        self.assertEqual(report["archive"]["duplicate_member_extras"], 1)

    def test_inspect_encrypted_miz_returns_json_exit_one_without_traceback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "encrypted.miz"
            write_miz(path)
            mark_zip_entries_encrypted(path)
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["inspect", str(path)],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertFalse(report["validation"]["archive_valid"])
        self.assertFalse(report["validation"]["parse_valid"])
        self.assertEqual(report["archive"]["crc_status"], "not_checked")
        self.assertGreater(report["archive"]["encrypted_entries"], 0)
        self.assertTrue(
            all(
                item["error_code"] == "encrypted_member"
                for item in report["mission"]["core_members"]
            )
        )

    def test_inspect_archive_error_never_reads_member_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsafe.miz"
            write_miz(path, unsafe=True)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "dcsmizzer.cli.analyse_miz",
                side_effect=AssertionError("member reads must be blocked"),
            ) as analyse:
                exit_code = main(
                    ["inspect", str(path)],
                    stdout=stdout,
                    stderr=stderr,
                )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertFalse(report["validation"]["archive_valid"])
        self.assertTrue(report["validation"]["archive_content_read_blocked"])
        analyse.assert_not_called()

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
        self.assertEqual(report["input"], "fixture.cmp")
        self.assertNotIn(temp_dir, json.dumps(report))
        self.assertEqual(report["campaign"]["resolved_references"], 1)

    def test_current_static_country_and_payload_lookup_are_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            database = dcs_root / "Scripts" / "Database"
            database.mkdir(parents=True)
            (database / "db_countries.lua").write_text(
                """
                country = { next_index = 0 }
                country:add('USA', _('USA'), 'USA', 'USA')
                country:next()
                country:add('FRANCE', _('France'), 'France', 'FRA')
                """,
                encoding="utf-8",
            )
            payload_root = (
                dcs_root / "MissionEditor" / "data" / "scripts" / "UnitPayloads"
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
                    "--preset",
                    "CAP",
                ],
                stdout=payloads_out,
            )

        countries = json.loads(countries_out.getvalue())
        payloads = json.loads(payloads_out.getvalue())
        self.assertEqual(countries_exit, 0)
        self.assertEqual(countries["identifiers"], ["USA", "FRANCE"])
        self.assertEqual(
            countries["entries"],
            [
                {"id": 0, "identifier": "USA"},
                {"id": 2, "identifier": "FRANCE"},
            ],
        )
        self.assertEqual(countries["reserved_ids"], [1])
        self.assertEqual(countries["authority"], "current_install_static_source")
        self.assertEqual(payloads_exit, 0)
        self.assertFalse(payloads["compatibility_complete"])
        self.assertEqual(payloads["presets"][0]["pylons"][0]["CLSID"], "{A}")
        self.assertEqual(payloads["presets"][0]["tasks"], [11])

    def test_registry_summary_only_keeps_theatre_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "fixture.miz"
            write_miz(path)
            stdout = io.StringIO()

            exit_code = main(
                [
                    "miz-registry",
                    "--root",
                    f"fixture={root}",
                    "--summary-only",
                ],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            report["schema"],
            "dcsmizzer.observed-miz-summary/v1",
        )
        self.assertEqual(
            report["theatres"],
            [
                {
                    "theatre_ref": "observed-theatre-1",
                    "identity_source": "anonymous_observation",
                    "missions": 1,
                }
            ],
        )
        self.assertNotIn("unit_types", report)
        self.assertNotIn("environment", report)

    def test_registry_cli_rejects_ancestor_link_without_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            outside = base / "PRIVATE_OUTSIDE_ROOT"
            real_root = outside / "missions"
            real_root.mkdir(parents=True)
            write_miz(real_root / "PRIVATE_MISSION_NAME.miz")
            alias = base / "alias"
            try:
                alias.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "miz-registry",
                    "--root",
                    f"fixture={alias / 'missions'}",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("must not contain symbolic links", stderr.getvalue())
        self.assertNotIn("PRIVATE_OUTSIDE_ROOT", stderr.getvalue())
        self.assertNotIn("PRIVATE_MISSION_NAME", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
