from __future__ import annotations

import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from .model import ArchiveInspection, Diagnostic


CORE_MEMBERS: tuple[str, ...] = (
    "mission",
    "options",
    "warehouses",
    "l10n/DEFAULT/dictionary",
    "l10n/DEFAULT/mapResource",
)


@dataclass(frozen=True)
class ArchivePolicy:
    max_members: int = 4_096
    max_member_uncompressed: int = 128 * 1024 * 1024
    max_total_uncompressed: int = 512 * 1024 * 1024
    max_compression_ratio: float = 250.0

    def __post_init__(self) -> None:
        if self.max_members <= 0:
            raise ValueError("max_members must be positive")
        if self.max_member_uncompressed <= 0:
            raise ValueError("max_member_uncompressed must be positive")
        if self.max_total_uncompressed <= 0:
            raise ValueError("max_total_uncompressed must be positive")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be positive")


def inspect_miz(
    path: Path | BinaryIO,
    *,
    policy: ArchivePolicy | None = None,
    verify_crc: bool = True,
) -> ArchiveInspection:
    selected_policy = policy or ArchivePolicy()
    try:
        _rewind_stream(path)
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            diagnostics: list[Diagnostic] = []
            name_counts = Counter(names)
            duplicate_extras = sum(
                count - 1 for count in name_counts.values() if count > 1
            )
            for _name, count in sorted(name_counts.items()):
                if count > 1:
                    diagnostics.append(
                        Diagnostic(
                            "duplicate_member",
                            severity="error",
                        )
                    )

            unsafe_paths = 0
            encrypted_entries = 0
            compressed_bytes = 0
            uncompressed_bytes = 0
            policy_violation = False

            if len(infos) > selected_policy.max_members:
                diagnostics.append(Diagnostic("member_count_limit"))
                policy_violation = True

            for info in infos:
                compressed_bytes += info.compress_size
                uncompressed_bytes += info.file_size
                if _unsafe_member_path(info.filename):
                    unsafe_paths += 1
                    diagnostics.append(Diagnostic("unsafe_member_path"))
                if info.flag_bits & 0x1:
                    encrypted_entries += 1
                    diagnostics.append(Diagnostic("encrypted_member"))
                if info.file_size > selected_policy.max_member_uncompressed:
                    diagnostics.append(Diagnostic("member_size_limit"))
                    policy_violation = True
                if (
                    info.file_size > 0
                    and info.compress_size > 0
                    and info.file_size / info.compress_size
                    > selected_policy.max_compression_ratio
                ):
                    diagnostics.append(Diagnostic("compression_ratio_limit"))
                    policy_violation = True

            if uncompressed_bytes > selected_policy.max_total_uncompressed:
                diagnostics.append(Diagnostic("total_size_limit"))
                policy_violation = True

            present_core = tuple(name for name in CORE_MEMBERS if name in name_counts)
            for _missing in (name for name in CORE_MEMBERS if name not in name_counts):
                diagnostics.append(
                    Diagnostic(
                        "missing_core_member",
                        severity="warning",
                    )
                )

            crc_status = "skipped"
            if verify_crc:
                pre_crc_error = any(
                    item.severity == "error" for item in diagnostics
                )
                if policy_violation or pre_crc_error:
                    crc_status = "not_checked"
                else:
                    try:
                        bad_member = archive.testzip()
                    except (zipfile.BadZipFile, RuntimeError):
                        bad_member = "<unreadable>"
                    if bad_member is None:
                        crc_status = "passed"
                    else:
                        crc_status = "failed"
                        diagnostics.append(Diagnostic("bad_crc"))

            safe = not any(item.severity == "error" for item in diagnostics)
            return ArchiveInspection(
                valid_zip=True,
                safe=safe,
                member_count=len(infos),
                compressed_bytes=compressed_bytes,
                uncompressed_bytes=uncompressed_bytes,
                crc_status=crc_status,
                present_core_members=present_core,
                duplicate_member_extras=duplicate_extras,
                unsafe_path_entries=unsafe_paths,
                encrypted_entries=encrypted_entries,
                diagnostics=tuple(diagnostics),
            )
    except (OSError, zipfile.BadZipFile):
        return ArchiveInspection(
            valid_zip=False,
            safe=False,
            member_count=0,
            compressed_bytes=0,
            uncompressed_bytes=0,
            crc_status="not_checked",
            present_core_members=(),
            duplicate_member_extras=0,
            unsafe_path_entries=0,
            encrypted_entries=0,
            diagnostics=(Diagnostic("bad_zip"),),
        )


def _rewind_stream(path: Path | BinaryIO) -> None:
    if not isinstance(path, Path):
        path.seek(0)


def is_safe_archive_member_name(name: str) -> bool:
    """Return whether a member name is a nonempty relative POSIX path."""

    if not name or "\x00" in name or name.endswith(("/", "\\")):
        return False
    return not _unsafe_member_path(name)


def _unsafe_member_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(name)
    return (
        normalized.startswith("/")
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
    )
