"""Replayable v2 construction bundles with sealed audit evidence."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import audit_transcript as transcripts
from . import construction_provenance as v1
from .builder import SPEC_SCHEMA, build_miz, verify_miz
from .report_provenance import attach_report_evidence_ref, intrinsic_report_sha256

CONSTRUCTION_BUNDLE_SCHEMA = "dcsmizzer.construction-bundle/v2"
CONSTRUCTION_SNAPSHOT_SCHEMA = "dcsmizzer.construction-snapshot/v2"
CONSTRUCTION_VERIFICATION_SCHEMA = "dcsmizzer.construction-verification/v2"
CONSTRUCTION_QUERY_SCHEMA = "dcsmizzer.construction-query/v2"
CONSTRUCTION_COMMAND = "construction-snapshot"
_TRANSCRIPT_MEDIA_TYPE = "application/vnd.dcsmizzer.audit-evidence-transcript+json"
_WINDOWS_RESERVED_BASENAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{suffix}" for suffix in (*range(1, 10), "¹", "²", "³")),
    *(f"lpt{suffix}" for suffix in (*range(1, 10), "¹", "²", "³")),
}


def create_construction_snapshot_v2(
    spec_path: Path,
    construction_root: Path,
    *,
    evidence_bundle: Path,
    dcs_root: Path,
    cache_root: Path,
    installed_terrain: str | None = None,
    pydcs_terrain: str | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """Capture, replay, build, verify, and seal one strict v2 construction."""

    repository = Path(__file__).resolve().parents[2]
    producer_before = v1._producer_record(repository)
    v1._require_reproducible_producer(producer_before)
    dcs = v1.canonical_existing_directory(Path(dcs_root), "construction DCS root")
    cache = v1.canonical_existing_directory(
        Path(cache_root), "construction upstream cache"
    )
    pydcs_root = v1.canonical_existing_directory(
        cache / "pydcs", "construction pydcs root"
    )
    br_root = v1.canonical_existing_directory(
        cache / "briefing-room-for-dcs", "construction BriefingRoom root"
    )
    evidence = v1.canonical_existing_directory(
        Path(evidence_bundle), "construction evidence bundle"
    )
    output_candidate = v1._construction_root_candidate(
        Path(construction_root),
        protected=(repository, dcs, cache, pydcs_root, br_root, evidence),
    )

    spec, spec_payload, resource_payloads, resource_ledger = v1._capture_inputs(
        Path(spec_path)
    )
    v1._reject_construction_root_overlap(
        output_candidate,
        (spec.path, *(resource.source for resource in spec.resources)),
    )
    if v1.audit_spec_dependencies(spec)["gci"]:
        raise ValueError(
            "construction snapshots with GCI stations require an evidence "
            "domain that is not implemented"
        )
    mandatory_domains = tuple(
        sorted(
            {
                *v1._AUDIT_BASE_DOMAINS,
                *({"airfields"} if installed_terrain is not None else set()),
            }
        )
    )
    query = {
        "schema": CONSTRUCTION_QUERY_SCHEMA,
        "spec_sha256": spec.sha256,
        "resources": resource_ledger,
        "installed_terrain": installed_terrain,
        "pydcs_terrain": pydcs_terrain,
        "resolved_pydcs_terrain": pydcs_terrain or spec.theatre,
        "resolved_briefingroom_terrain": spec.theatre,
        "briefingroom_enabled": True,
        "require_acknowledged_upstreams": True,
        "mandatory_domains": list(mandatory_domains),
    }
    query_sha256 = v1._sha256(v1._canonical_bytes(query))
    context_before = v1.current_report_evidence_context(
        evidence,
        dcs,
        report_command=CONSTRUCTION_COMMAND,
        query_sha256=query_sha256,
        mandatory_domains=mandatory_domains,
        source_roots_matched=True,
        cache_root=cache,
        required_domains=mandatory_domains,
    )
    v1._require_context_producer(context_before)

    first_audit, first_valid, first_transcript = transcripts.capture_live_audit(
        spec.path,
        dcs_root=dcs,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=True,
    )
    second_audit, second_valid, second_transcript = transcripts.capture_live_audit(
        spec.path,
        dcs_root=dcs,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=True,
    )
    transcript_payload = transcripts.canonical_audit_transcript_bytes(first_transcript)
    if (
        first_valid is not second_valid
        or v1._canonical_bytes(first_audit) != v1._canonical_bytes(second_audit)
        or transcript_payload
        != transcripts.canonical_audit_transcript_bytes(second_transcript)
    ):
        raise ValueError(
            "construction audit or transcript changed between stable passes"
        )
    v1._require_build_spec_unchanged(spec)
    v1._confirm_inputs(spec.path, spec_payload, resource_ledger)
    if not first_valid:
        return _failed_snapshot_report(
            first_audit,
            context_before,
            producer_before,
            reason="audit_checks_failed",
            audit_replay_passed=None,
        )

    replayed_audit, replayed_valid = _replay_sealed_audit(
        transcript_payload=transcript_payload,
        spec_payload=spec_payload,
        spec_basename=_audit_spec_basename(first_audit),
        resources=resource_ledger,
        resource_payloads=resource_payloads,
        query=query,
    )
    if replayed_valid is not True or v1._canonical_bytes(
        replayed_audit
    ) != v1._canonical_bytes(first_audit):
        raise ValueError("sealed construction audit replay did not match capture")

    build_report, built, verify_report, verified, artifact_payload = (
        _build_and_verify_sealed(
            spec_payload=spec_payload,
            spec_basename=_audit_spec_basename(first_audit),
            resources=resource_ledger,
            resource_payloads=resource_payloads,
        )
    )
    if not built:
        return _failed_snapshot_report(
            build_report,
            context_before,
            producer_before,
            reason="build_checks_failed",
            audit_replay_passed=True,
        )
    assert verify_report is not None and artifact_payload is not None
    if not verified:
        return _failed_snapshot_report(
            verify_report,
            context_before,
            producer_before,
            reason="verify_checks_failed",
            audit_replay_passed=True,
        )
    v1._validate_pipeline_continuity(
        spec.sha256,
        resource_ledger,
        build_report,
        verify_report,
    )
    if v1._sha256(artifact_payload) != build_report["artifact_sha256"]:
        raise ValueError("construction artifact changed after verification")

    context_after = v1.current_report_evidence_context(
        evidence,
        dcs,
        report_command=CONSTRUCTION_COMMAND,
        query_sha256=query_sha256,
        mandatory_domains=mandatory_domains,
        source_roots_matched=True,
        cache_root=cache,
        required_domains=mandatory_domains,
    )
    v1._require_context_producer(context_after)
    if v1._canonical_bytes(context_before) != v1._canonical_bytes(context_after):
        raise ValueError("construction evidence changed during the pipeline")
    v1._require_build_spec_unchanged(spec)
    v1._confirm_inputs(spec.path, spec_payload, resource_ledger)
    producer_after = v1._producer_record(repository)
    if producer_after != producer_before:
        raise ValueError("construction producer changed during the pipeline")

    bound_audit = attach_report_evidence_ref(
        first_audit,
        context_after["reference"],
        command_succeeded=True,
    )
    manifest, object_payloads = _construction_manifest_v2(
        created_utc=v1._timestamp(created_utc),
        producer=producer_after,
        query=query,
        query_sha256=query_sha256,
        spec_payload=spec_payload,
        resource_payloads=resource_payloads,
        resource_ledger=resource_ledger,
        transcript_payload=transcript_payload,
        audit_report=bound_audit,
        build_report=build_report,
        verify_report=verify_report,
        artifact_payload=artifact_payload,
        evidence_context=context_after,
    )

    output_root, root_created, root_identity = v1._create_construction_root(
        output_candidate
    )
    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=v1._STAGING_PREFIX, dir=output_root))
        _populate_staging_v2(
            staging,
            manifest,
            object_payloads,
            source_evidence_bundle=evidence,
        )
        final = output_root / manifest["bundle"]["id"]
        reused = _publish_staging_v2(output_root, staging, final)
        staging = None
        verified_bundle = verify_construction_bundle(final)
        validation = verified_bundle["validation"]
        if (
            validation["audit_decision_replay_passed"] is not True
            or validation["artifact_rebuilt_exact"] is not True
            or validation["verification_replayed"] is not True
        ):
            raise ValueError("published construction bundle did not replay exactly")
        return {
            "schema": CONSTRUCTION_SNAPSHOT_SCHEMA,
            "dcs_started": False,
            "bundle": {
                "id": manifest["bundle"]["id"],
                "directory_name": manifest["bundle"]["id"],
                "manifest_sha256": v1._sha256(v1._canonical_bytes(manifest)),
                "root": "<caller-supplied-construction-root>",
                "reused_existing_identical_bundle": reused,
            },
            "artifact": manifest["bindings"]["artifact"],
            "producer": producer_after,
            "evidence": {
                "bundle_id": context_after["reference"]["bundle"]["id"],
                "status": context_after["reference"]["status"],
                "required_domains": context_after["reference"]["required_domains"],
            },
            "privacy": manifest["privacy"],
            "recorded_gate": manifest["gate"],
            "validation": {
                "bundle_valid": True,
                "pipeline_complete": True,
                "audit_passed": True,
                "audit_decision_replay_available": True,
                "audit_decision_replay_performed": True,
                "audit_decision_replay_passed": True,
                "build_passed": True,
                "verify_passed": True,
                "artifact_rebuild_performed": True,
                "artifact_rebuilt_exact": True,
                "verification_replay_performed": True,
                "verification_replayed": True,
                "replay_toolchain_matches": True,
                "replay_producer_matches": True,
                "fully_reproducible": True,
                "evidence_ready_for_static_release": manifest["gate"][
                    "evidence_ready_for_static_release"
                ],
                "static_release_ready": manifest["gate"]["static_release_ready"],
                "runtime_valid": None,
            },
        }
    finally:
        if staging is not None and staging.exists():
            v1._remove_staging(staging, output_root)
        if root_created:
            v1._remove_empty_created_root(output_root, root_identity)


# The v2 module's default writer intentionally never emits v1.
create_construction_snapshot = create_construction_snapshot_v2


def verify_construction_bundle(bundle_path: Path) -> dict[str, Any]:
    """Dispatch v1 unchanged and verify v2 with strict offline replay."""

    try:
        schema = _peek_bundle_schema(Path(bundle_path))
        if schema == v1.CONSTRUCTION_BUNDLE_SCHEMA:
            return v1.verify_construction_bundle(Path(bundle_path))
        if schema != CONSTRUCTION_BUNDLE_SCHEMA:
            raise ValueError("unsupported construction bundle schema")
        return _verify_construction_bundle_v2(Path(bundle_path))
    except (
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
        RecursionError,
        StopIteration,
        TypeError,
    ) as error:
        raise ValueError("construction bundle has an invalid nested shape") from error


def _peek_bundle_schema(bundle_path: Path) -> str | None:
    bundle = v1.canonical_existing_directory(bundle_path, "construction bundle")
    v1._validate_root_members(bundle)
    manifest_path = v1.canonical_existing_file(
        bundle / "manifest.json", "construction manifest"
    )
    raw = v1._read_exact_regular_file(
        manifest_path,
        maximum_bytes=v1.MAX_CONSTRUCTION_MANIFEST_BYTES,
        label="construction manifest",
    )
    manifest = v1._parse_report_json(raw)
    if raw != v1._canonical_bytes(manifest):
        raise ValueError("construction manifest is not canonical JSON")
    return manifest.get("schema") if isinstance(manifest, dict) else None


def _verify_construction_bundle_v2(bundle_path: Path) -> dict[str, Any]:
    bundle = v1.canonical_existing_directory(bundle_path, "construction bundle")
    v1._validate_root_members(bundle)
    raw_manifest = v1._read_exact_regular_file(
        v1.canonical_existing_file(bundle / "manifest.json", "construction manifest"),
        maximum_bytes=v1.MAX_CONSTRUCTION_MANIFEST_BYTES,
        label="construction manifest",
    )
    manifest = v1._parse_report_json(raw_manifest)
    if raw_manifest != v1._canonical_bytes(manifest):
        raise ValueError("construction manifest is not canonical JSON")
    _validate_manifest_v2(manifest, directory_name=bundle.name)

    object_payloads = _read_objects(bundle, manifest)
    bindings = manifest["bindings"]
    spec_payload = v1._bound_object(object_payloads, bindings["spec"]["sha256"])
    if v1._sha256(spec_payload) != bindings["spec"]["original_sha256"]:
        raise ValueError("construction spec binding does not match")
    v1._validate_sealed_spec(spec_payload, bindings, manifest["query"])
    audit_report = v1._bound_json_report(object_payloads, bindings["reports"]["audit"])
    build_report = v1._bound_json_report(object_payloads, bindings["reports"]["build"])
    verify_report = v1._bound_json_report(
        object_payloads, bindings["reports"]["verify"]
    )
    readiness = v1._bound_json_report(
        object_payloads, bindings["evidence_preimages"]["readiness"]
    )
    evidence_verification = v1._bound_json_report(
        object_payloads, bindings["evidence_preimages"]["verification"]
    )
    transcript_payload = v1._bound_object(
        object_payloads, bindings["audit_transcript"]["sha256"]
    )
    transcripts.parse_audit_transcript(transcript_payload)

    v1._validate_bound_audit_report(audit_report, manifest)
    v1._validate_pipeline_continuity(
        bindings["spec"]["original_sha256"],
        bindings["resources"],
        build_report,
        verify_report,
    )
    artifact_payload = v1._bound_object(object_payloads, bindings["artifact"]["sha256"])
    if (
        len(artifact_payload) != bindings["artifact"]["size_bytes"]
        or v1._sha256(artifact_payload) != build_report["artifact_sha256"]
    ):
        raise ValueError("construction artifact binding does not match")
    v1._validate_evidence_anchor(bundle, manifest, readiness, evidence_verification)
    _validate_node_dag_v2(manifest)

    current_producer = v1._producer_record(Path(__file__).resolve().parents[2])
    replay_toolchain = (
        current_producer.get("toolchain") == manifest["producer"]["toolchain"]
    )
    replay_producer = current_producer == manifest["producer"]
    audit_performed = False
    audit_passed: bool | None = None
    artifact_exact: bool | None = None
    verification_replayed: bool | None = None
    fully_reproducible = False
    artifact_rebuild_performed = False
    verification_replay_performed = False
    if replay_producer:
        audit_performed = True
        replayed_audit, replayed_valid = _replay_sealed_audit(
            transcript_payload=transcript_payload,
            spec_payload=spec_payload,
            spec_basename=_audit_spec_basename(audit_report),
            resources=bindings["resources"],
            resource_payloads={
                item["member"]: v1._bound_object(object_payloads, item["object_sha256"])
                for item in bindings["resources"]
            },
            query=manifest["query"],
        )
        intrinsic_audit = dict(audit_report)
        intrinsic_audit.pop("evidence_ref", None)
        audit_passed = bool(
            replayed_valid
            and v1._canonical_bytes(replayed_audit)
            == v1._canonical_bytes(intrinsic_audit)
        )
        if audit_passed:
            artifact_rebuild_performed = True
            verification_replay_performed = True
            artifact_exact, verification_replayed = v1._replay_construction(
                spec_payload,
                artifact_payload,
                bindings["resources"],
                object_payloads,
            )
            fully_reproducible = bool(artifact_exact and verification_replayed)

    return {
        "schema": CONSTRUCTION_VERIFICATION_SCHEMA,
        "dcs_started": False,
        "bundle": {
            "id": manifest["bundle"]["id"],
            "directory_name": bundle.name,
            "manifest_sha256": v1._sha256(raw_manifest),
        },
        "producer": manifest["producer"],
        "artifact": bindings["artifact"],
        "evidence": manifest["evidence_anchor"],
        "recorded_gate": manifest["gate"],
        "privacy": {
            "absolute_paths_echoed": False,
            "objects_opened": len(object_payloads),
            "objects_may_contain_private_data": True,
            "trusted_directory_required": True,
        },
        "validation": {
            "bundle_valid": True,
            "content_address_valid": True,
            "all_objects_present": True,
            "all_object_hashes_valid": True,
            "node_dag_valid": True,
            "embedded_evidence_valid": True,
            "report_bindings_valid": True,
            "transcript_binding_valid": True,
            "pipeline_continuity_valid": True,
            "replay_toolchain_matches": replay_toolchain,
            "replay_producer_matches": replay_producer,
            "audit_decision_replay_available": True,
            "audit_decision_replay_performed": audit_performed,
            "audit_decision_replay_passed": audit_passed,
            "artifact_rebuild_performed": artifact_rebuild_performed,
            "artifact_rebuilt_exact": artifact_exact,
            "verification_replay_performed": verification_replay_performed,
            "verification_replayed": verification_replayed,
            "fully_reproducible": fully_reproducible,
            # A historical verification is evidence, not a new release gate.
            "static_release_ready": False,
            "runtime_valid": None,
        },
        "limitations": [
            "The bundle is content-addressed and tamper-evident, not signed.",
            (
                "Audit, build, and verification replay require the exact full "
                "recorded producer identity."
            ),
            "Historical verification does not itself reopen the recorded gate.",
            "Static validity never implies DCS load, smoke, or playability.",
        ],
    }


def _read_objects(bundle: Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    objects_dir = v1.canonical_existing_directory(
        bundle / "objects", "construction object directory"
    )
    expected_names = {record["sha256"] for record in manifest["objects"]}
    records = {record["sha256"]: record for record in manifest["objects"]}
    items = v1._bounded_directory_entries(
        objects_dir,
        maximum_entries=len(expected_names),
        label="construction object directory",
    )
    if set(items) != expected_names:
        raise ValueError("construction bundle has missing or unexpected objects")
    payloads: dict[str, bytes] = {}
    total = 0
    for name, item in items.items():
        path = v1.canonical_existing_file(item, "construction object")
        if path.name != name or not v1._is_hash(name):
            raise ValueError("construction object has an invalid name")
        payload = v1._read_exact_regular_file(
            path,
            maximum_bytes=v1.MAX_CONSTRUCTION_OBJECT_BYTES,
            label="construction object",
        )
        total += len(payload)
        if total > v1.MAX_CONSTRUCTION_TOTAL_BYTES:
            raise ValueError("construction objects exceed the total byte limit")
        if len(payload) != records[name]["size_bytes"] or v1._sha256(payload) != name:
            raise ValueError("construction object size or hash does not match")
        payloads[name] = payload
    return payloads


@contextmanager
def _sealed_inputs(
    *,
    spec_payload: bytes,
    spec_basename: str,
    resources: list[dict[str, Any]],
    resource_payloads: dict[str, bytes],
) -> Iterator[tuple[Path, Path, dict[str, Path]]]:
    basename = _safe_basename(spec_basename)
    with tempfile.TemporaryDirectory(prefix="dcsmizzer-construction-v2-") as temp:
        root = Path(temp)
        spec_root = root / "spec"
        resource_root = root / "resources"
        spec_root.mkdir()
        resource_root.mkdir()
        spec_path = spec_root / basename
        v1._write_new_file(spec_path, spec_payload)
        overrides: dict[str, Path] = {}
        for index, item in enumerate(resources):
            member = item["member"]
            payload = resource_payloads.get(member)
            if payload is None:
                raise ValueError("sealed construction resource is unavailable")
            if (
                len(payload) != item["size_bytes"]
                or v1._sha256(payload) != item["sha256"]
            ):
                raise ValueError("sealed construction resource binding changed")
            path = resource_root / f"resource-{index:03d}.bin"
            v1._write_new_file(path, payload)
            overrides[member] = path
        yield root, spec_path, overrides


def _replay_sealed_audit(
    *,
    transcript_payload: bytes,
    spec_payload: bytes,
    spec_basename: str,
    resources: list[dict[str, Any]],
    resource_payloads: dict[str, bytes],
    query: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    transcript = transcripts.parse_audit_transcript(transcript_payload)
    with _sealed_inputs(
        spec_payload=spec_payload,
        spec_basename=spec_basename,
        resources=resources,
        resource_payloads=resource_payloads,
    ) as (root, sealed_spec, overrides):
        return transcripts.replay_audit(
            transcript,
            sealed_spec,
            dcs_root=root / "missing-dcs-authority",
            installed_terrain=query["installed_terrain"],
            pydcs_root=root / "missing-pydcs-authority",
            pydcs_terrain=query["pydcs_terrain"],
            br_root=root / "missing-briefingroom-authority",
            require_acknowledged_upstreams=True,
            _resource_overrides=overrides,
        )


def _build_and_verify_sealed(
    *,
    spec_payload: bytes,
    spec_basename: str,
    resources: list[dict[str, Any]],
    resource_payloads: dict[str, bytes],
) -> tuple[
    dict[str, Any],
    bool,
    dict[str, Any] | None,
    bool,
    bytes | None,
]:
    with _sealed_inputs(
        spec_payload=spec_payload,
        spec_basename=spec_basename,
        resources=resources,
        resource_payloads=resource_payloads,
    ) as (root, sealed_spec, overrides):
        output_root = root / "output"
        output_root.mkdir()
        artifact = output_root / "built.miz"
        build_report, built = build_miz(
            sealed_spec, artifact, resource_overrides=overrides
        )
        if not built:
            return build_report, False, None, False, None
        artifact_payload = v1._read_exact_regular_file(
            artifact,
            maximum_bytes=v1.MAX_CONSTRUCTION_OBJECT_BYTES,
            label="construction MIZ artifact",
        )
        verify_report, verified = verify_miz(
            artifact, sealed_spec, resource_overrides=overrides
        )
        return build_report, True, verify_report, verified, artifact_payload


def _audit_spec_basename(report: dict[str, Any]) -> str:
    value = report.get("input_spec") if isinstance(report, dict) else None
    return _safe_basename(value)


def _safe_basename(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
    ):
        raise ValueError("construction audit input basename is invalid")
    try:
        utf16_code_units = len(value.encode("utf-16-le")) // 2
    except UnicodeEncodeError as error:
        raise ValueError("construction audit input basename is invalid") from error
    if (
        value.endswith((".", " "))
        or utf16_code_units > 255
        or any(
            ord(character) < 32 or character in '<>:"/\\|?*'
            for character in value
        )
        or value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_BASENAMES
        or Path(value).name != value
    ):
        raise ValueError("construction audit input basename is invalid")
    return value


def _construction_manifest_v2(
    *,
    created_utc: str,
    producer: dict[str, Any],
    query: dict[str, Any],
    query_sha256: str,
    spec_payload: bytes,
    resource_payloads: dict[str, bytes],
    resource_ledger: list[dict[str, Any]],
    transcript_payload: bytes,
    audit_report: dict[str, Any],
    build_report: dict[str, Any],
    verify_report: dict[str, Any],
    artifact_payload: bytes,
    evidence_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    transcript = transcripts.parse_audit_transcript(transcript_payload)
    if transcript_payload != transcripts.canonical_audit_transcript_bytes(transcript):
        raise ValueError("construction audit transcript is not canonical")
    store: dict[str, bytes] = {}
    media: dict[str, set[str]] = {}

    def add(payload: bytes, media_type: str) -> str:
        if not 0 <= len(payload) <= v1.MAX_CONSTRUCTION_OBJECT_BYTES:
            raise ValueError("construction object exceeds its size boundary")
        digest = v1._sha256(payload)
        existing = store.setdefault(digest, payload)
        if existing != payload:
            raise ValueError("construction object hash collision")
        media.setdefault(digest, set()).add(media_type)
        return digest

    spec_sha = add(spec_payload, "application/vnd.dcsmizzer.build-spec+json")
    resources: list[dict[str, Any]] = []
    for item in resource_ledger:
        payload = resource_payloads[item["member"]]
        digest = add(payload, "application/octet-stream")
        if digest != item["sha256"] or len(payload) != item["size_bytes"]:
            raise ValueError("construction resource ledger changed")
        resources.append({**item, "object_sha256": digest})
    transcript_sha = add(transcript_payload, _TRANSCRIPT_MEDIA_TYPE)
    report_bindings: dict[str, dict[str, Any]] = {}
    for name, report in (
        ("audit", audit_report),
        ("build", build_report),
        ("verify", verify_report),
    ):
        payload = v1._canonical_bytes(report)
        digest = add(payload, "application/vnd.dcsmizzer.report+json")
        report_bindings[name] = {
            "sha256": digest,
            "schema": report["schema"],
            "intrinsic_sha256": intrinsic_report_sha256(report),
        }
    readiness_payload = v1._canonical_bytes(evidence_context["readiness"])
    readiness_sha = add(
        readiness_payload, "application/vnd.dcsmizzer.evidence-readiness+json"
    )
    verification_payload = v1._canonical_bytes(evidence_context["verification"])
    evidence_verification_sha = add(
        verification_payload,
        "application/vnd.dcsmizzer.evidence-verification+json",
    )
    artifact_sha = add(artifact_payload, "application/vnd.dcs.miz")
    if artifact_sha != build_report["artifact_sha256"]:
        raise ValueError("construction artifact report binding changed")
    objects = [
        {
            "sha256": digest,
            "relative_path": f"objects/{digest}",
            "size_bytes": len(payload),
            "media_types": sorted(media[digest]),
        }
        for digest, payload in sorted(store.items())
    ]
    if len(objects) > v1.MAX_CONSTRUCTION_OBJECTS:
        raise ValueError("construction bundle has too many objects")
    if sum(item["size_bytes"] for item in objects) > v1.MAX_CONSTRUCTION_TOTAL_BYTES:
        raise ValueError("construction bundle exceeds its total byte limit")

    reference = evidence_context["reference"]
    evidence_anchor = {
        "bundle_id": reference["bundle"]["id"],
        "manifest_sha256": reference["bundle"]["manifest_sha256"],
        "embedded_relative_path": f"evidence/{reference['bundle']['id']}",
        "status": reference["status"],
        "mandatory_domains": reference["report_binding"]["mandatory_domains"],
        "required_domains": reference["required_domains"],
        "domain_artifact_bindings": reference["domain_artifact_bindings"],
        "readiness_canonical_sha256": reference["current_readiness"][
            "canonical_sha256"
        ],
    }
    bindings = {
        "spec": {
            "sha256": spec_sha,
            "original_sha256": spec_sha,
            "schema": SPEC_SCHEMA,
        },
        "resources": resources,
        "audit_transcript": {
            "sha256": transcript_sha,
            "schema": transcripts.AUDIT_TRANSCRIPT_SCHEMA,
        },
        "reports": report_bindings,
        "artifact": {
            "sha256": artifact_sha,
            "size_bytes": len(artifact_payload),
            "validation_tier": "V1",
        },
        "evidence_preimages": {
            "readiness": {
                "sha256": readiness_sha,
                "schema": evidence_context["readiness"]["schema"],
                "intrinsic_sha256": readiness_sha,
            },
            "verification": {
                "sha256": evidence_verification_sha,
                "schema": evidence_context["verification"]["schema"],
                "intrinsic_sha256": evidence_verification_sha,
            },
        },
    }
    nodes = _pipeline_nodes_v2(bindings, evidence_anchor, query_sha256)
    evidence_ready = reference["validation"]["evidence_ready_for_binding"]
    core = {
        "schema": CONSTRUCTION_BUNDLE_SCHEMA,
        "stage": "verify",
        "created_utc": created_utc,
        "producer": producer,
        "command": {
            "name": CONSTRUCTION_COMMAND,
            "query_sha256": query_sha256,
        },
        "query": query,
        "evidence_anchor": evidence_anchor,
        "objects": objects,
        "bindings": bindings,
        "nodes": nodes,
        "gate": {
            "audit_passed": True,
            "audit_decision_replay_available": True,
            "audit_decision_replay_passed": True,
            "build_passed": True,
            "verify_passed": True,
            "evidence_ready_for_static_release": evidence_ready,
            "static_release_ready": bool(evidence_ready),
            "runtime_valid": None,
        },
        "privacy": {
            "local_only": True,
            "redistribution_reviewed": False,
            "manifest_contains_absolute_paths": False,
            "objects_may_contain_private_data": True,
            "cli_echoes_absolute_paths": False,
            "trusted_directory_required": True,
        },
    }
    bundle_id = v1._sha256(v1._canonical_bytes(core))
    manifest = {
        **core,
        "bundle": {
            "algorithm": "sha256",
            "id": bundle_id,
            "content_address_basis": "canonical_manifest_without_bundle_field",
        },
    }
    if len(v1._canonical_bytes(manifest)) > v1.MAX_CONSTRUCTION_MANIFEST_BYTES:
        raise ValueError("construction manifest exceeds its byte limit")
    _validate_manifest_v2(manifest, directory_name=bundle_id)
    return manifest, store


def _pipeline_nodes_v2(
    bindings: dict[str, Any],
    evidence_anchor: dict[str, Any],
    query_sha256: str,
) -> list[dict[str, Any]]:
    audit_core = {
        "stage": "audit",
        "parent_id": None,
        "query_sha256": query_sha256,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "transcript_sha256": bindings["audit_transcript"]["sha256"],
        "report_sha256": bindings["reports"]["audit"]["sha256"],
        "evidence_bundle_id": evidence_anchor["bundle_id"],
        "evidence_manifest_sha256": evidence_anchor["manifest_sha256"],
        "domain_artifact_bindings": evidence_anchor["domain_artifact_bindings"],
    }
    audit_id = v1._sha256(v1._canonical_bytes(audit_core))
    build_core = {
        "stage": "build",
        "parent_id": audit_id,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "resources": bindings["resources"],
        "report_sha256": bindings["reports"]["build"]["sha256"],
        "artifact_sha256": bindings["artifact"]["sha256"],
    }
    build_id = v1._sha256(v1._canonical_bytes(build_core))
    verify_core = {
        "stage": "verify",
        "parent_id": build_id,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "resources": bindings["resources"],
        "report_sha256": bindings["reports"]["verify"]["sha256"],
        "artifact_sha256": bindings["artifact"]["sha256"],
    }
    verify_id = v1._sha256(v1._canonical_bytes(verify_core))
    return [
        {**audit_core, "id": audit_id},
        {**build_core, "id": build_id},
        {**verify_core, "id": verify_id},
    ]


def _validate_manifest_v2(manifest: Any, *, directory_name: str) -> None:
    required = {
        "schema",
        "stage",
        "created_utc",
        "producer",
        "command",
        "query",
        "evidence_anchor",
        "objects",
        "bindings",
        "nodes",
        "gate",
        "privacy",
        "bundle",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != required
        or manifest.get("schema") != CONSTRUCTION_BUNDLE_SCHEMA
        or manifest.get("stage") != "verify"
    ):
        raise ValueError("construction v2 manifest shape or schema is invalid")
    v1._timestamp(manifest.get("created_utc"))
    v1._validate_producer(manifest.get("producer"))
    command = manifest.get("command")
    if (
        not isinstance(command, dict)
        or set(command) != {"name", "query_sha256"}
        or command.get("name") != CONSTRUCTION_COMMAND
        or not v1._is_hash(command.get("query_sha256"))
    ):
        raise ValueError("construction v2 command binding is invalid")
    query = manifest.get("query")
    if (
        not isinstance(query, dict)
        or query.get("schema") != CONSTRUCTION_QUERY_SCHEMA
        or v1._sha256(v1._canonical_bytes(query)) != command["query_sha256"]
    ):
        raise ValueError("construction v2 query binding is invalid")
    v1._validate_evidence_anchor_shape(manifest.get("evidence_anchor"))
    v1._validate_objects(manifest.get("objects"))
    _validate_bindings_v2(manifest.get("bindings"), manifest["objects"])
    _validate_query_v2(query, manifest["bindings"], manifest["evidence_anchor"])
    nodes = manifest.get("nodes")
    if not isinstance(nodes, list) or [
        item.get("stage") for item in nodes if isinstance(item, dict)
    ] != ["audit", "build", "verify"]:
        raise ValueError("construction v2 node records are invalid")
    _validate_node_dag_v2(manifest)
    gate = manifest.get("gate")
    expected_gate_keys = {
        "audit_passed",
        "audit_decision_replay_available",
        "audit_decision_replay_passed",
        "build_passed",
        "verify_passed",
        "evidence_ready_for_static_release",
        "static_release_ready",
        "runtime_valid",
    }
    if (
        not isinstance(gate, dict)
        or set(gate) != expected_gate_keys
        or gate["audit_passed"] is not True
        or gate["audit_decision_replay_available"] is not True
        or gate["audit_decision_replay_passed"] is not True
        or gate["build_passed"] is not True
        or gate["verify_passed"] is not True
        or not isinstance(gate["evidence_ready_for_static_release"], bool)
        or gate["static_release_ready"] is not gate["evidence_ready_for_static_release"]
        or gate["runtime_valid"] is not None
    ):
        raise ValueError("construction v2 gate is invalid")
    if manifest.get("privacy") != {
        "local_only": True,
        "redistribution_reviewed": False,
        "manifest_contains_absolute_paths": False,
        "objects_may_contain_private_data": True,
        "cli_echoes_absolute_paths": False,
        "trusted_directory_required": True,
    }:
        raise ValueError("construction privacy policy is invalid")
    bundle = manifest.get("bundle")
    if (
        not isinstance(bundle, dict)
        or set(bundle) != {"algorithm", "id", "content_address_basis"}
        or bundle.get("algorithm") != "sha256"
        or bundle.get("content_address_basis")
        != "canonical_manifest_without_bundle_field"
        or not v1._is_hash(bundle.get("id"))
        or directory_name != bundle["id"]
    ):
        raise ValueError("construction content address is invalid")
    core = dict(manifest)
    del core["bundle"]
    if v1._sha256(v1._canonical_bytes(core)) != bundle["id"]:
        raise ValueError("construction manifest content address does not match")


def _validate_bindings_v2(value: Any, objects: list[dict[str, Any]]) -> None:
    if not isinstance(value, dict) or set(value) != {
        "spec",
        "resources",
        "audit_transcript",
        "reports",
        "artifact",
        "evidence_preimages",
    }:
        raise ValueError("construction v2 bindings are invalid")
    transcript = value["audit_transcript"]
    known = {item["sha256"]: item for item in objects}
    if (
        not isinstance(transcript, dict)
        or set(transcript) != {"sha256", "schema"}
        or not v1._is_hash(transcript.get("sha256"))
        or transcript.get("schema") != transcripts.AUDIT_TRANSCRIPT_SCHEMA
        or transcript["sha256"] not in known
        or _TRANSCRIPT_MEDIA_TYPE not in known[transcript["sha256"]]["media_types"]
    ):
        raise ValueError("construction audit transcript binding is invalid")
    legacy = dict(value)
    del legacy["audit_transcript"]
    legacy_hashes = _legacy_binding_hashes(legacy)
    legacy_objects = [item for item in objects if item["sha256"] in legacy_hashes]
    v1._validate_bindings(legacy, legacy_objects)
    if legacy_hashes | {transcript["sha256"]} != set(known):
        raise ValueError("construction bundle contains an unbound object")


def _legacy_binding_hashes(bindings: dict[str, Any]) -> set[str]:
    return {
        bindings["spec"]["sha256"],
        *(item["object_sha256"] for item in bindings["resources"]),
        *(item["sha256"] for item in bindings["reports"].values()),
        bindings["artifact"]["sha256"],
        *(item["sha256"] for item in bindings["evidence_preimages"].values()),
    }


def _validate_query_v2(
    query: dict[str, Any],
    bindings: dict[str, Any],
    anchor: dict[str, Any],
) -> None:
    expected = {
        "schema",
        "spec_sha256",
        "resources",
        "installed_terrain",
        "pydcs_terrain",
        "resolved_pydcs_terrain",
        "resolved_briefingroom_terrain",
        "briefingroom_enabled",
        "require_acknowledged_upstreams",
        "mandatory_domains",
    }
    if set(query) != expected or query["require_acknowledged_upstreams"] is not True:
        raise ValueError("construction v2 query shape is invalid")
    legacy_query = dict(query)
    legacy_query["schema"] = "dcsmizzer.construction-query/v1"
    del legacy_query["require_acknowledged_upstreams"]
    v1._validate_query(legacy_query, bindings, anchor)


def _validate_node_dag_v2(manifest: dict[str, Any]) -> None:
    expected = _pipeline_nodes_v2(
        manifest["bindings"],
        manifest["evidence_anchor"],
        manifest["command"]["query_sha256"],
    )
    if manifest["nodes"] != expected:
        raise ValueError("construction v2 node DAG is invalid")


def _populate_staging_v2(
    staging: Path,
    manifest: dict[str, Any],
    object_payloads: dict[str, bytes],
    *,
    source_evidence_bundle: Path,
) -> None:
    objects = staging / "objects"
    objects.mkdir()
    for digest, payload in sorted(object_payloads.items()):
        v1._write_new_file(objects / digest, payload)
    evidence_root = staging / "evidence"
    evidence_root.mkdir()
    destination = evidence_root / manifest["evidence_anchor"]["bundle_id"]
    v1._copy_evidence_bundle(source_evidence_bundle, destination)
    v1._write_new_file(staging / "manifest.json", v1._canonical_bytes(manifest))
    embedded = v1.verify_evidence_bundle(destination)
    if (
        embedded["bundle"]["id"] != manifest["evidence_anchor"]["bundle_id"]
        or embedded["bundle"]["manifest_sha256"]
        != manifest["evidence_anchor"]["manifest_sha256"]
    ):
        raise ValueError("embedded evidence bundle identity changed")


def _publish_staging_v2(root: Path, staging: Path, final: Path) -> bool:
    if final.exists():
        verify_construction_bundle(final)
        v1._remove_staging(staging, root)
        return True
    try:
        os.replace(staging, final)
        return False
    except OSError:
        if not final.exists():
            raise
        verify_construction_bundle(final)
        v1._remove_staging(staging, root)
        return True


def _failed_snapshot_report(
    report: dict[str, Any],
    context: dict[str, Any],
    producer: dict[str, Any],
    *,
    reason: str,
    audit_replay_passed: bool | None,
) -> dict[str, Any]:
    audit_passed = reason != "audit_checks_failed"
    build_passed = audit_passed and reason != "build_checks_failed"
    return {
        "schema": CONSTRUCTION_SNAPSHOT_SCHEMA,
        "dcs_started": False,
        "bundle": None,
        "producer": producer,
        "evidence": {
            "bundle_id": context["reference"]["bundle"]["id"],
            "status": "unbound",
        },
        "failed_stage": {
            "schema": report.get("schema"),
            "reason": reason,
            "intrinsic_sha256": intrinsic_report_sha256(report),
        },
        "validation": {
            "bundle_valid": False,
            "pipeline_complete": False,
            "audit_passed": audit_passed,
            "audit_decision_replay_available": True,
            "audit_decision_replay_performed": audit_replay_passed is not None,
            "audit_decision_replay_passed": audit_replay_passed,
            "build_passed": build_passed,
            "verify_passed": False,
            "artifact_rebuild_performed": False,
            "artifact_rebuilt_exact": None,
            "verification_replay_performed": False,
            "verification_replayed": None,
            "fully_reproducible": False,
            "evidence_ready_for_static_release": False,
            "static_release_ready": False,
            "runtime_valid": None,
        },
    }


__all__ = [
    "CONSTRUCTION_BUNDLE_SCHEMA",
    "CONSTRUCTION_QUERY_SCHEMA",
    "CONSTRUCTION_SNAPSHOT_SCHEMA",
    "CONSTRUCTION_VERIFICATION_SCHEMA",
    "create_construction_snapshot",
    "create_construction_snapshot_v2",
    "verify_construction_bundle",
]
