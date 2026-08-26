"""Read-only, fail-closed review of acknowledged upstream pin candidates.

The promotion audit never fetches, checks out, imports, or executes upstream
code.  It compares a ready immutable product cache with one caller-supplied
clean candidate checkout, verifies that the candidate is a fast-forward, and
parses the exact data surfaces consumed by DCSMizzer when those surfaces move.
The resulting report can authorize the *next* repository-regression step; it
never edits or authorizes editing the product lock by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import threading
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from . import br_static, pydcs_static
from .upstream_cache import (
    ACKNOWLEDGED_UPSTREAMS,
    AcknowledgedUpstream,
    upstream_source_lock_status,
    upstream_status_report,
)

UPSTREAM_PROMOTION_SCHEMA = "dcsmizzer.upstream-promotion-audit/v1"
PYDCS_MODEL_SCHEMA = "dcsmizzer.pydcs-consumer-model/v1"
BR_MODEL_SCHEMA = "dcsmizzer.br-consumer-model/v1"
GIT_AUDIT_TIMEOUT_SECONDS = 60
MAX_DIFF_BYTES = 2 * 1024 * 1024
MAX_CHANGED_PATHS = 4096
MAX_REPORTED_CHANGED_PATHS = 256
MAX_CONSUMER_INDEX_BYTES = 4 * 1024 * 1024
MAX_CONSUMER_FILES = 16_384
MAX_CONSUMER_FILE_BYTES = 128 * 1024 * 1024
MAX_CONSUMER_TOTAL_BYTES = 256 * 1024 * 1024
MAX_GIT_CAPTURE_BYTES = max(MAX_DIFF_BYTES, MAX_CONSUMER_INDEX_BYTES) + 1
_HASH40 = re.compile(r"\A[0-9a-f]{40}\Z")
_SAFE_DIFF_STATUSES = frozenset({"A", "D", "M", "T"})
_PYDCS_CONSUMER_FILES = frozenset(
    {
        "dcs/helicopters.py",
        "dcs/planes.py",
        "dcs/ships.py",
        "dcs/statics.py",
        "dcs/task.py",
        "dcs/vehicles.py",
        "dcs/weapons_data.py",
    }
)
_BR_CONSUMER_FILES = frozenset(
    {
        "DatabaseJSON/TheatersAirbases.json",
        "src/BriefingRoom/BriefingRoom.cs",
    }
)
_PYDCS_CONSUMER_PATHS = (
    *_PYDCS_CONSUMER_FILES,
    "dcs/terrain",
)
_BR_CONSUMER_PATHS = (
    *_BR_CONSUMER_FILES,
    "Database/Theaters",
    "DatabaseJSON/TheaterTerrainBounds",
    "DatabaseJSON/TheaterSpawnPoints",
)


def upstream_promotion_report(
    cache_root: Path,
    candidate_root: Path,
    source_key: str,
    *,
    manifest: Sequence[AcknowledgedUpstream] | None = None,
) -> dict[str, Any]:
    """Audit one candidate against the current immutable product pin.

    ``cache_root`` must be a fully ready acknowledged cache. ``candidate_root``
    is inspected in place and is never changed. A passing report means that
    the candidate is safe to take into the separately recorded repository
    regression step; it is deliberately not an automatic pin-promotion result.
    """

    sources = tuple(ACKNOWLEDGED_UPSTREAMS if manifest is None else manifest)
    source = _source_by_key(sources, source_key)
    baseline_status = upstream_status_report(cache_root, manifest=sources)
    baseline_record = _source_record(baseline_status, source.name)
    baseline_integrity = _repository_integrity(
        Path(cache_root) / source.directory,
        source,
    )
    baseline_ready = (
        baseline_status.get("validation", {}).get("all_sources_usable") is True
        and baseline_record.get("validation", {}).get("usable") is True
        and baseline_integrity["safe"] is True
    )

    candidate_lock = upstream_source_lock_status(
        candidate_root,
        source.name,
        manifest=sources,
    )
    candidate_actual = candidate_lock["actual"]
    candidate_validation = candidate_lock["validation"]
    candidate_integrity = _repository_integrity(candidate_root, source)
    candidate_safety = _candidate_safety(
        candidate_actual,
        candidate_validation,
        candidate_integrity,
    )

    revision = _empty_revision(source)
    if candidate_safety["safe"] is True:
        revision = _revision_report(
            candidate_root,
            source,
            candidate_actual["head"],
        )

    consumer_changes = revision["diff"]["consumer_changes"]
    compatibility = _unchanged_compatibility()
    if (
        baseline_ready
        and candidate_safety["safe"] is True
        and revision["validation"]["candidate_is_fast_forward"] is True
        and revision["validation"]["diff_complete"] is True
        and consumer_changes["count"] > 0
    ):
        compatibility = _compatibility_report(
            Path(cache_root) / source.directory,
            Path(candidate_root),
            source,
            consumer_changes["paths"],
            paths_truncated=consumer_changes["paths_truncated"],
        )

    stability = _stability_check(
        cache_root,
        candidate_root,
        source,
        sources,
        baseline_record,
        candidate_lock,
        baseline_integrity,
        candidate_integrity,
    )

    failure_reasons: list[str] = []
    if not baseline_ready:
        failure_reasons.append("baseline_cache_not_fully_usable")
    failure_reasons.extend(
        f"baseline_{reason}"
        for reason in baseline_integrity["failure_reasons"]
    )
    failure_reasons.extend(candidate_safety["failure_reasons"])
    failure_reasons.extend(revision["failure_reasons"])
    failure_reasons.extend(compatibility["failure_reasons"])
    failure_reasons.extend(stability["failure_reasons"])
    failure_reasons = sorted(set(failure_reasons))

    audit_passed = (
        baseline_ready
        and candidate_safety["safe"] is True
        and revision["validation"]["candidate_is_fast_forward"] is True
        and revision["validation"]["diff_complete"] is True
        and compatibility["validation"]["compatible"] is True
        and stability["stable"] is True
        and not failure_reasons
    )
    same_revision = revision["identity"]["same_commit"] is True
    consumer_model_changed = (
        compatibility["comparison"]["data_model_changed"] is True
    )
    requires_regression = (
        audit_passed
        and not same_revision
        and consumer_changes["count"] > 0
        and consumer_model_changed
    )
    recommendation = _recommendation(
        audit_passed=audit_passed,
        same_revision=same_revision,
        consumer_change_count=consumer_changes["count"],
        consumer_model_changed=consumer_model_changed,
    )

    return {
        "schema": UPSTREAM_PROMOTION_SCHEMA,
        "authority": "read_only_commit_and_consumer_model_promotion_audit",
        "dcs_started": False,
        "source": source.name,
        "baseline": {
            **_identity_projection(baseline_record["actual"]),
            "integrity": baseline_integrity,
        },
        "candidate": {
            **_identity_projection(candidate_actual),
            "currently_acknowledged": candidate_lock["acknowledged"] is True,
            "safety": candidate_safety,
        },
        "revision": revision,
        "compatibility": compatibility,
        "decision": {
            "recommendation": recommendation,
            "audit_passed": audit_passed,
            "repository_regression_required": requires_regression,
            "automatic_pin_update": False,
            "lock_update_authorized": False,
        },
        "validation": {
            "baseline_cache_fully_usable": baseline_ready,
            "candidate_checkout_safe": candidate_safety["safe"],
            "candidate_is_fast_forward": revision["validation"][
                "candidate_is_fast_forward"
            ],
            "diff_complete": revision["validation"]["diff_complete"],
            "consumer_compatibility_passed": compatibility["validation"][
                "compatible"
            ],
            "inputs_stable_across_audit": stability["stable"],
            "promotion_audit_passed": audit_passed,
        },
        "stability": stability,
        "failure_reasons": failure_reasons,
        "protocol": {
            "next_gate": (
                "record_repository_regression_and_review_lock_change"
                if requires_regression
                else "retain_current_pin"
                if recommendation.startswith("retain_")
                else "none"
                if recommendation == "no_revision_change"
                else "resolve_audit_failures"
            ),
            "promotion_requires": [
                "this exact candidate audit",
                "review of every consumed-model change",
                "passing repository compatibility and regression suites",
                "an explicit immutable lock edit",
                "post-edit upstream-status and evidence snapshot/diff/readiness",
            ],
        },
        "privacy": {
            "cache_root_echoed": False,
            "candidate_root_echoed": False,
            "local_paths_exposed": False,
            "remote_credentials_exposed": False,
            "changed_paths_are_upstream_repository_relative": True,
        },
        "safety": {
            "network_accessed": False,
            "checkout_written": False,
            "upstream_code_executed": False,
            "git_queries_disable_optional_locks_lazy_fetch_and_replacements": True,
        },
        "limitations": [
            (
                "A passing audit permits only the next repository-regression "
                "step; it does not authorize or perform a lock change."
            ),
            (
                "Unchanged consumed Git objects prove that DCSMizzer's current "
                "bounded reader inputs did not move, not that all upstream "
                "behavior is unchanged."
            ),
            (
                "Parsed upstream data remains lower authority than version-"
                "matched installed or initialized DCS evidence."
            ),
        ],
    }


def promotion_audit_passed(report: dict[str, Any]) -> bool:
    """Return the CLI gate for a complete, reviewable candidate audit."""

    return report.get("validation", {}).get("promotion_audit_passed") is True


def _source_by_key(
    sources: Sequence[AcknowledgedUpstream],
    source_key: str,
) -> AcknowledgedUpstream:
    folded = source_key.casefold()
    matches = [source for source in sources if source.name.casefold() == folded]
    if len(matches) != 1:
        raise ValueError("acknowledged upstream source key is unknown or ambiguous")
    if matches[0].name.casefold() not in {"pydcs", "briefingroom"}:
        raise ValueError("upstream promotion audit has no consumer model for source")
    return matches[0]


def _source_record(report: dict[str, Any], source_name: str) -> dict[str, Any]:
    matches = [
        record
        for record in report.get("sources", [])
        if isinstance(record, dict)
        and record.get("name") == source_name
    ]
    if len(matches) != 1:
        raise ValueError("acknowledged baseline source record is missing or ambiguous")
    return matches[0]


def _candidate_safety(
    actual: dict[str, Any],
    validation: dict[str, Any],
    integrity: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "exact_checkout_root": validation.get("exact_checkout_root") is True,
        "git_available": actual.get("git_available") is True,
        "clean": actual.get("clean") is True,
        "remote_matches": validation.get("remote_matches") is True,
        "branch_acceptable": validation.get("branch_acceptable") is True,
        "local_config_safe": validation.get("local_config_safe") is True,
        "required_paths_complete": (
            validation.get("required_paths_complete") is True
        ),
        "license_matches": validation.get("license_matches") is True,
        "commit_well_formed": isinstance(actual.get("head"), str)
        and _HASH40.fullmatch(actual["head"]) is not None,
        "tree_well_formed": isinstance(actual.get("tree"), str)
        and _HASH40.fullmatch(actual["tree"]) is not None,
        "repository_integrity": integrity["safe"] is True,
    }
    reasons = [
        f"candidate_{name}_failed" for name, passed in checks.items() if not passed
    ]
    reasons.extend(
        f"candidate_{reason}" for reason in integrity["failure_reasons"]
    )
    return {
        "safe": not reasons,
        "checks": checks,
        "failure_reasons": reasons,
        "exact_pin_not_required_for_candidate_review": True,
        "repository_integrity": integrity,
    }


def _empty_revision(source: AcknowledgedUpstream) -> dict[str, Any]:
    return {
        "identity": {
            "locked_commit": source.commit,
            "candidate_commit": None,
            "same_commit": False,
            "commits_ahead": None,
            "commits_behind": None,
        },
        "diff": {
            "complete": False,
            "changed_path_count": 0,
            "status_counts": {},
            "paths_sha256": None,
            "paths": [],
            "paths_truncated": False,
            "limits": {
                "maximum_bytes": MAX_DIFF_BYTES,
                "maximum_paths": MAX_CHANGED_PATHS,
                "maximum_reported_paths": MAX_REPORTED_CHANGED_PATHS,
            },
            "consumer_changes": {
                "count": 0,
                "paths_sha256": None,
                "paths": [],
                "paths_truncated": False,
            },
        },
        "validation": {
            "locked_commit_available": False,
            "candidate_is_fast_forward": False,
            "diff_complete": False,
        },
        "failure_reasons": ["candidate_revision_not_inspected"],
    }


def _revision_report(
    candidate_root: Path,
    source: AcknowledgedUpstream,
    candidate_commit: str,
) -> dict[str, Any]:
    failures: list[str] = []
    locked_object = _git(
        candidate_root,
        "cat-file",
        "-e",
        f"{source.commit}^{{commit}}",
    )
    locked_available = locked_object["returncode"] == 0
    if not locked_available:
        failures.append("locked_commit_unavailable_in_candidate")

    descendant = False
    ahead: int | None = None
    behind: int | None = None
    diff = _empty_revision(source)["diff"]
    if locked_available:
        ancestor = _git(
            candidate_root,
            "merge-base",
            "--is-ancestor",
            source.commit,
            candidate_commit,
        )
        descendant = ancestor["returncode"] == 0
        if not descendant:
            failures.append("candidate_is_not_fast_forward_from_lock")
        ahead = _revision_count(candidate_root, source.commit, candidate_commit)
        behind = _revision_count(candidate_root, candidate_commit, source.commit)
        if ahead is None or behind is None:
            failures.append("candidate_revision_count_unavailable")
        diff, diff_failures = _git_diff(candidate_root, source, candidate_commit)
        failures.extend(diff_failures)

    return {
        "identity": {
            "locked_commit": source.commit,
            "candidate_commit": candidate_commit,
            "same_commit": candidate_commit == source.commit,
            "commits_ahead": ahead,
            "commits_behind": behind,
        },
        "diff": diff,
        "validation": {
            "locked_commit_available": locked_available,
            "candidate_is_fast_forward": descendant and behind == 0,
            "diff_complete": diff["complete"],
        },
        "failure_reasons": sorted(set(failures)),
    }


def _revision_count(root: Path, before: str, after: str) -> int | None:
    result = _git(root, "rev-list", "--count", f"{before}..{after}")
    if result["returncode"] != 0:
        return None
    try:
        value = int(result["stdout"].decode("ascii", errors="strict").strip())
    except (UnicodeDecodeError, ValueError):
        return None
    return value if value >= 0 else None


def _git_diff(
    root: Path,
    source: AcknowledgedUpstream,
    candidate_commit: str,
) -> tuple[dict[str, Any], list[str]]:
    result = _git(
        root,
        "diff",
        "--name-status",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "-z",
        source.commit,
        candidate_commit,
        "--",
    )
    failures: list[str] = []
    payload = result["stdout"]
    if result["returncode"] != 0:
        failures.append("candidate_diff_query_failed")
    if len(payload) > MAX_DIFF_BYTES:
        failures.append("candidate_diff_exceeds_byte_limit")

    changes: list[dict[str, str]] = []
    if not failures:
        try:
            changes = _parse_name_status(payload)
        except ValueError:
            failures.append("candidate_diff_is_not_safe_canonical_name_status")
    if len(changes) > MAX_CHANGED_PATHS:
        failures.append("candidate_diff_exceeds_path_limit")
    complete = not failures
    if not complete:
        changes = []

    changes.sort(key=lambda item: (item["path"], item["status"]))
    status_counts = dict(sorted(Counter(item["status"] for item in changes).items()))
    paths_digest = _canonical_sha256(changes) if complete else None
    consumer = [
        item for item in changes if _is_consumer_path(source.name, item["path"])
    ]
    return (
        {
            "complete": complete,
            "changed_path_count": len(changes),
            "status_counts": status_counts,
            "paths_sha256": paths_digest,
            "paths": changes[:MAX_REPORTED_CHANGED_PATHS],
            "paths_truncated": len(changes) > MAX_REPORTED_CHANGED_PATHS,
            "limits": {
                "maximum_bytes": MAX_DIFF_BYTES,
                "maximum_paths": MAX_CHANGED_PATHS,
                "maximum_reported_paths": MAX_REPORTED_CHANGED_PATHS,
            },
            "consumer_changes": {
                "count": len(consumer),
                "paths_sha256": _canonical_sha256(consumer) if complete else None,
                "paths": consumer[:MAX_REPORTED_CHANGED_PATHS],
                "paths_truncated": len(consumer) > MAX_REPORTED_CHANGED_PATHS,
            },
        },
        failures,
    )


def _parse_name_status(payload: bytes) -> list[dict[str, str]]:
    if not payload:
        return []
    fields = payload.split(b"\0")
    if fields[-1] != b"" or (len(fields) - 1) % 2:
        raise ValueError("Git name-status output is incomplete")
    result: list[dict[str, str]] = []
    for offset in range(0, len(fields) - 1, 2):
        try:
            status = fields[offset].decode("ascii", errors="strict")
            path = fields[offset + 1].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Git name-status output is not UTF-8") from error
        if status not in _SAFE_DIFF_STATUSES or not _safe_repo_path(path):
            raise ValueError("Git name-status output contains an unsafe field")
        result.append({"status": status, "path": path})
    return result


def _safe_repo_path(value: str) -> bool:
    if (
        not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _is_consumer_path(source_name: str, path: str) -> bool:
    if source_name.casefold() == "pydcs":
        return path in _PYDCS_CONSUMER_FILES or path.startswith("dcs/terrain/")
    if source_name.casefold() == "briefingroom":
        return (
            path in _BR_CONSUMER_FILES
            or path.startswith(
                (
                    "Database/Theaters/",
                    "DatabaseJSON/TheaterTerrainBounds/",
                    "DatabaseJSON/TheaterSpawnPoints/",
                )
            )
        )
    return False


def _repository_integrity(
    root: Path,
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    """Reject Git metadata or checkout states that can hide consumer inputs."""

    root = Path(os.path.abspath(os.fspath(root)))
    git_directory_safe = _safe_directory(root / ".git")
    shallow = _git(root, "rev-parse", "--is-shallow-repository")
    replace_refs = _git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        "refs/replace/",
    )
    sparse = _git(
        root,
        "config",
        "--local",
        "--bool",
        "--get",
        "core.sparseCheckout",
    )
    sparse_disabled = (
        sparse["returncode"] == 1 and sparse["stdout"] == b""
    ) or (
        sparse["returncode"] == 0
        and sparse["stdout"].strip() == b"false"
    )
    marker_checks = {
        "grafts_absent": _path_absent(root / ".git" / "info" / "grafts"),
        "alternates_absent": _path_absent(
            root / ".git" / "objects" / "info" / "alternates"
        ),
        "http_alternates_absent": _path_absent(
            root / ".git" / "objects" / "info" / "http-alternates"
        ),
        "sparse_checkout_file_absent": _path_absent(
            root / ".git" / "info" / "sparse-checkout"
        ),
    }
    consumer = _consumer_surface_integrity(root, source)
    checks = {
        "standalone_git_directory_safe": git_directory_safe,
        "not_shallow": (
            shallow["returncode"] == 0
            and shallow["stdout"].strip() == b"false"
        ),
        "replace_refs_absent": (
            replace_refs["returncode"] == 0
            and replace_refs["stdout"] == b""
        ),
        "sparse_checkout_disabled": sparse_disabled,
        **marker_checks,
        "consumer_surface_exact": consumer["safe"] is True,
    }
    failures = [
        f"repository_{name}_failed"
        for name, passed in checks.items()
        if not passed
    ]
    failures.extend(consumer["failure_reasons"])
    return {
        "safe": not failures,
        "checks": checks,
        "consumer_surface": consumer,
        "failure_reasons": sorted(set(failures)),
    }


def _consumer_surface_integrity(
    root: Path,
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    pathspecs = _consumer_pathspecs(source.name)
    index = _git(root, "ls-files", "--stage", "-z", "--", *pathspecs)
    flags = _git(root, "ls-files", "-v", "-z", "--", *pathspecs)
    ignored = _git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        *pathspecs,
    )
    staged = _git(
        root,
        "diff-index",
        "--cached",
        "--quiet",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "HEAD",
        "--",
        *pathspecs,
    )

    failures: list[str] = []
    entries: list[dict[str, str]] = []
    if index["returncode"] != 0 or len(index["stdout"]) > MAX_CONSUMER_INDEX_BYTES:
        failures.append("consumer_index_query_failed")
    else:
        try:
            entries = _parse_index_entries(index["stdout"])
        except ValueError:
            failures.append("consumer_index_is_not_safe")
    if not entries:
        failures.append("consumer_index_is_empty")
    if len(entries) > MAX_CONSUMER_FILES:
        failures.append("consumer_index_exceeds_file_limit")

    total_checkout_bytes = 0
    total_blob_bytes = 0
    casefolded: set[str] = set()
    for entry in entries:
        path = entry["path"]
        if not _is_consumer_path(source.name, path):
            failures.append("consumer_index_contains_unexpected_path")
        folded = path.casefold()
        if folded in casefolded:
            failures.append("consumer_index_has_case_collision")
        casefolded.add(folded)
        status_result = _safe_regular_checkout_file(root, path)
        if status_result is None:
            failures.append("consumer_checkout_path_is_not_safe_regular_file")
            continue
        size = status_result.st_size
        if size < 0 or size > MAX_CONSUMER_FILE_BYTES:
            failures.append("consumer_file_exceeds_size_limit")
        else:
            blob_size = _checkout_file_index_blob_size(
                root,
                path,
                entry["object_id"],
                size,
            )
            if blob_size is None:
                failures.append("consumer_checkout_bytes_do_not_match_index")
            else:
                total_blob_bytes += blob_size
        total_checkout_bytes += max(size, 0)
    if total_checkout_bytes > MAX_CONSUMER_TOTAL_BYTES:
        failures.append("consumer_files_exceed_total_size_limit")

    tagged_paths: list[str] = []
    if flags["returncode"] != 0 or len(flags["stdout"]) > MAX_CONSUMER_INDEX_BYTES:
        failures.append("consumer_index_flags_query_failed")
    else:
        try:
            tagged_paths = _parse_index_flags(flags["stdout"])
        except ValueError:
            failures.append("consumer_index_flags_are_not_safe")
    indexed_paths = [entry["path"] for entry in entries]
    if tagged_paths != indexed_paths:
        failures.append("consumer_index_flags_are_not_normal")

    ignored_paths: list[str] = []
    if ignored["returncode"] != 0 or len(ignored["stdout"]) > MAX_CONSUMER_INDEX_BYTES:
        failures.append("consumer_ignored_input_query_failed")
    else:
        try:
            ignored_paths = _parse_nul_paths(ignored["stdout"])
        except ValueError:
            failures.append("consumer_ignored_inputs_are_not_safe")
    ignored_affecting = [
        path
        for path in ignored_paths
        if _ignored_path_may_affect_model(source.name, path)
    ]
    if ignored_affecting:
        failures.append("consumer_ignored_inputs_may_affect_model")
    if staged["returncode"] != 0:
        failures.append("consumer_index_differs_from_head")

    return {
        "safe": not failures,
        "tracked_files": len(entries),
        "tracked_blob_bytes": total_blob_bytes,
        "ignored_files": len(ignored_paths),
        "ignored_files_may_affect_model": len(ignored_affecting),
        "limits": {
            "maximum_index_bytes": MAX_CONSUMER_INDEX_BYTES,
            "maximum_files": MAX_CONSUMER_FILES,
            "maximum_file_bytes": MAX_CONSUMER_FILE_BYTES,
            "maximum_total_bytes": MAX_CONSUMER_TOTAL_BYTES,
        },
        "failure_reasons": sorted(set(failures)),
    }


def _consumer_pathspecs(source_name: str) -> tuple[str, ...]:
    if source_name.casefold() == "pydcs":
        return tuple(sorted(_PYDCS_CONSUMER_PATHS))
    if source_name.casefold() == "briefingroom":
        return tuple(sorted(_BR_CONSUMER_PATHS))
    raise ValueError("upstream promotion audit has no consumer paths")


def _parse_index_entries(payload: bytes) -> list[dict[str, str]]:
    records = _split_nul_records(payload)
    result: list[dict[str, str]] = []
    for record in records:
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.split(b" ")
            path = raw_path.decode("utf-8", errors="strict")
            decoded_object = object_id.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("Git index output is invalid") from error
        if (
            mode not in {b"100644", b"100755"}
            or _HASH40.fullmatch(decoded_object) is None
            or stage != b"0"
            or not _safe_repo_path(path)
        ):
            raise ValueError("Git index entry is unsafe")
        result.append({"path": path, "object_id": decoded_object})
    result.sort(key=lambda item: item["path"])
    return result


def _parse_index_flags(payload: bytes) -> list[str]:
    records = _split_nul_records(payload)
    paths: list[str] = []
    for record in records:
        if not record.startswith(b"H "):
            raise ValueError("Git index contains non-normal flags")
        try:
            path = record[2:].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Git index flag path is not UTF-8") from error
        if not _safe_repo_path(path):
            raise ValueError("Git index flag path is unsafe")
        paths.append(path)
    return sorted(paths)


def _parse_nul_paths(payload: bytes) -> list[str]:
    paths: list[str] = []
    for record in _split_nul_records(payload):
        try:
            path = record.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Git path output is not UTF-8") from error
        if not _safe_repo_path(path):
            raise ValueError("Git path output is unsafe")
        paths.append(path)
    return sorted(paths)


def _split_nul_records(payload: bytes) -> list[bytes]:
    if not payload:
        return []
    records = payload.split(b"\0")
    if records[-1] != b"":
        raise ValueError("Git NUL-delimited output is incomplete")
    return records[:-1]


def _ignored_path_may_affect_model(source_name: str, path: str) -> bool:
    if source_name.casefold() != "pydcs":
        return True
    parts = PurePosixPath(path).parts
    return not (
        len(parts) >= 4
        and parts[0:2] == ("dcs", "terrain")
        and parts[-2] == "__pycache__"
        and parts[-1].endswith((".pyc", ".pyo"))
    )


def _safe_regular_checkout_file(
    root: Path,
    relative_path: str,
) -> os.stat_result | None:
    current = root
    parts = PurePosixPath(relative_path).parts
    try:
        for index, component in enumerate(parts):
            current /= component
            status_result = current.lstat()
            if _is_link_or_reparse(status_result):
                return None
            if index < len(parts) - 1 and not stat.S_ISDIR(status_result.st_mode):
                return None
        return status_result if stat.S_ISREG(status_result.st_mode) else None
    except OSError:
        return None


def _checkout_file_index_blob_size(
    root: Path,
    relative_path: str,
    object_id: str,
    expected_size: int,
) -> int | None:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    before = _safe_regular_checkout_file(root, relative_path)
    if before is None or before.st_size != expected_size:
        return None
    try:
        raw_hash, crlf_pairs = _raw_blob_hash_and_crlf_count(path, expected_size)
        matched_size = expected_size if raw_hash == object_id else None
        if (
            matched_size is None
            and crlf_pairs
            and _allows_crlf_checkout_normalization(relative_path)
        ):
            normalized_size = expected_size - crlf_pairs
            if _normalized_blob_hash(path, normalized_size) == object_id:
                matched_size = normalized_size
    except OSError:
        return None
    after = _safe_regular_checkout_file(root, relative_path)
    stable = bool(
        matched_size is not None
        and after is not None
        and before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )
    return matched_size if stable else None


def _allows_crlf_checkout_normalization(relative_path: str) -> bool:
    return PurePosixPath(relative_path).suffix.casefold() in {
        ".cs",
        ".ini",
        ".json",
        ".py",
    }


def _raw_blob_hash_and_crlf_count(path: Path, size: int) -> tuple[str, int]:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size}\0".encode("ascii"))
    crlf_pairs = 0
    previous_cr = False
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            if previous_cr and chunk.startswith(b"\n"):
                crlf_pairs += 1
            crlf_pairs += chunk.count(b"\r\n")
            previous_cr = chunk.endswith(b"\r")
    return digest.hexdigest(), crlf_pairs


def _normalized_blob_hash(path: Path, normalized_size: int) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {normalized_size}\0".encode("ascii"))
    pending = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            data = pending + chunk
            if data.endswith(b"\r"):
                data, pending = data[:-1], b"\r"
            else:
                pending = b""
            digest.update(data.replace(b"\r\n", b"\n"))
    digest.update(pending)
    return digest.hexdigest()


def _safe_directory(path: Path) -> bool:
    try:
        status_result = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(status_result.st_mode) and not _is_link_or_reparse(
        status_result
    )


def _path_absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _is_link_or_reparse(status_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(
        stat.S_ISLNK(status_result.st_mode)
        or (reparse_flag and attributes & reparse_flag)
    )


def _unchanged_compatibility() -> dict[str, Any]:
    return {
        "state": "exact_consumer_inputs_unchanged",
        "baseline_model": None,
        "candidate_model": None,
        "comparison": {
            "model_changed": False,
            "data_model_changed": False,
            "changed_components": [],
            "summary_changes": {},
            "quality_regressions": [],
        },
        "validation": {
            "parser_run_required": False,
            "baseline_model_complete": True,
            "candidate_model_complete": True,
            "baseline_model_stable_across_two_passes": True,
            "candidate_model_stable_across_two_passes": True,
            "compatible": True,
        },
        "failure_reasons": [],
    }


def _compatibility_report(
    baseline_root: Path,
    candidate_root: Path,
    source: AcknowledgedUpstream,
    consumer_paths: list[dict[str, str]],
    *,
    paths_truncated: bool,
) -> dict[str, Any]:
    if paths_truncated:
        return {
            **_unchanged_compatibility(),
            "state": "consumer_path_list_truncated",
            "validation": {
                "parser_run_required": True,
                "baseline_model_complete": False,
                "candidate_model_complete": False,
                "baseline_model_stable_across_two_passes": False,
                "candidate_model_stable_across_two_passes": False,
                "compatible": False,
            },
            "failure_reasons": ["consumer_path_list_truncated"],
        }
    paths = [item["path"] for item in consumer_paths]
    try:
        spawn_terrains = _changed_spawn_terrains(paths)
    except ValueError:
        return {
            **_unchanged_compatibility(),
            "state": "unsupported_consumer_path_change",
            "validation": {
                "parser_run_required": True,
                "baseline_model_complete": False,
                "candidate_model_complete": False,
                "baseline_model_stable_across_two_passes": False,
                "candidate_model_stable_across_two_passes": False,
                "compatible": False,
            },
            "failure_reasons": ["unsupported_consumer_path_change"],
        }
    baseline = _safe_compatibility_snapshot(
        baseline_root,
        source.name,
        spawn_terrains=spawn_terrains,
        failure="baseline_consumer_model_parse_failed",
    )
    candidate = _safe_compatibility_snapshot(
        candidate_root,
        source.name,
        spawn_terrains=spawn_terrains,
        failure="candidate_consumer_model_parse_failed",
    )
    baseline_repeat = _safe_compatibility_snapshot(
        baseline_root,
        source.name,
        spawn_terrains=spawn_terrains,
        failure="baseline_consumer_model_repeat_parse_failed",
    )
    candidate_repeat = _safe_compatibility_snapshot(
        candidate_root,
        source.name,
        spawn_terrains=spawn_terrains,
        failure="candidate_consumer_model_repeat_parse_failed",
    )
    baseline_stable = _canonical_sha256(baseline) == _canonical_sha256(
        baseline_repeat
    )
    candidate_stable = _canonical_sha256(candidate) == _canonical_sha256(
        candidate_repeat
    )

    comparison = _compare_models(baseline, candidate)
    failures: list[str] = []
    if baseline["complete"] is not True:
        failures.append("baseline_consumer_model_incomplete")
    if candidate["complete"] is not True:
        failures.append("candidate_consumer_model_incomplete")
    if comparison["quality_regressions"]:
        failures.append("candidate_consumer_model_quality_regressed")
    if not baseline_stable:
        failures.append("baseline_consumer_model_unstable")
    if not candidate_stable:
        failures.append("candidate_consumer_model_unstable")
    compatible = not failures
    return {
        "state": "consumer_models_parsed" if compatible else "consumer_model_blocked",
        "baseline_model": baseline,
        "candidate_model": candidate,
        "comparison": comparison,
        "validation": {
            "parser_run_required": True,
            "baseline_model_complete": baseline["complete"] is True,
            "candidate_model_complete": candidate["complete"] is True,
            "baseline_model_stable_across_two_passes": baseline_stable,
            "candidate_model_stable_across_two_passes": candidate_stable,
            "compatible": compatible,
        },
        "failure_reasons": failures,
    }


def _safe_compatibility_snapshot(
    root: Path,
    source_name: str,
    *,
    spawn_terrains: tuple[str, ...],
    failure: str,
) -> dict[str, Any]:
    try:
        return _compatibility_snapshot(
            root,
            source_name,
            spawn_terrains=spawn_terrains,
        )
    except (OSError, OverflowError, ValueError, TypeError, json.JSONDecodeError):
        return _failed_model(source_name, failure)


def _compatibility_snapshot(
    root: Path,
    source_name: str,
    *,
    spawn_terrains: tuple[str, ...],
) -> dict[str, Any]:
    if source_name.casefold() == "pydcs":
        return _pydcs_model(root)
    if source_name.casefold() == "briefingroom":
        return _br_model(root, spawn_terrains=spawn_terrains)
    raise ValueError("upstream promotion audit has no consumer parser")


def _pydcs_model(root: Path) -> dict[str, Any]:
    checked = pydcs_static._validated_root(root)
    weapons, weapon_failures = pydcs_static._weapon_index(
        checked / "dcs" / "weapons_data.py"
    )
    tasks = pydcs_static._task_index(checked / "dcs" / "task.py")
    units: list[dict[str, Any]] = []
    units_by_category: dict[str, int] = {}
    unresolved_pylons = 0
    unresolved_tasks = 0
    for category, (filename, base_name) in pydcs_static._UNIT_SOURCE_FILES.items():
        records = pydcs_static._unit_declaration_index(
            checked / "dcs" / filename,
            category=category,
            base_name=base_name,
        )
        units_by_category[category] = len(records)
        for record in records:
            output = pydcs_static._unit_output_record(
                checked,
                record,
                detailed=False,
            )
            if category in {"plane", "helicopter"}:
                flying = pydcs_static._plane_class_record(
                    record["node"],
                    weapons,
                    tasks,
                )
                flying["unit_category"] = category
                unresolved_pylons += flying["unresolved_pylon_assignments"]
                unresolved_tasks += flying["unresolved_task_records"]
                output["flying_unit"] = flying
            units.append(output)

    terrain_root = checked / "dcs" / "terrain"
    packages = sorted(
        (
            path
            for path in terrain_root.iterdir()
            if path.is_dir()
            and (path / "airports.py").is_file()
            and (path / "projection.py").is_file()
        ),
        key=lambda path: path.name.casefold(),
    )
    terrains: list[dict[str, Any]] = []
    terrain_failures: list[str] = []
    for package in packages:
        try:
            terrains.append(
                pydcs_static._terrain_package_record(checked, package)
            )
        except ValueError:
            terrain_failures.append(package.name)
    airport_failures = sum(
        terrain["airport_summary"]["airport_parse_failures"]
        for terrain in terrains
    )
    payload = {
        "units": units,
        "weapons": [
            {"key": key, **value} for key, value in sorted(weapons.items())
        ],
        "tasks": [value for _key, value in sorted(tasks.items())],
        "terrains": terrains,
    }
    components = {
        "tasks": _canonical_sha256(payload["tasks"]),
        "terrains": _canonical_sha256(payload["terrains"]),
        "units": _canonical_sha256(payload["units"]),
        "weapons": _canonical_sha256(payload["weapons"]),
    }
    quality = {
        "airport_parse_failures": airport_failures,
        "terrain_parse_failures": len(terrain_failures),
        "unresolved_pylon_assignments": unresolved_pylons,
        "unresolved_task_records": unresolved_tasks,
        "weapon_parse_failures": weapon_failures,
    }
    complete = all(value == 0 for value in quality.values())
    return {
        "schema": PYDCS_MODEL_SCHEMA,
        "complete": complete,
        "fingerprint_sha256": _canonical_sha256(payload),
        "component_sha256": components,
        "summary": {
            "units_by_category": dict(sorted(units_by_category.items())),
            "units_total": len(units),
            "weapons": len(weapons),
            "tasks": len(tasks),
            "terrain_packages": len(terrains),
            "airports": sum(
                terrain["airport_summary"]["airports_parsed"]
                for terrain in terrains
            ),
            "parking_slots": sum(
                terrain["airport_summary"]["parking_slots"]
                for terrain in terrains
            ),
        },
        "quality": quality,
    }


def _br_model(root: Path, *, spawn_terrains: tuple[str, ...]) -> dict[str, Any]:
    checked = br_static._validated_root(root)
    entries = br_static._theatre_entries(checked)
    raw_airbases, _source = br_static._load_airbases(checked)
    airbases: list[dict[str, Any]] = []
    airbase_failures = 0
    for item in raw_airbases:
        try:
            airbases.append(br_static._airbase_record(item))
        except ValueError:
            airbase_failures += 1

    bounds: list[dict[str, Any]] = []
    bounds_failures = 0
    for entry in entries:
        source = br_static._contained_source(
            checked,
            checked / "DatabaseJSON" / "TheaterTerrainBounds",
            f"{entry['dcs_id']}.json",
        )
        try:
            bounds.append(
                {
                    "dcs_id": entry["dcs_id"],
                    "summary": br_static._bounds_summary(source),
                }
            )
        except ValueError:
            bounds_failures += 1

    spawn: list[dict[str, Any]] = []
    spawn_failures = 0
    spawn_malformed = 0
    known = {entry["dcs_id"].casefold(): entry["dcs_id"] for entry in entries}
    for requested in spawn_terrains:
        terrain = known.get(requested.casefold())
        if terrain is None:
            spawn_failures += 1
            continue
        try:
            report = br_static.br_spawnpoint_report(checked, terrain, limit=1)
        except ValueError:
            spawn_failures += 1
            continue
        coverage = report["coverage"]
        spawn_malformed += coverage["points_malformed"]
        spawn.append(
            {
                "terrain": terrain,
                "sources": report["sources"],
                "coverage": coverage,
            }
        )

    project_version = br_static._project_version_evidence(checked)
    payload = {
        "entries": entries,
        "airbases": airbases,
        "bounds": bounds,
        "spawn": spawn,
        "project_version": project_version,
    }
    components = {
        "airbases": _canonical_sha256(airbases),
        "bounds": _canonical_sha256(bounds),
        "project_version": _canonical_sha256(project_version),
        "spawn": _canonical_sha256(spawn),
        "theatres": _canonical_sha256(entries),
    }
    quality = {
        "airbase_parse_failures": airbase_failures,
        "bounds_parse_failures": bounds_failures,
        "spawn_parse_failures": spawn_failures,
        "spawn_points_malformed": spawn_malformed,
    }
    complete = all(value == 0 for value in quality.values())
    return {
        "schema": BR_MODEL_SCHEMA,
        "complete": complete,
        "fingerprint_sha256": _canonical_sha256(payload),
        "component_sha256": components,
        "summary": {
            "theatres": len(entries),
            "airbases": len(airbases),
            "parking_slots": sum(len(item["parking"]) for item in airbases),
            "bounds": len(bounds),
            "spawn_terrains_deep_parsed": len(spawn),
            "spawn_points_deep_parsed": sum(
                item["coverage"]["points_parsed"] for item in spawn
            ),
        },
        "quality": quality,
    }


def _failed_model(source_name: str, reason: str) -> dict[str, Any]:
    schema = (
        PYDCS_MODEL_SCHEMA
        if source_name.casefold() == "pydcs"
        else BR_MODEL_SCHEMA
    )
    return {
        "schema": schema,
        "complete": False,
        "fingerprint_sha256": None,
        "component_sha256": {},
        "summary": {},
        "quality": {reason: 1},
    }


def _compare_models(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    summary_changes = {
        key: {
            "before": baseline.get("summary", {}).get(key),
            "after": candidate.get("summary", {}).get(key),
        }
        for key in sorted(
            set(baseline.get("summary", {})) | set(candidate.get("summary", {}))
        )
        if baseline.get("summary", {}).get(key)
        != candidate.get("summary", {}).get(key)
    }
    quality_regressions = [
        {
            "metric": key,
            "before": before,
            "after": after,
        }
        for key in sorted(
            set(baseline.get("quality", {})) | set(candidate.get("quality", {}))
        )
        if isinstance((before := baseline.get("quality", {}).get(key, 0)), int)
        and isinstance((after := candidate.get("quality", {}).get(key, 0)), int)
        and after > before
    ]
    baseline_components = baseline.get("component_sha256", {})
    candidate_components = candidate.get("component_sha256", {})
    changed_components = [
        key
        for key in sorted(set(baseline_components) | set(candidate_components))
        if baseline_components.get(key) != candidate_components.get(key)
    ]
    metadata_only = {"project_version"}
    return {
        "model_changed": bool(changed_components),
        "data_model_changed": bool(set(changed_components) - metadata_only),
        "changed_components": changed_components,
        "summary_changes": summary_changes,
        "quality_regressions": quality_regressions,
    }


def _changed_spawn_terrains(paths: list[str]) -> tuple[str, ...]:
    prefix = "DatabaseJSON/TheaterSpawnPoints/"
    terrains: set[str] = set()
    for path in paths:
        if not path.startswith(prefix):
            continue
        filename = path[len(prefix) :]
        if "/" in filename or not filename.endswith(".json.gz"):
            raise ValueError("changed BriefingRoom spawn-point path is unsupported")
        stem = filename[: -len(".json.gz")]
        stem = stem.removesuffix("_Manual")
        if not stem or not re.fullmatch(r"[A-Za-z0-9_.-]+", stem):
            raise ValueError("changed BriefingRoom spawn-point identity is unsafe")
        terrains.add(stem)
    return tuple(sorted(terrains, key=str.casefold))


def _recommendation(
    *,
    audit_passed: bool,
    same_revision: bool,
    consumer_change_count: int,
    consumer_model_changed: bool,
) -> str:
    if not audit_passed:
        return "reject_candidate"
    if same_revision:
        return "no_revision_change"
    if consumer_change_count == 0 or not consumer_model_changed:
        return "retain_pin_consumed_model_unchanged"
    return "candidate_requires_repository_regression"


def _stability_check(
    cache_root: Path,
    candidate_root: Path,
    source: AcknowledgedUpstream,
    sources: Sequence[AcknowledgedUpstream],
    baseline_before: dict[str, Any],
    candidate_before: dict[str, Any],
    baseline_integrity_before: dict[str, Any],
    candidate_integrity_before: dict[str, Any],
) -> dict[str, Any]:
    try:
        baseline_after_report = upstream_status_report(
            cache_root,
            manifest=sources,
        )
        baseline_after = _source_record(baseline_after_report, source.name)
        candidate_after = upstream_source_lock_status(
            candidate_root,
            source.name,
            manifest=sources,
        )
        baseline_integrity_after = _repository_integrity(
            Path(cache_root) / source.directory,
            source,
        )
        candidate_integrity_after = _repository_integrity(
            candidate_root,
            source,
        )
    except (OSError, ValueError):
        return {
            "stable": False,
            "baseline_unchanged": False,
            "candidate_unchanged": False,
            "baseline_integrity_unchanged": False,
            "candidate_integrity_unchanged": False,
            "passes": 2,
            "failure_reasons": ["audit_input_revalidation_failed"],
        }
    baseline_unchanged = _canonical_sha256(baseline_before) == _canonical_sha256(
        baseline_after
    )
    candidate_unchanged = _canonical_sha256(candidate_before) == _canonical_sha256(
        candidate_after
    )
    baseline_integrity_unchanged = _canonical_sha256(
        baseline_integrity_before
    ) == _canonical_sha256(baseline_integrity_after)
    candidate_integrity_unchanged = _canonical_sha256(
        candidate_integrity_before
    ) == _canonical_sha256(candidate_integrity_after)
    failures: list[str] = []
    if not baseline_unchanged:
        failures.append("baseline_changed_during_audit")
    if not candidate_unchanged:
        failures.append("candidate_changed_during_audit")
    if not baseline_integrity_unchanged:
        failures.append("baseline_integrity_changed_during_audit")
    if not candidate_integrity_unchanged:
        failures.append("candidate_integrity_changed_during_audit")
    return {
        "stable": not failures,
        "baseline_unchanged": baseline_unchanged,
        "candidate_unchanged": candidate_unchanged,
        "baseline_integrity_unchanged": baseline_integrity_unchanged,
        "candidate_integrity_unchanged": candidate_integrity_unchanged,
        "passes": 2,
        "failure_reasons": failures,
    }


def _identity_projection(actual: dict[str, Any]) -> dict[str, Any]:
    license_record = actual.get("license")
    return {
        "commit": actual.get("head"),
        "tree": actual.get("tree"),
        "branch": actual.get("branch"),
        "detached": actual.get("detached"),
        "clean": actual.get("clean"),
        "remote": actual.get("remote"),
        "license": (
            {
                "sha256": license_record.get("sha256"),
                "bytes": license_record.get("bytes"),
                "safe_regular_file": license_record.get("safe_regular_file"),
            }
            if isinstance(license_record, dict)
            else None
        ),
    }


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git(root: Path, *arguments: str) -> dict[str, Any]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if (
            key in {
                "GIT_CONFIG",
                "GIT_CONFIG_PARAMETERS",
                "GIT_CONFIG_SYSTEM",
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_TEMPLATE_DIR",
                "GIT_SSH",
                "GIT_SSH_COMMAND",
                "GIT_PROXY_COMMAND",
            }
            or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
        ):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_COUNT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
        }
    )
    try:
        process = subprocess.Popen(
            ["git", "-C", os.fspath(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            shell=False,
        )
    except OSError:
        return {"returncode": None, "stdout": b""}
    captured: list[bytes] = []
    read_failed: list[bool] = []

    def read_stdout() -> None:
        try:
            assert process.stdout is not None
            captured.append(process.stdout.read(MAX_GIT_CAPTURE_BYTES))
        except OSError:
            read_failed.append(True)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    reader.join(GIT_AUDIT_TIMEOUT_SECONDS)
    if reader.is_alive():
        process.kill()
        reader.join(5)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        if process.stdout is not None:
            process.stdout.close()
        return {"returncode": None, "stdout": captured[0] if captured else b""}
    payload = captured[0] if captured else b""
    if len(payload) >= MAX_GIT_CAPTURE_BYTES and process.poll() is None:
        process.kill()
    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        returncode = None
    if process.stdout is not None:
        process.stdout.close()
    if read_failed:
        returncode = None
    return {
        "returncode": returncode,
        "stdout": payload,
    }
