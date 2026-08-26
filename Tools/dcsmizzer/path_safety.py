"""Filesystem path checks shared by security-sensitive readers and writers."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def canonical_existing_directory(path: Path, label: str) -> Path:
    """Return one canonical directory after rejecting linked path components.

    Windows can expose the same directory through an 8.3 alias (for example,
    ``RUNNER~1``) while :meth:`Path.resolve` returns its long name.  Comparing
    those spellings rejects a safe directory.  Checking every lexical and
    canonical component with ``lstat`` preserves the no-link boundary while
    allowing filesystem aliases that identify the same directory.
    """

    candidate = _absolute_path(path, label)
    before = _safe_directory_chain(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{label} cannot be resolved") from error
    after = _safe_directory_chain(candidate, label)
    canonical = _safe_directory_chain(resolved, label)
    if not _same_chain_identity(before, after):
        raise ValueError(f"{label} changed while it was validated")
    if not _same_identity(after[-1][1], canonical[-1][1]):
        raise ValueError(f"{label} resolved to a different directory")
    return resolved


def canonical_existing_file(path: Path, label: str) -> Path:
    """Return one canonical regular file without following linked components."""

    candidate = _absolute_path(path, label)
    canonical_parent = canonical_existing_directory(candidate.parent, label)
    parent_before = canonical_parent.lstat()
    before = _safe_regular_file(candidate, label)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{label} cannot be resolved") from error
    after = _safe_regular_file(candidate, label)
    canonical = _safe_regular_file(resolved, label)
    parent_after_path = canonical_existing_directory(candidate.parent, label)
    parent_after = parent_after_path.lstat()
    if (
        parent_after_path != canonical_parent
        or not _same_identity(parent_before, parent_after)
    ):
        raise ValueError(f"{label} parent changed while it was validated")
    if not _same_identity(before, after):
        raise ValueError(f"{label} changed while it was validated")
    if resolved.parent != canonical_parent or not _same_identity(after, canonical):
        raise ValueError(f"{label} resolved to a different file")
    return resolved


def _absolute_path(path: Path, label: str) -> Path:
    try:
        value = os.fspath(path)
    except TypeError as error:
        raise ValueError(f"{label} must be a filesystem path") from error
    if not value or "\x00" in value:
        raise ValueError(f"{label} must be a non-empty filesystem path")
    if os.name == "nt":
        _, tail = os.path.splitdrive(value)
        if ":" in tail:
            raise ValueError(
                f"{label} must not name a Windows alternate data stream"
            )
    try:
        return Path(os.path.abspath(value))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} cannot be made absolute") from error


def _safe_directory_chain(
    path: Path,
    label: str,
) -> list[tuple[Path, os.stat_result]]:
    if not path.is_absolute() or not path.anchor or not path.parts:
        raise ValueError(f"{label} is not an absolute directory")
    current = Path(path.parts[0])
    chain: list[tuple[Path, os.stat_result]] = []
    for component in (None, *path.parts[1:]):
        if component is not None:
            current /= component
        try:
            status_result = current.lstat()
        except OSError as error:
            raise ValueError(f"{label} does not exist") from error
        if _is_link_or_reparse(status_result):
            raise ValueError(f"{label} must not traverse a link or reparse point")
        if not stat.S_ISDIR(status_result.st_mode):
            raise ValueError(f"{label} is not a safe directory")
        chain.append((current, status_result))
    return chain


def _same_chain_identity(
    first: list[tuple[Path, os.stat_result]],
    second: list[tuple[Path, os.stat_result]],
) -> bool:
    return bool(
        len(first) == len(second)
        and all(
            first_path == second_path
            and _same_identity(first_status, second_status)
            for (first_path, first_status), (second_path, second_status) in zip(
                first,
                second,
                strict=True,
            )
        )
    )


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return bool(
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_ino != 0
    )


def _safe_regular_file(path: Path, label: str) -> os.stat_result:
    try:
        status_result = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} does not exist") from error
    if _is_link_or_reparse(status_result):
        raise ValueError(f"{label} must not be a link or reparse point")
    if not stat.S_ISREG(status_result.st_mode):
        raise ValueError(f"{label} is not a safe regular file")
    return status_result


def _is_link_or_reparse(status_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(
        stat.S_ISLNK(status_result.st_mode)
        or (reparse_flag and attributes & reparse_flag)
    )
