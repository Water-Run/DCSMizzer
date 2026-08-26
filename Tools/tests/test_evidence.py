from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main
from dcsmizzer.evidence import (
    compare_evidence,
    create_evidence_snapshot,
    evidence_readiness,
    verify_evidence_bundle,
)

VERSION = "2.9.28.26385"
CREATED = "2026-08-26T12:00:00Z"


class EvidenceLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dcs = self.root / "steamapps" / "common" / "DCSWorld"
        (self.dcs / "bin").mkdir(parents=True)
        (self.dcs / "bin" / "DCS.exe").write_bytes(b"fixture executable")
        (self.dcs / "API").mkdir()
        (self.dcs / "API" / "Sim_ControlAPI.md").write_text(
            "fixture API",
            encoding="utf-8",
        )
        (self.dcs / "_DCS_Steam").write_text("", encoding="utf-8")
        (self.root / "steamapps" / "appmanifest_223750.acf").write_text(
            '"AppState" { "buildid" "24431605" }',
            encoding="utf-8",
        )
        self.output_parent = self.root / "output"
        self.output_parent.mkdir()
        self.bundle_root = self.output_parent / "evidence"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_snapshot_is_content_addressed_repeatable_and_verifiable(self) -> None:
        with self._collection_patches():
            first = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
            second = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        bundle_id = first["bundle"]["id"]
        bundle = self.bundle_root / bundle_id
        verified = verify_evidence_bundle(bundle)

        self.assertRegex(bundle_id, r"^[0-9a-f]{64}$")
        self.assertTrue(first["validation"]["snapshot_stable"])
        self.assertTrue(first["validation"]["reproducible_producer"])
        self.assertFalse(first["bundle"]["reused_existing_identical_bundle"])
        self.assertTrue(second["bundle"]["reused_existing_identical_bundle"])
        self.assertEqual(first["bundle"]["id"], second["bundle"]["id"])
        self.assertTrue(verified["validation"]["bundle_valid"])
        self.assertEqual(verified["validation"]["artifact_count"], 7)
        self.assertEqual(
            {item["name"] for item in verified["artifacts"]},
            {
                "airfields.fixturemap",
                "capabilities",
                "countries",
                "installation",
                "modules",
                "payloads",
                "weather",
            },
        )
        rendered = json.dumps(verified)
        self.assertNotIn(str(self.root), rendered)

    def test_snapshot_and_readiness_bind_runtime_and_terrain_inputs(self) -> None:
        runtime_path = self.root / "runtime-manifest.json"
        terrain_path = self.root / "terrain-evidence.json"
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                runtime_manifests=[runtime_path],
                terrain_evidence=[terrain_path],
                created_utc=CREATED,
            )
            bundle = self.bundle_root / snapshot["bundle"]["id"]
            ready = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["runtime", "terrain"],
                runtime_manifests=[runtime_path],
                terrain_evidence=[terrain_path],
            )
            missing_live_input = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["runtime"],
            )

        verified = verify_evidence_bundle(bundle)
        artifact_names = {item["name"] for item in verified["artifacts"]}
        self.assertIn("runtime.fixture-runtime", artifact_names)
        self.assertTrue(
            any(name.startswith("terrain.sinai.") for name in artifact_names)
        )
        self.assertEqual(verified["validation"]["artifact_count"], 9)
        self.assertTrue(snapshot["validation"]["coverage_unblocked"])
        self.assertTrue(ready["validation"]["all_required_domains_ready"])
        self.assertFalse(
            missing_live_input["validation"]["all_required_domains_ready"]
        )
        self.assertEqual(
            missing_live_input["required_domains"]["runtime"]["states"],
            ["current_check_unavailable:absent"],
        )

    def test_snapshot_cli_fails_when_bound_runtime_is_blocked(self) -> None:
        blocked = self._runtime_bound()
        blocked["producer"]["git_dirty"] = True
        with self._collection_patches(runtime_bound=blocked):
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = main(
                [
                    "evidence-snapshot",
                    "--dcs-root",
                    str(self.dcs),
                    "--bundle-root",
                    str(self.bundle_root),
                    "--runtime-manifest",
                    str(self.root / "runtime-manifest.json"),
                ],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(code, 1)
        self.assertFalse(report["validation"]["coverage_unblocked"])
        runtime_record = next(
            item
            for item in report["collection"]["coverage"]
            if item["domain"] == "runtime"
        )
        self.assertEqual(runtime_record["status"], "blocked")

    def test_snapshot_cli_fails_when_bound_upstream_is_blocked(self) -> None:
        blocked_upstream = {
            "schema": "dcsmizzer.acknowledged-upstream-cache/v1",
            "authority": "immutable_acknowledged_upstream_pins",
            "sources": [],
            "validation": {"all_sources_usable": False},
        }
        with self._collection_patches(), patch(
            "dcsmizzer.evidence.upstream_status_report",
            return_value=blocked_upstream,
        ):
            stdout = io.StringIO()
            code = main(
                [
                    "evidence-snapshot",
                    "--dcs-root",
                    str(self.dcs),
                    "--bundle-root",
                    str(self.bundle_root),
                    "--cache-root",
                    str(self.root / "cache"),
                ],
                stdout=stdout,
                stderr=io.StringIO(),
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(report["validation"]["coverage_unblocked"])
        upstream = next(
            item
            for item in report["collection"]["coverage"]
            if item["domain"] == "upstream"
        )
        self.assertEqual(upstream["status"], "blocked")

    def test_snapshot_rejects_conflicting_runtime_installation_identity(
        self,
    ) -> None:
        conflicting = self._runtime_bound()
        conflicting["dcs"]["product_version"] = "0.0.0"
        conflicting["result_summary"]["dcs"][
            "expected_product_version"
        ] = "0.0.0"
        conflicting["result_summary"]["dcs"][
            "runtime_product_version"
        ] = "0.0.0"
        with self._collection_patches(
            runtime_bound=conflicting
        ), self.assertRaisesRegex(ValueError, "runtime evidence installation"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                runtime_manifests=[self.root / "runtime-manifest.json"],
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_verifier_rejects_tamper_and_unmanifested_files(self) -> None:
        with self._collection_patches():
            report = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / report["bundle"]["id"]
        artifact = bundle / "artifacts" / "countries.json"
        original = artifact.read_bytes()
        artifact.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "(size|hash) does not match"):
            verify_evidence_bundle(bundle)

        artifact.write_bytes(original)
        extra = bundle / "artifacts" / "extra.json"
        extra.write_text(
            "{}",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "unmanifested"):
            verify_evidence_bundle(bundle)
        extra.unlink()
        (bundle / "extra.txt").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unmanifested root"):
            verify_evidence_bundle(bundle)

    def test_verifier_requires_canonical_manifest_bytes(self) -> None:
        with self._collection_patches():
            report = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        manifest = (
            self.bundle_root / report["bundle"]["id"] / "manifest.json"
        )
        manifest.write_bytes(manifest.read_bytes() + b"\n")

        with self.assertRaisesRegex(ValueError, "not canonical"):
            verify_evidence_bundle(manifest.parent)

    def test_verifier_rejects_self_consistent_noncanonical_artifact(self) -> None:
        with self._collection_patches():
            report = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / report["bundle"]["id"]
        countries = json.loads(
            (bundle / "artifacts" / "countries.json").read_bytes()
        )
        noncanonical = (json.dumps(countries, indent=2) + "\n").encode()
        rewritten = self._rewrite_bundle(
            bundle,
            artifact_name="countries",
            artifact_payload=noncanonical,
        )

        with self.assertRaisesRegex(ValueError, "artifact countries.*canonical"):
            verify_evidence_bundle(rewritten)

    def test_verifier_rejects_self_consistent_internal_identity_conflict(
        self,
    ) -> None:
        with self._collection_patches():
            report = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / report["bundle"]["id"]
        airfields = json.loads(
            (bundle / "artifacts" / "airfields.fixturemap.json").read_bytes()
        )
        airfields["terrain_directory"] = "OtherMap"
        rewritten = self._rewrite_bundle(
            bundle,
            artifact_name="airfields.fixturemap",
            artifact_payload=self._canonical_bytes(airfields),
        )

        with self.assertRaisesRegex(ValueError, "airfield identity"):
            verify_evidence_bundle(rewritten)

    def test_diff_represents_installation_drift_and_scope_incomparability(
        self,
    ) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / snapshot["bundle"]["id"]
        legacy_path = self.root / "legacy.json"
        legacy_path.write_text(
            json.dumps(self._legacy_installation()),
            encoding="utf-8",
        )

        report = compare_evidence(legacy_path, bundle)
        domains = {item["domain"]: item for item in report["domains"]}

        self.assertEqual(
            report["identity"]["product_version"]["status"],
            "changed",
        )
        self.assertEqual(
            report["identity"]["distribution_build"]["status"],
            "changed",
        )
        self.assertEqual(domains["countries"]["status"], "unchanged")
        self.assertEqual(domains["modules"]["status"], "unchanged")
        self.assertEqual(domains["payloads"]["status"], "incomparable_basis")
        self.assertTrue(
            report["invalidation"]["installation_identity_changed"]
        )
        self.assertFalse(
            report["validation"]["same_installation_identity"]
        )

    def test_diff_rejects_malformed_known_report_shape(self) -> None:
        malformed = self.root / "malformed.json"
        malformed.write_text(
            json.dumps(
                {
                    "schema": "dcsmizzer.dcs-installation-survey/v1",
                    "dcs": [],
                    "steam": {},
                }
            ),
            encoding="utf-8",
        )
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / snapshot["bundle"]["id"]

        with self.assertRaisesRegex(ValueError, "invalid comparison shape"):
            compare_evidence(malformed, bundle)

    def test_diff_detects_upstream_license_lock_change(self) -> None:
        before = self.root / "upstream-before.json"
        after = self.root / "upstream-after.json"
        before.write_bytes(self._canonical_bytes(self._upstream("a" * 64)))
        after.write_bytes(self._canonical_bytes(self._upstream("b" * 64)))

        report = compare_evidence(before, after)

        self.assertEqual(len(report["domains"]), 1)
        self.assertEqual(report["domains"][0]["domain"], "upstream")
        self.assertEqual(report["domains"][0]["status"], "changed")
        self.assertEqual(
            report["invalidation"]["invalidated_domains"],
            ["upstream"],
        )

    def test_readiness_distinguishes_current_from_complete_authority(self) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
            bundle = self.bundle_root / snapshot["bundle"]["id"]
            countries = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["countries"],
            )
            payloads = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["payloads"],
            )

        self.assertTrue(
            countries["validation"]["all_required_domains_ready"]
        )
        self.assertEqual(
            countries["required_domains"]["countries"]["states"],
            ["current:complete"],
        )
        self.assertFalse(
            payloads["validation"]["all_required_domains_ready"]
        )
        self.assertEqual(
            payloads["required_domains"]["payloads"]["states"],
            ["current:partial"],
        )

    def test_readiness_marks_changed_domain_stale(self) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / snapshot["bundle"]["id"]
        changed = self._countries()
        changed["identifiers"] = ["FIXTURE", "NEW_COUNTRY"]
        changed["count"] = 2
        with self._collection_patches(countries=changed):
            report = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["countries"],
            )

        self.assertFalse(report["validation"]["all_required_domains_ready"])
        self.assertEqual(
            report["required_domains"]["countries"]["states"],
            ["stale:complete"],
        )

    def test_readiness_detects_payload_content_drift_with_equal_counts(
        self,
    ) -> None:
        original = self._payloads()
        original["unit_types"] = [
            {
                "unit_type": "Fixture",
                "sources": [{"source_sha256": "a" * 64}],
            }
        ]
        with self._collection_patches(payloads=original):
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        changed = self._payloads()
        changed["unit_types"] = [
            {
                "unit_type": "Fixture",
                "sources": [{"source_sha256": "b" * 64}],
            }
        ]
        with self._collection_patches(payloads=changed):
            report = evidence_readiness(
                self.bundle_root / snapshot["bundle"]["id"],
                self.dcs,
                required_domains=["payloads"],
            )

        self.assertEqual(
            report["required_domains"]["payloads"]["states"],
            ["stale:partial"],
        )

    def test_readiness_uses_current_coverage_not_only_bundled_coverage(
        self,
    ) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / snapshot["bundle"]["id"]
        ambiguous = self._countries()
        ambiguous["duplicate_identifiers"] = ["FIXTURE"]
        with self._collection_patches(countries=ambiguous):
            report = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["countries"],
            )

        self.assertFalse(report["validation"]["all_required_domains_ready"])
        country = next(
            item for item in report["domains"] if item["domain"] == "countries"
        )
        self.assertEqual(country["freshness"], "current")
        self.assertEqual(country["bundle_coverage"], "complete")
        self.assertEqual(country["current_coverage"], "blocked")
        self.assertEqual(country["coverage"], "blocked")

    def test_readiness_rejects_sources_that_change_between_live_passes(
        self,
    ) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
        bundle = self.bundle_root / snapshot["bundle"]["id"]
        changed = self._countries()
        changed["identifiers"] = ["CHANGED"]
        with self._collection_patches(), patch(
            "dcsmizzer.evidence.countries_report",
            side_effect=[self._countries(), changed],
        ), self.assertRaisesRegex(ValueError, "readiness passes"):
            evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["countries"],
            )

    def test_partial_collection_is_preserved_and_cli_returns_failure(self) -> None:
        with self._collection_patches(
            payload_error=ValueError("fixture payload failure")
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = main(
                [
                    "evidence-snapshot",
                    "--dcs-root",
                    str(self.dcs),
                    "--bundle-root",
                    str(self.bundle_root),
                ],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(code, 1)
        self.assertEqual(report["collection"]["failures"][0]["artifact"], "payloads")
        self.assertFalse(report["validation"]["collection_complete"])
        bundle = self.bundle_root / report["bundle"]["id"]
        self.assertTrue(verify_evidence_bundle(bundle)["validation"]["bundle_valid"])

    def test_dirty_producer_never_passes_readiness(self) -> None:
        with self._collection_patches(git_dirty=True):
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
            bundle = self.bundle_root / snapshot["bundle"]["id"]
            readiness = evidence_readiness(
                bundle,
                self.dcs,
                required_domains=["countries"],
            )

        self.assertFalse(snapshot["validation"]["reproducible_producer"])
        self.assertFalse(readiness["validation"]["reproducible_producer"])
        self.assertFalse(
            readiness["validation"]["all_required_domains_ready"]
        )

    def test_snapshot_rejects_sources_that_change_between_passes(self) -> None:
        changed = self._countries()
        changed["identifiers"] = ["CHANGED"]
        with self._collection_patches(), patch(
            "dcsmizzer.evidence.countries_report",
            side_effect=[self._countries(), changed],
        ), self.assertRaisesRegex(ValueError, "changed between"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_snapshot_rejects_producer_change_without_writing(self) -> None:
        with self._collection_patches(), patch(
            "dcsmizzer.evidence._git_identity",
            side_effect=[
                {"commit": "c" * 40, "dirty": False},
                {"commit": "d" * 40, "dirty": False},
            ],
        ), self.assertRaisesRegex(ValueError, "producer changed"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_snapshot_preflights_artifact_size_without_writing(self) -> None:
        oversized = self._countries()
        oversized["identifiers"] = ["X" * 2048]
        with self._collection_patches(countries=oversized), patch(
            "dcsmizzer.evidence.MAX_ARTIFACT_BYTES",
            1024,
        ), self.assertRaisesRegex(ValueError, "artifact byte size"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_snapshot_preflights_cross_artifact_identity(self) -> None:
        inconsistent = self._airfields()
        inconsistent["terrain_directory"] = "OtherMap"
        with self._collection_patches(
            airfields=inconsistent
        ), self.assertRaisesRegex(ValueError, "airfield identity"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_snapshot_cleans_staging_after_atomic_publish_failure(self) -> None:
        with self._collection_patches(), patch(
            "dcsmizzer.evidence.os.replace",
            side_effect=OSError("fixture publish failure"),
        ), self.assertRaisesRegex(OSError, "fixture publish failure"):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertTrue(self.bundle_root.is_dir())
        self.assertEqual(list(self.bundle_root.iterdir()), [])

    def test_snapshot_rejects_report_schema_in_the_wrong_domain(self) -> None:
        wrong = {
            "schema": "dcsmizzer.capabilities/v3",
            "survey_basis": "fixture",
        }
        with self._collection_patches(countries=wrong), self.assertRaisesRegex(
            ValueError,
            "wrong domain schema",
        ):
            create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )

        self.assertFalse(self.bundle_root.exists())

    def test_cli_verify_diff_and_readiness_exit_contract(self) -> None:
        with self._collection_patches():
            snapshot = create_evidence_snapshot(
                self.dcs,
                self.bundle_root,
                created_utc=CREATED,
            )
            bundle = self.bundle_root / snapshot["bundle"]["id"]
            legacy_path = self.root / "legacy.json"
            legacy_path.write_text(
                json.dumps(self._legacy_installation()),
                encoding="utf-8",
            )
            commands = (
                (["evidence-verify", str(bundle)], 0),
                (["evidence-diff", str(legacy_path), str(bundle)], 0),
                (
                    [
                        "evidence-readiness",
                        str(bundle),
                        "--dcs-root",
                        str(self.dcs),
                        "--require",
                        "countries",
                    ],
                    0,
                ),
                (
                    [
                        "evidence-readiness",
                        str(bundle),
                        "--dcs-root",
                        str(self.dcs),
                        "--require",
                        "payloads",
                    ],
                    1,
                ),
            )
            for argv, expected in commands:
                with self.subTest(argv=argv):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(argv, stdout=stdout, stderr=stderr)
                    self.assertEqual(code, expected)
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertIsInstance(json.loads(stdout.getvalue()), dict)

    def _collection_patches(
        self,
        *,
        countries: dict[str, object] | None = None,
        airfields: dict[str, object] | None = None,
        payloads: dict[str, object] | None = None,
        runtime_bound: dict[str, object] | None = None,
        terrain_bound: dict[str, object] | None = None,
        payload_error: Exception | None = None,
        git_dirty: bool = False,
    ) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch(
                "dcsmizzer.evidence._windows_product_version",
                return_value=VERSION,
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence._git_identity",
                return_value={"commit": "c" * 40, "dirty": git_dirty},
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.static_install_report",
                return_value=self._installation(),
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.capabilities_report",
                return_value={
                    "schema": "dcsmizzer.capabilities/v3",
                    "survey_basis": "fixture",
                    "fixture": {"status": "implemented"},
                },
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.countries_report",
                return_value=countries or self._countries(),
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.module_index_report",
                return_value=self._modules(),
            )
        )
        payload_patch = (
            patch(
                "dcsmizzer.evidence.payload_index_report",
                side_effect=payload_error,
            )
            if payload_error is not None
            else patch(
                "dcsmizzer.evidence.payload_index_report",
                return_value=payloads or self._payloads(),
            )
        )
        stack.enter_context(payload_patch)
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.weather_registry_report",
                return_value=self._weather(),
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.airbase_beacon_report",
                return_value=airfields or self._airfields(),
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.runtime_attestation",
                return_value=runtime_bound or self._runtime_bound(),
            )
        )
        stack.enter_context(
            patch(
                "dcsmizzer.evidence.terrain_attestation",
                return_value=terrain_bound or self._terrain_bound(),
            )
        )
        return stack

    @staticmethod
    def _canonical_bytes(value: object) -> bytes:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    def _rewrite_bundle(
        self,
        bundle: Path,
        *,
        artifact_name: str,
        artifact_payload: bytes,
    ) -> Path:
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        record = next(
            item
            for item in manifest["artifacts"]
            if item["name"] == artifact_name
        )
        artifact_path = bundle / record["relative_path"]
        artifact_path.write_bytes(artifact_payload)
        record["size_bytes"] = len(artifact_payload)
        record["sha256"] = hashlib.sha256(artifact_payload).hexdigest()
        core = dict(manifest)
        del core["bundle"]
        bundle_id = hashlib.sha256(self._canonical_bytes(core)).hexdigest()
        manifest["bundle"]["id"] = bundle_id
        manifest_path.write_bytes(self._canonical_bytes(manifest))
        rewritten = bundle.parent / bundle_id
        bundle.rename(rewritten)
        return rewritten

    @staticmethod
    def _installation() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-static/v1",
            "authority": "current_install_static_sources",
            "dcs_started": False,
            "dcs": {
                "product_version": VERSION,
                "steam_build_id": "24431605",
            },
            "installed_module_directories": {
                "aircraft": [
                    {
                        "directory": "FixtureAircraft",
                        "entry_present": True,
                        "declared_state": "installed",
                        "self_ids": ["Fixture Aircraft"],
                    }
                ],
                "campaigns": [],
                "terrains": [
                    {
                        "directory": "FixtureMap",
                        "entry_present": True,
                        "declared_state": "installed",
                        "self_ids": ["FixtureMap"],
                    }
                ],
            },
        }

    @staticmethod
    def _countries() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-countries/v1",
            "authority": "current_install_static_source",
            "dcs_started": False,
            "count": 1,
            "identifiers": ["FIXTURE"],
            "duplicate_identifiers": [],
            "source_sha256": "1" * 64,
        }

    @staticmethod
    def _modules() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-module-index/v1",
            "authority": "current_install_static_module_declarations",
            "dcs_started": False,
            "coverage": {"matching_modules": 1},
            "modules": [{"module_key": "Mods/aircraft/FixtureAircraft"}],
        }

    @staticmethod
    def _payloads() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-default-payload-index/v1",
            "authority": "current_install_default_payload_sources",
            "dcs_started": False,
            "compatibility_complete": False,
            "parse_failures": 0,
            "source_scope": [
                "MissionEditor/data/scripts/UnitPayloads/*.lua",
                "Mods/aircraft/*/UnitPayloads/**/*.lua",
            ],
            "coverage": {
                "source_files_discovered": 2,
                "source_files_parsed": 2,
                "presets": 3,
                "pylon_assignments": 4,
                "unique_clsids": 2,
                "task_ids": [10, 11],
            },
            "unit_types": [],
        }

    @staticmethod
    def _weather() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-weather-presets/v1",
            "authority": "current_install_static_weather_sources",
            "dcs_started": False,
            "parse_failures": 0,
            "coverage": {"usable_presets": 1},
            "presets": [{"id": "Fixture"}],
        }

    @staticmethod
    def _airfields() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-airbase-beacons/v1",
            "authority": "current_install_static_terrain_radio_and_beacons",
            "dcs_started": False,
            "terrain_directory": "FixtureMap",
            "coverage_complete": False,
            "airfield_ids_union": 1,
            "source_sha256": "2" * 64,
            "radio_source_sha256": "3" * 64,
            "airbases": [{"airdrome_id": 1}],
        }

    @staticmethod
    def _legacy_installation() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.dcs-installation-survey/v1",
            "collected_at": "2026-07-27T00:00:00Z",
            "dcs": {
                "edition": "Steam",
                "product_version": "2.9.28.26283",
                "executable_sha256": "0" * 64,
            },
            "steam": {"buildid": "24331355"},
            "countries": {
                "count": 1,
                "identifiers": ["FIXTURE"],
                "source_sha256": "1" * 64,
            },
            "installed_module_directories": {
                "aircraft": [
                    {
                        "directory": "FixtureAircraft",
                        "entry_present": True,
                        "declared_state": "installed",
                        "self_ids": ["Fixture Aircraft"],
                    }
                ],
                "campaigns": [],
                "terrains": [
                    {
                        "directory": "FixtureMap",
                        "entry_present": True,
                        "declared_state": "installed",
                        "self_ids": ["FixtureMap"],
                    }
                ],
            },
            "payload_presets": {
                "source": "MissionEditor/data/scripts/UnitPayloads/*.lua",
                "files": 1,
                "parsed": 1,
                "failures": {},
                "presets": 1,
                "pylon_assignments": 1,
                "unique_clsids": 1,
                "task_ids": [10],
            },
        }

    @staticmethod
    def _upstream(license_hash: str) -> dict[str, object]:
        return {
            "schema": "dcsmizzer.acknowledged-upstream-cache/v1",
            "coverage": {
                "configured_sources": 1,
                "usable_sources": 1,
                "unusable_sources": 0,
            },
            "sources": [
                {
                    "name": "Fixture",
                    "directory": "fixture",
                    "expected": {
                        "remote": "https://example.invalid/fixture",
                        "branch": "main",
                        "commit": "c" * 40,
                        "tree": "d" * 40,
                        "license": {"sha256": license_hash},
                    },
                    "actual": {
                        "remote": "https://example.invalid/fixture",
                        "head": "c" * 40,
                        "tree": "d" * 40,
                        "license": {"sha256": license_hash},
                    },
                    "validation": {"usable": True},
                    "errors": [],
                }
            ],
            "validation": {"all_sources_usable": True},
        }

    def _runtime_bound(self) -> dict[str, object]:
        executable = self.dcs / "bin" / "DCS.exe"
        api = self.dcs / "API" / "Sim_ControlAPI.md"
        return {
            "schema": "dcsmizzer.runtime-attestation/v1",
            "authority": "revalidated_hash_bound_runtime_collection",
            "dcs_started": False,
            "runtime_observed": True,
            "run_id": "fixture-runtime",
            "mode": "registry-probe",
            "prepared_utc": CREATED,
            "producer": {
                "name": "DCSMizzer",
                "version": "0.6.0",
                "git_commit": "d" * 40,
                "git_dirty": False,
            },
            "dcs": {
                "distribution": "steam",
                "distribution_build": "24431605",
                "distribution_manifest": {
                    "relative_path": "appmanifest_223750.acf",
                    "size_bytes": 10,
                    "sha256": "6" * 64,
                },
                "distribution_launcher": {
                    "size_bytes": 20,
                    "sha256": "7" * 64,
                },
                "product_version": VERSION,
                "executable": {
                    "relative_path": "bin/DCS.exe",
                    "size_bytes": executable.stat().st_size,
                    "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                },
                "sim_control_api": {
                    "relative_path": "API/Sim_ControlAPI.md",
                    "size_bytes": api.stat().st_size,
                    "sha256": hashlib.sha256(api.read_bytes()).hexdigest(),
                },
            },
            "mission": None,
            "evidence": {
                "collection_schema": "dcsmizzer.runtime-collection/v1",
                "collection_sha256": "1" * 64,
                "manifest_sha256": "2" * 64,
                "execution_sha256": "3" * 64,
                "result_sha256": "4" * 64,
                "dcs_log": {
                    "name": "dcs.log",
                    "size_bytes": 10,
                    "sha256": "5" * 64,
                },
            },
            "execution": {
                "classification": "normal_completion",
                "elapsed_seconds": 10.0,
                "timed_out": False,
                "terminated": False,
                "killed": False,
                "dcs_exit_observed": True,
                "result_exists": True,
                "process_attested": True,
                "profile_argument_attested": True,
                "mission_argument_attested": None,
                "executable_sha256": hashlib.sha256(
                    executable.read_bytes()
                ).hexdigest(),
            },
            "result_summary": {
                "schema": "dcsmizzer.runtime-result/v1",
                "run_id": "fixture-runtime",
                "mode": "registry-probe",
                "status": "ok",
                "created_utc": CREATED,
                "dcs": {
                    "expected_product_version": VERSION,
                    "runtime_product_version": VERSION,
                    "runtime_identity_attested": True,
                },
                "registry": {
                    "initialized": True,
                    "aggregate_only": True,
                    "counts": {
                        "countries": 1,
                        "unit_types": 1,
                        "weapons_by_clsid": 1,
                        "task_definitions": 1,
                        "planes": 1,
                        "pylon_launcher_edges": 1,
                    },
                },
                "failure_present": False,
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
            "privacy": {
                "absolute_paths_recorded": False,
                "raw_logs_recorded": False,
                "raw_manifest_recorded": False,
                "raw_execution_recorded": False,
            },
            "limitations": ["fixture runtime limitation"],
        }

    @staticmethod
    def _terrain_bound() -> dict[str, object]:
        return {
            "schema": "dcsmizzer.terrain-evidence-attestation/v1",
            "authority": "version_bound_initialized_dcs_terrain_api_export",
            "dcs_started": False,
            "terrain": "Sinai",
            "dcs": {
                "product_version": VERSION,
                "steam_build_id": "24431605",
                "product_version_basis": "runtime_attested",
                "runtime_identity_attested": True,
                "identity_source": "fixture",
            },
            "export": {
                "kind": "dcs_terrain_api_runtime_export",
                "runtime_initialized": True,
                "created_utc": CREATED,
            },
            "source": {
                "schema": "dcsmizzer.terrain-physical-evidence/v1",
                "size_bytes": 100,
                "sha256": "9" * 64,
            },
            "coverage": {
                "sampling_design_present": True,
                "sampling_design_sha256": hashlib.sha256(
                    b'"fixture"\n'
                ).hexdigest(),
                "sample_spacing_m": None,
                "sample_match_tolerance_m": 0.01,
                "object_inventory_complete": False,
                "object_search_complete": True,
                "object_search_complete_for_ground_placement": True,
                "airfield_inventory_complete": False,
                "object_searches": 1,
                "object_searches_sha256": "1" * 64,
                "samples": 1,
                "samples_sha256": "2" * 64,
                "objects": 1,
                "objects_sha256": "3" * 64,
                "airfields": 0,
                "airfields_sha256": "4" * 64,
            },
            "validation": {
                "source_schema_valid": True,
                "physical_authority": True,
                "runtime_version_attested": True,
            },
            "privacy": {
                "absolute_paths_recorded": False,
                "raw_physical_records_embedded": False,
            },
            "limitations": ["fixture terrain limitation"],
        }


if __name__ == "__main__":
    unittest.main()
