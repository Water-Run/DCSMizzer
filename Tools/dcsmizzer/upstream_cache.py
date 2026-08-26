"""Explicit, pinned cache management for acknowledged upstream repositories.

The cache is optional product input.  Merely importing this module or running
the status query never creates files.  The prepare operation is the only API
here that may write, and it only targets a caller-supplied cache root.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit, urlunsplit


UPSTREAM_CACHE_SCHEMA = "dcsmizzer.acknowledged-upstream-cache/v1"
GIT_QUERY_TIMEOUT_SECONDS = 15
GIT_MUTATION_TIMEOUT_SECONDS = 900
MAX_GIT_DIAGNOSTIC_BYTES = 1024
MAX_LICENSE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RequiredPath:
    """One required checkout-relative file or directory."""

    path: str
    kind: str


@dataclass(frozen=True, slots=True)
class AcknowledgedUpstream:
    """Immutable identity and minimum product profile for one upstream."""

    name: str
    remote: str
    branch: str
    commit: str
    tree: str
    directory: str
    license_id: str
    license_path: str
    license_sha256: str
    required_paths: tuple[RequiredPath, ...]


ACKNOWLEDGED_UPSTREAMS: tuple[AcknowledgedUpstream, ...] = (
    AcknowledgedUpstream(
        name="pydcs",
        remote="https://github.com/pydcs/dcs",
        branch="master",
        commit="e20f328390aecaac2a7f82444b4f5a96ac6bb2c3",
        tree="b07fadf3dddd0873176eab32c15caa4c34c46b0f",
        directory="pydcs",
        license_id="LGPL-3.0-only",
        license_path="LICENSE.txt",
        license_sha256=(
            "ea7d049c7705dc13afc202dd18e1827f"
            "3484f8212fd3fa7b82fc4a0c363432c9"
        ),
        required_paths=(
            RequiredPath("dcs/terrain", "directory"),
            RequiredPath("dcs/planes.py", "file"),
            RequiredPath("dcs/helicopters.py", "file"),
            RequiredPath("dcs/vehicles.py", "file"),
            RequiredPath("dcs/ships.py", "file"),
            RequiredPath("dcs/statics.py", "file"),
            RequiredPath("dcs/weapons_data.py", "file"),
            RequiredPath("dcs/task.py", "file"),
        ),
    ),
    AcknowledgedUpstream(
        name="BriefingRoom",
        remote=(
            "https://github.com/DCS-BR-Tools/briefing-room-for-dcs"
        ),
        branch="main",
        commit="4d8773e9eec0215edb5cd9f576c085ee9f1bf7a7",
        tree="75898835689457be82ffa08693aaadae92e28117",
        directory="briefing-room-for-dcs",
        license_id="GPL-3.0-only",
        license_path="LICENSE",
        license_sha256=(
            "a0ee746064b06d09cab0768116ec265f"
            "d0d45261d4087c9ad2c698a07c7aac0e"
        ),
        required_paths=(
            RequiredPath("Database/Theaters", "directory"),
            RequiredPath(
                "DatabaseJSON/TheaterTerrainBounds",
                "directory",
            ),
            RequiredPath(
                "DatabaseJSON/TheaterSpawnPoints",
                "directory",
            ),
            RequiredPath(
                "DatabaseJSON/TheatersAirbases.json",
                "file",
            ),
            RequiredPath(
                "src/BriefingRoom/BriefingRoom.cs",
                "file",
            ),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class _GitResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    unavailable: bool = False


def upstream_status_report(
    cache_root: Path,
    *,
    manifest: Sequence[AcknowledgedUpstream] | None = None,
) -> dict[str, Any]:
    """Inspect a caller-supplied cache without creating or changing it."""

    sources = _validated_manifest(manifest)
    root, root_present = _cache_root(cache_root, create=False)
    return _status_report(
        root,
        root_present=root_present,
        sources=sources,
        mode="status",
    )


def prepare_upstreams(
    cache_root: Path,
    *,
    offline: bool = False,
    manifest: Sequence[AcknowledgedUpstream] | None = None,
) -> dict[str, Any]:
    """Safely create or move clean recognized checkouts to immutable pins."""

    sources = _validated_manifest(manifest)
    root, _ = _cache_root(cache_root, create=True)
    operations: list[dict[str, Any]] = []
    for source in sources:
        target = root / source.directory
        _validate_checkout_path(root, target, source.directory)
        if not target.exists():
            if offline:
                operations.append(
                    _operation(
                        source,
                        "clone",
                        "skipped",
                        "offline_checkout_missing",
                    )
                )
            else:
                operations.append(_clone_pinned(root, target, source))
            continue
        current = _source_status(root, source)
        if current["validation"]["usable"] is True:
            operations.append(
                _operation(source, "none", "already_usable")
            )
            continue
        operations.append(
            _prepare_existing(
                root,
                target,
                source,
                current,
                offline=offline,
            )
        )

    report = _status_report(
        root,
        root_present=True,
        sources=sources,
        mode="prepare",
    )
    report["preparation"] = {
        "offline": offline,
        "write_scope": "caller_supplied_cache_root_only",
        "operations": operations,
    }
    return report


def upstream_report_usable(report: dict[str, Any]) -> bool:
    """Return the single shared status gate used by both CLI commands."""

    return report.get("validation", {}).get("all_sources_usable") is True


def upstream_source_lock_status(
    checkout_root: Path,
    source_key: str,
    *,
    manifest: Sequence[AcknowledgedUpstream] | None = None,
) -> dict[str, Any]:
    """Inspect one exact checkout against its acknowledged immutable pin.

    The caller supplies the checkout itself, not a cache containing every
    configured source.  The returned envelope deliberately omits local path
    components, so it is safe to embed in other evidence reports.
    """

    sources = _validated_manifest(manifest)
    folded_key = source_key.casefold()
    matches = [
        source
        for source in sources
        if source.name.casefold() == folded_key
    ]
    if len(matches) != 1:
        raise ValueError("acknowledged upstream source key is unknown")
    source = matches[0]

    target = _absolute_without_resolution(checkout_root)
    _reject_linked_existing_chain(
        target,
        "acknowledged upstream exact checkout root",
    )
    inspected_source = AcknowledgedUpstream(
        name=source.name,
        remote=source.remote,
        branch=source.branch,
        commit=source.commit,
        tree=source.tree,
        directory=target.name,
        license_id=source.license_id,
        license_path=source.license_path,
        license_sha256=source.license_sha256,
        required_paths=source.required_paths,
    )
    record = _source_status(target.parent, inspected_source)
    usable = record["validation"]["usable"] is True
    return {
        "schema": "dcsmizzer.acknowledged-upstream-source-lock/v1",
        "source": source.name,
        "acknowledged": usable,
        "expected": record["expected"],
        "actual": record["actual"],
        "validation": record["validation"],
        "failure_reasons": [
            error["code"]
            for error in record["errors"]
            if isinstance(error, dict) and isinstance(error.get("code"), str)
        ],
        "errors": record["errors"],
        "privacy": {
            "checkout_root_echoed": False,
            "local_paths_exposed": False,
            "remote_credentials_exposed": False,
        },
    }


def _validated_manifest(
    manifest: Sequence[AcknowledgedUpstream] | None,
) -> tuple[AcknowledgedUpstream, ...]:
    values = tuple(
        ACKNOWLEDGED_UPSTREAMS if manifest is None else manifest
    )
    if not values:
        raise ValueError("acknowledged upstream manifest must not be empty")
    names: set[str] = set()
    directories: set[str] = set()
    for source in values:
        if not isinstance(source, AcknowledgedUpstream):
            raise ValueError("acknowledged upstream manifest is invalid")
        if not _safe_component(source.name):
            raise ValueError("acknowledged upstream name is unsafe")
        if not _safe_component(source.directory):
            raise ValueError("acknowledged upstream directory is unsafe")
        if source.name.casefold() in names:
            raise ValueError("acknowledged upstream names must be unique")
        if source.directory.casefold() in directories:
            raise ValueError("acknowledged upstream directories must be unique")
        names.add(source.name.casefold())
        directories.add(source.directory.casefold())
        if not _safe_git_remote(source.remote):
            raise ValueError(
                f"acknowledged upstream {source.name} remote is unsafe"
            )
        if not _safe_git_branch(source.branch):
            raise ValueError(
                f"acknowledged upstream {source.name} branch is unsafe"
            )
        if re.fullmatch(r"[0-9a-f]{40}", source.commit) is None:
            raise ValueError(
                f"acknowledged upstream {source.name} commit is invalid"
            )
        if re.fullmatch(r"[0-9a-f]{40}", source.tree) is None:
            raise ValueError(
                f"acknowledged upstream {source.name} tree is invalid"
            )
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}", source.license_id)
            is None
        ):
            raise ValueError(
                f"acknowledged upstream {source.name} license ID is invalid"
            )
        if not _safe_relative_path(source.license_path):
            raise ValueError(
                f"acknowledged upstream {source.name} license path is unsafe"
            )
        if re.fullmatch(r"[0-9a-f]{64}", source.license_sha256) is None:
            raise ValueError(
                f"acknowledged upstream {source.name} license hash is invalid"
            )
        required_seen: set[str] = set()
        for required in source.required_paths:
            if (
                not isinstance(required, RequiredPath)
                or required.kind not in {"file", "directory"}
                or not _safe_relative_path(required.path)
            ):
                raise ValueError(
                    f"acknowledged upstream {source.name} required path is invalid"
                )
            folded = required.path.casefold()
            if folded in required_seen:
                raise ValueError(
                    f"acknowledged upstream {source.name} required paths "
                    "must be unique"
                )
            required_seen.add(folded)
    return values


def _cache_root(path: Path, *, create: bool) -> tuple[Path, bool]:
    root = _absolute_without_resolution(path)
    _reject_linked_existing_chain(root, "cache root")
    status_result = _lstat_optional(root)
    if status_result is None and create:
        root.mkdir(parents=True, exist_ok=False)
        _reject_linked_existing_chain(root, "cache root")
        status_result = root.lstat()
    if status_result is None:
        return root, False
    if _is_link_or_reparse(status_result):
        raise ValueError(
            "acknowledged upstream cache root must not be a symbolic "
            "link or reparse point"
        )
    if not stat.S_ISDIR(status_result.st_mode):
        raise ValueError(
            "acknowledged upstream cache root must be a directory"
        )
    return root, True


def _absolute_without_resolution(path: Path) -> Path:
    try:
        value = os.fspath(path)
    except TypeError as error:
        raise ValueError("cache root must be a filesystem path") from error
    if not value or "\x00" in value:
        raise ValueError("cache root must be a non-empty filesystem path")
    try:
        return Path(os.path.abspath(value))
    except (OSError, ValueError) as error:
        raise ValueError("cache root cannot be made absolute") from error


def _reject_linked_existing_chain(path: Path, subject: str) -> None:
    parts = path.parts
    if not parts:
        raise ValueError(f"{subject} is invalid")
    current = Path(parts[0])
    for component in parts[1:]:
        current /= component
        status_result = _lstat_optional(current)
        if status_result is None:
            break
        if _is_link_or_reparse(status_result):
            raise ValueError(
                f"{subject} must not traverse a symbolic link or reparse point"
            )


def _validate_checkout_path(
    root: Path,
    target: Path,
    directory: str,
) -> None:
    if target.parent != root or target.name != directory:
        raise ValueError("acknowledged upstream checkout path is invalid")
    status_result = _lstat_optional(target)
    if status_result is None:
        return
    if _is_link_or_reparse(status_result):
        raise ValueError(
            f"acknowledged upstream child {directory} must not be a "
            "symbolic link or reparse point"
        )
    if not stat.S_ISDIR(status_result.st_mode):
        raise ValueError(
            f"acknowledged upstream child {directory} must be a directory"
        )


def _status_report(
    root: Path,
    *,
    root_present: bool,
    sources: tuple[AcknowledgedUpstream, ...],
    mode: str,
) -> dict[str, Any]:
    records = (
        [_source_status(root, source) for source in sources]
        if root_present
        else [_missing_source_status(source) for source in sources]
    )
    usable = sum(
        record["validation"]["usable"] is True for record in records
    )
    all_usable = usable == len(records)
    return {
        "schema": UPSTREAM_CACHE_SCHEMA,
        "authority": {
            "kind": "immutable_acknowledged_upstream_pins",
            "status_mode": mode,
            "source_identity": (
                "exact origin URL, commit, root tree, license hash, and "
                "required checkout profile"
            ),
            "runtime_or_installed_dcs_authority": False,
        },
        "dcs_started": False,
        "privacy": {
            "cache_root_echoed": False,
            "local_paths_exposed": False,
            "remote_credentials_exposed": False,
            "source_paths": "cache-root-relative public directory names only",
        },
        "cache": {
            "present": root_present,
            "path": "<caller-supplied-cache-root>",
            "implicit_develope_default": False,
        },
        "coverage": {
            "configured_sources": len(records),
            "usable_sources": usable,
            "unusable_sources": len(records) - usable,
        },
        "validation": {
            "all_sources_usable": all_usable,
        },
        "sources": records,
    }


def _missing_source_status(
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    record = _source_envelope(source)
    record["actual"] = _empty_actual(checkout_present=False)
    record["validation"] = _empty_validation()
    record["errors"] = [
        {
            "code": "checkout_missing",
            "message": "recognized checkout directory is missing",
        }
    ]
    return record


def _source_status(
    root: Path,
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    target = root / source.directory
    _validate_checkout_path(root, target, source.directory)
    if _lstat_optional(target) is None:
        return _missing_source_status(source)

    record = _source_envelope(source)
    actual = _empty_actual(checkout_present=True)
    validation = _empty_validation()
    errors: list[dict[str, str]] = []

    top_level_result = _run_git(
        target,
        ("rev-parse", "--show-toplevel"),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    if top_level_result.unavailable:
        errors.append(
            {
                "code": "git_unavailable",
                "message": "git executable is unavailable",
            }
        )
        record["actual"] = actual
        record["validation"] = validation
        record["errors"] = errors
        return record
    if top_level_result.returncode != 0:
        errors.append(
            {
                "code": "not_git_repository",
                "message": "checkout directory is not an inspectable Git repository",
            }
        )
        record["actual"] = actual
        record["validation"] = validation
        record["errors"] = errors
        return record

    actual["git_available"] = True
    validation["exact_checkout_root"] = _same_checkout_root(
        top_level_result.stdout,
        target,
    )
    actual["exact_checkout_root"] = validation["exact_checkout_root"]
    if validation["exact_checkout_root"] is not True:
        errors.append(
            {
                "code": "checkout_root_mismatch",
                "message": "Git top-level is not the recognized child directory",
            }
        )
        record["actual"] = actual
        record["validation"] = validation
        record["errors"] = errors
        return record

    head_result = _run_git(
        target,
        ("rev-parse", "--verify", "HEAD^{commit}"),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    tree_result = _run_git(
        target,
        ("rev-parse", "--verify", "HEAD^{tree}"),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    remote_result = _run_git(
        target,
        (
            "config",
            "--local",
            "--no-includes",
            "--get-all",
            "remote.origin.url",
        ),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    local_config_result = _run_git(
        target,
        (
            "config",
            "--local",
            "--no-includes",
            "--null",
            "--name-only",
            "--list",
        ),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    info_attributes_result = _run_git(
        target,
        (
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "info/attributes",
        ),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    worktree_config_result = _run_git(
        target,
        (
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "config.worktree",
        ),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    branch_result = _run_git(
        target,
        ("symbolic-ref", "--quiet", "--short", "HEAD"),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
        isolated_config=True,
    )
    local_config_keys = (
        tuple(
            key
            for key in local_config_result.stdout.split("\x00")
            if key
        )
        if local_config_result.returncode == 0
        else ()
    )
    local_config_safe = (
        local_config_result.returncode == 0
        and not any(
            _dangerous_local_config_key(key)
            for key in local_config_keys
        )
        and _git_metadata_file_empty(info_attributes_result)
        and _git_metadata_file_empty(worktree_config_result)
    )
    clean_result = (
        _run_git(
            target,
            (
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.trustctime=true",
                "-c",
                "core.checkStat=default",
                "-c",
                "core.ignoreStat=false",
                "-c",
                f"core.autocrlf={'true' if os.name == 'nt' else 'false'}",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--ignored=matching",
                "--ignore-submodules=none",
            ),
            timeout=GIT_QUERY_TIMEOUT_SECONDS,
            redactions=(root, target, source.remote),
            isolated_config=True,
        )
        if local_config_safe
        else _GitResult(returncode=None, stdout="", stderr="")
    )
    index_flags_result = (
        _run_git(
            target,
            ("ls-files", "-v", "-z", "--cached", "--"),
            timeout=GIT_QUERY_TIMEOUT_SECONDS,
            redactions=(root, target, source.remote),
            isolated_config=True,
        )
        if local_config_safe
        else _GitResult(returncode=None, stdout="", stderr="")
    )

    head = _successful_line(head_result)
    tree = _successful_line(tree_result)
    remote_values = (
        tuple(
            value
            for value in remote_result.stdout.splitlines()
            if value
        )
        if remote_result.returncode == 0
        else ()
    )
    remote = remote_values[0] if len(remote_values) == 1 else None
    branch = _successful_line(branch_result)
    clean = (
        clean_result.stdout == ""
        if clean_result.returncode == 0
        else None
    )
    index_flags_safe = _tracked_index_flags_safe(index_flags_result)
    detached = branch_result.returncode == 1 and head is not None
    remote_matches = remote == source.remote
    branch_acceptable = branch == source.branch or detached
    exact_pin = head == source.commit
    tree_matches = tree == source.tree

    actual.update(
        {
            "remote": _sanitize_remote(remote),
            "remote_scope": (
                "sanitized_no_credentials_query_fragment_or_local_path"
            ),
            "branch": branch,
            "detached": detached,
            "head": head,
            "tree": tree,
            "clean": clean,
            "index_flags_safe": index_flags_safe,
            "local_config_safe": local_config_safe,
        }
    )

    license_result = _checkout_file_sha256(
        target,
        source.license_path,
    )
    required_results = [
        _required_path_status(target, required)
        for required in source.required_paths
    ]
    required_complete = all(
        result["present"] is True and result["safe_kind"] is True
        for result in required_results
    )
    license_matches = (
        license_result["sha256"] == source.license_sha256
        and license_result["safe_regular_file"] is True
    )
    profile_complete = (
        tree_matches and license_matches and required_complete
    )
    usable = (
        remote_matches
        and branch_acceptable
        and exact_pin
        and clean is True
        and index_flags_safe is True
        and validation["exact_checkout_root"] is True
        and local_config_safe
        and profile_complete
    )
    validation.update(
        {
            "remote_matches": remote_matches,
            "branch_acceptable": branch_acceptable,
            "exact_pin": exact_pin,
            "tree_matches": tree_matches,
            "license_matches": license_matches,
            "required_paths_complete": required_complete,
            "profile_complete": profile_complete,
            "index_flags_safe": index_flags_safe is True,
            "local_config_safe": local_config_safe,
            "usable": usable,
        }
    )
    actual["license"] = license_result
    actual["required_paths"] = required_results

    if len(remote_values) > 1:
        errors.append(
            {
                "code": "multiple_origin_urls",
                "message": "origin has more than one configured URL",
            }
        )
    elif remote is None:
        errors.append(
            {"code": "origin_missing", "message": "origin URL is unavailable"}
        )
    elif not remote_matches:
        errors.append(
            {
                "code": "remote_mismatch",
                "message": "origin URL does not equal the acknowledged remote",
            }
        )
    if head is None:
        errors.append(
            {"code": "head_unavailable", "message": "HEAD commit is unavailable"}
        )
    elif not exact_pin:
        errors.append(
            {
                "code": "commit_mismatch",
                "message": "HEAD is not the acknowledged immutable commit",
            }
        )
    if tree is None:
        errors.append(
            {"code": "tree_unavailable", "message": "HEAD tree is unavailable"}
        )
    elif not tree_matches:
        errors.append(
            {
                "code": "tree_mismatch",
                "message": "HEAD tree is not the acknowledged root tree",
            }
        )
    if not branch_acceptable:
        errors.append(
            {
                "code": "branch_mismatch",
                "message": (
                    "checkout is neither detached nor on the acknowledged branch"
                ),
            }
        )
    if clean is None:
        errors.append(
            {
                "code": "cleanliness_unavailable",
                "message": "worktree cleanliness could not be inspected",
            }
        )
    if not local_config_safe:
        errors.append(
            {
                "code": "unsafe_local_git_config",
                "message": "local Git configuration is unavailable or unsafe",
            }
        )
    elif index_flags_safe is not True:
        errors.append(
            {
                "code": "unsafe_index_flags",
                "message": (
                    "tracked files use hidden or unsupported Git index flags"
                ),
            }
        )
    if local_config_safe and clean is False:
        errors.append(
            {
                "code": "dirty_worktree",
                "message": "worktree or untracked-file state is not clean",
            }
        )
    if license_result["safe_regular_file"] is not True:
        errors.append(
            {
                "code": "license_unavailable",
                "message": "acknowledged license file is missing, unsafe, or oversized",
            }
        )
    elif not license_matches:
        errors.append(
            {
                "code": "license_hash_mismatch",
                "message": "license file hash does not match the acknowledged profile",
            }
        )
    if not required_complete:
        errors.append(
            {
                "code": "required_paths_incomplete",
                "message": (
                    "one or more acknowledged product paths are missing or unsafe"
                ),
            }
        )

    record["actual"] = actual
    record["validation"] = validation
    record["errors"] = errors
    return record


def _source_envelope(source: AcknowledgedUpstream) -> dict[str, Any]:
    return {
        "name": source.name,
        "directory": source.directory,
        "path": f"<cache-root>/{source.directory}",
        "expected": {
            "remote": _sanitize_remote(source.remote),
            "branch": source.branch,
            "commit": source.commit,
            "tree": source.tree,
            "license": {
                "spdx_id": source.license_id,
                "path": source.license_path,
                "sha256": source.license_sha256,
                "sha256_basis": "checkout_text_crlf_normalized",
            },
            "required_paths": [
                {"path": item.path, "kind": item.kind}
                for item in source.required_paths
            ],
        },
    }


def _empty_actual(*, checkout_present: bool) -> dict[str, Any]:
    return {
        "checkout_present": checkout_present,
        "git_available": False,
        "exact_checkout_root": False,
        "remote": None,
        "remote_scope": (
            "sanitized_no_credentials_query_fragment_or_local_path"
        ),
        "branch": None,
        "detached": None,
        "head": None,
        "tree": None,
        "clean": None,
        "index_flags_safe": None,
        "local_config_safe": False,
        "license": {
            "sha256": None,
            "bytes": None,
            "safe_regular_file": False,
            "sha256_basis": "checkout_text_crlf_normalized",
        },
        "required_paths": [],
    }


def _empty_validation() -> dict[str, bool]:
    return {
        "exact_checkout_root": False,
        "remote_matches": False,
        "branch_acceptable": False,
        "exact_pin": False,
        "tree_matches": False,
        "license_matches": False,
        "required_paths_complete": False,
        "profile_complete": False,
        "index_flags_safe": False,
        "local_config_safe": False,
        "usable": False,
    }


def _prepare_existing(
    root: Path,
    target: Path,
    source: AcknowledgedUpstream,
    current: dict[str, Any],
    *,
    offline: bool,
) -> dict[str, Any]:
    validation = current["validation"]
    actual = current["actual"]
    if (
        actual["git_available"] is not True
        or validation["exact_checkout_root"] is not True
    ):
        return _operation(
            source,
            "checkout",
            "refused",
            "existing_child_is_not_exact_git_checkout",
        )
    if validation["remote_matches"] is not True:
        return _operation(
            source,
            "checkout",
            "refused",
            "existing_checkout_remote_mismatch",
        )
    if validation["local_config_safe"] is not True:
        return _operation(
            source,
            "checkout",
            "refused",
            "existing_checkout_local_config_unsafe",
        )
    if validation["index_flags_safe"] is not True:
        return _operation(
            source,
            "checkout",
            "refused",
            "existing_checkout_index_flags_unsafe",
        )
    if actual["clean"] is not True:
        return _operation(
            source,
            "checkout",
            "refused",
            "existing_checkout_not_clean",
        )

    if not offline:
        fetch = _run_git(
            target,
            (
                "-c",
                "protocol.allow=never",
                "-c",
                "protocol.https.allow=always",
                "fetch",
                "--no-tags",
                "origin",
                source.branch,
            ),
            timeout=GIT_MUTATION_TIMEOUT_SECONDS,
            redactions=(root, target, source.remote),
            isolated_config=True,
        )
        if fetch.returncode != 0:
            return _failed_operation(
                source,
                "fetch",
                "git_fetch_failed",
                fetch,
                redactions=(root, target, source.remote),
            )

    object_result = _run_git(
        target,
        ("cat-file", "-e", f"{source.commit}^{{commit}}"),
        timeout=GIT_QUERY_TIMEOUT_SECONDS,
        redactions=(root, target, source.remote),
    )
    if object_result.returncode != 0:
        return _failed_operation(
            source,
            "checkout",
            (
                "offline_pinned_object_missing"
                if offline
                else "fetched_pinned_object_missing"
            ),
            object_result,
            redactions=(root, target, source.remote),
        )

    checkout = _checkout_detached(
        root,
        target,
        source,
    )
    if checkout.returncode != 0:
        return _failed_operation(
            source,
            "checkout",
            "git_checkout_failed",
            checkout,
            redactions=(root, target, source.remote),
        )
    return _operation(
        source,
        "checkout",
        "completed",
        "used_existing_object" if offline else "fetched_acknowledged_branch",
    )


def _clone_pinned(
    root: Path,
    target: Path,
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".dcsmizzer-{source.directory}-",
            dir=root,
        )
    )
    try:
        temporary.rmdir()
        with tempfile.TemporaryDirectory(
            prefix=".dcsmizzer-git-template-",
            dir=root,
        ) as template_directory:
            clone = _run_git_without_checkout(
                source,
                temporary,
                Path(template_directory),
                redactions=(root, temporary, source.remote),
            )
        if clone.returncode != 0:
            return _failed_operation(
                source,
                "clone",
                "git_clone_failed",
                clone,
                redactions=(root, temporary, source.remote),
            )
        _validate_checkout_path(root, temporary, temporary.name)
        cloned = _source_status_for_temporary(root, temporary, source)
        if (
            cloned["validation"]["exact_checkout_root"] is not True
            or cloned["validation"]["remote_matches"] is not True
        ):
            return _operation(
                source,
                "clone",
                "failed",
                "cloned_repository_failed_identity_gate",
            )
        checkout = _checkout_detached(root, temporary, source)
        if checkout.returncode != 0:
            return _failed_operation(
                source,
                "clone",
                "git_checkout_failed",
                checkout,
                redactions=(root, temporary, source.remote),
            )
        pinned = _source_status_for_temporary(root, temporary, source)
        if pinned["validation"]["usable"] is not True:
            return _operation(
                source,
                "clone",
                "failed",
                "cloned_repository_failed_final_gate",
            )
        if _lstat_optional(target) is not None:
            return _operation(
                source,
                "clone",
                "refused",
                "recognized_checkout_appeared_during_clone",
            )
        temporary.rename(target)
        _validate_checkout_path(root, target, source.directory)
        return _operation(
            source,
            "clone",
            "completed",
            "cloned_and_detached_at_acknowledged_pin",
        )
    finally:
        _remove_owned_temporary(root, temporary, source.directory)


def _source_status_for_temporary(
    root: Path,
    temporary: Path,
    source: AcknowledgedUpstream,
) -> dict[str, Any]:
    temporary_source = AcknowledgedUpstream(
        name=source.name,
        remote=source.remote,
        branch=source.branch,
        commit=source.commit,
        tree=source.tree,
        directory=temporary.name,
        license_id=source.license_id,
        license_path=source.license_path,
        license_sha256=source.license_sha256,
        required_paths=source.required_paths,
    )
    return _source_status(root, temporary_source)


def _run_git_without_checkout(
    source: AcknowledgedUpstream,
    target: Path,
    template_directory: Path,
    *,
    redactions: Sequence[object],
) -> _GitResult:
    arguments = (
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "clone",
        "--no-checkout",
        "--single-branch",
        "--origin",
        "origin",
        "--branch",
        source.branch,
        f"--template={template_directory}",
        "--",
        source.remote,
        os.fspath(target),
    )
    return _run_git_command(
        arguments,
        timeout=GIT_MUTATION_TIMEOUT_SECONDS,
        redactions=redactions,
        isolated_config=True,
    )


def _checkout_detached(
    root: Path,
    target: Path,
    source: AcknowledgedUpstream,
) -> _GitResult:
    with tempfile.TemporaryDirectory(
        prefix=".dcsmizzer-disabled-hooks-",
        dir=root,
    ) as hooks_directory:
        return _run_git(
            target,
            (
                "-c",
                f"core.hooksPath={hooks_directory}",
                "-c",
                "maintenance.auto=false",
                "checkout",
                "--detach",
                "--quiet",
                source.commit,
            ),
            timeout=GIT_MUTATION_TIMEOUT_SECONDS,
            redactions=(root, target, source.remote, hooks_directory),
            isolated_config=True,
        )


def _remove_owned_temporary(
    root: Path,
    temporary: Path,
    directory: str,
) -> None:
    status_result = _lstat_optional(temporary)
    if status_result is None:
        return
    if (
        temporary.parent != root
        or not temporary.name.startswith(f".dcsmizzer-{directory}-")
        or _is_link_or_reparse(status_result)
        or not stat.S_ISDIR(status_result.st_mode)
    ):
        raise ValueError("refusing to remove an unsafe temporary checkout")
    shutil.rmtree(temporary, onexc=_clear_readonly_and_retry)


def _clear_readonly_and_retry(
    function: Any,
    path: str,
    error: BaseException,
) -> None:
    del error
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _operation(
    source: AcknowledgedUpstream,
    action: str,
    result: str,
    reason: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source.name,
        "action": action,
        "result": result,
    }
    if reason is not None:
        record["reason"] = reason
    return record


def _failed_operation(
    source: AcknowledgedUpstream,
    action: str,
    reason: str,
    result: _GitResult,
    *,
    redactions: Sequence[object],
) -> dict[str, Any]:
    record = _operation(source, action, "failed", reason)
    record["git_error"] = {
        "kind": (
            "timeout"
            if result.timed_out
            else "unavailable"
            if result.unavailable
            else "nonzero_exit"
        ),
        "returncode": result.returncode,
        "diagnostic": _bounded_diagnostic(
            result.stderr or result.stdout,
            redactions=redactions,
        ),
        "diagnostic_limit_bytes": MAX_GIT_DIAGNOSTIC_BYTES,
    }
    return record


def _run_git(
    root: Path,
    arguments: Sequence[str],
    *,
    timeout: int,
    redactions: Sequence[object],
    isolated_config: bool = False,
) -> _GitResult:
    return _run_git_command(
        ("-C", os.fspath(root), *arguments),
        timeout=timeout,
        redactions=redactions,
        isolated_config=isolated_config,
    )


def _run_git_command(
    arguments: Sequence[str],
    *,
    timeout: int,
    redactions: Sequence[object],
    isolated_config: bool = False,
) -> _GitResult:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
        }
    )
    if isolated_config:
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
                or key.startswith("GIT_ATTR_")
                or key.startswith("GIT_CONFIG_KEY_")
                or key.startswith("GIT_CONFIG_VALUE_")
            ):
                environment.pop(key, None)
        environment.update(
            {
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CONFIG_COUNT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_ALLOW_PROTOCOL": "https",
                "GIT_PROTOCOL_FROM_USER": "0",
            }
        )
    try:
        completed = subprocess.run(
            ["git", *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        return _GitResult(
            returncode=None,
            stdout=_coerce_process_text(error.stdout),
            stderr=_coerce_process_text(error.stderr),
            timed_out=True,
        )
    except OSError as error:
        return _GitResult(
            returncode=None,
            stdout="",
            stderr=_bounded_diagnostic(
                type(error).__name__,
                redactions=redactions,
            ),
            unavailable=True,
        )
    return _GitResult(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=_bounded_diagnostic(
            completed.stderr,
            redactions=redactions,
        ),
    )


def _coerce_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _bounded_diagnostic(
    value: str,
    *,
    redactions: Sequence[object],
) -> str:
    text = value
    secrets = sorted(
        {
            os.fspath(item)
            for item in redactions
            if item is not None and os.fspath(item)
        },
        key=len,
        reverse=True,
    )
    for secret in secrets:
        for variant in {
            secret,
            secret.replace("\\", "/"),
            secret.replace("/", "\\"),
        }:
            text = text.replace(variant, "<redacted-path>")
    text = re.sub(
        r"(?i)\bfile://[^\s\"']+",
        "file://<redacted-local-remote>",
        text,
    )
    text = re.sub(
        r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/][^\s\"']+",
        "<redacted-local-path>",
        text,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9])/(?:Users|home|tmp|private|var/tmp)/[^\s\"']+",
        "<redacted-local-path>",
        text,
    )
    visible = " ".join(text.replace("\x00", "\\x00").split())
    encoded = visible.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_GIT_DIAGNOSTIC_BYTES:
        return visible
    suffix = b"... [truncated]"
    prefix = encoded[: MAX_GIT_DIAGNOSTIC_BYTES - len(suffix)]
    return prefix.decode("utf-8", errors="ignore") + suffix.decode("ascii")


def _successful_line(result: _GitResult) -> str | None:
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _tracked_index_flags_safe(result: _GitResult) -> bool | None:
    if result.returncode != 0:
        return None
    records = [record for record in result.stdout.split("\x00") if record]
    return bool(records) and all(record.startswith("H ") for record in records)


def _git_metadata_file_empty(result: _GitResult) -> bool:
    if result.returncode != 0 or not result.stdout:
        return False
    path = Path(result.stdout)
    status_result = _lstat_optional(path)
    if status_result is None:
        return True
    if _is_link_or_reparse(status_result) or not stat.S_ISREG(status_result.st_mode):
        return False
    try:
        return status_result.st_size == 0 and path.read_bytes() == b""
    except OSError:
        return False


def _same_checkout_root(value: str, target: Path) -> bool:
    if not value:
        return False
    try:
        return Path(value).resolve(strict=True) == target.resolve(strict=True)
    except (OSError, RuntimeError):
        return False


def _checkout_file_sha256(
    root: Path,
    relative_path: str,
) -> dict[str, Any]:
    path = _contained_checkout_path(root, relative_path)
    if not _checkout_relative_chain_safe(root, relative_path):
        return {
            "sha256": None,
            "bytes": None,
            "safe_regular_file": False,
        }
    status_before = _lstat_optional(path)
    if (
        status_before is None
        or _is_link_or_reparse(status_before)
        or not stat.S_ISREG(status_before.st_mode)
        or status_before.st_size > MAX_LICENSE_BYTES
    ):
        return {
            "sha256": None,
            "bytes": (
                status_before.st_size
                if status_before is not None
                and stat.S_ISREG(status_before.st_mode)
                else None
            ),
            "safe_regular_file": False,
        }
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        payload = bytearray()
        while len(payload) <= MAX_LICENSE_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, MAX_LICENSE_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        status_after = path.lstat()
    finally:
        os.close(descriptor)
    safe = (
        len(payload) <= MAX_LICENSE_BYTES
        and stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(status_after.st_mode)
        and not _is_link_or_reparse(status_after)
        and _same_identity(status_before, opened)
        and _same_identity(opened, status_after)
    )
    return {
        "sha256": (
            hashlib.sha256(_crlf_normalized(payload)).hexdigest()
            if safe
            else None
        ),
        "bytes": len(payload),
        "safe_regular_file": safe,
        "sha256_basis": "checkout_text_crlf_normalized",
    }


def _crlf_normalized(payload: bytes | bytearray) -> bytes:
    return bytes(payload).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _required_path_status(
    root: Path,
    required: RequiredPath,
) -> dict[str, Any]:
    path = _contained_checkout_path(root, required.path)
    safe_chain = _checkout_relative_chain_safe(root, required.path)
    status_result = _lstat_optional(path) if safe_chain else None
    present = status_result is not None
    safe_kind = bool(
        safe_chain
        and status_result is not None
        and not _is_link_or_reparse(status_result)
        and (
            stat.S_ISREG(status_result.st_mode)
            if required.kind == "file"
            else stat.S_ISDIR(status_result.st_mode)
        )
    )
    return {
        "path": required.path,
        "kind": required.kind,
        "present": present,
        "safe_kind": safe_kind,
    }


def _checkout_relative_chain_safe(root: Path, relative_path: str) -> bool:
    current = root
    for component in Path(relative_path).parts:
        current /= component
        status_result = _lstat_optional(current)
        if status_result is None or _is_link_or_reparse(status_result):
            return False
    return True


def _contained_checkout_path(root: Path, relative_path: str) -> Path:
    if not _safe_relative_path(relative_path):
        raise ValueError("acknowledged checkout-relative path is unsafe")
    candidate = root.joinpath(*Path(relative_path).parts)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("acknowledged checkout-relative path escapes") from error
    return candidate


def _same_identity(
    first: os.stat_result,
    second: os.stat_result,
) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_ino != 0
    )


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_link_or_reparse(status_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(
        stat.S_ISLNK(status_result.st_mode)
        or (reparse_flag and attributes & reparse_flag)
    )


def _safe_component(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value)
        and value not in {".", ".."}
    )


def _safe_relative_path(value: str) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
    ):
        return False
    parts = value.split("/")
    return all(_safe_component(part) for part in parts)


def _safe_git_branch(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value) <= 256
        and not value.startswith("-")
        and not value.endswith(("/", ".", ".lock"))
        and ".." not in value
        and "//" not in value
        and "@{" not in value
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value)
    )


def _dangerous_local_config_key(key: str) -> bool:
    folded = key.casefold()
    if folded.startswith(
        (
            "alias.",
            "credential.",
            "filter.",
            "http.",
            "include.",
            "includeif.",
            "submodule.",
            "url.",
        )
    ):
        return True
    if folded in {
        "core.attributesfile",
        "core.alternaterefscommand",
        "core.askpass",
        "core.editor",
        "core.fsmonitor",
        "core.gitproxy",
        "core.hookspath",
        "core.ignorestat",
        "core.pager",
        "core.checkstat",
        "core.sshcommand",
        "core.trustctime",
        "core.worktree",
        "diff.external",
        "gc.recentobjectshook",
        "gpg.program",
        "gpg.ssh.program",
        "interactive.difffilter",
        "sequence.editor",
        "extensions.worktreeconfig",
    }:
        return True
    return folded.endswith(
        (
            ".command",
            ".driver",
            ".helper",
            ".proxy",
            ".receivepack",
            ".uploadpack",
        )
    )


def _safe_git_remote(value: str) -> bool:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 0 < len(value) <= 4096
        or value.startswith("-")
        or any(character in value for character in "\x00\r\n")
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        return False
    return bool(
        parsed.scheme.casefold() == "https"
        and hostname
        and not _local_hostname(hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _sanitize_remote(remote: str | None) -> str | None:
    """Return public provenance syntax without credentials or local paths."""

    if remote is None:
        return None
    value = remote.strip()
    if not value:
        return None
    if _looks_like_local_path(value):
        return "<redacted-local-remote>"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-local-or-unrecognized-remote>"
    if parsed.scheme:
        if parsed.scheme.casefold() == "file":
            return "file://<redacted-local-remote>"
        try:
            hostname = parsed.hostname
        except ValueError:
            return "<redacted-local-or-unrecognized-remote>"
        if _local_hostname(hostname):
            return "<redacted-local-remote>"
        public_netloc = parsed.netloc.rsplit("@", 1)[-1]
        if not public_netloc:
            return f"{parsed.scheme}://<redacted-invalid-remote>"
        return urlunsplit(
            (parsed.scheme, public_netloc, parsed.path, "", "")
        )
    scp = re.fullmatch(
        r"(?:[^@\s/:]+@)?(?P<host>[^@\s/:]+):"
        r"(?P<path>[^?#\s]+)(?:[?#].*)?",
        value,
    )
    if scp is not None:
        host = scp.group("host")
        if _local_hostname(host):
            return "<redacted-local-remote>"
        return f"{host}:{scp.group('path')}"
    return "<redacted-local-or-unrecognized-remote>"


def _looks_like_local_path(value: str) -> bool:
    return bool(
        value.startswith(("/", "./", "../", "\\\\", "\\?\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or value.casefold().startswith("file:")
    )


def _local_hostname(hostname: str | None) -> bool:
    if hostname is None:
        return True
    folded = hostname.casefold().strip("[]")
    return bool(
        folded in {"localhost", "::1", "0.0.0.0"}
        or folded.startswith("127.")
        or folded.endswith(".local")
    )
