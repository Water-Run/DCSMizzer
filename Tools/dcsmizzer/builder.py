"""Deterministic low-level MIZ assembly and post-build verification."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import stat
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as calendar_date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from .archive import (
    ArchivePolicy,
    CORE_MEMBERS,
    inspect_miz,
    is_safe_archive_member_name,
)
from .facts import (
    CATEGORIES,
    collect_mission_facts,
    evaluate_expectations,
    expectation_coverage_warnings,
    numeric_tables,
    table,
    validate_expectations,
)
from .lua import LuaDataError, LuaTable, parse_lua_bytes
from .lua_write import (
    LuaSerializationError,
    dump_lua_assignment,
    json_to_lua,
)
from .logic import LogicSpecError, compile_logic
from .mission import analyse_miz, observe_miz_without_member_reads
from .structure import validate_mission_structure
from .templates import WAREHOUSE_COALITIONS


SPEC_SCHEMA = "dcsmizzer.miz-build-spec/v1"
BUILD_REPORT_SCHEMA = "dcsmizzer.miz-build/v1"
VERIFY_REPORT_SCHEMA = "dcsmizzer.miz-verification/v1"
# A build spec is a control-plane document: bulk briefing assets are external
# resource files with their own archive limits. 16 MiB leaves ample room for
# large mission tables while bounding the read, UTF-8 decode, and JSON object
# graph allocations caused by an untrusted input.
MAX_BUILD_SPEC_BYTES = 16 * 1024 * 1024
# Valid specs normally stay well below 32 levels. 128 preserves substantial
# authoring headroom while remaining safely below CPython's recursion ceiling
# for the recursive JSON-to-Lua and validation passes.
MAX_BUILD_SPEC_JSON_DEPTH = 128
QUALITY_PROFILES = frozenset({"technical_fixture", "complete_scenario"})
CORE_GLOBALS: dict[str, str] = {
    "mission": "mission",
    "options": "options",
    "warehouses": "warehouses",
    "l10n/DEFAULT/dictionary": "dictionary",
    "l10n/DEFAULT/mapResource": "mapResource",
}
SPEC_TABLES: dict[str, str] = {
    "mission": "mission",
    "options": "options",
    "warehouses": "warehouses",
    "dictionary": "l10n/DEFAULT/dictionary",
    "mapResource": "l10n/DEFAULT/mapResource",
}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
RESERVED_MEMBERS = frozenset((*CORE_MEMBERS, "theatre"))
_LOCAL_PATH_REDACTION = "<local-path-redacted>"
_WINDOWS_DRIVE_PATH = re.compile(r"(?i)(?<![a-z0-9.])[a-z]:[\\/]")
_BACKSLASH_UNC_PATH = re.compile(r"\\\\[^/\\\s]+[\\/]")
_FORWARD_UNC_PATH = re.compile(r"//[^/\\\s]+/")
_FILE_URI = re.compile(r"(?i)file:(?://)?[\\/]")
_EMBEDDED_POSIX_ABSOLUTE_PATH = re.compile(
    r"(?<![a-z0-9._~/\\-])/(?!/)",
    re.IGNORECASE,
)
_EMBEDDED_WINDOWS_ROOTED_PATH = re.compile(
    r"(?<![a-z0-9._~/\\-])\\(?!\\)",
    re.IGNORECASE,
)
_URI_WITH_PATH = re.compile(
    r"(?i)(?P<scheme>[a-z][a-z0-9+.-]*)://"
    r"(?P<authority>[^/\s\"'<>]+)(?P<path>/[^\s\"'<>]*)?"
)
_SCP_ABSOLUTE_PATH = re.compile(
    r"(?i)(?:[^@\s:]+@)?"
    r"(?P<host>\[[^\]]+\]|[^:/\\\s]+):(?P<path>[/\\][^\s]*)"
)


class BuildSpecError(ValueError):
    """The build specification or requested output operation is invalid."""


@dataclass(frozen=True)
class ResourceInput:
    member: str
    source: Path


@dataclass(frozen=True)
class BoundResourceInput:
    member: str
    source: Path
    stream: BinaryIO
    identity: os.stat_result
    size: int
    sha256: str


@dataclass(frozen=True)
class BuildSpec:
    path: Path
    sha256: str
    tables: dict[str, LuaTable]
    theatre: str
    resources: tuple[ResourceInput, ...]
    resource_members: tuple[str, ...]
    expectations: dict[str, Any]
    seed: str | int | None
    provenance: dict[str, Any]
    logic_summary: dict[str, Any] | None
    quality_profile: str


def _output_path_without_final_resolution(path: Path) -> Path:
    requested = path if path.is_absolute() else Path.cwd() / path
    try:
        parent = requested.parent.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise BuildSpecError("cannot resolve the output parent directory") from error
    return parent / requested.name


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _same_file_identity(
    first: os.stat_result,
    second: os.stat_result,
) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_ino != 0
    )


def _is_link_or_reparse(status: os.stat_result) -> bool:
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status, "st_file_attributes", 0)
    return bool(
        stat.S_ISLNK(status.st_mode)
        or (reparse_attribute and file_attributes & reparse_attribute)
    )


def _require_bound_regular_path(path: Path, descriptor: int) -> os.stat_result:
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        raise BuildSpecError("open artifact handle is not a regular file")
    current = _lstat_optional(path)
    if (
        current is None
        or not stat.S_ISREG(current.st_mode)
        or _is_link_or_reparse(current)
        or not _same_file_identity(opened, current)
    ):
        raise BuildSpecError("artifact path changed after its file handle was opened")
    return current


def _require_regular_stream(stream: BinaryIO) -> None:
    try:
        status = os.fstat(stream.fileno())
    except (AttributeError, OSError) as error:
        raise BuildSpecError(
            "artifact verification requires an open file handle"
        ) from error
    if not stat.S_ISREG(status.st_mode):
        raise BuildSpecError("artifact verification requires a regular file")


def _open_bound_regular_file(
    path: Path,
) -> tuple[int, os.stat_result]:
    before = _lstat_optional(path)
    if before is None:
        raise BuildSpecError("MIZ artifact does not exist")
    if _is_link_or_reparse(before):
        raise BuildSpecError(
            "MIZ artifact must not be a symbolic link or reparse point"
        )
    if not stat.S_ISREG(before.st_mode):
        raise BuildSpecError("MIZ artifact is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        after = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or _is_link_or_reparse(after)
            or not _same_file_identity(before, opened)
            or not _same_file_identity(opened, after)
        ):
            raise BuildSpecError("MIZ artifact path changed while it was being opened")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def _open_bound_resource_input(
    resource: ResourceInput,
) -> BoundResourceInput:
    before = _lstat_optional(resource.source)
    if before is None:
        raise BuildSpecError(f"resource {resource.member!r} does not exist")
    if _is_link_or_reparse(before):
        raise BuildSpecError(
            f"resource {resource.member!r} must not be a symbolic link or reparse point"
        )
    if not stat.S_ISREG(before.st_mode):
        raise BuildSpecError(f"resource {resource.member!r} is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    try:
        descriptor = os.open(resource.source, flags)
    except FileNotFoundError as error:
        raise BuildSpecError(
            f"resource {resource.member!r} changed while it was being opened"
        ) from error
    except OSError as error:
        raise BuildSpecError(f"cannot open resource {resource.member!r}") from error
    stream: BinaryIO | None = None
    try:
        opened = os.fstat(descriptor)
        after = resource.source.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or _is_link_or_reparse(after)
            or not _same_file_identity(before, opened)
            or not _same_file_identity(opened, after)
        ):
            raise BuildSpecError(
                f"resource {resource.member!r} path changed while it was being opened"
            )
        stream = os.fdopen(descriptor, "rb", closefd=True)
        if opened.st_size > ArchivePolicy().max_member_uncompressed:
            raise BuildSpecError(
                f"resource {resource.member!r} exceeds archive size policy"
            )
        sha256 = _hash_exact_resource_stream(
            stream,
            opened.st_size,
            resource.member,
        )
        final_status = os.fstat(stream.fileno())
        _require_bound_resource_path(
            resource.member,
            resource.source,
            stream,
            opened,
        )
        if final_status.st_size != opened.st_size:
            raise BuildSpecError(
                f"resource {resource.member!r} content changed while it was being bound"
            )
        return BoundResourceInput(
            member=resource.member,
            source=resource.source,
            stream=stream,
            identity=opened,
            size=opened.st_size,
            sha256=sha256,
        )
    except BaseException:
        if stream is not None:
            stream.close()
        else:
            os.close(descriptor)
        raise


def _open_bound_resource_inputs(
    spec: BuildSpec,
) -> tuple[BoundResourceInput, ...]:
    opened: list[BoundResourceInput] = []
    try:
        for resource in spec.resources:
            opened.append(_open_bound_resource_input(resource))
        return tuple(opened)
    except BaseException:
        _close_bound_resource_inputs(tuple(opened))
        raise


def _close_bound_resource_inputs(
    resources: tuple[BoundResourceInput, ...],
) -> None:
    first_error: OSError | None = None
    for resource in reversed(resources):
        try:
            resource.stream.close()
        except OSError as error:
            first_error = first_error or error
    if first_error is not None:
        raise BuildSpecError("could not close bound resource inputs") from first_error


def _require_bound_resource_path(
    member: str,
    source: Path,
    stream: BinaryIO,
    expected: os.stat_result,
) -> os.stat_result:
    try:
        opened = os.fstat(stream.fileno())
    except (AttributeError, OSError) as error:
        raise BuildSpecError(
            f"resource {member!r} is no longer bound to an open handle"
        ) from error
    current = _lstat_optional(source)
    if (
        current is None
        or not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or _is_link_or_reparse(current)
        or not _same_file_identity(expected, opened)
        or not _same_file_identity(opened, current)
    ):
        raise BuildSpecError(
            f"resource {member!r} path changed after its file handle was opened"
        )
    return opened


def _bound_resource_bytes(resource: BoundResourceInput) -> bytes:
    _require_bound_resource_path(
        resource.member,
        resource.source,
        resource.stream,
        resource.identity,
    )
    try:
        resource.stream.seek(0)
        data = _read_exact_resource_stream(
            resource.stream,
            resource.size,
            resource.member,
        )
        status = os.fstat(resource.stream.fileno())
    except OSError as error:
        raise BuildSpecError(
            f"cannot read bound resource {resource.member!r}"
        ) from error
    _require_bound_resource_path(
        resource.member,
        resource.source,
        resource.stream,
        resource.identity,
    )
    if (
        status.st_size != resource.size
        or len(data) != resource.size
        or hashlib.sha256(data).hexdigest() != resource.sha256
    ):
        raise BuildSpecError(
            f"resource {resource.member!r} content changed after it was bound"
        )
    return data


def _require_bound_resources_unchanged(
    resources: tuple[BoundResourceInput, ...],
) -> None:
    for resource in resources:
        _require_bound_resource_path(
            resource.member,
            resource.source,
            resource.stream,
            resource.identity,
        )
        try:
            digest = _hash_exact_resource_stream(
                resource.stream,
                resource.size,
                resource.member,
            )
            status = os.fstat(resource.stream.fileno())
        except OSError as error:
            raise BuildSpecError(
                f"cannot recheck bound resource {resource.member!r}"
            ) from error
        _require_bound_resource_path(
            resource.member,
            resource.source,
            resource.stream,
            resource.identity,
        )
        if status.st_size != resource.size or digest != resource.sha256:
            raise BuildSpecError(
                f"resource {resource.member!r} content changed after it was bound"
            )


def _read_exact_resource_stream(
    stream: BinaryIO,
    expected_size: int,
    member: str,
) -> bytes:
    remaining = expected_size
    chunks: list[bytes] = []
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise BuildSpecError(
                f"resource {member!r} content changed while it was read"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    if stream.read(1):
        raise BuildSpecError(f"resource {member!r} content changed while it was read")
    return b"".join(chunks)


def _hash_exact_resource_stream(
    stream: BinaryIO,
    expected_size: int,
    member: str,
) -> str:
    stream.seek(0)
    remaining = expected_size
    digest = hashlib.sha256()
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise BuildSpecError(
                f"resource {member!r} content changed while it was read"
            )
        digest.update(chunk)
        remaining -= len(chunk)
    if stream.read(1):
        raise BuildSpecError(f"resource {member!r} content changed while it was read")
    return digest.hexdigest()


def _require_resource_binding_set(
    spec: BuildSpec,
    resources: tuple[BoundResourceInput, ...],
) -> None:
    members = tuple(sorted(resource.member for resource in resources))
    if members != spec.resource_members:
        raise BuildSpecError(
            "bound resource inputs do not match the build specification"
        )


def _unlink_if_identity(
    path: Path,
    expected: os.stat_result,
) -> bool:
    current = _lstat_optional(path)
    if (
        current is None
        or not stat.S_ISREG(current.st_mode)
        or _is_link_or_reparse(current)
        or not _same_file_identity(current, expected)
    ):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _require_regular_identity(
    path: Path,
    expected: os.stat_result,
    message: str,
) -> os.stat_result:
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or _is_link_or_reparse(current)
        or not _same_file_identity(expected, current)
    ):
        raise BuildSpecError(message)
    return current


def _publication_output_status(
    output: Path,
    *,
    force: bool,
) -> os.stat_result | None:
    current = _lstat_optional(output)
    if current is None:
        return None
    if _is_link_or_reparse(current):
        raise BuildSpecError(
            "output path became a symbolic link or reparse point during publication"
        )
    if not stat.S_ISREG(current.st_mode):
        raise BuildSpecError("output path became a non-file during publication")
    if not force:
        raise BuildSpecError("output appeared while publishing; it was not replaced")
    return current


def _publish_candidate(
    candidate: Path,
    descriptor: int,
    output: Path,
    *,
    force: bool,
) -> None:
    candidate_status = os.fstat(descriptor)
    _require_bound_regular_path(candidate, descriptor)
    staging = candidate.with_name(f"{candidate.name}.publish")
    backup = candidate.with_name(f"{candidate.name}.previous")
    staging_created = False
    backup_created = False
    previous_output_status: os.stat_result | None = None
    publication_attempted = False
    try:
        os.link(candidate, staging, follow_symlinks=False)
        staging_created = True
        staging_error = (
            "publication staging path does not identify the validated candidate"
        )
        _require_regular_identity(
            staging,
            candidate_status,
            staging_error,
        )
        _require_bound_regular_path(candidate, descriptor)
        previous_output_status = _publication_output_status(
            output,
            force=force,
        )
        if previous_output_status is not None:
            os.link(output, backup, follow_symlinks=False)
            backup_created = True
            _require_regular_identity(
                backup,
                previous_output_status,
                "publication backup does not identify the previous output",
            )
            _require_regular_identity(
                output,
                previous_output_status,
                "output changed before guarded publication",
            )
        _require_regular_identity(
            staging,
            candidate_status,
            staging_error,
        )
        publication_attempted = True
        if force:
            os.replace(staging, output)
            staging_created = False
        else:
            try:
                os.link(staging, output, follow_symlinks=False)
            except FileExistsError as error:
                raise BuildSpecError(
                    "output appeared while publishing; it was not replaced"
                ) from error
        try:
            _require_regular_identity(
                output,
                candidate_status,
                "published path does not identify the validated candidate",
            )
        except (BuildSpecError, OSError):
            if backup_created and previous_output_status is not None:
                _restore_previous_output(
                    backup,
                    previous_output_status,
                    output,
                )
                backup_created = False
            elif publication_attempted:
                _remove_failed_publication(output)
            raise
        if backup_created and previous_output_status is not None:
            if not _unlink_if_identity(backup, previous_output_status):
                _restore_previous_output(
                    backup,
                    previous_output_status,
                    output,
                )
                backup_created = False
                raise BuildSpecError(
                    "could not securely remove the publication backup; "
                    "the previous output was restored"
                )
            backup_created = False
    finally:
        if staging_created:
            _unlink_if_identity(staging, candidate_status)
        if backup_created and previous_output_status is not None:
            _unlink_if_identity(backup, previous_output_status)


def _restore_previous_output(
    backup: Path,
    expected: os.stat_result,
    output: Path,
) -> None:
    _require_regular_identity(
        backup,
        expected,
        "publication backup changed before rollback",
    )
    os.replace(backup, output)
    _require_regular_identity(
        output,
        expected,
        "previous output could not be restored after publication failure",
    )


def _remove_failed_publication(output: Path) -> None:
    current = _lstat_optional(output)
    if current is None:
        return
    if stat.S_ISREG(current.st_mode) and not _is_link_or_reparse(current):
        _unlink_if_identity(output, current)
        return
    if _is_link_or_reparse(current):
        try:
            output.unlink()
        except FileNotFoundError:
            pass


def build_miz(
    spec_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Build a MIZ, then read it back and run all available static checks."""

    spec = load_build_spec(spec_path, require_resource_files=False)
    output = _output_path_without_final_resolution(output_path)
    if output.suffix.casefold() != ".miz":
        raise BuildSpecError("output path must use the .miz extension")
    if output == spec.path:
        raise BuildSpecError("output path cannot overwrite the build specification")
    for resource in spec.resources:
        if output == resource.source:
            raise BuildSpecError("output path cannot overwrite a resource input")
    output_status = _lstat_optional(output)
    if output_status is not None and _is_link_or_reparse(output_status):
        raise BuildSpecError("output path must not be a symbolic link or reparse point")
    existed_before = output_status is not None
    if existed_before and not force:
        raise BuildSpecError("output already exists; pass --force to replace it")
    if output_status is not None and not stat.S_ISREG(output_status.st_mode):
        raise BuildSpecError("output path exists and is not a file")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BuildSpecError("cannot prepare the requested output directory") from error
    temporary: Path | None = None
    descriptor: int | None = None
    stream: BinaryIO | None = None
    candidate_status: os.stat_result | None = None
    bound_resources: tuple[BoundResourceInput, ...] = ()
    try:
        bound_resources = _open_bound_resource_inputs(spec)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
        )
        temporary = Path(temporary_name)
        candidate_status = os.fstat(descriptor)
        if not stat.S_ISREG(candidate_status.st_mode):
            raise BuildSpecError("temporary build candidate is not a regular file")
        stream = os.fdopen(descriptor, "w+b", closefd=False)
        _write_miz(spec, stream, bound_resources)
        stream.flush()
        os.fsync(descriptor)
        report, valid = _verify(
            stream,
            spec,
            resources=bound_resources,
            schema=BUILD_REPORT_SCHEMA,
            artifact_name=temporary.name,
        )
        _require_bound_regular_path(temporary, descriptor)
        _require_bound_resources_unchanged(bound_resources)
        candidate = {
            "artifact_sha256": report["artifact_sha256"],
            "artifact_bytes": report["artifact_bytes"],
            "validated_in_temporary_file": True,
            "validated_from_original_open_handle": True,
            "retained_after_failure": False,
        }
        if valid:
            _publish_candidate(
                temporary,
                descriptor,
                output,
                force=force,
            )
        report["artifact"] = output.name if valid else None
        report["requested_output"] = output.name
        report["candidate"] = candidate
        report["publication"] = {
            "published": valid,
            "reason": (
                "available_checks_passed"
                if valid
                else "candidate_failed_available_checks"
            ),
            "replaced_existing_output": bool(valid and existed_before),
            "existing_output_preserved": bool(not valid and existed_before),
            "new_output_absent": bool(not valid and not existed_before),
            "atomic": False,
            "filesystem_path_update_atomic": True,
            "candidate_identity_bound_to_open_handle": True,
            "trusted_directory_required": True,
            "security_boundary": (
                "the output directory must not be writable by an "
                "untrusted concurrent actor"
            ),
            "path_scope": "basename_only",
        }
    except OSError as error:
        raise BuildSpecError(
            "candidate construction or guarded publication failed"
        ) from error
    finally:
        cleanup_error: OSError | None = None
        if stream is not None:
            try:
                stream.close()
            except OSError as error:
                cleanup_error = error
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                cleanup_error = cleanup_error or error
        if temporary is not None and candidate_status is not None:
            try:
                _unlink_if_identity(temporary, candidate_status)
            except OSError as error:
                cleanup_error = cleanup_error or error
        try:
            _close_bound_resource_inputs(bound_resources)
        except BuildSpecError as error:
            if cleanup_error is None:
                raise error
        if cleanup_error is not None:
            raise BuildSpecError(
                "could not close or remove the temporary build candidate"
            ) from cleanup_error

    report["input_spec"] = spec.path.name
    report["generation"] = {
        "method": "dcsmizzer_stdlib_low_level_assembler",
        "deterministic_archive": True,
        "seed": spec.seed,
        "spec_sha256": spec.sha256,
        "provenance": _sanitize_provenance(spec.provenance),
        "provenance_path_policy": "recursive_local_paths_redacted",
        "logic_compilation": spec.logic_summary,
        "quality_profile": spec.quality_profile,
    }
    report["replaced_existing_output"] = bool(valid and existed_before)
    return report, valid


def verify_miz(
    miz_path: Path,
    spec_path: Path,
) -> tuple[dict[str, Any], bool]:
    """Verify an existing MIZ against the complete low-level build spec."""

    spec = load_build_spec(spec_path, require_resource_files=False)
    requested_miz = _output_path_without_final_resolution(miz_path)
    descriptor: int | None = None
    stream: BinaryIO | None = None
    bound_resources: tuple[BoundResourceInput, ...] = ()
    try:
        bound_resources = _open_bound_resource_inputs(spec)
        descriptor, _ = _open_bound_regular_file(requested_miz)
        stream = os.fdopen(descriptor, "rb", closefd=False)
        report, valid = _verify(
            stream,
            spec,
            resources=bound_resources,
            schema=VERIFY_REPORT_SCHEMA,
            artifact_name=requested_miz.name,
        )
        _require_bound_regular_path(requested_miz, descriptor)
        _require_bound_resources_unchanged(bound_resources)
        report["validation"]["artifact_identity_bound_to_open_handle"] = True
    except OSError as error:
        raise BuildSpecError("cannot read the MIZ input artifact") from error
    finally:
        close_error: OSError | None = None
        if stream is not None:
            try:
                stream.close()
            except OSError as error:
                close_error = error
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                close_error = close_error or error
        try:
            _close_bound_resource_inputs(bound_resources)
        except BuildSpecError as error:
            if close_error is None:
                raise error
        if close_error is not None:
            raise BuildSpecError(
                "could not close the MIZ input artifact"
            ) from close_error
    report["input_spec"] = spec.path.name
    report["spec_sha256"] = spec.sha256
    report["logic_compilation"] = spec.logic_summary
    return report, valid


def load_build_spec(
    path: Path,
    *,
    require_resource_files: bool,
) -> BuildSpec:
    """Load one size- and depth-bounded build-spec JSON document."""

    try:
        return _load_build_spec(
            path,
            require_resource_files=require_resource_files,
        )
    except RecursionError as error:
        raise BuildSpecError(
            "build specification exceeds safe processing depth"
        ) from error


def _load_build_spec(
    path: Path,
    *,
    require_resource_files: bool,
) -> BuildSpec:
    try:
        source = path.resolve()
    except (OSError, RuntimeError) as error:
        raise BuildSpecError("cannot resolve the build specification path") from error
    if not source.is_file():
        raise BuildSpecError("build specification does not exist")
    try:
        with source.open("rb") as stream:
            raw_bytes = stream.read(MAX_BUILD_SPEC_BYTES + 1)
    except OSError as error:
        raise BuildSpecError(
            "cannot read the build specification (filesystem error)"
        ) from error
    if len(raw_bytes) > MAX_BUILD_SPEC_BYTES:
        raise BuildSpecError(
            f"build specification exceeds the {MAX_BUILD_SPEC_BYTES}-byte input limit"
        )
    _preflight_json_depth(raw_bytes)
    try:
        decoded = json.loads(
            raw_bytes.decode("utf-8-sig"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
            parse_float=_parse_finite_json_float,
            parse_int=_parse_finite_json_int,
        )
    except UnicodeDecodeError as error:
        raise BuildSpecError("build specification is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise BuildSpecError(
            "cannot parse build specification JSON at "
            f"line {error.lineno}, column {error.colno}"
        ) from error
    if not isinstance(decoded, dict):
        raise BuildSpecError("build specification root must be an object")

    allowed = {
        "schema",
        "seed",
        "provenance",
        *SPEC_TABLES,
        "resources",
        "expect",
        "logic",
        "quality",
    }
    unknown = set(decoded) - allowed
    if unknown:
        rendered_unknown = ", ".join(
            _bounded_json_key(key) for key in sorted(unknown)[:8]
        )
        omitted = len(unknown) - min(len(unknown), 8)
        if omitted:
            rendered_unknown += f", … ({omitted} more)"
        raise BuildSpecError(
            f"build specification contains {len(unknown)} unknown key(s): "
            f"{rendered_unknown}"
        )
    if decoded.get("schema") != SPEC_SCHEMA:
        raise BuildSpecError(f"schema must be {SPEC_SCHEMA!r}")
    missing = [name for name in SPEC_TABLES if name not in decoded]
    if missing:
        raise BuildSpecError(f"build specification is missing: {missing}")

    quality_profile = _quality_profile(decoded.get("quality"))
    logic_summary: dict[str, Any] | None = None
    if "logic" in decoded:
        mission_value = decoded["mission"]
        if not isinstance(mission_value, dict):
            raise BuildSpecError("mission must be a JSON object when logic is used")
        generated_fields = {"trigrules", "trig", "goals", "result"}
        conflicts = generated_fields.intersection(mission_value)
        if conflicts:
            raise BuildSpecError(
                "logic cannot be combined with caller-supplied mission fields: "
                f"{sorted(conflicts)}"
            )
        try:
            compiled, logic_summary = compile_logic(decoded["logic"])
        except LogicSpecError as error:
            raise BuildSpecError(str(error)) from error
        logic_summary["flag_dataflow"] = _logic_flag_dataflow(decoded["logic"])
        logic_summary["terminal_outcome_dataflow"] = _logic_terminal_outcome_dataflow(
            decoded["logic"]
        )
        mission_value.update(compiled)

    tables: dict[str, LuaTable] = {}
    for spec_name, member_name in SPEC_TABLES.items():
        try:
            value = json_to_lua(decoded[spec_name], path=f"$.{spec_name}")
        except LuaSerializationError as error:
            raise BuildSpecError(str(error)) from error
        if not isinstance(value, LuaTable):
            raise BuildSpecError(f"{spec_name} must encode a Lua table")
        tables[member_name] = value

    mission = tables["mission"]
    version = mission.get("version")
    if not _is_number(version):
        raise BuildSpecError("mission.version must be a number")
    theatre = mission.get("theatre")
    if not isinstance(theatre, str) or not theatre.strip():
        raise BuildSpecError("mission.theatre must be a nonempty string")
    if "\x00" in theatre or "\r" in theatre or "\n" in theatre:
        raise BuildSpecError("mission.theatre contains forbidden characters")

    _validate_flat_string_table(tables["l10n/DEFAULT/dictionary"], "dictionary")
    _validate_flat_string_table(
        tables["l10n/DEFAULT/mapResource"],
        "mapResource",
    )
    _validate_warehouses_table(tables["warehouses"])
    structure = validate_mission_structure(
        mission,
        dictionary=tables["l10n/DEFAULT/dictionary"],
        profile=quality_profile,
    )
    if not structure["valid"]:
        errors = [
            item for item in structure["diagnostics"] if item["severity"] == "error"
        ]
        codes = sorted({item["code"] for item in errors})
        locations = sorted({f"{item['code']}@{item['path']}" for item in errors})
        location_suffix = ""
        if locations:
            shown = locations[:20]
            if len(locations) > len(shown):
                shown.append(f"... {len(locations) - len(shown)} additional error(s)")
            location_suffix = f"; locations: {shown}"
        raise BuildSpecError(
            f"mission failed limited structural checks: {codes}{location_suffix}"
        )

    resources_value = decoded.get("resources", [])
    if not isinstance(resources_value, list):
        raise BuildSpecError("resources must be an array")
    resources: list[ResourceInput] = []
    members: set[str] = set()
    for index, item in enumerate(resources_value):
        item_path = f"resources[{index}]"
        if not isinstance(item, dict) or set(item) != {"member", "source"}:
            raise BuildSpecError(f"{item_path} must contain exactly member and source")
        member = item["member"]
        source_name = item["source"]
        if not isinstance(member, str) or not isinstance(source_name, str):
            raise BuildSpecError(f"{item_path} member/source must be strings")
        member = member.replace("\\", "/")
        if not is_safe_archive_member_name(member):
            raise BuildSpecError(f"{item_path} has an unsafe archive member")
        if member in RESERVED_MEMBERS:
            raise BuildSpecError(f"{item_path} would overwrite a reserved member")
        if member in members:
            raise BuildSpecError(f"{item_path} duplicates archive member {member!r}")
        members.add(member)
        resource_source = Path(source_name)
        if not resource_source.is_absolute():
            resource_source = source.parent / resource_source
        try:
            resource_source = resource_source.resolve()
        except (OSError, RuntimeError) as error:
            raise BuildSpecError(
                f"{item_path} source path cannot be resolved"
            ) from error
        if require_resource_files and not resource_source.is_file():
            raise BuildSpecError(f"{item_path} source does not exist")
        resources.append(ResourceInput(member=member, source=resource_source))

    expectations = decoded.get("expect", {})
    try:
        validate_expectations(expectations)
    except ValueError as error:
        raise BuildSpecError(str(error)) from error
    provenance = decoded.get("provenance", {})
    if not isinstance(provenance, dict):
        raise BuildSpecError("provenance must be an object")
    seed = decoded.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, str | int)):
        raise BuildSpecError("seed must be a string, integer, or omitted")
    if quality_profile == "complete_scenario":
        _validate_complete_spec(
            decoded,
            tables=tables,
            expectations=expectations,
            provenance=provenance,
            seed=seed,
        )

    return BuildSpec(
        path=source,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        tables=tables,
        theatre=theatre,
        resources=tuple(resources),
        resource_members=tuple(sorted(members)),
        expectations=expectations,
        seed=seed,
        provenance=provenance,
        logic_summary=logic_summary,
        quality_profile=quality_profile,
    )


def _write_miz(
    spec: BuildSpec,
    output: BinaryIO,
    resources: tuple[BoundResourceInput, ...],
) -> None:
    _require_resource_binding_set(spec, resources)
    policy = ArchivePolicy()
    payloads: list[tuple[str, bytes]] = []
    for _spec_name, member_name in SPEC_TABLES.items():
        global_name = CORE_GLOBALS[member_name]
        payloads.append(
            (
                member_name,
                dump_lua_assignment(global_name, spec.tables[member_name]),
            )
        )
    payloads.append(("theatre", spec.theatre.encode("utf-8")))
    if len(payloads) + len(resources) > policy.max_members:
        raise BuildSpecError("build exceeds archive member-count policy")
    total_bytes = sum(len(data) for _member, data in payloads)
    for member, data in payloads:
        if len(data) > policy.max_member_uncompressed:
            raise BuildSpecError(f"core member {member!r} exceeds archive size policy")
    for resource in sorted(resources, key=lambda item: item.member):
        size = resource.size
        if size > policy.max_member_uncompressed:
            raise BuildSpecError(
                f"resource {resource.member!r} exceeds archive size policy"
            )
        total_bytes += size
        if total_bytes > policy.max_total_uncompressed:
            raise BuildSpecError("build exceeds total archive size policy")
        data = _bound_resource_bytes(resource)
        payloads.append((resource.member, data))
    if total_bytes > policy.max_total_uncompressed:
        raise BuildSpecError("build exceeds total archive size policy")

    output.seek(0)
    output.truncate(0)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for member, data in payloads:
            info = zipfile.ZipInfo(member, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(
                info,
                data,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def _verify(
    miz_file: BinaryIO,
    spec: BuildSpec,
    *,
    resources: tuple[BoundResourceInput, ...],
    schema: str,
    artifact_name: str,
) -> tuple[dict[str, Any], bool]:
    _require_resource_binding_set(spec, resources)
    _require_regular_stream(miz_file)
    archive = inspect_miz(miz_file, verify_crc=True)
    content_read_blocked = bool(
        not archive.valid_zip or not archive.safe or archive.crc_status != "passed"
    )
    if content_read_blocked:
        mission_observation = observe_miz_without_member_reads(
            miz_file,
        )
        parsed_tables: dict[str, LuaTable] = {}
        table_errors = {"archive": "content_read_blocked"}
        archive_names: set[str] = set()
        theatre_member = None
    else:
        mission_observation = analyse_miz(miz_file)
        (
            parsed_tables,
            table_errors,
            archive_names,
            theatre_member,
        ) = _read_tables(miz_file)
    table_equality = {
        member: parsed_tables.get(member) == expected
        for member, expected in spec.tables.items()
    }
    all_core_tables_equal = len(parsed_tables) == len(CORE_MEMBERS) and all(
        table_equality.values()
    )
    theatre_member_matches = theatre_member == spec.theatre
    expected_members = {
        *CORE_MEMBERS,
        "theatre",
        *spec.resource_members,
    }
    unexpected_members = sorted(archive_names - expected_members)
    exact_member_set = archive_names == expected_members
    expected_resources_present = all(
        member in archive_names for member in spec.resource_members
    )
    if content_read_blocked:
        resource_equality: dict[str, bool] = {}
        resource_errors = {"archive": "content_read_blocked"}
    else:
        resource_equality, resource_errors = _compare_resources(
            miz_file,
            resources,
        )
    all_resources_equal = (
        len(resource_equality) == len(spec.resource_members)
        and all(resource_equality.values())
        and not resource_errors
    )

    mission = parsed_tables.get("mission")
    dictionary = parsed_tables.get("l10n/DEFAULT/dictionary")
    if mission is not None:
        structure = validate_mission_structure(
            mission,
            dictionary=dictionary,
            profile=spec.quality_profile,
        )
        facts = collect_mission_facts(
            mission,
            dictionary=dictionary,
            stats=mission_observation.stats,
        )
        checks, contract_valid = evaluate_expectations(
            spec.expectations,
            facts,
        )
        contract_coverage_warnings = expectation_coverage_warnings(
            spec.expectations,
            facts,
            require_role_coverage=(spec.quality_profile == "complete_scenario"),
        )
    else:
        structure = {
            "scope": [],
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [
                {
                    "code": "mission_table_unavailable",
                    "severity": "error",
                    "path": "$",
                }
            ],
            "runtime_validity_implied": False,
        }
        checks = []
        contract_valid = not spec.expectations
        contract_coverage_warnings = ["mission_table_unavailable"]

    archive_valid = bool(
        archive.valid_zip
        and archive.safe
        and archive.crc_status == "passed"
        and archive.duplicate_member_extras == 0
    )
    all_core_tables_parsed = len(parsed_tables) == len(CORE_MEMBERS)
    resources_complete = (
        mission_observation.stats.missing_resource_members == 0
        and expected_resources_present
        and all_resources_equal
    )
    static_structure_valid = bool(
        archive_valid
        and mission_observation.parse_valid
        and all_core_tables_parsed
        and exact_member_set
        and theatre_member_matches
        and resources_complete
        and structure["valid"]
    )
    review_warnings_clear = bool(
        structure["warning_count"] == 0 and not contract_coverage_warnings
    )
    quality_gate_passed = bool(
        spec.quality_profile != "complete_scenario" or review_warnings_clear
    )
    available_checks_passed = bool(
        static_structure_valid
        and all_core_tables_equal
        and contract_valid
        and quality_gate_passed
    )
    _require_bound_resources_unchanged(resources)
    report = {
        "schema": schema,
        "path_scope": "basename_only",
        "artifact": artifact_name,
        "artifact_sha256": _sha256_stream(miz_file),
        "artifact_bytes": os.fstat(miz_file.fileno()).st_size,
        "archive": archive.to_dict(),
        "core_table_errors": table_errors,
        "core_table_equality": table_equality,
        "unexpected_members": unexpected_members,
        "resource_errors": resource_errors,
        "resource_equality": resource_equality,
        "limited_structure": structure,
        "contract": {
            "requested": spec.expectations,
            "checks": checks,
            "coverage_warning_count": len(contract_coverage_warnings),
            "coverage_warnings": contract_coverage_warnings,
        },
        "quality": {
            "profile": spec.quality_profile,
            "warnings_are_fatal": (spec.quality_profile == "complete_scenario"),
            "gate_passed": quality_gate_passed,
        },
        "validation": {
            "archive_valid": archive_valid,
            "archive_content_read_blocked": content_read_blocked,
            "crc_verified": archive.crc_status == "passed",
            "all_core_tables_parsed": all_core_tables_parsed,
            "all_core_tables_equal": all_core_tables_equal,
            "exact_member_set": exact_member_set,
            "theatre_member_matches": theatre_member_matches,
            "expected_resources_present": expected_resources_present,
            "all_resources_equal": all_resources_equal,
            "resources_complete": resources_complete,
            "resource_inputs_identity_bound_to_open_handles": True,
            "resource_inputs_content_bound_to_sha256": True,
            "static_structure_valid": static_structure_valid,
            "contract_valid": contract_valid,
            "review_warnings_clear": review_warnings_clear,
            "quality_gate_passed": quality_gate_passed,
            "available_checks_passed": available_checks_passed,
            "runtime_valid": None,
        },
        "limitations": [
            "The builder serialized only caller-supplied, low-level DCS data.",
            "Exact identifiers and compatibility were not inferred or verified "
            "by the builder.",
            "No Lua code was executed.",
            "No DCS or Mission Editor process was started.",
            "Runtime validity remains unknown until the target DCS version "
            "loads the mission.",
        ],
    }
    return report, available_checks_passed


def _compare_resources(
    miz_file: BinaryIO,
    resources: tuple[BoundResourceInput, ...],
) -> tuple[dict[str, bool], dict[str, str]]:
    equality: dict[str, bool] = {}
    errors: dict[str, str] = {}
    try:
        miz_file.seek(0)
        with zipfile.ZipFile(miz_file) as archive:
            for resource in resources:
                try:
                    with archive.open(resource.member) as stream:
                        artifact_hash = _hash_stream(stream)
                    equality[resource.member] = artifact_hash == resource.sha256
                except KeyError:
                    equality[resource.member] = False
                    errors[resource.member] = "missing"
                except (OSError, RuntimeError):
                    equality[resource.member] = False
                    errors[resource.member] = "read_error"
    except (OSError, zipfile.BadZipFile):
        errors["archive"] = "bad_zip"
    return equality, errors


def _read_tables(
    miz_file: BinaryIO,
) -> tuple[dict[str, LuaTable], dict[str, str], set[str], str | None]:
    tables: dict[str, LuaTable] = {}
    errors: dict[str, str] = {}
    archive_names: set[str] = set()
    theatre_member: str | None = None
    try:
        miz_file.seek(0)
        with zipfile.ZipFile(miz_file) as archive:
            archive_names = set(archive.namelist())
            for member, global_name in CORE_GLOBALS.items():
                try:
                    parsed = parse_lua_bytes(archive.read(member))
                    value = parsed.document.get(global_name)
                    if value is None and isinstance(
                        parsed.document.returned,
                        LuaTable,
                    ):
                        value = parsed.document.returned
                    if not isinstance(value, LuaTable):
                        errors[member] = "missing_global_table"
                    else:
                        tables[member] = value
                except KeyError:
                    errors[member] = "missing"
                except (OSError, RuntimeError, LuaDataError) as error:
                    errors[member] = type(error).__name__
            try:
                theatre_member = archive.read("theatre").decode("utf-8-sig")
            except (KeyError, UnicodeDecodeError):
                theatre_member = None
    except (OSError, RuntimeError, zipfile.BadZipFile):
        errors["archive"] = "bad_zip"
    return tables, errors, archive_names, theatre_member


def _validate_flat_string_table(table: LuaTable, name: str) -> None:
    for field in table.fields:
        if not isinstance(field.key, str) or not isinstance(field.value, str):
            raise BuildSpecError(f"{name} must map strings directly to strings")


def _validate_warehouses_table(table: LuaTable) -> None:
    for field_name in ("airports", "warehouses"):
        if not isinstance(table.get(field_name), LuaTable):
            raise BuildSpecError(f"warehouses.{field_name} must encode a Lua table")


def _quality_profile(value: Any) -> str:
    if value is None:
        return "technical_fixture"
    if not isinstance(value, dict) or set(value) != {"profile"}:
        raise BuildSpecError("quality must contain exactly profile")
    profile = value["profile"]
    if profile not in QUALITY_PROFILES:
        raise BuildSpecError(
            f"quality.profile must be one of {sorted(QUALITY_PROFILES)}"
        )
    return profile


def _validate_complete_spec(
    decoded: dict[str, Any],
    *,
    tables: dict[str, LuaTable],
    expectations: dict[str, Any],
    provenance: dict[str, Any],
    seed: str | int | None,
) -> None:
    if seed is None:
        raise BuildSpecError("complete_scenario requires a deterministic seed")
    if not provenance:
        raise BuildSpecError("complete_scenario requires nonempty provenance")
    if any(
        not isinstance(key, str) or not key or value is None or value == ""
        for key, value in provenance.items()
    ):
        raise BuildSpecError(
            "complete_scenario provenance keys and values must be nonempty"
        )
    if not expectations:
        raise BuildSpecError("complete_scenario requires a nonempty expect contract")
    roles = expectations.get("roles")
    if not isinstance(roles, list) or not roles:
        raise BuildSpecError(
            "complete_scenario requires a nonempty expect.roles manifest"
        )
    logic = decoded.get("logic")
    if not isinstance(logic, dict):
        raise BuildSpecError(
            "complete_scenario requires the finite logic compiler input"
        )
    rules = logic.get("trigger_rules")
    goals = logic.get("goals")
    if not isinstance(rules, list) or len(rules) < 2:
        raise BuildSpecError(
            "complete_scenario requires at least two trigger checkpoints"
        )
    if not isinstance(goals, list):
        raise BuildSpecError("complete_scenario logic.goals must be an array")
    scores = [
        goal.get("score")
        for goal in goals
        if isinstance(goal, dict) and _is_number(goal.get("score"))
    ]
    if not any(score > 0 for score in scores) or not any(score < 0 for score in scores):
        raise BuildSpecError(
            "complete_scenario requires positive success and negative failure goals"
        )
    positive_conditions = {
        _goal_condition_signature(goal)
        for goal in goals
        if isinstance(goal, dict)
        and _is_number(goal.get("score"))
        and goal["score"] > 0
    }
    negative_conditions = {
        _goal_condition_signature(goal)
        for goal in goals
        if isinstance(goal, dict)
        and _is_number(goal.get("score"))
        and goal["score"] < 0
    }
    if positive_conditions.intersection(negative_conditions):
        raise BuildSpecError(
            "complete_scenario success and failure goals must not use "
            "identical conditions"
        )
    flag_dataflow = _logic_flag_dataflow(logic)
    if flag_dataflow["read_without_writer"]:
        raise BuildSpecError(
            "complete_scenario finite logic reads flags without any setter: "
            f"{flag_dataflow['read_without_writer']}"
        )
    _validate_terminal_outcome_dataflow(logic)

    mission = tables["mission"]
    _validate_complete_mission_core(mission)
    for optional_picture_table in (
        "pictureFileNameN",
        "pictureFileNameServer",
    ):
        if mission.has(optional_picture_table) and not isinstance(
            mission.get(optional_picture_table),
            LuaTable,
        ):
            raise BuildSpecError(
                "complete_scenario mission."
                f"{optional_picture_table} must be a table when present"
            )
    required_modules = mission.get("requiredModules")
    if not isinstance(required_modules, LuaTable):
        raise BuildSpecError(
            "complete_scenario mission.requiredModules must be a table; "
            "use an empty table unless exact evidence requires entries"
        )
    for field in required_modules.fields:
        if (
            not isinstance(field.key, str)
            or not isinstance(field.value, str)
            or field.key != field.value
        ):
            raise BuildSpecError(
                "mission.requiredModules entries must map an exact plugin ID "
                "string to the same string"
            )

    _validate_complete_options(tables["options"])
    _validate_complete_warehouses(
        mission,
        tables["warehouses"],
    )


def _goal_condition_signature(
    goal: dict[str, Any],
) -> frozenset[tuple[str, Any]]:
    conditions = goal.get("conditions")
    if not isinstance(conditions, list):
        return frozenset()
    return frozenset(_semantic_logic_value(condition) for condition in conditions)


def _semantic_logic_value(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return ("boolean", value)
    if _is_number(value):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null", None)
    if isinstance(value, list):
        return (
            "array",
            tuple(_semantic_logic_value(item) for item in value),
        )
    if isinstance(value, dict):
        return (
            "object",
            tuple(
                sorted(
                    (
                        str(key),
                        _semantic_logic_value(item),
                    )
                    for key, item in value.items()
                )
            ),
        )
    return ("unsupported", type(value).__name__)


def _logic_flag_dataflow(logic: dict[str, Any]) -> dict[str, Any]:
    written: set[int] = set()
    read: set[int] = set()
    rules = logic.get("trigger_rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            actions = rule.get("actions")
            if isinstance(actions, list):
                for action in actions:
                    if (
                        isinstance(action, dict)
                        and action.get("predicate")
                        in {"a_set_flag", "a_set_flag_value"}
                        and _is_integer(action.get("flag"))
                    ):
                        written.add(action["flag"])
            _collect_logic_flag_reads(rule.get("conditions"), read)
    goals = logic.get("goals")
    if isinstance(goals, list):
        for goal in goals:
            if isinstance(goal, dict):
                _collect_logic_flag_reads(goal.get("conditions"), read)
    return {
        "written_flags": sorted(written),
        "read_flags": sorted(read),
        "read_without_writer": sorted(read - written),
        "scope": "finite_vocabulary_writer_coverage_only",
        "temporal_reachability_proved": False,
    }


def _logic_terminal_outcome_dataflow(
    logic: dict[str, Any],
) -> dict[str, Any]:
    """Conservatively check flag-backed positive/negative mission outcomes."""

    goals = logic.get("goals")
    positive_flags: set[int] = set()
    negative_flags: set[int] = set()
    positive_goal_indexes: list[int] = []
    negative_goal_indexes: list[int] = []
    unbacked_positive_goals: list[int] = []
    unbacked_negative_goals: list[int] = []
    if isinstance(goals, list):
        for goal_index, goal in enumerate(goals, start=1):
            if not isinstance(goal, dict) or not _is_number(goal.get("score")):
                continue
            target = (
                positive_flags
                if goal["score"] > 0
                else negative_flags
                if goal["score"] < 0
                else None
            )
            if target is None:
                continue
            (
                positive_goal_indexes if goal["score"] > 0 else negative_goal_indexes
            ).append(goal_index)
            conditions = goal.get("conditions")
            if not isinstance(conditions, list):
                continue
            goal_flags = {
                condition["flag"]
                for condition in conditions
                if (
                    isinstance(condition, dict)
                    and condition.get("predicate") == "c_flag_is_true"
                    and _is_integer(condition.get("flag"))
                )
            }
            target.update(goal_flags)
            if not goal_flags:
                (
                    unbacked_positive_goals
                    if goal["score"] > 0
                    else unbacked_negative_goals
                ).append(goal_index)

    terminal_flags = positive_flags | negative_flags
    shared_flags = positive_flags & negative_flags
    writers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    startup_terminal_writers: list[dict[str, Any]] = []
    unsupported_terminal_writes: list[dict[str, Any]] = []
    rules = logic.get("trigger_rules")
    if isinstance(rules, list):
        for index, rule in enumerate(rules, start=1):
            if not isinstance(rule, dict):
                continue
            conditions = rule.get("conditions")
            condition_values = conditions if isinstance(conditions, list) else ()
            false_guards = {
                condition["flag"]
                for condition in condition_values
                if (
                    isinstance(condition, dict)
                    and condition.get("predicate") == "c_flag_is_false"
                    and _is_integer(condition.get("flag"))
                )
            }
            actions = rule.get("actions")
            if not isinstance(actions, list):
                continue
            for action_index, action in enumerate(actions, start=1):
                if not isinstance(action, dict):
                    continue
                predicate = action.get("predicate")
                flag = action.get("flag")
                if (
                    predicate not in {"a_set_flag", "a_set_flag_value"}
                    or not _is_integer(flag)
                    or flag not in terminal_flags
                ):
                    continue
                writes_true = predicate == "a_set_flag" or (
                    predicate == "a_set_flag_value" and action.get("value") == 1
                )
                write_reference = {
                    "flag": flag,
                    "rule_index": index,
                    "action_index": action_index,
                    "kind": rule.get("kind"),
                    "predicate": predicate,
                }
                if not writes_true:
                    if predicate == "a_set_flag_value":
                        write_reference["value"] = action.get("value")
                    unsupported_terminal_writes.append(write_reference)
                    continue
                if rule.get("kind") == "start":
                    startup_terminal_writers.append(write_reference)
                opposite = negative_flags if flag in positive_flags else positive_flags
                writers[flag].append(
                    {
                        **write_reference,
                        "false_guards": sorted(false_guards),
                        "missing_opposite_false_guards": sorted(
                            opposite - false_guards
                        ),
                    }
                )

    missing_writer_flags = sorted(flag for flag in terminal_flags if not writers[flag])
    missing_success_guards = [
        {
            "flag": flag,
            "rule_index": writer["rule_index"],
            "missing_flags": writer["missing_opposite_false_guards"],
        }
        for flag in sorted(positive_flags)
        for writer in writers[flag]
        if writer["missing_opposite_false_guards"]
    ]
    missing_failure_guards = [
        {
            "flag": flag,
            "rule_index": writer["rule_index"],
            "missing_flags": writer["missing_opposite_false_guards"],
        }
        for flag in sorted(negative_flags)
        for writer in writers[flag]
        if writer["missing_opposite_false_guards"]
    ]
    success_writer_indexes = [
        writer["rule_index"] for flag in positive_flags for writer in writers[flag]
    ]
    failure_writer_indexes = [
        writer["rule_index"] for flag in negative_flags for writer in writers[flag]
    ]
    applicable = bool(positive_goal_indexes and negative_goal_indexes)
    failure_writers_precede_success = (
        min(success_writer_indexes) > max(failure_writer_indexes)
        if (applicable and success_writer_indexes and failure_writer_indexes)
        else None
    )
    return {
        "applicable": applicable,
        "positive_goal_flags": sorted(positive_flags),
        "negative_goal_flags": sorted(negative_flags),
        "positive_goal_indexes": positive_goal_indexes,
        "negative_goal_indexes": negative_goal_indexes,
        "unbacked_positive_goal_indexes": unbacked_positive_goals,
        "unbacked_negative_goal_indexes": unbacked_negative_goals,
        "shared_positive_negative_flags": sorted(shared_flags),
        "missing_true_writer_flags": missing_writer_flags,
        "missing_success_false_guards": missing_success_guards,
        "missing_failure_false_guards": missing_failure_guards,
        "startup_terminal_writers": startup_terminal_writers,
        "unsupported_terminal_writes": unsupported_terminal_writes,
        "failure_writers_precede_success": failure_writers_precede_success,
        "guard_order_contract_passed": bool(
            applicable
            and not unbacked_positive_goals
            and not unbacked_negative_goals
            and not shared_flags
            and not missing_writer_flags
            and not missing_success_guards
            and not missing_failure_guards
            and not startup_terminal_writers
            and not unsupported_terminal_writes
            and failure_writers_precede_success
        ),
        "runtime_mutual_exclusion_proved": False,
        "temporal_reachability_proved": False,
        "scope": (
            "positive/negative goals backed by c_flag_is_true and finite "
            "true-setting actions only"
        ),
    }


def _validate_terminal_outcome_dataflow(logic: dict[str, Any]) -> None:
    outcome = _logic_terminal_outcome_dataflow(logic)
    if not outcome["applicable"]:
        return
    unbacked_goals = {
        "positive": outcome["unbacked_positive_goal_indexes"],
        "negative": outcome["unbacked_negative_goal_indexes"],
    }
    if any(unbacked_goals.values()):
        raise BuildSpecError(
            "complete_scenario terminal goals must each include a "
            f"c_flag_is_true condition: {unbacked_goals}"
        )
    if outcome["shared_positive_negative_flags"]:
        raise BuildSpecError(
            "complete_scenario positive and negative terminal goals must "
            "use distinct flags: "
            f"{outcome['shared_positive_negative_flags']}"
        )
    if outcome["missing_true_writer_flags"]:
        raise BuildSpecError(
            "complete_scenario terminal goal flags require a true-setting "
            f"writer: {outcome['missing_true_writer_flags']}"
        )
    if outcome["missing_success_false_guards"]:
        raise BuildSpecError(
            "complete_scenario success writers must guard every failure "
            "flag with c_flag_is_false: "
            f"{outcome['missing_success_false_guards']}"
        )
    if outcome["missing_failure_false_guards"]:
        raise BuildSpecError(
            "complete_scenario failure writers must guard every success "
            "flag with c_flag_is_false: "
            f"{outcome['missing_failure_false_guards']}"
        )
    if outcome["startup_terminal_writers"]:
        raise BuildSpecError(
            "complete_scenario terminal flags must not be written by start "
            "rules because funcStartup is a separate execution phase: "
            f"{outcome['startup_terminal_writers']}"
        )
    if outcome["unsupported_terminal_writes"]:
        raise BuildSpecError(
            "complete_scenario terminal flags may only be written true with "
            "a_set_flag or a_set_flag_value value 1; resets and other values "
            f"are forbidden: {outcome['unsupported_terminal_writes']}"
        )
    if outcome["failure_writers_precede_success"] is not True:
        raise BuildSpecError(
            "complete_scenario failure writers must precede success writers "
            "to resolve same-pass terminal outcomes conservatively"
        )


def _collect_logic_flag_reads(value: Any, target: set[int]) -> None:
    if not isinstance(value, list):
        return
    for condition in value:
        if (
            isinstance(condition, dict)
            and condition.get("predicate")
            in {"c_flag_equals", "c_flag_is_false", "c_flag_is_true"}
            and _is_integer(condition.get("flag"))
        ):
            target.add(condition["flag"])


def _validate_complete_mission_core(mission: LuaTable) -> None:
    facts = collect_mission_facts(mission)
    counters = facts["counters"]
    if sum(counters["groups"].values()) < 1:
        raise BuildSpecError(
            "complete_scenario requires at least one actual mission group"
        )
    if sum(counters["units"].values()) < 1:
        raise BuildSpecError(
            "complete_scenario requires at least one actual mission unit"
        )
    if sum(counters["human_slots"].values()) < 1:
        raise BuildSpecError(
            "complete_scenario requires at least one Player or Client unit"
        )

    date = mission.get("date")
    if not isinstance(date, LuaTable):
        raise BuildSpecError("complete_scenario mission.date must be a table")
    date_parts = {name: date.get(name) for name in ("Year", "Month", "Day")}
    if any(not _is_integer(value) for value in date_parts.values()):
        raise BuildSpecError(
            "complete_scenario mission.date must contain integer Year, Month, and Day"
        )
    try:
        calendar_date(
            date_parts["Year"],
            date_parts["Month"],
            date_parts["Day"],
        )
    except ValueError as error:
        raise BuildSpecError(
            "complete_scenario mission.date is not a valid calendar date"
        ) from error

    start_time = mission.get("start_time")
    if not _is_number(start_time) or start_time < 0 or start_time >= 24 * 60 * 60:
        raise BuildSpecError(
            "complete_scenario mission.start_time must be a number from "
            "0 (inclusive) to 86400 (exclusive)"
        )

    weather = mission.get("weather")
    if not isinstance(weather, LuaTable):
        raise BuildSpecError("complete_scenario mission.weather must be a table")
    atmosphere_type = weather.get("atmosphere_type")
    if not _is_integer(atmosphere_type) or atmosphere_type not in {0, 1}:
        raise BuildSpecError(
            "complete_scenario mission.weather.atmosphere_type must be 0 or 1"
        )
    clouds = _complete_subtable(
        weather,
        "clouds",
        path="mission.weather",
        required={"base", "density", "thickness"},
    )
    for field_name in ("base", "thickness"):
        _require_nonnegative_number(
            clouds,
            field_name,
            path="mission.weather.clouds",
        )
    density = clouds.get("density")
    if not _is_integer(density) or density < 0 or density > 10:
        raise BuildSpecError(
            "complete_scenario mission.weather.clouds.density must be "
            "an integer from 0 to 10"
        )

    wind = _complete_subtable(
        weather,
        "wind",
        path="mission.weather",
        required={"atGround", "at2000", "at8000"},
    )
    for level in ("atGround", "at2000", "at8000"):
        layer = _complete_subtable(
            wind,
            level,
            path="mission.weather.wind",
            required={"dir", "speed"},
        )
        direction = layer.get("dir")
        if not _is_number(direction) or direction < 0 or direction > 360:
            raise BuildSpecError(
                "complete_scenario mission.weather.wind."
                f"{level}.dir must be a number from 0 to 360"
            )
        _require_nonnegative_number(
            layer,
            "speed",
            path=f"mission.weather.wind.{level}",
        )


def _validate_complete_options(options: LuaTable) -> None:
    vr = _complete_subtable(
        options,
        "VR",
        path="options",
        required={
            "bloom",
            "box_mouse_cursor",
            "enable",
            "mirror_crop",
            "mirror_source",
            "mirror_use_DCS_resolution",
            "msaaMaskSize",
            "pixel_density",
            "use_mouse",
        },
    )
    difficulty = _complete_subtable(
        options,
        "difficulty",
        path="options",
        required={
            "birds",
            "easyCommunication",
            "easyFlight",
            "externalViews",
            "fuel",
            "geffect",
            "immortal",
            "labels",
            "map",
            "optionsView",
            "padlock",
            "permitCrash",
            "radio",
            "spectatorExternalViews",
            "tips",
            "units",
            "userMarks",
            "weapons",
        },
    )
    graphics = _complete_subtable(
        options,
        "graphics",
        path="options",
        required={
            "ScreenshotExt",
            "clouds",
            "defaultFOV",
            "fullScreen",
            "multiMonitorSetup",
            "outputGamma",
            "preloadRadius",
            "shadows",
            "sync",
            "terrainTextures",
            "textures",
            "visibRange",
            "water",
        },
    )
    miscellaneous = _complete_subtable(
        options,
        "miscellaneous",
        path="options",
        required={
            "Coordinate_Display",
            "F2_view_effects",
            "accidental_failures",
            "f10_awacs",
            "force_feedback_enabled",
            "headmove",
        },
    )
    if not isinstance(options.get("plugins"), LuaTable):
        raise BuildSpecError("complete_scenario options.plugins must be a table")
    sound = _complete_subtable(
        options,
        "sound",
        path="options",
        required={
            "cockpit",
            "gui",
            "headphones",
            "hp_output",
            "main_layout",
            "main_output",
            "microphone_use",
            "music",
            "play_audio_while_minimized",
            "radioSpeech",
            "subtitles",
            "switches",
            "voiceChatInSensitivity",
            "voiceChatInVolume",
            "voice_chat",
            "voice_chat_input",
            "voice_chat_output",
            "volume",
            "world",
        },
    )
    views = _complete_subtable(
        options,
        "views",
        path="options",
        required={"cockpit"},
    )
    cockpit_views = _complete_subtable(
        views,
        "cockpit",
        path="options.views",
        required={
            "avionics",
            "avionicsMFDEveryFrame",
            "mirrors",
            "mirrorsEveryFrame",
            "mirrorsResolution",
            "mirrorsSequentialRendering",
        },
    )

    player_name = options.get("playerName")
    if not isinstance(player_name, str) or not player_name.strip():
        raise BuildSpecError("complete_scenario options.playerName must be nonempty")
    if not _is_integer(options.get("format")) or options.get("format") != 1:
        raise BuildSpecError("complete_scenario options.format must be 1")

    _require_boolean_fields(
        vr,
        (
            "bloom",
            "box_mouse_cursor",
            "enable",
            "mirror_crop",
            "mirror_use_DCS_resolution",
            "use_mouse",
        ),
        path="options.VR",
    )
    _require_positive_number(vr, "pixel_density", path="options.VR")
    _require_nonnegative_number(vr, "msaaMaskSize", path="options.VR")
    _require_nonnegative_integer(vr, "mirror_source", path="options.VR")

    _require_boolean_fields(
        difficulty,
        (
            "easyCommunication",
            "easyFlight",
            "externalViews",
            "fuel",
            "immortal",
            "map",
            "padlock",
            "permitCrash",
            "radio",
            "spectatorExternalViews",
            "tips",
            "userMarks",
            "weapons",
        ),
        path="options.difficulty",
    )
    _require_nonnegative_integer(
        difficulty,
        "birds",
        path="options.difficulty",
    )
    labels = difficulty.get("labels")
    if not _is_integer(labels) or labels not in {0, 1, 2, 3, 4}:
        raise BuildSpecError(
            "complete_scenario options.difficulty.labels must be one of [0, 1, 2, 3, 4]"
        )
    _require_enum(
        difficulty,
        "geffect",
        {"none", "reduced", "realistic"},
        path="options.difficulty",
    )
    _require_nonempty_string(
        difficulty,
        "optionsView",
        path="options.difficulty",
    )
    _require_enum(
        difficulty,
        "units",
        {"imperial", "metric"},
        path="options.difficulty",
    )

    _require_boolean_fields(
        graphics,
        ("fullScreen", "sync"),
        path="options.graphics",
    )
    for field_name in (
        "clouds",
        "defaultFOV",
        "outputGamma",
        "preloadRadius",
        "shadows",
        "textures",
        "water",
    ):
        _require_nonnegative_number(
            graphics,
            field_name,
            path="options.graphics",
        )
    _require_enum(
        graphics,
        "ScreenshotExt",
        {"bmp", "jpg", "png"},
        path="options.graphics",
    )
    _require_nonempty_string(
        graphics,
        "multiMonitorSetup",
        path="options.graphics",
    )
    _require_enum(
        graphics,
        "terrainTextures",
        {"max", "min"},
        path="options.graphics",
    )
    _require_enum(
        graphics,
        "visibRange",
        {"Extreme", "High", "Low", "Medium", "Ultra"},
        path="options.graphics",
    )

    _require_boolean_fields(
        miscellaneous,
        (
            "accidental_failures",
            "f10_awacs",
            "force_feedback_enabled",
            "headmove",
        ),
        path="options.miscellaneous",
    )
    _require_nonnegative_integer(
        miscellaneous,
        "F2_view_effects",
        path="options.miscellaneous",
    )
    _require_nonempty_string(
        miscellaneous,
        "Coordinate_Display",
        path="options.miscellaneous",
    )

    for field_name in (
        "hp_output",
        "main_output",
        "main_layout",
        "voice_chat_output",
        "voice_chat_input",
    ):
        value = sound.get(field_name)
        if value not in {None, ""}:
            raise BuildSpecError(
                "complete_scenario options must not contain local audio "
                f"device identifiers ({field_name})"
            )
    _require_boolean_fields(
        sound,
        (
            "play_audio_while_minimized",
            "radioSpeech",
            "subtitles",
            "voice_chat",
        ),
        path="options.sound",
    )
    for field_name in (
        "cockpit",
        "gui",
        "headphones",
        "music",
        "switches",
        "voiceChatInVolume",
        "volume",
        "world",
    ):
        _require_bounded_number(
            sound,
            field_name,
            minimum=0,
            maximum=100,
            path="options.sound",
        )
    _require_bounded_number(
        sound,
        "voiceChatInSensitivity",
        minimum=-100,
        maximum=100,
        path="options.sound",
    )
    _require_nonnegative_integer(
        sound,
        "microphone_use",
        path="options.sound",
    )

    _require_boolean_fields(
        cockpit_views,
        (
            "avionicsMFDEveryFrame",
            "mirrors",
            "mirrorsEveryFrame",
            "mirrorsSequentialRendering",
        ),
        path="options.views.cockpit",
    )
    _require_nonnegative_number(
        cockpit_views,
        "avionics",
        path="options.views.cockpit",
    )
    _require_nonnegative_number(
        cockpit_views,
        "mirrorsResolution",
        path="options.views.cockpit",
    )


def _validate_complete_warehouses(
    mission: LuaTable,
    warehouses: LuaTable,
) -> None:
    airports = table(warehouses.get("airports"))
    used_airdromes: set[int | float] = set()
    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country in numeric_tables(side.get("country")):
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group in numeric_tables(category_table.get("group")):
                    for point in numeric_tables(
                        table(group.get("route")).get("points")
                    ):
                        identifier = point.get("airdromeId")
                        if _is_number(identifier):
                            used_airdromes.add(identifier)
    missing = sorted(
        identifier for identifier in used_airdromes if not airports.has(identifier)
    )
    if missing:
        raise BuildSpecError(
            "complete_scenario warehouses.airports is missing used "
            f"airdrome IDs: {missing}"
        )

    for registry_name in ("airports", "warehouses"):
        registry = table(warehouses.get(registry_name))
        identifiers: set[int | float] = set()
        for field in registry.fields:
            identifier = field.key
            if not _is_number(identifier) or identifier < 0:
                raise BuildSpecError(
                    "complete_scenario warehouses."
                    f"{registry_name} keys must be nonnegative numbers"
                )
            if identifier in identifiers:
                raise BuildSpecError(
                    "complete_scenario warehouses."
                    f"{registry_name} contains duplicate key {identifier}"
                )
            identifiers.add(identifier)
            if not isinstance(field.value, LuaTable):
                raise BuildSpecError(
                    "complete_scenario warehouses."
                    f"{registry_name}[{identifier}] must be a table"
                )
            _validate_complete_warehouse_entry(
                field.value,
                path=f"warehouses.{registry_name}[{identifier}]",
            )


def _validate_complete_warehouse_entry(
    entry: LuaTable,
    *,
    path: str,
) -> None:
    required_fields = {
        "OperatingLevel_Air",
        "OperatingLevel_Eqp",
        "OperatingLevel_Fuel",
        "aircrafts",
        "allowHotStart",
        "coalition",
        "diesel",
        "dynamicCargo",
        "dynamicSpawn",
        "gasoline",
        "jet_fuel",
        "methanol_mixture",
        "periodicity",
        "size",
        "speed",
        "suppliers",
        "unlimitedAircrafts",
        "unlimitedFuel",
        "unlimitedMunitions",
        "weapons",
    }
    missing = sorted(name for name in required_fields if not entry.has(name))
    if missing:
        raise BuildSpecError(f"complete_scenario {path} is missing fields: {missing}")

    aircrafts = _complete_subtable(
        entry,
        "aircrafts",
        path=path,
        required={"helicopters", "planes"},
    )
    for field_name in ("helicopters", "planes"):
        if not isinstance(aircrafts.get(field_name), LuaTable):
            raise BuildSpecError(
                f"complete_scenario {path}.aircrafts.{field_name} must be a table"
            )
    for field_name in ("suppliers", "weapons"):
        if not isinstance(entry.get(field_name), LuaTable):
            raise BuildSpecError(
                f"complete_scenario {path}.{field_name} must be a table"
            )

    for field_name in (
        "diesel",
        "gasoline",
        "jet_fuel",
        "methanol_mixture",
    ):
        fuel = _complete_subtable(
            entry,
            field_name,
            path=path,
            required={"InitFuel"},
        )
        _require_nonnegative_number(
            fuel,
            "InitFuel",
            path=f"{path}.{field_name}",
        )
    _require_boolean_fields(
        entry,
        (
            "allowHotStart",
            "dynamicCargo",
            "dynamicSpawn",
            "unlimitedAircrafts",
            "unlimitedFuel",
            "unlimitedMunitions",
        ),
        path=path,
    )
    for field_name in (
        "OperatingLevel_Air",
        "OperatingLevel_Eqp",
        "OperatingLevel_Fuel",
    ):
        _require_nonnegative_number(entry, field_name, path=path)
    for field_name in ("periodicity", "size", "speed"):
        _require_positive_number(entry, field_name, path=path)
    _require_enum(
        entry,
        "coalition",
        set(WAREHOUSE_COALITIONS),
        path=path,
    )


def _complete_subtable(
    parent: LuaTable,
    field_name: str,
    *,
    path: str,
    required: set[str],
) -> LuaTable:
    value = parent.get(field_name)
    field_path = f"{path}.{field_name}"
    if not isinstance(value, LuaTable):
        raise BuildSpecError(f"complete_scenario {field_path} must be a table")
    missing = sorted(name for name in required if not value.has(name))
    if missing:
        raise BuildSpecError(
            f"complete_scenario {field_path} is missing fields: {missing}"
        )
    return value


def _require_boolean_fields(
    table_value: LuaTable,
    field_names: tuple[str, ...],
    *,
    path: str,
) -> None:
    for field_name in field_names:
        if not isinstance(table_value.get(field_name), bool):
            raise BuildSpecError(
                f"complete_scenario {path}.{field_name} must be a boolean"
            )


def _require_bounded_number(
    table_value: LuaTable,
    field_name: str,
    *,
    minimum: int | float,
    maximum: int | float,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if not _is_number(value) or value < minimum or value > maximum:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be a number "
            f"from {minimum} to {maximum}"
        )


def _require_nonnegative_number(
    table_value: LuaTable,
    field_name: str,
    *,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if not _is_number(value) or value < 0:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be a nonnegative number"
        )


def _require_positive_number(
    table_value: LuaTable,
    field_name: str,
    *,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if not _is_number(value) or value <= 0:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be a positive number"
        )


def _require_nonnegative_integer(
    table_value: LuaTable,
    field_name: str,
    *,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if not _is_integer(value) or value < 0:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be a nonnegative integer"
        )


def _require_nonempty_string(
    table_value: LuaTable,
    field_name: str,
    *,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be a "
            "nonempty string without NUL"
        )


def _require_enum(
    table_value: LuaTable,
    field_name: str,
    allowed: set[str],
    *,
    path: str,
) -> None:
    value = table_value.get(field_name)
    if value not in allowed:
        raise BuildSpecError(
            f"complete_scenario {path}.{field_name} must be one of {sorted(allowed)}"
        )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildSpecError(f"duplicate JSON key: {_bounded_json_key(key)}")
        result[key] = value
    return result


def _bounded_json_key(value: str) -> str:
    maximum_characters = 128
    if len(value) <= maximum_characters:
        return repr(value)
    clipped = value[: maximum_characters - 1] + "…"
    return f"{clipped!r} (truncated from {len(value)} characters)"


def _preflight_json_depth(raw_bytes: bytes) -> None:
    """Reject excessive structural depth without recursively parsing JSON."""

    depth = 0
    in_string = False
    escaped = False
    for value in raw_bytes:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:  # Backslash.
                escaped = True
            elif value == 0x22:  # Double quote.
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in (0x7B, 0x5B):  # Opening brace or bracket.
            depth += 1
            if depth > MAX_BUILD_SPEC_JSON_DEPTH:
                raise BuildSpecError(
                    "build specification exceeds the JSON nesting depth "
                    f"limit of {MAX_BUILD_SPEC_JSON_DEPTH}"
                )
        elif value in (0x7D, 0x5D) and depth:  # Closing brace or bracket.
            depth -= 1


def _reject_json_constant(value: str) -> None:
    del value
    raise BuildSpecError("non-finite JSON number is forbidden")


def _parse_finite_json_float(value: str) -> float:
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as error:
        raise BuildSpecError("non-finite JSON number is forbidden") from error
    if not math.isfinite(parsed):
        raise BuildSpecError("non-finite JSON number is forbidden")
    return parsed


def _parse_finite_json_int(value: str) -> int:
    try:
        parsed = int(value)
        finite_value = float(parsed)
    except (OverflowError, ValueError) as error:
        raise BuildSpecError("JSON integer exceeds the finite numeric range") from error
    if not math.isfinite(finite_value):
        raise BuildSpecError("JSON integer exceeds the finite numeric range")
    return parsed


def _sha256_stream(stream: BinaryIO) -> str:
    stream.seek(0)
    return _hash_stream(stream)


def _hash_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _sanitize_provenance(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        redacted_key_index = 0
        for key, item in value.items():
            output_key = key
            if isinstance(key, str) and _contains_local_path(key):
                while True:
                    redacted_key_index += 1
                    output_key = f"{_LOCAL_PATH_REDACTION}-key-{redacted_key_index}"
                    if output_key not in sanitized:
                        break
            elif output_key in sanitized:
                while True:
                    redacted_key_index += 1
                    output_key = f"{_LOCAL_PATH_REDACTION}-key-{redacted_key_index}"
                    if output_key not in sanitized:
                        break
            sanitized[output_key] = _sanitize_provenance(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_provenance(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_provenance(item) for item in value]
    if isinstance(value, str) and _contains_local_path(value):
        return _LOCAL_PATH_REDACTION
    return value


def _contains_local_path(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False
    if _FILE_URI.search(candidate):
        return True
    if (
        PurePosixPath(candidate).is_absolute()
        or PureWindowsPath(candidate).is_absolute()
        or _WINDOWS_DRIVE_PATH.search(candidate)
        or _BACKSLASH_UNC_PATH.search(candidate)
    ):
        return True

    masked = list(candidate)
    for match in _URI_WITH_PATH.finditer(candidate):
        scheme = match.group("scheme").casefold()
        authority = match.group("authority")
        try:
            parsed = urlsplit(match.group(0))
        except ValueError:
            return True
        hostname = parsed.hostname or authority.rsplit("@", 1)[-1]
        if scheme == "file" or _is_private_hostname(hostname):
            return True
        for index in range(match.start(), match.end()):
            masked[index] = " "

    masked_candidate = "".join(masked)
    if _FORWARD_UNC_PATH.search(masked_candidate):
        return True

    scp_spans: list[tuple[int, int]] = []
    for match in _SCP_ABSOLUTE_PATH.finditer(masked_candidate):
        host = match.group("host").strip("[]")
        if _is_private_hostname(host):
            return True
        scp_spans.append((match.start(), match.end()))

    if scp_spans:
        masked = list(masked_candidate)
        for start, end in scp_spans:
            for index in range(start, end):
                masked[index] = " "
        masked_candidate = "".join(masked)

    return bool(
        _EMBEDDED_POSIX_ABSOLUTE_PATH.search(masked_candidate)
        or _EMBEDDED_WINDOWS_ROOTED_PATH.search(masked_candidate)
    )


def _is_private_hostname(value: str) -> bool:
    hostname = value.casefold().strip().strip("[]").rstrip(".")
    if not hostname:
        return True
    if hostname == "localhost" or hostname.endswith(
        (".localhost", ".local", ".lan", ".internal")
    ):
        return True
    try:
        address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        return "." not in hostname
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
