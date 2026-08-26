"""Content-addressed provenance for one audited low-level MIZ construction."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .builder import (
    MAX_BUILD_SPEC_BYTES,
    SPEC_SCHEMA,
    _bound_resource_bytes,
    _close_bound_resource_inputs,
    _open_bound_resource_inputs,
    _read_bound_build_spec,
    _require_build_spec_unchanged,
    build_miz,
    load_build_spec,
    verify_miz,
)
from .evidence import (
    _domain_artifact_bindings,
    current_report_evidence_context,
    validate_evidence_readiness_report,
    verify_evidence_bundle,
)
from .path_safety import canonical_existing_directory, canonical_existing_file
from .report_provenance import (
    attach_report_evidence_ref,
    intrinsic_report_sha256,
    validate_attached_report_evidence_ref,
)
from .report_views import _parse_report_json, _read_bounded_report
from .runtime import _git_identity, _write_new_file
from .spec_audit import audit_build_spec, audit_spec_dependencies

CONSTRUCTION_BUNDLE_SCHEMA = "dcsmizzer.construction-bundle/v1"
CONSTRUCTION_SNAPSHOT_SCHEMA = "dcsmizzer.construction-snapshot/v1"
CONSTRUCTION_VERIFICATION_SCHEMA = "dcsmizzer.construction-verification/v1"
MAX_CONSTRUCTION_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_CONSTRUCTION_OBJECTS = 512
MAX_CONSTRUCTION_OBJECT_BYTES = 256 * 1024 * 1024
MAX_CONSTRUCTION_TOTAL_BYTES = 256 * 1024 * 1024
_HASH = re.compile(r"\A[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"\A[0-9a-f]{40,64}\Z")
_STAGING_PREFIX = ".dcsmizzer-construction-"
_AUDIT_BASE_DOMAINS = (
    "capabilities",
    "countries",
    "installation",
    "modules",
    "payloads",
    "upstream",
    "weather",
)


def create_construction_snapshot(
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
    """Audit, build, verify, and seal one exact construction locally."""

    repository = Path(__file__).resolve().parents[2]
    producer_before = _producer_record(repository)
    _require_reproducible_producer(producer_before)
    dcs = canonical_existing_directory(Path(dcs_root), "construction DCS root")
    cache = canonical_existing_directory(
        Path(cache_root),
        "construction upstream cache",
    )
    pydcs_root = canonical_existing_directory(
        cache / "pydcs",
        "construction pydcs root",
    )
    br_root = canonical_existing_directory(
        cache / "briefing-room-for-dcs",
        "construction BriefingRoom root",
    )
    bundle = canonical_existing_directory(
        Path(evidence_bundle),
        "construction evidence bundle",
    )
    output_candidate = _construction_root_candidate(
        Path(construction_root),
        protected=(repository, dcs, cache, pydcs_root, br_root, bundle),
    )

    spec, spec_payload, resource_payloads, resource_ledger = _capture_inputs(
        Path(spec_path)
    )
    _reject_construction_root_overlap(
        output_candidate,
        (spec.path, *(resource.source for resource in spec.resources)),
    )
    if audit_spec_dependencies(spec)["gci"]:
        raise ValueError(
            "construction snapshots with GCI stations require an evidence "
            "domain that is not implemented"
        )
    mandatory_domains = tuple(
        sorted(
            {
                *_AUDIT_BASE_DOMAINS,
                *({"airfields"} if installed_terrain is not None else set()),
            }
        )
    )
    query = {
        "schema": "dcsmizzer.construction-query/v1",
        "spec_sha256": spec.sha256,
        "resources": resource_ledger,
        "installed_terrain": installed_terrain,
        "pydcs_terrain": pydcs_terrain,
        "resolved_pydcs_terrain": pydcs_terrain or spec.theatre,
        "resolved_briefingroom_terrain": spec.theatre,
        "briefingroom_enabled": True,
        "mandatory_domains": list(mandatory_domains),
    }
    query_sha256 = _sha256(_canonical_bytes(query))
    context_before = current_report_evidence_context(
        bundle,
        dcs,
        report_command="construction-snapshot",
        query_sha256=query_sha256,
        mandatory_domains=mandatory_domains,
        source_roots_matched=True,
        cache_root=cache,
        required_domains=mandatory_domains,
    )
    _require_context_producer(context_before)

    first_audit, first_audit_valid = audit_build_spec(
        spec.path,
        dcs_root=dcs,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=True,
    )
    second_audit, second_audit_valid = audit_build_spec(
        spec.path,
        dcs_root=dcs,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=True,
    )
    if (
        first_audit_valid is not second_audit_valid
        or _canonical_bytes(first_audit) != _canonical_bytes(second_audit)
    ):
        raise ValueError("construction audit changed between stable passes")
    _require_build_spec_unchanged(spec)
    _confirm_inputs(spec.path, spec_payload, resource_ledger)
    if not first_audit_valid:
        return _failed_snapshot_report(
            first_audit,
            context_before,
            producer_before,
            reason="audit_checks_failed",
        )

    output_root, root_created, root_identity = _create_construction_root(
        output_candidate
    )
    staging: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=output_root)
        )
        artifact = staging / "work.miz"
        build_report, built = build_miz(spec.path, artifact)
        if not built:
            return _failed_snapshot_report(
                build_report,
                context_before,
                producer_before,
                reason="build_checks_failed",
            )
        verify_report, verified = verify_miz(artifact, spec.path)
        if not verified:
            return _failed_snapshot_report(
                verify_report,
                context_before,
                producer_before,
                reason="verify_checks_failed",
            )
        _validate_pipeline_continuity(
            spec.sha256,
            resource_ledger,
            build_report,
            verify_report,
        )
        artifact_payload = _read_exact_regular_file(
            artifact,
            maximum_bytes=MAX_CONSTRUCTION_OBJECT_BYTES,
            label="construction MIZ artifact",
        )
        if _sha256(artifact_payload) != build_report["artifact_sha256"]:
            raise ValueError("construction artifact changed after verification")

        context_after = current_report_evidence_context(
            bundle,
            dcs,
            report_command="construction-snapshot",
            query_sha256=query_sha256,
            mandatory_domains=mandatory_domains,
            source_roots_matched=True,
            cache_root=cache,
            required_domains=mandatory_domains,
        )
        _require_context_producer(context_after)
        if _canonical_bytes(context_before) != _canonical_bytes(context_after):
            raise ValueError("construction evidence changed during the pipeline")
        _require_build_spec_unchanged(spec)
        _confirm_inputs(spec.path, spec_payload, resource_ledger)
        producer_after = _producer_record(repository)
        if producer_after != producer_before:
            raise ValueError("construction producer changed during the pipeline")

        bound_audit = attach_report_evidence_ref(
            first_audit,
            context_after["reference"],
            command_succeeded=True,
        )
        timestamp = _timestamp(created_utc)
        manifest, object_payloads = _construction_manifest(
            created_utc=timestamp,
            producer=producer_after,
            query=query,
            query_sha256=query_sha256,
            spec_payload=spec_payload,
            resource_payloads=resource_payloads,
            resource_ledger=resource_ledger,
            audit_report=bound_audit,
            build_report=build_report,
            verify_report=verify_report,
            artifact_payload=artifact_payload,
            evidence_context=context_after,
        )
        _populate_staging(
            staging,
            manifest,
            object_payloads,
            source_evidence_bundle=bundle,
        )
        final = output_root / manifest["bundle"]["id"]
        reused = _publish_staging(output_root, staging, final)
        staging = None
        verified_bundle = verify_construction_bundle(final)
        return {
            "schema": CONSTRUCTION_SNAPSHOT_SCHEMA,
            "dcs_started": False,
            "bundle": {
                "id": manifest["bundle"]["id"],
                "directory_name": manifest["bundle"]["id"],
                "manifest_sha256": _sha256(_canonical_bytes(manifest)),
                "root": "<caller-supplied-construction-root>",
                "reused_existing_identical_bundle": reused,
            },
            "artifact": {
                "sha256": build_report["artifact_sha256"],
                "size_bytes": build_report["artifact_bytes"],
                "validation_tier": "V1",
            },
            "producer": producer_after,
            "evidence": {
                "bundle_id": context_after["reference"]["bundle"]["id"],
                "status": context_after["reference"]["status"],
                "required_domains": context_after["reference"][
                    "required_domains"
                ],
            },
            "privacy": manifest["privacy"],
            "validation": {
                "bundle_valid": verified_bundle["validation"]["bundle_valid"],
                "audit_passed": True,
                "build_passed": True,
                "verify_passed": True,
                "artifact_rebuilt_exact": verified_bundle["validation"][
                    "artifact_rebuilt_exact"
                ],
                "verification_replayed": verified_bundle["validation"][
                    "verification_replayed"
                ],
                "replay_producer_matches": verified_bundle["validation"][
                    "replay_producer_matches"
                ],
                "audit_decision_replay_performed": False,
                "evidence_ready_for_static_release": manifest["gate"][
                    "evidence_ready_for_static_release"
                ],
                "static_release_ready": False,
                "runtime_valid": None,
            },
        }
    finally:
        if staging is not None and staging.exists():
            _remove_staging(staging, output_root)
        if root_created:
            _remove_empty_created_root(output_root, root_identity)


def verify_construction_bundle(bundle_path: Path) -> dict[str, Any]:
    """Verify a bundle while normalizing hostile JSON shape failures."""

    try:
        return _verify_construction_bundle(bundle_path)
    except (AttributeError, KeyError, StopIteration, TypeError) as error:
        raise ValueError("construction bundle has an invalid nested shape") from error


def _verify_construction_bundle(bundle_path: Path) -> dict[str, Any]:
    """Verify the complete local bundle and replay build/verify when possible."""

    bundle = canonical_existing_directory(
        Path(bundle_path),
        "construction bundle",
    )
    _validate_root_members(bundle)
    manifest_path = canonical_existing_file(
        bundle / "manifest.json",
        "construction manifest",
    )
    raw_manifest = _read_bounded_report(manifest_path)
    if len(raw_manifest) > MAX_CONSTRUCTION_MANIFEST_BYTES:
        raise ValueError("construction manifest exceeds its byte limit")
    manifest = _parse_report_json(raw_manifest)
    if raw_manifest != _canonical_bytes(manifest):
        raise ValueError("construction manifest is not canonical JSON")
    _validate_manifest(manifest, directory_name=bundle.name)

    objects_dir = canonical_existing_directory(
        bundle / "objects",
        "construction object directory",
    )
    expected_names = {record["sha256"] for record in manifest["objects"]}
    records_by_hash = {record["sha256"]: record for record in manifest["objects"]}
    items = _bounded_directory_entries(
        objects_dir,
        maximum_entries=len(expected_names),
        label="construction object directory",
    )
    actual_names = set(items)
    if actual_names != expected_names:
        raise ValueError("construction bundle has missing or unexpected objects")
    object_payloads: dict[str, bytes] = {}
    total_bytes = 0
    for item in items.values():
        path = canonical_existing_file(item, "construction object")
        if path.name != item.name or _HASH.fullmatch(item.name) is None:
            raise ValueError("construction object has an invalid name")
        record = records_by_hash[item.name]
        payload = _read_exact_regular_file(
            path,
            maximum_bytes=MAX_CONSTRUCTION_OBJECT_BYTES,
            label="construction object",
        )
        total_bytes += len(payload)
        if total_bytes > MAX_CONSTRUCTION_TOTAL_BYTES:
            raise ValueError("construction objects exceed the total byte limit")
        if len(payload) != record["size_bytes"] or _sha256(payload) != item.name:
            raise ValueError("construction object size or hash does not match")
        object_payloads[item.name] = payload
    bindings = manifest["bindings"]
    spec_payload = _bound_object(object_payloads, bindings["spec"]["sha256"])
    if _sha256(spec_payload) != bindings["spec"]["original_sha256"]:
        raise ValueError("construction spec binding does not match")
    _validate_sealed_spec(spec_payload, bindings, manifest["query"])
    audit_report = _bound_json_report(
        object_payloads,
        bindings["reports"]["audit"],
    )
    build_report = _bound_json_report(
        object_payloads,
        bindings["reports"]["build"],
    )
    verify_report = _bound_json_report(
        object_payloads,
        bindings["reports"]["verify"],
    )
    readiness = _bound_json_report(
        object_payloads,
        bindings["evidence_preimages"]["readiness"],
    )
    evidence_verification = _bound_json_report(
        object_payloads,
        bindings["evidence_preimages"]["verification"],
    )
    _validate_bound_audit_report(audit_report, manifest)
    _validate_pipeline_continuity(
        bindings["spec"]["original_sha256"],
        bindings["resources"],
        build_report,
        verify_report,
    )
    artifact_payload = _bound_object(
        object_payloads,
        bindings["artifact"]["sha256"],
    )
    if (
        len(artifact_payload) != bindings["artifact"]["size_bytes"]
        or _sha256(artifact_payload) != build_report["artifact_sha256"]
    ):
        raise ValueError("construction artifact binding does not match")
    _validate_evidence_anchor(
        bundle,
        manifest,
        readiness,
        evidence_verification,
    )
    _validate_node_dag(manifest)

    replay_environment = _toolchain_record() == manifest["producer"]["toolchain"]
    current_git = _git_identity(Path(__file__).resolve().parents[2])
    replay_producer = bool(
        replay_environment
        and current_git.get("commit") == manifest["producer"]["git_commit"]
        and current_git.get("dirty") is False
    )
    artifact_rebuilt_exact = False
    verification_replayed = False
    if replay_producer:
        artifact_rebuilt_exact, verification_replayed = _replay_construction(
            spec_payload,
            artifact_payload,
            bindings["resources"],
            object_payloads,
        )

    return {
        "schema": CONSTRUCTION_VERIFICATION_SCHEMA,
        "dcs_started": False,
        "bundle": {
            "id": manifest["bundle"]["id"],
            "directory_name": bundle.name,
            "manifest_sha256": _sha256(raw_manifest),
        },
        "producer": manifest["producer"],
        "artifact": manifest["bindings"]["artifact"],
        "evidence": manifest["evidence_anchor"],
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
            "pipeline_continuity_valid": True,
            "replay_toolchain_matches": replay_environment,
            "replay_producer_matches": replay_producer,
            "artifact_rebuilt_exact": artifact_rebuilt_exact,
            "verification_replayed": verification_replayed,
            "audit_decision_replay_performed": False,
            "fully_reproducible": False,
            "static_release_ready": False,
            "runtime_valid": None,
        },
        "limitations": [
            "The bundle is content-addressed and tamper-evident, not signed.",
            (
                "Build and verification can be byte-replayed only with the exact "
                "recorded producer commit and Python/zlib toolchain."
            ),
            (
                "Audit query preimages are not replayed by construction-bundle/v1; "
                "the saved audit is traceable but not independently recomputed."
            ),
            "Static V1 validity never implies DCS load, smoke, or playability.",
        ],
    }


def _capture_inputs(
    spec_path: Path,
) -> tuple[Any, bytes, dict[str, bytes], list[dict[str, Any]]]:
    spec = load_build_spec(spec_path, require_resource_files=True)
    source, spec_payload, identity = _read_bound_build_spec(spec.path)
    if (
        source != spec.path
        or identity.st_size != spec.identity.st_size
        or _sha256(spec_payload) != spec.sha256
    ):
        raise ValueError("construction spec changed while it was captured")
    resources = _open_bound_resource_inputs(spec)
    payloads: dict[str, bytes] = {}
    ledger: list[dict[str, Any]] = []
    try:
        for resource in sorted(resources, key=lambda item: item.member):
            payload = _bound_resource_bytes(resource)
            payloads[resource.member] = payload
            ledger.append(
                {
                    "member": resource.member,
                    "size_bytes": resource.size,
                    "sha256": resource.sha256,
                }
            )
    finally:
        _close_bound_resource_inputs(resources)
    _require_build_spec_unchanged(spec)
    return spec, spec_payload, payloads, ledger


def _confirm_inputs(
    spec_path: Path,
    expected_spec: bytes,
    expected_resources: list[dict[str, Any]],
) -> None:
    _spec, spec_payload, resource_payloads, ledger = _capture_inputs(spec_path)
    if spec_payload != expected_spec or ledger != expected_resources:
        raise ValueError("construction inputs changed during the pipeline")
    if any(
        _sha256(resource_payloads[item["member"]]) != item["sha256"]
        for item in ledger
    ):
        raise ValueError("construction resource bytes changed during the pipeline")


def _construction_manifest(
    *,
    created_utc: str,
    producer: dict[str, Any],
    query: dict[str, Any],
    query_sha256: str,
    spec_payload: bytes,
    resource_payloads: dict[str, bytes],
    resource_ledger: list[dict[str, Any]],
    audit_report: dict[str, Any],
    build_report: dict[str, Any],
    verify_report: dict[str, Any],
    artifact_payload: bytes,
    evidence_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    store: dict[str, bytes] = {}
    media: dict[str, set[str]] = {}

    def add(payload: bytes, media_type: str) -> str:
        if not 0 <= len(payload) <= MAX_CONSTRUCTION_OBJECT_BYTES:
            raise ValueError("construction object exceeds its size boundary")
        digest = _sha256(payload)
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
    report_bindings: dict[str, dict[str, Any]] = {}
    for name, report in (
        ("audit", audit_report),
        ("build", build_report),
        ("verify", verify_report),
    ):
        payload = _canonical_bytes(report)
        digest = add(payload, "application/vnd.dcsmizzer.report+json")
        report_bindings[name] = {
            "sha256": digest,
            "schema": report["schema"],
            "intrinsic_sha256": intrinsic_report_sha256(report),
        }
    readiness_payload = _canonical_bytes(evidence_context["readiness"])
    readiness_sha = add(
        readiness_payload,
        "application/vnd.dcsmizzer.evidence-readiness+json",
    )
    verification_payload = _canonical_bytes(evidence_context["verification"])
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
    total_bytes = sum(item["size_bytes"] for item in objects)
    if len(objects) > MAX_CONSTRUCTION_OBJECTS:
        raise ValueError("construction bundle has too many objects")
    if total_bytes > MAX_CONSTRUCTION_TOTAL_BYTES:
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
    nodes = _pipeline_nodes(bindings, evidence_anchor, query_sha256)
    core = {
        "schema": CONSTRUCTION_BUNDLE_SCHEMA,
        "stage": "verify",
        "created_utc": created_utc,
        "producer": producer,
        "command": {
            "name": "construction-snapshot",
            "query_sha256": query_sha256,
        },
        "query": query,
        "evidence_anchor": evidence_anchor,
        "objects": objects,
        "bindings": bindings,
        "nodes": nodes,
        "gate": {
            "audit_passed": True,
            "build_passed": True,
            "verify_passed": True,
            "evidence_ready_for_static_release": reference["validation"][
                "evidence_ready_for_binding"
            ],
            "audit_decision_replay_available": False,
            "static_release_ready": False,
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
    bundle_id = _sha256(_canonical_bytes(core))
    manifest = {
        **core,
        "bundle": {
            "algorithm": "sha256",
            "id": bundle_id,
            "content_address_basis": "canonical_manifest_without_bundle_field",
        },
    }
    payload = _canonical_bytes(manifest)
    if len(payload) > MAX_CONSTRUCTION_MANIFEST_BYTES:
        raise ValueError("construction manifest exceeds its byte limit")
    _validate_manifest(manifest, directory_name=bundle_id)
    return manifest, store


def _pipeline_nodes(
    bindings: dict[str, Any],
    evidence_anchor: dict[str, Any],
    query_sha256: str,
) -> list[dict[str, Any]]:
    audit_core = {
        "stage": "audit",
        "parent_id": None,
        "query_sha256": query_sha256,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "report_sha256": bindings["reports"]["audit"]["sha256"],
        "evidence_bundle_id": evidence_anchor["bundle_id"],
        "evidence_manifest_sha256": evidence_anchor["manifest_sha256"],
        "domain_artifact_bindings": evidence_anchor[
            "domain_artifact_bindings"
        ],
    }
    audit_id = _sha256(_canonical_bytes(audit_core))
    build_core = {
        "stage": "build",
        "parent_id": audit_id,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "resources": bindings["resources"],
        "report_sha256": bindings["reports"]["build"]["sha256"],
        "artifact_sha256": bindings["artifact"]["sha256"],
    }
    build_id = _sha256(_canonical_bytes(build_core))
    verify_core = {
        "stage": "verify",
        "parent_id": build_id,
        "spec_sha256": bindings["spec"]["original_sha256"],
        "resources": bindings["resources"],
        "report_sha256": bindings["reports"]["verify"]["sha256"],
        "artifact_sha256": bindings["artifact"]["sha256"],
    }
    verify_id = _sha256(_canonical_bytes(verify_core))
    return [
        {**audit_core, "id": audit_id},
        {**build_core, "id": build_id},
        {**verify_core, "id": verify_id},
    ]


def _populate_staging(
    staging: Path,
    manifest: dict[str, Any],
    object_payloads: dict[str, bytes],
    *,
    source_evidence_bundle: Path,
) -> None:
    work = staging / "work.miz"
    if work.exists():
        work.unlink()
    objects = staging / "objects"
    objects.mkdir()
    for digest, payload in sorted(object_payloads.items()):
        _write_new_file(objects / digest, payload)
    evidence_root = staging / "evidence"
    evidence_root.mkdir()
    destination = evidence_root / manifest["evidence_anchor"]["bundle_id"]
    _copy_evidence_bundle(source_evidence_bundle, destination)
    _write_new_file(staging / "manifest.json", _canonical_bytes(manifest))
    embedded = verify_evidence_bundle(destination)
    if (
        embedded["bundle"]["id"] != manifest["evidence_anchor"]["bundle_id"]
        or embedded["bundle"]["manifest_sha256"]
        != manifest["evidence_anchor"]["manifest_sha256"]
    ):
        raise ValueError("embedded evidence bundle identity changed")


def _copy_evidence_bundle(source: Path, destination: Path) -> None:
    verification = verify_evidence_bundle(source)
    destination.mkdir()
    artifacts_destination = destination / "artifacts"
    artifacts_destination.mkdir()
    manifest_source = canonical_existing_file(
        source / "manifest.json",
        "source evidence manifest",
    )
    _write_new_file(
        destination / "manifest.json",
        _read_bounded_report(manifest_source),
    )
    for record in verification["artifacts"]:
        name = record["name"]
        source_path = canonical_existing_file(
            source / "artifacts" / f"{name}.json",
            "source evidence artifact",
        )
        _write_new_file(
            artifacts_destination / f"{name}.json",
            _read_bounded_report(source_path),
        )


def _publish_staging(root: Path, staging: Path, final: Path) -> bool:
    if final.exists():
        verify_construction_bundle(final)
        _remove_staging(staging, root)
        return True
    try:
        os.replace(staging, final)
        return False
    except OSError:
        if not final.exists():
            raise
        verify_construction_bundle(final)
        _remove_staging(staging, root)
        return True


def _validate_sealed_spec(
    payload: bytes,
    bindings: dict[str, Any],
    query: dict[str, Any],
) -> None:
    if len(payload) > MAX_BUILD_SPEC_BYTES:
        raise ValueError("sealed construction spec exceeds the build-spec limit")
    with tempfile.TemporaryDirectory(prefix="dcsmizzer-sealed-spec-") as temp:
        path = Path(temp) / "spec.json"
        _write_new_file(path, payload)
        sealed = load_build_spec(path, require_resource_files=False)
    resource_members = [item["member"] for item in bindings["resources"]]
    if (
        sealed.sha256 != bindings["spec"]["original_sha256"]
        or resource_members != list(sealed.resource_members)
        or query["resolved_pydcs_terrain"]
        != (query["pydcs_terrain"] or sealed.theatre)
        or query["resolved_briefingroom_terrain"] != sealed.theatre
    ):
        raise ValueError("sealed construction spec bindings are inconsistent")
    if audit_spec_dependencies(sealed)["gci"]:
        raise ValueError(
            "sealed construction spec requires unsupported GCI evidence"
        )


def _replay_construction(
    spec_payload: bytes,
    artifact_payload: bytes,
    resources: list[dict[str, Any]],
    objects: dict[str, bytes],
) -> tuple[bool, bool]:
    with tempfile.TemporaryDirectory(prefix="dcsmizzer-construction-replay-") as temp:
        root = Path(temp)
        spec_path = root / "spec.json"
        _write_new_file(spec_path, spec_payload)
        overrides: dict[str, Path] = {}
        for index, item in enumerate(resources):
            path = root / f"resource-{index:03d}.bin"
            _write_new_file(path, _bound_object(objects, item["object_sha256"]))
            overrides[item["member"]] = path
        rebuilt = root / "rebuilt.miz"
        build_report, built = build_miz(
            spec_path,
            rebuilt,
            resource_overrides=overrides,
        )
        rebuilt_payload = _read_exact_regular_file(
            rebuilt,
            maximum_bytes=MAX_CONSTRUCTION_OBJECT_BYTES,
            label="replayed construction artifact",
        )
        artifact_exact = bool(
            built
            and rebuilt_payload == artifact_payload
            and build_report["artifact_sha256"] == _sha256(artifact_payload)
        )
        stored = root / "stored.miz"
        _write_new_file(stored, artifact_payload)
        verify_report, verified = verify_miz(
            stored,
            spec_path,
            resource_overrides=overrides,
        )
        return artifact_exact, bool(
            verified
            and verify_report["artifact_sha256"] == _sha256(artifact_payload)
        )


def _validate_bound_audit_report(
    report: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    validate_attached_report_evidence_ref(report)
    reference = report["evidence_ref"]
    anchor = manifest["evidence_anchor"]
    binding = reference["report_binding"]
    validation = reference["validation"]
    producer = manifest["producer"]
    producer_identity = {
        "name": producer["name"],
        "version": producer["version"],
        "git_commit": producer["git_commit"],
        "git_dirty": producer["git_dirty"],
    }
    if (
        report.get("input_spec_sha256")
        != manifest["bindings"]["spec"]["original_sha256"]
    ):
        raise ValueError("construction audit spec binding is invalid")
    if (
        reference["producer"]["current"] != producer_identity
        or reference["producer"]["bundle"] != producer_identity
    ):
        raise ValueError("construction audit producer binding is invalid")
    _validate_audit_decision(report, manifest["query"])
    if (
        validation["report_gate_passed"] is not True
        or reference["bundle"]
        != {
            "id": anchor["bundle_id"],
            "manifest_sha256": anchor["manifest_sha256"],
        }
        or reference["status"] != anchor["status"]
        or reference["required_domains"] != anchor["required_domains"]
        or reference["domain_artifact_bindings"]
        != anchor["domain_artifact_bindings"]
        or reference["current_readiness"]["canonical_sha256"]
        != anchor["readiness_canonical_sha256"]
        or binding["command"] != manifest["command"]["name"]
        or binding["query_sha256"] != manifest["command"]["query_sha256"]
        or binding["mandatory_domains"] != anchor["mandatory_domains"]
        or binding["source_roots_matched"] is not True
        or validation["evidence_ready_for_binding"]
        is not manifest["gate"]["evidence_ready_for_static_release"]
    ):
        raise ValueError("construction audit evidence anchor is invalid")


def _validate_audit_decision(
    report: dict[str, Any],
    query: dict[str, Any],
) -> None:
    checks = report.get("checks")
    warnings = report.get("warnings")
    validation = report.get("validation")
    filters = report.get("filters")
    if (
        set(report)
        != {
            "schema",
            "input_spec",
            "input_spec_sha256",
            "input_spec_path_scope",
            "dcs_started",
            "upstream_python_executed",
            "filters",
            "sources",
            "checks",
            "warnings",
            "validation",
            "limitations",
            "evidence_ref",
        }
        or report.get("dcs_started") is not False
        or report.get("upstream_python_executed") is not False
        or report.get("input_spec_path_scope") != "basename_only"
        or not isinstance(report.get("input_spec"), str)
        or Path(report["input_spec"]).name != report["input_spec"]
        or not isinstance(checks, list)
        or not isinstance(warnings, list)
        or not isinstance(validation, dict)
        or set(validation)
        != {
            "checks",
            "passed",
            "failed",
            "warning_count",
            "evidence_consistent",
            "review_warnings_clear",
            "runtime_valid",
        }
        or not isinstance(filters, dict)
    ):
        raise ValueError("construction audit decision shape is invalid")
    passed_values = [
        item.get("passed") if isinstance(item, dict) else None for item in checks
    ]
    if any(not isinstance(item, bool) for item in passed_values):
        raise ValueError("construction audit check result is invalid")
    failed = sum(item is False for item in passed_values)
    passed = len(passed_values) - failed
    if (
        validation["checks"] != len(checks)
        or validation["passed"] != passed
        or validation["failed"] != failed
        or validation["warning_count"] != len(warnings)
        or validation["evidence_consistent"] is not (failed == 0)
        or validation["review_warnings_clear"] is not (not warnings)
        or validation["runtime_valid"] is not None
        or failed != 0
        or filters
        != {
            "installed_terrain": query["installed_terrain"],
            "terrain_query": query["resolved_pydcs_terrain"],
            "briefingroom_terrain_query": query[
                "resolved_briefingroom_terrain"
            ],
            "briefingroom_enabled": True,
            "require_acknowledged_upstreams": True,
        }
    ):
        raise ValueError("construction audit decision did not pass exact checks")


def _validate_pipeline_continuity(
    spec_sha256: str,
    resources: list[dict[str, Any]],
    build_report: dict[str, Any],
    verify_report: dict[str, Any],
) -> None:
    if not isinstance(build_report, dict) or not isinstance(verify_report, dict):
        raise ValueError("construction build/verify reports are invalid")
    generation = build_report.get("generation")
    build_validation = build_report.get("validation")
    verify_validation = verify_report.get("validation")
    if (
        not isinstance(generation, dict)
        or not isinstance(build_validation, dict)
        or not isinstance(verify_validation, dict)
    ):
        raise ValueError("construction build/verify report shape is invalid")
    expected_resources = [
        {
            "member": item.get("member"),
            "size_bytes": item.get("size_bytes"),
            "sha256": item.get("sha256"),
        }
        for item in resources
    ]
    build_resources = build_report.get("resource_inputs")
    verify_resources = verify_report.get("resource_inputs")
    if (
        "evidence_ref" in build_report
        or "evidence_ref" in verify_report
        or build_report.get("schema") != "dcsmizzer.miz-build/v1"
        or verify_report.get("schema") != "dcsmizzer.miz-verification/v1"
        or generation.get("spec_sha256") != spec_sha256
        or verify_report.get("spec_sha256") != spec_sha256
        or build_resources != expected_resources
        or verify_resources != expected_resources
        or build_report.get("artifact_sha256")
        != verify_report.get("artifact_sha256")
        or build_report.get("artifact_bytes") != verify_report.get("artifact_bytes")
        or build_validation.get("available_checks_passed") is not True
        or verify_validation.get("available_checks_passed") is not True
        or build_validation.get("runtime_valid") is not None
        or verify_validation.get("runtime_valid") is not None
    ):
        raise ValueError("construction audit/build/verify continuity is invalid")


def _validate_evidence_anchor(
    bundle: Path,
    manifest: dict[str, Any],
    readiness: dict[str, Any],
    recorded_verification: dict[str, Any],
) -> None:
    anchor = manifest["evidence_anchor"]
    evidence_root = canonical_existing_directory(
        bundle / "evidence",
        "construction evidence directory",
    )
    evidence_entries = _bounded_directory_entries(
        evidence_root,
        maximum_entries=1,
        label="construction evidence directory",
    )
    if set(evidence_entries) != {anchor["bundle_id"]}:
        raise ValueError("construction evidence directory has unexpected members")
    embedded_path = canonical_existing_directory(
        evidence_entries[anchor["bundle_id"]],
        "embedded evidence bundle",
    )
    actual = verify_evidence_bundle(embedded_path)
    producer = manifest["producer"]
    producer_identity = {
        "name": producer["name"],
        "version": producer["version"],
        "git_commit": producer["git_commit"],
        "git_dirty": producer["git_dirty"],
    }
    if _canonical_bytes(actual) != _canonical_bytes(recorded_verification):
        raise ValueError("embedded evidence verification preimage changed")
    decision = validate_evidence_readiness_report(
        readiness,
        actual,
        tuple(anchor["required_domains"]),
    )
    readiness_status = {
        name: record["ready"]
        for name, record in decision["required_domains"].items()
    }
    all_domains_ready = decision["all_required_domains_ready"]
    expected_status = "bundle-current" if all_domains_ready else "unbound"
    if (
        actual["bundle"]["id"] != anchor["bundle_id"]
        or actual["bundle"]["manifest_sha256"] != anchor["manifest_sha256"]
        or actual.get("producer") != producer_identity
        or _domain_artifact_bindings(
            actual,
            tuple(anchor["required_domains"]),
        )
        != anchor["domain_artifact_bindings"]
        or _sha256(_canonical_bytes(readiness))
        != anchor["readiness_canonical_sha256"]
        or readiness.get("bundle")
        != {
            "kind": "content_addressed_bundle",
            "schema": "dcsmizzer.evidence-bundle/v1",
            "bundle_id": anchor["bundle_id"],
        }
        or readiness_status != anchor["required_domains"]
        or decision["producer"]
        != {
            "name": producer["name"],
            "version": producer["version"],
            "git_commit": producer["git_commit"],
            "reproducible": True,
        }
        or anchor["status"] != expected_status
        or manifest["gate"]["evidence_ready_for_static_release"]
        is not all_domains_ready
    ):
        raise ValueError("construction evidence anchor is invalid")


def _validate_node_dag(manifest: dict[str, Any]) -> None:
    expected = _pipeline_nodes(
        manifest["bindings"],
        manifest["evidence_anchor"],
        manifest["command"]["query_sha256"],
    )
    if manifest["nodes"] != expected:
        raise ValueError("construction node DAG is invalid")


def _validate_manifest(manifest: dict[str, Any], *, directory_name: str) -> None:
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
        set(manifest) != required
        or manifest.get("schema") != CONSTRUCTION_BUNDLE_SCHEMA
    ):
        raise ValueError("construction manifest shape or schema is invalid")
    if manifest.get("stage") != "verify":
        raise ValueError("construction manifest final stage is invalid")
    _timestamp(manifest.get("created_utc"))
    _validate_producer(manifest.get("producer"))
    command = manifest.get("command")
    if (
        not isinstance(command, dict)
        or set(command) != {"name", "query_sha256"}
        or command.get("name") != "construction-snapshot"
        or _HASH.fullmatch(str(command.get("query_sha256"))) is None
    ):
        raise ValueError("construction command binding is invalid")
    query = manifest.get("query")
    if (
        not isinstance(query, dict)
        or query.get("schema") != "dcsmizzer.construction-query/v1"
        or _sha256(_canonical_bytes(query)) != command["query_sha256"]
    ):
        raise ValueError("construction query binding is invalid")
    _validate_evidence_anchor_shape(manifest.get("evidence_anchor"))
    _validate_objects(manifest.get("objects"))
    _validate_bindings(manifest.get("bindings"), manifest["objects"])
    _validate_query(
        query,
        manifest["bindings"],
        manifest["evidence_anchor"],
    )
    nodes = manifest.get("nodes")
    if (
        not isinstance(nodes, list)
        or [item.get("stage") for item in nodes if isinstance(item, dict)]
        != ["audit", "build", "verify"]
    ):
        raise ValueError("construction node records are invalid")
    gate = manifest.get("gate")
    if (
        not isinstance(gate, dict)
        or set(gate)
        != {
            "audit_passed",
            "build_passed",
            "verify_passed",
            "evidence_ready_for_static_release",
            "audit_decision_replay_available",
            "static_release_ready",
            "runtime_valid",
        }
        or gate["audit_passed"] is not True
        or gate["build_passed"] is not True
        or gate["verify_passed"] is not True
        or not isinstance(gate["evidence_ready_for_static_release"], bool)
        or gate["audit_decision_replay_available"] is not False
        or gate["static_release_ready"] is not False
        or gate["runtime_valid"] is not None
    ):
        raise ValueError("construction gate is invalid")
    privacy = manifest.get("privacy")
    if privacy != {
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
        or _HASH.fullmatch(str(bundle.get("id"))) is None
        or directory_name != bundle["id"]
    ):
        raise ValueError("construction content address is invalid")
    core = dict(manifest)
    del core["bundle"]
    if _sha256(_canonical_bytes(core)) != bundle["id"]:
        raise ValueError("construction manifest content address does not match")


def _validate_producer(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"name", "version", "git_commit", "git_dirty", "toolchain"}
        or value.get("name") != "DCSMizzer"
        or not isinstance(value.get("version"), str)
        or _COMMIT.fullmatch(str(value.get("git_commit"))) is None
        or value.get("git_dirty") is not False
        or not isinstance(value.get("toolchain"), dict)
    ):
        raise ValueError("construction producer is invalid")
    toolchain = value["toolchain"]
    if (
        set(toolchain)
        != {
            "python_implementation",
            "python_version",
            "zlib_compile_version",
            "zlib_runtime_version",
            "platform",
        }
        or any(not isinstance(item, str) or not item for item in toolchain.values())
    ):
        raise ValueError("construction producer toolchain is invalid")


def _validate_query(
    query: dict[str, Any],
    bindings: dict[str, Any],
    anchor: dict[str, Any],
) -> None:
    if set(query) != {
        "schema",
        "spec_sha256",
        "resources",
        "installed_terrain",
        "pydcs_terrain",
        "resolved_pydcs_terrain",
        "resolved_briefingroom_terrain",
        "briefingroom_enabled",
        "mandatory_domains",
    }:
        raise ValueError("construction query shape is invalid")
    installed_terrain = query["installed_terrain"]
    pydcs_terrain = query["pydcs_terrain"]
    resolved_pydcs = query["resolved_pydcs_terrain"]
    resolved_briefingroom = query["resolved_briefingroom_terrain"]
    if (
        (installed_terrain is not None and not isinstance(installed_terrain, str))
        or (pydcs_terrain is not None and not isinstance(pydcs_terrain, str))
        or isinstance(installed_terrain, str)
        and not installed_terrain
        or isinstance(pydcs_terrain, str)
        and not pydcs_terrain
        or not isinstance(resolved_pydcs, str)
        or not resolved_pydcs
        or not isinstance(resolved_briefingroom, str)
        or not resolved_briefingroom
    ):
        raise ValueError("construction terrain query is invalid")
    expected_domains = tuple(
        sorted(
            {
                *_AUDIT_BASE_DOMAINS,
                *({"airfields"} if installed_terrain is not None else set()),
            }
        )
    )
    expected_resources = [
        {
            "member": item["member"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
        }
        for item in bindings["resources"]
    ]
    if (
        query["spec_sha256"] != bindings["spec"]["original_sha256"]
        or query["resources"] != expected_resources
        or query["briefingroom_enabled"] is not True
        or query["mandatory_domains"] != list(expected_domains)
        or anchor["mandatory_domains"] != list(expected_domains)
    ):
        raise ValueError(
            "construction query spec/resource bindings are invalid"
        )


def _validate_evidence_anchor_shape(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "bundle_id",
            "manifest_sha256",
            "embedded_relative_path",
            "status",
            "mandatory_domains",
            "required_domains",
            "domain_artifact_bindings",
            "readiness_canonical_sha256",
        }
        or _HASH.fullmatch(str(value.get("bundle_id"))) is None
        or _HASH.fullmatch(str(value.get("manifest_sha256"))) is None
        or value.get("embedded_relative_path") != f"evidence/{value.get('bundle_id')}"
        or value.get("status") not in {"bundle-current", "unbound"}
        or not isinstance(value.get("mandatory_domains"), list)
        or any(
            not isinstance(item, str) for item in value["mandatory_domains"]
        )
        or value["mandatory_domains"] != sorted(set(value["mandatory_domains"]))
        or not isinstance(value.get("required_domains"), dict)
        or set(value["required_domains"]) != set(value["mandatory_domains"])
        or any(
            not isinstance(item, bool)
            for item in value["required_domains"].values()
        )
        or not isinstance(value.get("domain_artifact_bindings"), dict)
        or set(value["domain_artifact_bindings"])
        != set(value["mandatory_domains"])
        or any(
            _HASH.fullmatch(str(item)) is None
            for item in value["domain_artifact_bindings"].values()
        )
        or _HASH.fullmatch(str(value.get("readiness_canonical_sha256"))) is None
    ):
        raise ValueError("construction evidence anchor shape is invalid")


def _validate_objects(value: Any) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CONSTRUCTION_OBJECTS:
        raise ValueError("construction object manifest is invalid")
    hashes: list[str] = []
    total = 0
    for item in value:
        digest = item.get("sha256") if isinstance(item, dict) else None
        size = item.get("size_bytes") if isinstance(item, dict) else None
        media = item.get("media_types") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "relative_path", "size_bytes", "media_types"}
            or _HASH.fullmatch(str(digest)) is None
            or item.get("relative_path") != f"objects/{digest}"
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 <= size <= MAX_CONSTRUCTION_OBJECT_BYTES
            or not isinstance(media, list)
            or not media
            or any(not isinstance(name, str) or not name for name in media)
            or media != sorted(set(media))
        ):
            raise ValueError("construction object record is invalid")
        hashes.append(digest)
        total += size
    if hashes != sorted(set(hashes)) or total > MAX_CONSTRUCTION_TOTAL_BYTES:
        raise ValueError("construction object records are unordered or oversized")


def _validate_bindings(value: Any, objects: list[dict[str, Any]]) -> None:
    if not isinstance(value, dict) or set(value) != {
        "spec",
        "resources",
        "reports",
        "artifact",
        "evidence_preimages",
    }:
        raise ValueError("construction bindings are invalid")
    known = {item["sha256"]: item for item in objects}
    referenced: set[str] = set()
    spec = value["spec"]
    if (
        not isinstance(spec, dict)
        or set(spec) != {"sha256", "original_sha256", "schema"}
        or spec.get("schema") != SPEC_SCHEMA
        or not _is_hash(spec.get("sha256"))
        or not _is_hash(spec.get("original_sha256"))
        or spec.get("sha256") != spec.get("original_sha256")
        or spec.get("sha256") not in known
    ):
        raise ValueError("construction spec binding is invalid")
    referenced.add(spec["sha256"])
    resources = value["resources"]
    if not isinstance(resources, list):
        raise ValueError("construction resource bindings are invalid")
    members: list[str] = []
    for item in resources:
        if (
            not isinstance(item, dict)
            or set(item) != {"member", "size_bytes", "sha256", "object_sha256"}
            or not isinstance(item.get("member"), str)
            or not item["member"]
            or not _is_hash(item.get("sha256"))
            or not _is_hash(item.get("object_sha256"))
            or item.get("sha256") != item.get("object_sha256")
            or item.get("sha256") not in known
            or item.get("size_bytes") != known[item["sha256"]]["size_bytes"]
        ):
            raise ValueError("construction resource binding is invalid")
        members.append(item["member"])
        referenced.add(item["object_sha256"])
    if members != sorted(set(members)):
        raise ValueError("construction resource bindings are unordered")
    reports = value["reports"]
    if not isinstance(reports, dict) or set(reports) != {"audit", "build", "verify"}:
        raise ValueError("construction report bindings are invalid")
    expected_schemas = {
        "audit": "dcsmizzer.build-spec-evidence-audit/v1",
        "build": "dcsmizzer.miz-build/v1",
        "verify": "dcsmizzer.miz-verification/v1",
    }
    for name, binding in reports.items():
        _validate_report_binding(binding, known, expected_schemas[name])
        referenced.add(binding["sha256"])
    artifact = value["artifact"]
    if (
        not isinstance(artifact, dict)
        or set(artifact) != {"sha256", "size_bytes", "validation_tier"}
        or not _is_hash(artifact.get("sha256"))
        or isinstance(artifact.get("size_bytes"), bool)
        or not isinstance(artifact.get("size_bytes"), int)
        or artifact.get("sha256") not in known
        or artifact.get("size_bytes") != known[artifact["sha256"]]["size_bytes"]
        or artifact.get("validation_tier") != "V1"
    ):
        raise ValueError("construction artifact binding is invalid")
    referenced.add(artifact["sha256"])
    preimages = value["evidence_preimages"]
    if not isinstance(preimages, dict) or set(preimages) != {
        "readiness",
        "verification",
    }:
        raise ValueError("construction evidence preimages are invalid")
    _validate_report_binding(
        preimages["readiness"],
        known,
        "dcsmizzer.evidence-readiness/v1",
    )
    _validate_report_binding(
        preimages["verification"],
        known,
        "dcsmizzer.evidence-bundle-verification/v1",
    )
    referenced.update(
        {
            preimages["readiness"]["sha256"],
            preimages["verification"]["sha256"],
        }
    )
    if referenced != set(known):
        raise ValueError("construction bundle contains an unbound object")


def _validate_report_binding(
    value: Any,
    known: dict[str, dict[str, Any]],
    schema: str,
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"sha256", "schema", "intrinsic_sha256"}
        or not _is_hash(value.get("sha256"))
        or value.get("sha256") not in known
        or value.get("schema") != schema
        or not _is_hash(value.get("intrinsic_sha256"))
    ):
        raise ValueError("construction report binding is invalid")


def _bound_json_report(
    objects: dict[str, bytes],
    binding: dict[str, Any],
) -> dict[str, Any]:
    payload = _bound_object(objects, binding["sha256"])
    report = _parse_report_json(payload)
    if (
        payload != _canonical_bytes(report)
        or report.get("schema") != binding["schema"]
        or intrinsic_report_sha256(report) != binding["intrinsic_sha256"]
    ):
        raise ValueError("construction bound report is invalid")
    return report


def _bound_object(objects: dict[str, bytes], digest: str) -> bytes:
    payload = objects.get(digest)
    if payload is None or _sha256(payload) != digest:
        raise ValueError("construction bound object is unavailable")
    return payload


def _validate_root_members(bundle: Path) -> None:
    entries = _bounded_directory_entries(
        bundle,
        maximum_entries=3,
        label="construction bundle",
    )
    if set(entries) != {"manifest.json", "objects", "evidence"}:
        raise ValueError("construction bundle has unexpected root members")
    for name in ("objects", "evidence"):
        canonical_existing_directory(entries[name], f"construction {name} directory")
    canonical_existing_file(entries["manifest.json"], "construction manifest")


def _bounded_directory_entries(
    directory: Path,
    *,
    maximum_entries: int,
    label: str,
) -> dict[str, Path]:
    if isinstance(maximum_entries, bool) or not isinstance(maximum_entries, int):
        raise ValueError(f"{label} entry limit is invalid")
    if maximum_entries < 0:
        raise ValueError(f"{label} entry limit is invalid")
    entries: dict[str, Path] = {}
    for item in directory.iterdir():
        if len(entries) >= maximum_entries:
            raise ValueError(f"{label} contains too many entries")
        if item.name in entries:
            raise ValueError(f"{label} contains duplicate entry names")
        entries[item.name] = item
    return entries


def _read_exact_regular_file(path: Path, *, maximum_bytes: int, label: str) -> bytes:
    source = canonical_existing_file(path, label)
    before = source.lstat()
    if before.st_size < 0 or before.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its size boundary")
    with source.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        payload = stream.read(maximum_bytes + 1)
        final_opened = os.fstat(stream.fileno())
    after = source.lstat()
    if (
        len(payload) != before.st_size
        or len(payload) > maximum_bytes
        or not os.path.samestat(before, opened)
        or not os.path.samestat(opened, final_opened)
        or not os.path.samestat(final_opened, after)
    ):
        raise ValueError(f"{label} changed while it was read")
    return payload


def _producer_record(repository: Path) -> dict[str, Any]:
    identity = _git_identity(repository)
    return {
        "name": "DCSMizzer",
        "version": __version__,
        "git_commit": identity.get("commit"),
        "git_dirty": identity.get("dirty"),
        "toolchain": _toolchain_record(),
    }


def _toolchain_record() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "zlib_compile_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": getattr(
            zlib,
            "ZLIB_RUNTIME_VERSION",
            zlib.ZLIB_VERSION,
        ),
        "platform": sys.platform,
    }


def _require_reproducible_producer(producer: dict[str, Any]) -> None:
    if (
        producer.get("name") != "DCSMizzer"
        or _COMMIT.fullmatch(str(producer.get("git_commit"))) is None
        or producer.get("git_dirty") is not False
    ):
        raise ValueError("construction requires one clean exact producer commit")


def _require_context_producer(context: dict[str, Any]) -> None:
    reference = context.get("reference")
    validation = reference.get("validation") if isinstance(reference, dict) else None
    if (
        not isinstance(validation, dict)
        or validation.get("bundle_reference_present") is not True
        or validation.get("bundle_integrity_verified") is not True
        or validation.get("bundle_stable_during_binding") is not True
        or validation.get("current_state_revalidated") is not True
        or validation.get("reproducible_current_producer") is not True
        or validation.get("current_producer_matches_bundle") is not True
    ):
        raise ValueError(
            "construction evidence producer is not current and reproducible"
        )


def _failed_snapshot_report(
    report: dict[str, Any],
    context: dict[str, Any],
    producer: dict[str, Any],
    *,
    reason: str,
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
            "build_passed": build_passed,
            "verify_passed": False,
            "evidence_ready_for_static_release": False,
            "audit_decision_replay_performed": False,
            "static_release_ready": False,
            "runtime_valid": None,
        },
    }


def _timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    if not isinstance(value, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value,
    ) is None:
        raise ValueError("construction timestamp must be canonical UTC seconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError(
            "construction timestamp must be canonical UTC seconds"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("construction timestamp must be canonical UTC seconds")
    return value


def _construction_root_candidate(
    path: Path,
    *,
    protected: tuple[Path, ...],
) -> Path:
    try:
        value = os.fspath(path)
    except TypeError as error:
        raise ValueError("construction root must be a filesystem path") from error
    if not value or "\x00" in value:
        raise ValueError("construction root must be a non-empty path")
    if os.name == "nt":
        _drive, tail = os.path.splitdrive(value)
        if ":" in tail:
            raise ValueError("construction root must not name an alternate stream")
    try:
        candidate = Path(os.path.abspath(value))
    except (OSError, ValueError) as error:
        raise ValueError("construction root cannot be made absolute") from error
    if candidate == Path(candidate.anchor):
        raise ValueError("construction root must not be a filesystem root")
    if candidate.exists():
        candidate = canonical_existing_directory(candidate, "construction root")
    else:
        parent = canonical_existing_directory(
            candidate.parent,
            "construction root parent",
        )
        candidate = parent / candidate.name
    _reject_construction_root_overlap(candidate, protected)
    return candidate


def _reject_construction_root_overlap(
    candidate: Path,
    protected: tuple[Path, ...],
) -> None:
    for source in protected:
        if (
            candidate == source
            or candidate in source.parents
            or source in candidate.parents
        ):
            raise ValueError("construction root overlaps a protected input path")


def _create_construction_root(
    candidate: Path,
) -> tuple[Path, bool, os.stat_result]:
    created = False
    created_identity: os.stat_result | None = None
    try:
        candidate.mkdir(mode=0o700)
        created = True
        created_identity = candidate.lstat()
    except FileExistsError:
        pass
    try:
        root = canonical_existing_directory(candidate, "construction root")
    except Exception:
        if created_identity is not None:
            _remove_empty_created_root(candidate, created_identity)
        raise
    identity = root.lstat()
    if created and (
        created_identity is None
        or not os.path.samestat(created_identity, identity)
    ):
        raise ValueError("construction root changed while it was created")
    return root, created, identity


def _remove_empty_created_root(path: Path, expected: os.stat_result) -> bool:
    try:
        current = path.lstat()
        if (
            not stat.S_ISDIR(current.st_mode)
            or _is_reparse(current)
            or not os.path.samestat(current, expected)
        ):
            return False
        iterator = path.iterdir()
        try:
            next(iterator)
            return False
        except StopIteration:
            path.rmdir()
            return True
    except OSError:
        return False


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("construction content is not canonical JSON") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _remove_staging(staging: Path, root: Path) -> None:
    candidate = staging.absolute()
    if candidate.parent != root or not candidate.name.startswith(_STAGING_PREFIX):
        raise ValueError("refusing to remove an unrecognized construction staging path")
    _remove_safe_directory(candidate, depth=0)


def _remove_safe_directory(path: Path, *, depth: int) -> None:
    if depth > 4:
        raise ValueError("construction staging tree exceeds safe cleanup depth")
    status_result = path.lstat()
    if not stat.S_ISDIR(status_result.st_mode) or _is_reparse(status_result):
        raise ValueError("construction staging contains an unsafe directory")
    for item in path.iterdir():
        item_status = item.lstat()
        if _is_reparse(item_status):
            raise ValueError("construction staging contains a reparse point")
        if stat.S_ISDIR(item_status.st_mode):
            _remove_safe_directory(item, depth=depth + 1)
        elif stat.S_ISREG(item_status.st_mode):
            item.unlink()
        else:
            raise ValueError("construction staging contains an unsafe entry")
    path.rmdir()


def _is_reparse(status_result: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(stat.S_ISLNK(status_result.st_mode) or (flag and attributes & flag))
