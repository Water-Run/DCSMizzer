from __future__ import annotations

import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer import construction_provenance as provenance  # noqa: E402
from dcsmizzer.builder import build_miz, verify_miz  # noqa: E402
from dcsmizzer.cli import main as cli_main  # noqa: E402
from dcsmizzer.report_provenance import (  # noqa: E402
    REPORT_EVIDENCE_REF_SCHEMA,
    attach_report_evidence_ref,
)

from tests.test_builder import fixture_spec  # noqa: E402

CREATED = "2026-08-27T01:00:00Z"
PRODUCER_COMMIT = "c" * 40
EVIDENCE_BUNDLE_ID = "a" * 64
EVIDENCE_MANIFEST_SHA256 = "b" * 64


class ConstructionProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spec_path = self.root / "private-spec.json"
        self.resource_path = self.root / "private-briefing.bin"
        self.artifact_path = self.root / "private-mission.miz"

        spec = fixture_spec()
        spec["mapResource"] = {"briefing": "briefing.bin"}
        spec["resources"] = [
            {
                "member": "briefing.bin",
                "source": self.resource_path.name,
            }
        ]
        spec["expect"]["minimum"]["resource_mappings"] = 1
        self.resource_path.write_bytes(b"content-addressed briefing fixture")
        self.spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

        (
            captured_spec,
            self.spec_payload,
            self.resource_payloads,
            self.resource_ledger,
        ) = provenance._capture_inputs(self.spec_path)
        self.assertEqual(captured_spec.sha256, provenance._sha256(self.spec_payload))

        self.build_report, built = build_miz(
            self.spec_path,
            self.artifact_path,
        )
        self.verify_report, verified = verify_miz(
            self.artifact_path,
            self.spec_path,
        )
        self.assertTrue(built)
        self.assertTrue(verified)
        self.artifact_payload = self.artifact_path.read_bytes()

        self.query = {
            "schema": "dcsmizzer.construction-query/v1",
            "spec_sha256": provenance._sha256(self.spec_payload),
            "resources": self.resource_ledger,
            "installed_terrain": None,
            "pydcs_terrain": "fixture",
            "resolved_pydcs_terrain": "fixture",
            "resolved_briefingroom_terrain": "FixtureMap",
            "briefingroom_enabled": True,
            "mandatory_domains": list(provenance._AUDIT_BASE_DOMAINS),
        }
        self.query_sha256 = provenance._sha256(
            provenance._canonical_bytes(self.query)
        )
        self.producer = {
            "name": "DCSMizzer",
            "version": provenance.__version__,
            "git_commit": PRODUCER_COMMIT,
            "git_dirty": False,
            "toolchain": provenance._toolchain_record(),
        }
        self.evidence_producer = {
            key: self.producer[key]
            for key in ("name", "version", "git_commit", "git_dirty")
        }
        domains = tuple(sorted(provenance._AUDIT_BASE_DOMAINS))
        schemas = {
            "capabilities": "dcsmizzer.capabilities/v3",
            "countries": "dcsmizzer.dcs-countries/v1",
            "installation": "dcsmizzer.dcs-static/v1",
            "modules": "dcsmizzer.dcs-module-index/v1",
            "payloads": "dcsmizzer.dcs-default-payload-index/v1",
            "upstream": "dcsmizzer.acknowledged-upstream-cache/v1",
            "weather": "dcsmizzer.dcs-weather-presets/v1",
        }
        artifacts = [
            {
                "name": name,
                "schema": schemas[name],
                "size_bytes": index,
                "sha256": f"{index:064x}",
                "verified": True,
            }
            for index, name in enumerate(domains, start=1)
        ]
        coverage = [
            {
                "artifact": name,
                "domain": name,
                "status": "complete",
                "reason": "Synthetic complete construction evidence fixture.",
            }
            for name in domains
        ]
        self.evidence_verification = {
            "schema": "dcsmizzer.evidence-bundle-verification/v1",
            "bundle": {
                "id": EVIDENCE_BUNDLE_ID,
                "directory_name": EVIDENCE_BUNDLE_ID,
                "manifest_sha256": EVIDENCE_MANIFEST_SHA256,
            },
            "producer": copy.deepcopy(self.evidence_producer),
            "collection": {
                "stable_across_passes": True,
                "outcome": "complete",
            },
            "coverage": coverage,
            "artifacts": artifacts,
            "validation": {"bundle_valid": True},
        }
        self.domain_bindings = provenance._domain_artifact_bindings(
            self.evidence_verification,
            domains,
        )
        self.readiness = {
            "schema": "dcsmizzer.evidence-readiness/v1",
            "bundle": {
                "kind": "content_addressed_bundle",
                "schema": "dcsmizzer.evidence-bundle/v1",
                "bundle_id": EVIDENCE_BUNDLE_ID,
            },
            "dcs_started": False,
            "current_identity": {},
            "required_domains": {
                name: {
                    "ready": True,
                    "records": 1,
                    "states": ["current:complete"],
                }
                for name in domains
            },
            "producer": {
                "name": self.producer["name"],
                "version": self.producer["version"],
                "git_commit": self.producer["git_commit"],
                "reproducible": True,
            },
            "domains": [
                {
                    "domain": name,
                    "base_domain": name,
                    "required": True,
                    "freshness": "current",
                    "bundle_coverage": "complete",
                    "current_coverage": "complete",
                    "coverage": "complete",
                    "usable_for_required_decision": True,
                }
                for name in domains
            ],
            "live_collection_failures": [],
            "live_collection": {
                "passes": 2,
                "stable_across_passes": True,
            },
            "validation": {
                "bundle_valid": True,
                "current_identity_collected": True,
                "reproducible_producer": True,
                "all_required_domains_ready": True,
            },
            "limitations": [],
        }
        self.reference = self._evidence_reference()
        self.context = {
            "reference": self.reference,
            "readiness": self.readiness,
            "verification": self.evidence_verification,
        }
        self.audit_intrinsic = {
            "schema": "dcsmizzer.build-spec-evidence-audit/v1",
            "input_spec": self.spec_path.name,
            "input_spec_sha256": provenance._sha256(self.spec_payload),
            "input_spec_path_scope": "basename_only",
            "dcs_started": False,
            "upstream_python_executed": False,
            "filters": {
                "installed_terrain": self.query["installed_terrain"],
                "terrain_query": self.query["pydcs_terrain"],
                "briefingroom_terrain_query": "FixtureMap",
                "briefingroom_enabled": True,
                "require_acknowledged_upstreams": True,
            },
            "sources": {},
            "checks": [],
            "warnings": [],
            "validation": {
                "checks": 0,
                "passed": 0,
                "failed": 0,
                "warning_count": 0,
                "evidence_consistent": True,
                "review_warnings_clear": True,
                "runtime_valid": None,
            },
            "limitations": [],
        }
        self.audit_report = attach_report_evidence_ref(
            self.audit_intrinsic,
            self.reference,
            command_succeeded=True,
        )
        self.manifest, self.objects = self._make_manifest()
        self.bundle = self._write_bundle(
            self.root / "base-bundle",
            self.manifest,
            self.objects,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_bundle_verifies_and_replays_exact_artifact(self) -> None:
        report = self._verify(self.bundle)

        self.assertTrue(report["validation"]["bundle_valid"])
        self.assertTrue(report["validation"]["all_object_hashes_valid"])
        self.assertTrue(report["validation"]["node_dag_valid"])
        self.assertTrue(report["validation"]["pipeline_continuity_valid"])
        self.assertTrue(report["validation"]["replay_toolchain_matches"])
        self.assertTrue(report["validation"]["replay_producer_matches"])
        self.assertTrue(report["validation"]["artifact_rebuilt_exact"])
        self.assertTrue(report["validation"]["verification_replayed"])
        self.assertFalse(report["validation"]["fully_reproducible"])
        self.assertFalse(report["validation"]["static_release_ready"])
        self.assertIsNone(report["validation"]["runtime_valid"])
        self.assertNotIn(str(self.root), json.dumps(self.manifest))
        self.assertNotIn(str(self.root), json.dumps(report))

        repeated, repeated_objects = self._make_manifest()
        self.assertEqual(repeated, self.manifest)
        self.assertEqual(repeated_objects, self.objects)

    def test_object_and_manifest_byte_tampering_are_rejected(self) -> None:
        object_tamper = self._copy_bundle("object-tamper")
        artifact_digest = self.manifest["bindings"]["artifact"]["sha256"]
        artifact_object = object_tamper / "objects" / artifact_digest
        changed = bytearray(artifact_object.read_bytes())
        changed[len(changed) // 2] ^= 0x01
        artifact_object.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "size or hash"):
            self._verify(object_tamper)

        manifest_tamper = self._copy_bundle("manifest-tamper")
        manifest_path = manifest_tamper / "manifest.json"
        manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            self._verify(manifest_tamper)

        extra_root = self._copy_bundle("extra-root")
        (extra_root / "unexpected.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "too many|unexpected root"):
            self._verify(extra_root)

    def test_unmanifested_content_addressed_object_is_rejected_cleanly(self) -> None:
        bundle = self._copy_bundle("unmanifested-object")
        (bundle / "objects" / ("f" * 64)).write_bytes(b"unmanifested")

        with self.assertRaisesRegex(
            ValueError,
            "too many|missing or unexpected objects",
        ):
            self._verify(bundle)

    def test_manifest_listed_but_unbound_object_is_rejected(self) -> None:
        payload = b"manifest-listed object with no semantic binding"
        digest = provenance._sha256(payload)
        manifest = copy.deepcopy(self.manifest)
        manifest["objects"].append(
            {
                "sha256": digest,
                "relative_path": f"objects/{digest}",
                "size_bytes": len(payload),
                "media_types": ["application/octet-stream"],
            }
        )
        manifest["objects"].sort(key=lambda item: item["sha256"])
        manifest = self._readdress_manifest(manifest)
        objects = {**self.objects, digest: payload}
        bundle = self._write_bundle(
            self.root / "bound-nowhere",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "unbound object"):
            self._verify(bundle)

    def test_manifest_hostile_types_and_calendar_values_fail_cleanly(self) -> None:
        mutations = (
            (
                "unhashable-domain",
                lambda value: value["evidence_anchor"].__setitem__(
                    "mandatory_domains", [{}]
                ),
            ),
            (
                "unhashable-media-type",
                lambda value: value["objects"][0].__setitem__(
                    "media_types", [{}]
                ),
            ),
            (
                "invalid-calendar-date",
                lambda value: value.__setitem__(
                    "created_utc", "2026-99-99T01:00:00Z"
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                manifest = self._readdress_manifest(manifest)
                bundle = self._write_bundle(
                    self.root / label,
                    manifest,
                    self.objects,
                )
                with self.assertRaises(ValueError):
                    self._verify(bundle)

    def test_hostile_hash_report_and_readiness_lists_fail_cleanly(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["bindings"]["artifact"]["sha256"] = []
        manifest = self._readdress_manifest(manifest)
        hostile_hash = self._write_bundle(
            self.root / "hostile-hash-list",
            manifest,
            self.objects,
        )
        self._assert_value_error_and_cli_clean(hostile_hash)

        for field in ("generation", "validation"):
            with self.subTest(build_report_field=field):
                build_report = copy.deepcopy(self.build_report)
                build_report[field] = []
                manifest, objects = self._make_manifest(
                    build_report=build_report,
                )
                bundle = self._write_bundle(
                    self.root / f"build-{field}-list",
                    manifest,
                    objects,
                )
                self._assert_value_error_and_cli_clean(bundle)

        readiness = copy.deepcopy(self.readiness)
        readiness["producer"] = []
        reference = copy.deepcopy(self.reference)
        reference["current_readiness"]["canonical_sha256"] = provenance._sha256(
            provenance._canonical_bytes(readiness)
        )
        context = {
            "reference": reference,
            "readiness": readiness,
            "verification": copy.deepcopy(self.evidence_verification),
        }
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            reference,
            command_succeeded=True,
        )
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        hostile_readiness = self._write_bundle(
            self.root / "readiness-producer-list",
            manifest,
            objects,
        )
        self._assert_value_error_and_cli_clean(hostile_readiness)

    def test_build_and_verify_reports_cannot_carry_transport_metadata(
        self,
    ) -> None:
        for name in ("build", "verify"):
            with self.subTest(name=name):
                build_report = copy.deepcopy(self.build_report)
                verify_report = copy.deepcopy(self.verify_report)
                if name == "build":
                    build_report = attach_report_evidence_ref(build_report)
                else:
                    verify_report = attach_report_evidence_ref(verify_report)
                manifest, objects = self._make_manifest(
                    build_report=build_report,
                    verify_report=verify_report,
                )
                bundle = self._write_bundle(
                    self.root / f"{name}-transport",
                    manifest,
                    objects,
                )
                with self.assertRaisesRegex(ValueError, "continuity"):
                    self._verify(bundle)

    def test_self_consistent_report_mutations_fail_pipeline_validation(self) -> None:
        mutations = (
            ("failed-verification", ("validation", "available_checks_passed"), False),
            ("invented-runtime", ("validation", "runtime_valid"), True),
            ("other-spec", ("spec_sha256",), "0" * 64),
        )
        for label, path, value in mutations:
            with self.subTest(label=label):
                verify_report = copy.deepcopy(self.verify_report)
                target = verify_report
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = value
                manifest, objects = self._make_manifest(
                    verify_report=verify_report,
                )
                bundle = self._write_bundle(
                    self.root / label,
                    manifest,
                    objects,
                )
                with self.assertRaisesRegex(ValueError, "continuity"):
                    self._verify(bundle)

    def test_audit_transport_must_match_sealed_evidence_and_query(self) -> None:
        mutations = (
            (
                "other-bundle",
                lambda value: value["bundle"].update({"id": "d" * 64}),
            ),
            (
                "other-manifest",
                lambda value: value["bundle"].update(
                    {"manifest_sha256": "e" * 64}
                ),
            ),
            (
                "other-query",
                lambda value: value["report_binding"].update(
                    {"query_sha256": "f" * 64}
                ),
            ),
            (
                "other-domain-artifact",
                lambda value: value["domain_artifact_bindings"].update(
                    {"countries": "1" * 64}
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                alternate_reference = copy.deepcopy(self.reference)
                mutate(alternate_reference)
                alternate_audit = attach_report_evidence_ref(
                    self.audit_intrinsic,
                    alternate_reference,
                    command_succeeded=True,
                )
                manifest, objects = self._make_manifest(
                    audit_report=alternate_audit,
                )
                bundle = self._write_bundle(
                    self.root / label,
                    manifest,
                    objects,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "audit.*(evidence|query)|evidence.*audit",
                ):
                    self._verify(bundle)

    def test_audit_report_must_match_the_sealed_spec(self) -> None:
        audit = copy.deepcopy(self.audit_intrinsic)
        audit["input_spec_sha256"] = "0" * 64
        audit = attach_report_evidence_ref(
            audit,
            self.reference,
            command_succeeded=True,
        )
        manifest, objects = self._make_manifest(audit_report=audit)
        bundle = self._write_bundle(
            self.root / "audit-other-spec",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "audit spec binding"):
            self._verify(bundle)

    def test_audit_rejects_consistent_failure_and_count_drift(self) -> None:
        failed = copy.deepcopy(self.audit_intrinsic)
        failed["checks"] = [{"id": "synthetic-failure", "passed": False}]
        failed["validation"] = {
            "checks": 1,
            "passed": 0,
            "failed": 1,
            "warning_count": 0,
            "evidence_consistent": False,
            "review_warnings_clear": True,
            "runtime_valid": None,
        }
        drifted = copy.deepcopy(self.audit_intrinsic)
        drifted["validation"]["checks"] = 1
        for label, audit in (
            ("consistent-audit-failure", failed),
            ("audit-count-drift", drifted),
        ):
            with self.subTest(label=label):
                bound = attach_report_evidence_ref(
                    audit,
                    self.reference,
                    command_succeeded=True,
                )
                manifest, objects = self._make_manifest(audit_report=bound)
                bundle = self._write_bundle(
                    self.root / label,
                    manifest,
                    objects,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "audit decision did not pass",
                ):
                    self._verify(bundle)

    def test_audit_resolved_terrain_filters_are_sealed(self) -> None:
        mutations = (
            (
                "other-resolved-pydcs-terrain",
                "terrain_query",
                "OtherPydcsTerrain",
            ),
            (
                "other-briefingroom-terrain",
                "briefingroom_terrain_query",
                "OtherBriefingRoomTerrain",
            ),
        )
        for label, field, value in mutations:
            with self.subTest(label=label):
                audit = copy.deepcopy(self.audit_intrinsic)
                audit["filters"][field] = value
                audit = attach_report_evidence_ref(
                    audit,
                    self.reference,
                    command_succeeded=True,
                )
                manifest, objects = self._make_manifest(audit_report=audit)
                bundle = self._write_bundle(
                    self.root / label,
                    manifest,
                    objects,
                )
                with self.assertRaisesRegex(ValueError, "audit decision"):
                    self._verify(bundle)

    def test_query_preimage_must_match_the_sealed_spec_and_resources(self) -> None:
        mutations = (
            (
                "query-other-spec",
                lambda value: value.update({"spec_sha256": "0" * 64}),
            ),
            (
                "query-other-resource",
                lambda value: value["resources"][0].update(
                    {"sha256": "1" * 64}
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                query = copy.deepcopy(self.query)
                mutate(query)
                query_sha256 = provenance._sha256(
                    provenance._canonical_bytes(query)
                )
                reference = copy.deepcopy(self.reference)
                reference["report_binding"]["query_sha256"] = query_sha256
                context = copy.deepcopy(self.context)
                context["reference"] = reference
                audit = attach_report_evidence_ref(
                    self.audit_intrinsic,
                    reference,
                    command_succeeded=True,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "query.*bindings",
                ):
                    self._make_manifest(
                        audit_report=audit,
                        query=query,
                        query_sha256=query_sha256,
                        evidence_context=context,
                    )

    def test_sealed_input_shape_is_checked_without_replay_producer(self) -> None:
        invalid_json_manifest, invalid_json_objects = self._make_preimage_manifest(
            spec_payload=b"not a JSON construction spec\n",
            resource_payloads=self.resource_payloads,
            resource_ledger=self.resource_ledger,
        )
        invalid_json = self._write_bundle(
            self.root / "sealed-spec-not-json",
            invalid_json_manifest,
            invalid_json_objects,
        )

        source = self.resource_ledger[0]
        renamed_member = "renamed-briefing.bin"
        renamed_ledger = [{**source, "member": renamed_member}]
        renamed_payloads = {
            renamed_member: self.resource_payloads[source["member"]]
        }
        resource_manifest, resource_objects = self._make_preimage_manifest(
            spec_payload=self.spec_payload,
            resource_payloads=renamed_payloads,
            resource_ledger=renamed_ledger,
        )
        inconsistent_resource = self._write_bundle(
            self.root / "sealed-spec-resource-mismatch",
            resource_manifest,
            resource_objects,
        )

        for label, bundle in (
            ("non-json-spec", invalid_json),
            ("resource-member-mismatch", inconsistent_resource),
        ):
            with self.subTest(label=label):
                with (
                    patch.object(
                        provenance,
                        "verify_evidence_bundle",
                        return_value=copy.deepcopy(self.evidence_verification),
                    ),
                    patch.object(
                        provenance,
                        "_git_identity",
                        return_value={"commit": "d" * 40, "dirty": False},
                    ),
                    patch.object(provenance, "build_miz") as build,
                    patch.object(provenance, "verify_miz") as verify,
                    self.assertRaises(ValueError),
                ):
                    provenance.verify_construction_bundle(bundle)
                build.assert_not_called()
                verify.assert_not_called()

    def test_replay_detects_a_self_consistent_artifact_replacement(self) -> None:
        replacement = self.artifact_payload + b"trailing replacement byte"
        digest = provenance._sha256(replacement)
        build_report = copy.deepcopy(self.build_report)
        verify_report = copy.deepcopy(self.verify_report)
        for report in (build_report, verify_report):
            report["artifact_sha256"] = digest
            report["artifact_bytes"] = len(replacement)
        manifest, objects = self._make_manifest(
            build_report=build_report,
            verify_report=verify_report,
            artifact_payload=replacement,
        )
        bundle = self._write_bundle(
            self.root / "replaced-artifact",
            manifest,
            objects,
        )

        report = self._verify(bundle)

        self.assertTrue(report["validation"]["bundle_valid"])
        self.assertFalse(report["validation"]["artifact_rebuilt_exact"])
        self.assertFalse(report["validation"]["fully_reproducible"])
        self.assertFalse(report["validation"]["static_release_ready"])

    def test_wrong_producer_or_toolchain_never_runs_replay(self) -> None:
        with (
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.evidence_verification),
            ),
            patch.object(
                provenance,
                "_git_identity",
                return_value={"commit": "d" * 40, "dirty": False},
            ),
            patch.object(provenance, "build_miz") as build,
            patch.object(provenance, "verify_miz") as verify,
        ):
            report = provenance.verify_construction_bundle(self.bundle)
        build.assert_not_called()
        verify.assert_not_called()
        self.assertTrue(report["validation"]["replay_toolchain_matches"])
        self.assertFalse(report["validation"]["replay_producer_matches"])
        self.assertFalse(report["validation"]["artifact_rebuilt_exact"])

        producer = copy.deepcopy(self.producer)
        producer["toolchain"]["platform"] = "different-platform"
        manifest, objects = self._make_manifest(producer=producer)
        bundle = self._write_bundle(
            self.root / "different-toolchain",
            manifest,
            objects,
        )
        with (
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.evidence_verification),
            ),
            patch.object(
                provenance,
                "_git_identity",
                return_value={"commit": PRODUCER_COMMIT, "dirty": False},
            ),
            patch.object(provenance, "build_miz") as build,
            patch.object(provenance, "verify_miz") as verify,
        ):
            report = provenance.verify_construction_bundle(bundle)
        build.assert_not_called()
        verify.assert_not_called()
        self.assertFalse(report["validation"]["replay_toolchain_matches"])
        self.assertFalse(report["validation"]["replay_producer_matches"])

    def test_cli_fails_when_available_construction_replay_fails(self) -> None:
        for failed_field in ("artifact_rebuilt_exact", "verification_replayed"):
            with self.subTest(failed_field=failed_field):
                validation = {
                    "bundle_valid": True,
                    "pipeline_continuity_valid": True,
                    "replay_toolchain_matches": True,
                    "replay_producer_matches": True,
                    "artifact_rebuilt_exact": True,
                    "verification_replayed": True,
                }
                validation[failed_field] = False
                replay_report = {
                    "schema": provenance.CONSTRUCTION_VERIFICATION_SCHEMA,
                    "validation": validation,
                }
                stdout = io.StringIO()
                stderr = io.StringIO()
                with patch(
                    "dcsmizzer.cli.verify_construction_bundle",
                    return_value=replay_report,
                ):
                    exit_code = cli_main(
                        ["construction-verify", str(self.bundle)],
                        stdout=stdout,
                        stderr=stderr,
                    )

                self.assertEqual(exit_code, 1)
                self.assertEqual(stderr.getvalue(), "")
                rendered = json.loads(stdout.getvalue())
                self.assertFalse(rendered["validation"][failed_field])

    def test_construction_producer_must_match_audit_evidence_producer(self) -> None:
        producer = copy.deepcopy(self.producer)
        producer["git_commit"] = "d" * 40
        manifest, objects = self._make_manifest(producer=producer)
        bundle = self._write_bundle(
            self.root / "substituted-producer",
            manifest,
            objects,
        )

        with (
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.evidence_verification),
            ),
            patch.object(
                provenance,
                "_git_identity",
                return_value={"commit": "d" * 40, "dirty": False},
            ),
            self.assertRaisesRegex(ValueError, "audit producer binding"),
        ):
            provenance.verify_construction_bundle(bundle)

    def test_embedded_evidence_identity_is_revalidated(self) -> None:
        changed = copy.deepcopy(self.evidence_verification)
        changed["bundle"]["id"] = "d" * 64

        with self.assertRaisesRegex(
            ValueError,
            "evidence anchor|verification preimage",
        ):
            self._verify(self.bundle, evidence_verification=changed)

    def test_unready_evidence_is_valid_but_cannot_open_the_gate(self) -> None:
        context, audit = self._unready_evidence_context()
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        bundle = self._write_bundle(
            self.root / "unready-evidence",
            manifest,
            objects,
        )

        report = self._verify(bundle)

        self.assertTrue(report["validation"]["bundle_valid"])
        self.assertEqual(report["evidence"]["status"], "unbound")
        self.assertFalse(
            manifest["gate"]["evidence_ready_for_static_release"]
        )
        self.assertFalse(report["validation"]["static_release_ready"])

    def test_readiness_domains_must_explain_required_domain_results(self) -> None:
        readiness = copy.deepcopy(self.readiness)
        countries = next(
            item
            for item in readiness["domains"]
            if item["base_domain"] == "countries"
        )
        countries["required"] = False
        reference = copy.deepcopy(self.reference)
        reference["current_readiness"]["canonical_sha256"] = provenance._sha256(
            provenance._canonical_bytes(readiness)
        )
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            reference,
            command_succeeded=True,
        )
        context = {
            "reference": reference,
            "readiness": readiness,
            "verification": copy.deepcopy(self.evidence_verification),
        }
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        bundle = self._write_bundle(
            self.root / "contradictory-readiness-domains",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "evidence anchor|readiness"):
            self._verify(bundle)

    def test_readiness_bundle_coverage_must_match_verified_evidence(self) -> None:
        verification = copy.deepcopy(self.evidence_verification)
        modules_coverage = next(
            item
            for item in verification["coverage"]
            if item["artifact"] == "modules"
        )
        modules_coverage["status"] = "partial"
        modules_coverage["reason"] = "Synthetic partial modules coverage."

        domains = tuple(sorted(provenance._AUDIT_BASE_DOMAINS))
        reference = copy.deepcopy(self.reference)
        reference["domain_artifact_bindings"] = (
            provenance._domain_artifact_bindings(verification, domains)
        )
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            reference,
            command_succeeded=True,
        )
        context = {
            "reference": reference,
            "readiness": copy.deepcopy(self.readiness),
            "verification": verification,
        }
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        bundle = self._write_bundle(
            self.root / "verified-modules-partial-readiness-complete",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "bundle coverage"):
            self._verify(bundle, evidence_verification=verification)

    def test_gate_cannot_be_forced_over_unready_evidence(self) -> None:
        context, audit = self._unready_evidence_context()
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        manifest["gate"]["evidence_ready_for_static_release"] = True
        manifest = self._readdress_manifest(manifest)
        bundle = self._write_bundle(
            self.root / "forced-evidence-gate",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "audit evidence anchor"):
            self._verify(bundle)

    def test_audit_gate_failure_cannot_be_replayed_as_success(self) -> None:
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            self.reference,
            command_succeeded=False,
        )
        manifest, objects = self._make_manifest(audit_report=audit)
        bundle = self._write_bundle(
            self.root / "failed-audit-gate",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "audit evidence anchor"):
            self._verify(bundle)

    def test_stale_readiness_cannot_be_resealed_as_current(self) -> None:
        readiness = copy.deepcopy(self.readiness)
        readiness["live_collection"]["passes"] = 1
        reference = copy.deepcopy(self.reference)
        reference["status"] = "unbound"
        reference["authority_tier"] = "report_intrinsic_only"
        reference["current_readiness"]["canonical_sha256"] = provenance._sha256(
            provenance._canonical_bytes(readiness)
        )
        reference["current_readiness"]["live_collection_passes"] = 1
        reference["validation"]["current_state_revalidated"] = False
        reference["validation"]["evidence_ready_for_binding"] = False
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            reference,
            command_succeeded=True,
        )
        context = {
            "reference": reference,
            "readiness": readiness,
            "verification": copy.deepcopy(self.evidence_verification),
        }
        manifest, objects = self._make_manifest(
            audit_report=audit,
            evidence_context=context,
        )
        bundle = self._write_bundle(
            self.root / "stale-readiness",
            manifest,
            objects,
        )

        with self.assertRaisesRegex(ValueError, "evidence anchor|readiness"):
            self._verify(bundle)

    def test_evidence_directory_rejects_extra_or_missing_bundle(self) -> None:
        extra = self._copy_bundle("extra-evidence")
        (extra / "evidence" / ("d" * 64)).mkdir()
        with self.assertRaisesRegex(ValueError, "too many|unexpected members"):
            self._verify(extra)

        missing = self._copy_bundle("missing-evidence")
        (missing / "evidence" / EVIDENCE_BUNDLE_ID).rmdir()
        with self.assertRaisesRegex(ValueError, "unexpected members"):
            self._verify(missing)

    def test_oversized_directory_sets_are_rejected_after_one_extra(self) -> None:
        root_bundle = self._copy_bundle("bounded-root-scan")
        for index in range(8):
            (root_bundle / f"extra-{index}").write_bytes(b"extra")
        self._assert_bounded_directory_rejection(
            root_bundle,
            root_bundle,
            expected_entries=3,
        )

        object_bundle = self._copy_bundle("bounded-object-scan")
        objects = object_bundle / "objects"
        for index in range(8):
            (objects / f"{1000 + index:064x}").write_bytes(b"extra")
        self._assert_bounded_directory_rejection(
            object_bundle,
            objects,
            expected_entries=len(self.manifest["objects"]),
        )

        evidence_bundle = self._copy_bundle("bounded-evidence-scan")
        evidence = evidence_bundle / "evidence"
        for index in range(8):
            (evidence / f"extra-{index}").mkdir()
        self._assert_bounded_directory_rejection(
            evidence_bundle,
            evidence,
            expected_entries=1,
        )

    def test_linked_bundle_or_object_is_rejected(self) -> None:
        linked_bundle = self.root / "linked-construction"
        try:
            linked_bundle.symlink_to(self.bundle, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {type(error).__name__}")
        with self.assertRaisesRegex(ValueError, "link|reparse"):
            self._verify(linked_bundle)

        object_link_bundle = self._copy_bundle("linked-object")
        digest = self.manifest["bindings"]["artifact"]["sha256"]
        object_path = object_link_bundle / "objects" / digest
        target = self.root / "outside-object"
        target.write_bytes(object_path.read_bytes())
        object_path.unlink()
        try:
            object_path.symlink_to(target)
        except OSError as error:
            self.skipTest(f"file symlinks unavailable: {type(error).__name__}")
        with self.assertRaisesRegex(ValueError, "link|reparse"):
            self._verify(object_link_bundle)

    def test_output_root_cannot_be_nested_under_any_input_root(self) -> None:
        for label, root_name in (
            ("under-evidence", "evidence"),
            ("under-dcs", "dcs"),
            ("under-cache", "cache"),
        ):
            with self.subTest(label=label):
                dcs, cache, evidence, _construction = self._snapshot_roots(label)
                sources = {
                    "evidence": evidence,
                    "dcs": dcs,
                    "cache": cache,
                }
                source = sources[root_name]
                output = source / "nested-construction-output"
                before = {
                    item.relative_to(source)
                    for item in source.rglob("*")
                }
                with (
                    patch.object(
                        provenance,
                        "_producer_record",
                        return_value=copy.deepcopy(self.producer),
                    ),
                    patch.object(
                        provenance,
                        "current_report_evidence_context",
                        side_effect=AssertionError(
                            "overlapping output reached evidence collection"
                        ),
                    ) as collect,
                    self.assertRaises(ValueError),
                ):
                    provenance.create_construction_snapshot(
                        self.spec_path,
                        output,
                        evidence_bundle=evidence,
                        dcs_root=dcs,
                        cache_root=cache,
                        pydcs_terrain="fixture",
                        created_utc=CREATED,
                    )

                self.assertFalse(output.exists())
                self.assertEqual(
                    {item.relative_to(source) for item in source.rglob("*")},
                    before,
                )
                collect.assert_not_called()

    def test_gci_station_snapshot_fails_closed_on_audit_failure(self) -> None:
        spec = json.loads(self.spec_path.read_text(encoding="utf-8"))
        country = spec["mission"]["coalition"]["blue"]["country"][0]
        country["vehicle"] = {
            "group": [
                {
                    "groupId": 90,
                    "name": "Fixture GCI Group",
                    "task": "Ground Nothing",
                    "route": {
                        "points": [
                            {
                                "x": 1000.0,
                                "y": 2000.0,
                                "type": "Turning Point",
                                "action": "Off Road",
                                "task": {
                                    "id": "ComboTask",
                                    "params": {
                                        "tasks": [
                                            {
                                                "number": 1,
                                                "auto": True,
                                                "id": "WrappedAction",
                                                "enabled": True,
                                                "params": {
                                                    "action": {
                                                        "id": "ActivateGCI",
                                                        "params": {
                                                            "unitId": 90,
                                                            "channel": 5,
                                                            "radius": 200000,
                                                            "x": 50000,
                                                            "y": 60000,
                                                        },
                                                    }
                                                },
                                            }
                                        ]
                                    },
                                },
                            }
                        ]
                    },
                    "units": [
                        {
                            "unitId": 90,
                            "name": "Fixture GCI Station",
                            "type": "GCI_station_MiG29",
                            "skill": "Excellent",
                            "x": 1000.0,
                            "y": 2000.0,
                            "heading": 0.0,
                        }
                    ],
                },
                {
                    "groupId": 91,
                    "name": "Fixture GCI Radar",
                    "task": "Ground Nothing",
                    "route": {
                        "points": [
                            {
                                "x": 100000.0,
                                "y": 2000.0,
                                "type": "Turning Point",
                                "action": "Off Road",
                            }
                        ]
                    },
                    "units": [
                        {
                            "unitId": 91,
                            "name": "Fixture EWR",
                            "type": "1L13 EWR",
                            "skill": "Excellent",
                            "x": 100000.0,
                            "y": 2000.0,
                            "heading": 0.0,
                        }
                    ],
                },
            ]
        }
        gci_spec = self.root / "gci-spec.json"
        gci_spec.write_text(
            json.dumps(spec, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        captured, payload, _resources, _ledger = provenance._capture_inputs(
            gci_spec
        )
        self.assertIn(b"GCI_station_MiG29", payload)
        self.assertEqual(captured.sha256, provenance._sha256(payload))
        dcs, cache, evidence, construction_root = self._snapshot_roots(
            "gci-audit-failure"
        )
        with (
            patch.object(
                provenance,
                "_producer_record",
                return_value=copy.deepcopy(self.producer),
            ),
            patch.object(
                provenance,
                "current_report_evidence_context",
            ) as collect,
            patch.object(provenance, "audit_build_spec") as audit_call,
            patch.object(provenance, "build_miz") as build,
            patch.object(provenance, "_populate_staging") as populate,
            self.assertRaisesRegex(ValueError, "GCI.*not implemented"),
        ):
            provenance.create_construction_snapshot(
                gci_spec,
                construction_root,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
                pydcs_terrain="fixture",
                created_utc=CREATED,
            )

        self.assertFalse(construction_root.exists())
        collect.assert_not_called()
        audit_call.assert_not_called()
        build.assert_not_called()
        populate.assert_not_called()

    def test_create_snapshot_publishes_without_cleaning_the_final_bundle(
        self,
    ) -> None:
        dcs, cache, evidence, construction_root = self._snapshot_roots(
            "successful-snapshot"
        )

        def copy_embedded(_source: Path, destination: Path) -> None:
            destination.mkdir()

        verification = {
            "validation": {
                "bundle_valid": True,
                "artifact_rebuilt_exact": True,
                "verification_replayed": True,
                "replay_producer_matches": True,
            }
        }
        contexts = [copy.deepcopy(self.context), copy.deepcopy(self.context)]
        with (
            patch.object(
                provenance,
                "_producer_record",
                return_value=copy.deepcopy(self.producer),
            ),
            patch.object(
                provenance,
                "current_report_evidence_context",
                side_effect=contexts,
            ),
            patch.object(
                provenance,
                "audit_build_spec",
                return_value=(copy.deepcopy(self.audit_intrinsic), True),
            ),
            patch.object(
                provenance,
                "_copy_evidence_bundle",
                side_effect=copy_embedded,
            ),
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.evidence_verification),
            ),
            patch.object(
                provenance,
                "verify_construction_bundle",
                return_value=verification,
            ) as verify_bundle,
            patch.object(
                provenance,
                "_remove_staging",
                wraps=provenance._remove_staging,
            ) as remove_staging,
        ):
            report = provenance.create_construction_snapshot(
                self.spec_path,
                construction_root,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
                pydcs_terrain="fixture",
                created_utc=CREATED,
            )

        final = construction_root / report["bundle"]["id"]
        self.assertTrue(report["validation"]["bundle_valid"])
        self.assertTrue(final.is_dir())
        self.assertEqual(
            {item.name for item in final.iterdir()},
            {"evidence", "manifest.json", "objects"},
        )
        self.assertFalse(
            any(
                item.name.startswith(provenance._STAGING_PREFIX)
                for item in construction_root.iterdir()
            )
        )
        remove_staging.assert_not_called()
        verify_bundle.assert_called_once()
        verified_path = verify_bundle.call_args.args[0]
        self.assertTrue(os.path.samefile(verified_path, final))

    def test_create_snapshot_cleans_staging_after_failed_build(self) -> None:
        dcs, cache, evidence, construction_root = self._snapshot_roots(
            "failed-snapshot"
        )
        failed_build = {
            "schema": "dcsmizzer.miz-build/v1",
            "validation": {"available_checks_passed": False},
        }
        with (
            patch.object(
                provenance,
                "_producer_record",
                return_value=copy.deepcopy(self.producer),
            ),
            patch.object(
                provenance,
                "current_report_evidence_context",
                return_value=copy.deepcopy(self.context),
            ),
            patch.object(
                provenance,
                "audit_build_spec",
                return_value=(copy.deepcopy(self.audit_intrinsic), True),
            ),
            patch.object(
                provenance,
                "build_miz",
                return_value=(failed_build, False),
            ),
            patch.object(provenance, "verify_miz") as verify,
            patch.object(
                provenance,
                "_remove_staging",
                wraps=provenance._remove_staging,
            ) as remove_staging,
        ):
            report = provenance.create_construction_snapshot(
                self.spec_path,
                construction_root,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
                pydcs_terrain="fixture",
                created_utc=CREATED,
            )

        self.assertIsNone(report["bundle"])
        self.assertEqual(report["failed_stage"]["reason"], "build_checks_failed")
        self.assertFalse(construction_root.exists())
        remove_staging.assert_called_once()
        verify.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows ADS regression")
    def test_windows_alternate_data_stream_is_rejected(self) -> None:
        source = self.root / "base-object"
        source.write_bytes(b"base bytes")
        stream = Path(f"{source}:construction")
        try:
            stream.write_bytes(b"alternate bytes")
        except OSError as error:
            self.skipTest(f"alternate data streams unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "alternate data stream"):
            provenance._read_exact_regular_file(
                stream,
                maximum_bytes=1024,
                label="construction object",
            )

    def _evidence_reference(self) -> dict[str, object]:
        domains = tuple(sorted(provenance._AUDIT_BASE_DOMAINS))
        return {
            "schema": REPORT_EVIDENCE_REF_SCHEMA,
            "status": "bundle-current",
            "bundle": {
                "id": EVIDENCE_BUNDLE_ID,
                "manifest_sha256": EVIDENCE_MANIFEST_SHA256,
            },
            "authority_tier": "current_verified_binding_context",
            "producer": {
                "bundle": copy.deepcopy(self.evidence_producer),
                "current": copy.deepcopy(self.evidence_producer),
            },
            "required_domains": {name: True for name in domains},
            "domain_artifact_bindings": copy.deepcopy(self.domain_bindings),
            "current_readiness": {
                "schema": "dcsmizzer.evidence-readiness/v1",
                "canonical_sha256": provenance._sha256(
                    provenance._canonical_bytes(self.readiness)
                ),
                "live_collection_passes": 2,
                "stable_across_passes": True,
                "live_collection_failures": 0,
            },
            "report_binding": {
                "command": "construction-snapshot",
                "query_sha256": self.query_sha256,
                "mandatory_domains": list(domains),
                "source_roots_matched": True,
            },
            "limitations": ["Synthetic construction provenance fixture."],
            "validation": {
                "bundle_reference_present": True,
                "bundle_integrity_verified": True,
                "bundle_stable_during_binding": True,
                "current_state_revalidated": True,
                "required_domains_ready": True,
                "reproducible_current_producer": True,
                "current_producer_matches_bundle": True,
                "evidence_ready_for_binding": True,
            },
        }

    def _unready_evidence_context(
        self,
    ) -> tuple[dict[str, object], dict[str, object]]:
        readiness = copy.deepcopy(self.readiness)
        readiness["required_domains"]["countries"]["ready"] = False
        readiness["required_domains"]["countries"]["states"] = [
            "stale:complete"
        ]
        countries = next(
            item
            for item in readiness["domains"]
            if item["base_domain"] == "countries"
        )
        countries["freshness"] = "stale"
        countries["usable_for_required_decision"] = False
        readiness["validation"]["all_required_domains_ready"] = False
        reference = copy.deepcopy(self.reference)
        reference["status"] = "unbound"
        reference["authority_tier"] = "report_intrinsic_only"
        reference["required_domains"]["countries"] = False
        reference["current_readiness"]["canonical_sha256"] = provenance._sha256(
            provenance._canonical_bytes(readiness)
        )
        reference["validation"]["required_domains_ready"] = False
        reference["validation"]["evidence_ready_for_binding"] = False
        audit = attach_report_evidence_ref(
            self.audit_intrinsic,
            reference,
            command_succeeded=True,
        )
        context = {
            "reference": reference,
            "readiness": readiness,
            "verification": copy.deepcopy(self.evidence_verification),
        }
        return context, audit

    def _snapshot_roots(
        self,
        label: str,
    ) -> tuple[Path, Path, Path, Path]:
        base = self.root / label
        dcs = base / "DCS"
        cache = base / "upstream"
        evidence = base / "evidence-source"
        construction = base / "construction"
        dcs.mkdir(parents=True)
        (cache / "pydcs").mkdir(parents=True)
        (cache / "briefing-room-for-dcs").mkdir()
        evidence.mkdir()
        return dcs, cache, evidence, construction

    def _make_preimage_manifest(
        self,
        *,
        spec_payload: bytes,
        resource_payloads: dict[str, bytes],
        resource_ledger: list[dict[str, object]],
    ) -> tuple[dict[str, object], dict[str, bytes]]:
        spec_sha256 = provenance._sha256(spec_payload)
        query = copy.deepcopy(self.query)
        query["spec_sha256"] = spec_sha256
        query["resources"] = copy.deepcopy(resource_ledger)
        query_sha256 = provenance._sha256(provenance._canonical_bytes(query))
        reference = copy.deepcopy(self.reference)
        reference["report_binding"]["query_sha256"] = query_sha256
        context = {
            "reference": reference,
            "readiness": copy.deepcopy(self.readiness),
            "verification": copy.deepcopy(self.evidence_verification),
        }
        audit = copy.deepcopy(self.audit_intrinsic)
        audit["input_spec_sha256"] = spec_sha256
        audit = attach_report_evidence_ref(
            audit,
            reference,
            command_succeeded=True,
        )
        build_report = copy.deepcopy(self.build_report)
        build_report["generation"]["spec_sha256"] = spec_sha256
        build_report["resource_inputs"] = copy.deepcopy(resource_ledger)
        verify_report = copy.deepcopy(self.verify_report)
        verify_report["spec_sha256"] = spec_sha256
        verify_report["resource_inputs"] = copy.deepcopy(resource_ledger)
        return provenance._construction_manifest(
            created_utc=CREATED,
            producer=copy.deepcopy(self.producer),
            query=query,
            query_sha256=query_sha256,
            spec_payload=spec_payload,
            resource_payloads=copy.deepcopy(resource_payloads),
            resource_ledger=copy.deepcopy(resource_ledger),
            audit_report=audit,
            build_report=build_report,
            verify_report=verify_report,
            artifact_payload=self.artifact_payload,
            evidence_context=context,
        )

    def _assert_value_error_and_cli_clean(self, bundle: Path) -> None:
        with self.assertRaises(ValueError):
            self._verify(bundle)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.evidence_verification),
            ),
            patch.object(
                provenance,
                "_git_identity",
                return_value={"commit": PRODUCER_COMMIT, "dirty": False},
            ),
        ):
            exit_code = cli_main(
                ["construction-verify", str(bundle)],
                stdout=stdout,
                stderr=stderr,
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertEqual(stderr.getvalue().count("\n"), 1)

    def _assert_bounded_directory_rejection(
        self,
        bundle: Path,
        directory: Path,
        *,
        expected_entries: int,
    ) -> None:
        original_iterdir = Path.iterdir
        target = os.path.normcase(str(directory.absolute()))
        seen = 0

        def guarded_iterdir(path: Path):
            nonlocal seen
            if os.path.normcase(str(path.absolute())) != target:
                yield from original_iterdir(path)
                return
            for item in original_iterdir(path):
                seen += 1
                if seen > expected_entries + 1:
                    raise AssertionError(
                        "directory scan continued beyond expected + 1"
                    )
                yield item

        with (
            patch.object(Path, "iterdir", guarded_iterdir),
            self.assertRaises(ValueError),
        ):
            self._verify(bundle)
        self.assertLessEqual(seen, expected_entries + 1)

    @staticmethod
    def _readdress_manifest(
        manifest: dict[str, object],
    ) -> dict[str, object]:
        rewritten = copy.deepcopy(manifest)
        core = dict(rewritten)
        core.pop("bundle")
        rewritten["bundle"]["id"] = provenance._sha256(
            provenance._canonical_bytes(core)
        )
        return rewritten

    def _make_manifest(
        self,
        *,
        audit_report: dict[str, object] | None = None,
        build_report: dict[str, object] | None = None,
        verify_report: dict[str, object] | None = None,
        artifact_payload: bytes | None = None,
        producer: dict[str, object] | None = None,
        query: dict[str, object] | None = None,
        query_sha256: str | None = None,
        evidence_context: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, bytes]]:
        return provenance._construction_manifest(
            created_utc=CREATED,
            producer=copy.deepcopy(producer or self.producer),
            query=copy.deepcopy(query or self.query),
            query_sha256=query_sha256 or self.query_sha256,
            spec_payload=self.spec_payload,
            resource_payloads=copy.deepcopy(self.resource_payloads),
            resource_ledger=copy.deepcopy(self.resource_ledger),
            audit_report=copy.deepcopy(audit_report or self.audit_report),
            build_report=copy.deepcopy(build_report or self.build_report),
            verify_report=copy.deepcopy(verify_report or self.verify_report),
            artifact_payload=artifact_payload or self.artifact_payload,
            evidence_context=copy.deepcopy(evidence_context or self.context),
        )

    def _write_bundle(
        self,
        parent: Path,
        manifest: dict[str, object],
        objects: dict[str, bytes],
    ) -> Path:
        bundle = parent / manifest["bundle"]["id"]
        objects_directory = bundle / "objects"
        evidence_directory = bundle / "evidence" / EVIDENCE_BUNDLE_ID
        objects_directory.mkdir(parents=True)
        evidence_directory.mkdir(parents=True)
        for digest, payload in objects.items():
            (objects_directory / digest).write_bytes(payload)
        (bundle / "manifest.json").write_bytes(
            provenance._canonical_bytes(manifest)
        )
        return bundle

    def _copy_bundle(self, label: str) -> Path:
        destination = self.root / label / self.bundle.name
        destination.parent.mkdir()
        shutil.copytree(self.bundle, destination)
        return destination

    def _verify(
        self,
        bundle: Path,
        *,
        evidence_verification: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with (
            patch.object(
                provenance,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(
                    evidence_verification or self.evidence_verification
                ),
            ),
            patch.object(
                provenance,
                "_git_identity",
                return_value={"commit": PRODUCER_COMMIT, "dirty": False},
            ),
        ):
            return provenance.verify_construction_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
