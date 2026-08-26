from __future__ import annotations

import json
import unittest

from Tools.dcsmizzer.report_provenance import (
    REPORT_EVIDENCE_REF_SCHEMA,
    attach_report_evidence_ref,
    intrinsic_report_sha256,
    validate_attached_report_evidence_ref,
)
from Tools.dcsmizzer.report_views import SUMMARY_BUDGET_BYTES, output_view

_BUNDLE_ID = "a" * 64
_MANIFEST_SHA256 = "b" * 64


class ReportProvenanceTests(unittest.TestCase):
    def test_unbound_report_is_explicit_and_original_is_unchanged(self) -> None:
        original = {
            "schema": "dcsmizzer.fixture/v1",
            "authority": "synthetic_fixture",
            "dcs_started": False,
            "validation": {"runtime_valid": None},
        }

        output = attach_report_evidence_ref(original)

        self.assertNotIn("evidence_ref", original)
        reference = output["evidence_ref"]
        self.assertEqual(reference["schema"], REPORT_EVIDENCE_REF_SCHEMA)
        self.assertEqual(reference["status"], "unbound")
        self.assertIsNone(reference["bundle"])
        self.assertEqual(
            reference["report_authority"]["declared_authority"],
            "synthetic_fixture",
        )
        self.assertFalse(
            reference["validation"]["usable_for_current_production_decision"]
        )

    def test_explicit_current_reference_is_copied_and_attached(self) -> None:
        reference = self._current_reference(ready=True)
        report = {"schema": "dcsmizzer.fixture/v1"}

        output = attach_report_evidence_ref(report, reference)
        reference["bundle"]["id"] = "c" * 64

        self.assertEqual(output["evidence_ref"]["bundle"]["id"], _BUNDLE_ID)
        self.assertEqual(
            output["evidence_ref"]["report_binding"][
                "intrinsic_report_sha256"
            ],
            intrinsic_report_sha256(report),
        )
        self.assertTrue(
            output["evidence_ref"]["validation"][
                "usable_for_current_production_decision"
            ]
        )
        validate_attached_report_evidence_ref(output)

    def test_attached_reference_validator_rejects_transport_mutation(self) -> None:
        output = attach_report_evidence_ref(
            {"schema": "dcsmizzer.fixture/v1"},
            self._current_reference(ready=True),
        )
        mutations = (
            (
                "invalid bundle identity",
                lambda value: value["evidence_ref"]["bundle"].__setitem__(
                    "id", "invalid"
                ),
            ),
            (
                "contradictory usability",
                lambda value: value["evidence_ref"]["validation"].__setitem__(
                    "usable_for_current_production_decision", False
                ),
            ),
            (
                "wrong report authority",
                lambda value: value["evidence_ref"]["report_authority"].__setitem__(
                    "report_schema", "dcsmizzer.other/v1"
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(output))
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_attached_report_evidence_ref(candidate)

    def test_failed_command_downgrades_a_current_bundle_reference(self) -> None:
        output = attach_report_evidence_ref(
            {
                "schema": "dcsmizzer.fixture/v1",
                "validation": {"runtime_valid": False},
            },
            self._current_reference(ready=True),
            command_succeeded=False,
        )

        reference = output["evidence_ref"]
        self.assertEqual(reference["status"], "unbound")
        self.assertFalse(reference["validation"]["report_gate_passed"])
        self.assertFalse(
            reference["validation"]["usable_for_current_production_decision"]
        )
        self.assertFalse(reference["report_authority"]["runtime_valid"])
        validate_attached_report_evidence_ref(output)

    def test_rejects_malformed_or_preexisting_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "already contains"):
            attach_report_evidence_ref(
                {
                    "schema": "dcsmizzer.fixture/v1",
                    "evidence_ref": {},
                }
            )
        malformed = self._current_reference(ready=True)
        malformed["bundle"]["id"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "invalid"):
            attach_report_evidence_ref(
                {"schema": "dcsmizzer.fixture/v1"},
                malformed,
            )
        contradictory = self._current_reference(ready=True)
        contradictory["validation"]["evidence_ready_for_binding"] = False
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            attach_report_evidence_ref(
                {"schema": "dcsmizzer.fixture/v1"},
                contradictory,
            )
        other_content = self._current_reference(ready=True)
        other_content["report_binding"]["intrinsic_report_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "other content"):
            attach_report_evidence_ref(
                {"schema": "dcsmizzer.fixture/v1"},
                other_content,
            )
        hostile_values = (
            (
                "unhashable git state",
                ("producer", "current"),
                "git_dirty",
                {},
            ),
            (
                "unhashable mandatory domain",
                ("report_binding",),
                "mandatory_domains",
                [{}],
            ),
            ("mixed domain key", ("required_domains",), 1, True),
        )
        for label, path, key, value in hostile_values:
            with self.subTest(label=label):
                hostile = self._current_reference(ready=True)
                target = hostile
                for component in path:
                    target = target[component]
                target[key] = value
                with self.assertRaises(ValueError):
                    attach_report_evidence_ref(
                        {"schema": "dcsmizzer.fixture/v1"},
                        hostile,
                    )

    def test_snapshot_and_verification_self_reference_content_address(self) -> None:
        for schema in (
            "dcsmizzer.evidence-snapshot/v1",
            "dcsmizzer.evidence-bundle-verification/v1",
        ):
            with self.subTest(schema=schema):
                output = attach_report_evidence_ref(
                    {
                        "schema": schema,
                        "bundle": {
                            "id": _BUNDLE_ID,
                            "manifest_sha256": _MANIFEST_SHA256,
                        },
                        "validation": {"bundle_valid": True},
                    }
                )

                reference = output["evidence_ref"]
                self.assertEqual(reference["status"], "self")
                self.assertTrue(reference["validation"]["bundle_integrity_verified"])
                self.assertFalse(
                    reference["validation"]["usable_for_current_production_decision"]
                )

    def test_readiness_self_reference_requires_every_gate(self) -> None:
        base = {
            "schema": "dcsmizzer.evidence-readiness/v1",
            "bundle": {
                "kind": "content_addressed_bundle",
                "bundle_id": _BUNDLE_ID,
            },
            "required_domains": {"installation": {"ready": True}},
            "validation": {
                "bundle_valid": True,
                "current_identity_collected": True,
                "reproducible_producer": True,
                "all_required_domains_ready": True,
            },
        }

        ready = attach_report_evidence_ref(base)
        blocked_input = dict(base)
        blocked_input["validation"] = dict(base["validation"])
        blocked_input["validation"]["all_required_domains_ready"] = False
        blocked = attach_report_evidence_ref(blocked_input)
        contradictory_input = dict(base)
        contradictory_input["required_domains"] = {
            "installation": {"ready": False}
        }
        contradictory_domain = attach_report_evidence_ref(contradictory_input)

        self.assertEqual(
            ready["evidence_ref"]["status"],
            "self",
        )
        self.assertTrue(
            ready["evidence_ref"]["validation"][
                "usable_for_current_production_decision"
            ]
        )
        self.assertEqual(
            blocked["evidence_ref"]["status"],
            "self",
        )
        self.assertFalse(
            contradictory_domain["evidence_ref"]["validation"][
                "usable_for_current_production_decision"
            ]
        )
        self.assertFalse(
            contradictory_domain["evidence_ref"]["validation"][
                "required_domains_ready"
            ]
        )

    def test_full_binding_keeps_a_large_exact_summary_within_budget(self) -> None:
        domains = (
            "airfields",
            "capabilities",
            "countries",
            "installation",
            "modules",
            "payloads",
            "runtime",
            "terrain",
            "upstream",
            "weather",
        )
        payload_report = {
            "schema": "dcsmizzer.dcs-default-payloads/v1",
            "unit_type": "Fixture",
            "presets": [
                {
                    "name": "Exact",
                    "display_name": "Exact",
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
        }
        summary = output_view(
            "dcs-payloads",
            payload_report,
            preset="Exact",
        ).report

        bound = attach_report_evidence_ref(
            summary,
            self._current_reference(ready=True, domains=domains),
        )
        rendered = (
            json.dumps(
                bound,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        self.assertEqual(len(bound["presets"]), 1)
        self.assertLessEqual(len(rendered), SUMMARY_BUDGET_BYTES)

    @staticmethod
    def _current_reference(
        *,
        ready: bool,
        domains: tuple[str, ...] = ("installation",),
    ) -> dict[str, object]:
        git_commit = "c" * 40
        return {
            "schema": REPORT_EVIDENCE_REF_SCHEMA,
            "status": "bundle-current" if ready else "unbound",
            "bundle": {
                "id": _BUNDLE_ID,
                "manifest_sha256": _MANIFEST_SHA256,
            },
            "authority_tier": (
                "current_verified_binding_context" if ready else "report_intrinsic_only"
            ),
            "producer": {
                "bundle": {
                    "name": "DCSMizzer",
                    "version": "0.9.0",
                    "git_commit": git_commit,
                    "git_dirty": False,
                },
                "current": {
                    "name": "DCSMizzer",
                    "version": "0.9.0",
                    "git_commit": git_commit,
                    "git_dirty": False,
                },
            },
            "required_domains": {domain: ready for domain in sorted(domains)},
            "domain_artifact_bindings": {
                domain: "d" * 64 for domain in sorted(domains)
            },
            "current_readiness": {
                "schema": "dcsmizzer.evidence-readiness/v1",
                "canonical_sha256": "e" * 64,
                "live_collection_passes": 2,
                "stable_across_passes": True,
                "live_collection_failures": 0,
            },
            "report_binding": {
                "command": "dcs-static",
                "query_sha256": "f" * 64,
                "mandatory_domains": [sorted(domains)[0]],
                "source_roots_matched": True,
            },
            "limitations": ["Fixture limitation."],
            "validation": {
                "bundle_reference_present": True,
                "bundle_integrity_verified": True,
                "bundle_stable_during_binding": True,
                "current_state_revalidated": True,
                "required_domains_ready": ready,
                "reproducible_current_producer": True,
                "current_producer_matches_bundle": True,
                "evidence_ready_for_binding": ready,
            },
        }


if __name__ == "__main__":
    unittest.main()
