from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class RootKind(StrEnum):
    DCS_INSTALL = "dcs_install"
    SAVED_GAMES = "saved_games"
    OFFICIAL_MIRROR = "official_mirror"
    UPSTREAM = "upstream"
    OTHER = "other"


@dataclass(frozen=True)
class EvidenceRoot:
    name: str
    kind: RootKind
    path: Path
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("evidence root name must not be empty")


@dataclass(frozen=True)
class SurveyConfig:
    roots: tuple[EvidenceRoot, ...]
    verify_crc: bool = True
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.roots:
            raise ValueError("at least one evidence root is required")
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        names = [root.name for root in self.roots]
        if len(names) != len(set(names)):
            raise ValueError("evidence root names must be unique")


@dataclass(frozen=True)
class Diagnostic:
    code: str
    layer: str = "archive"
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "layer": self.layer,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ArchiveInspection:
    valid_zip: bool
    safe: bool
    member_count: int
    compressed_bytes: int
    uncompressed_bytes: int
    crc_status: str
    present_core_members: tuple[str, ...]
    duplicate_member_extras: int
    unsafe_path_entries: int
    encrypted_entries: int
    diagnostics: tuple[Diagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_zip": self.valid_zip,
            "safe": self.safe,
            "member_count": self.member_count,
            "compressed_bytes": self.compressed_bytes,
            "uncompressed_bytes": self.uncompressed_bytes,
            "crc_status": self.crc_status,
            "present_core_members": list(self.present_core_members),
            "duplicate_member_extras": self.duplicate_member_extras,
            "unsafe_path_entries": self.unsafe_path_entries,
            "encrypted_entries": self.encrypted_entries,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True)
class FileObservation:
    root_name: str
    relative_path: str
    extension: str
    size_bytes: int
    sha256: str
    archive: ArchiveInspection | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "root": self.root_name,
            "relative_path": self.relative_path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }
        if self.archive is not None:
            result["archive"] = self.archive.to_dict()
        return result


@dataclass
class RootObservation:
    source: EvidenceRoot
    exists: bool
    files: list[FileObservation] = field(default_factory=list)
    errors: list[Diagnostic] = field(default_factory=list)
    root_unique_content: int = 0
    net_new_content: int = 0

    def to_dict(self) -> dict[str, Any]:
        extensions = Counter(item.extension for item in self.files)
        archives = [item.archive for item in self.files if item.archive is not None]
        diagnostic_counts = Counter(
            diagnostic.code
            for archive in archives
            for diagnostic in archive.diagnostics
        )
        return {
            "name": self.source.name,
            "kind": self.source.kind.value,
            "version": self.source.version,
            "exists": self.exists,
            "errors": len(self.errors),
            "file_instances": len(self.files),
            "miz_instances": extensions[".miz"],
            "cmp_instances": extensions[".cmp"],
            "root_unique_content": self.root_unique_content,
            "net_new_content": self.net_new_content,
            "archive": {
                "valid_zip": sum(archive.valid_zip for archive in archives),
                "invalid_zip": sum(not archive.valid_zip for archive in archives),
                "safe": sum(archive.safe for archive in archives),
                "unsafe": sum(not archive.safe for archive in archives),
                "crc_passed": sum(
                    archive.crc_status == "passed" for archive in archives
                ),
                "crc_failed": sum(
                    archive.crc_status == "failed" for archive in archives
                ),
                "crc_skipped": sum(
                    archive.crc_status == "skipped" for archive in archives
                ),
                "duplicate_member_extras": sum(
                    archive.duplicate_member_extras for archive in archives
                ),
                "unsafe_path_entries": sum(
                    archive.unsafe_path_entries for archive in archives
                ),
                "encrypted_entries": sum(
                    archive.encrypted_entries for archive in archives
                ),
                "diagnostics": dict(sorted(diagnostic_counts.items())),
            },
        }


@dataclass(frozen=True)
class SurveyResult:
    collected_at: datetime
    roots: tuple[RootObservation, ...]

    @property
    def files(self) -> tuple[FileObservation, ...]:
        return tuple(item for root in self.roots for item in root.files)

    def to_dict(self, *, include_file_details: bool = False) -> dict[str, Any]:
        files = self.files
        unique_content = {item.sha256 for item in files}
        result: dict[str, Any] = {
            "schema": "dcsmizzer.corpus-survey/v1",
            "collected_at": _format_utc(self.collected_at),
            "totals": {
                "file_instances": len(files),
                "unique_content": len(unique_content),
                "miz_instances": sum(item.extension == ".miz" for item in files),
                "cmp_instances": sum(item.extension == ".cmp" for item in files),
            },
            "roots": [root.to_dict() for root in self.roots],
            "overlaps": _overlaps(self.roots),
        }
        if include_file_details:
            result["files"] = [item.to_dict() for item in files]
        return result

    def has_errors(self) -> bool:
        if any(root.errors for root in self.roots):
            return True
        return any(
            archive is not None and not archive.safe
            for item in self.files
            if (archive := item.archive) is not None
        )


def _format_utc(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _overlaps(roots: tuple[RootObservation, ...]) -> list[dict[str, Any]]:
    hashes = [{item.sha256 for item in root.files} for root in roots]
    result: list[dict[str, Any]] = []
    for left_index, left in enumerate(roots):
        for right_index in range(left_index + 1, len(roots)):
            shared = len(hashes[left_index] & hashes[right_index])
            if shared:
                result.append(
                    {
                        "left": left.source.name,
                        "right": roots[right_index].source.name,
                        "shared_content": shared,
                    }
                )
    return result
