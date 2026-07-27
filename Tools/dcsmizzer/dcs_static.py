from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .lua import LuaDataError, LuaField, LuaTable, parse_lua_bytes


_COUNTRY_EVENT = re.compile(
    r"""\bcountry\s*:\s*
    (?:
        (?P<add>add)\s*\(\s*
        (?P<quote>['"])(?P<key>.*?)(?P=quote)
        |
        (?P<next>next)\s*\(
    )
    """,
    re.DOTALL | re.VERBOSE,
)
_COUNTRY_NEXT_INDEX_ZERO = re.compile(r"\bnext_index\s*=\s*0\b")
_COUNTRY_ADD_CALL = re.compile(r"\bcountry\s*:\s*add\s*\(")
_STATE = re.compile(r"""\bstate\s*=\s*(['"])(.*?)\1""")
_SELF_ID = re.compile(
    r"""\blocal\s+self_ID\s*=\s*(['"])(.*?)\1"""
)
_BEACON_BLOCK = re.compile(
    r"^[ \t]*\{[ \t]*\r?\n(?P<body>.*?)^[ \t]*\};[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_AIRFIELD_BEACON_ID = re.compile(
    r"""\bbeaconId\s*=\s*(['"])airfield(?P<id>\d+)_(?P<index>[^'"]+)\1"""
)
_AIRFIELD_RADIO_ID = re.compile(
    r"""\bradioId\s*=\s*(['"])airfield(?P<id>\d+)_(?P<index>[^'"]+)\1"""
)
_RADIO_NAME_COMMENT = re.compile(
    r"^[ \t]*--[ \t]*(?P<name>[^\r\n]+?)[ \t]*$",
    re.MULTILINE,
)
_RADIO_CALLSIGN = re.compile(
    r"""\bcallsign\s*=.*?_\(\s*(['"])(?P<value>.*?)\1\s*\)""",
    re.DOTALL,
)
_DISPLAY_NAME = re.compile(
    r"""\bdisplay_name\s*=\s*_\(\s*(['"])(?P<value>.*?)\1\s*\)""",
    re.DOTALL,
)
_NUMBER_TEXT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_POSITION = re.compile(
    rf"""\bposition\s*=\s*\{{\s*
    (?P<x>{_NUMBER_TEXT})\s*,\s*
    (?P<elevation>{_NUMBER_TEXT})\s*,\s*
    (?P<z>{_NUMBER_TEXT})\s*
    \}}""",
    re.VERBOSE,
)
_POSITION_GEO = re.compile(
    rf"""\bpositionGeo\s*=\s*\{{\s*
    latitude\s*=\s*(?P<latitude>{_NUMBER_TEXT})\s*,\s*
    longitude\s*=\s*(?P<longitude>{_NUMBER_TEXT})\s*
    \}}""",
    re.VERBOSE,
)
_BEACON_TYPE = re.compile(r"\btype\s*=\s*(?P<value>BEACON_TYPE_[A-Z0-9_]+)")
_QUOTED_FIELD_TEMPLATE = (
    r"""\b{field}\s*=\s*(['"])(?P<value>.*?)\1"""
)
_NUMERIC_FIELD_TEMPLATE = (
    rf"""\b{{field}}\s*=\s*(?P<value>{_NUMBER_TEXT})"""
)
_TASK_CONSTANT = re.compile(
    r"^\s*local\s+(?P<name>t[A-Za-z0-9_]+)\s*=\s*(?P<value>\d+)\s*$",
    re.MULTILINE,
)
_TASK_COMMENT_CONSTANT = re.compile(
    r'^\s*"(?P<name>[A-Za-z0-9_]+)"\s*=\s*(?P<value>\d+)\s*$',
    re.MULTILINE,
)
_TASK_ALIASES: dict[str, str] = {
    "Intercept": "tIntercept",
    "CAP": "tCAP",
    "AFAC": "tAFAC",
    "Reconnaissance": "tRecon",
    "Escort": "tEscort",
    "FighterSweep": "tFighterSweep",
    "SEAD": "tSEAD",
    "AntishipStrike": "tAntiShip",
    "CAS": "tCAS",
    "GroundAttack": "tGndAttack",
    "PinpointStrike": "tPinpntStrike",
    "RunwayAttack": "tRwyAttack",
}
_NUMERIC_MULTI_ASSIGNMENT = re.compile(
    rf"""^(?P<indent>[ \t]*)local\s+
    (?P<names>[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)+)
    \s*=\s*
    (?P<values>{_NUMBER_TEXT}(?:\s*,\s*{_NUMBER_TEXT})+)
    [ \t]*\r?$""",
    re.MULTILINE | re.VERBOSE,
)
_ENTRY_LITERAL_ASSIGNMENT = re.compile(
    r"""^(?![ \t]*--)[ \t]*(?:local[ \t]+)?
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*
    (?P<quote>['"])(?P<value>.*?)(?P=quote)
    [ \t]*(?:--.*)?$""",
    re.MULTILINE | re.VERBOSE,
)
_ENTRY_IDENTIFIER_CALL = re.compile(
    r"""^(?![ \t]*--)[ \t]*
    (?P<call>declare_plugin|make_flyable)[ \t]*\(\s*
    (?:
        (?P<quote>['"])(?P<literal>.*?)(?P=quote)
        |
        (?P<identifier>[A-Za-z_][A-Za-z0-9_]*)
    )(?=\s*[,)])""",
    re.MULTILINE | re.VERBOSE,
)
_ENTRY_CALL_HEAD = re.compile(
    r"^(?![ \t]*--)[ \t]*(?P<call>declare_plugin|make_flyable)[ \t]*\(",
    re.MULTILINE,
)
_SERVICE_LIFE_CALL = re.compile(
    r"""declare_service_life[ \t]*\([ \t]*
    (?P<unit_quote>['"])(?P<unit>.*?)(?P=unit_quote)[ \t]*,[ \t]*
    (?P<country_quote>['"])(?P<country>.*?)(?P=country_quote)[ \t]*,[ \t]*
    (?P<start>\d+)[ \t]*,[ \t]*(?P<end>\d+)[ \t]*\)""",
    re.VERBOSE,
)
_PAYLOAD_FINGERPRINT_SCHEMA = "dcsmizzer.payload-fingerprint/v1"
_MAX_PAYLOAD_ASSIGNMENTS = 128
_MAX_PAYLOAD_TASKS = 128
_MAX_PAYLOAD_MATCHES = 100
_MAX_PAYLOAD_SOURCE_EXAMPLES = 32
_MAX_PAYLOAD_SOURCE_FILES = 2048
_MAX_PAYLOAD_SOURCE_BYTES = 512 * 1024
_MAX_PAIR_OBSERVATIONS = 5
_MAX_PAYLOAD_SETTINGS_BYTES = 64 * 1024
_MAX_STORE_SETTINGS_BYTES = 16 * 1024
_PAYLOAD_PRESET_FIELDS = {
    "name",
    "displayName",
    "category",
    "pylons",
    "tasks",
}


def countries_report(dcs_root: Path) -> dict[str, Any]:
    path = dcs_root / "Scripts" / "Database" / "db_countries.lua"
    if not path.is_file():
        raise ValueError("DCS country source is missing")
    text = path.read_text(encoding="utf-8-sig")
    if _COUNTRY_NEXT_INDEX_ZERO.search(text) is None:
        raise ValueError("DCS country ID origin could not be verified")
    entries: list[dict[str, int | str]] = []
    reserved_ids: list[int] = []
    next_index = 0
    for match in _COUNTRY_EVENT.finditer(text):
        if match.group("next") is not None:
            reserved_ids.append(next_index)
        else:
            entries.append(
                {
                    "id": next_index,
                    "identifier": match.group("key"),
                }
            )
        next_index += 1
    if len(entries) != len(_COUNTRY_ADD_CALL.findall(text)):
        raise ValueError("not every DCS country:add call has a literal identifier")
    identifiers = [str(entry["identifier"]) for entry in entries]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if count > 1
    )
    return {
        "schema": "dcsmizzer.dcs-countries/v1",
        "authority": "current_install_static_source",
        "source": "Scripts/Database/db_countries.lua",
        "source_sha256": _sha256(path),
        "dcs_started": False,
        "count": len(set(identifiers)),
        "identifiers": identifiers,
        "entries": entries,
        "reserved_ids": reserved_ids,
        "id_derivation": (
            "Parsed source order from verified next_index = 0; each "
            "country:add or explicit country:next call consumes the next ID."
        ),
        "duplicate_identifiers": duplicates,
    }


def payload_fingerprint(
    unit_type: str,
    pylons: Mapping[int | float, str] | Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[int | float] = (),
    preset_name: str | None = None,
    display_name: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Normalize and fingerprint one complete payload without DCS execution."""

    unit_issue = _payload_text_issue(
        unit_type,
        field="unit_type",
        required=True,
        max_length=512,
    )
    pylon_records, pylon_issues = _payload_assignment_analysis(pylons)
    normalized_tasks, task_issues = _payload_task_analysis(tasks)
    metadata_issues = [
        issue
        for issue in (
            _payload_text_issue(
                preset_name,
                field="preset_name",
                required=False,
                max_length=4096,
            ),
            _payload_text_issue(
                display_name,
                field="display_name",
                required=False,
                max_length=4096,
            ),
            _payload_text_issue(
                category,
                field="category",
                required=False,
                max_length=4096,
            ),
        )
        if issue is not None
    ]
    issues = (
        ([unit_issue] if unit_issue is not None else [])
        + pylon_issues
        + task_issues
        + metadata_issues
    )
    if issues:
        codes = ", ".join(str(issue["code"]) for issue in issues)
        raise ValueError(f"invalid payload fingerprint input: {codes}")
    normalized = {
        "unit_type": unit_type,
        "pylons": pylon_records,
        "tasks": normalized_tasks,
        "preset_name": preset_name,
        "display_name": display_name,
        "category": category,
    }
    composition = {
        "schema": _PAYLOAD_FINGERPRINT_SCHEMA,
        "kind": "composition",
        "unit_type": unit_type,
        "pylons": [
            {
                "num": pylon["num"],
                "CLSID": pylon["CLSID"],
            }
            for pylon in pylon_records
        ],
    }
    configured_composition = {
        "schema": _PAYLOAD_FINGERPRINT_SCHEMA,
        "kind": "configured_composition",
        "unit_type": unit_type,
        "pylons": pylon_records,
    }
    preset = {
        "schema": _PAYLOAD_FINGERPRINT_SCHEMA,
        "kind": "preset",
        **normalized,
    }
    return {
        "schema": _PAYLOAD_FINGERPRINT_SCHEMA,
        "normalization": _payload_fingerprint_rules(),
        "normalized": normalized,
        "composition_sha256": _json_sha256(composition),
        "configured_composition_sha256": _json_sha256(
            configured_composition
        ),
        "preset_sha256": _json_sha256(preset),
    }


def payload_match_report(
    dcs_root: Path,
    unit_type: str,
    pylons: Mapping[int | float, str] | Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[int | float] | None = None,
    preset_name: str | None = None,
    display_name: str | None = None,
    category: str | None = None,
    match_limit: int = 20,
) -> dict[str, Any]:
    """Compare a whole payload with current installed default-preset evidence."""

    if (
        not isinstance(unit_type, str)
        or not unit_type.strip()
        or len(unit_type) > 512
    ):
        raise ValueError(
            "unit_type must be a nonempty string of at most 512 characters"
        )
    for field, value in (
        ("preset_name", preset_name),
        ("display_name", display_name),
        ("category", category),
    ):
        if value is not None and (
            not isinstance(value, str) or len(value) > 4096
        ):
            raise ValueError(
                f"{field} must be null or a string of at most 4096 characters"
            )
    if (
        not isinstance(match_limit, int)
        or isinstance(match_limit, bool)
        or not 1 <= match_limit <= _MAX_PAYLOAD_MATCHES
    ):
        raise ValueError(
            f"match_limit must be from 1 to {_MAX_PAYLOAD_MATCHES}"
        )

    pylon_records, pylon_issues = _payload_assignment_analysis(pylons)
    normalized_tasks, task_issues = _payload_task_analysis(
        () if tasks is None else tasks
    )
    unit_issue = _payload_text_issue(
        unit_type,
        field="unit_type",
        required=True,
        max_length=512,
    )
    metadata_issues = [
        issue
        for issue in (
            _payload_text_issue(
                preset_name,
                field="preset_name",
                required=False,
                max_length=4096,
            ),
            _payload_text_issue(
                display_name,
                field="display_name",
                required=False,
                max_length=4096,
            ),
            _payload_text_issue(
                category,
                field="category",
                required=False,
                max_length=4096,
            ),
        )
        if issue is not None
    ]
    query_issues = (
        ([unit_issue] if unit_issue is not None else [])
        + pylon_issues
        + task_issues
        + metadata_issues
    )
    query_fingerprints: dict[str, Any] | None = None
    if not query_issues:
        query_fingerprints = payload_fingerprint(
            unit_type,
            pylon_records,
            tasks=normalized_tasks,
            preset_name=preset_name,
            display_name=display_name,
            category=category,
        )

    static_report = payload_report(dcs_root, unit_type)
    valid_presets = [
        preset
        for preset in static_report["presets"]
        if preset["integrity"]["valid"]
    ]
    metadata_filters = {
        "tasks": tasks is not None,
        "preset_name": preset_name is not None,
        "display_name": display_name is not None,
        "category": category is not None,
    }
    composition_candidates: list[dict[str, Any]] = []
    configuration_candidates: list[dict[str, Any]] = []
    exact_matches: list[dict[str, Any]] = []
    configuration_gap_records: list[tuple[dict[str, Any], list[int]]] = []
    pair_evidence: list[dict[str, Any]] = []
    unknown_pairs: list[dict[str, Any]] = []

    if query_fingerprints is not None:
        composition_sha256 = query_fingerprints["composition_sha256"]
        composition_candidates = [
            preset
            for preset in valid_presets
            if preset["fingerprints"]["composition_sha256"]
            == composition_sha256
        ]
        configuration_records = []
        for preset in composition_candidates:
            mismatch, unspecified_stations = _payload_configuration_relation(
                pylon_records,
                preset["pylons"],
            )
            if not mismatch:
                configuration_candidates.append(preset)
                configuration_records.append(
                    (preset, unspecified_stations)
                )
        metadata_records = [
            (preset, unspecified_stations)
            for preset, unspecified_stations in configuration_records
            if (
                (tasks is None or preset["tasks"] == normalized_tasks)
                and (
                    preset_name is None
                    or preset["name"] == preset_name
                )
                and (
                    display_name is None
                    or preset["display_name"] == display_name
                )
                and (
                    category is None
                    or preset["category"] == category
                )
            )
        ]
        exact_matches = [
            preset
            for preset, unspecified_stations in metadata_records
            if not unspecified_stations
        ]
        configuration_gap_records = [
            (preset, unspecified_stations)
            for preset, unspecified_stations in metadata_records
            if unspecified_stations
        ]
        pair_index = _payload_pair_index(valid_presets)
        for assignment in pylon_records:
            key = (assignment["num"], assignment["CLSID"])
            observations = pair_index.get(key, [])
            evidence = {
                **assignment,
                "observed": bool(observations),
                "observation_count": len(observations),
                "observations": observations[:_MAX_PAIR_OBSERVATIONS],
                "observations_truncated": (
                    len(observations) > _MAX_PAIR_OBSERVATIONS
                ),
            }
            pair_evidence.append(evidence)
            if not observations:
                unknown_pairs.append(dict(assignment))

    source_records = static_report["unit_type_sources"]
    parse_failure_sources = static_report["parse_failure_sources"]
    relevant_parse_failures = static_report[
        "unit_type_parse_failure_sources"
    ]
    source_binding = static_report["source_binding"]
    candidate_enumeration_complete = (
        source_binding.get("candidate_enumeration_complete") is True
    )

    if any(
        issue["code"] == "duplicate_station" for issue in query_issues
    ):
        classification = "duplicate_station"
    elif query_issues:
        classification = "invalid_query"
    elif not candidate_enumeration_complete:
        classification = "source_evidence_incomplete"
    elif not static_report["unit_type_sources"]:
        classification = "unit_type_not_observed"
    elif not valid_presets:
        classification = "source_evidence_invalid"
    elif len(exact_matches) > 1:
        classification = "ambiguous_observed_preset"
    elif len(exact_matches) == 1:
        classification = "exact_observed_preset"
    elif configuration_gap_records:
        classification = "observed_composition_configuration_unspecified"
    elif composition_candidates and not configuration_candidates:
        classification = "observed_composition_configuration_mismatch"
    elif composition_candidates and any(metadata_filters.values()):
        classification = "observed_composition_metadata_mismatch"
    elif unknown_pairs:
        classification = "unknown_pair"
    else:
        classification = "custom_composition_only"

    invalid_examples = [
        _payload_preset_reference(preset, include_integrity=True)
        for preset in static_report["presets"]
        if not preset["integrity"]["valid"]
    ]
    matches = [
        _payload_preset_reference(preset)
        for preset in exact_matches[:match_limit]
    ]
    query: dict[str, Any] = {
        "valid": not query_issues,
        "issues": query_issues,
        "metadata_filters": metadata_filters,
        "normalized": {
            "unit_type": unit_type,
            "pylons": pylon_records,
            "tasks": normalized_tasks if tasks is not None else None,
            "preset_name": preset_name,
            "display_name": display_name,
            "category": category,
        },
    }
    if query_fingerprints is not None:
        query["fingerprints"] = {
            "schema": query_fingerprints["schema"],
            "composition_sha256": query_fingerprints[
                "composition_sha256"
            ],
            "configured_composition_sha256": query_fingerprints[
                "configured_composition_sha256"
            ],
            "query_preset_sha256": query_fingerprints["preset_sha256"],
        }
    return {
        "schema": "dcsmizzer.dcs-payload-match/v1",
        "authority": "current_install_static_default_presets",
        "dcs_started": False,
        "dcs": static_report["dcs"],
        "unit_type": unit_type,
        "fingerprint_normalization": static_report[
            "fingerprint_normalization"
        ],
        "classification": classification,
        "verified_exact_observed_preset": (
            classification == "exact_observed_preset"
        ),
        "query": query,
        "exact_composition_candidate_count": len(composition_candidates),
        "configuration_candidate_count": len(configuration_candidates),
        "configuration_gap_candidate_count": len(
            configuration_gap_records
        ),
        "exact_match_count": len(exact_matches),
        "configuration_unspecified_stations": sorted(
            {
                station
                for _preset, gaps in configuration_gap_records
                for station in gaps
            }
        )
        if not exact_matches
        else [],
        "matches": matches,
        "matches_truncated": len(exact_matches) > match_limit,
        "pair_evidence": pair_evidence,
        "unknown_pairs": unknown_pairs,
        "source_binding": {
            **source_binding,
            "unit_type_sources": source_records[
                :_MAX_PAYLOAD_SOURCE_EXAMPLES
            ],
            "unit_type_sources_truncated": (
                len(source_records) > _MAX_PAYLOAD_SOURCE_EXAMPLES
            ),
            "parse_failure_count": len(parse_failure_sources),
            "relevant_parse_failure_count": len(
                relevant_parse_failures
            ),
            "candidate_enumeration_complete": (
                candidate_enumeration_complete
            ),
            "parse_failure_sources": parse_failure_sources[
                :_MAX_PAYLOAD_SOURCE_EXAMPLES
            ],
            "parse_failure_sources_truncated": (
                len(parse_failure_sources) > _MAX_PAYLOAD_SOURCE_EXAMPLES
            ),
            "relevant_parse_failure_sources": (
                relevant_parse_failures[:_MAX_PAYLOAD_SOURCE_EXAMPLES]
            ),
            "relevant_parse_failure_sources_truncated": (
                len(relevant_parse_failures)
                > _MAX_PAYLOAD_SOURCE_EXAMPLES
            ),
        },
        "source_integrity": {
            **static_report["source_integrity"],
            "invalid_preset_examples": invalid_examples[
                :_MAX_PAYLOAD_SOURCE_EXAMPLES
            ],
            "invalid_preset_examples_truncated": (
                len(invalid_examples) > _MAX_PAYLOAD_SOURCE_EXAMPLES
            ),
        },
        "compatibility_complete": False,
        "limitations": [
            "An exact result proves an observed installed default preset, "
            "not every store-to-station combination accepted at runtime.",
            "Installed per-store settings must be supplied and match before "
            "a configured preset is classified as exact.",
            "A custom-composition result only means that every pair appeared "
            "somewhere for this unit; it does not prove the combination.",
            "A parse failure with the queried literal unit-type hint, or "
            "without a safe literal hint, makes candidate enumeration "
            "incomplete even when another source proves an observation.",
            "A malformed payload table or preset for the queried unit type "
            "also makes candidate enumeration incomplete because it could "
            "hide another composition or store configuration.",
            "Payload source discovery and reads are bounded; reparse entries "
            "and source changes fail closed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def payload_report(dcs_root: Path, unit_type: str) -> dict[str, Any]:
    if (
        not isinstance(unit_type, str)
        or not unit_type.strip()
        or len(unit_type) > 512
    ):
        raise ValueError(
            "unit_type must be a nonempty string of at most 512 characters"
        )
    sources = _payload_source_files(dcs_root)
    if not sources:
        raise ValueError("DCS default payload sources are missing")
    task_constants, task_source = _payload_task_constants(dcs_root)
    matches: list[dict[str, Any]] = []
    matching_sources: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []
    source_inventory: list[dict[str, str]] = []
    shadowed_preset_assignments = 0
    invalid_payload_tables = 0
    for relative, path in sources:
        try:
            source_bytes = _read_payload_source(path)
        except OSError as error:
            parse_failures.append(
                _payload_failure_record(relative, error)
            )
            continue
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_inventory.append(
            {
                "source": relative,
                "source_sha256": source_sha256,
            }
        )
        try:
            payload_table = _parse_payload_table(
                source_bytes,
                task_constants,
            )
        except LuaDataError as error:
            parse_failures.append(
                _payload_failure_record(
                    relative,
                    error,
                    source_bytes=source_bytes,
                )
            )
            continue
        if payload_table is None:
            parse_failures.append(
                _payload_failure_record(
                    relative,
                    "missing_payload_table",
                    source_bytes=source_bytes,
                )
            )
            continue
        if payload_table.get("name") != unit_type:
            continue
        matching_sources.append(
            {
                "source": relative,
                "source_sha256": source_sha256,
            }
        )
        payloads = payload_table.get("payloads")
        if not isinstance(payloads, LuaTable):
            invalid_payload_tables += 1
            continue
        preset_fields = _effective_numeric_items(payloads)
        shadowed_preset_assignments += (
            len(payloads.numeric_items()) - len(preset_fields)
        )
        for preset_field in preset_fields:
            if not isinstance(preset_field.value, LuaTable):
                matches.append(
                    {
                        "name": None,
                        "display_name": None,
                        "category": None,
                        "source": relative,
                        "source_sha256": source_sha256,
                        "source_preset_key": preset_field.key,
                        "pylons": [],
                        "tasks": [],
                        "integrity": {
                            "valid": False,
                            "issues": [
                                {
                                    "code": "invalid_preset_record",
                                }
                            ],
                        },
                    }
                )
                continue
            matches.append(
                _payload_preset_record(
                    unit_type,
                    preset_field.value,
                    source=relative,
                    source_sha256=source_sha256,
                    source_preset_key=preset_field.key,
                )
            )
    valid_presets = sum(
        bool(preset["integrity"]["valid"]) for preset in matches
    )
    invalid_presets = len(matches) - valid_presets
    relevant_parse_failures = _payload_failures_for_unit_type(
        parse_failures,
        unit_type,
    )
    return {
        "schema": "dcsmizzer.dcs-default-payloads/v1",
        "authority": "current_install_static_default_presets",
        "dcs_started": False,
        "dcs": _dcs_install_identity(dcs_root),
        "unit_type": unit_type,
        "compatibility_complete": False,
        "compatibility_warning": (
            "Default presets prove observed preset assignments only; they do "
            "not enumerate every store allowed on every station."
        ),
        "fingerprint_normalization": _payload_fingerprint_rules(),
        "source_scope": _payload_source_scope(),
        "task_constant_source": task_source,
        "files_scanned": len(sources),
        "parse_failures": len(parse_failures),
        "parse_failure_sources": parse_failures,
        "unit_type_parse_failure_sources": relevant_parse_failures,
        "unit_type_sources": matching_sources,
        "source_binding": {
            "source_scope": _payload_source_scope(),
            "files_scanned": len(sources),
            "files_hashed": len(source_inventory),
            "source_inventory_complete": (
                len(source_inventory) == len(sources)
            ),
            "candidate_enumeration_complete": bool(
                len(source_inventory) == len(sources)
                and not relevant_parse_failures
                and invalid_payload_tables == 0
                and invalid_presets == 0
            ),
            "candidate_enumeration_scope": (
                "semantically valid queried unit-type tables/presets plus "
                "failures without a safe literal unit-type hint"
            ),
            "unit_type_invalid_payload_tables": invalid_payload_tables,
            "unit_type_invalid_presets": invalid_presets,
            "payload_inventory_sha256": _json_sha256(source_inventory),
            "task_constant_source": task_source,
        },
        "source_integrity": {
            "presets_seen": len(matches),
            "valid_presets": valid_presets,
            "invalid_presets": invalid_presets,
            "invalid_payload_tables": invalid_payload_tables,
            "shadowed_preset_table_assignments": (
                shadowed_preset_assignments
            ),
        },
        "presets": matches,
    }


def payload_index_report(dcs_root: Path) -> dict[str, Any]:
    """Index every data-only default UnitPayload table in known install roots."""

    sources = _payload_source_files(dcs_root)
    if not sources:
        raise ValueError("DCS default payload sources are missing")
    task_constants, task_source = _payload_task_constants(dcs_root)
    parse_failures: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    all_clsids: set[str] = set()
    all_tasks: set[int | float] = set()
    shadowed_preset_assignments = 0
    shadowed_pylon_assignments = 0
    shadowed_task_assignments = 0
    for relative, path in sources:
        try:
            source_bytes = _read_payload_source(path)
        except OSError as error:
            parse_failures.append(
                _payload_failure_record(relative, error)
            )
            continue
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        try:
            payload_table = _parse_payload_table(
                source_bytes,
                task_constants,
            )
        except LuaDataError as error:
            parse_failures.append(
                _payload_failure_record(
                    relative,
                    error,
                    source_bytes=source_bytes,
                )
            )
            continue
        if payload_table is None:
            parse_failures.append(
                _payload_failure_record(
                    relative,
                    "missing_payload_table",
                    source_bytes=source_bytes,
                )
            )
            continue
        unit_type = payload_table.get("name")
        if not isinstance(unit_type, str):
            parse_failures.append(
                _payload_failure_record(
                    relative,
                    "missing_unit_type",
                    source_bytes=source_bytes,
                )
            )
            continue
        payloads_table = _table(payload_table.get("payloads"))
        shadowed_preset_assignments += (
            len(payloads_table.numeric_items())
            - len(_effective_numeric_items(payloads_table))
        )
        presets = _numeric_tables(payloads_table)
        clsids: set[str] = set()
        tasks: set[int | float] = set()
        pylon_assignments = 0
        for preset in presets:
            pylon_table = _table(preset.get("pylons"))
            shadowed_pylon_assignments += (
                len(pylon_table.numeric_items())
                - len(_effective_numeric_items(pylon_table))
            )
            for pylon in _numeric_tables(pylon_table):
                pylon_assignments += 1
                clsid = pylon.get("CLSID")
                if isinstance(clsid, str):
                    clsids.add(clsid)
                    all_clsids.add(clsid)
            task_table = _table(preset.get("tasks"))
            shadowed_task_assignments += (
                len(task_table.numeric_items())
                - len(_effective_numeric_items(task_table))
            )
            for field in _effective_numeric_items(task_table):
                if isinstance(field.value, int | float) and not isinstance(
                    field.value,
                    bool,
                ):
                    tasks.add(field.value)
                    all_tasks.add(field.value)
        record = records.setdefault(
            unit_type,
            {
                "unit_type": unit_type,
                "sources": [],
                "presets": 0,
                "pylon_assignments": 0,
                "clsids": set(),
                "task_ids": set(),
            },
        )
        record["sources"].append(
            {
                "source": relative,
                "source_sha256": source_sha256,
            }
        )
        record["presets"] += len(presets)
        record["pylon_assignments"] += pylon_assignments
        record["clsids"].update(clsids)
        record["task_ids"].update(tasks)

    unit_types = []
    for unit_type, record in sorted(records.items()):
        unit_types.append(
            {
                "unit_type": unit_type,
                "sources": sorted(
                    record["sources"],
                    key=lambda item: item["source"].casefold(),
                ),
                "presets": record["presets"],
                "pylon_assignments": record["pylon_assignments"],
                "unique_clsids": len(record["clsids"]),
                "task_ids": sorted(record["task_ids"]),
            }
        )
    return {
        "schema": "dcsmizzer.dcs-default-payload-index/v1",
        "authority": "current_install_static_default_presets",
        "dcs_started": False,
        "compatibility_complete": False,
        "source_scope": _payload_source_scope(),
        "task_constant_source": task_source,
        "files_scanned": len(sources),
        "parse_failures": len(parse_failures),
        "parse_failure_sources": parse_failures,
        "unit_type_count": len(unit_types),
        "coverage": {
            "source_files_discovered": len(sources),
            "source_files_parsed": len(sources) - len(parse_failures),
            "unit_types": len(unit_types),
            "presets": sum(record["presets"] for record in unit_types),
            "pylon_assignments": sum(
                record["pylon_assignments"] for record in unit_types
            ),
            "unique_clsids": len(all_clsids),
            "task_ids": sorted(all_tasks),
        },
        "normalization_evidence": {
            "lua_table_semantics": "last assignment to a duplicate key wins",
            "shadowed_preset_table_assignments": (
                shadowed_preset_assignments
            ),
            "shadowed_pylon_table_assignments": (
                shadowed_pylon_assignments
            ),
            "shadowed_task_table_assignments": shadowed_task_assignments,
        },
        "unit_types": unit_types,
        "limitations": [
            "Only data-only UnitPayload tables in the declared source scope "
            "were indexed.",
            "Default presets are observations, not a complete compatibility "
            "matrix.",
        ],
    }


def module_index_report(
    dcs_root: Path,
    *,
    module: str | None = None,
    unit_type: str | None = None,
    service_country: str | None = None,
    service_year: int | None = None,
) -> dict[str, Any]:
    """Link static plugin/flyable literals to module payload unit types."""

    if (service_country is not None or service_year is not None) and (
        unit_type is None
    ):
        raise ValueError("service-country/year filters require --unit-type")
    if service_country is not None and not service_country.strip():
        raise ValueError("service country must be nonempty")
    if service_year is not None and (
        not isinstance(service_year, int)
        or isinstance(service_year, bool)
        or service_year < 1900
    ):
        raise ValueError("service year must be an integer of at least 1900")

    module_scopes = (
        ("CoreMods", "aircraft"),
        ("CoreMods", "tech"),
        ("Mods", "aircraft"),
        ("Mods", "tech"),
        ("Mods", "terrains"),
    )
    payload_by_module: dict[str, set[str]] = {}
    payload_sources = _payload_source_files(dcs_root)
    payload_failures = 0
    if payload_sources:
        payload_index = payload_index_report(dcs_root)
        payload_failures = payload_index["parse_failures"]
        for unit_record in payload_index["unit_types"]:
            for source in unit_record["sources"]:
                parts = PurePosixPath(source["source"]).parts
                if (
                    len(parts) >= 3
                    and parts[0] in {"CoreMods", "Mods"}
                    and parts[1] in {"aircraft", "tech"}
                ):
                    key = "/".join(parts[:3])
                    payload_by_module.setdefault(key, set()).add(
                        unit_record["unit_type"]
                    )

    records: list[dict[str, Any]] = []
    directories_seen = 0
    entry_sources = 0
    for family, kind in module_scopes:
        root = dcs_root / family / kind
        if not root.is_dir():
            continue
        for directory in sorted(
            (path for path in root.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            directories_seen += 1
            module_key = f"{family}/{kind}/{directory.name}"
            entry = next(
                (
                    candidate
                    for candidate in directory.iterdir()
                    if candidate.is_file()
                    and candidate.name.casefold() == "entry.lua"
                ),
                None,
            )
            plugin_ids: list[str] = []
            flyable_types: list[str] = []
            unresolved_calls: dict[str, int] = {}
            source: str | None = None
            source_sha256: str | None = None
            if entry is not None:
                entry_sources += 1
                source = entry.relative_to(dcs_root).as_posix()
                source_sha256 = _sha256(entry)
                identifiers = _entry_identifiers(entry)
                plugin_ids = identifiers["plugin_ids"]
                flyable_types = identifiers["flyable_types"]
                unresolved_calls = identifiers["unresolved_calls"]
            payload_types = sorted(payload_by_module.get(module_key, set()))
            record = {
                "scope": f"{family}/{kind}",
                "module_directory": directory.name,
                "module_key": module_key,
                "entry_source": source,
                "entry_source_sha256": source_sha256,
                "plugin_ids": plugin_ids,
                "flyable_types": flyable_types,
                "default_payload_unit_types": payload_types,
                "unresolved_literal_calls": unresolved_calls,
            }
            if module is not None and (
                directory.name.casefold() != module.casefold()
                and module_key.casefold() != module.casefold()
            ):
                continue
            if unit_type is not None and (
                unit_type not in flyable_types
                and unit_type not in payload_types
            ):
                continue
            records.append(record)

    unit_type_resolution: dict[str, Any] | None = None
    if unit_type is not None:
        service_life_records = _service_life_records(
            dcs_root,
            records,
            unit_type,
        )
        service_life_matches = [
            record
            for record in service_life_records
            if (
                service_country is None
                or record["country"].casefold()
                == service_country.casefold()
            )
            and (
                service_year is None
                or record["start_year"] <= service_year <= record["end_year"]
            )
        ]
        unit_type_resolution = {
            "unit_type": unit_type,
            "flyable_declared": any(
                unit_type in record["flyable_types"] for record in records
            ),
            "flyable_module_keys": [
                record["module_key"]
                for record in records
                if unit_type in record["flyable_types"]
            ],
            "payload_module_keys": [
                record["module_key"]
                for record in records
                if unit_type in record["default_payload_unit_types"]
            ],
            "declared_plugin_ids_in_matching_modules": sorted(
                {
                    plugin_id
                    for record in records
                    for plugin_id in record["plugin_ids"]
                }
            ),
            "flyable_plugin_ids": sorted(
                {
                    plugin_id
                    for record in records
                    if unit_type in record["flyable_types"]
                    for plugin_id in record["plugin_ids"]
                }
            ),
            "payload_module_plugin_ids": sorted(
                {
                    plugin_id
                    for record in records
                    if unit_type in record["default_payload_unit_types"]
                    for plugin_id in record["plugin_ids"]
                }
            ),
            "service_life_records": service_life_records,
            "service_life_query": {
                "country": service_country,
                "year": service_year,
                "requested": (
                    service_country is not None or service_year is not None
                ),
                "matched": bool(service_life_matches),
                "matches": service_life_matches,
            },
        }

    return {
        "schema": "dcsmizzer.dcs-module-index/v1",
        "authority": "current_install_static_entry_and_payload_sources",
        "dcs_started": False,
        "filters": {
            "module": module,
            "unit_type": unit_type,
            "service_country": service_country,
            "service_year": service_year,
        },
        "coverage": {
            "scope": [
                f"{family}/{kind}/*/entry.lua"
                for family, kind in module_scopes
            ],
            "module_directories_seen": directories_seen,
            "entry_sources_seen": entry_sources,
            "payload_files_seen": len(payload_sources),
            "payload_parse_failures": payload_failures,
            "matching_modules": len(records),
            "matching_service_life_records": (
                len(
                    unit_type_resolution["service_life_query"]["matches"]
                )
                if unit_type_resolution is not None
                else 0
            ),
        },
        "unit_type_resolution": unit_type_resolution,
        "modules": records,
        "limitations": [
            "Only literal assignments passed to declare_plugin and "
            "make_flyable in static entry.lua files were resolved.",
            "Service-life records include only literal "
            "declare_service_life calls under matching module directories.",
            "Default-payload unit types are linked by their module directory; "
            "they do not prove flyability or complete compatibility.",
            "A module directory or installed=true literal does not prove "
            "ownership, activation, or runtime availability.",
            "No Lua code was executed and no DCS or Mission Editor process "
            "was started.",
        ],
    }


def airbase_beacon_report(
    dcs_root: Path,
    terrain: str,
    *,
    airdrome_id: int | None = None,
) -> dict[str, Any]:
    """Map static beacon-encoded airfield IDs to names and beacon positions."""

    selected, beacon_path, records, malformed_airfield_blocks = (
        _load_airfield_beacons(dcs_root, terrain)
    )
    radio_path, radio_records, malformed_radio_blocks = (
        _load_airfield_radios(selected)
    )
    for identifier, radio_record in radio_records.items():
        record = records.setdefault(
            identifier,
            {
                "airdrome_id": identifier,
                "names": set(),
                "beacons": [],
            },
        )
        record["names"].update(radio_record["names"])
        record["radios"] = radio_record["radios"]
    for record in records.values():
        record.setdefault("radios", [])
    selected_records = [
        value
        for key, value in sorted(records.items())
        if airdrome_id is None or key == airdrome_id
    ]
    airbases = [
        _airbase_beacon_summary(
            record,
            include_beacons=airdrome_id is not None,
        )
        for record in selected_records
    ]
    relative_source = beacon_path.relative_to(dcs_root).as_posix()
    relative_radio_source = (
        radio_path.relative_to(dcs_root).as_posix()
        if radio_path is not None
        else None
    )
    return {
        "schema": "dcsmizzer.dcs-airbase-beacons/v1",
        "authority": "current_install_static_terrain_radio_and_beacons",
        "dcs_started": False,
        "terrain_directory": selected.name,
        "source": relative_source,
        "source_sha256": _sha256(beacon_path),
        "radio_source": relative_radio_source,
        "radio_source_sha256": (
            _sha256(radio_path) if radio_path is not None else None
        ),
        "filter": {"airdrome_id": airdrome_id},
        "coverage_complete": False,
        "airfield_ids_with_beacons": sum(
            bool(record["beacons"]) for record in records.values()
        ),
        "airfield_ids_with_radio": len(radio_records),
        "airfield_ids_union": len(records),
        "malformed_airfield_blocks": malformed_airfield_blocks,
        "malformed_radio_blocks": malformed_radio_blocks,
        "airbases": airbases,
        "limitations": [
            "The union covers only airfield IDs represented in the terrain's "
            "static radio.lua or beacon source; absent IDs remain unknown.",
            "Beacon positions are not airport centers, runway thresholds, or "
            "parking positions.",
            "Runway and parking registries still require version-matched "
            "terrain/runtime evidence.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def _load_airfield_beacons(
    dcs_root: Path,
    terrain: str,
) -> tuple[Path, Path, dict[int, dict[str, Any]], int]:
    terrain_root = dcs_root / "Mods" / "terrains"
    if not terrain_root.is_dir():
        raise ValueError("DCS terrain directory is missing")
    candidates = {
        path.name.casefold(): path
        for path in terrain_root.iterdir()
        if path.is_dir()
    }
    selected = candidates.get(terrain.casefold())
    if selected is None:
        raise ValueError("requested terrain directory is not installed")
    beacon_path = next(
        (
            path
            for name in ("beacons.lua", "Beacons.lua")
            if (path := selected / name).is_file()
        ),
        None,
    )
    if beacon_path is None:
        raise ValueError("terrain beacon source is missing")
    text = beacon_path.read_text(encoding="utf-8-sig")
    records: dict[int, dict[str, Any]] = {}
    malformed_airfield_blocks = 0
    for block_match in _BEACON_BLOCK.finditer(text):
        body = block_match.group("body")
        identifier = _AIRFIELD_BEACON_ID.search(body)
        if identifier is None:
            continue
        identifier_value = int(identifier.group("id"))
        try:
            beacon = _parse_airfield_beacon(body, identifier)
        except ValueError:
            malformed_airfield_blocks += 1
            continue
        record = records.setdefault(
            identifier_value,
            {
                "airdrome_id": identifier_value,
                "names": set(),
                "beacons": [],
            },
        )
        if beacon["display_name"]:
            record["names"].add(beacon["display_name"])
        record["beacons"].append(beacon)
    return selected, beacon_path, records, malformed_airfield_blocks


def _load_airfield_radios(
    terrain_root: Path,
) -> tuple[Path | None, dict[int, dict[str, Any]], int]:
    radio_path = next(
        (
            path
            for name in ("radio.lua", "Radio.lua")
            if (path := terrain_root / name).is_file()
        ),
        None,
    )
    if radio_path is None:
        return None, {}, 0
    text = radio_path.read_text(encoding="utf-8-sig")
    records: dict[int, dict[str, Any]] = {}
    malformed = 0
    for block_match in _BEACON_BLOCK.finditer(text):
        body = block_match.group("body")
        identifier = _AIRFIELD_RADIO_ID.search(body)
        if identifier is None:
            continue
        identifier_value = int(identifier.group("id"))
        name_match = _RADIO_NAME_COMMENT.search(body)
        if name_match is None:
            malformed += 1
            continue
        name = name_match.group("name").strip()
        callsign_match = _RADIO_CALLSIGN.search(body)
        radio = {
            "radio_id": (
                f"airfield{identifier.group('id')}_"
                f"{identifier.group('index')}"
            ),
            "display_name": name,
            "callsign": (
                _unescape_short_string(callsign_match.group("value"))
                if callsign_match is not None
                else None
            ),
        }
        record = records.setdefault(
            identifier_value,
            {
                "airdrome_id": identifier_value,
                "names": set(),
                "radios": [],
            },
        )
        record["names"].add(name)
        record["radios"].append(radio)
    return radio_path, records, malformed


def static_install_report(dcs_root: Path) -> dict[str, Any]:
    countries = countries_report(dcs_root)
    module_roots = {
        "aircraft": dcs_root / "Mods" / "aircraft",
        "terrains": dcs_root / "Mods" / "terrains",
        "campaigns": dcs_root / "Mods" / "campaigns",
    }
    modules = {
        kind: _module_inventory(path)
        for kind, path in module_roots.items()
    }
    payload_sources = _payload_source_files(dcs_root)
    payload_summary: dict[str, Any] = {
        "files_scanned": len(payload_sources),
        "parse_failures": None,
        "unit_type_count": None,
        "compatibility_complete": False,
    }
    if payload_sources:
        payload_index = payload_index_report(dcs_root)
        payload_summary.update(
            {
                "parse_failures": payload_index["parse_failures"],
                "unit_type_count": payload_index["unit_type_count"],
            }
        )
    executable = dcs_root / "bin" / "DCS.exe"
    product_version: str | None = None
    if executable.is_file():
        try:
            product_version = _windows_product_version(executable)
        except OSError:
            product_version = None
    manifest = dcs_root.parent.parent / "appmanifest_223750.acf"
    steam_build_id: str | None = None
    if manifest.is_file():
        try:
            manifest_text = manifest.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            manifest_text = ""
        build_match = re.search(
            r'"buildid"\s*"(?P<build>\d+)"',
            manifest_text,
        )
        steam_build_id = (
            build_match.group("build") if build_match is not None else None
        )
    return {
        "schema": "dcsmizzer.dcs-static/v1",
        "authority": "current_install_static_sources",
        "dcs_started": False,
        "dcs": {
            "product_version": product_version,
            "steam_build_id": steam_build_id,
        },
        "installed_module_directories": modules,
        "countries": {
            "count": countries["count"],
            "source_sha256": countries["source_sha256"],
        },
        "default_payload_files": len(payload_sources),
        "default_payloads": payload_summary,
        "runtime_required_for": [
            "initialized unit registry",
            "complete task capability matrix",
            "complete store-to-station compatibility",
            "per-terrain airbase, runway, and parking registry",
            "mission load and Mission Editor resave validation",
        ],
    }


def _payload_preset_record(
    unit_type: str,
    preset: LuaTable,
    *,
    source: str,
    source_sha256: str,
    source_preset_key: int | float,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    pylon_value = preset.get("pylons")
    pylons: list[dict[str, Any]] = []
    station_indices: dict[int, list[int]] = {}
    shadowed_pylon_assignments = 0
    if not isinstance(pylon_value, LuaTable):
        issues.append({"code": "invalid_pylons_table"})
    else:
        all_pylon_fields = pylon_value.numeric_items()
        pylon_fields = _effective_numeric_items(pylon_value)
        shadowed_pylon_assignments = (
            len(all_pylon_fields) - len(pylon_fields)
        )
        if len(pylon_fields) > _MAX_PAYLOAD_ASSIGNMENTS:
            issues.append(
                {
                    "code": "too_many_pylons",
                    "maximum": _MAX_PAYLOAD_ASSIGNMENTS,
                }
            )
        for index, pylon_field in enumerate(
            pylon_fields[:_MAX_PAYLOAD_ASSIGNMENTS]
        ):
            pylon_record: dict[str, Any] = {}
            pylon = pylon_field.value
            if not isinstance(pylon, LuaTable):
                issues.append(
                    {
                        "code": "invalid_pylon_record",
                        "index": index,
                    }
                )
                continue
            pylon_field_counts = Counter(
                field.key
                for field in pylon.fields
                if isinstance(field.key, str)
            )
            duplicate_pylon_fields = sorted(
                field
                for field, count in pylon_field_counts.items()
                if count > 1
            )
            if duplicate_pylon_fields:
                issues.append(
                    {
                        "code": "duplicate_pylon_fields",
                        "index": index,
                        "field_count": len(duplicate_pylon_fields),
                        "fields": _payload_field_sample(
                            duplicate_pylon_fields
                        ),
                    }
                )
            unsupported_pylon_fields = sorted(
                field
                for field in pylon_field_counts
                if field not in {"CLSID", "num", "settings"}
            )
            if unsupported_pylon_fields:
                issues.append(
                    {
                        "code": "unsupported_pylon_fields",
                        "index": index,
                        "field_count": len(unsupported_pylon_fields),
                        "fields": _payload_field_sample(
                            unsupported_pylon_fields
                        ),
                    }
                )
            unsupported_pylon_keys = sum(
                1
                for field in pylon.fields
                if not isinstance(field.key, str)
            )
            if unsupported_pylon_keys:
                issues.append(
                    {
                        "code": "unsupported_pylon_table_keys",
                        "index": index,
                        "count": unsupported_pylon_keys,
                    }
                )
            clsid = pylon.get("CLSID")
            if (
                not isinstance(clsid, str)
                or len(clsid) > 1024
            ):
                issues.append(
                    {
                        "code": "invalid_clsid",
                        "index": index,
                    }
                )
            else:
                pylon_record["CLSID"] = clsid
            if pylon.has("settings"):
                try:
                    pylon_record["settings"] = _payload_settings_value(
                        pylon.get("settings")
                    )
                except ValueError:
                    issues.append(
                        {
                            "code": "invalid_settings",
                            "index": index,
                        }
                    )
            if pylon.has("num"):
                station_value = pylon.get("num")
                station_evidence = "num_field"
            else:
                station_value = pylon_field.key
                station_evidence = "table_key"
            station = _payload_integral_value(
                station_value,
                minimum=1,
                maximum=10_000,
            )
            if station is None:
                issues.append(
                    {
                        "code": "invalid_station",
                        "index": index,
                    }
                )
            else:
                pylon_record["num"] = station
                pylon_record["station_evidence"] = station_evidence
                station_indices.setdefault(station, []).append(index)
            if pylon_record:
                pylons.append(pylon_record)
    for station, indices in sorted(station_indices.items()):
        if len(indices) > 1:
            issues.append(
                {
                    "code": "duplicate_station",
                    "station": station,
                    "indices": indices,
                }
            )
    pylons.sort(
        key=lambda record: (
            record.get("num", 10_001),
            record.get("CLSID", ""),
        )
    )

    task_value = preset.get("tasks")
    tasks: list[int] = []
    shadowed_task_assignments = 0
    if not isinstance(task_value, LuaTable):
        issues.append({"code": "invalid_tasks_table"})
    else:
        all_task_fields = task_value.numeric_items()
        task_fields = _effective_numeric_items(task_value)
        shadowed_task_assignments = len(all_task_fields) - len(task_fields)
        if len(task_fields) > _MAX_PAYLOAD_TASKS:
            issues.append(
                {
                    "code": "too_many_tasks",
                    "maximum": _MAX_PAYLOAD_TASKS,
                }
            )
        invalid_task_keys = len(task_value.fields) - len(all_task_fields)
        if invalid_task_keys:
            issues.append(
                {
                    "code": "invalid_task_table_keys",
                    "count": invalid_task_keys,
                }
            )
        for index, task_field in enumerate(
            task_fields[:_MAX_PAYLOAD_TASKS]
        ):
            task = _payload_integral_value(
                task_field.value,
                minimum=0,
                maximum=1_000_000,
            )
            if task is None:
                issues.append(
                    {
                        "code": "invalid_task_id",
                        "index": index,
                    }
                )
            else:
                tasks.append(task)
    tasks = sorted(set(tasks))

    name = preset.get("name")
    display_name = preset.get("displayName")
    category = preset.get("category")
    for field, value, required in (
        ("name", name, True),
        ("displayName", display_name, False),
        ("category", category, False),
    ):
        issue = _payload_text_issue(
            value,
            field=field,
            required=required,
            max_length=4096,
        )
        if issue is not None:
            issues.append(issue)
    field_counts = Counter(
        field.key
        for field in preset.fields
        if isinstance(field.key, str)
    )
    duplicate_fields = sorted(
        field for field, count in field_counts.items() if count > 1
    )
    if duplicate_fields:
        issues.append(
            {
                "code": "duplicate_preset_fields",
                "field_count": len(duplicate_fields),
                "fields": _payload_field_sample(duplicate_fields),
            }
        )
    unsupported_fields = sorted(
        field
        for field in field_counts
        if field not in _PAYLOAD_PRESET_FIELDS
    )
    if unsupported_fields:
        issues.append(
            {
                "code": "unsupported_preset_metadata",
                "field_count": len(unsupported_fields),
                "fields": _payload_field_sample(unsupported_fields),
            }
        )
    numeric_metadata_fields = sum(
        1
        for field in preset.fields
        if isinstance(field.key, (int, float))
        and not isinstance(field.key, bool)
    )
    if numeric_metadata_fields:
        issues.append(
            {
                "code": "unsupported_numeric_preset_fields",
                "count": numeric_metadata_fields,
            }
        )

    record: dict[str, Any] = {
        "name": name if isinstance(name, str) else None,
        "display_name": (
            display_name if isinstance(display_name, str) else None
        ),
        "category": category if isinstance(category, str) else None,
        "source": source,
        "source_sha256": source_sha256,
        "source_preset_key": source_preset_key,
        "pylons": pylons,
        "tasks": tasks,
        "integrity": {
            "valid": not issues,
            "issues": issues,
        },
        "normalization_evidence": {
            "shadowed_pylon_table_assignments": (
                shadowed_pylon_assignments
            ),
            "shadowed_task_table_assignments": shadowed_task_assignments,
        },
    }
    if not issues:
        fingerprints = payload_fingerprint(
            unit_type,
            pylons,
            tasks=tasks,
            preset_name=name,
            display_name=display_name,
            category=category,
        )
        record["fingerprints"] = {
            "schema": fingerprints["schema"],
            "composition_sha256": fingerprints["composition_sha256"],
            "configured_composition_sha256": fingerprints[
                "configured_composition_sha256"
            ],
            "preset_sha256": fingerprints["preset_sha256"],
        }
    return record


def _payload_assignment_analysis(
    pylons: Mapping[int | float, str] | Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(pylons, Mapping):
        raw_records: list[Any] = [
            {"num": station, "CLSID": clsid}
            for station, clsid in pylons.items()
        ]
    elif isinstance(pylons, Sequence) and not isinstance(
        pylons,
        (str, bytes, bytearray),
    ):
        raw_records = list(pylons)
    else:
        return [], [{"code": "invalid_pylon_collection"}]
    if len(raw_records) > _MAX_PAYLOAD_ASSIGNMENTS:
        raise ValueError(
            "payload query accepts at most "
            f"{_MAX_PAYLOAD_ASSIGNMENTS} pylon assignments"
        )

    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    station_indices: dict[int, list[int]] = {}
    settings_bytes = 0
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            issues.append(
                {
                    "code": "invalid_pylon_record",
                    "index": index,
                }
            )
            continue
        unsupported_fields = sorted(
            str(key)
            for key in raw_record
            if (
                not isinstance(key, str)
                or key
                not in {
                    "num",
                    "station",
                    "CLSID",
                    "settings",
                    "station_evidence",
                }
            )
        )
        if unsupported_fields:
            issues.append(
                {
                    "code": "unsupported_pylon_fields",
                    "index": index,
                    "field_count": len(unsupported_fields),
                    "fields": _payload_field_sample(unsupported_fields),
                }
            )
            continue
        has_num = "num" in raw_record
        has_station = "station" in raw_record
        if has_num and has_station and raw_record["num"] != raw_record["station"]:
            issues.append(
                {
                    "code": "conflicting_station_fields",
                    "index": index,
                }
            )
            continue
        station_value = (
            raw_record.get("num")
            if has_num
            else raw_record.get("station")
        )
        station = _payload_integral_value(
            station_value,
            minimum=1,
            maximum=10_000,
        )
        if station is None:
            issues.append(
                {
                    "code": "invalid_station",
                    "index": index,
                }
            )
            continue
        clsid = raw_record.get("CLSID")
        if (
            not isinstance(clsid, str)
            or len(clsid) > 1024
        ):
            issues.append(
                {
                    "code": "invalid_clsid",
                    "index": index,
                }
            )
            continue
        record = {"num": station, "CLSID": clsid}
        if "settings" in raw_record:
            try:
                normalized_settings = _payload_settings_value(
                    raw_record["settings"]
                )
            except ValueError:
                issues.append(
                    {
                        "code": "invalid_settings",
                        "index": index,
                    }
                )
                continue
            settings_bytes += len(_canonical_json_bytes(normalized_settings))
            if settings_bytes > _MAX_PAYLOAD_SETTINGS_BYTES:
                raise ValueError(
                    "payload settings exceed the 65536-byte normalized limit"
                )
            record["settings"] = normalized_settings
        records.append(record)
        station_indices.setdefault(station, []).append(index)
    for station, indices in sorted(station_indices.items()):
        if len(indices) > 1:
            issues.append(
                {
                    "code": "duplicate_station",
                    "station": station,
                    "indices": indices,
                }
            )
    records.sort(key=lambda record: (record["num"], record["CLSID"]))
    return records, issues


def _payload_configuration_relation(
    query_pylons: Sequence[dict[str, Any]],
    source_pylons: Sequence[dict[str, Any]],
) -> tuple[bool, list[int]]:
    source_by_station = {
        pylon["num"]: pylon
        for pylon in source_pylons
    }
    unspecified: list[int] = []
    for query in query_pylons:
        source = source_by_station[query["num"]]
        if "settings" in query:
            if (
                "settings" not in source
                or query["settings"] != source["settings"]
            ):
                return True, []
        elif "settings" in source:
            unspecified.append(query["num"])
    return False, sorted(unspecified)


def _payload_settings_value(value: Any) -> Any:
    budget = [0]

    def normalize(item: Any, depth: int) -> Any:
        budget[0] += 1
        if budget[0] > 2048 or depth > 16:
            raise ValueError("settings limit exceeded")
        if isinstance(item, bool):
            return item
        if isinstance(item, int):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("non-finite settings number")
            return int(item) if item.is_integer() else item
        if isinstance(item, str):
            if len(item) > 4096:
                raise ValueError("settings string limit exceeded")
            return item
        if isinstance(item, LuaTable):
            numeric_fields = [
                field
                for field in item.fields
                if isinstance(field.key, (int, float))
                and not isinstance(field.key, bool)
            ]
            string_fields = [
                field
                for field in item.fields
                if isinstance(field.key, str)
            ]
            if len(numeric_fields) + len(string_fields) != len(item.fields):
                raise ValueError("unsupported settings table key")
            if numeric_fields and string_fields:
                raise ValueError("mixed settings table keys")
            if numeric_fields:
                effective = _effective_numeric_items(item)
                keys = [
                    _payload_integral_value(
                        field.key,
                        minimum=1,
                        maximum=256,
                    )
                    for field in effective
                ]
                if any(key is None for key in keys) or keys != list(
                    range(1, len(keys) + 1)
                ):
                    raise ValueError("settings array must be dense")
                return [
                    normalize(field.value, depth + 1)
                    for field in effective
                ]
            effective_strings: dict[str, Any] = {}
            for field in item.fields:
                if len(field.key) > 256:
                    raise ValueError("settings key limit exceeded")
                effective_strings[field.key] = field.value
            if len(effective_strings) > 256:
                raise ValueError("settings table limit exceeded")
            return {
                key: normalize(effective_strings[key], depth + 1)
                for key in sorted(effective_strings)
            }
        if isinstance(item, Mapping):
            if len(item) > 256:
                raise ValueError("settings object limit exceeded")
            if any(
                not isinstance(key, str) or len(key) > 256
                for key in item
            ):
                raise ValueError("settings object keys must be strings")
            return {
                key: normalize(item[key], depth + 1)
                for key in sorted(item)
            }
        if isinstance(item, Sequence) and not isinstance(
            item,
            (str, bytes, bytearray),
        ):
            if len(item) > 256:
                raise ValueError("settings array limit exceeded")
            return [normalize(child, depth + 1) for child in item]
        raise ValueError("unsupported settings value")

    result = normalize(value, 0)
    if len(_canonical_json_bytes(result)) > _MAX_STORE_SETTINGS_BYTES:
        raise ValueError("normalized store settings size limit exceeded")
    return result


def _payload_task_analysis(
    tasks: Sequence[int | float],
) -> tuple[list[int], list[dict[str, Any]]]:
    if not isinstance(tasks, Sequence) or isinstance(
        tasks,
        (str, bytes, bytearray),
    ):
        return [], [{"code": "invalid_task_collection"}]
    if len(tasks) > _MAX_PAYLOAD_TASKS:
        raise ValueError(
            f"payload query accepts at most {_MAX_PAYLOAD_TASKS} task IDs"
        )
    normalized: list[int] = []
    issues: list[dict[str, Any]] = []
    for index, value in enumerate(tasks):
        task = _payload_integral_value(
            value,
            minimum=0,
            maximum=1_000_000,
        )
        if task is None:
            issues.append(
                {
                    "code": "invalid_task_id",
                    "index": index,
                }
            )
        else:
            normalized.append(task)
    return sorted(set(normalized)), issues


def _payload_text_issue(
    value: Any,
    *,
    field: str,
    required: bool,
    max_length: int,
) -> dict[str, Any] | None:
    if value is None and not required:
        return None
    if (
        not isinstance(value, str)
        or (required and not value.strip())
        or len(value) > max_length
    ):
        return {
            "code": f"invalid_{field}",
        }
    return None


def _payload_field_sample(fields: Sequence[str]) -> list[str]:
    return [
        field[:128]
        for field in sorted(fields)[:16]
    ]


def _payload_integral_value(
    value: Any,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    normalized = int(value)
    return normalized if minimum <= normalized <= maximum else None


def _payload_fingerprint_rules() -> dict[str, Any]:
    return {
        "schema": _PAYLOAD_FINGERPRINT_SCHEMA,
        "unit_type": "exact Unicode string; no trimming or case folding",
        "pylons": (
            "complete positive integral station-to-exact-CLSID-string "
            "assignments, including an installed empty clean marker; sorted "
            "by station; duplicate stations are invalid; optional settings "
            "are normalized as bounded JSON-like data"
        ),
        "tasks": "unique integral task IDs sorted ascending",
        "preset_metadata": (
            "exact name, displayName, and category strings or null"
        ),
        "serialization": (
            "UTF-8 JSON with sorted keys, compact separators, and no NaN"
        ),
        "limits": {
            "pylons": _MAX_PAYLOAD_ASSIGNMENTS,
            "tasks": _MAX_PAYLOAD_TASKS,
            "normalized_settings_bytes_per_store": (
                _MAX_STORE_SETTINGS_BYTES
            ),
            "normalized_settings_bytes_per_payload": (
                _MAX_PAYLOAD_SETTINGS_BYTES
            ),
        },
        "composition_fingerprint_includes": ["unit_type", "pylons"],
        "composition_fingerprint_excludes": ["pylon settings"],
        "configured_composition_fingerprint_includes": [
            "unit_type",
            "pylons",
            "pylon settings",
        ],
        "preset_fingerprint_includes": [
            "unit_type",
            "pylons",
            "pylon settings",
            "tasks",
            "preset_name",
            "display_name",
            "category",
        ],
    }


def _payload_pair_index(
    presets: Sequence[dict[str, Any]],
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    result: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for preset in presets:
        reference = _payload_preset_reference(preset)
        for pylon in preset["pylons"]:
            key = (pylon["num"], pylon["CLSID"])
            result.setdefault(key, []).append(reference)
    for observations in result.values():
        observations.sort(
            key=lambda item: (
                item["source"].casefold(),
                item["source_preset_key"],
                item["name"] or "",
            )
        )
    return result


def _payload_preset_reference(
    preset: dict[str, Any],
    *,
    include_integrity: bool = False,
) -> dict[str, Any]:
    result = {
        "name": preset["name"],
        "display_name": preset["display_name"],
        "category": preset["category"],
        "tasks": preset["tasks"],
        "source": preset["source"],
        "source_sha256": preset["source_sha256"],
        "source_preset_key": preset["source_preset_key"],
    }
    if "fingerprints" in preset:
        result["fingerprints"] = preset["fingerprints"]
    if include_integrity:
        result["integrity"] = preset["integrity"]
    return result


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _dcs_install_identity(dcs_root: Path) -> dict[str, str | None]:
    executable = dcs_root / "bin" / "DCS.exe"
    product_version: str | None = None
    if executable.is_file():
        try:
            product_version = _windows_product_version(executable)
        except OSError:
            product_version = None
    manifest = dcs_root.parent.parent / "appmanifest_223750.acf"
    steam_build_id: str | None = None
    if manifest.is_file():
        try:
            manifest_text = manifest.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            manifest_text = ""
        build_match = re.search(
            r'"buildid"\s*"(?P<build>\d+)"',
            manifest_text,
        )
        if build_match is not None:
            steam_build_id = build_match.group("build")
    return {
        "product_version": product_version,
        "steam_build_id": steam_build_id,
    }


def _payload_source_scope() -> list[str]:
    return [
        "MissionEditor/data/scripts/UnitPayloads/*.lua",
        "CoreMods/aircraft/*/UnitPayloads/**/*.lua",
        "Mods/aircraft/*/UnitPayloads/**/*.lua",
        "CoreMods/tech/*/UnitPayloads/**/*.lua",
        "Mods/tech/*/UnitPayloads/**/*.lua",
    ]


def _payload_error_code(error: OSError | LuaDataError) -> str:
    if isinstance(error, LuaDataError):
        message = str(error)
        if "executable statement" in message or "function or member access" in message:
            return "executable_lua_rejected"
        if "undefined identifier" in message:
            return "unresolved_identifier"
    return type(error).__name__


def _entry_identifiers(path: Path) -> dict[str, Any]:
    text = _read_static_lua(path)
    assignments = {
        match.group("name"): _unescape_short_string(match.group("value"))
        for match in _ENTRY_LITERAL_ASSIGNMENT.finditer(text)
    }
    resolved: dict[str, list[str]] = {
        "declare_plugin": [],
        "make_flyable": [],
    }
    unresolved: Counter[str] = Counter()
    for call_head in _ENTRY_CALL_HEAD.finditer(text):
        call = call_head.group("call")
        match = _ENTRY_IDENTIFIER_CALL.match(text, call_head.start())
        if match is None:
            unresolved[call] += 1
            continue
        literal = match.group("literal")
        if literal is not None:
            value = _unescape_short_string(literal)
        else:
            value = assignments.get(match.group("identifier"))
        if value is None:
            unresolved[call] += 1
        else:
            resolved[call].append(value)
    return {
        "plugin_ids": sorted(set(resolved["declare_plugin"])),
        "flyable_types": sorted(set(resolved["make_flyable"])),
        "unresolved_calls": dict(sorted(unresolved.items())),
    }


def _service_life_records(
    dcs_root: Path,
    modules: list[dict[str, Any]],
    unit_type: str,
) -> list[dict[str, Any]]:
    records: dict[
        tuple[str, str, int, int, str],
        dict[str, Any],
    ] = {}
    for module in modules:
        module_root = dcs_root.joinpath(
            *PurePosixPath(module["module_key"]).parts
        )
        if not module_root.is_dir():
            continue
        for path in sorted(
            module_root.rglob("*.lua"),
            key=lambda item: item.as_posix().casefold(),
        ):
            try:
                text = _read_static_lua(path)
            except (OSError, UnicodeDecodeError):
                continue
            for match in _SERVICE_LIFE_CALL.finditer(text):
                observed_type = _unescape_short_string(match.group("unit"))
                if observed_type != unit_type:
                    continue
                country = _unescape_short_string(match.group("country"))
                start_year = int(match.group("start"))
                end_year = int(match.group("end"))
                source = path.relative_to(dcs_root).as_posix()
                key = (
                    observed_type,
                    country,
                    start_year,
                    end_year,
                    source,
                )
                records[key] = {
                    "unit_type": observed_type,
                    "country": country,
                    "start_year": start_year,
                    "end_year": end_year,
                    "source": source,
                    "source_sha256": _sha256(path),
                }
    return [records[key] for key in sorted(records)]


def _read_static_lua(path: Path) -> str:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_payload_source(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise OSError("payload source cannot be inspected safely") from error
    _validate_payload_source_status(before)
    if before.st_size > _MAX_PAYLOAD_SOURCE_BYTES:
        raise OSError("payload source exceeds its byte limit")

    flags = os.O_RDONLY
    for name in (
        "O_BINARY",
        "O_CLOEXEC",
        "O_NOINHERIT",
        "O_NOFOLLOW",
        "O_NONBLOCK",
    ):
        flags |= getattr(os, name, 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise OSError("payload source cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        _validate_payload_source_status(opened)
        if not _same_file_snapshot(before, opened):
            raise OSError("payload source changed before it was read")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(_MAX_PAYLOAD_SOURCE_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_PAYLOAD_SOURCE_BYTES:
        raise OSError("payload source exceeds its byte limit")
    if not _same_file_snapshot(opened, after):
        raise OSError("payload source changed while it was read")
    try:
        final_path = path.lstat()
    except OSError as error:
        raise OSError("payload source changed after it was read") from error
    _validate_payload_source_status(final_path)
    if not _same_file_snapshot(opened, final_path):
        raise OSError("payload source path changed while it was read")
    return payload


def _validate_payload_source_status(status: os.stat_result) -> None:
    if not stat.S_ISREG(status.st_mode):
        raise OSError("payload source is not a regular file")
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if attributes & reparse_flag:
        raise OSError("payload source is a reparse point")


def _same_file_snapshot(
    first: os.stat_result,
    second: os.stat_result,
) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _path_is_reparse_or_symlink(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def _payload_failure_record(
    source: str,
    error: BaseException | str,
    *,
    source_bytes: bytes | None = None,
) -> dict[str, Any]:
    error_code = (
        error
        if isinstance(error, str)
        else _payload_error_code(error)
    )
    record: dict[str, Any] = {
        "source": source,
        "error_code": error_code,
        "unit_type_hint": None,
        "unit_type_hint_authority": "unavailable",
    }
    if source_bytes is not None:
        hint = _payload_unit_type_hint(source_bytes)
        if hint is not None:
            record["unit_type_hint"] = hint
            record["unit_type_hint_authority"] = (
                "safe_literal_top_level_unitPayloads_name"
            )
    return record


def _payload_failures_for_unit_type(
    failures: Sequence[Mapping[str, Any]],
    unit_type: str,
) -> list[dict[str, Any]]:
    return [
        dict(failure)
        for failure in failures
        if failure.get("unit_type_hint") in {None, unit_type}
    ]


def _payload_unit_type_hint(source: bytes) -> str | None:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = source.decode("cp1251")
        except UnicodeDecodeError:
            return None
    visible, code = _payload_lua_lexical_views(text)
    declaration = re.search(
        r"\blocal[ \t]+unitPayloads[ \t]*=[ \t]*\{",
        code,
    )
    if declaration is None:
        return None
    opening = code.find("{", declaration.start(), declaration.end())
    if opening < 0:
        return None
    limit = min(len(code), opening + 8192)
    depth = 1
    cursor = opening + 1
    while cursor < limit and depth:
        character = code[cursor]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        elif depth == 1:
            previous = code[cursor - 1] if cursor > opening + 1 else " "
            match = (
                None
                if previous.isalnum() or previous == "_"
                else re.match(r"name[ \t]*=", code[cursor:])
            )
            if match is not None:
                value_start = cursor + match.end()
                while (
                    value_start < len(visible)
                    and visible[value_start].isspace()
                ):
                    value_start += 1
                if (
                    value_start >= limit
                    or visible[value_start] not in {'"', "'"}
                ):
                    return None
                return _bounded_lua_short_string(
                    visible,
                    value_start,
                    maximum_chars=512,
                )
        cursor += 1
    return None


def _payload_lua_lexical_views(text: str) -> tuple[str, str]:
    visible = list(text)
    code = list(text)
    index = 0
    while index < len(text):
        if text.startswith("--", index):
            opening = _lua_long_bracket(text, index + 2)
            if opening is not None:
                opener_end, equals = opening
                closing = "]" + ("=" * equals) + "]"
                end = text.find(closing, opener_end)
                end = len(text) if end < 0 else end + len(closing)
            else:
                newline = text.find("\n", index + 2)
                end = len(text) if newline < 0 else newline
            _mask_lua_range(visible, index, end)
            _mask_lua_range(code, index, end)
            index = end
            continue
        if text[index] in {'"', "'"}:
            end = _lua_short_string_end(text, index)
            _mask_lua_range(code, index, end)
            index = end
            continue
        opening = _lua_long_bracket(text, index)
        if opening is not None:
            opener_end, equals = opening
            closing = "]" + ("=" * equals) + "]"
            found = text.find(closing, opener_end)
            end = len(text) if found < 0 else found + len(closing)
            _mask_lua_range(code, index, end)
            index = end
            continue
        index += 1
    return "".join(visible), "".join(code)


def _lua_long_bracket(
    text: str,
    index: int,
) -> tuple[int, int] | None:
    if index >= len(text) or text[index] != "[":
        return None
    cursor = index + 1
    while cursor < len(text) and text[cursor] == "=":
        cursor += 1
    if cursor >= len(text) or text[cursor] != "[":
        return None
    return cursor + 1, cursor - index - 1


def _lua_short_string_end(text: str, start: int) -> int:
    quote = text[start]
    cursor = start + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        cursor += 1
        if text[cursor - 1] == quote:
            return cursor
    return len(text)


def _mask_lua_range(target: list[str], start: int, end: int) -> None:
    for index in range(start, min(end, len(target))):
        if target[index] not in {"\r", "\n"}:
            target[index] = " "


def _bounded_lua_short_string(
    text: str,
    start: int,
    *,
    maximum_chars: int,
) -> str | None:
    quote = text[start]
    cursor = start + 1
    output: list[str] = []
    while cursor < len(text):
        character = text[cursor]
        if character == quote:
            value = "".join(output)
            return value if value.strip() and len(value) <= maximum_chars else None
        if character == "\\":
            if cursor + 1 >= len(text):
                return None
            escaped = text[cursor + 1]
            translations = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "\\": "\\",
                '"': '"',
                "'": "'",
            }
            if escaped not in translations:
                return None
            output.append(translations[escaped])
            cursor += 2
        else:
            output.append(character)
            cursor += 1
        if len(output) > maximum_chars:
            return None
    return None


def _payload_source_files(dcs_root: Path) -> list[tuple[str, Path]]:
    candidates: set[Path] = set()
    central = (
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "UnitPayloads"
    )
    if _path_is_reparse_or_symlink(central):
        raise ValueError(
            "DCS payload source scope contains a reparse entry"
        )
    if central.is_dir():
        candidates.update(central.glob("*.lua"))
    for family in ("CoreMods", "Mods"):
        for kind in ("aircraft", "tech"):
            module_root = dcs_root / family / kind
            if _path_is_reparse_or_symlink(module_root):
                raise ValueError(
                    "DCS payload source scope contains a reparse entry"
                )
            if not module_root.is_dir():
                continue
            for module in module_root.iterdir():
                if _path_is_reparse_or_symlink(module):
                    raise ValueError(
                        "DCS payload source scope contains a reparse entry"
                    )
                payload_root = module / "UnitPayloads"
                if _path_is_reparse_or_symlink(payload_root):
                    raise ValueError(
                        "DCS payload source scope contains a reparse entry"
                    )
                if payload_root.is_dir():
                    for entry in payload_root.rglob(
                        "*",
                        recurse_symlinks=False,
                    ):
                        if _path_is_reparse_or_symlink(entry):
                            raise ValueError(
                                "DCS payload source scope contains a "
                                "reparse entry"
                            )
                        try:
                            status = entry.lstat()
                        except OSError as error:
                            raise ValueError(
                                "DCS payload source scope cannot be "
                                "inspected safely"
                            ) from error
                        if (
                            stat.S_ISREG(status.st_mode)
                            and entry.suffix.casefold() == ".lua"
                        ):
                            candidates.add(entry)
    if len(candidates) > _MAX_PAYLOAD_SOURCE_FILES:
        raise ValueError(
            "DCS payload source count exceeds the "
            f"{_MAX_PAYLOAD_SOURCE_FILES}-file safety limit"
        )
    return sorted(
        (
            (path.relative_to(dcs_root).as_posix(), path)
            for path in candidates
        ),
        key=lambda item: item[0].casefold(),
    )


def _parse_payload_table(
    data: bytes,
    task_constants: dict[str, int] | None = None,
) -> LuaTable | None:
    if task_constants:
        data = _prepare_payload_bytes(data, task_constants)
    parsed = parse_lua_bytes(data)
    result = parsed.document.returned
    if not isinstance(result, LuaTable):
        result = parsed.document.get("unitPayloads")
    return result if isinstance(result, LuaTable) else None


def _payload_task_constants(
    dcs_root: Path,
) -> tuple[dict[str, int], dict[str, Any] | None]:
    comment_path = (
        dcs_root
        / "CoreMods"
        / "aircraft"
        / "I-16"
        / "UnitPayloads"
        / "I-16.lua"
    )
    try:
        comment_bytes = _read_payload_source(comment_path)
        comment_text = comment_bytes.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        comment_bytes = b""
        comment_text = ""
    if comment_text:
        comment_constants = {
            match.group("name"): int(match.group("value"))
            for match in _TASK_COMMENT_CONSTANT.finditer(comment_text)
        }
        if comment_constants:
            return comment_constants, {
                "source": comment_path.relative_to(dcs_root).as_posix(),
                "source_sha256": hashlib.sha256(comment_bytes).hexdigest(),
                "constants": comment_constants,
                "use": (
                    "Data-only parser predefinitions from the installed "
                    "UnitPayload task-ID reference comment."
                ),
            }

    fallback_path = (
        dcs_root
        / "CoreMods"
        / "aircraft"
        / "ChinaAssetPack"
        / "UnitPayloads"
        / "JF-17.lua"
    )
    try:
        fallback_bytes = _read_payload_source(fallback_path)
        text = fallback_bytes.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}, None
    values = {
        match.group("name"): int(match.group("value"))
        for match in _TASK_CONSTANT.finditer(text)
    }
    constants = {
        canonical: values[alias]
        for canonical, alias in _TASK_ALIASES.items()
        if alias in values
    }
    if not constants:
        return {}, None
    return constants, {
        "source": fallback_path.relative_to(dcs_root).as_posix(),
        "source_sha256": hashlib.sha256(fallback_bytes).hexdigest(),
        "constants": constants,
        "use": (
            "Data-only parser predefinitions for UnitPayload files that refer "
            "to DCS task constants symbolically."
        ),
    }


def _prepare_payload_bytes(
    data: bytes,
    task_constants: dict[str, int],
) -> bytes:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")

    def expand(match: re.Match[str]) -> str:
        names = [item.strip() for item in match.group("names").split(",")]
        values = [item.strip() for item in match.group("values").split(",")]
        if len(names) != len(values):
            return match.group(0)
        indent = match.group("indent")
        return "\n".join(
            f"{indent}local {name} = {value}"
            for name, value in zip(names, values, strict=True)
        )

    expanded = _NUMERIC_MULTI_ASSIGNMENT.sub(expand, text)
    preamble = "\n".join(
        f"local {name} = {value}"
        for name, value in sorted(task_constants.items())
    )
    return f"{preamble}\n{expanded}".encode("utf-8")


def _parse_airfield_beacon(
    body: str,
    identifier: re.Match[str],
) -> dict[str, Any]:
    name_match = _DISPLAY_NAME.search(body)
    position_match = _POSITION.search(body)
    geo_match = _POSITION_GEO.search(body)
    type_match = _BEACON_TYPE.search(body)
    if position_match is None and geo_match is None:
        raise ValueError("beacon has no parseable position")
    display_name = (
        _unescape_short_string(name_match.group("value"))
        if name_match is not None
        else ""
    )
    beacon: dict[str, Any] = {
        "beacon_id": f"airfield{identifier.group('id')}_{identifier.group('index')}",
        "display_name": display_name,
        "type": type_match.group("value") if type_match is not None else None,
    }
    for field in ("callsign",):
        value = _quoted_field(body, field)
        if value is not None:
            beacon[field] = value
    for field in ("frequency", "channel", "direction"):
        value = _numeric_field(body, field)
        if value is not None:
            beacon[field] = value
    if position_match is not None:
        beacon["map_position"] = {
            "x": float(position_match.group("x")),
            "elevation": float(position_match.group("elevation")),
            "z": float(position_match.group("z")),
        }
    if geo_match is not None:
        beacon["geo_position"] = {
            "latitude": float(geo_match.group("latitude")),
            "longitude": float(geo_match.group("longitude")),
        }
    return beacon


def _airbase_beacon_summary(
    record: dict[str, Any],
    *,
    include_beacons: bool,
) -> dict[str, Any]:
    beacons = sorted(record["beacons"], key=lambda item: item["beacon_id"])
    map_positions = [
        beacon["map_position"]
        for beacon in beacons
        if "map_position" in beacon
    ]
    geo_positions = [
        beacon["geo_position"]
        for beacon in beacons
        if "geo_position" in beacon
    ]
    result: dict[str, Any] = {
        "airdrome_id": record["airdrome_id"],
        "names": sorted(record["names"]),
        "beacon_count": len(beacons),
        "radio_count": len(record.get("radios", [])),
        "beacon_types": sorted(
            {
                beacon["type"]
                for beacon in beacons
                if isinstance(beacon.get("type"), str)
            }
        ),
        "callsigns": sorted(
            {
                beacon["callsign"]
                for beacon in beacons
                if isinstance(beacon.get("callsign"), str)
            }
            | {
                radio["callsign"]
                for radio in record.get("radios", [])
                if isinstance(radio.get("callsign"), str)
            }
        ),
    }
    if map_positions:
        result["map_position_bounds"] = {
            field: [
                min(position[field] for position in map_positions),
                max(position[field] for position in map_positions),
            ]
            for field in ("x", "elevation", "z")
        }
    if geo_positions:
        result["geo_position_bounds"] = {
            field: [
                min(position[field] for position in geo_positions),
                max(position[field] for position in geo_positions),
            ]
            for field in ("latitude", "longitude")
        }
    if include_beacons:
        result["beacons"] = beacons
        result["radios"] = sorted(
            record.get("radios", []),
            key=lambda item: item["radio_id"],
        )
    return result


def _quoted_field(body: str, field: str) -> str | None:
    match = re.search(
        _QUOTED_FIELD_TEMPLATE.format(field=re.escape(field)),
        body,
        re.DOTALL,
    )
    return (
        _unescape_short_string(match.group("value"))
        if match is not None
        else None
    )


def _numeric_field(body: str, field: str) -> int | float | None:
    match = re.search(
        _NUMERIC_FIELD_TEMPLATE.format(field=re.escape(field)),
        body,
    )
    if match is None:
        return None
    value = float(match.group("value"))
    return int(value) if value.is_integer() else value


def _unescape_short_string(value: str) -> str:
    return (
        value.replace("\\\\", "\0")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\0", "\\")
    )


def _module_inventory(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for directory in sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.name.casefold(),
    ):
        entry = directory / "entry.lua"
        state: str | None = None
        self_ids: list[str] = []
        if entry.is_file():
            try:
                text = entry.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                text = ""
            match = _STATE.search(text)
            state = match.group(2) if match else None
            self_ids = sorted(
                {match.group(2) for match in _SELF_ID.finditer(text)}
            )
        result.append(
            {
                "directory": directory.name,
                "entry_present": entry.is_file(),
                "declared_state": state,
                "self_ids": self_ids,
            }
        )
    return result


def _numeric_tables(value: Any) -> list[LuaTable]:
    return [
        field.value
        for field in _effective_numeric_items(_table(value))
        if isinstance(field.value, LuaTable)
    ]


def _effective_numeric_items(value: LuaTable) -> tuple[LuaField, ...]:
    """Apply Lua table-constructor last-write semantics to numeric keys."""

    effective: dict[int | float, LuaField] = {}
    for field in value.fields:
        if isinstance(field.key, (int, float)) and not isinstance(
            field.key,
            bool,
        ):
            effective[field.key] = field
    return tuple(
        effective[key]
        for key in sorted(effective)
    )


def _table(value: Any) -> LuaTable:
    return value if isinstance(value, LuaTable) else LuaTable(())


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _windows_product_version(executable: Path) -> str:
    if not hasattr(ctypes, "windll"):
        raise OSError("Windows version API is unavailable")
    size = ctypes.windll.version.GetFileVersionInfoSizeW(
        str(executable),
        None,
    )
    if size == 0:
        raise OSError("version resource is unavailable")
    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(
        str(executable),
        0,
        size,
        buffer,
    ):
        raise OSError("failed to read version resource")
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(
        buffer,
        "\\",
        ctypes.byref(pointer),
        ctypes.byref(length),
    ):
        raise OSError("fixed version info is missing")

    class FixedFileInfo(ctypes.Structure):
        _fields_ = [
            ("signature", ctypes.c_uint32),
            ("structure_version", ctypes.c_uint32),
            ("file_version_ms", ctypes.c_uint32),
            ("file_version_ls", ctypes.c_uint32),
            ("product_version_ms", ctypes.c_uint32),
            ("product_version_ls", ctypes.c_uint32),
            ("file_flags_mask", ctypes.c_uint32),
            ("file_flags", ctypes.c_uint32),
            ("file_os", ctypes.c_uint32),
            ("file_type", ctypes.c_uint32),
            ("file_subtype", ctypes.c_uint32),
            ("file_date_ms", ctypes.c_uint32),
            ("file_date_ls", ctypes.c_uint32),
        ]

    info = ctypes.cast(pointer, ctypes.POINTER(FixedFileInfo)).contents
    return ".".join(
        str(value)
        for value in (
            info.product_version_ms >> 16,
            info.product_version_ms & 0xFFFF,
            info.product_version_ls >> 16,
            info.product_version_ls & 0xFFFF,
        )
    )
