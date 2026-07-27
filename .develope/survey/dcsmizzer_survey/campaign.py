from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .lua import LuaDataError, LuaLimits, LuaTable, parse_lua_bytes


@dataclass(frozen=True)
class CampaignObservation:
    parse_valid: bool
    encoding: str | None
    version: int | float | None
    start_stage: int | float | None
    start_stage_exists: bool
    stage_count: int
    mission_references: int
    resolved_references: int
    missing_references: int
    interval_overlaps: int
    interval_gaps: int
    invalid_intervals: int
    top_level_keys: tuple[str, ...]
    error_code: str | None = None


def analyse_cmp(
    path: Path,
    *,
    limits: LuaLimits | None = None,
) -> CampaignObservation:
    selected_limits = limits or LuaLimits()
    try:
        if path.stat().st_size > selected_limits.max_input_bytes:
            return _invalid("input_limit")
        parsed = parse_lua_bytes(path.read_bytes(), limits=selected_limits)
        campaign = parsed.document.get("campaign")
        if not isinstance(campaign, LuaTable):
            return _invalid(
                "missing_campaign_table",
                encoding=parsed.encoding,
            )
    except (OSError, LuaDataError) as error:
        return _invalid(type(error).__name__)

    stages = _table(campaign.get("stages"))
    stage_fields = stages.numeric_items()
    stage_ids = {field.key for field in stage_fields}
    version = _number(campaign.get("version"))
    start_stage = _number(campaign.get("startStage"))
    mission_references = 0
    resolved_references = 0
    missing_references = 0
    overlaps = 0
    gaps = 0
    invalid_intervals = 0

    for stage_field in stage_fields:
        stage = _table(stage_field.value)
        intervals: list[tuple[float, float]] = []
        for reference_value in _numeric_values(stage.get("missions")):
            reference = _table(reference_value)
            mission_references += 1
            relative = reference.get("file")
            if isinstance(relative, str) and _safe_relative_path(relative):
                candidate = path.parent / Path(relative.replace("\\", "/"))
                if candidate.is_file():
                    resolved_references += 1
                else:
                    missing_references += 1
            else:
                missing_references += 1

            interval_values = [
                field.value
                for field in _table(reference.get("interval")).numeric_items()
            ]
            if (
                len(interval_values) == 2
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    for value in interval_values
                )
                and interval_values[0] <= interval_values[1]
            ):
                intervals.append(
                    (float(interval_values[0]), float(interval_values[1]))
                )
            else:
                invalid_intervals += 1

        stage_overlaps, stage_gaps = _interval_diagnostics(intervals)
        overlaps += stage_overlaps
        gaps += stage_gaps

    return CampaignObservation(
        parse_valid=True,
        encoding=parsed.encoding,
        version=version,
        start_stage=start_stage,
        start_stage_exists=start_stage in stage_ids,
        stage_count=len(stage_fields),
        mission_references=mission_references,
        resolved_references=resolved_references,
        missing_references=missing_references,
        interval_overlaps=overlaps,
        interval_gaps=gaps,
        invalid_intervals=invalid_intervals,
        top_level_keys=tuple(
            field.key
            for field in campaign.fields
            if isinstance(field.key, str)
        ),
    )


def _interval_diagnostics(
    intervals: list[tuple[float, float]],
) -> tuple[int, int]:
    if not intervals:
        return 0, 0
    ordered = sorted(intervals)
    overlaps = 0
    gaps = int(ordered[0][0] > 0)
    high = ordered[0][1]
    for low, upper in ordered[1:]:
        if low <= high:
            overlaps += 1
        elif low > high + 1:
            gaps += 1
        high = max(high, upper)
    if high < 100:
        gaps += 1
    return overlaps, gaps


def _safe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    return not (
        normalized.startswith("/")
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
    )


def _number(value: object) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _table(value: object) -> LuaTable:
    return value if isinstance(value, LuaTable) else LuaTable(())


def _numeric_values(value: object) -> list[object]:
    return [field.value for field in _table(value).numeric_items()]


def _invalid(
    error_code: str,
    *,
    encoding: str | None = None,
) -> CampaignObservation:
    return CampaignObservation(
        parse_valid=False,
        encoding=encoding,
        version=None,
        start_stage=None,
        start_stage_exists=False,
        stage_count=0,
        mission_references=0,
        resolved_references=0,
        missing_references=0,
        interval_overlaps=0,
        interval_gaps=0,
        invalid_intervals=0,
        top_level_keys=(),
        error_code=error_code,
    )
