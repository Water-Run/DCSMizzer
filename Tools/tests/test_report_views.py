from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.report_views import (  # noqa: E402
    REPORT_SUMMARY_SCHEMA,
    SUMMARY_BUDGET_BYTES,
    SUMMARY_SCHEMA,
    output_view,
    report_summary,
)
from dcsmizzer.report_provenance import intrinsic_report_sha256  # noqa: E402


def windows_stdout_size(value: object) -> int:
    text = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return len(text.replace("\n", "\r\n").encode("utf-8"))


def base_report(schema: str) -> dict[str, object]:
    return {
        "schema": schema,
        "authority": "fixture_authority",
        "dcs_started": False,
        "coverage": {},
    }


class ReportViewTests(unittest.TestCase):
    def assert_bounded(self, value: object) -> None:
        self.assertLessEqual(
            windows_stdout_size(value),
            SUMMARY_BUDGET_BYTES,
        )

    def test_large_catalogs_are_bounded_by_default(self) -> None:
        fixtures = {
            "dcs-payload-index": (
                "dcsmizzer.dcs-default-payload-index/v1",
                "unit_types",
                [
                    {
                        "unit_type": f"Fixture Aircraft {index:03}",
                        "presets": 30,
                        "pylon_assignments": 300,
                        "unique_clsids": 80,
                        "task_ids": list(range(20)),
                        "sources": [
                            {
                                "source": "x" * 1000,
                                "source_sha256": "a" * 64,
                            }
                        ],
                    }
                    for index in range(300)
                ],
            ),
            "dcs-airbases": (
                "dcsmizzer.dcs-airbase-beacons/v1",
                "airbases",
                [
                    {
                        "airdrome_id": index,
                        "names": [f"Airbase {index}", "x" * 1000],
                        "callsigns": ["Fixture"],
                        "beacon_count": 10,
                        "beacon_types": ["ILS", "TACAN"],
                        "radio_count": 2,
                    }
                    for index in range(300)
                ],
            ),
            "pydcs-airports": (
                "dcsmizzer.pydcs-airports/v1",
                "airports",
                [
                    {
                        "airdrome_id": index,
                        "name": f"Airport {index}",
                        "class": "Fixture",
                        "center": {"x": index * 1000, "y": index * 2000},
                        "civilian": False,
                        "runway_count": 3,
                        "parking_slot_count": 300,
                        "airplane_parking_slots": 250,
                        "helicopter_parking_slots": 100,
                        "parking": [{"private": "x" * 1000}],
                    }
                    for index in range(300)
                ],
            ),
            "br-airbases": (
                "dcsmizzer.br-airbases/v1",
                "airbases",
                [
                    {
                        "airdrome_id": index,
                        "name": f"Airbase {index}",
                        "display_name": f"Display {index}",
                        "type_name": "Fixture",
                        "icao": "TEST",
                        "center": {
                            "x": index * 1000,
                            "y": index * 2000,
                        },
                        "runway_designators": ["01", "19"],
                        "parking_slot_count": 300,
                        "airplane_parking_slots": 250,
                        "helicopter_parking_slots": 100,
                        "parking": [{"private": "x" * 1000}],
                    }
                    for index in range(300)
                ],
            ),
            "dcs-modules": (
                "dcsmizzer.dcs-module-index/v1",
                "modules",
                [
                    {
                        "module_directory": f"Module-{index}",
                        "module_key": f"module_key_{index}",
                        "scope": "aircraft",
                        "plugin_ids": [f"Plugin {index}", "x" * 1000],
                        "flyable_types": [f"Aircraft {index}"],
                        "default_payload_unit_types": [f"Aircraft {index}"],
                        "unresolved_literal_calls": 0,
                        "entry_source": "x" * 1000,
                    }
                    for index in range(300)
                ],
            ),
            "dcs-cloud-presets": (
                "dcsmizzer.dcs-cloud-presets/v1",
                "presets",
                [
                    {
                        "id": f"Preset{index}",
                        "readable_name_short": f"Cloud preset {index}",
                        "base_altitude_range": {
                            "minimum": 100,
                            "maximum": 3000,
                        },
                        "precipitation_power": index % 10,
                        "visible_in_gui": True,
                        "thumbnail": "x" * 1000,
                    }
                    for index in range(300)
                ],
            ),
        }
        for command, (schema, collection, records) in fixtures.items():
            with self.subTest(command=command):
                report = base_report(schema)
                report[collection] = records
                if command == "dcs-airbases":
                    report["filter"] = {"airdrome_id": None}
                elif command == "dcs-cloud-presets":
                    report["filter"] = {"preset": None}
                else:
                    report["filters"] = {
                        "airport": None,
                        "airdrome_id": None,
                    }

                view = output_view(command, report)

                self.assertEqual(view.report["schema"], SUMMARY_SCHEMA)
                self.assertTrue(view.report["view"]["output_truncated"])
                self.assert_bounded(view.report)

    def test_nested_collection_truncation_is_explicit(self) -> None:
        report = {
            **base_report("dcsmizzer.dcs-module-index/v1"),
            "filters": {"module": "Fixture"},
            "coverage": {"matching_modules": 1},
            "modules": [
                {
                    "module_directory": "Fixture",
                    "module_key": "fixture",
                    "scope": "aircraft",
                    "plugin_ids": [f"Plugin {index:02}" for index in range(30)],
                    "flyable_types": ["Fixture Plane"],
                    "default_payload_unit_types": ["Fixture Plane"],
                    "unresolved_literal_calls": 0,
                }
            ],
        }

        rendered = output_view("dcs-modules", report).report

        self.assertEqual(len(rendered["modules"]), 1)
        self.assertEqual(len(rendered["modules"][0]["plugin_ids"]), 12)
        self.assertFalse(rendered["catalog"]["output_truncated"])
        self.assertTrue(rendered["view"]["output_truncated"])
        self.assertTrue(rendered["view"]["nested_output_truncated"])
        self.assertEqual(rendered["view"]["nested_truncation_count"], 1)
        self.assertEqual(
            rendered["view"]["nested_truncations"],
            [
                {
                    "path": "$.modules[0].plugin_ids",
                    "total_items": 30,
                    "returned_items": 12,
                    "omitted_items": 18,
                }
            ],
        )
        self.assert_bounded(rendered)

    def test_exact_catalog_queries_are_bounded_until_details_requested(
        self,
    ) -> None:
        padding = ["x" * 1000 for _ in range(1000)]
        fixtures = (
            (
                "br-terrains",
                {
                    **base_report("dcsmizzer.br-terrains/v1"),
                    "filters": {"terrain": "FixtureMap"},
                    "terrains": [
                        {
                            "dcs_id": "FixtureMap",
                            "declaration_id": "FixtureMap",
                            "display_name": "Fixture Map",
                            "airbases": 1,
                            "full_record_padding": padding,
                        }
                    ],
                },
                {},
                "terrains",
            ),
            (
                "pydcs-airports",
                {
                    **base_report("dcsmizzer.pydcs-airports/v1"),
                    "filters": {
                        "airport": "Fixture Airbase",
                        "airdrome_id": None,
                    },
                    "airports": [
                        {
                            "airdrome_id": 7,
                            "name": "Fixture Airbase",
                            "class": "Fixture",
                            "parking": padding,
                        }
                    ],
                },
                {},
                "airports",
            ),
            (
                "br-airbases",
                {
                    **base_report("dcsmizzer.br-airbases/v1"),
                    "filters": {
                        "airport": "Fixture Airbase",
                        "airdrome_id": None,
                    },
                    "airbases": [
                        {
                            "airdrome_id": 7,
                            "display_name": "Fixture Airbase",
                            "name": "Fixture",
                            "parking": padding,
                        }
                    ],
                },
                {},
                "airbases",
            ),
            (
                "dcs-payloads",
                {
                    **base_report("dcsmizzer.dcs-default-payloads/v1"),
                    "unit_type": "Fixture Plane",
                    "presets": [
                        {
                            "name": "Fixture CAP",
                            "display_name": "Fixture CAP",
                            "source": "fixture.lua",
                            "tasks": [11],
                            "pylons": [
                                {
                                    "num": index,
                                    "CLSID": f"{{STORE-{index}}}",
                                    "padding": "x" * 1000,
                                }
                                for index in range(1000)
                            ],
                        }
                    ],
                },
                {"preset": "Fixture CAP"},
                "presets",
            ),
        )

        for command, report, options, collection in fixtures:
            with self.subTest(command=command):
                original = json.dumps(report, ensure_ascii=False, sort_keys=True)
                bounded = output_view(command, report, **options)
                detailed = output_view(
                    command,
                    report,
                    details=True,
                    **options,
                )

                self.assertEqual(bounded.report["schema"], SUMMARY_SCHEMA)
                self.assertEqual(len(bounded.report[collection]), 1)
                self.assertTrue(bounded.report["view"]["output_truncated"])
                self.assertTrue(bounded.report["view"]["nested_output_truncated"])
                self.assertIs(detailed.report, report)
                self.assertEqual(
                    json.dumps(report, ensure_ascii=False, sort_keys=True),
                    original,
                )
                self.assert_bounded(bounded.report)

    def test_clipped_text_is_reported_as_output_truncation(self) -> None:
        source_name = "Fixture " + "x" * 1000
        report = {
            **base_report("dcsmizzer.br-terrains/v1"),
            "filters": {"terrain": None},
            "terrains": [
                {
                    "dcs_id": "FixtureMap",
                    "declaration_id": "FixtureMap",
                    "display_name": source_name,
                }
            ],
        }

        bounded = output_view("br-terrains", report).report

        self.assertEqual(report["terrains"][0]["display_name"], source_name)
        self.assertTrue(bounded["view"]["output_truncated"])
        self.assertTrue(bounded["view"]["nested_output_truncated"])
        self.assertEqual(bounded["view"]["nested_truncation_count"], 1)
        self.assertEqual(
            bounded["view"]["nested_truncations"],
            [
                {
                    "path": "$.terrains[0].display_name",
                    "total_characters": len(source_name),
                    "returned_characters": 256,
                    "omitted_characters": len(source_name) - 256,
                }
            ],
        )
        self.assert_bounded(bounded)

    def test_exact_terrain_queries_are_bounded_until_details_requested(
        self,
    ) -> None:
        record = {
            "record_key": "briefingroom:1",
            "dcs_theatre": "Kola",
            "display_name": "Kola",
            "pydcs": {
                "terrain_package": "kola",
                "terrain_class": "Kola",
                "declared_miz_theatre_name": "Kola",
                "projection": {"central_meridian": 27},
                "declared_bounds_consistency": {
                    "status": "inconsistent",
                    "obviously_outside": 500,
                    "obviously_outside_airports": ["x" * 1000] * 500,
                },
            },
            "briefingroom": {
                "declaration_id": "Kola",
                "airbases": 37,
            },
            "identity_resolution": {"status": "matched"},
            "full": ["x" * 1000] * 500,
        }
        exact = {
            **base_report("dcsmizzer.terrain-coverage/v2"),
            "filters": {"terrain": "Kola"},
            "coverage": {"exact_query_usable": True},
            "source_lock": {
                "required_sources": ["pydcs", "briefingroom"],
                "all_sources_commit_bound": False,
                "failure_reasons": [
                    {
                        "source": "briefingroom",
                        "reasons": ["commit_mismatch"],
                    }
                ],
            },
            "terrains": [record],
            "identity_conflicts": [
                {
                    "code": "matching-conflict",
                    "briefingroom_record": {"record_key": "briefingroom:1"},
                },
                {
                    "code": "unrelated-conflict",
                    "briefingroom_record": {"record_key": "briefingroom:2"},
                },
            ],
        }
        catalog = {
            **base_report("dcsmizzer.terrain-coverage/v2"),
            "filters": {"terrain": None},
            "coverage": {"exact_query_usable": None},
            "terrains": [record],
        }

        bounded = output_view("terrain-coverage", exact).report
        self.assertEqual(bounded["schema"], SUMMARY_SCHEMA)
        self.assertNotIn("full", bounded["terrains"][0])
        self.assertEqual(
            bounded["terrains"][0]["pydcs"]["projection"]["central_meridian"],
            27,
        )
        self.assertEqual(
            bounded["terrains"][0]["pydcs"]["declared_bounds_consistency"][
                "obviously_outside_airports_count"
            ],
            500,
        )
        self.assertEqual(
            [item["code"] for item in bounded["identity_conflicts"]],
            ["matching-conflict"],
        )
        self.assertFalse(
            bounded["source_lock"]["all_sources_commit_bound"]
        )
        self.assertEqual(
            bounded["source_lock"]["failure_reasons"][0]["reasons"],
            ["commit_mismatch"],
        )
        self.assert_bounded(bounded)
        self.assertIs(
            output_view(
                "terrain-coverage",
                exact,
                details=True,
            ).report,
            exact,
        )
        self.assertIs(
            output_view(
                "terrain-coverage",
                catalog,
                details=True,
            ).report,
            catalog,
        )

        pydcs_record = {
            "terrain_package": "kola",
            "terrain_class": "Kola",
            "miz_theatre_name": "Kola",
            "projection": {"central_meridian": 27},
            "declared_bounds_consistency": {
                "status": "inconsistent",
                "obviously_outside": 500,
                "obviously_outside_airports": ["x" * 1000] * 500,
            },
            "airport_summary": {
                "airports_parsed": 37,
                "parking_slots": 1000,
            },
            "full": ["x" * 1000] * 500,
        }
        pydcs_exact = {
            **base_report("dcsmizzer.pydcs-terrains/v1"),
            "filters": {"terrain": "Kola"},
            "coverage": {"exact_query_usable": True},
            "terrains": [pydcs_record],
            "conversion": {"output": {"x": 1.0, "y": 2.0}},
        }
        pydcs_bounded = output_view(
            "pydcs-terrains",
            pydcs_exact,
        ).report
        self.assertEqual(pydcs_bounded["schema"], SUMMARY_SCHEMA)
        self.assertNotIn("full", pydcs_bounded["terrains"][0])
        self.assertEqual(
            pydcs_bounded["conversion"]["output"],
            {"x": 1.0, "y": 2.0},
        )
        self.assert_bounded(pydcs_bounded)
        self.assertIs(
            output_view(
                "pydcs-terrains",
                pydcs_exact,
                details=True,
            ).report,
            pydcs_exact,
        )

    def test_exact_flying_unit_omits_duplicate_assignments_by_default(
        self,
    ) -> None:
        assignments = [
            {
                "station": index % 10 + 1,
                "CLSID": f"{{STORE-{index}}}",
                "name": f"Store {index}",
            }
            for index in range(500)
        ]
        unit = {
            "unit_category": "plane",
            "id": "Fixture",
            "name": "Fixture",
            "declared": {"flyable": True},
            "flying_unit": {
                "declared_pylons": list(range(1, 11)),
                "pylon_assignment_count": len(assignments),
                "unresolved_pylon_assignments": 0,
                "task_classes": ["CAP"],
                "tasks": [
                    {
                        "class": "CAP",
                        "id": 11,
                        "mission_group_task": "CAP",
                        "resolved": True,
                    }
                ],
                "task_default": {
                    "class": "CAP",
                    "id": 11,
                    "mission_group_task": "CAP",
                    "resolved": True,
                },
                "pylon_assignments": assignments,
            },
        }
        report = {
            **base_report("dcsmizzer.pydcs-units/v1"),
            "filters": {"unit_type": "Fixture", "limit": 20},
            "coverage": {
                "units_indexed": 1,
                "matching_units": 1,
            },
            "units": [unit],
        }

        compact = output_view("pydcs-units", report).report

        self.assertNotIn("flying_unit", compact["units"][0])
        self.assertEqual(
            compact["units"][0]["flying_summary"]["pylon_assignment_count"],
            500,
        )
        self.assertEqual(
            compact["routing"]["next_command"],
            "pydcs-aircraft",
        )
        self.assertIn(
            "Do not use pydcs-units --details",
            compact["routing"]["avoid"],
        )
        self.assertIs(
            output_view("pydcs-units", report, details=True).report,
            report,
        )
        self.assert_bounded(compact)

    def test_aircraft_routes_summary_query_and_details_separately(
        self,
    ) -> None:
        assignments = [
            {
                "station": index % 10 + 1,
                "CLSID": f"{{STORE-{index}}}",
                "name": f"Fixture Store {index}",
                "declaration": f"Store_{index}",
            }
            for index in range(500)
        ]
        report = {
            **base_report("dcsmizzer.pydcs-aircraft/v2"),
            "unit_type": "Fixture",
            "filters": {"station": None, "CLSID": None},
            "aircraft": {
                "id": "Fixture",
                "declared_pylons": list(range(1, 11)),
                "pylon_assignment_count": len(assignments),
                "unresolved_pylon_assignments": 0,
                "tasks": [],
                "pylon_assignments": assignments,
            },
        }

        compact = output_view("pydcs-aircraft", report).report
        query = output_view(
            "pydcs-aircraft",
            report,
            search="Store 49",
        ).report
        details = output_view(
            "pydcs-aircraft",
            report,
            details=True,
        ).report

        self.assertNotIn("pylon_assignments", compact["aircraft"])
        self.assertIn("assignments_by_station", compact["aircraft"])
        self.assertFalse(compact["routing"]["details_needed"])
        self.assertLessEqual(len(query["pylon_assignments"]), 20)
        self.assertFalse(query["routing"]["details_needed"])
        self.assertEqual(
            len(details["aircraft"]["pylon_assignments"]),
            500,
        )
        self.assert_bounded(compact)
        self.assert_bounded(query)

    def test_payload_catalog_exact_preset_and_details_are_distinct(self) -> None:
        presets = [
            {
                "name": f"Preset {index}",
                "display_name": None,
                "source": "fixture.lua",
                "tasks": [11],
                "pylons": [
                    {"num": station, "CLSID": f"{{STORE-{index}-{station}}}"}
                    for station in range(1, 20)
                ],
            }
            for index in range(100)
        ]
        report = {
            **base_report("dcsmizzer.dcs-default-payloads/v1"),
            "unit_type": "Fixture",
            "presets": presets,
        }

        catalog = output_view("dcs-payloads", report).report
        exact = output_view(
            "dcs-payloads",
            report,
            preset="Preset 42",
        )
        details = output_view(
            "dcs-payloads",
            report,
            details=True,
        ).report
        one_preset_catalog = output_view(
            "dcs-payloads",
            {**report, "presets": presets[:1]},
        ).report

        self.assertNotIn("pylons", catalog["presets"][0])
        self.assertEqual(one_preset_catalog["schema"], SUMMARY_SCHEMA)
        self.assertNotIn("pylons", one_preset_catalog["presets"][0])
        self.assertTrue(exact.query_matched)
        self.assertEqual(exact.report["schema"], SUMMARY_SCHEMA)
        self.assertEqual(len(exact.report["presets"]), 1)
        self.assertEqual(len(exact.report["presets"][0]["pylons"]), 12)
        self.assertTrue(exact.report["view"]["nested_output_truncated"])
        self.assertEqual(len(details["presets"]), 100)
        self.assert_bounded(catalog)
        self.assert_bounded(exact.report)

    def test_registry_defaults_to_summary_and_details_restores_registry(
        self,
    ) -> None:
        report = {
            **base_report("dcsmizzer.observed-miz-registry/v1"),
            "filters": {},
            "coverage": {"missions_matching_filters": 1},
            "theatres": [{"theatre_ref": "observed-theatre-1"}],
            "privacy": {"paths_exposed": False},
            "unit_types": [{"unit_type": "private-detail"}],
            "limitations": [],
        }

        summary = output_view("miz-registry", report).report

        self.assertEqual(
            summary["schema"],
            "dcsmizzer.observed-miz-summary/v1",
        )
        self.assertNotIn("unit_types", summary)
        self.assertIs(
            output_view("miz-registry", report, details=True).report,
            report,
        )

    def test_payload_match_defaults_to_bounded_fingerprint_summary(self) -> None:
        report = {
            **base_report("dcsmizzer.dcs-payload-match/v1"),
            "unit_type": "Fixture Plane",
            "dcs": {
                "product_version": "2.9.28",
                "steam_build_id": "424242",
            },
            "classification": "exact_observed_preset",
            "verified_exact_observed_preset": True,
            "query": {
                "valid": True,
                "issues": [],
                "normalized": {
                    "pylons": [
                        {"num": index, "CLSID": f"{{STORE-{index}}}"}
                        for index in range(1, 129)
                    ],
                    "tasks": [11],
                    "preset_name": "CAP",
                    "display_name": None,
                    "category": None,
                },
                "fingerprints": {
                    "composition_sha256": "a" * 64,
                    "configured_composition_sha256": "b" * 64,
                    "query_preset_sha256": "c" * 64,
                },
            },
            "exact_composition_candidate_count": 1,
            "configuration_candidate_count": 1,
            "configuration_gap_candidate_count": 0,
            "exact_match_count": 1,
            "configuration_unspecified_stations": [],
            "unknown_pairs": [],
            "matches": [{"name": "CAP", "source_sha256": "d" * 64}],
            "pair_evidence": [{"padding": "x" * 1000} for _ in range(128)],
            "source_binding": {
                "payload_inventory_sha256": "e" * 64,
                "files_scanned": 143,
                "files_hashed": 143,
                "source_inventory_complete": True,
                "candidate_enumeration_complete": True,
                "candidate_enumeration_scope": "queried unit type",
                "parse_failure_count": 0,
                "relevant_parse_failure_count": 0,
                "unit_type_invalid_payload_tables": 0,
                "unit_type_invalid_presets": 0,
                "relevant_parse_failure_sources": [],
                "unit_type_sources": [
                    {"source": "Fixture.lua", "source_sha256": "f" * 64}
                ],
            },
        }

        summary = output_view("dcs-payload-match", report).report

        self.assertEqual(summary["schema"], SUMMARY_SCHEMA)
        self.assertEqual(summary["query"]["pylon_count"], 128)
        self.assertTrue(
            summary["source_binding"]["candidate_enumeration_complete"]
        )
        self.assertEqual(
            summary["source_binding"]["relevant_parse_failure_count"],
            0,
        )
        self.assertEqual(
            summary["source_binding"]["unit_type_invalid_payload_tables"],
            0,
        )
        self.assertEqual(
            summary["source_binding"]["unit_type_invalid_presets"],
            0,
        )
        self.assertNotIn("pair_evidence", summary)
        self.assertIs(
            output_view(
                "dcs-payload-match",
                report,
                details=True,
            ).report,
            report,
        )
        self.assert_bounded(summary)
        self.assert_bounded(summary)

    def test_registry_summary_is_bounded_without_mutating_source(self) -> None:
        report = {
            **base_report("dcsmizzer.observed-miz-registry/v1"),
            "filters": {"nested": {"private": "x" * 1000}},
            "coverage": {"missions_matching_filters": 50},
            "theatres": [
                {
                    "theatre_ref": f"observed-theatre-{index}",
                    "nested": {"padding": "x" * 1000},
                }
                for index in range(50)
            ],
            "privacy": {"paths_exposed": False},
            "limitations": ["x" * 1000 for _ in range(50)],
        }
        original = json.loads(json.dumps(report))

        summary = output_view("miz-registry", report).report

        self.assertEqual(report, original)
        self.assertTrue(summary["view"]["output_truncated"])
        self.assertLess(
            summary["view"]["returned_items"],
            summary["view"]["matching_items"],
        )
        self.assert_bounded(summary)

    def test_report_summary_extracts_failures_warnings_and_hashes(self) -> None:
        report = {
            "schema": "dcsmizzer.miz-verification/v1",
            "artifact": "fixture.miz",
            "artifact_sha256": "a" * 64,
            "spec_sha256": "b" * 64,
            "validation": {
                "available_checks_passed": False,
                "archive_valid": True,
                "runtime_valid": None,
            },
            "limited_structure": {
                "valid": False,
                "error_count": 1,
                "warning_count": 1,
                "diagnostics": [
                    {
                        "code": "fixture_error",
                        "severity": "error",
                        "path": "$.mission",
                    },
                    {
                        "code": "fixture_warning",
                        "severity": "warning",
                        "path": "$.briefing",
                    },
                ],
            },
            "contract": {
                "checks": [{"code": "contract_failed", "passed": False}],
                "coverage_warnings": ["coverage_unknown"],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "verification.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertEqual(summary["schema"], REPORT_SUMMARY_SCHEMA)
        self.assertEqual(summary["source_schema"], report["schema"])
        self.assertTrue(summary["claims_unverified"])
        self.assertFalse(summary["reported_status"]["passed"])
        self.assertEqual(summary["reported_hash_count"], 2)
        self.assertEqual(summary["view"]["hash_scan_depth_limit"], 12)
        self.assertEqual(
            summary["reported_identity"],
            {"artifact": "fixture.miz"},
        )
        self.assertIn(
            "fixture_error",
            {item["code"] for item in summary["reported_failures"]},
        )
        self.assertIn(
            "fixture_warning",
            {item["code"] for item in summary["reported_warnings"]},
        )
        self.assert_bounded(summary)

    def test_report_summary_preserves_only_bounded_unverified_evidence_ref(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.capabilities/v3",
            "evidence_ref": {
                "schema": "dcsmizzer.report-evidence-ref/v1",
                "status": "bundle-current",
                "bundle": {
                    "id": "a" * 64,
                    "manifest_sha256": "b" * 64,
                    "untrusted_extra": "x" * 100_000,
                },
                "authority_tier": "untrusted authority claim",
                "secret_local_path_sha256": "c" * 64,
                "required_domains": {"untrusted": "x" * 100_000},
                "limitations": ["x" * 100_000],
                "validation": {
                    "usable_for_current_production_decision": True,
                    "untrusted_extra": "x" * 100_000,
                },
            },
        }
        expected_report_sha256 = intrinsic_report_sha256(report)
        report["evidence_ref"]["report_binding"] = {
            "intrinsic_report_sha256": expected_report_sha256,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bound-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertEqual(
            summary["reported_evidence_ref"],
            {
                "claims_unverified": True,
                "status": "bundle-current",
                "bundle": {
                    "id": "a" * 64,
                    "manifest_sha256": "b" * 64,
                },
                "reported_usable_for_current_production_decision": True,
                "reported_intrinsic_report_sha256": expected_report_sha256,
                "intrinsic_report_binding_matches": True,
            },
        )
        self.assertNotIn("authority_tier", summary["reported_evidence_ref"])
        self.assertNotIn("required_domains", summary["reported_evidence_ref"])
        self.assertEqual(summary["reported_hash_count"], 0)
        self.assertEqual(summary["reported_hashes"], [])
        self.assert_bounded(summary)

    def test_report_summary_separates_reported_runtime_claim_from_own_work(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.miz-verification/v1",
            "validation": {
                "available_checks_passed": True,
                "runtime_valid": True,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime-claim.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertTrue(summary["reported_runtime_validation_performed"])
        self.assertFalse(summary["view"]["runtime_validation_performed"])
        self.assert_bounded(summary)

    def test_report_summary_rejects_untrusted_evidence_ref_value_shapes(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.capabilities/v3",
            "evidence_ref": {
                "status": {"invented-ready-state": True},
                "bundle": {
                    "id": 1,
                    "manifest_sha256": "not-a-hash",
                },
                "validation": {
                    "usable_for_current_production_decision": 1,
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "untrusted-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertEqual(
            summary["reported_evidence_ref"],
            {
                "claims_unverified": True,
                "status": None,
                "bundle": {"id": None, "manifest_sha256": None},
                "reported_usable_for_current_production_decision": None,
                "reported_intrinsic_report_sha256": None,
                "intrinsic_report_binding_matches": None,
            },
        )
        self.assert_bounded(summary)

    def test_report_summary_detects_intrinsic_report_mutation(self) -> None:
        report = {
            "schema": "dcsmizzer.capabilities/v3",
            "capabilities": [{"id": "fixture", "status": "implemented"}],
        }
        expected = intrinsic_report_sha256(report)
        report["evidence_ref"] = {
            "status": "bundle-current",
            "bundle": {
                "id": "a" * 64,
                "manifest_sha256": "b" * 64,
            },
            "report_binding": {"intrinsic_report_sha256": expected},
            "validation": {"usable_for_current_production_decision": True},
        }
        report["capabilities"][0]["status"] = "mutated"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mutated-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        reference = summary["reported_evidence_ref"]
        self.assertTrue(
            reference["reported_usable_for_current_production_decision"]
        )
        self.assertFalse(reference["intrinsic_report_binding_matches"])
        self.assert_bounded(summary)

    def test_report_summary_does_not_turn_review_warnings_into_failure(
        self,
    ) -> None:
        report = {
            "schema": "dcsmizzer.build-spec-evidence-audit/v1",
            "validation": {
                "evidence_consistent": True,
                "review_warnings_clear": False,
                "runtime_valid": None,
            },
            "warnings": [
                {
                    "code": "fixture_warning",
                    "path": "$.fixture",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "audit.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertTrue(summary["reported_status"]["passed"])
        self.assertEqual(summary["reported_failure_count"], 0)
        self.assertEqual(summary["reported_warning_count"], 1)
        self.assertEqual(
            summary["reported_warnings"],
            [{"code": "fixture_warning", "path": "$.fixture"}],
        )

    def test_report_summary_discloses_nested_text_truncation(self) -> None:
        long_text = "x" * 1_000_000
        report = {
            "schema": "dcsmizzer.capabilities/v3",
            "validation": {
                "runtime_valid": None,
                "diagnostic": long_text,
            },
            "warnings": [
                {
                    "code": long_text,
                    "path": "$." + long_text,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large-text-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        truncations = summary["view"]["nested_truncations"]
        paths = {item["path"] for item in truncations}
        self.assertTrue(summary["view"]["output_truncated"])
        self.assertTrue(summary["view"]["nested_output_truncated"])
        self.assertGreaterEqual(
            summary["view"]["nested_truncation_count"],
            3,
        )
        self.assertIn("$.reported_validation.diagnostic", paths)
        self.assertIn("$.reported_warnings[0].code", paths)
        self.assertIn("$.reported_warnings[0].path", paths)
        self.assert_bounded(summary)

    def test_report_summary_uses_schema_specific_overall_status(self) -> None:
        reports = (
            (
                {
                    "schema": "dcsmizzer.miz-inspection/v1",
                    "validation": {
                        "archive_valid": True,
                        "parse_valid": False,
                        "runtime_valid": None,
                    },
                },
                False,
                "archive_valid_and_parse_valid",
            ),
            (
                {
                    "schema": "dcsmizzer.capabilities/v3",
                    "validation": {
                        "archive_valid": True,
                        "runtime_valid": None,
                    },
                },
                None,
                None,
            ),
            (
                {
                    "schema": "dcsmizzer.terrain-placement/v1",
                    "validation": {
                        "placement_valid": None,
                        "sampled_placement_valid": True,
                    },
                },
                True,
                "sampled_placement_valid",
            ),
            (
                {
                    "schema": "dcsmizzer.terrain-corridor/v1",
                    "validation": {
                        "corridor_clear": False,
                        "sampled_corridor_clear": False,
                    },
                },
                False,
                "sampled_corridor_clear",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, (report, passed, basis) in enumerate(reports):
                with self.subTest(schema=report["schema"]):
                    path = root / f"report-{index}.json"
                    path.write_text(json.dumps(report), encoding="utf-8")

                    summary = report_summary(path)

                    self.assertIs(
                        summary["reported_status"]["passed"],
                        passed,
                    )
                    self.assertEqual(
                        summary["reported_status"]["basis"],
                        basis,
                    )
                    self.assertEqual(
                        summary["view"]["schema_check"],
                        "identifier_only",
                    )
                    self.assertEqual(
                        summary["view"]["shape_check"],
                        "not_performed",
                    )
                    self.assertEqual(
                        summary["view"]["authenticity_check"],
                        "not_performed",
                    )
            miz_summary = report_summary(root / "report-0.json")
        self.assertIn(
            "validation_parse_valid_false",
            {item["code"] for item in miz_summary["reported_failures"]},
        )

    def test_report_summary_preserves_coordinate_failure_reasons(self) -> None:
        reports = (
            (
                ["best_candidate_scale_factor_out_of_range"],
                "best_candidate_scale_factor_out_of_range",
            ),
            ([], "validation_validated_false"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, (reasons, expected_code) in enumerate(reports):
                with self.subTest(reasons=reasons):
                    path = root / f"coordinate-{index}.json"
                    path.write_text(
                        json.dumps(
                            {
                                "schema": ("dcsmizzer.br-coordinate-conversion/v1"),
                                "validation": {
                                    "validated": False,
                                    "failure_reasons": reasons,
                                },
                            }
                        ),
                        encoding="utf-8",
                    )

                    summary = report_summary(path)

                    self.assertFalse(summary["reported_status"]["passed"])
                    self.assertGreater(
                        summary["reported_failure_count"],
                        0,
                    )
                    self.assertIn(
                        expected_code,
                        {item["code"] for item in summary["reported_failures"]},
                    )

    def test_report_summary_rejects_path_replacement_during_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "report.json"
            replacement = root / "replacement.json"
            path.write_text(
                '{"schema":"dcsmizzer.capabilities/v3"}',
                encoding="utf-8",
            )
            replacement.write_text(
                '{"schema":"dcsmizzer.dcs-static/v1"}',
                encoding="utf-8",
            )
            real_open = os.open

            def replace_then_open(
                name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                flags: int,
            ) -> int:
                replacement.replace(path)
                return real_open(name, flags)

            with patch(
                "dcsmizzer.report_views.os.open",
                side_effect=replace_then_open,
            ):
                with self.assertRaisesRegex(ValueError, "being opened"):
                    report_summary(path)

    def test_report_summary_rejects_unknown_duplicate_and_oversize_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unknown = root / "unknown.json"
            unknown.write_text(
                '{"schema":"unknown/v1"}',
                encoding="utf-8",
            )
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schema":"dcsmizzer.miz-build/v1","schema":"dcsmizzer.miz-build/v1"}',
                encoding="utf-8",
            )
            oversized = root / "oversized.json"
            oversized.write_text(
                '{"schema":"dcsmizzer.miz-build/v1","padding":"xxxxx"}',
                encoding="utf-8",
            )
            non_finite = root / "non-finite.json"
            non_finite.write_text(
                '{"schema":"dcsmizzer.capabilities/v3","value":1e9999}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "known"):
                report_summary(unknown)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                report_summary(duplicate)
            with self.assertRaisesRegex(ValueError, "non-finite"):
                report_summary(non_finite)
            with patch(
                "dcsmizzer.report_views.MAX_REPORT_INPUT_BYTES",
                16,
            ):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    report_summary(oversized)

    def test_report_summary_retains_only_bounded_issue_and_hash_samples(
        self,
    ) -> None:
        item_count = 1000
        report = {
            "schema": "dcsmizzer.miz-verification/v1",
            "validation": {"available_checks_passed": False},
            "checks": [
                {
                    "code": f"failure-{index}",
                    "path": f"$.checks[{index}]",
                    "passed": False,
                }
                for index in range(item_count)
            ],
            "warnings": [
                {
                    "code": f"warning-{index}",
                    "path": f"$.warnings[{index}]",
                }
                for index in range(item_count)
            ],
            "hash_records": [
                {"sha256": f"{index:064x}"} for index in range(item_count)
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertEqual(summary["reported_failure_count"], item_count + 1)
        self.assertEqual(summary["reported_warning_count"], item_count)
        self.assertEqual(summary["reported_hash_count"], item_count)
        self.assertLessEqual(len(summary["reported_failures"]), 40)
        self.assertLessEqual(len(summary["reported_warnings"]), 40)
        self.assertLessEqual(len(summary["reported_hashes"]), 40)
        self.assertTrue(summary["view"]["failures_truncated"])
        self.assertTrue(summary["view"]["warnings_truncated"])
        self.assertTrue(summary["view"]["hashes_truncated"])
        self.assertEqual(
            summary["view"]["issue_count_basis"],
            "occurrences_before_bounded_deduplication",
        )
        self.assert_bounded(summary)

    def test_report_summary_truncates_oversized_validation_metadata(self) -> None:
        validation = {
            f"validation-field-{index:04}-{'k' * 128}": "v" * 512
            for index in range(500)
        }
        validation["available_checks_passed"] = True
        report = {
            "schema": "dcsmizzer.miz-verification/v1",
            "validation": validation,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large-validation.json"
            path.write_text(json.dumps(report), encoding="utf-8")

            summary = report_summary(path)

        self.assertEqual(
            summary["reported_validation_field_count"],
            len(validation),
        )
        self.assertTrue(summary["view"]["validation_fields_truncated"])
        self.assertLess(
            len(summary["reported_validation"]),
            len(validation),
        )
        self.assertTrue(summary["reported_status"]["passed"])
        self.assert_bounded(summary)


if __name__ == "__main__":
    unittest.main()
