from __future__ import annotations

import copy
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer import audit_transcript as transcript_module  # noqa: E402, RUF100
from dcsmizzer import construction_provenance as legacy_module  # noqa: E402, RUF100
from dcsmizzer import construction_replay as replay_module  # noqa: E402, RUF100
from dcsmizzer import spec_audit as spec_audit_module  # noqa: E402, RUF100
from dcsmizzer.report_provenance import (  # noqa: E402, RUF100
    attach_report_evidence_ref,
)

from tests import test_construction_provenance as legacy_fixtures  # noqa: E402, RUF100
from tests import test_spec_audit as audit_fixtures  # noqa: E402, RUF100
from tests.test_audit_transcript import _entries  # noqa: E402, RUF100


class ConstructionReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.legacy = legacy_fixtures.ConstructionProvenanceTests(
            "test_complete_bundle_verifies_and_replays_exact_artifact"
        )
        self.legacy.setUp()
        self.root = self.legacy.root
        self.query = copy.deepcopy(self.legacy.query)
        self.query["schema"] = replay_module.CONSTRUCTION_QUERY_SCHEMA
        self.query["require_acknowledged_upstreams"] = True
        self.query_sha256 = legacy_module._sha256(
            legacy_module._canonical_bytes(self.query)
        )
        self.context = copy.deepcopy(self.legacy.context)
        self.context["reference"]["report_binding"].update(
            command=replay_module.CONSTRUCTION_COMMAND,
            query_sha256=self.query_sha256,
        )
        self.audit_intrinsic = copy.deepcopy(self.legacy.audit_intrinsic)
        self.audit_report = attach_report_evidence_ref(
            self.audit_intrinsic,
            self.context["reference"],
            command_succeeded=True,
        )
        self.transcript_payload = transcript_module.canonical_audit_transcript_bytes(
            transcript_module.build_audit_transcript(_entries())
        )
        self.manifest, self.objects = replay_module._construction_manifest_v2(
            created_utc=legacy_fixtures.CREATED,
            producer=copy.deepcopy(self.legacy.producer),
            query=copy.deepcopy(self.query),
            query_sha256=self.query_sha256,
            spec_payload=self.legacy.spec_payload,
            resource_payloads=copy.deepcopy(self.legacy.resource_payloads),
            resource_ledger=copy.deepcopy(self.legacy.resource_ledger),
            transcript_payload=self.transcript_payload,
            audit_report=self.audit_report,
            build_report=copy.deepcopy(self.legacy.build_report),
            verify_report=copy.deepcopy(self.legacy.verify_report),
            artifact_payload=self.legacy.artifact_payload,
            evidence_context=copy.deepcopy(self.context),
        )
        self.bundle = self._write_bundle("base", self.manifest, self.objects)

    def tearDown(self) -> None:
        self.legacy.tearDown()

    def test_v2_bundle_happy_path_replays_all_three_stages(self) -> None:
        report = self._verify(self.bundle)

        self.assertEqual(
            report["schema"], replay_module.CONSTRUCTION_VERIFICATION_SCHEMA
        )
        self.assertTrue(report["validation"]["bundle_valid"])
        self.assertTrue(report["validation"]["audit_decision_replay_performed"])
        self.assertTrue(report["validation"]["audit_decision_replay_passed"])
        self.assertTrue(report["validation"]["artifact_rebuild_performed"])
        self.assertTrue(report["validation"]["artifact_rebuilt_exact"])
        self.assertTrue(report["validation"]["verification_replay_performed"])
        self.assertTrue(report["validation"]["verification_replayed"])
        self.assertTrue(report["validation"]["fully_reproducible"])
        self.assertTrue(report["recorded_gate"]["static_release_ready"])
        self.assertFalse(report["validation"]["static_release_ready"])
        transcript_sha = self.manifest["bindings"]["audit_transcript"]["sha256"]
        self.assertEqual(self.manifest["nodes"][0]["transcript_sha256"], transcript_sha)

    def test_writer_captures_twice_then_replays_sealed_inputs(self) -> None:
        dcs = self.root / "writer-roots" / "DCS"
        cache = self.root / "writer-roots" / "upstream"
        evidence = self.root / "writer-roots" / "evidence"
        construction = self.root / "writer-output"
        dcs.mkdir(parents=True)
        (cache / "pydcs").mkdir(parents=True)
        (cache / "briefing-room-for-dcs").mkdir()
        evidence.mkdir()
        transcript = transcript_module.parse_audit_transcript(self.transcript_payload)

        def evidence_context(
            _bundle: Path,
            _dcs: Path,
            *,
            report_command: str,
            query_sha256: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            context = copy.deepcopy(self.context)
            context["reference"]["report_binding"].update(
                command=report_command,
                query_sha256=query_sha256,
            )
            return context

        def copy_evidence(_source: Path, destination: Path) -> None:
            destination.mkdir()

        with (
            patch.object(
                legacy_module,
                "_producer_record",
                return_value=copy.deepcopy(self.legacy.producer),
            ),
            patch.object(
                legacy_module,
                "current_report_evidence_context",
                side_effect=evidence_context,
            ),
            patch.object(
                transcript_module,
                "capture_live_audit",
                side_effect=[
                    (
                        copy.deepcopy(self.audit_intrinsic),
                        True,
                        copy.deepcopy(transcript),
                    ),
                    (
                        copy.deepcopy(self.audit_intrinsic),
                        True,
                        copy.deepcopy(transcript),
                    ),
                ],
            ) as capture,
            patch.object(
                replay_module,
                "_replay_sealed_audit",
                return_value=(copy.deepcopy(self.audit_intrinsic), True),
            ) as audit_replay,
            patch.object(
                legacy_module,
                "_copy_evidence_bundle",
                side_effect=copy_evidence,
            ),
            patch.object(
                legacy_module,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.legacy.evidence_verification),
            ),
        ):
            report = replay_module.create_construction_snapshot_v2(
                self.legacy.spec_path,
                construction,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
                pydcs_terrain="fixture",
                created_utc=legacy_fixtures.CREATED,
            )

        self.assertEqual(report["schema"], replay_module.CONSTRUCTION_SNAPSHOT_SCHEMA)
        self.assertTrue(report["validation"]["fully_reproducible"])
        self.assertTrue(report["validation"]["static_release_ready"])
        self.assertEqual(capture.call_count, 2)
        self.assertEqual(audit_replay.call_count, 2)
        first_replay = audit_replay.call_args_list[0].kwargs
        self.assertEqual(first_replay["spec_payload"], self.legacy.spec_payload)
        self.assertEqual(set(first_replay["resource_payloads"]), {"briefing.bin"})
        final = construction / report["bundle"]["id"]
        self.assertTrue((final / "manifest.json").is_file())

    def test_writer_rejects_transcript_drift_before_creating_output(self) -> None:
        dcs = self.root / "drift-roots" / "DCS"
        cache = self.root / "drift-roots" / "upstream"
        evidence = self.root / "drift-roots" / "evidence"
        construction = self.root / "must-not-exist"
        dcs.mkdir(parents=True)
        (cache / "pydcs").mkdir(parents=True)
        (cache / "briefing-room-for-dcs").mkdir()
        evidence.mkdir()
        first = transcript_module.build_audit_transcript(_entries())
        drifted_entries = _entries()
        drifted_entries[0]["result"]["drift_marker"] = True
        second = transcript_module.build_audit_transcript(drifted_entries)

        def evidence_context(
            _bundle: Path,
            _dcs: Path,
            *,
            report_command: str,
            query_sha256: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            context = copy.deepcopy(self.context)
            context["reference"]["report_binding"].update(
                command=report_command,
                query_sha256=query_sha256,
            )
            return context

        with (
            patch.object(
                legacy_module,
                "_producer_record",
                return_value=copy.deepcopy(self.legacy.producer),
            ),
            patch.object(
                legacy_module,
                "current_report_evidence_context",
                side_effect=evidence_context,
            ),
            patch.object(
                transcript_module,
                "capture_live_audit",
                side_effect=[
                    (copy.deepcopy(self.audit_intrinsic), True, first),
                    (copy.deepcopy(self.audit_intrinsic), True, second),
                ],
            ),
            patch.object(
                replay_module,
                "_replay_sealed_audit",
                side_effect=AssertionError("replay must not start after drift"),
            ) as audit_replay,
            self.assertRaisesRegex(ValueError, "transcript changed"),
        ):
            replay_module.create_construction_snapshot_v2(
                self.legacy.spec_path,
                construction,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
                pydcs_terrain="fixture",
                created_utc=legacy_fixtures.CREATED,
            )

        audit_replay.assert_not_called()
        self.assertFalse(construction.exists())

    def test_writer_rejects_repository_internal_output_before_writing(self) -> None:
        dcs = self.root / "repository-root-check" / "DCS"
        cache = self.root / "repository-root-check" / "upstream"
        evidence = self.root / "repository-root-check" / "evidence"
        dcs.mkdir(parents=True)
        (cache / "pydcs").mkdir(parents=True)
        (cache / "briefing-room-for-dcs").mkdir()
        evidence.mkdir()
        repository = Path(replay_module.__file__).resolve().parents[2]
        construction = repository / f".construction-test-{self.root.name}"
        self.assertFalse(construction.exists())

        with (
            patch.object(
                legacy_module,
                "_producer_record",
                return_value=copy.deepcopy(self.legacy.producer),
            ),
            patch.object(
                transcript_module,
                "capture_live_audit",
                side_effect=AssertionError("audit must not start"),
            ) as capture,
            self.assertRaisesRegex(ValueError, "protected input path"),
        ):
            replay_module.create_construction_snapshot_v2(
                self.legacy.spec_path,
                construction,
                evidence_bundle=evidence,
                dcs_root=dcs,
                cache_root=cache,
            )

        capture.assert_not_called()
        self.assertFalse(construction.exists())

    def test_wrong_full_producer_identity_never_touches_replay(self) -> None:
        wrong = copy.deepcopy(self.legacy.producer)
        wrong["version"] = f"{wrong['version']}-different"
        with (
            patch.object(
                legacy_module,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.legacy.evidence_verification),
            ),
            patch.object(legacy_module, "_producer_record", return_value=wrong),
            patch.object(
                replay_module,
                "_replay_sealed_audit",
                side_effect=AssertionError("audit replay must not run"),
            ) as audit_replay,
            patch.object(
                legacy_module,
                "_replay_construction",
                side_effect=AssertionError("construction replay must not run"),
            ) as construction_replay,
        ):
            report = replay_module.verify_construction_bundle(self.bundle)

        audit_replay.assert_not_called()
        construction_replay.assert_not_called()
        validation = report["validation"]
        self.assertFalse(validation["replay_producer_matches"])
        self.assertFalse(validation["audit_decision_replay_performed"])
        self.assertIsNone(validation["audit_decision_replay_passed"])
        self.assertFalse(validation["artifact_rebuild_performed"])
        self.assertIsNone(validation["artifact_rebuilt_exact"])
        self.assertFalse(validation["verification_replay_performed"])
        self.assertIsNone(validation["verification_replayed"])
        self.assertFalse(validation["fully_reproducible"])
        self.assertFalse(validation["static_release_ready"])

    def test_exact_producer_audit_mismatch_stops_construction_replay(self) -> None:
        mismatch = copy.deepcopy(self.audit_intrinsic)
        mismatch["warnings"] = [
            {"id": "replay", "code": "synthetic_transcript_mismatch"}
        ]
        with (
            patch.object(
                legacy_module,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.legacy.evidence_verification),
            ),
            patch.object(
                legacy_module,
                "_producer_record",
                return_value=copy.deepcopy(self.legacy.producer),
            ),
            patch.object(
                replay_module,
                "_replay_sealed_audit",
                return_value=(mismatch, True),
            ) as audit_replay,
            patch.object(
                legacy_module,
                "_replay_construction",
                side_effect=AssertionError("build replay must remain gated"),
            ) as construction_replay,
        ):
            report = replay_module.verify_construction_bundle(self.bundle)

        audit_replay.assert_called_once()
        construction_replay.assert_not_called()
        validation = report["validation"]
        self.assertTrue(validation["audit_decision_replay_performed"])
        self.assertFalse(validation["audit_decision_replay_passed"])
        self.assertFalse(validation["artifact_rebuild_performed"])
        self.assertIsNone(validation["artifact_rebuilt_exact"])
        self.assertFalse(validation["verification_replay_performed"])
        self.assertIsNone(validation["verification_replayed"])
        self.assertFalse(validation["fully_reproducible"])

    def test_sealed_audit_replay_uses_missing_authority_roots(self) -> None:
        root = self.root / "offline-audit"
        dcs = root / "DCS"
        pydcs = root / "pydcs"
        briefingroom = root / "briefing-room"
        audit_fixtures.BuildSpecEvidenceAuditTests._write_sources(dcs, pydcs)
        audit_fixtures.BuildSpecEvidenceAuditTests._write_br_sources(briefingroom)
        spec_path = root / "sealed-name.json"
        spec_path.write_text(
            json.dumps(audit_fixtures._parking_spec()), encoding="utf-8"
        )
        spec, spec_payload, resources, ledger = legacy_module._capture_inputs(spec_path)
        report, valid, transcript = transcript_module.capture_live_audit(
            spec_path,
            dcs_root=dcs,
            installed_terrain="FixtureTerrain",
            pydcs_root=pydcs,
            pydcs_terrain="fixture",
            br_root=briefingroom,
            require_acknowledged_upstreams=True,
        )
        query = {
            "installed_terrain": "FixtureTerrain",
            "pydcs_terrain": "fixture",
        }

        original_replay = transcript_module.replay_audit
        checked_missing_roots: list[Path] = []

        def replay_with_missing_roots(*args: object, **kwargs: object):
            for name in ("dcs_root", "pydcs_root", "br_root"):
                authority_root = kwargs[name]
                self.assertIsInstance(authority_root, Path)
                self.assertFalse(authority_root.exists())
                checked_missing_roots.append(authority_root)
            self.assertEqual(kwargs["_resource_overrides"], {})
            return original_replay(*args, **kwargs)

        with (
            patch.object(
                transcript_module,
                "replay_audit",
                side_effect=replay_with_missing_roots,
            ),
            patch.object(
                spec_audit_module._LiveAuditQueryProvider,
                "_query_canonical",
                side_effect=AssertionError("live collector must not run"),
            ) as live_collector,
        ):
            replayed, replayed_valid = replay_module._replay_sealed_audit(
                transcript_payload=(
                    transcript_module.canonical_audit_transcript_bytes(transcript)
                ),
                spec_payload=spec_payload,
                spec_basename=spec.path.name,
                resources=ledger,
                resource_payloads=resources,
                query=query,
            )

        self.assertIs(replayed_valid, valid)
        self.assertEqual(
            legacy_module._canonical_bytes(replayed),
            legacy_module._canonical_bytes(report),
        )
        self.assertEqual(len(checked_missing_roots), 3)
        live_collector.assert_not_called()

    def test_v1_dispatch_delegates_to_original_verifier(self) -> None:
        sentinel = {"schema": legacy_module.CONSTRUCTION_VERIFICATION_SCHEMA}
        with patch.object(
            legacy_module,
            "verify_construction_bundle",
            return_value=sentinel,
        ) as original:
            report = replay_module.verify_construction_bundle(self.legacy.bundle)

        self.assertIs(report, sentinel)
        original.assert_called_once_with(self.legacy.bundle)

    def test_strict_query_gate_dag_and_transcript_hashes_are_rejected(self) -> None:
        mutations = []

        query = copy.deepcopy(self.manifest)
        query["query"]["require_acknowledged_upstreams"] = False
        mutations.append(("query", query))

        gate = copy.deepcopy(self.manifest)
        gate["gate"]["audit_decision_replay_passed"] = False
        mutations.append(("gate", gate))

        dag = copy.deepcopy(self.manifest)
        dag["nodes"][0]["transcript_sha256"] = "0" * 64
        mutations.append(("dag", dag))

        binding = copy.deepcopy(self.manifest)
        binding["bindings"]["audit_transcript"]["schema"] = (
            "dcsmizzer.audit-evidence-transcript/v999"
        )
        mutations.append(("binding", binding))

        for label, manifest in mutations:
            with self.subTest(label=label):
                bundle = self._write_readdressed(label, manifest, self.objects)
                with self.assertRaises(ValueError):
                    self._verify(bundle)

    def test_tampered_and_unused_transcript_objects_are_rejected(self) -> None:
        tampered = self.root / "tampered" / self.bundle.name
        tampered.parent.mkdir()
        shutil.copytree(self.bundle, tampered)
        transcript_sha = self.manifest["bindings"]["audit_transcript"]["sha256"]
        (tampered / "objects" / transcript_sha).write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self._verify(tampered)

        transcript = json.loads(self.transcript_payload)
        transcript["responses"].append(copy.deepcopy(transcript["responses"][0]))
        invalid_payload = json.dumps(
            transcript,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        manifest = copy.deepcopy(self.manifest)
        objects = copy.deepcopy(self.objects)
        self._replace_transcript(manifest, objects, invalid_payload)
        unused = self._write_readdressed("unused", manifest, objects)
        with self.assertRaises(ValueError):
            self._verify(unused)

    def test_safe_basename_rejects_hostile_windows_names(self) -> None:
        for hostile in (
            "a\x00.json",
            "C:spec.json",
            "a/b.json",
            "a\\b.json",
            "a?.json",
            "spec.json ",
            "spec.",
            "CON",
            "nul.json",
            "COM1.txt",
            "LPT¹.json",
            "x" * 256,
            "\ud800.json",
        ):
            with self.subTest(hostile=repr(hostile)), self.assertRaises(ValueError):
                replay_module._safe_basename(hostile)

    def test_sealed_inputs_isolate_colliding_spec_names(self) -> None:
        for basename in ("built.miz", "resource-000.bin"):
            with self.subTest(basename=basename), replay_module._sealed_inputs(
                spec_payload=self.legacy.spec_payload,
                spec_basename=basename,
                resources=copy.deepcopy(self.legacy.resource_ledger),
                resource_payloads=copy.deepcopy(self.legacy.resource_payloads),
            ) as (root, spec_path, overrides):
                self.assertEqual(spec_path.parent.name, "spec")
                self.assertEqual(spec_path.name, basename)
                self.assertEqual(
                    {path.parent.name for path in overrides.values()}, {"resources"}
                )
                self.assertNotEqual(spec_path.parent, root)

    def _verify(self, bundle: Path) -> dict[str, object]:
        with (
            patch.object(
                legacy_module,
                "verify_evidence_bundle",
                return_value=copy.deepcopy(self.legacy.evidence_verification),
            ),
            patch.object(
                legacy_module,
                "_producer_record",
                return_value=copy.deepcopy(self.legacy.producer),
            ),
            patch.object(
                replay_module,
                "_replay_sealed_audit",
                return_value=(copy.deepcopy(self.audit_intrinsic), True),
            ),
            patch.object(
                legacy_module,
                "_replay_construction",
                return_value=(True, True),
            ),
        ):
            return replay_module.verify_construction_bundle(bundle)

    def _write_bundle(
        self,
        label: str,
        manifest: dict[str, object],
        objects: dict[str, bytes],
    ) -> Path:
        bundle = self.root / label / manifest["bundle"]["id"]
        object_root = bundle / "objects"
        evidence_root = bundle / "evidence" / manifest["evidence_anchor"]["bundle_id"]
        object_root.mkdir(parents=True)
        evidence_root.mkdir(parents=True)
        for digest, payload in objects.items():
            (object_root / digest).write_bytes(payload)
        (bundle / "manifest.json").write_bytes(legacy_module._canonical_bytes(manifest))
        return bundle

    def _write_readdressed(
        self,
        label: str,
        manifest: dict[str, object],
        objects: dict[str, bytes],
    ) -> Path:
        core = dict(manifest)
        core.pop("bundle")
        manifest["bundle"]["id"] = legacy_module._sha256(
            legacy_module._canonical_bytes(core)
        )
        return self._write_bundle(label, manifest, objects)

    def _replace_transcript(
        self,
        manifest: dict[str, object],
        objects: dict[str, bytes],
        payload: bytes,
    ) -> None:
        old = manifest["bindings"]["audit_transcript"]["sha256"]
        new = legacy_module._sha256(payload)
        objects.pop(old)
        objects[new] = payload
        manifest["bindings"]["audit_transcript"]["sha256"] = new
        manifest["objects"] = [
            item for item in manifest["objects"] if item["sha256"] != old
        ]
        manifest["objects"].append(
            {
                "sha256": new,
                "relative_path": f"objects/{new}",
                "size_bytes": len(payload),
                "media_types": [replay_module._TRANSCRIPT_MEDIA_TYPE],
            }
        )
        manifest["objects"].sort(key=lambda item: item["sha256"])
        manifest["nodes"] = replay_module._pipeline_nodes_v2(
            manifest["bindings"],
            manifest["evidence_anchor"],
            manifest["command"]["query_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
