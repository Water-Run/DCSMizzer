"""Bounded, model-facing views over complete evidence and validation reports.

The parsers in the rest of :mod:`dcsmizzer` intentionally return complete
Python dictionaries.  This module does not change those APIs.  It only shapes
CLI output so catalog discovery is cheap, while an explicit ``--details``
request can still expose the complete underlying report.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUMMARY_SCHEMA = "dcsmizzer.cli-summary/v1"
REPORT_SUMMARY_SCHEMA = "dcsmizzer.report-summary/v1"
SUMMARY_BUDGET_BYTES = 12 * 1024
DEFAULT_SUMMARY_LIMIT = 20
MAX_VIEW_LIMIT = 100
MAX_REPORT_INPUT_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_SUMMARY_TEXT = 256
MAX_REPORT_ISSUES = 40
MAX_REPORT_HASHES = 40
MAX_REPORT_HASH_DEPTH = 12

VIEW_COMMANDS = frozenset(
    {
        "capabilities",
        "terrain-coverage",
        "pydcs-terrains",
        "br-terrains",
        "pydcs-units",
        "pydcs-airports",
        "br-airbases",
        "pydcs-aircraft",
        "dcs-payload-index",
        "dcs-payload-match",
        "dcs-payloads",
        "dcs-airbases",
        "dcs-countries",
        "dcs-modules",
        "dcs-cloud-presets",
        "dcs-weather",
        "miz-registry",
    }
)

KNOWN_REPORT_SCHEMAS = frozenset(
    {
        "dcsmizzer.br-airbases/v1",
        "dcsmizzer.br-airfield-footprint/v1",
        "dcsmizzer.br-coordinate-conversion/v1",
        "dcsmizzer.br-spawnpoints/v1",
        "dcsmizzer.br-terrains/v1",
        "dcsmizzer.airfield-footprint/v1",
        "dcsmizzer.build-spec-evidence-audit/v1",
        "dcsmizzer.capabilities/v3",
        "dcsmizzer.cli-summary/v1",
        "dcsmizzer.cmp-inspection/v1",
        "dcsmizzer.corpus-survey/v1",
        "dcsmizzer.dcs-airbase-beacons/v1",
        "dcsmizzer.dcs-cloud-presets/v1",
        "dcsmizzer.dcs-coordinate-conversion/v1",
        "dcsmizzer.dcs-countries/v1",
        "dcsmizzer.dcs-default-payload-index/v1",
        "dcsmizzer.dcs-default-payloads/v1",
        "dcsmizzer.dcs-payload-match/v1",
        "dcsmizzer.dcs-mig29-gci/v1",
        "dcsmizzer.dcs-module-index/v1",
        "dcsmizzer.dcs-options-template/v1",
        "dcsmizzer.dcs-static/v1",
        "dcsmizzer.dcs-warehouse-template/v1",
        "dcsmizzer.dcs-weather-constraints/v1",
        "dcsmizzer.dcs-weather-presets/v1",
        "dcsmizzer.miz-build/v1",
        "dcsmizzer.miz-inspection/v1",
        "dcsmizzer.miz-verification/v1",
        "dcsmizzer.observed-miz-registry/v1",
        "dcsmizzer.observed-miz-summary/v1",
        "dcsmizzer.pydcs-aircraft/v2",
        "dcsmizzer.pydcs-airports/v1",
        "dcsmizzer.pydcs-terrains/v1",
        "dcsmizzer.pydcs-units/v1",
        "dcsmizzer.report-summary/v1",
        "dcsmizzer.evidence-manifest/v1",
        "dcsmizzer.runtime-collection/v1",
        "dcsmizzer.runtime-execution/v1",
        "dcsmizzer.runtime-preparation/v1",
        "dcsmizzer.runtime-preview/v1",
        "dcsmizzer.runtime-result/v1",
        "dcsmizzer.runtime-run/v1",
        "dcsmizzer.terrain-catalog/v1",
        "dcsmizzer.terrain-coverage/v1",
        "dcsmizzer.terrain-coverage/v2",
        "dcsmizzer.terrain-corridor/v1",
        "dcsmizzer.terrain-landmarks/v1",
        "dcsmizzer.terrain-physical-evidence/v1",
        "dcsmizzer.terrain-placement/v1",
        "dcsmizzer.terrain-point/v1",
        "dcsmizzer.terrain-probe-extraction/v1",
        "dcsmizzer.terrain-probe-instrumentation/v1",
        "dcsmizzer.terrain-probe-script/v1",
        "dcsmizzer.weather-consistency/v1",
    }
)

_HASH = re.compile(r"\A[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True)
class OutputView:
    """A rendered report plus the result of any new view-layer query."""

    report: dict[str, Any]
    query_matched: bool | None = None


class _ClippedList(list[Any]):
    """A JSON-compatible list carrying view-only truncation metadata."""

    def __init__(
        self,
        values: list[Any],
        *,
        total_items: int,
        returned_items: int,
    ) -> None:
        super().__init__(values)
        self.total_items = total_items
        self.returned_items = returned_items


class _ClippedDict(dict[str, Any]):
    """A JSON-compatible mapping carrying view-only truncation metadata."""

    def __init__(
        self,
        values: dict[str, Any],
        *,
        total_items: int,
        returned_items: int,
    ) -> None:
        super().__init__(values)
        self.total_items = total_items
        self.returned_items = returned_items


class _ClippedText(str):
    """A JSON-compatible string carrying view-only truncation metadata."""

    def __new__(
        cls,
        value: str,
        *,
        total_characters: int,
        returned_characters: int,
    ) -> _ClippedText:
        instance = super().__new__(cls, value)
        instance.total_characters = total_characters
        instance.returned_characters = returned_characters
        return instance


def output_view(
    command: str,
    report: dict[str, Any],
    *,
    details: bool = False,
    search: str | None = None,
    preset: str | None = None,
    limit: int | None = None,
) -> OutputView:
    """Return a bounded CLI view without mutating the complete report."""

    if command not in VIEW_COMMANDS:
        return OutputView(report)
    search = _validate_search(search)
    preset = _validate_preset(preset)
    limit = _validate_limit(limit)
    if search is not None and preset is not None:
        raise ValueError("--search and --preset are mutually exclusive")

    handlers = {
        "capabilities": _capabilities_view,
        "terrain-coverage": _terrain_coverage_view,
        "pydcs-terrains": _pydcs_terrain_view,
        "br-terrains": _br_terrain_view,
        "pydcs-units": _pydcs_unit_view,
        "pydcs-airports": _pydcs_airport_view,
        "br-airbases": _br_airbase_view,
        "pydcs-aircraft": _pydcs_aircraft_view,
        "dcs-payload-index": _payload_index_view,
        "dcs-payload-match": _payload_match_view,
        "dcs-payloads": _payload_view,
        "dcs-airbases": _dcs_airbase_view,
        "dcs-countries": _countries_view,
        "dcs-modules": _module_view,
        "dcs-cloud-presets": _cloud_preset_view,
        "dcs-weather": _weather_preset_view,
        "miz-registry": _registry_view,
    }
    return handlers[command](
        report,
        details=details,
        search=search,
        preset=preset,
        limit=limit,
    )


def _capabilities_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    """Keep the startup capability gate small while preserving full details."""

    del search, preset, limit
    if details:
        return OutputView(report)

    capabilities: dict[str, Any] = {}
    for name, raw in sorted(report.items()):
        if name in {"schema", "survey_basis"} or not isinstance(raw, dict):
            continue
        status = raw.get("status")
        if not isinstance(status, str):
            continue
        item: dict[str, Any] = {"status": status}
        for key in (
            "runtime_validity",
            "complete_compatibility",
            "current_runtime_exports_committed",
        ):
            if key in raw:
                item[key] = _clip_value(raw[key])
        capabilities[name] = item

    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "source_schema": _clip_value(report.get("schema")),
        "survey_basis": _clip_value(report.get("survey_basis")),
        "capabilities": capabilities,
        "routing": (
            "Use --details or Docs/capabilities.md only for the capability "
            "decision currently being made."
        ),
    }
    _set_view(
        summary,
        matched=len(capabilities),
        returned=len(capabilities),
    )
    if _encoded_size(summary) > SUMMARY_BUDGET_BYTES:
        raise ValueError("capability summary exceeds the model-context budget")
    return OutputView(summary)


def report_summary(path: Path) -> dict[str, Any]:
    """Safely read one known JSON report and return its bounded essentials."""

    raw = _read_bounded_report(path)
    parsed = _parse_report_json(raw)
    schema = parsed.get("schema")
    if not isinstance(schema, str) or schema not in KNOWN_REPORT_SCHEMAS:
        raise ValueError("JSON input does not use a known dcsmizzer report schema")

    validation = _validation_summary(parsed)
    failures, failure_count, warnings, warning_count = _report_issues(parsed)
    hashes, hash_count = _report_hashes(parsed)
    summary: dict[str, Any] = {
        "schema": REPORT_SUMMARY_SCHEMA,
        "source_schema": schema,
        "input": path.name,
        "input_bytes": len(raw),
        "claims_unverified": True,
        "reported_identity": _report_identity(parsed),
        "reported_status": _report_status(schema, validation),
        "reported_validation": validation,
        "reported_failure_count": failure_count,
        "reported_failures": failures,
        "reported_warning_count": warning_count,
        "reported_warnings": warnings,
        "reported_hash_count": hash_count,
        "reported_hashes": hashes[:MAX_REPORT_HASHES],
        "view": {
            "mode": "summary",
            "budget_bytes": SUMMARY_BUDGET_BYTES,
            "complete_report_read": True,
            "runtime_validation_performed": _runtime_performed(parsed),
            "failures_truncated": failure_count > len(failures),
            "warnings_truncated": warning_count > len(warnings),
            "hashes_truncated": hash_count > MAX_REPORT_HASHES,
            "issue_count_basis": "occurrences_before_bounded_deduplication",
            "hash_count_basis": "matching_fields",
            "hash_scan_depth_limit": MAX_REPORT_HASH_DEPTH,
            "schema_check": "identifier_only",
            "shape_check": "not_performed",
            "authenticity_check": "not_performed",
        },
    }
    return _fit_report_summary(summary)


def _terrain_coverage_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "terrains")
    exact = _terrain_query_is_exact(report)
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --terrain")
    selected = _search_records(
        records,
        search,
        ("dcs_theatre", "display_name", "record_key"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "terrains", selected, limit),
            _search_match(search, selected),
        )
    items = [
        (
            _terrain_coverage_exact_summary(item)
            if exact
            else {
                "dcs_theatre": item.get("dcs_theatre"),
                "display_name": item.get("display_name"),
                "identity_status": _mapping(item.get("identity_resolution")).get(
                    "status"
                ),
                "pydcs": item.get("pydcs") is not None,
                "briefingroom": item.get("briefingroom") is not None,
                "selected_parking_authority": item.get("selected_parking_authority"),
                "theatre_identity_conflict": item.get("theatre_identity_conflict"),
            }
        )
        for item in selected
    ]
    view = _catalog_summary(
        report,
        "terrains",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )
    if exact:
        view.report.update(
            {
                "identity_conflicts": _clip_value(
                    _relevant_identity_conflicts(report, selected)
                ),
                "selection_policy": _clip_value(report.get("selection_policy")),
                "limitations": _clip_value(report.get("limitations")),
            }
        )
        view = OutputView(
            _fit_catalog_summary(view.report, "terrains"),
            view.query_matched,
        )
    return view


def _pydcs_terrain_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "terrains")
    exact = _terrain_query_is_exact(report)
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --terrain")
    selected = _search_records(
        records,
        search,
        ("terrain_package", "terrain_class", "miz_theatre_name"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "terrains", selected, limit),
            _search_match(search, selected),
        )
    items: list[dict[str, Any]] = []
    for item in selected:
        if exact:
            items.append(_pydcs_terrain_exact_summary(item))
            continue
        airport = _mapping(item.get("airport_summary"))
        consistency = _mapping(
            airport.get("declared_bounds_consistency")
            or item.get("declared_bounds_consistency")
        )
        items.append(
            {
                "terrain_package": item.get("terrain_package"),
                "terrain_class": item.get("terrain_class"),
                "miz_theatre_name": item.get("miz_theatre_name"),
                "airports": airport.get("airports_parsed"),
                "parking_slots": airport.get("parking_slots"),
                "airport_parse_failures": airport.get("airport_parse_failures"),
                "declared_bounds_status": consistency.get("status"),
            }
        )
    view = _catalog_summary(
        report,
        "terrains",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )
    if exact:
        view.report.update(
            {
                "conversion": _clip_value(report.get("conversion")),
                "limitations": _clip_value(report.get("limitations")),
            }
        )
        view = OutputView(
            _fit_catalog_summary(view.report, "terrains"),
            view.query_matched,
        )
    return view


def _br_terrain_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "terrains")
    exact = _terrain_query_is_exact(report)
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --terrain")
    selected = _search_records(
        records,
        search,
        ("dcs_id", "declaration_id", "display_name"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "terrains", selected, limit),
            _search_match(search, selected),
        )
    items = (
        [dict(item) for item in selected]
        if exact
        else [
            {
                "dcs_id": item.get("dcs_id"),
                "declaration_id": item.get("declaration_id"),
                "display_name": item.get("display_name"),
                "airbases": item.get("airbases"),
                "default_map_center": item.get("default_map_center"),
                "magnetic_declination": item.get("magnetic_declination"),
            }
            for item in selected
        ]
    )
    return _catalog_summary(
        report,
        "terrains",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _pydcs_unit_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    units = _records(report, "units")
    if details:
        return OutputView(report)
    compact: list[dict[str, Any]] = []
    for unit in units:
        output = {
            key: _clip_value(value)
            for key, value in unit.items()
            if key != "flying_unit"
        }
        flying = _mapping(unit.get("flying_unit"))
        if flying:
            output["flying_summary"] = {
                "declared_pylons": flying.get("declared_pylons"),
                "pylon_assignment_count": flying.get("pylon_assignment_count"),
                "unresolved_pylon_assignments": flying.get(
                    "unresolved_pylon_assignments"
                ),
                "task_classes": flying.get("task_classes"),
                "tasks": [
                    _task_summary(item) for item in _dict_records(flying.get("tasks"))
                ],
                "task_default": _task_summary(_mapping(flying.get("task_default"))),
            }
        compact.append(output)
    view = _catalog_summary(
        report,
        "units",
        compact,
        total=_coverage_int(report, "units_indexed", len(units)),
        matched=_coverage_int(report, "matching_units", len(units)),
        search=search,
        limit=limit,
        preserve_existing_limit=True,
    )
    exact_type = _mapping(report.get("filters")).get("unit_type")
    if isinstance(exact_type, str) and any(
        item.get("unit_category") == "plane" for item in compact
    ):
        view.report["routing"] = {
            "need": "plane station/store compatibility",
            "next_command": "pydcs-aircraft",
            "narrow_with": [
                "--unit-type",
                "--station",
                "--search or --clsid",
            ],
            "avoid": ("Do not use pydcs-units --details for pylon compatibility."),
        }
        _fit_catalog_summary(view.report, "units")
    return view


def _pydcs_airport_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "airports")
    filters = _mapping(report.get("filters"))
    exact = filters.get("airport") is not None or filters.get("airdrome_id") is not None
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --airport/--airdrome-id")
    selected = _search_records(
        records,
        search,
        ("name", "class", "airdrome_id"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "airports", selected, None),
            _search_match(search, selected),
        )
    items = (
        [dict(item) for item in selected]
        if exact
        else [
            {
                "airdrome_id": item.get("airdrome_id"),
                "name": item.get("name"),
                "class": item.get("class"),
                "center": item.get("center"),
                "civilian": item.get("civilian"),
                "runway_count": item.get("runway_count"),
                "parking_slot_count": item.get("parking_slot_count"),
                "airplane_parking_slots": item.get("airplane_parking_slots"),
                "helicopter_parking_slots": item.get("helicopter_parking_slots"),
            }
            for item in selected
        ]
    )
    return _catalog_summary(
        report,
        "airports",
        items,
        total=_coverage_int(report, "airports_parsed", len(records)),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _br_airbase_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "airbases")
    filters = _mapping(report.get("filters"))
    exact = filters.get("airport") is not None or filters.get("airdrome_id") is not None
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --airport/--airdrome-id")
    selected = _search_records(
        records,
        search,
        (
            "airdrome_id",
            "display_name",
            "name",
            "type_name",
            "icao",
        ),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "airbases", selected, None),
            _search_match(search, selected),
        )
    items = (
        [dict(item) for item in selected]
        if exact
        else [
            {
                "airdrome_id": item.get("airdrome_id"),
                "name": item.get("name"),
                "display_name": item.get("display_name"),
                "type_name": item.get("type_name"),
                "icao": item.get("icao"),
                "center": item.get("center"),
                "runway_designators": item.get("runway_designators"),
                "parking_slot_count": item.get("parking_slot_count"),
                "airplane_parking_slots": item.get("airplane_parking_slots"),
                "helicopter_parking_slots": item.get("helicopter_parking_slots"),
            }
            for item in selected
        ]
    )
    return _catalog_summary(
        report,
        "airbases",
        items,
        total=_coverage_int(report, "airbases_in_terrain", len(records)),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _pydcs_aircraft_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    aircraft = _mapping(report.get("aircraft"))
    assignments = _dict_records(aircraft.get("pylon_assignments"))
    if search is not None:
        assignments = _search_records(
            assignments,
            search,
            (
                "station",
                "CLSID",
                "name",
                "declaration",
                "weapon_key",
            ),
        )
    query = bool(
        search is not None
        or _mapping(report.get("filters")).get("station") is not None
        or _mapping(report.get("filters")).get("CLSID") is not None
    )
    matched = len(assignments)
    if details:
        selected = _apply_explicit_limit(assignments, limit)
        output_aircraft = {**aircraft, "pylon_assignments": selected}
        output = {
            **report,
            "aircraft": output_aircraft or None,
            "view": _detail_view_metadata(
                matched=matched,
                returned=len(selected),
                explicit_limit=limit,
            ),
        }
        return OutputView(output, bool(matched) if query else None)

    if query:
        item_limit = limit if limit is not None else DEFAULT_SUMMARY_LIMIT
        selected = assignments[:item_limit]
        summary = _summary_envelope(report)
        summary.update(
            {
                "unit_type": report.get("unit_type"),
                "aircraft": _aircraft_summary(aircraft),
                "pylon_assignments": [_clip_mapping(item) for item in selected],
                "routing": {
                    "need": "prove one final station/store relationship",
                    "next_filter": "--station N --clsid {EXACT-CLSID}",
                    "details_needed": False,
                },
            }
        )
        _set_view(
            summary,
            matched=matched,
            returned=len(selected),
            limit=item_limit,
            search=search,
        )
        return OutputView(
            _fit_catalog_summary(summary, "pylon_assignments"),
            bool(matched),
        )

    summary = _summary_envelope(report)
    summary.update(
        {
            "unit_type": report.get("unit_type"),
            "aircraft": _aircraft_summary(aircraft),
            "routing": {
                "need": "list candidate stores without full output",
                "next_filter": "--station N --search TEXT --limit N",
                "then": "--station N --clsid {EXACT-CLSID}",
                "details_needed": False,
            },
        }
    )
    _set_view(summary, matched=1 if aircraft else 0, returned=1 if aircraft else 0)
    return OutputView(_fit_catalog_summary(summary, None))


def _payload_index_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "unit_types")
    selected = _search_records(records, search, ("unit_type",))
    if details:
        return OutputView(
            _full_collection_view(report, "unit_types", selected, limit),
            _search_match(search, selected),
        )
    items = [
        {
            "unit_type": item.get("unit_type"),
            "presets": item.get("presets"),
            "pylon_assignments": item.get("pylon_assignments"),
            "unique_clsids": item.get("unique_clsids"),
            "task_ids": item.get("task_ids"),
        }
        for item in selected
    ]
    return _catalog_summary(
        report,
        "unit_types",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _payload_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    records = _records(report, "presets")
    if preset is not None:
        selected = [
            item
            for item in records
            if item.get("name") == preset or item.get("display_name") == preset
        ]
    else:
        selected = _search_records(
            records,
            search,
            ("name", "display_name", "source", "CLSID"),
        )
    exact_single = preset is not None
    query_matched = (
        len(selected) == 1 if preset is not None else _search_match(search, selected)
    )
    if details:
        return OutputView(
            _full_collection_view(report, "presets", selected, limit),
            query_matched,
        )
    items = (
        [dict(item) for item in selected]
        if exact_single
        else [
            {
                "name": item.get("name"),
                "display_name": item.get("display_name"),
                "source": item.get("source"),
                "pylon_count": len(_list(item.get("pylons"))),
                "tasks": item.get("tasks"),
            }
            for item in selected
        ]
    )
    return _catalog_summary(
        report,
        "presets",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        preset=preset,
        limit=limit,
        query_matched=query_matched,
    )


def _payload_match_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del search, preset, limit
    if details:
        return OutputView(report)
    query = _mapping(report.get("query"))
    normalized = _mapping(query.get("normalized"))
    fingerprints = _mapping(query.get("fingerprints"))
    source_binding = _mapping(report.get("source_binding"))
    matches = [
        _clip_mapping(item)
        for item in _dict_records(report.get("matches"))
    ]
    summary = _summary_envelope(report)
    summary.update(
        {
            "dcs": _clip_mapping(_mapping(report.get("dcs"))),
            "classification": report.get("classification"),
            "verified_exact_observed_preset": report.get(
                "verified_exact_observed_preset"
            ),
            "query": {
                "valid": query.get("valid"),
                "issues": _clip_value(query.get("issues")),
                "pylon_count": len(_dict_records(normalized.get("pylons"))),
                "tasks": _clip_value(normalized.get("tasks")),
                "preset_name": _clip_value(normalized.get("preset_name")),
                "display_name": _clip_value(normalized.get("display_name")),
                "category": _clip_value(normalized.get("category")),
                "composition_sha256": fingerprints.get(
                    "composition_sha256"
                ),
                "configured_composition_sha256": fingerprints.get(
                    "configured_composition_sha256"
                ),
                "query_preset_sha256": fingerprints.get(
                    "query_preset_sha256"
                ),
            },
            "exact_composition_candidate_count": report.get(
                "exact_composition_candidate_count"
            ),
            "configuration_candidate_count": report.get(
                "configuration_candidate_count"
            ),
            "configuration_gap_candidate_count": report.get(
                "configuration_gap_candidate_count"
            ),
            "exact_match_count": report.get("exact_match_count"),
            "configuration_unspecified_stations": _clip_value(
                report.get("configuration_unspecified_stations")
            ),
            "unknown_pairs": _clip_value(report.get("unknown_pairs")),
            "matches": matches,
            "source_binding": {
                key: _clip_value(source_binding.get(key))
                for key in (
                    "payload_inventory_sha256",
                    "files_scanned",
                    "files_hashed",
                    "source_inventory_complete",
                    "candidate_enumeration_complete",
                    "candidate_enumeration_scope",
                    "parse_failure_count",
                    "relevant_parse_failure_count",
                    "unit_type_invalid_payload_tables",
                    "unit_type_invalid_presets",
                    "unit_type_sources",
                    "relevant_parse_failure_sources",
                )
                if key in source_binding
            },
        }
    )
    _set_view(
        summary,
        matched=int(report.get("exact_match_count") or 0),
        returned=len(matches),
    )
    return OutputView(_fit_catalog_summary(summary, "matches"))


def _dcs_airbase_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "airbases")
    exact = _mapping(report.get("filter")).get("airdrome_id") is not None
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --airdrome-id")
    selected = _search_records(
        records,
        search,
        ("airdrome_id", "names", "callsigns"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "airbases", selected, limit),
            _search_match(search, selected),
        )
    items = [
        {
            "airdrome_id": item.get("airdrome_id"),
            "names": item.get("names"),
            "callsigns": item.get("callsigns"),
            "beacon_count": item.get("beacon_count"),
            "beacon_types": item.get("beacon_types"),
            "radio_count": item.get("radio_count"),
        }
        for item in selected
    ]
    return _catalog_summary(
        report,
        "airbases",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _countries_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "entries")
    selected = _search_records(records, search, ("identifier", "id"))
    if details:
        return OutputView(
            _full_collection_view(report, "entries", selected, limit),
            _search_match(search, selected),
        )
    item_limit = limit if limit is not None else DEFAULT_SUMMARY_LIMIT
    returned = selected[:item_limit]
    summary = _summary_envelope(report)
    summary.update(
        {
            "count": report.get("count"),
            "reserved_ids": report.get("reserved_ids"),
            "reserved_id_count": len(_list(report.get("reserved_ids"))),
            "duplicate_identifiers": report.get("duplicate_identifiers"),
            "entries": [_clip_mapping(item) for item in returned],
            # Preserve the convenient old lookup field within the bounded view.
            "identifiers": [item.get("identifier") for item in returned],
        }
    )
    _set_view(
        summary,
        matched=len(selected),
        returned=len(returned),
        limit=item_limit,
        search=search,
    )
    return OutputView(
        _fit_catalog_summary(summary, "entries", linked_key="identifiers"),
        _search_match(search, selected),
    )


def _module_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "modules")
    filters = _mapping(report.get("filters"))
    exact = any(
        filters.get(key) is not None
        for key in (
            "module",
            "unit_type",
            "service_country",
            "service_year",
        )
    )
    if exact and search is not None:
        raise ValueError("--search cannot be combined with module/unit/service filters")
    selected = _search_records(
        records,
        search,
        (
            "module_directory",
            "module_key",
            "plugin_ids",
            "flyable_types",
            "default_payload_unit_types",
        ),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "modules", selected, limit),
            _search_match(search, selected),
        )
    items = [
        {
            "module_directory": item.get("module_directory"),
            "module_key": item.get("module_key"),
            "scope": item.get("scope"),
            "plugin_ids": item.get("plugin_ids"),
            "flyable_types": item.get("flyable_types"),
            "default_payload_unit_types": item.get("default_payload_unit_types"),
            "unresolved_literal_calls": item.get("unresolved_literal_calls"),
        }
        for item in selected
    ]
    return _catalog_summary(
        report,
        "modules",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _cloud_preset_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset
    records = _records(report, "presets")
    exact = _mapping(report.get("filter")).get("preset") is not None
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --preset")
    selected = _search_records(
        records,
        search,
        ("id", "readable_name_short"),
    )
    if details:
        return OutputView(
            _full_collection_view(report, "presets", selected, limit),
            _search_match(search, selected),
        )
    items = [
        {
            "id": item.get("id"),
            "readable_name_short": item.get("readable_name_short"),
            "base_altitude_range": item.get("base_altitude_range"),
            "precipitation_power": item.get("precipitation_power"),
            "visible_in_gui": item.get("visible_in_gui"),
        }
        for item in selected
    ]
    return _catalog_summary(
        report,
        "presets",
        items,
        total=len(records),
        matched=len(selected),
        search=search,
        limit=limit,
    )


def _weather_preset_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    records = _records(report, "presets")
    exact = preset is not None
    if exact and search is not None:
        raise ValueError("--search cannot be combined with --preset")
    if search is None:
        selected = records
    else:
        term = search.casefold()
        selected = []
        for item in records:
            names = _mapping(item.get("names"))
            texts = [
                item.get("id"),
                item.get("kind"),
                item.get("source"),
                *names.values(),
            ]
            if any(
                term in str(value).casefold()
                for value in texts
                if _is_scalar(value)
            ):
                selected.append(item)
    query_matched = (
        len(selected) == 1 if exact else _search_match(search, selected)
    )
    if details:
        return OutputView(
            _full_collection_view(report, "presets", selected, limit),
            query_matched,
        )
    if exact:
        items = [dict(item) for item in selected]
    else:
        items = []
        for item in selected:
            weather = _mapping(item.get("weather"))
            validation = _mapping(item.get("validation"))
            names = _mapping(item.get("names"))
            items.append(
                {
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "default_name": names.get("default"),
                    "source_sha256": item.get("source_sha256"),
                    "season": weather.get("season"),
                    "clouds": weather.get("clouds"),
                    "wind": weather.get("wind"),
                    "consistent": validation.get("consistent"),
                    "error_count": len(_list(validation.get("errors"))),
                    "warning_count": len(_list(validation.get("warnings"))),
                }
            )
    view = _catalog_summary(
        report,
        "presets",
        items,
        total=_coverage_int(report, "parsed_presets", len(records)),
        matched=len(selected),
        search=search,
        preset=preset,
        limit=limit,
        query_matched=query_matched,
    )
    view.report["constraints"] = _weather_constraints_summary(
        _mapping(report.get("constraints"))
    )
    return OutputView(
        _fit_catalog_summary(view.report, "presets"),
        view.query_matched,
    )


def _weather_constraints_summary(
    constraints: dict[str, Any],
) -> dict[str, Any]:
    temperature = _mapping(constraints.get("temperature"))
    ranges = _dict_records(temperature.get("fallback_ranges_c"))
    minimums = [
        item.get("minimum")
        for item in ranges
        if _is_scalar(item.get("minimum"))
    ]
    maximums = [
        item.get("maximum")
        for item in ranges
        if _is_scalar(item.get("maximum"))
    ]
    return {
        "precipitation_types": [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "name",
                    "minimum_density",
                    "minimum_temperature_c",
                    "maximum_temperature_c",
                )
            }
            for item in _dict_records(
                constraints.get("precipitation_types")
            )
        ],
        "fog_modes": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
            }
            for item in _dict_records(constraints.get("fog_modes"))
        ],
        "fog_dust_mutually_exclusive": constraints.get(
            "fog_dust_mutually_exclusive"
        ),
        "dust": _mapping(constraints.get("dust")),
        "temperature": {
            "fallback_seasons": len(ranges),
            "fallback_minimum_c": min(minimums) if minimums else None,
            "fallback_maximum_c": max(maximums) if maximums else None,
            "terrain_date_override_available": temperature.get(
                "terrain_date_override_available"
            ),
        },
    }


def _registry_view(
    report: dict[str, Any],
    *,
    details: bool,
    search: str | None,
    preset: str | None,
    limit: int | None,
) -> OutputView:
    del preset, limit
    if search is not None:
        raise ValueError("miz-registry does not support --search")
    if details:
        return OutputView(report)
    source_theatres = _list(report.get("theatres"))
    bounded_theatres = _clip_value(source_theatres)
    if not isinstance(bounded_theatres, list):
        bounded_theatres = []
    summary = {
        "schema": "dcsmizzer.observed-miz-summary/v1",
        "authority": _clip_value(report.get("authority")),
        "dcs_started": report.get("dcs_started"),
        "filters": _clip_value(report.get("filters")),
        "coverage": _clip_value(report.get("coverage")),
        "theatres": bounded_theatres,
        "privacy": _clip_value(report.get("privacy")),
        "limitations": _clip_value(report.get("limitations")),
        "view": {
            "mode": "summary",
            "budget_bytes": SUMMARY_BUDGET_BYTES,
            "details_available": True,
            "details_flag": "--details",
            "matching_items": len(source_theatres),
            "returned_items": len(bounded_theatres),
            "output_truncated": len(bounded_theatres) < len(source_theatres),
        },
    }
    return OutputView(_fit_catalog_summary(summary, "theatres"))


def _catalog_summary(
    report: dict[str, Any],
    collection: str,
    items: list[dict[str, Any]],
    *,
    total: int,
    matched: int,
    search: str | None,
    limit: int | None,
    preset: str | None = None,
    query_matched: bool | None = None,
    preserve_existing_limit: bool = False,
) -> OutputView:
    item_limit = limit if limit is not None else DEFAULT_SUMMARY_LIMIT
    if preserve_existing_limit and limit is None:
        returned = items
        item_limit = max(len(returned), 1)
    else:
        returned = items[:item_limit]
    summary = _summary_envelope(report)
    summary[collection] = [_clip_mapping(item) for item in returned]
    summary["catalog"] = {
        "total_items": total,
        "matching_items": matched,
        "returned_items": len(returned),
        "output_truncated": len(returned) < matched,
    }
    _set_view(
        summary,
        matched=matched,
        returned=len(returned),
        limit=item_limit,
        search=search,
        preset=preset,
    )
    return OutputView(
        _fit_catalog_summary(summary, collection),
        (query_matched if query_matched is not None else _search_match(search, items)),
    )


def _summary_envelope(report: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "source_schema": _clip_value(report.get("schema")),
        "authority": _clip_value(report.get("authority")),
        "dcs_started": report.get("dcs_started"),
        "filters": _compact_filters(report.get("filters", report.get("filter"))),
        "coverage": _compact_coverage(report.get("coverage")),
        "provenance": _provenance(report),
    }
    source_lock = report.get("source_lock")
    if isinstance(source_lock, dict):
        summary["source_lock"] = {
            "required_sources": _clip_value(
                source_lock.get("required_sources")
            ),
            "all_sources_commit_bound": source_lock.get(
                "all_sources_commit_bound"
            ),
            "failure_reasons": _clip_value(
                source_lock.get("failure_reasons")
            ),
        }
    for key in (
        "unit_type",
        "terrain_directory",
        "compatibility_complete",
        "coverage_complete",
    ):
        if key in report:
            summary[key] = _clip_value(report[key])
    return summary


def _set_view(
    report: dict[str, Any],
    *,
    matched: int,
    returned: int,
    limit: int | None = None,
    search: str | None = None,
    preset: str | None = None,
) -> None:
    filters = _mapping(report.get("filters"))
    if search is not None:
        filters["search"] = search
    if preset is not None:
        filters["preset"] = preset
    if limit is not None:
        filters["limit"] = limit
    report["filters"] = filters
    report["view"] = {
        "mode": "summary",
        "budget_bytes": SUMMARY_BUDGET_BYTES,
        "details_available": True,
        "details_flag": "--details",
        "matching_items": matched,
        "returned_items": returned,
        "output_truncated": returned < matched,
    }


def _detail_view_metadata(
    *,
    matched: int,
    returned: int,
    explicit_limit: int | None,
) -> dict[str, Any]:
    return {
        "mode": "details",
        "explicit": True,
        "matching_items": matched,
        "returned_items": returned,
        "output_truncated": returned < matched,
        "limit": explicit_limit,
        "context_warning": (
            "Detailed output can be large; redirect stdout to a JSON file and "
            "use report-summary or a narrower exact query."
        ),
    }


def _full_collection_view(
    report: dict[str, Any],
    collection: str,
    selected: list[dict[str, Any]],
    limit: int | None,
) -> dict[str, Any]:
    original = _records(report, collection)
    returned = _apply_explicit_limit(selected, limit)
    if limit is None and selected == original:
        return report
    output = {
        **report,
        collection: returned,
        "view": _detail_view_metadata(
            matched=len(selected),
            returned=len(returned),
            explicit_limit=limit,
        ),
    }
    return output


def _terrain_coverage_exact_summary(
    terrain: dict[str, Any],
) -> dict[str, Any]:
    pydcs = _mapping(terrain.get("pydcs"))
    briefingroom = _mapping(terrain.get("briefingroom"))
    return {
        "record_key": _clip_value(terrain.get("record_key")),
        "dcs_theatre": _clip_value(terrain.get("dcs_theatre")),
        "display_name": _clip_value(terrain.get("display_name")),
        "selected_parking_authority": _clip_value(
            terrain.get("selected_parking_authority")
        ),
        "theatre_identity_conflict": terrain.get("theatre_identity_conflict"),
        "identity_resolution": _clip_value(terrain.get("identity_resolution")),
        "pydcs": (
            {
                key: _clip_value(pydcs.get(key))
                for key in (
                    "terrain_package",
                    "terrain_class",
                    "declared_miz_theatre_name",
                    "airports",
                    "parking_slots",
                    "airport_parse_failures",
                    "bounds",
                    "projection",
                    "declared_center_wgs84",
                    "declared_center_diagnostic",
                    "sources",
                )
                if key in pydcs
            }
            | {
                "declared_bounds_consistency": (
                    _bounds_consistency_summary(
                        pydcs.get("declared_bounds_consistency")
                    )
                )
            }
            if pydcs
            else None
        ),
        "briefingroom": (
            {
                key: _clip_value(briefingroom.get(key))
                for key in (
                    "declaration_id",
                    "airbases",
                    "sea_mask_planning_geometry",
                    "sources",
                )
                if key in briefingroom
            }
            if briefingroom
            else None
        ),
    }


def _relevant_identity_conflicts(
    report: dict[str, Any],
    terrains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_keys = {
        item.get("record_key")
        for item in terrains
        if isinstance(item.get("record_key"), str)
    }
    if not selected_keys:
        return []
    output: list[dict[str, Any]] = []
    for conflict in _dict_records(report.get("identity_conflicts")):
        source_keys = {
            _mapping(conflict.get(source)).get("record_key")
            for source in ("pydcs_record", "briefingroom_record")
        }
        if selected_keys.intersection(source_keys):
            output.append(conflict)
    return output


def _pydcs_terrain_exact_summary(
    terrain: dict[str, Any],
) -> dict[str, Any]:
    airport = _mapping(terrain.get("airport_summary"))
    airport_summary = {
        key: _clip_value(airport.get(key))
        for key in (
            "airports_parsed",
            "airport_parse_failures",
            "parking_slots",
            "airplane_parking_slots",
            "helicopter_parking_slots",
        )
        if key in airport
    }
    if "declared_bounds_consistency" in airport:
        airport_summary["declared_bounds_consistency"] = _bounds_consistency_summary(
            airport.get("declared_bounds_consistency")
        )
    return {
        key: _clip_value(terrain.get(key))
        for key in (
            "terrain_package",
            "terrain_class",
            "miz_theatre_name",
            "declared_center_wgs84",
            "declared_center_diagnostic",
            "bounds",
            "projection",
            "sources",
        )
        if key in terrain
    } | {
        "declared_bounds_consistency": _bounds_consistency_summary(
            terrain.get("declared_bounds_consistency")
        ),
        "airport_summary": airport_summary,
    }


def _bounds_consistency_summary(value: Any) -> dict[str, Any]:
    consistency = _mapping(value)
    output = {
        key: _clip_value(consistency.get(key))
        for key in (
            "status",
            "hard_coordinate_rejection_allowed",
            "reason",
            "tolerance_m",
            "tolerance_rule",
            "airport_centers_parsed",
            "airport_parse_failures",
            "strictly_within",
            "within_tolerance",
            "obviously_outside",
        )
        if key in consistency
    }
    outside = consistency.get("obviously_outside_airports")
    if isinstance(outside, list):
        output["obviously_outside_airports_count"] = len(outside)
    return output


def _aircraft_summary(aircraft: dict[str, Any]) -> dict[str, Any] | None:
    if not aircraft:
        return None
    station_counts = Counter(
        item.get("station")
        for item in _dict_records(aircraft.get("pylon_assignments"))
        if isinstance(item.get("station"), int)
    )
    return {
        key: _clip_value(aircraft.get(key))
        for key in (
            "id",
            "flyable",
            "height",
            "width",
            "length",
            "fuel_max",
            "max_speed",
            "declared_pylons",
            "pylon_assignment_count",
            "unresolved_pylon_assignments",
            "task_classes",
            "unresolved_task_records",
        )
        if key in aircraft
    } | {
        "tasks": [_task_summary(item) for item in _dict_records(aircraft.get("tasks"))],
        "task_default": _task_summary(_mapping(aircraft.get("task_default"))),
        "assignments_by_station": [
            {"station": station, "assignments": count}
            for station, count in sorted(station_counts.items())
        ],
    }


def _task_summary(task: dict[str, Any]) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        key: _clip_value(task.get(key))
        for key in (
            "class",
            "id",
            "mission_group_task",
            "payload_internal_name",
            "resolved",
        )
        if key in task
    }


def _compact_filters(value: Any) -> dict[str, Any]:
    return {
        str(key): _clip_value(item)
        for key, item in _mapping(value).items()
        if _is_scalar(item)
    }


def _compact_coverage(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in _mapping(value).items():
        if _is_scalar(item):
            output[str(key)] = _clip_value(item)
        elif isinstance(item, list):
            if len(item) <= 12 and all(_is_scalar(entry) for entry in item):
                output[str(key)] = [_clip_value(entry) for entry in item]
            else:
                output[f"{key}_count"] = len(item)
        elif isinstance(item, dict):
            scalars = {
                str(child_key): _clip_value(child)
                for child_key, child in item.items()
                if _is_scalar(child)
            }
            if scalars:
                output[str(key)] = scalars
    return output


def _provenance(report: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    upstream = _mapping(report.get("upstream"))
    if upstream:
        output["upstream"] = _upstream_summary(upstream)
    sources = report.get("sources")
    if isinstance(sources, dict):
        source_versions: dict[str, Any] = {}
        for key in ("pydcs", "briefingroom"):
            source = _mapping(sources.get(key))
            if source:
                source_versions[key] = _upstream_summary(source)
        if source_versions:
            output["source_versions"] = source_versions
    source_refs = _source_references(report)
    if source_refs:
        output["source_references"] = source_refs
    version = report.get("upstream_project_version")
    if isinstance(version, dict):
        output["upstream_project_version"] = {
            str(key): _clip_value(value)
            for key, value in version.items()
            if _is_scalar(value)
        }
    return output


def _upstream_summary(upstream: dict[str, Any]) -> dict[str, Any]:
    summary = {
        key: _clip_value(upstream.get(key))
        for key in (
            "remote",
            "branch",
            "commit",
            "provenance",
            "acknowledged",
            "worktree_clean",
        )
        if key in upstream
    }
    source_lock = upstream.get("source_lock")
    if isinstance(source_lock, dict):
        summary["source_lock"] = {
            "acknowledged": source_lock.get("acknowledged"),
            "failure_reasons": _clip_value(
                source_lock.get("failure_reasons")
            ),
        }
    return summary


def _source_references(report: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    source = report.get("source")
    source_hash = report.get("source_sha256")
    if isinstance(source, str) or _valid_hash(source_hash):
        references.append(
            {
                "source": _clip_value(source),
                "source_sha256": source_hash if _valid_hash(source_hash) else None,
            }
        )
    for key in ("sources", "unit_type_sources"):
        values = report.get(key)
        if not isinstance(values, list):
            continue
        for item in _dict_records(values)[:8]:
            references.append(
                {
                    name: _clip_value(item.get(name))
                    for name in ("kind", "source", "source_sha256")
                    if name in item
                }
            )
    return references[:8]


def _fit_catalog_summary(
    report: dict[str, Any],
    collection: str | None,
    *,
    linked_key: str | None = None,
) -> dict[str, Any]:
    truncation_path_limit = 8
    _refresh_nested_truncation_metadata(
        report,
        path_limit=truncation_path_limit,
    )
    while _encoded_size(report) > SUMMARY_BUDGET_BYTES:
        records = report.get(collection) if collection is not None else None
        if isinstance(records, list) and records:
            records.pop()
            if linked_key is not None:
                linked = report.get(linked_key)
                if isinstance(linked, list) and linked:
                    linked.pop()
            view = _mapping(report.get("view"))
            view["returned_items"] = len(records)
            view["output_truncated"] = True
            report["view"] = view
            catalog = _mapping(report.get("catalog"))
            if catalog:
                catalog["returned_items"] = len(records)
                catalog["output_truncated"] = True
                report["catalog"] = catalog
            _refresh_nested_truncation_metadata(
                report,
                path_limit=truncation_path_limit,
            )
            continue
        if truncation_path_limit > 0:
            truncation_path_limit -= 1
            _refresh_nested_truncation_metadata(
                report,
                path_limit=truncation_path_limit,
            )
            continue
        raise ValueError("summary metadata exceeds the model-context budget")
    return report


def _fit_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    truncation_path_limit = 8
    _refresh_nested_truncation_metadata(
        report,
        path_limit=truncation_path_limit,
    )
    shrink_order = (
        ("reported_warnings", "warnings_truncated"),
        ("reported_failures", "failures_truncated"),
        ("reported_hashes", "hashes_truncated"),
    )
    while _encoded_size(report) > SUMMARY_BUDGET_BYTES:
        changed = False
        for key, truncated_key in shrink_order:
            values = report.get(key)
            if isinstance(values, list) and values:
                values.pop()
                report["view"][truncated_key] = True
                changed = True
                _refresh_nested_truncation_metadata(
                    report,
                    path_limit=truncation_path_limit,
                )
                break
        if changed:
            continue
        if truncation_path_limit > 0:
            truncation_path_limit -= 1
            _refresh_nested_truncation_metadata(
                report,
                path_limit=truncation_path_limit,
            )
            continue
        raise ValueError("report summary metadata exceeds the context budget")
    return report


def _encoded_size(value: object) -> int:
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
    # ``sys.stdout`` uses CRLF translation on Windows.  Budget the larger
    # representation so the process byte stream, not merely ``json.dumps``,
    # remains bounded on every supported host.
    return len(text.replace("\n", "\r\n").encode("utf-8"))


def _validate_search(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("--search must not be empty")
    if len(value) > MAX_SUMMARY_TEXT:
        raise ValueError("--search is too long")
    return value


def _validate_preset(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or not value.strip():
        raise ValueError("--preset must not be empty")
    if len(value) > MAX_SUMMARY_TEXT:
        raise ValueError("--preset is too long")
    return value


def _validate_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_VIEW_LIMIT
    ):
        raise ValueError(f"--limit must be an integer from 1 to {MAX_VIEW_LIMIT}")
    return value


def _records(report: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return _dict_records(report.get(key))


def _dict_records(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coverage_int(report: dict[str, Any], key: str, fallback: int) -> int:
    value = _mapping(report.get("coverage")).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _terrain_query_is_exact(report: dict[str, Any]) -> bool:
    filters = report.get("filters")
    if isinstance(filters, dict) and "terrain" in filters:
        return filters["terrain"] is not None
    # Some older/minimal reports did not echo filters.  In those reports a
    # boolean exact-query verdict is the only available scope signal.
    return isinstance(
        _mapping(report.get("coverage")).get("exact_query_usable"),
        bool,
    )


def _search_records(
    records: list[dict[str, Any]],
    search: str | None,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if search is None:
        return records
    term = search.casefold()
    return [
        item
        for item in records
        if any(term in text.casefold() for text in _field_texts(item, fields))
    ]


def _field_texts(
    item: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    output: list[str] = []
    for field in fields:
        if field == "CLSID" and "pylons" in item:
            for pylon in _dict_records(item.get("pylons")):
                value = pylon.get("CLSID")
                if _is_scalar(value):
                    output.append(str(value))
            continue
        value = item.get(field)
        if isinstance(value, list):
            output.extend(str(entry) for entry in value if _is_scalar(entry))
        elif _is_scalar(value):
            output.append(str(value))
    return output


def _search_match(
    search: str | None,
    selected: list[dict[str, Any]],
) -> bool | None:
    return bool(selected) if search is not None else None


def _apply_explicit_limit(
    records: list[dict[str, Any]],
    limit: int | None,
) -> list[dict[str, Any]]:
    return records if limit is None else records[:limit]


def _clip_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {_clip_text(str(key)): _clip_value(item) for key, item in value.items()}


def _clip_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _clip_text(value)
    if _is_scalar(value):
        return value
    if depth >= 3:
        if isinstance(value, (list, dict)):
            if not value:
                return [] if isinstance(value, list) else {}
            return _ClippedDict(
                {"omitted_items": len(value)},
                total_items=len(value),
                returned_items=0,
            )
        return None
    if isinstance(value, list):
        clipped = [_clip_value(item, depth=depth + 1) for item in value[:20]]
        if len(value) > len(clipped):
            return _ClippedList(
                clipped,
                total_items=len(value),
                returned_items=len(clipped),
            )
        return clipped
    if isinstance(value, dict):
        clipped_mapping = {
            _clip_text(str(key)): _clip_value(item, depth=depth + 1)
            for key, item in list(value.items())[:20]
        }
        if len(value) > len(clipped_mapping):
            return _ClippedDict(
                clipped_mapping,
                total_items=len(value),
                returned_items=len(clipped_mapping),
            )
        return clipped_mapping
    return _clip_text(str(value))


def _refresh_nested_truncation_metadata(
    report: dict[str, Any],
    *,
    path_limit: int,
) -> None:
    view = _mapping(report.get("view"))
    for key in (
        "nested_output_truncated",
        "nested_truncation_count",
        "nested_truncations",
        "nested_truncation_paths_truncated",
    ):
        view.pop(key, None)
    records, total = _nested_truncations(
        {key: value for key, value in report.items() if key != "view"},
        limit=path_limit,
    )
    if total:
        view["output_truncated"] = True
        view["nested_output_truncated"] = True
        view["nested_truncation_count"] = total
        if records:
            view["nested_truncations"] = records
        view["nested_truncation_paths_truncated"] = total > len(records)
    report["view"] = view


def _nested_truncations(
    value: Any,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    total = 0

    def visit(item: Any, path: str) -> None:
        nonlocal total
        if isinstance(item, _ClippedText):
            total += 1
            if len(records) < limit:
                records.append(
                    {
                        "path": _clip_text(path),
                        "total_characters": item.total_characters,
                        "returned_characters": item.returned_characters,
                        "omitted_characters": (
                            item.total_characters - item.returned_characters
                        ),
                    }
                )
        elif isinstance(item, (_ClippedList, _ClippedDict)):
            total += 1
            if len(records) < limit:
                records.append(
                    {
                        "path": _clip_text(path),
                        "total_items": item.total_items,
                        "returned_items": item.returned_items,
                        "omitted_items": (item.total_items - item.returned_items),
                    }
                )
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, _ClippedText):
                    visit(key, f"{path}.<key>")
                visit(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, "$")
    return records, total


def _clip_text(value: str) -> str:
    if len(value) <= MAX_SUMMARY_TEXT:
        return value
    clipped = value[: MAX_SUMMARY_TEXT - 1] + "…"
    return _ClippedText(
        clipped,
        total_characters=len(value),
        returned_characters=len(clipped),
    )


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _read_bounded_report(path: Path) -> bytes:
    try:
        path_status = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("report file does not exist") from error
    _validate_report_file_status(path_status)
    flags = os.O_RDONLY
    for name in ("O_BINARY", "O_CLOEXEC", "O_NOINHERIT", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise ValueError("report file changed while it was being opened") from error
    try:
        opened_status = os.fstat(descriptor)
        _validate_report_file_status(opened_status)
        if _file_identity(path_status) != _file_identity(opened_status):
            raise ValueError("report file changed while it was being opened")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_REPORT_INPUT_BYTES + 1)
            final_status = os.fstat(descriptor)
        _validate_report_file_status(final_status)
        if _file_identity(opened_status) != _file_identity(
            final_status
        ) or _file_version(opened_status) != _file_version(final_status):
            raise ValueError("report file changed while it was being read")
        try:
            final_path_status = path.lstat()
        except FileNotFoundError as error:
            raise ValueError("report file changed while it was being read") from error
        _validate_report_file_status(final_path_status)
        if _file_identity(opened_status) != _file_identity(final_path_status):
            raise ValueError("report file changed while it was being read")
    finally:
        os.close(descriptor)
    if len(raw) > MAX_REPORT_INPUT_BYTES:
        raise ValueError("report file exceeds the JSON size limit")
    if len(raw) != final_status.st_size:
        raise ValueError("report file changed while it was being read")
    if not raw:
        raise ValueError("report file is empty")
    _validate_json_depth(raw)
    return raw


def _validate_report_file_status(status: os.stat_result) -> None:
    if stat.S_ISLNK(status.st_mode) or _status_is_reparse_point(status):
        raise ValueError("report file must not be a symbolic link or reparse point")
    if not stat.S_ISREG(status.st_mode):
        raise ValueError("report path is not a regular file")
    if status.st_size > MAX_REPORT_INPUT_BYTES:
        raise ValueError("report file exceeds the JSON size limit")


def _status_is_reparse_point(status: os.stat_result) -> bool:
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _file_identity(status: os.stat_result) -> tuple[int, int]:
    return status.st_dev, status.st_ino


def _file_version(status: os.stat_result) -> tuple[int, int, int]:
    return status.st_size, status.st_mtime_ns, status.st_ctime_ns


def _validate_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
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
        elif byte in (0x7B, 0x5B):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("report JSON exceeds the nesting-depth limit")
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                break


def _parse_report_json(raw: bytes) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number is not allowed")
        return parsed

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("report JSON contains duplicate object keys")
            output[key] = value
        return output

    try:
        parsed = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("report file is not valid bounded UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError("report JSON root must be an object")
    return parsed


def _validation_summary(report: dict[str, Any]) -> dict[str, Any]:
    validation = _mapping(report.get("validation"))
    output = {
        str(key): _clip_value(value)
        for key, value in validation.items()
        if _is_scalar(value)
    }
    structure = _mapping(report.get("limited_structure"))
    if structure:
        output["limited_structure"] = {
            key: structure.get(key)
            for key in ("valid", "error_count", "warning_count")
            if key in structure
        }
    contract = _mapping(report.get("contract"))
    if contract:
        output["contract"] = {
            "checks": len(_list(contract.get("checks"))),
            "coverage_warning_count": contract.get(
                "coverage_warning_count",
                len(_list(contract.get("coverage_warnings"))),
            ),
        }
    return output


def _report_status(
    schema: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    if schema == "dcsmizzer.miz-inspection/v1":
        basis = "archive_valid_and_parse_valid"
        archive_valid = validation.get("archive_valid")
        parse_valid = validation.get("parse_valid")
        passed = (
            archive_valid and parse_valid
            if isinstance(archive_valid, bool) and isinstance(parse_valid, bool)
            else None
        )
    else:
        verdict_keys = {
            "dcsmizzer.miz-build/v1": "available_checks_passed",
            "dcsmizzer.miz-verification/v1": "available_checks_passed",
            "dcsmizzer.build-spec-evidence-audit/v1": "evidence_consistent",
            "dcsmizzer.cmp-inspection/v1": "static_reference_valid",
            "dcsmizzer.dcs-coordinate-conversion/v1": "validated",
            "dcsmizzer.br-coordinate-conversion/v1": "validated",
            "dcsmizzer.terrain-point/v1": "evidence_usable",
            "dcsmizzer.terrain-placement/v1": "sampled_placement_valid",
            "dcsmizzer.terrain-corridor/v1": "sampled_corridor_clear",
            "dcsmizzer.terrain-landmarks/v1": "exact_query_usable",
            "dcsmizzer.airfield-footprint/v1": "exact_airfield_usable",
            "dcsmizzer.br-airfield-footprint/v1": "planning_footprint_usable",
        }
        basis = verdict_keys.get(schema)
        value = validation.get(basis) if basis is not None else None
        passed = value if isinstance(value, bool) else None
    return {
        "passed": passed,
        "basis": basis,
        "runtime_valid": validation.get("runtime_valid"),
    }


def _report_identity(report: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in (
        "artifact",
        "input",
        "input_spec",
        "kind",
        "unit_type",
        "quality_profile",
        "path_scope",
        "input_spec_path_scope",
    ):
        value = report.get(key)
        if value is not None and _is_scalar(value):
            output[key] = _clip_value(value)
    quality = _mapping(report.get("quality"))
    if "profile" in quality:
        output["quality_profile"] = _clip_value(quality["profile"])
    return output


def _runtime_performed(report: dict[str, Any]) -> bool:
    validation = _mapping(report.get("validation"))
    return validation.get("runtime_valid") is not None


def _report_hashes(
    report: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    found: list[dict[str, str]] = []
    found_count = 0

    def visit(value: Any, path: str, depth: int) -> None:
        nonlocal found_count
        if depth > MAX_REPORT_HASH_DEPTH:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if (
                    isinstance(child, str)
                    and (
                        str(key).casefold() == "sha256"
                        or str(key).casefold().endswith("_sha256")
                    )
                    and _valid_hash(child)
                ):
                    found_count += 1
                    if len(found) < MAX_REPORT_HASHES:
                        found.append(
                            {
                                "field": _clip_text(child_path),
                                "sha256": child.lower(),
                            }
                        )
                else:
                    visit(child, child_path, depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]", depth + 1)

    visit(report, "", 0)
    found.sort(key=lambda item: (item["field"], item["sha256"]))
    return found, found_count


def _report_issues(
    report: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    int,
    list[dict[str, Any]],
    int,
]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failure_keys: set[tuple[str, str, str]] = set()
    warning_keys: set[tuple[str, str, str]] = set()
    failure_count = 0
    warning_count = 0

    def add(value: Any, path: str, *, warning: bool = False) -> None:
        nonlocal failure_count, warning_count
        target = warnings if warning else failures
        seen = warning_keys if warning else failure_keys
        if warning:
            warning_count += 1
        else:
            failure_count += 1
        if len(target) >= MAX_REPORT_ISSUES:
            return
        if isinstance(value, str):
            issue = {"code": _clip_text(value), "path": path}
        elif not isinstance(value, dict):
            issue = {"code": _clip_text(str(value)), "path": path}
        else:
            code = next(
                (
                    value.get(key)
                    for key in ("code", "id", "name", "check", "message")
                    if _is_scalar(value.get(key))
                ),
                "unspecified",
            )
            issue = {
                "code": _clip_text(str(code)),
                "path": _clip_text(str(value.get("path", value.get("field", path)))),
            }
            severity = value.get("severity")
            if severity is not None and _is_scalar(severity):
                issue["severity"] = _clip_value(severity)
        issue_key = (
            str(issue.get("code")),
            str(issue.get("path")),
            str(issue.get("severity")),
        )
        if issue_key not in seen:
            seen.add(issue_key)
            target.append(issue)

    for index, check in enumerate(_dict_records(report.get("checks"))):
        if check.get("passed") is False:
            add(check, f"checks[{index}]")
    contract = _mapping(report.get("contract"))
    for index, check in enumerate(_dict_records(contract.get("checks"))):
        if check.get("passed") is False:
            add(check, f"contract.checks[{index}]")
    for index, value in enumerate(_list(contract.get("coverage_warnings"))):
        add(value, f"contract.coverage_warnings[{index}]", warning=True)

    structure = _mapping(report.get("limited_structure"))
    for index, diagnostic in enumerate(_dict_records(structure.get("diagnostics"))):
        add(
            diagnostic,
            f"limited_structure.diagnostics[{index}]",
            warning=diagnostic.get("severity") == "warning",
        )
    archive = _mapping(report.get("archive"))
    for index, diagnostic in enumerate(_dict_records(archive.get("diagnostics"))):
        add(
            diagnostic,
            f"archive.diagnostics[{index}]",
            warning=diagnostic.get("severity") == "warning",
        )
    for index, value in enumerate(_list(report.get("warnings"))):
        add(value, f"warnings[{index}]", warning=True)
    for mapping_name in ("core_table_errors", "resource_errors"):
        for key, value in _mapping(report.get(mapping_name)).items():
            add(value, f"{mapping_name}.{key}")
    validation = _mapping(report.get("validation"))
    failure_reasons = validation.get("failure_reasons")
    reasons_added = 0
    if isinstance(failure_reasons, list):
        for index, value in enumerate(failure_reasons):
            add(value, f"validation.failure_reasons[{index}]")
            reasons_added += 1
    elif failure_reasons is not None:
        add(failure_reasons, "validation.failure_reasons")
        reasons_added = 1
    if validation.get("validated") is False and reasons_added == 0:
        add(
            {
                "code": "validation_validated_false",
                "path": "validation.validated",
            },
            "validation.validated",
        )
    for key, value in validation.items():
        if value is False and (
            key.endswith(("_valid", "_passed", "_complete"))
            or key
            in {
                "crc_verified",
                "all_core_tables_parsed",
                "all_core_tables_equal",
                "exact_member_set",
                "theatre_member_matches",
                "expected_resources_present",
                "all_resources_equal",
            }
        ):
            add(
                {"code": f"validation_{key}_false", "path": f"validation.{key}"},
                f"validation.{key}",
            )
        elif key == "archive_content_read_blocked" and value is True:
            add(
                {
                    "code": "archive_content_read_blocked",
                    "path": "validation.archive_content_read_blocked",
                },
                "validation.archive_content_read_blocked",
            )
    return failures, failure_count, warnings, warning_count
