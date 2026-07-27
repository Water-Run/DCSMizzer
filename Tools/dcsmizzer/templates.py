"""Current-install-backed safe templates for authored MIZ core tables."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Sequence

from .lua import LuaTable, parse_lua_bytes


_AUDIO_DEVICE_FIELDS = (
    "hp_output",
    "main_output",
    "main_layout",
    "voice_chat_output",
    "voice_chat_input",
)
WAREHOUSE_COALITIONS = frozenset({"BLUE", "NEUTRAL", "RED"})
_FULL_SIM_DIFFICULTY = {
    "easyCommunication": False,
    "easyFlight": False,
    "fuel": False,
    "immortal": False,
    "labels": 0,
    "padlock": False,
    "radio": False,
    "weapons": False,
}
_WAREHOUSE_LITERAL_PATTERNS = {
    "unlimitedAircrafts": r"unlimitedAircrafts\s*=\s*true",
    "unlimitedFuel": r"unlimitedFuel\s*=\s*true",
    "unlimitedMunitions": r"unlimitedMunitions\s*=\s*true",
    "dynamicSpawn": r"dynamicSpawn\s*=\s*false",
    "allowHotStart": r"allowHotStart\s*=\s*false",
    "speed": r"speed\s*=\s*16\.666666\b",
    "periodicity": r"periodicity\s*=\s*30\b",
    "size": r"size\s*=\s*100\b",
    "jet_fuel": r"jet_fuel\.InitFuel\s*=\s*100\b",
    "gasoline": r"gasoline\.InitFuel\s*=\s*100\b",
    "methanol_mixture": r"methanol_mixture\.InitFuel\s*=\s*100\b",
    "diesel": r"diesel\.InitFuel\s*=\s*100\b",
    "OperatingLevel_Eqp": r"OperatingLevel_Eqp\s*=\s*10\b",
    "OperatingLevel_Air": r"OperatingLevel_Air\s*=\s*10\b",
    "OperatingLevel_Fuel": r"OperatingLevel_Fuel\s*=\s*10\b",
    "dynamicCargo": r"dynamicCargo\s*=\s*true",
}


def options_template_report(
    dcs_root: Path,
    *,
    player_name: str = "DCSMizzer",
    full_sim: bool = False,
) -> dict[str, Any]:
    """Parse the shipped data-only options table and sanitize local devices."""

    if (
        not isinstance(player_name, str)
        or not player_name.strip()
        or "\x00" in player_name
    ):
        raise ValueError("player name must be a nonempty string without NUL")
    source = (
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "options.lua"
    )
    if not source.is_file():
        raise ValueError("DCS Mission Editor options template is missing")
    parsed = parse_lua_bytes(source.read_bytes())
    options = parsed.document.get("options")
    if not isinstance(options, LuaTable):
        raise ValueError("DCS options source has no data-only options table")
    output = _lua_to_json(options)
    if not isinstance(output, dict) or "$fields" in output:
        raise ValueError("DCS options table is not string-keyed")

    sanitized: list[str] = []
    sound = output.get("sound")
    if not isinstance(sound, dict):
        raise ValueError("DCS options source has no sound table")
    for field_name in _AUDIO_DEVICE_FIELDS:
        if sound.get(field_name) not in {None, ""}:
            sanitized.append(field_name)
        sound[field_name] = ""
    output["playerName"] = player_name

    applied_overrides: dict[str, Any] = {}
    if full_sim:
        difficulty = output.get("difficulty")
        if not isinstance(difficulty, dict):
            raise ValueError("DCS options source has no difficulty table")
        for field_name, value in _FULL_SIM_DIFFICULTY.items():
            difficulty[field_name] = value
        applied_overrides = dict(_FULL_SIM_DIFFICULTY)

    return {
        "schema": "dcsmizzer.dcs-options-template/v1",
        "authority": "current_install_data_only_mission_editor_default",
        "dcs_started": False,
        "source": "MissionEditor/data/scripts/options.lua",
        "source_sha256": _sha256(source),
        "parser": {
            "data_only": True,
            "encoding": parsed.encoding,
            "lua_executed": False,
        },
        "policy": {
            "player_name": player_name,
            "full_sim": full_sim,
            "full_sim_overrides": applied_overrides,
            "audio_device_fields_forced_blank": list(_AUDIO_DEVICE_FIELDS),
            "source_audio_fields_sanitized": sanitized,
        },
        "options": output,
        "limitations": [
            "The table is the current installed editor default plus explicit "
            "reported policy edits; it is not copied from a user mission.",
            "The full-sim switch changes only the listed difficulty fields; "
            "views, map visibility, and other scenario policy remain explicit "
            "author decisions.",
            "Plugin-specific option requirements are not inferred.",
            "No Lua was executed and no DCS or Mission Editor process was "
            "started.",
        ],
    }


def warehouse_template_report(
    dcs_root: Path,
    airdrome_ids: Sequence[int],
    *,
    coalition: str = "NEUTRAL",
) -> dict[str, Any]:
    """Build bounded unlimited-stock airport records from verified literals."""

    if coalition not in WAREHOUSE_COALITIONS:
        raise ValueError(
            "warehouse coalition must be one of "
            f"{sorted(WAREHOUSE_COALITIONS)}"
        )
    selected: list[int] = []
    seen: set[int] = set()
    for identifier in airdrome_ids:
        if (
            not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or identifier < 0
        ):
            raise ValueError("airdrome IDs must be nonnegative integers")
        if identifier not in seen:
            selected.append(identifier)
            seen.add(identifier)
    if not selected:
        raise ValueError("at least one airdrome ID is required")

    source = dcs_root / "MissionEditor" / "modules" / "me_mission.lua"
    if not source.is_file():
        raise ValueError("DCS Mission Editor warehouse source is missing")
    text = source.read_text(encoding="utf-8-sig")
    missing_literals = [
        name
        for name, pattern in _WAREHOUSE_LITERAL_PATTERNS.items()
        if re.search(pattern, text) is None
    ]
    if missing_literals:
        raise ValueError(
            "current warehouse source no longer matches verified literals: "
            f"{missing_literals}"
        )

    fields = [
        {
            "key": identifier,
            "value": _unlimited_airport_warehouse(coalition),
        }
        for identifier in selected
    ]
    return {
        "schema": "dcsmizzer.dcs-warehouse-template/v1",
        "authority": "current_install_static_mission_editor_literals",
        "dcs_started": False,
        "source": "MissionEditor/modules/me_mission.lua",
        "source_sha256": _sha256(source),
        "source_code_executed": False,
        "verified_literal_groups": sorted(_WAREHOUSE_LITERAL_PATTERNS),
        "filters": {
            "airdrome_ids": selected,
            "coalition": coalition,
            "mode": "unlimited",
        },
        "warehouses": {
            "airports": {"$fields": fields},
            "warehouses": {},
        },
        "limitations": [
            "Airdrome IDs are caller-supplied and must first be verified by a "
            "terrain-specific pydcs or BriefingRoom airbase query.",
            "The unlimited template intentionally leaves aircraft and weapon "
            "inventory arrays empty; it does not reproduce the editor's "
            "runtime initialized resource registry.",
            "Warehouse coalition is an authored initial state and is not "
            "assumed to match the departure coalition.",
            "No Lua was executed and no DCS or Mission Editor process was "
            "started.",
        ],
    }


def _unlimited_airport_warehouse(coalition: str) -> dict[str, Any]:
    return {
        "OperatingLevel_Air": 10,
        "OperatingLevel_Eqp": 10,
        "OperatingLevel_Fuel": 10,
        "aircrafts": {"planes": {}, "helicopters": {}},
        "allowHotStart": False,
        "coalition": coalition,
        "diesel": {"InitFuel": 100},
        "dynamicCargo": True,
        "dynamicSpawn": False,
        "gasoline": {"InitFuel": 100},
        "jet_fuel": {"InitFuel": 100},
        "methanol_mixture": {"InitFuel": 100},
        "periodicity": 30,
        "size": 100,
        "speed": 16.666666,
        "suppliers": {},
        "unlimitedAircrafts": True,
        "unlimitedFuel": True,
        "unlimitedMunitions": True,
        "weapons": [],
    }


def _lua_to_json(value: Any) -> Any:
    if not isinstance(value, LuaTable):
        return value
    numeric = value.numeric_items()
    if len(numeric) == len(value.fields) and tuple(
        field.key for field in numeric
    ) == tuple(range(1, len(numeric) + 1)):
        return [_lua_to_json(field.value) for field in numeric]
    if all(isinstance(field.key, str) for field in value.fields):
        return {
            str(field.key): _lua_to_json(field.value)
            for field in value.fields
        }
    return {
        "$fields": [
            {
                "key": field.key,
                "value": _lua_to_json(field.value),
            }
            for field in value.fields
        ]
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
