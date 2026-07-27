"""Fit bounded, commit-bound coordinate transforms from BriefingRoom exports.

The BriefingRoom airbase export contains both WGS84 airport centres and DCS
mission-local airport centres.  This module treats those pairs as lower-
authority, commit-bound evidence for terrains which may not be installed
locally.  It never executes upstream code and never removes a finite outlier.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .br_static import (
    _git_state,
    _resolve_unique_theatre_id,
    _validated_root,
)
from .coordinates import (
    UTM_CENTRAL_MERIDIANS,
    CoordinateSample,
    ProjectionFit,
    _checked_latlon_to_map,
    _checked_map_to_latlon,
    _fit_projection,
    _inverse_errors,
    _latlon_to_map,
    _map_to_latlon,
    _surface_distance_m,
)


_MIN_UNIQUE_SAMPLES = 5
_MIN_SCALE_FACTOR = 0.99
_MAX_SCALE_FACTOR = 1.01
_MAX_ERROR_M = 25.0
_MIN_NEXT_CANDIDATE_ABSOLUTE_GAP_M = 1.0
_MIN_NEXT_CANDIDATE_RELATIVE_GAP = 0.25
_MAX_DUPLICATE_GROUPS = 5
_MAX_DUPLICATE_RECORD_REFERENCES = 5
_MAX_AIRBASE_EXPORT_BYTES = 64 * 1024 * 1024
_MAX_THEATRE_DECLARATION_BYTES = 1024 * 1024
_MAX_PROJECT_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 128
_MAX_AIRBASE_EXPORT_RECORDS = 10_000
_MAX_TERRAIN_RECORDS = 512
_MAX_UNIQUE_SAMPLES = 256
_REPORT_CONTEXT_BUDGET_BYTES = 12 * 1024
_MAX_DIAGNOSTIC_TEXT = 128
_MAX_THEATRE_ID_TEXT = 128
_MAX_THEATRE_DISPLAY_TEXT = 256
_MAX_PROJECT_VERSION_TEXT = 128
_REGULAR_GIT_BLOB_MODES = frozenset({"100644", "100755"})
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_PROJECT_VERSION = re.compile(
    r'\bTARGETED_DCS_WORLD_VERSION\s*=\s*"(?P<version>[^"]+)"'
)


@dataclass(frozen=True)
class _ExtractedSamples:
    samples: list[CoordinateSample]
    records_in_terrain: int
    finite_coordinate_records: int
    invalid_coordinate_records: int
    duplicate_coordinate_records: int
    duplicate_groups: list[dict[str, Any]]
    duplicate_groups_total: int


@dataclass(frozen=True)
class _DecisionSource:
    relative_path: str
    payload: bytes
    git_mode: str | None
    git_blob_oid: str | None
    worktree_regular_file: bool
    parsed_from: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    @property
    def bound_to_head(self) -> bool:
        return bool(
            self.parsed_from == "git_HEAD_blob"
            and self.git_mode in _REGULAR_GIT_BLOB_MODES
            and self.git_blob_oid
            and self.worktree_regular_file
        )


def br_coordinate_report(
    br_root: Path,
    terrain: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    map_x: float | None = None,
    map_y: float | None = None,
) -> dict[str, Any]:
    """Return a validated BR airbase-centre projection and optional conversion.

    A model is usable only when the exact theatre resolves uniquely, the
    BriefingRoom checkout is clean and commit-bound, every unique finite
    coordinate tuple participates in the fit, and the full/leave-one-out
    validation gates pass.  Invalid candidates remain bounded diagnostics;
    they are never returned as a conversion model.
    """

    _validate_conversion_request(
        latitude=latitude,
        longitude=longitude,
        map_x=map_x,
        map_y=map_y,
    )
    root = _validated_root(br_root)
    upstream = _git_state(root)
    (
        airbase_source,
        theatre_sources,
        project_source,
        source_binding,
    ) = _load_bound_sources(root, upstream)
    entries = _parse_theatre_entries(theatre_sources)
    selected_theatre = _resolve_unique_theatre_id(entries, terrain)
    airbases = _parse_airbases(airbase_source)
    selected_airbases = [
        item for item in airbases if item.get("theatre") == selected_theatre
    ]
    if len(selected_airbases) > _MAX_TERRAIN_RECORDS:
        raise ValueError("BriefingRoom terrain exceeds the airbase-record limit")
    extracted = _extract_coordinate_samples(selected_airbases)
    if len(extracted.samples) > _MAX_UNIQUE_SAMPLES:
        raise ValueError("BriefingRoom terrain exceeds the coordinate-sample limit")
    fit_diagnostics = _fit_diagnostics(extracted.samples)

    failure_reasons: list[str] = []
    if not (
        upstream.get("provenance") == "commit_bound"
        and upstream.get("acknowledged") is True
    ):
        failure_reasons.append("upstream_checkout_not_clean_commit_bound")
    if source_binding["all_required_sources_bound_to_head"] is not True:
        failure_reasons.append("decision_sources_not_bound_to_head")
    if len(extracted.samples) < _MIN_UNIQUE_SAMPLES:
        failure_reasons.append("too_few_unique_finite_coordinate_samples")
    failure_reasons.extend(fit_diagnostics["failure_reasons"])
    validated = not failure_reasons

    model = (
        _model_record(fit_diagnostics["fit"])
        if validated and fit_diagnostics["fit"] is not None
        else None
    )
    envelope = _sample_envelope(extracted.samples)
    extrapolation = _extrapolation_record(
        envelope,
        latitude=latitude,
        longitude=longitude,
        map_x=map_x,
        map_y=map_y,
    )
    conversion = (
        _conversion_record(
            fit_diagnostics["fit"],
            latitude=latitude,
            longitude=longitude,
            map_x=map_x,
            map_y=map_y,
        )
        if validated and fit_diagnostics["fit"] is not None
        else None
    )

    provenance = upstream.get("provenance")
    if (
        provenance == "commit_bound"
        and upstream.get("acknowledged") is True
        and source_binding["all_required_sources_bound_to_head"] is True
    ):
        authority = "derived_commit_bound_br_airbase_export_projection"
    elif provenance == "dirty_worktree_snapshot":
        authority = "derived_dirty_br_airbase_export_projection_candidate"
    elif provenance == "commit_bound" and upstream.get("acknowledged") is True:
        authority = "derived_unbound_br_airbase_export_projection_candidate"
    elif provenance == "clean_unacknowledged_snapshot":
        authority = (
            "derived_clean_unacknowledged_br_airbase_export_projection_candidate"
        )
    else:
        authority = "derived_unversioned_br_airbase_export_projection_candidate"

    report = {
        "schema": "dcsmizzer.br-coordinate-conversion/v1",
        "authority": authority,
        "dcs_started": False,
        "runtime_valid": None,
        "terrain": selected_theatre,
        "source": airbase_source.relative_path,
        "source_sha256": airbase_source.sha256,
        "source_sha256_scope": f"{airbase_source.parsed_from}_bytes",
        "decision_source_binding": source_binding,
        "upstream": upstream,
        "upstream_project_version": _project_version_evidence(project_source),
        "source_mapping": {
            "latitude": "pos.World.lat",
            "longitude": "pos.World.lon",
            "mission_x": "pos.DCS.x",
            "mission_y": "pos.DCS.z",
            "ignored": ["pos.World.alt", "pos.DCS.y"],
        },
        "source_limits": {
            "maximum_json_depth": _MAX_JSON_DEPTH,
            "maximum_airbase_export_records": (_MAX_AIRBASE_EXPORT_RECORDS),
            "maximum_records_in_selected_terrain": _MAX_TERRAIN_RECORDS,
            "maximum_unique_coordinate_samples": _MAX_UNIQUE_SAMPLES,
        },
        "coverage": {
            "airbase_records_in_terrain": extracted.records_in_terrain,
            "finite_coordinate_records": extracted.finite_coordinate_records,
            "invalid_coordinate_records": extracted.invalid_coordinate_records,
            "all_airbase_records_have_usable_coordinates": (
                extracted.invalid_coordinate_records == 0
            ),
            "invalid_coordinate_records_used": False,
            "unique_finite_coordinate_samples": len(extracted.samples),
            "duplicate_coordinate_records": (extracted.duplicate_coordinate_records),
            "fit_samples": len(extracted.samples),
            "all_unique_finite_samples_used": True,
        },
        "sample_envelope": envelope,
        "duplicate_coordinate_diagnostics": {
            "groups_total": extracted.duplicate_groups_total,
            "groups_returned": len(extracted.duplicate_groups),
            "output_truncated": (
                len(extracted.duplicate_groups) < extracted.duplicate_groups_total
            ),
            "groups": extracted.duplicate_groups,
        },
        "model": model,
        "validation": {
            "validated": validated,
            "failure_reasons": failure_reasons,
            "thresholds": {
                "minimum_unique_finite_samples": _MIN_UNIQUE_SAMPLES,
                "scale_factor": {
                    "minimum": _MIN_SCALE_FACTOR,
                    "maximum": _MAX_SCALE_FACTOR,
                },
                "maximum_forward_error_m": _MAX_ERROR_M,
                "maximum_inverse_error_m": _MAX_ERROR_M,
                "maximum_leave_one_out_error_m": _MAX_ERROR_M,
                "next_candidate_minimum_absolute_rms_gap_m": (
                    _MIN_NEXT_CANDIDATE_ABSOLUTE_GAP_M
                ),
                "next_candidate_minimum_relative_rms_gap": (
                    _MIN_NEXT_CANDIDATE_RELATIVE_GAP
                ),
            },
            "best_candidate": fit_diagnostics["best_candidate"],
            "next_candidate": fit_diagnostics["next_candidate"],
            "candidate_separation": fit_diagnostics["candidate_separation"],
            "leave_one_out": fit_diagnostics["leave_one_out"],
            "outlier_policy": (
                "exact duplicate tuples are collapsed; every distinct finite "
                "tuple is fitted; no outlier or placeholder candidate is removed"
            ),
            "invalid_coordinate_policy": (
                "records without finite, in-range World.lat/lon and finite "
                "DCS.x/z are counted as invalid and cannot participate in a "
                "numeric fit; their presence does not independently fail a "
                "fit made from at least five usable unique tuples"
            ),
        },
        "extrapolation": extrapolation,
        "conversion": conversion,
        "view": {
            "mode": "bounded_evidence",
            "budget_bytes": _REPORT_CONTEXT_BUDGET_BYTES,
            "output_truncated": False,
        },
        "limitations": [
            "This is a lower-authority transform derived from exported "
            "BriefingRoom airport centres, not the current initialized DCS "
            "terrain registry.",
            "Validation at airport centres does not prove terrain height, "
            "surface, collision, runway, parking, or unit placement validity.",
            "Points outside the reported sample envelope are extrapolations.",
            "runtime_valid is null because DCS and Mission Editor were not started.",
        ],
    }
    return _fit_report_context_budget(report)


def _load_bound_sources(
    root: Path,
    upstream: dict[str, Any],
) -> tuple[
    _DecisionSource,
    list[_DecisionSource],
    _DecisionSource | None,
    dict[str, Any],
]:
    commit_value = upstream.get("commit")
    commit = commit_value if isinstance(commit_value, str) else None
    head_entries, tree_read = _head_tree_entries(root, commit)

    airbase_relative = "DatabaseJSON/TheatersAirbases.json"
    airbase_source = _decision_source(
        root,
        airbase_relative,
        head_entries.get(airbase_relative),
        max_bytes=_MAX_AIRBASE_EXPORT_BYTES,
    )

    theatre_relatives = sorted(
        (
            relative
            for relative in head_entries
            if _is_direct_theatre_declaration(relative)
        ),
        key=str.casefold,
    )
    if not theatre_relatives:
        theatre_relatives = _worktree_theatre_relatives(root)
    theatre_sources = [
        _decision_source(
            root,
            relative,
            head_entries.get(relative),
            max_bytes=_MAX_THEATRE_DECLARATION_BYTES,
        )
        for relative in theatre_relatives
    ]
    if not theatre_sources:
        raise ValueError("BriefingRoom root has no theatre declarations")

    project_relative = "src/BriefingRoom/BriefingRoom.cs"
    project_source = (
        _decision_source(
            root,
            project_relative,
            head_entries.get(project_relative),
            max_bytes=_MAX_PROJECT_SOURCE_BYTES,
        )
        if project_relative in head_entries
        else None
    )
    required_sources = [airbase_source, *theatre_sources]
    return (
        airbase_source,
        theatre_sources,
        project_source,
        _decision_source_binding(
            required_sources,
            commit=commit,
            git_tree_read=tree_read,
        ),
    )


def _head_tree_entries(
    root: Path,
    commit: str | None,
) -> tuple[dict[str, tuple[str, str, str]], bool]:
    if commit is None:
        return {}, False
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-tree",
                "-r",
                "-z",
                commit,
                "--",
                "Database/Theaters",
                "DatabaseJSON/TheatersAirbases.json",
                "src/BriefingRoom/BriefingRoom.cs",
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}, False
    if result.returncode != 0:
        return {}, False

    entries: dict[str, tuple[str, str, str]] = {}
    try:
        records = result.stdout.split(b"\0")
        for raw_record in records:
            if not raw_record:
                continue
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode, object_type, oid = metadata.decode("ascii").split(" ", 2)
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative in entries:
                return {}, False
            entries[relative] = (mode, object_type, oid)
    except (UnicodeError, ValueError):
        return {}, False
    return entries, True


def _decision_source(
    root: Path,
    relative: str,
    head_entry: tuple[str, str, str] | None,
    *,
    max_bytes: int,
) -> _DecisionSource:
    path = root / PurePosixPath(relative)
    worktree_regular = _is_regular_worktree_file(root, path)
    if head_entry is not None:
        mode, object_type, oid = head_entry
        if mode in _REGULAR_GIT_BLOB_MODES and object_type == "blob":
            payload = _read_head_blob(
                root,
                oid,
                max_bytes=max_bytes,
            )
            return _DecisionSource(
                relative_path=relative,
                payload=payload,
                git_mode=mode,
                git_blob_oid=oid,
                worktree_regular_file=worktree_regular,
                parsed_from="git_HEAD_blob",
            )

    payload = _read_regular_worktree_file(
        root,
        path,
        max_bytes=max_bytes,
    )
    return _DecisionSource(
        relative_path=relative,
        payload=payload,
        git_mode=head_entry[0] if head_entry is not None else None,
        git_blob_oid=head_entry[2] if head_entry is not None else None,
        worktree_regular_file=True,
        parsed_from="unbound_worktree_file",
    )


def _read_head_blob(
    root: Path,
    oid: str,
    *,
    max_bytes: int,
) -> bytes:
    try:
        size_result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-s", oid],
            check=False,
            capture_output=True,
            timeout=15,
        )
        if size_result.returncode != 0:
            raise ValueError("cannot read a required BriefingRoom HEAD blob")
        size = int(size_result.stdout.strip())
        if size < 0 or size > max_bytes:
            raise ValueError("required BriefingRoom source exceeds its size limit")
        blob_result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", oid],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise ValueError("cannot read a required BriefingRoom HEAD blob") from error
    if blob_result.returncode != 0 or len(blob_result.stdout) != size:
        raise ValueError("cannot read a required BriefingRoom HEAD blob")
    return blob_result.stdout


def _worktree_theatre_relatives(root: Path) -> list[str]:
    directory = root / "Database" / "Theaters"
    if not _is_regular_worktree_directory(root, directory):
        raise ValueError(
            "BriefingRoom theatre directory is not a regular contained directory"
        )
    try:
        paths = [
            path
            for path in directory.iterdir()
            if path.name.casefold().endswith(".ini")
        ]
    except OSError as error:
        raise ValueError(
            "cannot enumerate BriefingRoom theatre declarations"
        ) from error
    return sorted(
        (path.relative_to(root).as_posix() for path in paths),
        key=str.casefold,
    )


def _is_direct_theatre_declaration(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(
        len(parts) == 3
        and parts[:2] == ("Database", "Theaters")
        and parts[2].casefold().endswith(".ini")
    )


def _is_regular_worktree_file(root: Path, path: Path) -> bool:
    try:
        _require_contained_path(root, path)
        _require_regular_path_components(root, path.parent)
        status = path.lstat()
    except (OSError, ValueError):
        return False
    return bool(
        stat.S_ISREG(status.st_mode)
        and not stat.S_ISLNK(status.st_mode)
        and not _status_is_reparse_point(status)
    )


def _is_regular_worktree_directory(root: Path, path: Path) -> bool:
    try:
        _require_contained_path(root, path)
        _require_regular_path_components(root, path.parent)
        status = path.lstat()
    except (OSError, ValueError):
        return False
    return bool(
        stat.S_ISDIR(status.st_mode)
        and not stat.S_ISLNK(status.st_mode)
        and not _status_is_reparse_point(status)
    )


def _read_regular_worktree_file(
    root: Path,
    path: Path,
    *,
    max_bytes: int,
) -> bytes:
    _require_contained_path(root, path)
    _require_regular_path_components(root, path.parent)
    try:
        path_status = path.lstat()
    except OSError as error:
        raise ValueError("required BriefingRoom source does not exist") from error
    _validate_regular_source_status(path_status, max_bytes=max_bytes)

    flags = os.O_RDONLY
    for name in ("O_BINARY", "O_CLOEXEC", "O_NOINHERIT", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("cannot open a required BriefingRoom source") from error
    try:
        opened_status = os.fstat(descriptor)
        _validate_regular_source_status(opened_status, max_bytes=max_bytes)
        if _file_identity(path_status) != _file_identity(opened_status):
            raise ValueError("BriefingRoom source changed while it was opened")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(max_bytes + 1)
            final_status = os.fstat(descriptor)
        _validate_regular_source_status(final_status, max_bytes=max_bytes)
        if _file_identity(opened_status) != _file_identity(
            final_status
        ) or _file_version(opened_status) != _file_version(final_status):
            raise ValueError("BriefingRoom source changed while it was read")
        final_path_status = path.lstat()
        _validate_regular_source_status(final_path_status, max_bytes=max_bytes)
        if _file_identity(opened_status) != _file_identity(final_path_status):
            raise ValueError("BriefingRoom source changed while it was read")
    except OSError as error:
        raise ValueError("cannot read a required BriefingRoom source") from error
    finally:
        os.close(descriptor)
    if len(payload) > max_bytes:
        raise ValueError("required BriefingRoom source exceeds its size limit")
    if len(payload) != final_status.st_size:
        raise ValueError("BriefingRoom source changed while it was read")
    return payload


def _require_contained_path(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError("required BriefingRoom source escapes its checkout") from error


def _require_regular_path_components(root: Path, directory: Path) -> None:
    current = directory
    while current != root:
        try:
            current.relative_to(root)
            status = current.lstat()
        except (OSError, ValueError) as error:
            raise ValueError("BriefingRoom source path has an unsafe parent") from error
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or _status_is_reparse_point(status)
        ):
            raise ValueError("BriefingRoom source path has an unsafe parent")
        current = current.parent


def _validate_regular_source_status(
    status: os.stat_result,
    *,
    max_bytes: int,
) -> None:
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or _status_is_reparse_point(status)
    ):
        raise ValueError("required BriefingRoom source is not a regular file")
    if status.st_size < 0 or status.st_size > max_bytes:
        raise ValueError("required BriefingRoom source exceeds its size limit")


def _status_is_reparse_point(status: os.stat_result) -> bool:
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _file_identity(status: os.stat_result) -> tuple[int, int]:
    return status.st_dev, status.st_ino


def _file_version(status: os.stat_result) -> tuple[int, int, int]:
    return status.st_size, status.st_mtime_ns, status.st_ctime_ns


def _parse_airbases(source: _DecisionSource) -> list[dict[str, Any]]:
    _validate_json_depth(source.payload)
    try:
        data = json.loads(source.payload.decode("utf-8-sig"))
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise ValueError("cannot parse BriefingRoom airbase export") from error
    if not isinstance(data, list):
        raise ValueError("BriefingRoom airbase export root is not an array")
    if len(data) > _MAX_AIRBASE_EXPORT_RECORDS:
        raise ValueError("BriefingRoom airbase export exceeds its record limit")
    records = [item for item in data if isinstance(item, dict)]
    if len(records) != len(data):
        raise ValueError("BriefingRoom airbase export has non-object records")
    return records


def _parse_theatre_entries(
    sources: list[_DecisionSource],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sources:
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read_string(source.payload.decode("utf-8-sig"))
            dcs_id = parser["Theater"]["DCSID"].strip()
            display_name = parser["GUI"]["DisplayName"].strip()
        except (
            UnicodeDecodeError,
            KeyError,
            configparser.Error,
        ) as error:
            raise ValueError("cannot parse BriefingRoom theatre declaration") from error
        if _SAFE_COMPONENT.fullmatch(dcs_id) is None or not display_name:
            raise ValueError("BriefingRoom theatre declaration is incomplete")
        if (
            len(dcs_id) > _MAX_THEATRE_ID_TEXT
            or len(display_name) > _MAX_THEATRE_DISPLAY_TEXT
        ):
            raise ValueError("BriefingRoom theatre declaration exceeds its text limit")
        records.append(
            {
                "declaration_id": PurePosixPath(source.relative_path).stem,
                "dcs_id": dcs_id,
                "display_name": display_name,
                "default_map_center": parser["Theater"].get("DefaultMapCenter"),
                "magnetic_declination": _optional_float(
                    parser["Theater"].get("MagneticDeclination")
                ),
                "source": source.relative_path,
                "source_sha256": source.sha256,
            }
        )
    return records


def _project_version_evidence(
    source: _DecisionSource | None,
) -> dict[str, Any] | None:
    if source is None:
        return None
    try:
        text = source.payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    match = _PROJECT_VERSION.search(text)
    version = match.group("version") if match is not None else None
    version_too_long = (
        isinstance(version, str) and len(version) > _MAX_PROJECT_VERSION_TEXT
    )
    return {
        "targeted_dcs_world_version": (None if version_too_long else version),
        "parse_status": (
            "value_exceeds_text_limit"
            if version_too_long
            else "matched"
            if version is not None
            else "not_found"
        ),
        "scope": "project_level_not_per_export_file",
        "source": source.relative_path,
        "source_sha256": source.sha256,
        "parsed_from": source.parsed_from,
    }


def _decision_source_binding(
    sources: list[_DecisionSource],
    *,
    commit: str | None,
    git_tree_read: bool,
) -> dict[str, Any]:
    unbound = [source.relative_path for source in sources if not source.bound_to_head]
    manifest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.relative_path.casefold()):
        manifest.update(source.relative_path.encode("utf-8"))
        manifest.update(b"\0")
        manifest.update(source.sha256.encode("ascii"))
        manifest.update(b"\0")
        manifest.update((source.git_blob_oid or "").encode("ascii"))
        manifest.update(b"\0")
    return {
        "basis": (
            "the exact git HEAD blob bytes are parsed and hashed; each "
            "required worktree path must materialize as a contained regular "
            "non-reparse file"
        ),
        "head_commit": commit,
        "git_tree_read": git_tree_read,
        "required_sources": len(sources),
        "parsed_from_head_blobs": sum(
            source.parsed_from == "git_HEAD_blob" for source in sources
        ),
        "regular_worktree_files": sum(
            source.worktree_regular_file for source in sources
        ),
        "all_required_sources_bound_to_head": bool(
            commit
            and git_tree_read
            and sources
            and all(source.bound_to_head for source in sources)
        ),
        "parsed_source_manifest_sha256": manifest.hexdigest(),
        "unbound_sources": unbound[:5],
        "unbound_sources_truncated": len(unbound) > 5,
    }


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value.strip())
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _validate_conversion_request(
    *,
    latitude: float | None,
    longitude: float | None,
    map_x: float | None,
    map_y: float | None,
) -> None:
    forward_requested = latitude is not None or longitude is not None
    inverse_requested = map_x is not None or map_y is not None
    if forward_requested and inverse_requested:
        raise ValueError("choose either latitude/longitude or x/y")
    if forward_requested and (latitude is None or longitude is None):
        raise ValueError("latitude and longitude must be supplied together")
    if inverse_requested and (map_x is None or map_y is None):
        raise ValueError("x and y must be supplied together")
    for name, value in (
        ("latitude", latitude),
        ("longitude", longitude),
        ("x", map_x),
        ("y", map_y),
    ):
        if value is not None and _finite_float(value) is None:
            raise ValueError(f"{name} must be finite")
    if latitude is not None and not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if longitude is not None and not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")


def _extract_coordinate_samples(
    records: list[dict[str, Any]],
) -> _ExtractedSamples:
    grouped: dict[
        tuple[float, float, float, float],
        list[dict[str, Any]],
    ] = defaultdict(list)
    invalid = 0
    for record_index, item in enumerate(records):
        position = item.get("pos")
        if not isinstance(position, dict):
            invalid += 1
            continue
        dcs = position.get("DCS")
        world = position.get("World")
        if not isinstance(dcs, dict) or not isinstance(world, dict):
            invalid += 1
            continue
        values = (
            world.get("lat"),
            world.get("lon"),
            dcs.get("x"),
            dcs.get("z"),
        )
        converted_values = tuple(_finite_float(value) for value in values)
        if any(value is None for value in converted_values):
            invalid += 1
            continue
        latitude, longitude, map_x, map_y = converted_values
        assert latitude is not None
        assert longitude is not None
        assert map_x is not None
        assert map_y is not None
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            invalid += 1
            continue
        grouped[(latitude, longitude, map_x, map_y)].append(
            _record_reference(item, record_index)
        )

    samples = [
        CoordinateSample(
            latitude=key[0],
            longitude=key[1],
            map_x=key[2],
            map_y=key[3],
            airdrome_id=index,
        )
        for index, key in enumerate(
            sorted(grouped),
            start=1,
        )
    ]
    duplicate_items = sorted(
        (
            (key, references)
            for key, references in grouped.items()
            if len(references) > 1
        ),
        key=lambda item: (
            -len(item[1]),
            item[0],
        ),
    )
    duplicate_groups = [
        _duplicate_group_record(key, references)
        for key, references in duplicate_items[:_MAX_DUPLICATE_GROUPS]
    ]
    finite_records = sum(len(references) for references in grouped.values())
    return _ExtractedSamples(
        samples=samples,
        records_in_terrain=len(records),
        finite_coordinate_records=finite_records,
        invalid_coordinate_records=invalid,
        duplicate_coordinate_records=finite_records - len(samples),
        duplicate_groups=duplicate_groups,
        duplicate_groups_total=len(duplicate_items),
    )


def _record_reference(
    item: dict[str, Any],
    record_index: int,
) -> dict[str, Any]:
    identifier = item.get("ID")
    name = item.get("displayName")
    if not isinstance(name, str) or not name.strip():
        name = item.get("typeName")
    normalized_name = name.strip() if isinstance(name, str) else ""
    return {
        "record_index": record_index,
        "airdrome_id": (
            identifier
            if isinstance(identifier, int) and not isinstance(identifier, bool)
            else None
        ),
        "name": (
            _bounded_text(normalized_name, _MAX_DIAGNOSTIC_TEXT)
            if normalized_name
            else None
        ),
        "name_truncated": len(normalized_name) > _MAX_DIAGNOSTIC_TEXT,
    }


def _duplicate_group_record(
    key: tuple[float, float, float, float],
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    latitude, longitude, map_x, map_y = key
    possible_placeholder = (
        abs(latitude) <= 0.01
        and abs(longitude) <= 0.01
        and math.hypot(map_x, map_y) >= 100_000.0
    )
    ordered_references = sorted(
        references,
        key=lambda item: (
            item["airdrome_id"] is None,
            item["airdrome_id"] if item["airdrome_id"] is not None else 0,
            item["record_index"],
        ),
    )
    return {
        "classification": (
            "possible_repeated_placeholder_coordinate"
            if possible_placeholder
            else "exact_duplicate_coordinate_tuple"
        ),
        "coordinate": {
            "latitude": latitude,
            "longitude": longitude,
            "x": map_x,
            "y": map_y,
        },
        "occurrences": len(references),
        "record_references": ordered_references[:_MAX_DUPLICATE_RECORD_REFERENCES],
        "record_references_truncated": (
            len(references) > _MAX_DUPLICATE_RECORD_REFERENCES
        ),
    }


def _fit_diagnostics(
    samples: list[CoordinateSample],
) -> dict[str, Any]:
    empty = {
        "fit": None,
        "best_candidate": None,
        "next_candidate": None,
        "candidate_separation": None,
        "leave_one_out": None,
        "failure_reasons": [],
    }
    if len(samples) < _MIN_UNIQUE_SAMPLES:
        return empty

    fits = _candidate_fits(samples)
    if len(fits) < 2:
        return {
            **empty,
            "failure_reasons": ["projection_candidates_could_not_be_fitted"],
        }
    best, next_best = fits[:2]
    inverse_rms, inverse_max = _inverse_error_summary(samples, best)
    separation = _candidate_separation(best, next_best)
    leave_one_out = _leave_one_out_diagnostics(
        samples,
        expected_central_meridian=best.central_meridian,
    )

    reasons: list[str] = []
    if not _MIN_SCALE_FACTOR <= best.scale_factor <= _MAX_SCALE_FACTOR:
        reasons.append("best_candidate_scale_factor_out_of_range")
    if best.max_error_m > _MAX_ERROR_M:
        reasons.append("best_candidate_forward_error_exceeds_limit")
    if inverse_max > _MAX_ERROR_M:
        reasons.append("best_candidate_inverse_error_exceeds_limit")
    if not separation["significant"]:
        reasons.append("best_projection_candidate_not_significantly_separated")
    if leave_one_out["folds_completed"] != len(samples):
        reasons.append("leave_one_out_fit_incomplete")
    elif not leave_one_out["same_central_meridian"]:
        reasons.append("leave_one_out_central_meridian_unstable")
    if leave_one_out["maximum_forward_error_m"] is None or (
        leave_one_out["maximum_forward_error_m"] > _MAX_ERROR_M
    ):
        reasons.append("leave_one_out_forward_error_exceeds_limit")
    if leave_one_out["maximum_inverse_error_m"] is None or (
        leave_one_out["maximum_inverse_error_m"] > _MAX_ERROR_M
    ):
        reasons.append("leave_one_out_inverse_error_exceeds_limit")

    return {
        "fit": best,
        "best_candidate": {
            **_candidate_record(best),
            "inverse_rms_error_m": inverse_rms,
            "inverse_max_error_m": inverse_max,
        },
        "next_candidate": _candidate_record(next_best),
        "candidate_separation": separation,
        "leave_one_out": leave_one_out,
        "failure_reasons": reasons,
    }


def _candidate_fits(
    samples: list[CoordinateSample],
) -> list[ProjectionFit]:
    fits: list[ProjectionFit] = []
    for central_meridian in UTM_CENTRAL_MERIDIANS:
        try:
            fit = _fit_projection(samples, central_meridian)
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if _fit_is_finite(fit):
            fits.append(fit)
    return sorted(
        fits,
        key=lambda item: (
            item.rms_error_m,
            item.max_error_m,
            abs(item.scale_factor - 1.0),
            item.central_meridian,
        ),
    )


def _fit_is_finite(fit: ProjectionFit) -> bool:
    return all(
        math.isfinite(value)
        for value in (
            fit.scale_factor,
            fit.false_easting,
            fit.false_northing,
            fit.rms_error_m,
            fit.max_error_m,
        )
    )


def _inverse_error_summary(
    samples: list[CoordinateSample],
    fit: ProjectionFit,
) -> tuple[float, float]:
    try:
        errors = _inverse_errors(samples, fit)
    except (OverflowError, ValueError, ZeroDivisionError):
        return math.inf, math.inf
    if not errors or not all(math.isfinite(error) for error in errors):
        return math.inf, math.inf
    return (
        math.sqrt(sum(error**2 for error in errors) / len(errors)),
        max(errors),
    )


def _candidate_record(fit: ProjectionFit) -> dict[str, Any]:
    return {
        "central_meridian": fit.central_meridian,
        "scale_factor": fit.scale_factor,
        "rms_error_m": fit.rms_error_m,
        "max_error_m": fit.max_error_m,
    }


def _candidate_separation(
    best: ProjectionFit,
    next_best: ProjectionFit,
) -> dict[str, Any]:
    absolute_gap = next_best.rms_error_m - best.rms_error_m
    required_gap = max(
        _MIN_NEXT_CANDIDATE_ABSOLUTE_GAP_M,
        best.rms_error_m * _MIN_NEXT_CANDIDATE_RELATIVE_GAP,
    )
    return {
        "absolute_rms_gap_m": absolute_gap,
        "required_rms_gap_m": required_gap,
        "significant": absolute_gap >= required_gap,
    }


def _leave_one_out_diagnostics(
    samples: list[CoordinateSample],
    *,
    expected_central_meridian: int,
) -> dict[str, Any]:
    forward_errors: list[float] = []
    inverse_errors: list[float] = []
    central_meridians: set[int] = set()
    for held_out_index, held_out in enumerate(samples):
        training = [
            sample for index, sample in enumerate(samples) if index != held_out_index
        ]
        fits = _candidate_fits(training)
        if not fits:
            break
        fit = fits[0]
        central_meridians.add(fit.central_meridian)
        try:
            predicted_x, predicted_y = _latlon_to_map(
                held_out.latitude,
                held_out.longitude,
                fit,
            )
            predicted_latitude, predicted_longitude = _map_to_latlon(
                held_out.map_x,
                held_out.map_y,
                fit,
            )
            forward_error = math.hypot(
                predicted_x - held_out.map_x,
                predicted_y - held_out.map_y,
            )
            inverse_error = _surface_distance_m(
                held_out.latitude,
                held_out.longitude,
                predicted_latitude,
                predicted_longitude,
            )
        except (OverflowError, ValueError, ZeroDivisionError):
            break
        if not math.isfinite(forward_error) or not math.isfinite(inverse_error):
            break
        forward_errors.append(forward_error)
        inverse_errors.append(inverse_error)
    return {
        "folds_requested": len(samples),
        "folds_completed": len(forward_errors),
        "central_meridians": sorted(central_meridians),
        "same_central_meridian": (
            len(forward_errors) == len(samples)
            and central_meridians == {expected_central_meridian}
        ),
        "maximum_forward_error_m": (max(forward_errors) if forward_errors else None),
        "maximum_inverse_error_m": (max(inverse_errors) if inverse_errors else None),
    }


def _model_record(fit: ProjectionFit) -> dict[str, Any]:
    return {
        "name": "WGS84 Transverse Mercator",
        "central_meridian": fit.central_meridian,
        "scale_factor": fit.scale_factor,
        "false_easting": fit.false_easting,
        "false_northing": fit.false_northing,
        "axis_mapping": {
            "mission_x": "projected_northing",
            "mission_y": "projected_easting",
        },
    }


def _sample_envelope(
    samples: list[CoordinateSample],
) -> dict[str, Any] | None:
    if not samples:
        return None
    return {
        "wgs84": {
            "minimum_latitude": min(sample.latitude for sample in samples),
            "maximum_latitude": max(sample.latitude for sample in samples),
            "minimum_longitude": min(sample.longitude for sample in samples),
            "maximum_longitude": max(sample.longitude for sample in samples),
        },
        "mission_local": {
            "minimum_x": min(sample.map_x for sample in samples),
            "maximum_x": max(sample.map_x for sample in samples),
            "minimum_y": min(sample.map_y for sample in samples),
            "maximum_y": max(sample.map_y for sample in samples),
        },
    }


def _extrapolation_record(
    envelope: dict[str, Any] | None,
    *,
    latitude: float | None,
    longitude: float | None,
    map_x: float | None,
    map_y: float | None,
) -> dict[str, Any]:
    if latitude is None and map_x is None:
        return {
            "query_requested": False,
            "outside_sample_envelope": None,
            "warning": None,
        }
    if envelope is None:
        return {
            "query_requested": True,
            "outside_sample_envelope": None,
            "warning": "No finite sample envelope is available.",
        }
    if latitude is not None and longitude is not None:
        bounds = envelope["wgs84"]
        outside = not (
            bounds["minimum_latitude"] <= latitude <= bounds["maximum_latitude"]
            and bounds["minimum_longitude"] <= longitude <= bounds["maximum_longitude"]
        )
    else:
        assert map_x is not None and map_y is not None
        bounds = envelope["mission_local"]
        outside = not (
            bounds["minimum_x"] <= map_x <= bounds["maximum_x"]
            and bounds["minimum_y"] <= map_y <= bounds["maximum_y"]
        )
    return {
        "query_requested": True,
        "outside_sample_envelope": outside,
        "warning": (
            "Requested point is outside the fitted airport-centre sample "
            "envelope; the result is an extrapolation."
            if outside
            else None
        ),
    }


def _conversion_record(
    fit: ProjectionFit,
    *,
    latitude: float | None,
    longitude: float | None,
    map_x: float | None,
    map_y: float | None,
) -> dict[str, Any] | None:
    if latitude is not None and longitude is not None:
        converted_x, converted_y = _checked_latlon_to_map(
            latitude,
            longitude,
            fit,
        )
        return {
            "direction": "WGS84_to_mission_local",
            "input": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "output": {"x": converted_x, "y": converted_y},
        }
    if map_x is not None and map_y is not None:
        converted_latitude, converted_longitude = _checked_map_to_latlon(
            map_x,
            map_y,
            fit,
        )
        return {
            "direction": "mission_local_to_WGS84",
            "input": {"x": map_x, "y": map_y},
            "output": {
                "latitude": converted_latitude,
                "longitude": converted_longitude,
            },
        }
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _validate_json_depth(payload: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                raise ValueError(
                    "BriefingRoom airbase export exceeds its JSON nesting-depth limit"
                )
        elif byte in (0x5D, 0x7D):
            depth -= 1


def _finite_float(value: Any) -> float | None:
    if not _is_number(value):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _bounded_text(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return value[: maximum - 1] + "…"


def _fit_report_context_budget(
    report: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = report["duplicate_coordinate_diagnostics"]
    groups = diagnostics["groups"]
    while _encoded_report_size(report) > _REPORT_CONTEXT_BUDGET_BYTES and groups:
        groups.pop()
        diagnostics["groups_returned"] = len(groups)
        diagnostics["output_truncated"] = True
        report["view"]["output_truncated"] = True
    if _encoded_report_size(report) > _REPORT_CONTEXT_BUDGET_BYTES:
        raise ValueError(
            "BriefingRoom coordinate report metadata exceeds the model-context budget"
        )
    return report


def _encoded_report_size(value: dict[str, Any]) -> int:
    text = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return len(text.replace("\n", "\r\n").encode("utf-8"))
