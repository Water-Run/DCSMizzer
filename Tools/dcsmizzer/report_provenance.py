"""Uniform evidence-binding metadata for model-facing CLI reports."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any


REPORT_EVIDENCE_REF_SCHEMA = "dcsmizzer.report-evidence-ref/v1"
MAX_REPORT_EVIDENCE_REF_BYTES = 3840
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40,64}\Z")
_COMMAND = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_MAX_AUTHORITY_TEXT = 256
_DOMAINS = frozenset(
    {
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
    }
)
_EXPLICIT_VALIDATION_KEYS = {
    "bundle_reference_present",
    "bundle_integrity_verified",
    "bundle_stable_during_binding",
    "current_state_revalidated",
    "required_domains_ready",
    "reproducible_current_producer",
    "current_producer_matches_bundle",
    "evidence_ready_for_binding",
}


def attach_report_evidence_ref(
    report: dict[str, Any],
    evidence_ref: dict[str, Any] | None = None,
    *,
    command_succeeded: bool = True,
) -> dict[str, Any]:
    """Copy a report and make its evidence-binding state explicit."""

    if not isinstance(report, dict) or not isinstance(report.get("schema"), str):
        raise ValueError("CLI report has no schema identity")
    if "evidence_ref" in report:
        raise ValueError("CLI report already contains an evidence reference")
    reference = (
        _self_reference(report, command_succeeded=command_succeeded)
        if evidence_ref is None
        else _explicit_reference_for_report(evidence_ref, report)
    )
    if evidence_ref is not None:
        evidence_ready = reference["validation"]["evidence_ready_for_binding"]
        usable = bool(evidence_ready and command_succeeded)
        reference["status"] = "bundle-current" if usable else "unbound"
        reference["authority_tier"] = (
            "current_verified_binding_context" if usable else "report_intrinsic_only"
        )
        reference["validation"]["report_gate_passed"] = command_succeeded
        reference["validation"]["usable_for_current_production_decision"] = usable
    reference["report_authority"] = _report_authority(report)
    if _encoded_reference_size(reference) > MAX_REPORT_EVIDENCE_REF_BYTES:
        raise ValueError("CLI report evidence reference exceeds its byte budget")
    output = dict(report)
    output["evidence_ref"] = reference
    return output


def intrinsic_report_sha256(report: dict[str, Any]) -> str:
    """Hash canonical report content while excluding CLI transport metadata."""

    if not isinstance(report, dict):
        raise ValueError("CLI report is not an object")
    intrinsic = dict(report)
    intrinsic.pop("evidence_ref", None)
    try:
        payload = (
            json.dumps(
                intrinsic,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("CLI report is not canonical JSON") from error
    return hashlib.sha256(payload).hexdigest()


def _explicit_reference_for_report(
    value: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    draft = deepcopy(value)
    binding = draft.get("report_binding") if isinstance(draft, dict) else None
    if isinstance(binding, dict):
        expected = intrinsic_report_sha256(report)
        supplied = binding.get("intrinsic_report_sha256")
        if supplied is None:
            binding["intrinsic_report_sha256"] = expected
        elif supplied != expected:
            raise ValueError("explicit report evidence reference binds other content")
    return _validated_explicit_reference(draft)


def _validated_explicit_reference(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("explicit report evidence reference is invalid")
    if _encoded_reference_size(value) > MAX_REPORT_EVIDENCE_REF_BYTES:
        raise ValueError("explicit report evidence reference exceeds its byte budget")
    reference = deepcopy(value)
    if (
        set(reference)
        != {
            "schema",
            "status",
            "bundle",
            "authority_tier",
            "producer",
            "required_domains",
            "domain_artifact_bindings",
            "current_readiness",
            "report_binding",
            "limitations",
            "validation",
        }
        or reference.get("schema") != REPORT_EVIDENCE_REF_SCHEMA
    ):
        raise ValueError("explicit report evidence reference is invalid")

    status = reference.get("status")
    bundle = reference.get("bundle")
    validation = reference.get("validation")
    if (
        status not in {"bundle-current", "unbound"}
        or reference.get("authority_tier")
        != (
            "current_verified_binding_context"
            if status == "bundle-current"
            else "report_intrinsic_only"
        )
        or not isinstance(bundle, dict)
        or set(bundle) != {"id", "manifest_sha256"}
        or _HASH.fullmatch(str(bundle.get("id"))) is None
        or _HASH.fullmatch(str(bundle.get("manifest_sha256"))) is None
        or not isinstance(validation, dict)
        or set(validation) != _EXPLICIT_VALIDATION_KEYS
        or any(not isinstance(item, bool) for item in validation.values())
    ):
        raise ValueError("explicit report evidence reference is invalid")

    producers = _validated_producers(reference.get("producer"))
    required = _validated_required_domains(reference.get("required_domains"))
    _validate_artifact_bindings(
        reference.get("domain_artifact_bindings"),
        required,
    )
    readiness = _validated_current_readiness(reference.get("current_readiness"))
    binding = _validated_report_binding(reference.get("report_binding"), required)
    _validate_limitations(reference.get("limitations"))

    current = producers["current"]
    bundled = producers["bundle"]
    reproducible_current = bool(
        _GIT_COMMIT.fullmatch(str(current["git_commit"]))
        and current["git_dirty"] is False
    )
    producer_matches = bool(
        reproducible_current
        and bundled["name"] == current["name"] == "DCSMizzer"
        and bundled["version"] == current["version"]
        and bundled["git_commit"] == current["git_commit"]
        and bundled["git_dirty"] is False
    )
    domains_ready = all(required.values())
    current_revalidated = bool(
        readiness["schema"] == "dcsmizzer.evidence-readiness/v1"
        and readiness["live_collection_passes"] == 2
        and readiness["stable_across_passes"] is True
    )
    evidence_ready = bool(
        validation["bundle_reference_present"]
        and validation["bundle_integrity_verified"]
        and validation["bundle_stable_during_binding"]
        and validation["current_state_revalidated"]
        and validation["required_domains_ready"]
        and validation["reproducible_current_producer"]
        and validation["current_producer_matches_bundle"]
        and binding["source_roots_matched"]
    )
    if (
        validation["bundle_reference_present"] is not True
        or validation["reproducible_current_producer"] is not reproducible_current
        or validation["current_producer_matches_bundle"] is not producer_matches
        or validation["required_domains_ready"] is not domains_ready
        or validation["current_state_revalidated"] is not current_revalidated
        or validation["evidence_ready_for_binding"] is not evidence_ready
        or (status == "bundle-current") is not evidence_ready
    ):
        raise ValueError("explicit report evidence reference is inconsistent")
    return reference


def _validated_producers(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {"bundle", "current"}:
        raise ValueError("explicit report evidence reference is invalid")
    for record in value.values():
        git_dirty = record.get("git_dirty") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or set(record) != {"name", "version", "git_commit", "git_dirty"}
            or record.get("name") != "DCSMizzer"
            or not isinstance(record.get("version"), str)
            or not 1 <= len(record["version"]) <= 64
            or (
                record.get("git_commit") is not None
                and _GIT_COMMIT.fullmatch(str(record["git_commit"])) is None
            )
            or (git_dirty is not None and not isinstance(git_dirty, bool))
        ):
            raise ValueError("explicit report evidence reference is invalid")
    return value


def _validated_required_domains(value: Any) -> dict[str, bool]:
    keys = list(value) if isinstance(value, dict) else []
    if (
        not isinstance(value, dict)
        or not value
        or len(value) > len(_DOMAINS)
        or any(not isinstance(key, str) for key in keys)
        or set(keys) - _DOMAINS
        or keys != sorted(keys)
    ):
        raise ValueError("explicit report evidence reference is invalid")
    if any(not isinstance(ready, bool) for ready in value.values()):
        raise ValueError("explicit report evidence reference is invalid")
    return value


def _validate_artifact_bindings(value: Any, required: dict[str, Any]) -> None:
    keys = list(value) if isinstance(value, dict) else []
    if (
        not isinstance(value, dict)
        or any(not isinstance(key, str) for key in keys)
        or set(keys) != set(required)
        or keys != sorted(keys)
    ):
        raise ValueError("explicit report evidence reference is invalid")
    for record in value.values():
        if not isinstance(record, str) or _HASH.fullmatch(record) is None:
            raise ValueError("explicit report evidence reference is invalid")


def _validated_current_readiness(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema",
            "canonical_sha256",
            "live_collection_passes",
            "stable_across_passes",
            "live_collection_failures",
        }
        or value.get("schema") != "dcsmizzer.evidence-readiness/v1"
        or _HASH.fullmatch(str(value.get("canonical_sha256"))) is None
        or isinstance(value.get("live_collection_passes"), bool)
        or not isinstance(value.get("live_collection_passes"), int)
        or not 0 <= value["live_collection_passes"] <= 2
        or not isinstance(value.get("stable_across_passes"), bool)
        or isinstance(value.get("live_collection_failures"), bool)
        or not isinstance(value.get("live_collection_failures"), int)
        or not 0 <= value["live_collection_failures"] <= 64
    ):
        raise ValueError("explicit report evidence reference is invalid")
    return value


def _validated_report_binding(
    value: Any,
    required: dict[str, Any],
) -> dict[str, Any]:
    mandatory = value.get("mandatory_domains") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "command",
            "query_sha256",
            "intrinsic_report_sha256",
            "mandatory_domains",
            "source_roots_matched",
        }
        or _COMMAND.fullmatch(str(value.get("command"))) is None
        or _HASH.fullmatch(str(value.get("query_sha256"))) is None
        or _HASH.fullmatch(str(value.get("intrinsic_report_sha256"))) is None
        or not isinstance(mandatory, list)
        or not mandatory
        or any(not isinstance(item, str) for item in mandatory)
        or mandatory != sorted(set(mandatory))
        or not set(mandatory) <= set(required)
        or any(item not in _DOMAINS for item in mandatory)
        or not isinstance(value.get("source_roots_matched"), bool)
    ):
        raise ValueError("explicit report evidence reference is invalid")
    return value


def _validate_limitations(value: Any) -> None:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 8
        or any(not isinstance(item, str) or not 1 <= len(item) <= 512 for item in value)
    ):
        raise ValueError("explicit report evidence reference is invalid")


def _self_reference(
    report: dict[str, Any],
    *,
    command_succeeded: bool,
) -> dict[str, Any]:
    schema = report["schema"]
    bundle = report.get("bundle")
    validation = report.get("validation")
    if not isinstance(validation, dict):
        validation = {}

    bundle_record = _self_bundle_record(schema, bundle)
    if bundle_record is None:
        return {
            "schema": REPORT_EVIDENCE_REF_SCHEMA,
            "status": "unbound",
            "bundle": None,
            "authority_tier": "report_intrinsic_only",
            "required_domains": {},
            "current_readiness": None,
            "limitations": [
                "No content-addressed evidence bundle was bound to this CLI output.",
                "Intrinsic source and validation fields remain authoritative only "
                "within their declared finite scope.",
                "This metadata never upgrades static evidence to DCS runtime validity.",
            ],
            "validation": {
                "bundle_reference_present": False,
                "bundle_integrity_verified": False,
                "current_state_revalidated": False,
                "required_domains_ready": False,
                "report_gate_passed": command_succeeded,
                "usable_for_current_production_decision": False,
            },
        }

    domain_status = _self_required_domain_status(report.get("required_domains"))
    domains_ready = bool(domain_status) and all(domain_status.values())
    readiness = bool(
        schema == "dcsmizzer.evidence-readiness/v1"
        and validation.get("bundle_valid") is True
        and validation.get("current_identity_collected") is True
        and validation.get("reproducible_producer") is True
        and validation.get("all_required_domains_ready") is True
        and domains_ready
    )
    bundle_valid = validation.get("bundle_valid") is True
    return {
        "schema": REPORT_EVIDENCE_REF_SCHEMA,
        "status": "self",
        "bundle": bundle_record,
        "authority_tier": (
            "current_content_addressed_complete_evidence"
            if readiness and command_succeeded
            else "content_addressed_integrity_only"
        ),
        "required_domains": domain_status,
        "current_readiness": (
            {
                "schema": schema,
                "all_required_domains_ready": readiness,
            }
            if schema == "dcsmizzer.evidence-readiness/v1"
            else None
        ),
        "limitations": [
            "Self-reference covers the evidence report or bundle named here; it "
            "does not prove unrelated reports were derived from that bundle.",
            "No evidence metadata upgrades a lower runtime validation tier.",
        ],
        "validation": {
            "bundle_reference_present": True,
            "bundle_integrity_verified": bundle_valid,
            "current_state_revalidated": readiness,
            "required_domains_ready": bool(
                domains_ready
                and validation.get("all_required_domains_ready") is True
            ),
            "report_gate_passed": command_succeeded,
            "usable_for_current_production_decision": bool(
                readiness and command_succeeded
            ),
        },
    }


def _self_required_domain_status(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {
        name: value[name].get("ready") is True
        for name in sorted(
            key for key in value if isinstance(key, str) and key in _DOMAINS
        )
        if isinstance(value[name], dict)
    }


def _self_bundle_record(schema: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if schema in {
        "dcsmizzer.evidence-snapshot/v1",
        "dcsmizzer.evidence-bundle-verification/v1",
    }:
        bundle_id = value.get("id")
        manifest_sha256 = value.get("manifest_sha256")
    elif schema == "dcsmizzer.evidence-readiness/v1":
        bundle_id = value.get("bundle_id")
        manifest_sha256 = None
    else:
        return None
    if _HASH.fullmatch(str(bundle_id)) is None:
        return None
    if manifest_sha256 is not None and _HASH.fullmatch(str(manifest_sha256)) is None:
        return None
    return {
        "id": bundle_id,
        "manifest_sha256": manifest_sha256,
    }


def _report_authority(report: dict[str, Any]) -> dict[str, Any]:
    declared = report.get("authority")
    if isinstance(declared, str):
        declared = declared.encode("utf-8")[:_MAX_AUTHORITY_TEXT].decode(
            "utf-8",
            errors="ignore",
        )
    elif declared is not None:
        declared = "structured_schema_specific_authority"
    validation = report.get("validation")
    reported_runtime_valid = (
        validation.get("runtime_valid") if isinstance(validation, dict) else None
    )
    runtime_valid = (
        reported_runtime_valid
        if reported_runtime_valid is None or isinstance(reported_runtime_valid, bool)
        else None
    )
    dcs_started = report.get("dcs_started")
    if not isinstance(dcs_started, bool):
        dcs_started = None
    return {
        "report_schema": report["schema"],
        "declared_authority": declared,
        "dcs_started": dcs_started,
        "runtime_valid": runtime_valid,
        "scope": "reported_fields_preserved_without_authority_upgrade",
    }


def _encoded_reference_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                {"evidence_ref": value},
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "CLI report evidence reference is not canonical JSON"
        ) from error
