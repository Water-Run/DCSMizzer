from __future__ import annotations

import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

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
    max_members: int = 20_000
    max_member_uncompressed: int = 1 * 1024 * 1024 * 1024
    max_total_uncompressed: int = 8 * 1024 * 1024 * 1024
    max_compression_ratio: float = 2_000.0

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
    path: Path,
    *,
    policy: ArchivePolicy | None = None,
    verify_crc: bool = True,
) -> ArchiveInspection:
    selected_policy = policy or ArchivePolicy()
    try:
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
                            severity="warning",
                        )
                    )

            unsafe_paths = 0
            encrypted_entries = 0
            compressed_bytes = 0
            uncompressed_bytes = 0

            if len(infos) > selected_policy.max_members:
                diagnostics.append(Diagnostic("member_count_limit"))

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
                if (
                    info.file_size > 0
                    and info.compress_size > 0
                    and info.file_size / info.compress_size
                    > selected_policy.max_compression_ratio
                ):
                    diagnostics.append(Diagnostic("compression_ratio_limit"))

            if uncompressed_bytes > selected_policy.max_total_uncompressed:
                diagnostics.append(Diagnostic("total_size_limit"))

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
                if encrypted_entries:
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
