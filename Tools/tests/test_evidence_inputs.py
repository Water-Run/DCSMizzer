from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.evidence_inputs import (  # noqa: E402
    runtime_artifact_name,
    runtime_attestation,
    runtime_coverage,
    terrain_artifact_name,
    terrain_attestation,
    terrain_coverage,
    validate_runtime_attestation,
    validate_terrain_attestation,
)


class BoundEvidenceInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_runtime_attestation_revalidates_and_removes_absolute_paths(
        self,
    ) -> None:
        collection = self._runtime_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        validate_runtime_attestation(report)
        rendered = json.dumps(report)
        self.assertNotIn("C:\\\\", rendered)
        self.assertNotIn("D:\\\\", rendered)
        self.assertEqual(runtime_artifact_name(report), "runtime.fixture-runtime")
        self.assertEqual(runtime_coverage(report)[0], "complete")
        self.assertEqual(
            report["evidence"]["manifest_sha256"],
            "1" * 64,
        )
        self.assertEqual(
            report["dcs"]["distribution_manifest"]["semantic_identity"],
            {
                "schema": "dcsmizzer.steam-app-identity/v1",
                "app_id": "223750",
                "build_id": "24431605",
                "install_dir_casefold": "dcsworld",
                "state_flags": 4,
            },
        )
        self.assertEqual(
            report["result_summary"]["registry"]["counts"]["countries"],
            92,
        )

    def test_runtime_attestation_blocks_dirty_or_invalid_collection(self) -> None:
        dirty = self._runtime_collection()
        dirty["producer"]["git_dirty"] = True
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=dirty,
        ):
            dirty_report = runtime_attestation(self.root / "dirty.json")
        self.assertEqual(runtime_coverage(dirty_report)[0], "blocked")

        invalid = self._runtime_collection()
        invalid["validation"]["runtime_valid"] = False
        invalid["validation"]["failure_reasons"] = ["fixture_failure"]
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=invalid,
        ):
            invalid_report = runtime_attestation(self.root / "invalid.json")
        self.assertEqual(runtime_coverage(invalid_report)[0], "blocked")

    def test_failed_registry_result_is_retained_as_blocked_evidence(self) -> None:
        collection = self._runtime_collection()
        collection["result"]["status"] = "error"
        del collection["result"]["registry"]
        collection["result"]["failure"] = {
            "class": "registry_probe_failed",
            "message": "bounded failure",
        }
        collection["validation"]["runtime_valid"] = False
        collection["validation"]["failure_reasons"] = [
            "registry_not_initialized"
        ]
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        self.assertIsNone(report["result_summary"]["registry"])
        self.assertTrue(report["result_summary"]["failure_present"])
        self.assertEqual(runtime_coverage(report)[0], "blocked")

    def test_runtime_attestation_drops_unrecognized_path_from_result(self) -> None:
        collection = self._runtime_collection()
        collection["result"]["registry"]["source"] = (
            "C:\\Users\\fixture\\private.json"
        )
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        self.assertNotIn("C:\\\\Users", json.dumps(report))

    def test_mission_runtime_attestation_binds_miz_without_its_path(self) -> None:
        collection = self._mission_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        validate_runtime_attestation(report)
        self.assertEqual(runtime_coverage(report)[0], "complete")
        self.assertEqual(report["mode"], "mission-smoke")
        self.assertEqual(report["mission"]["name"], "fixture.miz")
        self.assertTrue(report["execution"]["mission_argument_attested"])
        self.assertNotIn("D:\\\\missions", json.dumps(report))
        self.assertNotIn(
            "runtime_filename",
            report["result_summary"]["mission"],
        )
        self.assertEqual(
            report["result_summary"]["coordinate_checks"][0]["label"],
            "pyramid",
        )

        inconsistent = copy.deepcopy(report)
        inconsistent["execution"]["mission_argument_attested"] = False
        with self.assertRaisesRegex(ValueError, "inconsistent evidence"):
            validate_runtime_attestation(inconsistent)

        inconsistent = copy.deepcopy(report)
        inconsistent["result_summary"]["run_id"] = "different-run"
        with self.assertRaisesRegex(ValueError, "result identity"):
            validate_runtime_attestation(inconsistent)

    def test_runtime_validator_rejects_valid_registry_summary_tamper(self) -> None:
        collection = self._runtime_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        mutations = (
            (
                lambda item: item["result_summary"].__setitem__(
                    "status",
                    "failed",
                ),
                "result identity",
            ),
            (
                lambda item: item["result_summary"]["dcs"].__setitem__(
                    "runtime_identity_attested",
                    False,
                ),
                "result identity",
            ),
            (
                lambda item: item["result_summary"]["registry"][
                    "counts"
                ].__setitem__("countries", 0),
                "registry result",
            ),
            (
                lambda item: item["result_summary"].__setitem__(
                    "failure_present",
                    True,
                ),
                "registry result",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                tampered = copy.deepcopy(report)
                mutate(tampered)
                with self.assertRaisesRegex(ValueError, message):
                    validate_runtime_attestation(tampered)

    def test_runtime_validator_rejects_valid_mission_summary_tamper(self) -> None:
        collection = self._mission_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        mutations = (
            lambda item: item["result_summary"]["mission"].__setitem__(
                "runtime_theatre",
                "Caucasus",
            ),
            lambda item: item["result_summary"]["coordinate_checks"][
                0
            ].__setitem__("passed", False),
            lambda item: item["result_summary"].__setitem__(
                "coordinate_checks_passed",
                False,
            ),
            lambda item: item["result_summary"].__setitem__(
                "events",
                ["mission_load_end", "simulation_start"],
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(report)
                mutate(tampered)
                with self.assertRaisesRegex(ValueError, "mission result"):
                    validate_runtime_attestation(tampered)

    def test_runtime_validator_enforces_distribution_identity_shape(self) -> None:
        collection = self._runtime_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            report = runtime_attestation(self.root / "manifest.json")

        standalone = copy.deepcopy(report)
        standalone["dcs"].update(
            {
                "distribution": "standalone",
                "distribution_build": None,
                "distribution_manifest": None,
                "distribution_launcher": None,
            }
        )
        validate_runtime_attestation(standalone)

        incomplete_steam = copy.deepcopy(report)
        incomplete_steam["dcs"]["distribution_launcher"] = None
        with self.assertRaisesRegex(ValueError, "Steam.*incomplete"):
            validate_runtime_attestation(incomplete_steam)

        contaminated_standalone = copy.deepcopy(standalone)
        contaminated_standalone["dcs"]["distribution_manifest"] = {
            "relative_path": "appmanifest_223750.acf",
            "size_bytes": 10,
            "sha256": "a" * 64,
        }
        with self.assertRaisesRegex(ValueError, "contains Steam data"):
            validate_runtime_attestation(contaminated_standalone)

    def test_terrain_attestation_binds_full_raw_hash_and_finite_coverage(
        self,
    ) -> None:
        path = self.root / "terrain.json"
        raw = json.dumps(self._terrain_evidence()).encode("utf-8")
        path.write_bytes(raw)

        report = terrain_attestation(path)

        validate_terrain_attestation(report)
        self.assertEqual(report["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["coverage"]["samples"], 1)
        self.assertEqual(report["coverage"]["objects"], 1)
        self.assertEqual(report["coverage"]["airfields"], 0)
        self.assertEqual(terrain_coverage(report)[0], "complete")
        self.assertRegex(
            terrain_artifact_name(report),
            r"^terrain\.sinai\.[0-9a-f]{16}$",
        )

    def test_terrain_attestation_distinguishes_declared_and_nonphysical(
        self,
    ) -> None:
        declared = self._terrain_evidence()
        declared["dcs"]["runtime_identity_attested"] = False
        declared["dcs"]["product_version_basis"] = "declared"
        declared_path = self.root / "declared.json"
        declared_path.write_text(json.dumps(declared), encoding="utf-8")
        self.assertEqual(
            terrain_coverage(terrain_attestation(declared_path))[0],
            "partial",
        )

        planning = self._terrain_evidence()
        planning["export"]["kind"] = "planning_snapshot"
        planning["export"]["runtime_initialized"] = False
        planning_path = self.root / "planning.json"
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
        self.assertEqual(
            terrain_coverage(terrain_attestation(planning_path))[0],
            "blocked",
        )

    def test_terrain_validator_rejects_authority_coverage_and_path_tamper(
        self,
    ) -> None:
        path = self.root / "terrain.json"
        path.write_text(json.dumps(self._terrain_evidence()), encoding="utf-8")
        report = terrain_attestation(path)

        authority = copy.deepcopy(report)
        authority["authority"] = (
            "initialized_dcs_terrain_api_export_with_declared_version"
        )
        with self.assertRaisesRegex(ValueError, "authority is inconsistent"):
            validate_terrain_attestation(authority)

        coverage = copy.deepcopy(report)
        coverage["coverage"]["samples"] = 1_000_001
        with self.assertRaisesRegex(ValueError, "coverage samples"):
            validate_terrain_attestation(coverage)

        private_path = copy.deepcopy(report)
        private_path["dcs"]["identity_source"] = "C:\\Users\\private"
        with self.assertRaisesRegex(ValueError, "absolute path"):
            validate_terrain_attestation(private_path)

    def test_attestation_validators_reject_policy_tamper(self) -> None:
        collection = self._runtime_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            runtime_report = runtime_attestation(self.root / "manifest.json")
        manifest_policy = copy.deepcopy(runtime_report)
        runtime_report["privacy"]["absolute_paths_recorded"] = True
        with self.assertRaisesRegex(ValueError, "privacy"):
            validate_runtime_attestation(runtime_report)

        manifest_policy["dcs"]["distribution_manifest"]["verification"][
            "current_check"
        ] = "raw_hash"
        with self.assertRaisesRegex(ValueError, "verification policy"):
            validate_runtime_attestation(manifest_policy)

        path = self.root / "terrain.json"
        path.write_text(json.dumps(self._terrain_evidence()), encoding="utf-8")
        terrain_report = terrain_attestation(path)
        terrain_report["source"]["sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "source hash"):
            validate_terrain_attestation(terrain_report)

    def test_attestation_validators_reject_impossible_source_sizes(self) -> None:
        collection = self._runtime_collection()
        with patch(
            "dcsmizzer.evidence_inputs.collect_runtime",
            return_value=collection,
        ):
            runtime_report = runtime_attestation(self.root / "manifest.json")
        runtime_report["dcs"]["executable"]["size_bytes"] = 1 << 40
        with self.assertRaisesRegex(ValueError, "executable size"):
            validate_runtime_attestation(runtime_report)

        path = self.root / "terrain.json"
        path.write_text(json.dumps(self._terrain_evidence()), encoding="utf-8")
        terrain_report = terrain_attestation(path)
        terrain_report["source"]["size_bytes"] = 1 << 40
        with self.assertRaisesRegex(ValueError, "terrain source size"):
            validate_terrain_attestation(terrain_report)

    @staticmethod
    def _runtime_collection() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.runtime-collection/v1",
            "run_id": "fixture-runtime",
            "mode": "registry-probe",
            "authority": "run_id_and_content_hash_bound_dcs_runtime_result",
            "dcs_started": True,
            "prepared_utc": "2026-08-26T00:00:00Z",
            "producer": {
                "name": "DCSMizzer",
                "version": "0.6.1",
                "git_commit": "c" * 40,
                "git_dirty": False,
            },
            "evidence": {
                "manifest_sha256": "1" * 64,
                "execution_sha256": "2" * 64,
                "result_sha256": "3" * 64,
                "dcs_log": {
                    "name": "dcs.log",
                    "size_bytes": 123,
                    "sha256": "4" * 64,
                },
                "dcs": {
                    "distribution": "steam",
                    "distribution_build": "24431605",
                    "distribution_manifest": {
                        "relative_path": "appmanifest_223750.acf",
                        "size_bytes": 10,
                        "sha256": "5" * 64,
                        "semantic_identity": {
                            "schema": "dcsmizzer.steam-app-identity/v1",
                            "app_id": "223750",
                            "build_id": "24431605",
                            "install_dir_casefold": "dcsworld",
                            "state_flags": 4,
                        },
                        "verification": {
                            "raw_hash_scope": "preparation_observation_only",
                            "current_check": "selected_semantic_identity",
                        },
                    },
                    "distribution_launcher": {
                        "absolute_path": "C:\\Program Files\\Steam\\steam.exe",
                        "size_bytes": 20,
                        "sha256": "6" * 64,
                    },
                    "product_version": "2.9.28.26385",
                    "executable": {
                        "absolute_path": "D:\\DCSWorld\\bin\\DCS.exe",
                        "relative_path": "bin/DCS.exe",
                        "size_bytes": 30,
                        "sha256": "7" * 64,
                    },
                    "sim_control_api": {
                        "relative_path": "API/Sim_ControlAPI.md",
                        "size_bytes": 40,
                        "sha256": "8" * 64,
                    },
                },
                "mission": None,
            },
            "execution": {
                "classification": "normal_completion",
                "elapsed_seconds": 30.0,
                "timed_out": False,
                "terminated": False,
                "killed": False,
                "dcs_exit_observed": True,
                "result_exists": True,
                "process_attestation": {
                    "attested": True,
                    "executable_path": "D:\\DCSWorld\\bin\\DCS.exe",
                    "executable_sha256": "7" * 64,
                    "profile_argument_attested": True,
                    "mission_argument_attested": None,
                },
            },
            "result": {
                "schema": "dcsmizzer.runtime-result/v1",
                "run_id": "fixture-runtime",
                "mode": "registry-probe",
                "status": "ok",
                "created_utc": "2026-08-26T00:01:00Z",
                "dcs": {
                    "expected_product_version": "2.9.28.26385",
                    "runtime_product_version": "2.9.28.26385",
                    "runtime_identity_attested": True,
                },
                "registry": {
                    "initialized": True,
                    "aggregate_only": True,
                    "counts": {
                        "countries": 92,
                        "unit_types": 1000,
                        "weapons_by_clsid": 2000,
                        "task_definitions": 40,
                        "planes": 300,
                        "pylon_launcher_edges": 5000,
                    },
                },
            },
            "validation": {
                "manifest_valid": True,
                "inputs_unchanged": True,
                "hook_unchanged": True,
                "execution_bound": True,
                "result_present": True,
                "run_id_matched": True,
                "mode_matched": True,
                "runtime_version_matched": True,
                "failure_reasons": [],
                "runtime_valid": True,
            },
        }

    @staticmethod
    def _terrain_evidence() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.terrain-physical-evidence/v1",
            "terrain": "Sinai",
            "dcs": {
                "product_version": "2.9.28.26385",
                "product_version_basis": "runtime_attested",
                "steam_build_id": "24431605",
                "runtime_identity_attested": True,
                "identity_source": "runtime",
            },
            "export": {
                "kind": "dcs_terrain_api_runtime_export",
                "runtime_initialized": True,
                "created_utc": "2026-08-26T00:00:00Z",
            },
            "coverage": {
                "sampling_design": "explicit_points",
                "sample_spacing_m": None,
                "sample_match_tolerance_m": 0.01,
                "object_inventory_complete": False,
                "object_search_complete": True,
                "object_search_complete_for_ground_placement": True,
                "airfield_inventory_complete": False,
                "object_searches": [
                    {
                        "x": 0.0,
                        "y": 0.0,
                        "radius_m": 100.0,
                        "volume_kind": "box_3d",
                        "minimum_altitude_msl": -1000.0,
                        "maximum_altitude_msl": 1000.0,
                        "complete_for_ground_placement": True,
                    }
                ],
            },
            "samples": [
                {"x": 0.0, "y": 0.0, "height_msl": 10.0, "surface": "land"}
            ],
            "objects": [
                {
                    "model": "fixture",
                    "center": {"x": 5.0, "y": 5.0},
                    "heading_deg": 0.0,
                    "size_obb": {"length": 2.0, "width": 2.0},
                }
            ],
            "airfields": [],
        }

    @classmethod
    def _mission_collection(cls) -> dict[str, object]:
        collection = copy.deepcopy(cls._runtime_collection())
        collection["run_id"] = "fixture-mission"
        collection["mode"] = "mission-smoke"
        collection["evidence"]["mission"] = {
            "absolute_path": "D:\\missions\\fixture.miz",
            "name": "fixture.miz",
            "size_bytes": 1000,
            "sha256": "9" * 64,
            "archive_valid": True,
            "parse_valid": True,
            "theatre": "Sinai",
            "expected_groups": 2,
            "expected_units": 3,
            "expected_player_slots": 1,
        }
        collection["execution"]["process_attestation"][
            "mission_argument_attested"
        ] = True
        collection["result"] = {
            "schema": "dcsmizzer.runtime-result/v1",
            "run_id": "fixture-mission",
            "mode": "mission-smoke",
            "status": "ok",
            "created_utc": "2026-08-26T00:01:00Z",
            "dcs": {
                "expected_product_version": "2.9.28.26385",
                "runtime_product_version": "2.9.28.26385",
                "runtime_identity_attested": True,
            },
            "mission": {
                "expected_name": "fixture.miz",
                "runtime_name": "fixture",
                "runtime_filename": "D:\\missions\\fixture.miz",
                "runtime_filename_name": "fixture.miz",
                "expected_theatre": "Sinai",
                "runtime_theatre": "Sinai",
                "expected_groups": 2,
                "groups": 2,
                "expected_units": 3,
                "units": 3,
                "expected_player_slots": 1,
                "available_slots": 1,
                "result_blue": 0,
                "result_red": 0,
            },
            "smoke": {
                "required_seconds": 10.0,
                "observed_seconds": 10.0,
                "interval_completed": True,
            },
            "coordinate_checks": [
                {
                    "label": "pyramid",
                    "latitude": 29.9792,
                    "longitude": 31.1342,
                    "expected_x": 100.0,
                    "expected_y": 200.0,
                    "runtime_x": 100.1,
                    "runtime_y": 199.9,
                    "error_m": 0.1414213562373095,
                    "tolerance_m": 1.0,
                    "passed": True,
                }
            ],
            "coordinate_checks_passed": True,
            "events": [
                {
                    "name": "mission_load_end",
                    "utc": "2026-08-26T00:00:01Z",
                },
                {
                    "name": "simulation_start",
                    "utc": "2026-08-26T00:00:02Z",
                },
                {
                    "name": "smoke_interval_complete",
                    "utc": "2026-08-26T00:00:12Z",
                },
            ],
        }
        return collection


if __name__ == "__main__":
    unittest.main()
