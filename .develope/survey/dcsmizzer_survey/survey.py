from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .archive import inspect_miz
from .model import (
    Diagnostic,
    FileObservation,
    RootObservation,
    SurveyConfig,
    SurveyResult,
)


def survey_evidence(config: SurveyConfig) -> SurveyResult:
    roots: list[RootObservation] = []
    seen_content: set[str] = set()

    for source in config.roots:
        observation = RootObservation(source=source, exists=source.path.is_dir())
        roots.append(observation)
        if not observation.exists:
            observation.errors.append(
                Diagnostic(
                    "root_unavailable",
                    layer="discovery",
                )
            )
            continue

        for path in discover_evidence_files(source.path, observation.errors):
            try:
                digest = _sha256(path)
                relative = path.relative_to(source.path).as_posix()
                extension = path.suffix.lower()
                archive = (
                    inspect_miz(path, verify_crc=config.verify_crc)
                    if extension == ".miz"
                    else None
                )
                observation.files.append(
                    FileObservation(
                        root_name=source.name,
                        relative_path=relative,
                        extension=extension,
                        size_bytes=path.stat().st_size,
                        sha256=digest,
                        archive=archive,
                    )
                )
            except OSError:
                observation.errors.append(
                    Diagnostic(
                        "file_unreadable",
                        layer="discovery",
                    )
                )

        observation.files.sort(key=lambda item: item.relative_path.casefold())
        root_hashes = {item.sha256 for item in observation.files}
        observation.root_unique_content = len(root_hashes)
        observation.net_new_content = len(root_hashes - seen_content)
        seen_content.update(root_hashes)

    return SurveyResult(
        collected_at=config.collected_at,
        roots=tuple(roots),
    )


def discover_evidence_files(
    root: Path,
    errors: list[Diagnostic],
) -> list[Path]:
    found: list[Path] = []

    def on_error(_error: OSError) -> None:
        errors.append(
            Diagnostic(
                "directory_unreadable",
                layer="discovery",
            )
        )

    for directory, dirnames, filenames in os.walk(
        root,
        topdown=True,
        onerror=on_error,
        followlinks=False,
    ):
        dirnames.sort(key=str.casefold)
        filenames.sort(key=str.casefold)
        base = Path(directory)
        for filename in filenames:
            path = base / filename
            if path.suffix.lower() in {".miz", ".cmp"}:
                found.append(path)
    return found


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
