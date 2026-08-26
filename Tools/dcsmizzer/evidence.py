"""Content-addressed evidence snapshots, verification, drift, and readiness."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import capabilities_report
from .dcs_static import (
    airbase_beacon_report,
    countries_report,
    module_index_report,
    payload_index_report,
    static_install_report,
)
from .evidence_inputs import (
    MAX_BOUND_INPUTS_PER_KIND,
    RUNTIME_ATTESTATION_SCHEMA,
    TERRAIN_ATTESTATION_SCHEMA,
    runtime_artifact_name,
    runtime_attestation,
    runtime_coverage,
    terrain_artifact_name,
    terrain_attestation,
    terrain_coverage,
    validate_runtime_attestation,
    validate_terrain_attestation,
)
from .path_safety import canonical_existing_directory
from .report_provenance import REPORT_EVIDENCE_REF_SCHEMA
from .report_views import (
    KNOWN_REPORT_SCHEMAS,
    _parse_report_json,
    _read_bounded_report,
)
from .runtime import (
    MAX_MISSION_BYTES,
    _distribution_identity,
    _existing_directory,
    _git_identity,
    _optional_source_record,
    _select_dcs_executable,
    _sha256_file,
    _windows_product_version,
    _write_new_file,
)
from .upstream_cache import upstream_status_report
from .weather import weather_registry_report

BUNDLE_SCHEMA = "dcsmizzer.evidence-bundle/v1"
SNAPSHOT_SCHEMA = "dcsmizzer.evidence-snapshot/v1"
VERIFICATION_SCHEMA = "dcsmizzer.evidence-bundle-verification/v1"
DIFF_SCHEMA = "dcsmizzer.evidence-diff/v1"
READINESS_SCHEMA = "dcsmizzer.evidence-readiness/v1"
LEGACY_INSTALLATION_SCHEMA = "dcsmizzer.dcs-installation-survey/v1"
MAX_ARTIFACTS = 64
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_BUNDLE_ID = re.compile(r"\A[0-9a-f]{64}\Z")
_ARTIFACT_NAME = re.compile(r"\A[a-z0-9][a-z0-9.-]{0,95}\Z")
_HASH = re.compile(r"\A[0-9a-f]{64}\Z")
_COLLECTION_RUN_ID = re.compile(r"\Asnapshot-[0-9TZ.]{8,32}\Z")
_RUNTIME_ARTIFACT_RUN_ID = re.compile(r"\A[a-z0-9][a-z0-9-]{0,47}\Z")
_STAGING_PREFIX = ".dcsmizzer-evidence-"
_REQUIRED_DOMAINS = frozenset(
    {
        "installation",
        "countries",
        "modules",
        "payloads",
        "weather",
        "airfields",
        "upstream",
        "capabilities",
        "runtime",
        "terrain",
    }
)
_ARTIFACT_SCHEMAS = {
    "installation": frozenset({"dcsmizzer.dcs-static/v1"}),
    "capabilities": frozenset({"dcsmizzer.capabilities/v3"}),
    "countries": frozenset({"dcsmizzer.dcs-countries/v1"}),
    "modules": frozenset({"dcsmizzer.dcs-module-index/v1"}),
    "payloads": frozenset({"dcsmizzer.dcs-default-payload-index/v1"}),
    "weather": frozenset({"dcsmizzer.dcs-weather-presets/v1"}),
    "upstream": frozenset({"dcsmizzer.acknowledged-upstream-cache/v1"}),
    "airfields": frozenset({"dcsmizzer.dcs-airbase-beacons/v1"}),
    "runtime": frozenset({RUNTIME_ATTESTATION_SCHEMA}),
    "terrain": frozenset({TERRAIN_ATTESTATION_SCHEMA}),
}
_DOMAIN_ARTIFACT_DEPENDENCIES = {
    "modules": frozenset({"installation", "modules"}),
}


def create_evidence_snapshot(
    dcs_root: Path,
    bundle_root: Path,
    *,
    cache_root: Path | None = None,
    runtime_manifests: list[Path] | tuple[Path, ...] = (),
    terrain_evidence: list[Path] | tuple[Path, ...] = (),
    repository_root: Path | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """Collect two stable passes and write one content-addressed local bundle."""

    dcs = _existing_directory(Path(dcs_root), "DCS root")
    repository = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    runtime_inputs = _bounded_evidence_inputs(
        runtime_manifests,
        "runtime manifests",
    )
    terrain_inputs = _bounded_evidence_inputs(
        terrain_evidence,
        "terrain evidence",
    )
    git_before = _git_identity(repository)
    first = _collect_snapshot_pass(
        dcs,
        cache_root,
        runtime_inputs,
        terrain_inputs,
    )
    second = _collect_snapshot_pass(
        dcs,
        cache_root,
        runtime_inputs,
        terrain_inputs,
    )
    if _canonical_bytes(first) != _canonical_bytes(second):
        raise ValueError("evidence sources changed between the two collection passes")
    git_after = _git_identity(repository)
    if git_before != git_after:
        raise ValueError("evidence producer changed during collection")

    timestamp = _timestamp(created_utc)
    git = git_after
    artifacts = first["artifacts"]
    failures = first["failures"]
    artifact_payloads = {
        name: _canonical_bytes(report)
        for name, report in sorted(artifacts.items())
    }
    total_bytes = sum(len(payload) for payload in artifact_payloads.values())
    if not artifact_payloads or len(artifact_payloads) > MAX_ARTIFACTS:
        raise ValueError("evidence snapshot has an invalid artifact count")
    if any(
        not 1 <= len(payload) <= MAX_ARTIFACT_BYTES
        for payload in artifact_payloads.values()
    ):
        raise ValueError("evidence snapshot has an invalid artifact byte size")
    if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
        raise ValueError("evidence snapshot exceeds the total artifact byte limit")

    records: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for name, report in sorted(artifacts.items()):
        _validate_artifact_name(name)
        if "evidence_ref" in report:
            raise ValueError(
                f"evidence artifact {name} contains CLI transport metadata"
            )
        schema = report.get("schema")
        if not isinstance(schema, str) or schema not in KNOWN_REPORT_SCHEMAS:
            raise ValueError(f"evidence artifact {name} has an unknown report schema")
        if not _artifact_schema_allowed(name, schema):
            raise ValueError(f"evidence artifact {name} has the wrong domain schema")
        payload = artifact_payloads[name]
        records.append(
            {
                "name": name,
                "relative_path": f"artifacts/{name}.json",
                "schema": schema,
                "authority": _artifact_authority(report),
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        coverage.append(_coverage_record(name, report))

    producer = {
        "name": "DCSMizzer",
        "version": __version__,
        "git_commit": git.get("commit"),
        "git_dirty": git.get("dirty"),
    }
    core = {
        "schema": BUNDLE_SCHEMA,
        "created_utc": timestamp,
        "producer": producer,
        "identity": first["identity"],
        "collection": {
            "run_id": "snapshot-" + timestamp.replace("-", "").replace(
                ":",
                "",
            ),
            "passes": 2,
            "stable_across_passes": True,
            "outcome": "complete" if not failures else "partial",
            "failures": failures,
        },
        "artifacts": records,
        "coverage": coverage,
        "licensing": {
            "redistribution_reviewed": False,
            "local_only": True,
            "raw_initialized_dcs_export_committed": False,
        },
        "privacy": {
            "absolute_paths_recorded": False,
            "bundle_root_echoed": False,
            "report_claims_revalidated": False,
        },
    }
    bundle_id = hashlib.sha256(_canonical_bytes(core)).hexdigest()
    manifest = {
        **core,
        "bundle": {
            "algorithm": "sha256",
            "id": bundle_id,
            "content_address_basis": "canonical_manifest_without_bundle_field",
        },
    }
    manifest_payload = _canonical_bytes(manifest)
    if len(manifest_payload) > MAX_MANIFEST_BYTES:
        raise ValueError("evidence bundle manifest exceeds the byte limit")
    _validate_manifest_shape(manifest)
    _validate_artifact_consistency(manifest, artifacts)

    output_root = _safe_bundle_root(Path(bundle_root), create=True)
    final_path = output_root / bundle_id
    reused = _write_bundle(
        output_root,
        final_path,
        manifest_payload,
        artifact_payloads,
    )
    verified = verify_evidence_bundle(final_path)
    reproducible = (
        producer["git_commit"] is not None
        and producer["git_dirty"] is False
        and verified["validation"]["bundle_valid"] is True
    )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "dcs_started": False,
        "bundle": {
            "id": bundle_id,
            "directory_name": bundle_id,
            "root": "<caller-supplied-bundle-root>",
            "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "reused_existing_identical_bundle": reused,
        },
        "identity": first["identity"],
        "collection": {
            "artifacts": len(records),
            "artifact_bytes": total_bytes,
            "failures": failures,
            "coverage": coverage,
        },
        "producer": producer,
        "privacy": manifest["privacy"],
        "validation": {
            "snapshot_stable": True,
            "collection_complete": not failures,
            "bundle_valid": True,
            "content_address_verified": True,
            "reproducible_producer": reproducible,
            "coverage_unblocked": all(
                item["status"] != "blocked" for item in coverage
            ),
        },
    }


def verify_evidence_bundle(bundle_path: Path) -> dict[str, Any]:
    """Verify one complete bundle without trusting its manifest claims."""

    bundle = _safe_bundle_directory(Path(bundle_path), "evidence bundle")
    _validate_bundle_members(bundle)
    manifest_path = bundle / "manifest.json"
    raw_manifest = _read_bounded_report(manifest_path)
    if len(raw_manifest) > MAX_MANIFEST_BYTES:
        raise ValueError("evidence bundle manifest exceeds the byte limit")
    manifest = _parse_report_json(raw_manifest)
    if raw_manifest != _canonical_bytes(manifest):
        raise ValueError("evidence bundle manifest is not canonical JSON")
    _validate_manifest_shape(manifest)

    bundle_record = manifest["bundle"]
    bundle_id = bundle_record["id"]
    if bundle.name != bundle_id:
        raise ValueError("evidence bundle directory does not match its content ID")
    core = dict(manifest)
    del core["bundle"]
    computed_id = hashlib.sha256(_canonical_bytes(core)).hexdigest()
    if computed_id != bundle_id:
        raise ValueError("evidence bundle content address is invalid")

    artifact_results: list[dict[str, Any]] = []
    total_bytes = 0
    artifacts: dict[str, dict[str, Any]] = {}
    for record in manifest["artifacts"]:
        name = record["name"]
        _validate_artifact_name(name)
        expected_relative = f"artifacts/{name}.json"
        if record["relative_path"] != expected_relative:
            raise ValueError("evidence artifact path does not match its name")
        path = bundle / Path(expected_relative)
        raw = _read_bounded_report(path)
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("evidence bundle exceeds the total artifact byte limit")
        if len(raw) != record["size_bytes"]:
            raise ValueError(f"evidence artifact {name} size does not match")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != record["sha256"]:
            raise ValueError(f"evidence artifact {name} hash does not match")
        parsed = _parse_report_json(raw)
        if "evidence_ref" in parsed:
            raise ValueError(
                f"evidence artifact {name} contains CLI transport metadata"
            )
        if raw != _canonical_bytes(parsed):
            raise ValueError(f"evidence artifact {name} is not canonical JSON")
        if parsed.get("schema") != record["schema"]:
            raise ValueError(f"evidence artifact {name} schema does not match")
        if parsed["schema"] not in KNOWN_REPORT_SCHEMAS:
            raise ValueError(f"evidence artifact {name} schema is unknown")
        if not _artifact_schema_allowed(name, parsed["schema"]):
            raise ValueError(f"evidence artifact {name} domain schema is invalid")
        if _artifact_authority(parsed) != record["authority"]:
            raise ValueError(f"evidence artifact {name} authority does not match")
        expected_coverage = next(
            item
            for item in manifest["coverage"]
            if item["artifact"] == name
        )
        if _coverage_record(name, parsed) != expected_coverage:
            raise ValueError(f"evidence artifact {name} coverage does not match")
        artifacts[name] = parsed
        artifact_results.append(
            {
                "name": name,
                "schema": parsed["schema"],
                "size_bytes": len(raw),
                "sha256": digest,
                "verified": True,
            }
        )

    expected_names = {record["name"] for record in manifest["artifacts"]}
    actual_names = _artifact_directory_names(bundle / "artifacts")
    if actual_names != {f"{name}.json" for name in expected_names}:
        raise ValueError("evidence bundle contains unmanifested or missing artifacts")
    _validate_artifact_consistency(manifest, artifacts)

    return {
        "schema": VERIFICATION_SCHEMA,
        "dcs_started": False,
        "bundle": {
            "id": bundle_id,
            "directory_name": bundle.name,
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        },
        "identity": manifest["identity"],
        "producer": manifest["producer"],
        "collection": manifest["collection"],
        "coverage": manifest["coverage"],
        "artifacts": artifact_results,
        "privacy": {
            "absolute_paths_echoed": False,
            "claims_revalidated": False,
            "verification_scope": (
                "safe file identity, exact bytes, schema identifiers, manifest "
                "binding, and content address"
            ),
        },
        "validation": {
            "bundle_valid": True,
            "content_address_valid": True,
            "all_artifacts_present": True,
            "all_artifact_hashes_valid": True,
            "artifact_count": len(artifact_results),
            "artifact_bytes": total_bytes,
            "coverage_unblocked": all(
                item["status"] != "blocked"
                for item in manifest["coverage"]
            ),
        },
    }


def compare_evidence(before: Path, after: Path) -> dict[str, Any]:
    """Compare two bundle directories or recognized evidence JSON files."""

    before_source = _load_evidence_source(Path(before))
    after_source = _load_evidence_source(Path(after))
    try:
        before_normalized = _normalize_source(before_source)
        after_normalized = _normalize_source(after_source)
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError(
            "recognized evidence report has an invalid comparison shape"
        ) from error

    identity_fields = (
        "product_version",
        "distribution",
        "distribution_build",
        "executable_sha256",
        "sim_control_api_sha256",
    )
    identity_changes = {
        field: _scalar_change(
            before_normalized["identity"].get(field),
            after_normalized["identity"].get(field),
        )
        for field in identity_fields
    }
    domains: list[dict[str, Any]] = []
    before_domains = before_normalized["domains"]
    after_domains = after_normalized["domains"]
    for name in sorted(set(before_domains) | set(after_domains)):
        old = before_domains.get(name)
        new = after_domains.get(name)
        if old is None:
            status = "added"
        elif new is None:
            status = "removed"
        elif old["basis"] != new["basis"]:
            status = "incomparable_basis"
        elif old["fingerprint"] == new["fingerprint"]:
            status = "unchanged"
        else:
            status = "changed"
        domains.append(
            {
                "domain": name,
                "status": status,
                "before_basis": old["basis"] if old is not None else None,
                "after_basis": new["basis"] if new is not None else None,
                "before_fingerprint": (
                    old["fingerprint"] if old is not None else None
                ),
                "after_fingerprint": (
                    new["fingerprint"] if new is not None else None
                ),
                "before_summary": old["summary"] if old is not None else None,
                "after_summary": new["summary"] if new is not None else None,
            }
        )

    identity_changed = any(
        change["status"] in {"changed", "removed"}
        for change in identity_changes.values()
    )
    identity_comparison_complete = all(
        change["status"] == "unchanged"
        for change in identity_changes.values()
    )
    identity_conflict = any(
        change["status"] == "changed" for change in identity_changes.values()
    )
    invalidated_domains = [
        item["domain"]
        for item in domains
        if item["status"] in {"changed", "removed", "incomparable_basis"}
    ]
    return {
        "schema": DIFF_SCHEMA,
        "dcs_started": False,
        "before": before_source["reference"],
        "after": after_source["reference"],
        "identity": identity_changes,
        "domains": domains,
        "invalidation": {
            "installation_identity_changed": identity_changed,
            "invalidated_domains": invalidated_domains,
            "historical_source_preserved": True,
            "policy": (
                "changed, removed, or differently scoped evidence cannot be "
                "silently reused for a current decision"
            ),
        },
        "validation": {
            "sources_recognized": True,
            "comparison_complete": True,
            "identity_comparison_complete": identity_comparison_complete,
            "same_installation_identity": identity_comparison_complete,
            "no_conflicting_installation_identity": not identity_conflict,
        },
    }


def evidence_readiness(
    bundle_path: Path,
    dcs_root: Path,
    *,
    cache_root: Path | None = None,
    required_domains: list[str] | tuple[str, ...] = (),
    runtime_manifests: list[Path] | tuple[Path, ...] = (),
    terrain_evidence: list[Path] | tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Compare a bundle with live read-only identities and gate named domains."""

    required = _validate_required_domains(required_domains)
    runtime_inputs = _bounded_evidence_inputs(
        runtime_manifests,
        "runtime manifests",
    )
    terrain_inputs = _bounded_evidence_inputs(
        terrain_evidence,
        "terrain evidence",
    )
    bundle_source = _load_evidence_source(Path(bundle_path), require_bundle=True)
    dcs = _existing_directory(Path(dcs_root), "DCS root")
    live = _collect_snapshot_pass(
        dcs,
        cache_root,
        runtime_inputs,
        terrain_inputs,
    )
    live_confirmation = _collect_snapshot_pass(
        dcs,
        cache_root,
        runtime_inputs,
        terrain_inputs,
    )
    if _canonical_bytes(live) != _canonical_bytes(live_confirmation):
        raise ValueError("current evidence changed between readiness passes")
    live_source = {
        "reference": {
            "kind": "live_read_only_collection",
            "schema": SNAPSHOT_SCHEMA,
        },
        "manifest": {
            "identity": live["identity"],
            "coverage": [
                _coverage_record(name, report)
                for name, report in sorted(live["artifacts"].items())
            ],
        },
        "artifacts": live["artifacts"],
    }
    try:
        bundled = _normalize_source(bundle_source)
        current = _normalize_source(live_source)
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError(
            "verified evidence artifacts have an invalid readiness shape"
        ) from error
    bundle_coverage = _coverage_by_base(bundle_source["manifest"]["coverage"])
    current_coverage = _coverage_by_base(live_source["manifest"]["coverage"])
    domain_names = sorted(set(bundled["domains"]) | set(current["domains"]))
    records: list[dict[str, Any]] = []
    for name in domain_names:
        old = bundled["domains"].get(name)
        new = current["domains"].get(name)
        base = _base_domain(name)
        bundled_coverage = bundle_coverage.get(base, "absent")
        live_coverage = current_coverage.get(base, "absent")
        coverage = _readiness_coverage(bundled_coverage, live_coverage)
        if old is None:
            freshness = "absent_from_bundle"
        elif new is None:
            freshness = "current_check_unavailable"
        elif old["basis"] != new["basis"]:
            freshness = "incomparable_basis"
        elif old["fingerprint"] != new["fingerprint"]:
            freshness = "stale"
        else:
            freshness = "current"
        usable = freshness == "current" and coverage == "complete"
        records.append(
            {
                "domain": name,
                "base_domain": base,
                "required": base in required,
                "freshness": freshness,
                "bundle_coverage": bundled_coverage,
                "current_coverage": live_coverage,
                "coverage": coverage,
                "usable_for_required_decision": usable,
            }
        )

    producer = bundle_source["manifest"].get("producer", {})
    collection = bundle_source["manifest"].get("collection", {})
    decision = _readiness_decision(records, required, producer, collection)
    required_results = decision["required_domains"]
    producer_result = decision["producer"]
    overall = decision["all_required_domains_ready"]
    return {
        "schema": READINESS_SCHEMA,
        "dcs_started": False,
        "bundle": bundle_source["reference"],
        "current_identity": current["identity"],
        "required_domains": required_results,
        "producer": producer_result,
        "domains": records,
        "live_collection_failures": live["failures"],
        "live_collection": {
            "passes": 2,
            "stable_across_passes": True,
        },
        "limitations": [
            "Freshness compares exact normalized evidence, not DCS runtime behavior.",
            "Partial static authority remains partial even when its bytes are current.",
            "A domain absent from the live check cannot be assumed unchanged.",
        ],
        "validation": {
            "bundle_valid": True,
            "current_identity_collected": True,
            "reproducible_producer": producer_result["reproducible"],
            "all_required_domains_ready": overall,
        },
    }


def validate_evidence_readiness_report(
    readiness: Any,
    verification: Any,
    required_domains: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate a saved readiness report against one verified bundle result."""

    required = _validate_required_domains(required_domains)
    if (
        not isinstance(readiness, dict)
        or set(readiness)
        != {
            "schema",
            "dcs_started",
            "bundle",
            "current_identity",
            "required_domains",
            "producer",
            "domains",
            "live_collection_failures",
            "live_collection",
            "limitations",
            "validation",
        }
        or readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("dcs_started") is not False
        or not isinstance(readiness.get("bundle"), dict)
        or not isinstance(readiness.get("current_identity"), dict)
        or not isinstance(readiness.get("live_collection_failures"), list)
        or readiness.get("live_collection")
        != {"passes": 2, "stable_across_passes": True}
        or not isinstance(readiness.get("limitations"), list)
        or any(not isinstance(item, str) for item in readiness["limitations"])
        or not isinstance(verification, dict)
        or not isinstance(verification.get("bundle"), dict)
        or not isinstance(verification.get("producer"), dict)
        or not isinstance(verification.get("collection"), dict)
        or not isinstance(verification.get("coverage"), list)
    ):
        raise ValueError("evidence readiness report shape is invalid")
    decision = _readiness_decision(
        readiness.get("domains"),
        required,
        verification["producer"],
        verification["collection"],
    )
    bundle_coverage = _coverage_by_base(verification["coverage"])
    if any(
        item["bundle_coverage"]
        != bundle_coverage.get(item["base_domain"], "absent")
        for item in readiness["domains"]
    ):
        raise ValueError("evidence readiness bundle coverage is inconsistent")
    expected_validation = {
        "bundle_valid": True,
        "current_identity_collected": True,
        "reproducible_producer": decision["producer"]["reproducible"],
        "all_required_domains_ready": decision["all_required_domains_ready"],
    }
    if (
        readiness.get("bundle")
        != {
            "kind": "content_addressed_bundle",
            "schema": BUNDLE_SCHEMA,
            "bundle_id": verification["bundle"].get("id"),
        }
        or readiness.get("required_domains") != decision["required_domains"]
        or readiness.get("producer") != decision["producer"]
        or readiness.get("validation") != expected_validation
    ):
        raise ValueError("evidence readiness decision is inconsistent")
    return decision


def _readiness_decision(
    records: Any,
    required: frozenset[str],
    producer: Any,
    collection: Any,
) -> dict[str, Any]:
    if not isinstance(records, list):
        raise ValueError("evidence readiness domain records are invalid")
    names: list[str] = []
    freshness_values = {
        "absent_from_bundle",
        "current_check_unavailable",
        "incomparable_basis",
        "stale",
        "current",
    }
    coverage_values = {"absent", "complete", "partial", "blocked"}
    for item in records:
        if not isinstance(item, dict) or set(item) != {
            "domain",
            "base_domain",
            "required",
            "freshness",
            "bundle_coverage",
            "current_coverage",
            "coverage",
            "usable_for_required_decision",
        }:
            raise ValueError("evidence readiness domain record shape is invalid")
        name = item.get("domain")
        base = item.get("base_domain")
        freshness = item.get("freshness")
        bundled_coverage = item.get("bundle_coverage")
        current_coverage = item.get("current_coverage")
        coverage = item.get("coverage")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(base, str)
            or base != _base_domain(name)
            or base not in _REQUIRED_DOMAINS
            or item.get("required") is not (base in required)
            or not isinstance(freshness, str)
            or freshness not in freshness_values
            or not isinstance(bundled_coverage, str)
            or bundled_coverage not in coverage_values
            or not isinstance(current_coverage, str)
            or current_coverage not in coverage_values
            or coverage != _readiness_coverage(
                bundled_coverage,
                current_coverage,
            )
            or item.get("usable_for_required_decision")
            is not (freshness == "current" and coverage == "complete")
        ):
            raise ValueError("evidence readiness domain record is inconsistent")
        names.append(name)
    if names != sorted(set(names)):
        raise ValueError("evidence readiness domain records are unordered")

    required_results: dict[str, dict[str, Any]] = {}
    for domain in sorted(required):
        matching = [item for item in records if item["base_domain"] == domain]
        ready = bool(matching) and all(
            item["usable_for_required_decision"] for item in matching
        )
        required_results[domain] = {
            "ready": ready,
            "records": len(matching),
            "states": sorted(
                {
                    f"{item['freshness']}:{item['coverage']}"
                    for item in matching
                }
            ),
        }
    producer_reproducible = bool(
        isinstance(producer, dict)
        and producer.get("git_dirty") is False
        and isinstance(producer.get("git_commit"), str)
        and re.fullmatch(r"[0-9a-f]{40,64}", producer["git_commit"])
        and isinstance(collection, dict)
        and collection.get("stable_across_passes") is True
        and collection.get("outcome") == "complete"
    )
    producer_result = {
        "name": producer.get("name") if isinstance(producer, dict) else None,
        "version": producer.get("version") if isinstance(producer, dict) else None,
        "git_commit": (
            producer.get("git_commit") if isinstance(producer, dict) else None
        ),
        "reproducible": producer_reproducible,
    }
    return {
        "required_domains": required_results,
        "producer": producer_result,
        "all_required_domains_ready": bool(
            producer_reproducible
            and all(item["ready"] for item in required_results.values())
        ),
    }


def required_evidence_domains() -> tuple[str, ...]:
    """Return the stable CLI choice list."""

    return tuple(sorted(_REQUIRED_DOMAINS))


def current_report_evidence_context(
    bundle_path: Path,
    dcs_root: Path,
    *,
    report_command: str,
    query_sha256: str,
    mandatory_domains: list[str] | tuple[str, ...],
    source_roots_matched: bool,
    cache_root: Path | None = None,
    required_domains: list[str] | tuple[str, ...] = (),
    runtime_manifests: list[Path] | tuple[Path, ...] = (),
    terrain_evidence: list[Path] | tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Return a reference plus its exact verified readiness preimages."""

    required_values = _validate_required_domains(required_domains)
    mandatory_values = _binding_domains(
        mandatory_domains,
        label="mandatory report domains",
    )
    if not mandatory_values <= required_values:
        raise ValueError("mandatory report domains are not all required")
    if (
        not isinstance(report_command, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", report_command) is None
        or not isinstance(query_sha256, str)
        or _HASH.fullmatch(query_sha256) is None
        or not isinstance(source_roots_matched, bool)
    ):
        raise ValueError("report evidence binding identity is invalid")

    repository = Path(__file__).resolve().parents[2]
    git_before = _git_identity(repository)
    initial = verify_evidence_bundle(Path(bundle_path))
    readiness = evidence_readiness(
        Path(bundle_path),
        Path(dcs_root),
        cache_root=cache_root,
        required_domains=sorted(required_values),
        runtime_manifests=runtime_manifests,
        terrain_evidence=terrain_evidence,
    )
    confirmation = verify_evidence_bundle(Path(bundle_path))
    git_after = _git_identity(repository)
    if initial != confirmation:
        raise ValueError("evidence bundle changed while binding a report")
    if git_before != git_after:
        raise ValueError("report evidence producer changed while binding")

    required_results = readiness["required_domains"]
    required_status = {
        name: item["ready"] is True
        for name, item in required_results.items()
    }
    bundle_producer = initial["producer"]
    current_producer = {
        "name": "DCSMizzer",
        "version": __version__,
        "git_commit": git_after.get("commit"),
        "git_dirty": git_after.get("dirty"),
    }
    reproducible_current = bool(
        isinstance(current_producer["git_commit"], str)
        and re.fullmatch(
            r"[0-9a-f]{40,64}",
            current_producer["git_commit"],
        )
        and current_producer["git_dirty"] is False
    )
    producer_matches = bool(
        reproducible_current
        and bundle_producer.get("name") == current_producer["name"]
        and bundle_producer.get("version") == current_producer["version"]
        and bundle_producer.get("git_commit") == current_producer["git_commit"]
        and bundle_producer.get("git_dirty") is False
    )
    required_ready = bool(
        readiness["validation"]["all_required_domains_ready"] is True
        and all(required_status.values())
    )
    current_revalidated = bool(
        readiness["live_collection"]["passes"] == 2
        and readiness["live_collection"]["stable_across_passes"] is True
    )
    ready = bool(
        source_roots_matched
        and required_ready
        and current_revalidated
        and reproducible_current
        and producer_matches
    )
    reference = {
        "schema": REPORT_EVIDENCE_REF_SCHEMA,
        "status": "bundle-current" if ready else "unbound",
        "bundle": {
            "id": initial["bundle"]["id"],
            "manifest_sha256": initial["bundle"]["manifest_sha256"],
        },
        "authority_tier": (
            "current_verified_binding_context" if ready else "report_intrinsic_only"
        ),
        "producer": {
            "bundle": bundle_producer,
            "current": current_producer,
        },
        "required_domains": required_status,
        "domain_artifact_bindings": _domain_artifact_bindings(
            initial,
            tuple(required_results),
        ),
        "current_readiness": {
            "schema": readiness["schema"],
            "canonical_sha256": hashlib.sha256(
                _canonical_bytes(readiness)
            ).hexdigest(),
            "live_collection_passes": readiness["live_collection"]["passes"],
            "stable_across_passes": readiness["live_collection"][
                "stable_across_passes"
            ],
            "live_collection_failures": len(
                readiness["live_collection_failures"]
            ),
        },
        "report_binding": {
            "command": report_command,
            "query_sha256": query_sha256,
            "mandatory_domains": sorted(mandatory_values),
            "source_roots_matched": source_roots_matched,
        },
        "limitations": [
            (
                "Binding proves current bundle context for the command's mandatory "
                "domains; report fields retain their own declared authority."
            ),
            "Additional caller-required domains participate in the readiness gate.",
            "Static or planning evidence is never upgraded to DCS runtime validity.",
        ],
        "validation": {
            "bundle_reference_present": True,
            "bundle_integrity_verified": True,
            "bundle_stable_during_binding": True,
            "current_state_revalidated": current_revalidated,
            "required_domains_ready": required_ready,
            "reproducible_current_producer": reproducible_current,
            "current_producer_matches_bundle": producer_matches,
            "evidence_ready_for_binding": ready,
        },
    }
    return {
        "reference": reference,
        "readiness": readiness,
        "verification": initial,
    }


def current_report_evidence_reference(
    bundle_path: Path,
    dcs_root: Path,
    *,
    report_command: str,
    query_sha256: str,
    mandatory_domains: list[str] | tuple[str, ...],
    source_roots_matched: bool,
    cache_root: Path | None = None,
    required_domains: list[str] | tuple[str, ...] = (),
    runtime_manifests: list[Path] | tuple[Path, ...] = (),
    terrain_evidence: list[Path] | tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Build a path-free reference after live two-pass readiness validation."""

    context = current_report_evidence_context(
        bundle_path,
        dcs_root,
        report_command=report_command,
        query_sha256=query_sha256,
        mandatory_domains=mandatory_domains,
        source_roots_matched=source_roots_matched,
        cache_root=cache_root,
        required_domains=required_domains,
        runtime_manifests=runtime_manifests,
        terrain_evidence=terrain_evidence,
    )
    return context["reference"]


def _binding_domains(values: Any, *, label: str) -> frozenset[str]:
    if (
        not isinstance(values, (list, tuple))
        or not values
        or len(values) > len(_REQUIRED_DOMAINS)
        or any(not isinstance(value, str) for value in values)
    ):
        raise ValueError(f"{label} are invalid")
    domains = frozenset(values)
    if len(domains) != len(values) or not domains <= _REQUIRED_DOMAINS:
        raise ValueError(f"{label} are duplicate or unknown")
    return domains


def _domain_artifact_bindings(
    verification: dict[str, Any],
    domains: tuple[str, ...],
) -> dict[str, str]:
    coverage = {
        item["artifact"]: item
        for item in verification["coverage"]
        if isinstance(item, dict) and isinstance(item.get("artifact"), str)
    }
    output: dict[str, str] = {}
    for domain in sorted(domains):
        artifact_domains = _DOMAIN_ARTIFACT_DEPENDENCIES.get(
            domain,
            frozenset({domain}),
        )
        records = [
            {
                "name": item["name"],
                "schema": item["schema"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
                "verified": item["verified"],
                "coverage": coverage.get(item["name"]),
            }
            for item in verification["artifacts"]
            if _snapshot_artifact_domain(item.get("name")) in artifact_domains
        ]
        output[domain] = hashlib.sha256(_canonical_bytes(records)).hexdigest()
    return output


def _collect_snapshot_pass(
    dcs_root: Path,
    cache_root: Path | None,
    runtime_manifests: tuple[Path, ...] = (),
    terrain_evidence: tuple[Path, ...] = (),
) -> dict[str, Any]:
    installation = static_install_report(dcs_root)
    identity = _installation_identity(dcs_root, installation)
    artifacts: dict[str, dict[str, Any]] = {
        "installation": installation,
        "capabilities": capabilities_report(),
    }
    failures: list[dict[str, str]] = []
    collectors: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
        ("countries", lambda: countries_report(dcs_root)),
        ("modules", lambda: module_index_report(dcs_root)),
        ("payloads", lambda: payload_index_report(dcs_root)),
        ("weather", lambda: weather_registry_report(dcs_root)),
    )
    for name, collector in collectors:
        _collect_optional(artifacts, failures, name, collector)

    terrain_records = installation.get("installed_module_directories", {}).get(
        "terrains",
        [],
    )
    if isinstance(terrain_records, list):
        for item in terrain_records:
            directory = item.get("directory") if isinstance(item, dict) else None
            if not isinstance(directory, str) or not directory:
                continue
            qualifier = _artifact_qualifier(directory)
            name = f"airfields.{qualifier}"
            if name in artifacts:
                raise ValueError(
                    "installed terrain identities collide after safe normalization"
                )
            _collect_optional(
                artifacts,
                failures,
                name,
                lambda terrain=directory: airbase_beacon_report(
                    dcs_root,
                    terrain,
                ),
            )
    if cache_root is not None:
        _collect_optional(
            artifacts,
            failures,
            "upstream",
            lambda: upstream_status_report(Path(cache_root)),
        )
    for manifest_path in runtime_manifests:
        report = runtime_attestation(manifest_path)
        name = runtime_artifact_name(report)
        _add_bound_artifact(artifacts, name, report)
    for evidence_path in terrain_evidence:
        report = terrain_attestation(evidence_path)
        name = terrain_artifact_name(report)
        _add_bound_artifact(artifacts, name, report)
    return {
        "identity": identity,
        "artifacts": artifacts,
        "failures": failures,
    }


def _add_bound_artifact(
    artifacts: dict[str, dict[str, Any]],
    name: str,
    report: dict[str, Any],
) -> None:
    if name in artifacts:
        raise ValueError("bound evidence artifact identity is duplicated")
    artifacts[name] = report


def _collect_optional(
    artifacts: dict[str, dict[str, Any]],
    failures: list[dict[str, str]],
    name: str,
    collector: Callable[[], dict[str, Any]],
) -> None:
    try:
        artifacts[name] = collector()
    except (OSError, ValueError) as error:
        failures.append(
            {
                "artifact": name,
                "error_type": type(error).__name__,
                "message": (
                    "collector rejected or could not read its bounded source; "
                    "run the exact domain command for sanitized diagnostics"
                ),
            }
        )


def _installation_identity(
    dcs_root: Path,
    installation: dict[str, Any],
) -> dict[str, Any]:
    distribution, build, _launcher = _distribution_identity(dcs_root)
    executable = _select_dcs_executable(
        dcs_root,
        prefer_steam_target=distribution == "steam",
    )
    product_version = _windows_product_version(executable)
    reported = installation.get("dcs", {}).get("product_version")
    if reported is not None and reported != product_version:
        raise ValueError("DCS product version changed during evidence collection")
    api = _optional_source_record(
        dcs_root / "API" / "Sim_ControlAPI.md",
        dcs_root,
    )
    executable_record = {
        "relative_path": executable.relative_to(dcs_root).as_posix(),
        "size_bytes": executable.stat().st_size,
        "sha256": _sha256_file(executable, MAX_MISSION_BYTES),
    }
    return {
        "dcs": {
            "product_version": product_version,
            "distribution": distribution,
            "distribution_build": build,
            "executable": executable_record,
            "sim_control_api": api,
        },
        "terrain_directories": sorted(
            (
                item["directory"]
                for item in installation.get(
                    "installed_module_directories",
                    {},
                ).get("terrains", [])
                if isinstance(item, dict)
                and isinstance(item.get("directory"), str)
            ),
            key=str.casefold,
        ),
    }


def _coverage_record(name: str, report: dict[str, Any]) -> dict[str, Any]:
    base = _base_domain(name)
    status = "complete"
    reason = "the collected report passed its finite static collection scope"
    if base == "installation":
        reason = "exact installation identity and current static summary collected"
    elif base == "modules":
        status = "partial"
        reason = "static declarations do not prove entitlement or runtime activation"
    elif base == "payloads":
        failures = report.get("parse_failures")
        if failures or report.get("compatibility_complete") is not True:
            status = "partial"
            reason = (
                "default-preset observations are incomplete compatibility evidence"
            )
    elif base == "airfields":
        status = "partial"
        reason = (
            "static radio/beacon records are not a complete initialized "
            "airfield registry"
        )
    elif base == "upstream":
        validation = report.get("validation")
        if not isinstance(validation, dict) or (
            validation.get("all_sources_usable") is not True
        ):
            status = "blocked"
            reason = "one or more acknowledged upstream source locks are unusable"
    elif base == "weather":
        if not _weather_coverage_complete(report):
            status = "partial"
            reason = (
                "current weather presets are missing, failed, incomplete, "
                "inconsistent, filtered, or truncated"
            )
    elif base == "countries":
        duplicates = report.get("duplicate_identifiers")
        if duplicates:
            status = "blocked"
            reason = "country identifiers are ambiguous"
    elif base == "runtime":
        status, reason = runtime_coverage(report)
    elif base == "terrain":
        status, reason = terrain_coverage(report)
    return {
        "artifact": name,
        "domain": base,
        "status": status,
        "reason": reason,
    }


def _weather_coverage_complete(report: dict[str, Any]) -> bool:
    coverage = report.get("coverage")
    failures = report.get("parse_failures")
    presets = report.get("presets")
    filters = report.get("filter")
    if (
        not isinstance(coverage, dict)
        or not isinstance(failures, list)
        or not isinstance(presets, list)
        or not isinstance(filters, dict)
        or filters.get("preset") is not None
    ):
        return False
    names = (
        "source_files",
        "parsed_presets",
        "parse_failures",
        "fields_complete_presets",
        "fields_incomplete_presets",
        "consistent_presets",
        "usable_presets",
        "matching_presets",
        "returned_presets",
    )
    if any(
        isinstance(coverage.get(name), bool)
        or not isinstance(coverage.get(name), int)
        or coverage[name] < 0
        for name in names
    ):
        return False
    parsed = coverage["parsed_presets"]
    failed = coverage["parse_failures"]
    return bool(
        coverage["source_files"] > 0
        and parsed > 0
        and coverage["source_files"] == parsed + failed
        and failed == len(failures) == 0
        and coverage["fields_complete_presets"] == parsed
        and coverage["fields_incomplete_presets"] == 0
        and coverage["consistent_presets"] == parsed
        and coverage["usable_presets"] == parsed
        and coverage["matching_presets"] == parsed
        and coverage["returned_presets"] == parsed == len(presets)
        and coverage.get("truncated") is False
    )


def _artifact_authority(report: dict[str, Any]) -> str:
    authority = report.get("authority")
    if isinstance(authority, str) and authority:
        return authority[:256]
    schema = report.get("schema")
    if schema == "dcsmizzer.capabilities/v3":
        return "product_declared_capability_matrix"
    if schema == "dcsmizzer.acknowledged-upstream-cache/v1":
        return "immutable_acknowledged_upstream_pins"
    return "schema_identified_report_claims_not_revalidated"


def _write_bundle(
    root: Path,
    final_path: Path,
    manifest_payload: bytes,
    artifact_payloads: dict[str, bytes],
) -> bool:
    if final_path.exists():
        verify_evidence_bundle(final_path)
        return True
    staging = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=root))
    try:
        artifacts_dir = staging / "artifacts"
        artifacts_dir.mkdir()
        for name, payload in sorted(artifact_payloads.items()):
            _write_new_file(artifacts_dir / f"{name}.json", payload)
        _write_new_file(staging / "manifest.json", manifest_payload)
        try:
            os.replace(staging, final_path)
        except OSError:
            if not final_path.exists():
                raise
            verify_evidence_bundle(final_path)
            _remove_staging(staging, root)
            return True
        return False
    except BaseException:
        if staging.exists():
            _remove_staging(staging, root)
        raise


def _remove_staging(staging: Path, root: Path) -> None:
    candidate = staging.absolute()
    if candidate.parent != root or not candidate.name.startswith(_STAGING_PREFIX):
        raise ValueError("refusing to remove an unrecognized evidence staging path")
    status_result = candidate.lstat()
    if not stat.S_ISDIR(status_result.st_mode) or _is_reparse(status_result):
        raise ValueError("refusing to remove an unsafe evidence staging path")
    for item in candidate.iterdir():
        item_status = item.lstat()
        if item.name == "manifest.json":
            if not stat.S_ISREG(item_status.st_mode) or _is_reparse(item_status):
                raise ValueError("refusing to remove an unsafe staging manifest")
            item.unlink()
            continue
        if item.name != "artifacts":
            raise ValueError("refusing to remove unrecognized staging content")
        if not stat.S_ISDIR(item_status.st_mode) or _is_reparse(item_status):
            raise ValueError("refusing to remove an unsafe staging artifact directory")
        for artifact in item.iterdir():
            artifact_status = artifact.lstat()
            if (
                not stat.S_ISREG(artifact_status.st_mode)
                or _is_reparse(artifact_status)
            ):
                raise ValueError("refusing to remove unsafe staging artifact content")
            artifact.unlink()
        item.rmdir()
    candidate.rmdir()


def _safe_bundle_root(path: Path, *, create: bool) -> Path:
    candidate = path.absolute()
    if candidate == Path(candidate.anchor):
        raise ValueError("bundle root must not be a filesystem root")
    if not candidate.exists():
        if not create:
            raise ValueError("bundle root does not exist")
        parent = _safe_bundle_directory(candidate.parent, "bundle-root parent")
        try:
            candidate.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if candidate.parent.resolve() != parent:
            raise ValueError("bundle root parent changed while being created")
    return _safe_bundle_directory(candidate, "bundle root")


def _safe_bundle_directory(path: Path, label: str) -> Path:
    return canonical_existing_directory(path, label)


def _artifact_directory_names(path: Path) -> set[str]:
    directory = _safe_bundle_directory(path, "evidence artifact directory")
    names: set[str] = set()
    for item in directory.iterdir():
        if len(names) >= MAX_ARTIFACTS:
            raise ValueError("evidence artifact directory has too many entries")
        status_result = item.lstat()
        if not stat.S_ISREG(status_result.st_mode) or _is_reparse(status_result):
            raise ValueError("evidence artifact directory contains an unsafe entry")
        names.add(item.name)
    return names


def _validate_bundle_members(bundle: Path) -> None:
    entries: dict[str, Path] = {}
    for item in bundle.iterdir():
        if len(entries) >= 2:
            raise ValueError(
                "evidence bundle contains unmanifested root entries "
                "(too many entries)"
            )
        entries[item.name] = item
    if set(entries) != {"artifacts", "manifest.json"}:
        raise ValueError("evidence bundle contains unmanifested root entries")
    manifest_status = entries["manifest.json"].lstat()
    artifacts_status = entries["artifacts"].lstat()
    if (
        not stat.S_ISREG(manifest_status.st_mode)
        or _is_reparse(manifest_status)
        or not stat.S_ISDIR(artifacts_status.st_mode)
        or _is_reparse(artifacts_status)
    ):
        raise ValueError("evidence bundle root contains an unsafe entry")


def _validate_manifest_shape(manifest: dict[str, Any]) -> None:
    required = {
        "schema",
        "created_utc",
        "producer",
        "identity",
        "collection",
        "artifacts",
        "coverage",
        "licensing",
        "privacy",
        "bundle",
    }
    if set(manifest) != required or manifest.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("evidence bundle manifest shape or schema is invalid")
    _timestamp(manifest.get("created_utc"))
    producer = manifest.get("producer")
    if not isinstance(producer, dict) or set(producer) != {
        "name",
        "version",
        "git_commit",
        "git_dirty",
    }:
        raise ValueError("evidence bundle producer record is invalid")
    if (
        producer.get("name") != "DCSMizzer"
        or not isinstance(producer.get("version"), str)
        or not 1 <= len(producer["version"]) <= 64
    ):
        raise ValueError("evidence bundle producer identity is invalid")
    git_commit = producer.get("git_commit")
    if git_commit is not None and not (
        isinstance(git_commit, str)
        and re.fullmatch(r"[0-9a-f]{40,64}", git_commit)
    ):
        raise ValueError("evidence bundle producer commit is invalid")
    git_dirty = producer.get("git_dirty")
    if git_dirty is not None and not isinstance(git_dirty, bool):
        raise ValueError("evidence bundle producer cleanliness is invalid")
    _validate_bundle_identity(manifest.get("identity"))
    collection = manifest.get("collection")
    if not isinstance(collection, dict) or set(collection) != {
        "run_id",
        "passes",
        "stable_across_passes",
        "outcome",
        "failures",
    }:
        raise ValueError("evidence bundle collection record is invalid")
    if (
        not isinstance(collection.get("run_id"), str)
        or _COLLECTION_RUN_ID.fullmatch(collection["run_id"]) is None
        or collection.get("passes") != 2
        or collection.get("stable_across_passes") is not True
        or collection.get("outcome") not in {"complete", "partial"}
        or not isinstance(collection.get("failures"), list)
        or len(collection["failures"]) > MAX_ARTIFACTS
    ):
        raise ValueError("evidence bundle collection values are invalid")
    failure_names: set[str] = set()
    for failure in collection["failures"]:
        if not isinstance(failure, dict) or set(failure) != {
            "artifact",
            "error_type",
            "message",
        }:
            raise ValueError("evidence bundle collection failure is invalid")
        failure_name = failure.get("artifact")
        _validate_artifact_name(failure_name)
        if (
            _snapshot_artifact_domain(failure_name) is None
            or failure_name in {"installation", "capabilities"}
            or failure_name in failure_names
        ):
            raise ValueError("evidence bundle collection failure is invalid")
        failure_names.add(failure_name)
        if not all(
            isinstance(failure.get(field), str)
            and 1 <= len(failure[field]) <= 256
            for field in ("error_type", "message")
        ):
            raise ValueError("evidence bundle collection failure is invalid")
    if (collection["outcome"] == "complete") != (not collection["failures"]):
        raise ValueError("evidence bundle collection outcome is inconsistent")
    records = manifest.get("artifacts")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_ARTIFACTS:
        raise ValueError("evidence bundle artifact manifest is invalid")
    names: set[str] = set()
    ordered_names: list[str] = []
    total = 0
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "name",
            "relative_path",
            "schema",
            "authority",
            "size_bytes",
            "sha256",
        }:
            raise ValueError("evidence bundle artifact record is invalid")
        name = record.get("name")
        _validate_artifact_name(name)
        if name in names:
            raise ValueError("evidence bundle artifact names are not unique")
        names.add(name)
        ordered_names.append(name)
        size = record.get("size_bytes")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or not 1 <= size <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError("evidence bundle artifact size is invalid")
        total += size
        if total > MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("evidence bundle artifact bytes exceed the limit")
        if record.get("schema") not in KNOWN_REPORT_SCHEMAS or not (
            _artifact_schema_allowed(name, record["schema"])
        ):
            raise ValueError("evidence bundle artifact schema is invalid")
        if record.get("relative_path") != f"artifacts/{name}.json":
            raise ValueError("evidence bundle artifact path is invalid")
        if (
            not isinstance(record.get("authority"), str)
            or not 1 <= len(record["authority"]) <= 256
        ):
            raise ValueError("evidence bundle artifact authority is invalid")
        if not isinstance(record.get("sha256"), str) or _HASH.fullmatch(
            record["sha256"]
        ) is None:
            raise ValueError("evidence bundle artifact hash is invalid")
    if ordered_names != sorted(ordered_names):
        raise ValueError("evidence bundle artifact records are not ordered")
    if not {"installation", "capabilities"} <= names:
        raise ValueError("evidence bundle is missing a mandatory artifact")
    if failure_names & names:
        raise ValueError("evidence artifact cannot be both collected and failed")
    terrain_names = {
        f"airfields.{_artifact_qualifier(directory)}"
        for directory in manifest["identity"]["terrain_directories"]
    }
    required_optional_names = {
        "countries",
        "modules",
        "payloads",
        "weather",
        *terrain_names,
    }
    if not required_optional_names <= names | failure_names:
        raise ValueError("evidence bundle omits a required collection result")
    fixed_allowed_names = {
        "installation",
        "capabilities",
        "upstream",
        *required_optional_names,
    }
    unexpected_names = {
        name
        for name in names | failure_names
        if name not in fixed_allowed_names
        and _snapshot_artifact_domain(name) not in {"runtime", "terrain"}
    }
    if unexpected_names:
        raise ValueError("evidence bundle contains an unexpected collection result")
    coverage = manifest.get("coverage")
    if not isinstance(coverage, list) or len(coverage) != len(records):
        raise ValueError("evidence bundle coverage manifest is invalid")
    coverage_names: list[str] = []
    for item in coverage:
        if not isinstance(item, dict) or set(item) != {
            "artifact",
            "domain",
            "status",
            "reason",
        }:
            raise ValueError("evidence bundle coverage record is invalid")
        artifact = item.get("artifact")
        domain = item.get("domain")
        if (
            not isinstance(artifact, str)
            or artifact not in names
            or domain not in _REQUIRED_DOMAINS
            or domain != _base_domain(artifact)
            or item.get("status") not in {"complete", "partial", "blocked"}
            or not isinstance(item.get("reason"), str)
            or not 1 <= len(item["reason"]) <= 512
        ):
            raise ValueError("evidence bundle coverage record is invalid")
        coverage_names.append(artifact)
    if set(coverage_names) != names:
        raise ValueError("evidence bundle coverage does not match its artifacts")
    if coverage_names != sorted(names):
        raise ValueError("evidence bundle coverage records are not ordered")
    _validate_policy_records(manifest)
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict) or set(bundle) != {
        "algorithm",
        "id",
        "content_address_basis",
    }:
        raise ValueError("evidence bundle identity record is invalid")
    if (
        bundle.get("algorithm") != "sha256"
        or bundle.get("content_address_basis")
        != "canonical_manifest_without_bundle_field"
        or not isinstance(bundle.get("id"), str)
        or _BUNDLE_ID.fullmatch(bundle["id"]) is None
    ):
        raise ValueError("evidence bundle content ID is invalid")


def _validate_bundle_identity(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "dcs",
        "terrain_directories",
    }:
        raise ValueError("evidence bundle identity is invalid")
    dcs = value.get("dcs")
    if not isinstance(dcs, dict) or set(dcs) != {
        "product_version",
        "distribution",
        "distribution_build",
        "executable",
        "sim_control_api",
    }:
        raise ValueError("evidence bundle DCS identity is invalid")
    if (
        not isinstance(dcs.get("product_version"), str)
        or not 1 <= len(dcs["product_version"]) <= 64
        or dcs.get("distribution") not in {"steam", "standalone"}
        or (
            dcs.get("distribution_build") is not None
            and (
                not isinstance(dcs["distribution_build"], str)
                or re.fullmatch(r"[0-9]{1,32}", dcs["distribution_build"])
                is None
            )
        )
    ):
        raise ValueError("evidence bundle DCS identity values are invalid")
    _validate_source_record(
        dcs.get("executable"),
        "DCS executable",
        maximum_bytes=MAX_MISSION_BYTES,
    )
    if dcs.get("sim_control_api") is not None:
        _validate_source_record(
            dcs["sim_control_api"],
            "DCS control API",
            maximum_bytes=MAX_ARTIFACT_BYTES,
        )
    terrains = value.get("terrain_directories")
    if (
        not isinstance(terrains, list)
        or len(terrains) > 128
        or terrains != sorted(terrains, key=str.casefold)
        or len({item.casefold() for item in terrains if isinstance(item, str)})
        != len(terrains)
        or any(
            not isinstance(item, str)
            or not 1 <= len(item) <= 128
            or item in {".", ".."}
            or any(separator in item for separator in ("/", "\\", ":"))
            or any(ord(character) < 0x20 for character in item)
            for item in terrains
        )
    ):
        raise ValueError("evidence bundle terrain identities are invalid")
    if len({_artifact_qualifier(item) for item in terrains}) != len(terrains):
        raise ValueError("evidence bundle terrain identities collide")


def _validate_source_record(
    value: Any,
    label: str,
    *,
    maximum_bytes: int,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "relative_path",
        "size_bytes",
        "sha256",
    }:
        raise ValueError(f"evidence bundle {label} record is invalid")
    relative = value.get("relative_path")
    size = value.get("size_bytes")
    digest = value.get("sha256")
    if (
        not isinstance(relative, str)
        or not 1 <= len(relative) <= 256
        or relative.startswith("/")
        or "\\" in relative
        or ":" in relative
        or any(ord(character) < 0x20 for character in relative)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= maximum_bytes
        or not isinstance(digest, str)
        or _HASH.fullmatch(digest) is None
    ):
        raise ValueError(f"evidence bundle {label} values are invalid")


def _validate_policy_records(manifest: dict[str, Any]) -> None:
    licensing = manifest.get("licensing")
    if not isinstance(licensing, dict) or licensing != {
        "redistribution_reviewed": False,
        "local_only": True,
        "raw_initialized_dcs_export_committed": False,
    }:
        raise ValueError("evidence bundle licensing policy is invalid")
    privacy = manifest.get("privacy")
    if not isinstance(privacy, dict) or privacy != {
        "absolute_paths_recorded": False,
        "bundle_root_echoed": False,
        "report_claims_revalidated": False,
    }:
        raise ValueError("evidence bundle privacy policy is invalid")


def _validate_artifact_consistency(
    manifest: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> None:
    installation = artifacts.get("installation")
    if not isinstance(installation, dict):
        raise ValueError(  # noqa: TRY004 - malformed external JSON value
            "evidence bundle installation artifact is invalid"
        )
    installation_dcs = installation.get("dcs")
    installed = installation.get("installed_module_directories")
    terrain_records = installed.get("terrains") if isinstance(installed, dict) else None
    if not isinstance(installation_dcs, dict) or not isinstance(
        terrain_records,
        list,
    ):
        raise ValueError(  # noqa: TRY004 - malformed external JSON value
            "evidence bundle installation artifact shape is invalid"
        )
    terrain_directories: list[str] = []
    for record in terrain_records:
        directory = record.get("directory") if isinstance(record, dict) else None
        if not isinstance(directory, str):
            raise ValueError(  # noqa: TRY004 - malformed external JSON value
                "evidence bundle terrain record is invalid"
            )
        terrain_directories.append(directory)
    terrain_directories.sort(key=str.casefold)
    identity = manifest["identity"]
    identity_dcs = identity["dcs"]
    if (
        installation_dcs.get("product_version")
        != identity_dcs["product_version"]
        or installation_dcs.get("steam_build_id")
        != identity_dcs["distribution_build"]
        or terrain_directories != identity["terrain_directories"]
    ):
        raise ValueError("evidence bundle installation identity is inconsistent")
    terrain_by_artifact = {
        f"airfields.{_artifact_qualifier(directory)}": directory
        for directory in terrain_directories
    }
    for name, report in artifacts.items():
        if name.startswith("airfields.") and report.get(
            "terrain_directory"
        ) != terrain_by_artifact.get(name):
            raise ValueError("evidence bundle airfield identity is inconsistent")
        if name.startswith("runtime."):
            validate_runtime_attestation(report)
            if name != runtime_artifact_name(report):
                raise ValueError("runtime evidence artifact identity is inconsistent")
            runtime_dcs = report["dcs"]
            if (
                runtime_dcs["product_version"]
                != identity_dcs["product_version"]
                or runtime_dcs["distribution"] != identity_dcs["distribution"]
                or runtime_dcs["distribution_build"]
                != identity_dcs["distribution_build"]
                or runtime_dcs["executable"]["sha256"]
                != identity_dcs["executable"]["sha256"]
                or runtime_dcs.get("sim_control_api")
                != identity_dcs.get("sim_control_api")
            ):
                raise ValueError("runtime evidence installation identity conflicts")
        if name.startswith("terrain."):
            validate_terrain_attestation(report)
            if name != terrain_artifact_name(report):
                raise ValueError("terrain evidence artifact identity is inconsistent")
            terrain_dcs = report["dcs"]
            if (
                terrain_dcs["product_version"]
                != identity_dcs["product_version"]
                or (
                    terrain_dcs["steam_build_id"] is not None
                    and terrain_dcs["steam_build_id"]
                    != identity_dcs["distribution_build"]
                )
            ):
                raise ValueError("terrain evidence installation identity conflicts")


def _load_evidence_source(
    path: Path,
    *,
    require_bundle: bool = False,
) -> dict[str, Any]:
    if path.is_dir():
        verification = verify_evidence_bundle(path)
        raw_manifest = _read_bounded_report(path / "manifest.json")
        if hashlib.sha256(raw_manifest).hexdigest() != verification["bundle"][
            "manifest_sha256"
        ]:
            raise ValueError("evidence bundle changed after verification")
        manifest = _parse_report_json(raw_manifest)
        artifacts: dict[str, dict[str, Any]] = {}
        for record in manifest["artifacts"]:
            raw = _read_bounded_report(path / record["relative_path"])
            if (
                len(raw) != record["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != record["sha256"]
            ):
                raise ValueError("evidence bundle changed after verification")
            artifacts[record["name"]] = _parse_report_json(raw)
        confirmation = verify_evidence_bundle(path)
        if confirmation["bundle"] != verification["bundle"] or confirmation[
            "artifacts"
        ] != verification["artifacts"]:
            raise ValueError("evidence bundle changed while it was being loaded")
        return {
            "reference": {
                "kind": "content_addressed_bundle",
                "schema": BUNDLE_SCHEMA,
                "bundle_id": verification["bundle"]["id"],
            },
            "manifest": manifest,
            "artifacts": artifacts,
        }
    if require_bundle:
        raise ValueError("readiness requires a content-addressed evidence bundle")
    raw = _read_bounded_report(path)
    report = _parse_report_json(raw)
    schema = report.get("schema")
    if schema == BUNDLE_SCHEMA:
        return _load_evidence_source(path.parent)
    if schema not in KNOWN_REPORT_SCHEMAS:
        raise ValueError("evidence source does not use a recognized schema")
    # ``evidence_ref`` is CLI transport metadata attached after a report has
    # been produced.  It is not part of the report's intrinsic evidence and
    # therefore must not create semantic drift when comparing standalone
    # reports.  Keep the raw-byte digest in ``reference`` below so physical
    # file identity remains exact even though normalization ignores this one
    # top-level transport field.
    report = dict(report)
    report.pop("evidence_ref", None)
    return {
        "reference": {
            "kind": "standalone_report",
            "schema": schema,
            "name": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "manifest": {
            "identity": {},
            "coverage": [],
        },
        "artifacts": {_infer_artifact_name(report): report},
    }


def _infer_artifact_name(report: dict[str, Any]) -> str:
    schema = report.get("schema")
    if schema == RUNTIME_ATTESTATION_SCHEMA:
        return runtime_artifact_name(report)
    if schema == TERRAIN_ATTESTATION_SCHEMA:
        return terrain_artifact_name(report)
    mapping = {
        LEGACY_INSTALLATION_SCHEMA: "legacy-installation",
        "dcsmizzer.dcs-static/v1": "installation",
        "dcsmizzer.dcs-countries/v1": "countries",
        "dcsmizzer.dcs-module-index/v1": "modules",
        "dcsmizzer.dcs-default-payload-index/v1": "payloads",
        "dcsmizzer.dcs-weather-presets/v1": "weather",
        "dcsmizzer.acknowledged-upstream-cache/v1": "upstream",
        "dcsmizzer.capabilities/v3": "capabilities",
    }
    if schema not in mapping:
        raise ValueError("standalone evidence report has no comparison domain")
    return mapping[schema]


def _normalize_source(source: dict[str, Any]) -> dict[str, Any]:
    artifacts = source["artifacts"]
    manifest_identity = source.get("manifest", {}).get("identity", {})
    domains: dict[str, dict[str, Any]] = {}
    identity = _flat_identity(manifest_identity)

    legacy = artifacts.get("legacy-installation")
    if isinstance(legacy, dict):
        identity.update(_legacy_identity(legacy))
        _set_domain(domains, "countries", "dcs-country-identifiers/v1", {
            "count": legacy.get("countries", {}).get("count"),
            "identifiers": legacy.get("countries", {}).get("identifiers"),
            "source_sha256": legacy.get("countries", {}).get("source_sha256"),
        })
        _set_domain(
            domains,
            "modules",
            "installed-module-directories/v1",
            _module_inventory_semantic(legacy.get("installed_module_directories")),
        )
        _set_payload_domain(domains, legacy.get("payload_presets"), legacy=True)

    installation = artifacts.get("installation")
    if isinstance(installation, dict):
        if not identity.get("product_version"):
            dcs = installation.get("dcs", {})
            identity["product_version"] = dcs.get("product_version")
            identity["distribution_build"] = dcs.get("steam_build_id")
        _set_domain(
            domains,
            "modules",
            "installed-module-directories/v1",
            _module_inventory_semantic(
                installation.get("installed_module_directories")
            ),
        )
        _set_domain(domains, "installation", "dcs-installation-identity/v1", identity)

    countries = artifacts.get("countries")
    if isinstance(countries, dict):
        _set_domain(domains, "countries", "dcs-country-identifiers/v1", {
            "count": countries.get("count"),
            "identifiers": countries.get("identifiers"),
            "source_sha256": countries.get("source_sha256"),
        })
    modules = artifacts.get("modules")
    if isinstance(modules, dict):
        _set_domain(domains, "module-declarations", "dcs-module-index/v1", {
            "coverage": modules.get("coverage"),
            "modules": modules.get("modules"),
        })
    payloads = artifacts.get("payloads")
    if isinstance(payloads, dict):
        _set_payload_domain(domains, payloads, legacy=False)
    weather = artifacts.get("weather")
    if isinstance(weather, dict):
        _set_domain(domains, "weather", "dcs-weather-presets/v1", weather)
    upstream = artifacts.get("upstream")
    if isinstance(upstream, dict):
        _set_domain(domains, "upstream", "acknowledged-upstream-locks/v1", {
            "coverage": upstream.get("coverage"),
            "sources": [
                {
                    "name": item.get("name"),
                    "directory": item.get("directory"),
                    "expected": item.get("expected"),
                    "actual": item.get("actual"),
                    "validation": item.get("validation"),
                    "errors": item.get("errors"),
                }
                for item in upstream.get("sources", [])
                if isinstance(item, dict)
            ],
            "validation": upstream.get("validation"),
        })
    capabilities = artifacts.get("capabilities")
    if isinstance(capabilities, dict):
        _set_domain(domains, "capabilities", "dcsmizzer-capabilities/v3", capabilities)
    for name, report in sorted(artifacts.items()):
        if name.startswith("airfields.") and isinstance(report, dict):
            qualifier = name.split(".", 1)[1]
            _set_domain(
                domains,
                f"airfields:{qualifier}",
                "dcs-static-airfield-beacons/v1",
                report,
            )
        elif name.startswith("runtime.") and isinstance(report, dict):
            _set_domain(
                domains,
                f"runtime:{report.get('run_id')}",
                RUNTIME_ATTESTATION_SCHEMA,
                report,
            )
        elif name.startswith("terrain.") and isinstance(report, dict):
            source = report.get("source", {})
            source_hash = source.get("sha256") if isinstance(source, dict) else None
            _set_domain(
                domains,
                (
                    f"terrain:{str(report.get('terrain')).casefold()}:"
                    f"{str(source_hash)[:16]}"
                ),
                TERRAIN_ATTESTATION_SCHEMA,
                report,
            )
    if "installation" not in domains and any(identity.values()):
        _set_domain(domains, "installation", "dcs-installation-identity/v1", identity)
    return {"identity": identity, "domains": domains}


def _flat_identity(value: Any) -> dict[str, Any]:
    dcs = value.get("dcs", {}) if isinstance(value, dict) else {}
    executable = dcs.get("executable", {}) if isinstance(dcs, dict) else {}
    api = dcs.get("sim_control_api", {}) if isinstance(dcs, dict) else {}
    return {
        "product_version": dcs.get("product_version"),
        "distribution": dcs.get("distribution"),
        "distribution_build": dcs.get("distribution_build"),
        "executable_sha256": executable.get("sha256"),
        "sim_control_api_sha256": api.get("sha256"),
    }


def _legacy_identity(report: dict[str, Any]) -> dict[str, Any]:
    dcs = report.get("dcs", {})
    steam = report.get("steam", {})
    edition = dcs.get("edition")
    return {
        "product_version": dcs.get("product_version"),
        "distribution": edition.casefold() if isinstance(edition, str) else None,
        "distribution_build": steam.get("buildid"),
        "executable_sha256": dcs.get("executable_sha256"),
        "sim_control_api_sha256": None,
    }


def _module_inventory_semantic(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(kind): [
            {
                "directory": item.get("directory"),
                "entry_present": item.get("entry_present"),
                "declared_state": item.get("declared_state"),
                "self_ids": item.get("self_ids"),
            }
            for item in records
            if isinstance(item, dict)
        ]
        for kind, records in sorted(value.items())
        if isinstance(records, list)
    }


def _set_payload_domain(
    domains: dict[str, dict[str, Any]],
    report: Any,
    *,
    legacy: bool,
) -> None:
    if not isinstance(report, dict):
        return
    if legacy:
        scope = report.get("source")
        semantic = {
            "scope": scope,
            "files_discovered": report.get("files"),
            "files_parsed": report.get("parsed"),
            "parse_failures": len(report.get("failures", {})),
            "presets": report.get("presets"),
            "pylon_assignments": report.get("pylon_assignments"),
            "unique_clsids": report.get("unique_clsids"),
            "task_ids": report.get("task_ids"),
        }
    else:
        coverage = report.get("coverage", {})
        scope = report.get("source_scope")
        semantic = {
            "scope": scope,
            "files_discovered": coverage.get("source_files_discovered"),
            "files_parsed": coverage.get("source_files_parsed"),
            "parse_failures": report.get("parse_failures"),
            "presets": coverage.get("presets"),
            "pylon_assignments": coverage.get("pylon_assignments"),
            "unique_clsids": coverage.get("unique_clsids"),
            "task_ids": coverage.get("task_ids"),
            "compatibility_complete": report.get("compatibility_complete"),
            "parse_failure_sources": report.get("parse_failure_sources"),
            "files_scanned": report.get("files_scanned"),
            "normalization_evidence": report.get("normalization_evidence"),
            "task_constant_source": report.get("task_constant_source"),
            "unit_type_count": report.get("unit_type_count"),
            "unit_types": report.get("unit_types"),
        }
    scope_hash = _semantic_hash(scope)
    _set_domain(domains, "payloads", f"dcs-default-payloads/{scope_hash}", semantic)


def _set_domain(
    domains: dict[str, dict[str, Any]],
    name: str,
    basis: str,
    semantic: Any,
) -> None:
    domains[name] = {
        "basis": basis,
        "fingerprint": _semantic_hash(semantic),
        "summary": _semantic_summary(name, semantic),
    }


def _semantic_summary(name: str, value: Any) -> dict[str, Any]:
    if name == "countries" and isinstance(value, dict):
        return {
            "count": value.get("count"),
            "source_sha256": value.get("source_sha256"),
        }
    if name == "payloads" and isinstance(value, dict):
        return {
            key: value.get(key)
            for key in (
                "files_discovered",
                "files_parsed",
                "parse_failures",
                "presets",
                "pylon_assignments",
                "unique_clsids",
            )
        }
    if name == "installation" and isinstance(value, dict):
        return {
            key: value.get(key)
            for key in (
                "product_version",
                "distribution",
                "distribution_build",
            )
        }
    if name == "modules" and isinstance(value, dict):
        return {
            kind: len(records)
            for kind, records in value.items()
            if isinstance(records, list)
        }
    if name.startswith("airfields:") and isinstance(value, dict):
        return {
            "terrain_directory": value.get("terrain_directory"),
            "airfield_ids_union": value.get("airfield_ids_union"),
            "source_sha256": value.get("source_sha256"),
            "radio_source_sha256": value.get("radio_source_sha256"),
        }
    if name.startswith("runtime:") and isinstance(value, dict):
        return {
            "run_id": value.get("run_id"),
            "mode": value.get("mode"),
            "runtime_valid": value.get("validation", {}).get("runtime_valid"),
            "result_sha256": value.get("evidence", {}).get("result_sha256"),
        }
    if name.startswith("terrain:") and isinstance(value, dict):
        return {
            "terrain": value.get("terrain"),
            "source_sha256": value.get("source", {}).get("sha256"),
            "samples": value.get("coverage", {}).get("samples"),
            "objects": value.get("coverage", {}).get("objects"),
            "airfields": value.get("coverage", {}).get("airfields"),
        }
    if isinstance(value, dict):
        return {"top_level_fields": len(value)}
    return {"value_present": value is not None}


def _scalar_change(before: Any, after: Any) -> dict[str, Any]:
    if before is None and after is None:
        status = "unknown_both"
    elif before is None:
        status = "added"
    elif after is None:
        status = "removed"
    elif before == after:
        status = "unchanged"
    else:
        status = "changed"
    return {"before": before, "after": after, "status": status}


def _coverage_by_base(records: Any) -> dict[str, str]:
    priorities = {"absent": 0, "complete": 1, "partial": 2, "blocked": 3}
    output: dict[str, str] = {}
    if not isinstance(records, list):
        return output
    for item in records:
        if not isinstance(item, dict):
            continue
        domain = item.get("domain")
        status_value = item.get("status")
        if domain not in _REQUIRED_DOMAINS or status_value not in priorities:
            continue
        current = output.get(domain, "absent")
        if priorities[status_value] > priorities[current] or current == "absent":
            output[domain] = status_value
    return output


def _readiness_coverage(bundle_status: str, current_status: str) -> str:
    if "absent" in {bundle_status, current_status}:
        return "absent"
    priorities = {"complete": 1, "partial": 2, "blocked": 3}
    if bundle_status not in priorities or current_status not in priorities:
        return "blocked"
    return max(
        (bundle_status, current_status),
        key=lambda value: priorities[value],
    )


def _validate_required_domains(values: Any) -> frozenset[str]:
    if not values:
        return frozenset(
            {
                "installation",
                "countries",
                "modules",
                "payloads",
                "weather",
                "airfields",
            }
        )
    if not isinstance(values, (list, tuple)) or len(values) > len(_REQUIRED_DOMAINS):
        raise ValueError("required evidence domains are invalid")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("required evidence domains are invalid")
    result = frozenset(values)
    if len(result) != len(values) or not result <= _REQUIRED_DOMAINS:
        raise ValueError("required evidence domains are duplicate or unknown")
    return result


def _bounded_evidence_inputs(
    values: Any,
    label: str,
) -> tuple[Path, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > (
        MAX_BOUND_INPUTS_PER_KIND
    ):
        raise ValueError(f"{label} are invalid")
    paths: list[Path] = []
    identities: set[str] = set()
    for value in values:
        try:
            path = Path(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} contain an invalid path") from error
        identity = os.path.normcase(str(path.absolute()))
        if identity in identities:
            raise ValueError(f"{label} contain a duplicate path")
        identities.add(identity)
        paths.append(path)
    return tuple(paths)


def _base_domain(name: str) -> str:
    if name.startswith(("airfields.", "airfields:")):
        return "airfields"
    if name.startswith(("runtime.", "runtime:")):
        return "runtime"
    if name.startswith(("terrain.", "terrain:")):
        return "terrain"
    if name == "module-declarations":
        return "modules"
    return name.split(".", 1)[0]


def _artifact_schema_allowed(name: str, schema: str) -> bool:
    domain = _snapshot_artifact_domain(name)
    return schema in _ARTIFACT_SCHEMAS.get(domain, frozenset())


def _snapshot_artifact_domain(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    if name in {
        "installation",
        "capabilities",
        "countries",
        "modules",
        "payloads",
        "weather",
        "upstream",
    }:
        return name
    if name.startswith("airfields."):
        qualifier = name.removeprefix("airfields.")
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", qualifier):
            return "airfields"
    if name.startswith("runtime."):
        run_id = name.removeprefix("runtime.")
        if _RUNTIME_ARTIFACT_RUN_ID.fullmatch(run_id) is not None:
            return "runtime"
    if name.startswith("terrain."):
        parts = name.split(".")
        if (
            len(parts) == 3
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", parts[1])
            and re.fullmatch(r"[0-9a-f]{16}", parts[2])
        ):
            return "terrain"
    return None


def _artifact_qualifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.casefold()).strip("-")
    if not normalized:
        raise ValueError("terrain directory cannot form an evidence artifact name")
    return normalized[:64]


def _validate_artifact_name(value: Any) -> None:
    if not isinstance(value, str) or _ARTIFACT_NAME.fullmatch(value) is None:
        raise ValueError("evidence artifact name is invalid")
    if ".." in value or value.endswith("."):
        raise ValueError("evidence artifact name is unsafe")


def _timestamp(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00",
            "Z",
        )
    if not isinstance(value, str) or len(value) > 40 or not value.endswith("Z"):
        raise ValueError("evidence timestamp must be bounded UTC ISO-8601")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("evidence timestamp is invalid") from error
    if parsed.tzinfo != UTC:
        raise ValueError("evidence timestamp must use UTC")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _semantic_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_reparse(status_result: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(attribute and file_attributes & attribute)
