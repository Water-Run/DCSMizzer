"""Current-install, data-only weather preset evidence."""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .dcs_static import _windows_product_version
from .lua import (
    LuaDataError,
    LuaEncodingError,
    LuaLimitError,
    LuaLimits,
    LuaSyntaxError,
    LuaTable,
    parse_lua_bytes,
)


_PRESET_HEADER = re.compile(
    r"^(?P<indent>[ \t]+)(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)"
    r"[ \t]*=[ \t]*\r?$",
    re.MULTILINE,
)
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_MAX_WEATHER_SOURCE_FILES = 128
_MAX_WEATHER_PRESET_BYTES = 512 * 1024
_MAX_ME_WEATHER_BYTES = 2 * 1024 * 1024
_MAX_CLOUD_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_WEATHER_RESULTS = _MAX_WEATHER_SOURCE_FILES
_WEATHER_LUA_LIMITS = LuaLimits(
    max_input_bytes=_MAX_WEATHER_PRESET_BYTES,
    max_depth=64,
    max_nodes=100_000,
    max_string_chars=8192,
)
_EXPECTED_PRECIPITATION_NAMES = (
    "NONE",
    "RAIN",
    "THUNDERSTORM",
    "SNOW",
    "SNOWSTORM",
)
_EXPECTED_FOG_MODE_NAMES = ("off", "auto", "manual")
_LOCALIZED_NAME_FIELDS = (
    ("default", "name"),
    ("chinese", "name_cn"),
    ("russian", "name_ru"),
    ("german", "name_de"),
    ("spanish", "name_es"),
    ("french", "name_fr"),
)
_SUPPORTED_VDATA_FIELDS = frozenset(
    {
        "atmosphere_type",
        "clouds",
        "cyclones",
        "dust_density",
        "enable_dust",
        "fog2",
        "groundTurbulence",
        "name",
        "name_cn",
        "name_de",
        "name_es",
        "name_fr",
        "name_ru",
        "qnh",
        "season",
        "visibility",
        "wind",
    }
)
_CYCLONE_FIELDS = (
    "pressure_spread",
    "centerZ",
    "groupId",
    "ellipticity",
    "rotation",
    "pressure_excess",
    "centerX",
)
_MAX_SELECTED_CYCLONES = 32


def cloud_preset_report(
    dcs_root: Path,
    *,
    preset: str | None = None,
) -> dict[str, Any]:
    """List literal GUI cloud-preset IDs without executing DCS Lua."""

    source = dcs_root / "Config" / "Effects" / "clouds.lua"
    try:
        payload = _read_bounded_regular_file(
            source,
            maximum_bytes=_MAX_CLOUD_SOURCE_BYTES,
        )
        text = payload.decode("utf-8-sig")
    except FileNotFoundError as error:
        raise ValueError("DCS cloud preset source is missing") from error
    except UnicodeDecodeError as error:
        raise ValueError("DCS cloud preset source is not valid UTF-8") from error
    except OSError as error:
        raise ValueError(
            "DCS cloud preset source cannot be read safely"
        ) from error
    records: list[dict[str, Any]] = []
    malformed = 0
    for match in _PRESET_HEADER.finditer(text):
        opening = _next_nonspace(text, match.end())
        if opening is None or text[opening] != "{":
            continue
        try:
            closing = _matching_brace(text, opening)
        except ValueError:
            malformed += 1
            continue
        body = text[opening + 1 : closing]
        if (
            re.search(r"\bpresetAltMin\s*=", body) is None
            or re.search(r"\bpresetAltMax\s*=", body) is None
            or re.search(r"\blayers\s*=", body) is None
        ):
            continue
        identifier = match.group("identifier")
        record: dict[str, Any] = {
            "id": identifier,
            "visible_in_gui": _boolean_field(body, "visibleInGUI"),
            "readable_name_short": _translated_string_field(
                body,
                "readableNameShort",
            ),
            "precipitation_power": _number_field(
                body,
                "precipitationPower",
            ),
            "base_altitude_range": {
                "minimum": _number_field(body, "presetAltMin"),
                "maximum": _number_field(body, "presetAltMax"),
            },
        }
        thumbnail = _quoted_field(body, "thumbnailName")
        if thumbnail is not None:
            record["thumbnail"] = thumbnail
        records.append(record)

    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = record["id"]
        if identifier in unique:
            raise ValueError("DCS cloud source contains duplicate preset IDs")
        unique[identifier] = record
    selected = [
        record
        for identifier, record in sorted(unique.items())
        if preset is None or identifier == preset
    ]
    return {
        "schema": "dcsmizzer.dcs-cloud-presets/v1",
        "authority": "current_install_static_cloud_source",
        "dcs_started": False,
        "source": "Config/Effects/clouds.lua",
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "filter": {"preset": preset},
        "coverage": {
            "literal_presets": len(unique),
            "matching_presets": len(selected),
            "malformed_candidate_blocks": malformed,
        },
        "presets": selected,
        "limitations": [
            "Only literal cloud blocks with altitude bounds and layers in the "
            "installed Config/Effects/clouds.lua were parsed.",
            "The report does not execute getCloudsPresets.lua or prove that a "
            "preset will render identically on every terrain.",
            "Wind, fog, visibility, temperature, QNH, and turbulence remain "
            "separate mission weather fields.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def weather_constraints_report(dcs_root: Path) -> dict[str, Any]:
    """Extract Mission Editor weather rules without importing its Lua module."""

    source = dcs_root / "MissionEditor" / "modules" / "me_weather.lua"
    if not source.exists():
        raise ValueError("DCS Mission Editor weather source is missing")
    try:
        payload = _read_bounded_regular_file(
            source,
            maximum_bytes=_MAX_ME_WEATHER_BYTES,
        )
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(
            "DCS Mission Editor weather source is not valid UTF-8"
        ) from error
    except OSError as error:
        raise ValueError(
            "DCS Mission Editor weather source cannot be read safely"
        ) from error

    literal_text, code_text = _lua_lexical_views(text)
    precipitation = _extract_precipitation_constraints(
        literal_text,
        code_text,
    )
    fog_modes = _extract_fog_modes(code_text)
    dust_minimum = _extract_dust_minimum(code_text)
    fog_off = next(
        (item["id"] for item in fog_modes if item["name"] == "off"),
        None,
    )
    exclusion_off = _extract_fog_dust_exclusion(code_text)
    if fog_off is None or exclusion_off != fog_off:
        raise ValueError(
            "DCS fog and dust exclusion no longer matches the fog mode table"
        )
    temperature_ranges = _extract_temperature_ranges(code_text)
    terrain_override = (
        re.search(
            r"\bTerrain\.getTempratureRangeByDate\b",
            code_text,
        )
        is not None
    )
    if not terrain_override:
        raise ValueError(
            "DCS terrain/date temperature override evidence is missing"
        )

    product_version = _installed_product_version(dcs_root)
    return {
        "schema": "dcsmizzer.dcs-weather-constraints/v1",
        "authority": "current_install_static_mission_editor_source",
        "dcs_started": False,
        "dcs": {
            "product_version": product_version,
        },
        "source": "MissionEditor/modules/me_weather.lua",
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "constraints": {
            "precipitation_types": precipitation,
            "fog_modes": fog_modes,
            "fog_dust_mutually_exclusive": True,
            "dust": {
                "minimum_density_when_enabled": dust_minimum,
            },
            "temperature": {
                "fallback_ranges_c": temperature_ranges,
                "terrain_date_override_available": True,
            },
        },
        "source_evidence": [
            {
                "constraint": "precipitation_type_and_eligibility",
                "symbols": ["precptns", "getPrecptns", "precptnsList"],
            },
            {
                "constraint": "fog_mode_ids",
                "symbols": ["createFogPanel", "modeId"],
            },
            {
                "constraint": "fog_dust_mutual_exclusion",
                "symbols": ["fixFog", "enable_dust"],
            },
            {
                "constraint": "dust_minimum_when_enabled",
                "symbols": ["createDustPanel", "dust_density"],
            },
            {
                "constraint": "temperature_fallback_and_terrain_override",
                "symbols": ["temperatures", "getTempratureRangeByDate"],
            },
        ],
        "limitations": [
            "Rules were extracted from literal structures and control-flow "
            "guards in the installed MissionEditor/modules/me_weather.lua; "
            "the module was not imported or executed.",
            "Terrain.getTempratureRangeByDate can replace the static -50 to "
            "50 degree fallback at runtime for a mission date and terrain.",
            "Widget-only ranges, rendered cloud behavior, and terrain-specific "
            "weather effects are not proven by this source.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def validate_weather_consistency(
    weather: Mapping[str, Any] | LuaTable,
    constraints_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate supplied weather fields against extracted ME constraints."""

    if not _is_table_like(weather):
        raise ValueError("weather must be a table")
    if constraints_report.get("schema") != (
        "dcsmizzer.dcs-weather-constraints/v1"
    ):
        raise ValueError("unsupported weather constraints schema")
    constraints = constraints_report.get("constraints")
    if not isinstance(constraints, Mapping):
        raise ValueError("weather constraints are missing")
    precipitation_items = constraints.get("precipitation_types")
    fog_items = constraints.get("fog_modes")
    dust_constraints = constraints.get("dust")
    if (
        not isinstance(precipitation_items, list)
        or not isinstance(fog_items, list)
        or not isinstance(dust_constraints, Mapping)
    ):
        raise ValueError("weather constraints have an invalid shape")

    precipitation_by_id: dict[int, Mapping[str, Any]] = {}
    for item in precipitation_items:
        if not isinstance(item, Mapping):
            raise ValueError("weather precipitation constraint is invalid")
        identifier = item.get("id")
        if not _is_integer(identifier) or identifier in precipitation_by_id:
            raise ValueError("weather precipitation IDs are invalid")
        precipitation_by_id[identifier] = item
    fog_ids = {
        item.get("id")
        for item in fog_items
        if isinstance(item, Mapping) and _is_integer(item.get("id"))
    }
    if len(fog_ids) != len(fog_items):
        raise ValueError("weather fog mode constraints are invalid")

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    evaluated: set[str] = set()
    clouds = _optional_table(weather, "clouds", errors)
    season = _optional_table(weather, "season", errors)
    fog = _optional_table(weather, "fog2", errors)

    if clouds is not None and _table_has(clouds, "iprecptns"):
        evaluated.add("clouds.iprecptns")
        precipitation_id = _table_get(clouds, "iprecptns")
        if not _is_integer(precipitation_id):
            _add_issue(
                errors,
                "invalid_precipitation_type",
                "clouds.iprecptns",
                "must be an integer precipitation ID",
            )
        elif precipitation_id not in precipitation_by_id:
            _add_issue(
                errors,
                "unknown_precipitation_type",
                "clouds.iprecptns",
                "must match an extracted Mission Editor precipitation ID",
            )
        else:
            precipitation = precipitation_by_id[precipitation_id]
            _validate_precipitation_dependencies(
                clouds,
                season,
                precipitation,
                errors,
                evaluated,
            )

    fog_mode: Any = None
    if fog is not None and _table_has(fog, "mode"):
        evaluated.add("fog2.mode")
        fog_mode = _table_get(fog, "mode")
        if not _is_integer(fog_mode) or fog_mode not in fog_ids:
            _add_issue(
                errors,
                "unknown_fog_mode",
                "fog2.mode",
                "must match an extracted Mission Editor fog mode ID",
            )

    dust_enabled: Any = False
    if _table_has(weather, "enable_dust"):
        evaluated.add("enable_dust")
        dust_enabled = _table_get(weather, "enable_dust")
        if not isinstance(dust_enabled, bool):
            _add_issue(
                errors,
                "invalid_enable_dust",
                "enable_dust",
                "must be a boolean",
            )
            dust_enabled = False
    if dust_enabled is True:
        if (
            fog_mode is not None
            and _is_integer(fog_mode)
            and fog_mode in fog_ids
            and fog_mode != _fog_off_id(fog_items)
        ):
            _add_issue(
                errors,
                "fog_dust_mutually_exclusive",
                "enable_dust",
                "cannot be enabled while fog mode is not off",
            )
        evaluated.add("dust_density")
        dust_density = _table_get(weather, "dust_density")
        minimum = dust_constraints.get("minimum_density_when_enabled")
        if not _is_number(dust_density):
            _add_issue(
                errors,
                "invalid_dust_density",
                "dust_density",
                "must be numeric when dust is enabled",
            )
        elif not _is_number(minimum):
            raise ValueError("weather dust minimum constraint is invalid")
        elif dust_density < minimum:
            _add_issue(
                errors,
                "dust_density_below_minimum",
                "dust_density",
                "must meet the Mission Editor minimum when dust is enabled",
            )
    elif (
        _table_has(weather, "dust_density")
        and _is_number(_table_get(weather, "dust_density"))
        and _table_get(weather, "dust_density") != 0
    ):
        evaluated.add("dust_density")
        _add_issue(
            warnings,
            "inactive_dust_density",
            "dust_density",
            "is ignored by this check while dust is disabled",
        )

    return {
        "schema": "dcsmizzer.weather-consistency/v1",
        "authority": "provided_current_install_constraints",
        "constraint_source_sha256": constraints_report.get("source_sha256"),
        "consistent": not errors,
        "evaluated_fields": sorted(evaluated),
        "errors": errors,
        "warnings": warnings,
    }


def weather_registry_report(
    dcs_root: Path,
    *,
    preset: str | None = None,
    limit: int = _MAX_WEATHER_RESULTS,
) -> dict[str, Any]:
    """Parse the installed default weather presets as bounded data-only Lua."""

    if preset is not None:
        if (
            not isinstance(preset, str)
            or not preset
            or len(preset) > 256
            or "\x00" in preset
            or "\r" in preset
            or "\n" in preset
        ):
            raise ValueError("preset filter must be a bounded exact ID")
    if (
        not _is_integer(limit)
        or limit < 1
        or limit > _MAX_WEATHER_RESULTS
    ):
        raise ValueError(
            f"limit must be an integer from 1 to {_MAX_WEATHER_RESULTS}"
        )
    root = (
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "weather"
    )
    if not root.is_dir():
        raise ValueError("DCS default weather preset directory is missing")

    sources = _weather_source_files(root)
    if not sources:
        raise ValueError("DCS default weather presets are missing")
    if len(sources) > _MAX_WEATHER_SOURCE_FILES:
        raise ValueError(
            "DCS default weather source count exceeds the safety limit"
        )
    constraints_report = weather_constraints_report(dcs_root)
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for relative, source, kind in sources:
        try:
            payload = _read_bounded_regular_file(
                source,
                maximum_bytes=_MAX_WEATHER_PRESET_BYTES,
            )
            parsed = parse_lua_bytes(
                payload,
                limits=_WEATHER_LUA_LIMITS,
            )
            vdata = parsed.document.get("vdata")
            if not isinstance(vdata, LuaTable):
                raise ValueError("weather preset does not define a vdata table")
            record = _weather_preset_record(
                relative,
                kind,
                payload,
                parsed.encoding,
                vdata,
                parsed.document.get("dtime"),
                constraints_report,
            )
        except (OSError, LuaDataError, ValueError) as error:
            failures.append(
                {
                    "source": relative,
                    "error_code": _weather_error_code(error),
                }
            )
            continue
        records.append(record)

    selected = [
        item
        for item in records
        if preset is None or item["id"] == preset
    ]
    returned = selected[:limit]
    static_count = sum(item["kind"] == "static" for item in records)
    dynamic_count = len(records) - static_count
    fields_complete_count = sum(
        item["validation"].get("fields_complete") is True
        for item in records
    )
    consistent_count = sum(
        item["validation"].get("consistent") is True
        for item in records
    )
    usable_count = sum(
        item["validation"].get("fields_complete") is True
        and item["validation"].get("consistent") is True
        for item in records
    )
    return {
        "schema": "dcsmizzer.dcs-weather-presets/v1",
        "authority": "current_install_static_weather_sources",
        "dcs_started": False,
        "dcs": constraints_report["dcs"],
        "sources": {
            "preset_directory": (
                "MissionEditor/data/scripts/weather"
            ),
            "constraint_source": constraints_report["source"],
            "constraint_source_sha256": constraints_report["source_sha256"],
        },
        "filter": {
            "preset": preset,
            "limit": limit,
        },
        "coverage": {
            "source_files": len(sources),
            "parsed_presets": len(records),
            "parse_failures": len(failures),
            "static_presets": static_count,
            "dynamic_presets": dynamic_count,
            "fields_complete_presets": fields_complete_count,
            "fields_incomplete_presets": (
                len(records) - fields_complete_count
            ),
            "consistent_presets": consistent_count,
            "usable_presets": usable_count,
            "matching_presets": len(selected),
            "returned_presets": len(returned),
            "truncated": len(returned) < len(selected),
        },
        "constraints": constraints_report["constraints"],
        "presets": returned,
        "parse_failures": failures,
        "limitations": [
            "Only direct regular files in the installed default static and "
            "dynamic weather directories were parsed as data-only Lua.",
            "User Saved Games weather presets were not searched by this "
            "current-install report.",
            "Preset data and Mission Editor constraints do not prove runtime "
            "rendering, terrain/date temperature acceptance, or DCS mission "
            "load success.",
            "A preset is usable only when its supported field view is complete, "
            "untruncated, and consistent with the extracted constraints.",
            "No preset Lua, DCS, or Mission Editor code was executed.",
        ],
    }


def _lua_lexical_views(text: str) -> tuple[str, str]:
    """Return comment-free literals and code with comments/strings masked."""

    literal = list(text)
    code = list(text)
    index = 0
    while index < len(text):
        if text.startswith("--", index):
            opening = _lua_long_bracket(text, index + 2)
            if opening is not None:
                opener_end, equals = opening
                closing = "]" + ("=" * equals) + "]"
                found = text.find(closing, opener_end)
                if found < 0:
                    raise ValueError(
                        "DCS weather source has an unterminated long comment"
                    )
                end = found + len(closing)
            else:
                newline = text.find("\n", index + 2)
                end = len(text) if newline < 0 else newline
            _mask_lua_range(literal, index, end)
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
            if found < 0:
                raise ValueError(
                    "DCS weather source has an unterminated long string"
                )
            end = found + len(closing)
            _mask_lua_range(code, index, end)
            index = end
            continue
        index += 1
    return "".join(literal), "".join(code)


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
    raise ValueError("DCS weather source has an unterminated short string")


def _mask_lua_range(target: list[str], start: int, end: int) -> None:
    for index in range(start, min(end, len(target))):
        if target[index] not in {"\r", "\n"}:
            target[index] = " "


def _extract_translated_literal_list(
    literal_text: str,
    code_text: str,
    name: str,
) -> tuple[str, ...]:
    body, body_code = _literal_assignment_body(
        literal_text,
        code_text,
        name,
    )
    pattern = re.compile(
        r"_\(\s*(?P<quote>['\"])(?P<name>[A-Z]+)(?P=quote)\s*\)"
    )
    names = [
        match.group("name")
        for match in pattern.finditer(body)
        if body_code[match.start()] == "_"
    ]
    return tuple(names)


def _extract_precipitation_constraints(
    literal_text: str,
    code_text: str,
) -> list[dict[str, Any]]:
    body, body_code = _literal_assignment_body(
        literal_text,
        code_text,
        "precptns",
    )
    entry_pattern = re.compile(
        r"\{\s*name\s*=\s*_\(\s*"
        r"(?P<quote>['\"])(?P<name>[A-Z]+)(?P=quote)\s*\)"
        r"(?P<body>.*?)\}",
        re.DOTALL,
    )
    entries: list[dict[str, Any]] = []
    for match in entry_pattern.finditer(body):
        if body_code[match.start()] != "{":
            continue
        entry_code = body_code[
            match.start("body") : match.end("body")
        ]
        record: dict[str, Any] = {
            "id": len(entries),
            "name": match.group("name"),
            "minimum_density": _number_field(
                entry_code,
                "minDensity",
            ),
            "minimum_temperature_c": _number_field(
                entry_code,
                "minTemp",
            ),
            "maximum_temperature_c": _number_field(
                entry_code,
                "maxTemp",
            ),
        }
        entries.append(record)
    entry_names = tuple(item["name"] for item in entries)
    list_names = _extract_translated_literal_list(
        literal_text,
        code_text,
        "precptnsList",
    )
    if (
        entry_names != _EXPECTED_PRECIPITATION_NAMES
        or list_names != entry_names
    ):
        raise ValueError(
            "DCS precipitation type and ID tables could not be mapped exactly"
        )
    required_guards = (
        r"\bv\.minDensity\s*<=\s*density\b",
        r"\bv\.minTemp\s*<=\s*temp\b",
        r"\bv\.maxTemp\s*>=\s*temp\b",
        r"\bprecptnsList\s*\[\s*vdata\.clouds\.iprecptns\s*\+\s*1\s*\]",
    )
    if any(
        re.search(pattern, code_text) is None
        for pattern in required_guards
    ):
        raise ValueError(
            "DCS precipitation eligibility guards could not be verified"
        )
    return entries


def _extract_fog_modes(code_text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"\bitem\s*=\s*ListBoxItem\.new\(\s*cdata\."
        r"(?P<name>off|auto|manual)\s*\)\s*"
        r"item\.modeId\s*=\s*(?P<id>\d+)",
        re.DOTALL,
    )
    modes = [
        {
            "id": int(match.group("id")),
            "name": match.group("name"),
        }
        for match in pattern.finditer(code_text)
    ]
    if (
        tuple(item["name"] for item in modes) != _EXPECTED_FOG_MODE_NAMES
        or len({item["id"] for item in modes}) != len(modes)
    ):
        raise ValueError("DCS fog mode table could not be mapped exactly")
    return modes


def _extract_dust_minimum(code_text: str) -> int | float:
    match = re.search(
        rf"\belseif\s+vdata\.dust_density\s*<\s*"
        rf"(?P<minimum>{_NUMBER})\s+then\s*"
        rf"vdata\.dust_density\s*=\s*(?P=minimum)\b",
        code_text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("DCS enabled-dust minimum could not be verified")
    return _normalized_number(match.group("minimum"))


def _extract_fog_dust_exclusion(code_text: str) -> int:
    match = re.search(
        r"\bif\s+a_data\.fog2\s+and\s+"
        r"a_data\.fog2\.mode\s*~=\s*(?P<off>\d+)\s+then\s*"
        r"a_data\.enable_dust\s*=\s*false\b",
        code_text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("DCS fog and dust exclusion could not be verified")
    return int(match.group("off"))


def _extract_temperature_ranges(
    code_text: str,
) -> list[dict[str, int | float]]:
    body, _body_code = _literal_assignment_body(
        code_text,
        code_text,
        "temperatures",
    )
    pattern = re.compile(
        rf"\[(?P<season>\d+)\]\s*=\s*\{{\s*"
        rf"min\s*=\s*(?P<minimum>{_NUMBER})\s*,\s*"
        rf"max\s*=\s*(?P<maximum>{_NUMBER})\s*,?\s*\}}"
    )
    ranges = [
        {
            "season_id": int(match.group("season")),
            "minimum": _normalized_number(match.group("minimum")),
            "maximum": _normalized_number(match.group("maximum")),
        }
        for match in pattern.finditer(body)
    ]
    if [item["season_id"] for item in ranges] != [1, 2, 3, 4]:
        raise ValueError(
            "DCS fallback temperature ranges could not be mapped exactly"
        )
    if any(item["minimum"] > item["maximum"] for item in ranges):
        raise ValueError("DCS fallback temperature range is inverted")
    return ranges


def _literal_assignment_body(
    literal_text: str,
    code_text: str,
    name: str,
) -> tuple[str, str]:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*",
        code_text,
    )
    if match is None:
        raise ValueError(f"DCS {name} literal table is missing")
    opening = _next_nonspace(code_text, match.end())
    if opening is None or code_text[opening] != "{":
        raise ValueError(f"DCS {name} literal table is malformed")
    try:
        closing = _matching_brace(code_text, opening)
    except ValueError as error:
        raise ValueError(f"DCS {name} literal table is malformed") from error
    return (
        literal_text[opening + 1 : closing],
        code_text[opening + 1 : closing],
    )


def _validate_precipitation_dependencies(
    clouds: Mapping[str, Any] | LuaTable,
    season: Mapping[str, Any] | LuaTable | None,
    precipitation: Mapping[str, Any],
    errors: list[dict[str, str]],
    evaluated: set[str],
) -> None:
    minimum_density = precipitation.get("minimum_density")
    if minimum_density is not None:
        evaluated.add("clouds.density")
        density = _table_get(clouds, "density")
        if not _is_number(density):
            _add_issue(
                errors,
                "missing_precipitation_density",
                "clouds.density",
                "must be numeric for the selected precipitation type",
            )
        elif not _is_number(minimum_density):
            raise ValueError("weather precipitation density constraint is invalid")
        elif density < minimum_density:
            _add_issue(
                errors,
                "precipitation_density_below_minimum",
                "clouds.density",
                "is below the selected precipitation type minimum",
            )

    minimum_temperature = precipitation.get("minimum_temperature_c")
    maximum_temperature = precipitation.get("maximum_temperature_c")
    if minimum_temperature is not None or maximum_temperature is not None:
        evaluated.add("season.temperature")
        temperature = (
            _table_get(season, "temperature")
            if season is not None
            else None
        )
        if not _is_number(temperature):
            _add_issue(
                errors,
                "missing_precipitation_temperature",
                "season.temperature",
                "must be numeric for the selected precipitation type",
            )
            return
        if minimum_temperature is not None:
            if not _is_number(minimum_temperature):
                raise ValueError(
                    "weather precipitation temperature constraint is invalid"
                )
            if temperature < minimum_temperature:
                _add_issue(
                    errors,
                    "precipitation_temperature_below_minimum",
                    "season.temperature",
                    "is below the selected precipitation type minimum",
                )
        if maximum_temperature is not None:
            if not _is_number(maximum_temperature):
                raise ValueError(
                    "weather precipitation temperature constraint is invalid"
                )
            if temperature > maximum_temperature:
                _add_issue(
                    errors,
                    "precipitation_temperature_above_maximum",
                    "season.temperature",
                    "is above the selected precipitation type maximum",
                )


def _optional_table(
    table: Mapping[str, Any] | LuaTable,
    key: str,
    errors: list[dict[str, str]],
) -> Mapping[str, Any] | LuaTable | None:
    if not _table_has(table, key):
        return None
    value = _table_get(table, key)
    if _is_table_like(value):
        return value
    _add_issue(
        errors,
        f"invalid_{key}_table",
        key,
        "must be a table when present",
    )
    return None


def _fog_off_id(items: list[Any]) -> int:
    for item in items:
        if isinstance(item, Mapping) and item.get("name") == "off":
            identifier = item.get("id")
            if _is_integer(identifier):
                return identifier
    raise ValueError("weather fog-off mode constraint is missing")


def _add_issue(
    issues: list[dict[str, str]],
    code: str,
    field: str,
    requirement: str,
) -> None:
    issues.append(
        {
            "code": code,
            "field": field,
            "requirement": requirement,
        }
    )


def _weather_source_files(
    root: Path,
) -> list[tuple[str, Path, str]]:
    candidates: list[tuple[str, Path, str]] = []
    for path in root.iterdir():
        if path.name == "dynamic":
            continue
        if path.is_file() or path.is_symlink():
            candidates.append((path.name, path, "static"))
    dynamic = root / "dynamic"
    if dynamic.is_dir():
        for path in dynamic.iterdir():
            if path.is_file() or path.is_symlink():
                relative = f"dynamic/{path.name}"
                candidates.append((relative, path, "dynamic"))
    return sorted(candidates, key=lambda item: item[0].casefold())


def _weather_field_integrity(
    vdata: LuaTable,
    *,
    kind: str,
) -> dict[str, Any]:
    missing: list[str] = []
    invalid: list[str] = []
    unsupported: list[str] = []
    truncated: list[str] = []

    def field_path(prefix: str, key: Any) -> str:
        if isinstance(key, str):
            return f"{prefix}.{key}"
        return f"{prefix}[{str(key)[:128]}]"

    def reject_unknown(
        table: LuaTable,
        *,
        prefix: str,
        allowed: set[str] | frozenset[str],
    ) -> None:
        for field in table.fields:
            if not isinstance(field.key, str) or field.key not in allowed:
                unsupported.append(field_path(prefix, field.key))

    def table_field(
        table: LuaTable,
        name: str,
        *,
        prefix: str,
        required: bool,
    ) -> LuaTable | None:
        path = f"{prefix}.{name}"
        if not table.has(name):
            if required:
                missing.append(path)
            return None
        value = table.get(name)
        if not isinstance(value, LuaTable):
            invalid.append(path)
            return None
        _reject_duplicate_table_keys(value, path)
        return value

    def numeric_field(
        table: LuaTable,
        name: str,
        *,
        prefix: str,
        required: bool = True,
        integer: bool = False,
    ) -> None:
        path = f"{prefix}.{name}"
        if not table.has(name):
            if required:
                missing.append(path)
            return
        value = table.get(name)
        valid = _is_integer(value) if integer else _is_finite_number(value)
        if not valid:
            invalid.append(path)

    reject_unknown(
        vdata,
        prefix="vdata",
        allowed=_SUPPORTED_VDATA_FIELDS,
    )
    if not vdata.has("name"):
        missing.append("vdata.name")
    elif (
        not isinstance(vdata.get("name"), str)
        or not vdata.get("name")
    ):
        invalid.append("vdata.name")
    for _output_name, source_name in _LOCALIZED_NAME_FIELDS:
        if source_name == "name" or not vdata.has(source_name):
            continue
        if not isinstance(vdata.get(source_name), str):
            invalid.append(f"vdata.{source_name}")

    numeric_field(vdata, "groundTurbulence", prefix="vdata")
    numeric_field(vdata, "qnh", prefix="vdata")

    season = table_field(
        vdata,
        "season",
        prefix="vdata",
        required=True,
    )
    if season is not None:
        reject_unknown(
            season,
            prefix="vdata.season",
            allowed={"temperature"},
        )
        numeric_field(season, "temperature", prefix="vdata.season")

    clouds = table_field(
        vdata,
        "clouds",
        prefix="vdata",
        required=True,
    )
    if clouds is not None:
        reject_unknown(
            clouds,
            prefix="vdata.clouds",
            allowed={
                "preset",
                "base",
                "thickness",
                "density",
                "iprecptns",
            },
        )
        for name in ("base", "thickness", "density"):
            numeric_field(clouds, name, prefix="vdata.clouds")
        numeric_field(
            clouds,
            "iprecptns",
            prefix="vdata.clouds",
            integer=True,
        )
        if clouds.has("preset") and not (
            clouds.get("preset") is None
            or isinstance(clouds.get("preset"), str)
        ):
            invalid.append("vdata.clouds.preset")

    visibility = table_field(
        vdata,
        "visibility",
        prefix="vdata",
        required=True,
    )
    if visibility is not None:
        reject_unknown(
            visibility,
            prefix="vdata.visibility",
            allowed={"distance"},
        )
        numeric_field(
            visibility,
            "distance",
            prefix="vdata.visibility",
        )

    wind = table_field(
        vdata,
        "wind",
        prefix="vdata",
        required=True,
    )
    wind_levels = ("atGround", "at2000", "at8000")
    if wind is not None:
        reject_unknown(
            wind,
            prefix="vdata.wind",
            allowed=set(wind_levels),
        )
        for level in wind_levels:
            level_table = table_field(
                wind,
                level,
                prefix="vdata.wind",
                required=True,
            )
            if level_table is None:
                continue
            prefix = f"vdata.wind.{level}"
            reject_unknown(
                level_table,
                prefix=prefix,
                allowed={"speed", "dir"},
            )
            numeric_field(level_table, "speed", prefix=prefix)
            numeric_field(level_table, "dir", prefix=prefix)

    if vdata.has("atmosphere_type"):
        numeric_field(
            vdata,
            "atmosphere_type",
            prefix="vdata",
            integer=True,
        )
    elif kind == "dynamic":
        missing.append("vdata.atmosphere_type")

    if vdata.has("enable_dust") and not isinstance(
        vdata.get("enable_dust"),
        bool,
    ):
        invalid.append("vdata.enable_dust")
    if vdata.has("dust_density") and not _is_finite_number(
        vdata.get("dust_density")
    ):
        invalid.append("vdata.dust_density")

    fog = table_field(
        vdata,
        "fog2",
        prefix="vdata",
        required=False,
    )
    if fog is not None:
        reject_unknown(fog, prefix="vdata.fog2", allowed={"mode"})
        numeric_field(
            fog,
            "mode",
            prefix="vdata.fog2",
            integer=True,
        )

    cyclones = table_field(
        vdata,
        "cyclones",
        prefix="vdata",
        required=kind == "dynamic",
    )
    if cyclones is not None:
        numeric_items = cyclones.numeric_items()
        if len(numeric_items) > _MAX_SELECTED_CYCLONES:
            truncated.append("vdata.cyclones")
        numeric_keys = {field.key for field in numeric_items}
        expected_keys = set(range(1, len(numeric_items) + 1))
        if numeric_keys != expected_keys:
            invalid.append("vdata.cyclones")
        for field in cyclones.fields:
            if field.key not in numeric_keys:
                unsupported.append(field_path("vdata.cyclones", field.key))
        for index, field in enumerate(numeric_items, start=1):
            prefix = f"vdata.cyclones[{index}]"
            if not isinstance(field.value, LuaTable):
                invalid.append(prefix)
                continue
            _reject_duplicate_table_keys(field.value, prefix)
            reject_unknown(
                field.value,
                prefix=prefix,
                allowed=set(_CYCLONE_FIELDS),
            )
            for name in _CYCLONE_FIELDS:
                numeric_field(field.value, name, prefix=prefix)

    missing = sorted(set(missing))
    invalid = sorted(set(invalid))
    unsupported = sorted(set(unsupported))
    truncated = sorted(set(truncated))
    return {
        "fields_complete": not (
            missing or invalid or unsupported or truncated
        ),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unsupported_fields": unsupported,
        "truncated_fields": truncated,
    }


def _weather_preset_record(
    relative: str,
    kind: str,
    payload: bytes,
    encoding: str,
    vdata: LuaTable,
    dtime: Any,
    constraints_report: Mapping[str, Any],
) -> dict[str, Any]:
    _reject_duplicate_table_keys(vdata, "vdata")
    identifier = (
        relative[:-4]
        if relative.casefold().endswith(".lua")
        else relative
    )
    names: dict[str, str] = {}
    for output_name, source_name in _LOCALIZED_NAME_FIELDS:
        value = vdata.get(source_name)
        if isinstance(value, str):
            names[output_name] = value
    field_integrity = _weather_field_integrity(vdata, kind=kind)
    weather = _selected_weather(vdata)
    validation = validate_weather_consistency(
        weather,
        constraints_report,
    )
    validation.update(field_integrity)
    record: dict[str, Any] = {
        "id": identifier,
        "kind": kind,
        "source": relative,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "encoding": encoding,
        "names": names,
        "weather": weather,
        "validation": validation,
    }
    selected_time = _selected_time(dtime)
    if selected_time:
        record["time"] = selected_time
    return record


def _selected_weather(vdata: LuaTable) -> dict[str, Any]:
    result: dict[str, Any] = {}
    _copy_scalar(vdata, result, "atmosphere_type")
    _copy_scalar(vdata, result, "groundTurbulence")
    _copy_scalar(vdata, result, "qnh")
    _copy_scalar(vdata, result, "enable_dust")
    _copy_scalar(vdata, result, "dust_density")

    season = _selected_fields(vdata.get("season"), ("temperature",))
    if season:
        result["season"] = season
    clouds = _selected_fields(
        vdata.get("clouds"),
        ("preset", "base", "thickness", "density", "iprecptns"),
    )
    if clouds:
        result["clouds"] = clouds
    visibility = _selected_fields(
        vdata.get("visibility"),
        ("distance",),
    )
    if visibility:
        result["visibility"] = visibility
    fog = _selected_fields(vdata.get("fog2"), ("mode",))
    if fog:
        result["fog2"] = fog

    wind_value = vdata.get("wind")
    if isinstance(wind_value, LuaTable):
        _reject_duplicate_table_keys(wind_value, "vdata.wind")
        wind: dict[str, Any] = {}
        for level in ("atGround", "at2000", "at8000"):
            selected = _selected_fields(
                wind_value.get(level),
                ("speed", "dir"),
            )
            if selected:
                wind[level] = selected
        if wind:
            result["wind"] = wind

    cyclones_value = vdata.get("cyclones")
    if isinstance(cyclones_value, LuaTable):
        cyclones: list[dict[str, Any]] = []
        for field in cyclones_value.numeric_items()[:_MAX_SELECTED_CYCLONES]:
            selected = _selected_fields(
                field.value,
                _CYCLONE_FIELDS,
            )
            if selected:
                cyclones.append(selected)
        result["cyclones"] = cyclones
        if len(cyclones_value.numeric_items()) > len(cyclones):
            result["cyclones_truncated"] = True
    return result


def _selected_time(value: Any) -> dict[str, Any]:
    if not isinstance(value, LuaTable):
        return {}
    result: dict[str, Any] = {}
    _copy_scalar(value, result, "start_time")
    date = _selected_fields(
        value.get("date"),
        ("Year", "Month", "Day"),
    )
    if date:
        result["date"] = date
    return result


def _selected_fields(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, LuaTable):
        return {}
    _reject_duplicate_table_keys(value, "weather subtable")
    result: dict[str, Any] = {}
    for name in names:
        _copy_scalar(value, result, name)
    return result


def _copy_scalar(
    source: LuaTable,
    target: dict[str, Any],
    name: str,
) -> None:
    if not source.has(name):
        return
    value = source.get(name)
    if (
        value is None
        or isinstance(value, (str, bool, int, float))
        and (not isinstance(value, float) or value == value)
    ):
        target[name] = value


def _reject_duplicate_table_keys(table: LuaTable, path: str) -> None:
    seen: set[str | int | float] = set()
    for field in table.fields:
        if field.key in seen:
            raise ValueError(f"{path} contains duplicate keys")
        seen.add(field.key)


def _weather_error_code(error: BaseException) -> str:
    if isinstance(error, LuaSyntaxError):
        return "lua_syntax_error"
    if isinstance(error, LuaLimitError):
        return "lua_limit_error"
    if isinstance(error, LuaEncodingError):
        return "lua_encoding_error"
    if isinstance(error, LuaDataError):
        return "lua_data_error"
    if isinstance(error, OSError):
        return "source_io_error"
    return "malformed_weather_preset"


def _read_bounded_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or _status_is_reparse(before):
        raise OSError("weather source is not a regular file")
    if before.st_size > maximum_bytes:
        raise OSError("weather source exceeds its byte limit")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _status_is_reparse(opened):
            raise OSError("weather source is not a regular file")
        if not _same_identity(before, opened):
            raise OSError("weather source changed before it was read")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum_bytes + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(payload) > maximum_bytes:
        raise OSError("weather source exceeds its byte limit")
    if not _same_identity(opened, after):
        raise OSError("weather source changed while it was read")
    final_path = path.lstat()
    if (
        not stat.S_ISREG(final_path.st_mode)
        or _status_is_reparse(final_path)
        or not _same_identity(opened, final_path)
    ):
        raise OSError("weather source path changed while it was read")
    return payload


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _status_is_reparse(status_result: os.stat_result) -> bool:
    attributes = getattr(status_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _installed_product_version(dcs_root: Path) -> str | None:
    executable = dcs_root / "bin" / "DCS.exe"
    if not executable.is_file():
        return None
    try:
        return _windows_product_version(executable)
    except OSError:
        return None


def _normalized_number(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or value == value)
    )


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_table_like(value: Any) -> bool:
    return isinstance(value, (Mapping, LuaTable))


def _table_has(table: Mapping[str, Any] | LuaTable, key: str) -> bool:
    if isinstance(table, LuaTable):
        return table.has(key)
    return key in table


def _table_get(
    table: Mapping[str, Any] | LuaTable | None,
    key: str,
) -> Any:
    if table is None:
        return None
    if isinstance(table, LuaTable):
        return table.get(key)
    return table.get(key)


def _matching_brace(text: str, opening: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    index = opening
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "-" and next_character == "-":
            newline = text.find("\n", index + 2)
            if newline == -1:
                break
            index = newline + 1
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unterminated cloud preset block")


def _next_nonspace(text: str, start: int) -> int | None:
    for index in range(start, len(text)):
        if not text[index].isspace():
            return index
    return None


def _number_field(body: str, field: str) -> int | float | None:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*(?P<value>{_NUMBER})",
        body,
    )
    if match is None:
        return None
    value = float(match.group("value"))
    return int(value) if value.is_integer() else value


def _boolean_field(body: str, field: str) -> bool | None:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*(?P<value>true|false)",
        body,
    )
    if match is None:
        return None
    return match.group("value") == "true"


def _quoted_field(body: str, field: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*(?P<quote>['\"])"
        r"(?P<value>.*?)(?P=quote)",
        body,
        re.DOTALL,
    )
    return _unescape(match.group("value")) if match else None


def _translated_string_field(body: str, field: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*_\(\s*(?P<quote>['\"])"
        r"(?P<value>.*?)(?P=quote)\s*\)",
        body,
        re.DOTALL,
    )
    return _unescape(match.group("value")) if match else None


def _unescape(value: str) -> str:
    return (
        value.replace("\\\\", "\0")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\0", "\\")
    )
