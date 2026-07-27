"""Current-install evidence for MiG-29 ground-controlled interception."""

from __future__ import annotations

import hashlib
import math
import re
import zipfile
from pathlib import Path
from typing import Any

from .facts import CATEGORIES, numeric_tables, numeric_values, table
from .lua import LuaDataError, LuaTable, parse_lua_bytes


GCI_STATION_TYPE = "GCI_station_MiG29"
GCI_ACTION_ID = "ActivateGCI"
GCI_RADAR_LINK_RADIUS_METERS = 250_000
GCI_MAX_INTERCEPTORS_PER_CHANNEL = 24

# Exact current internal type names corresponding to the compatible radar list
# in the installed MiG-29A manual, pages 177-181. The two EWR entries are also
# present in the installed official GCI training mission.
GCI_COMPATIBLE_RADARS: dict[str, int] = {
    "P14_SR": 400_000,
    "p-19 s-125 sr": 160_000,
    "FPS-117": 460_000,
    "FPS-117 Dome": 460_000,
    "55G6 EWR": 400_000,
    "1L13 EWR": 300_000,
    "CHAP_IRISTSLM_STR": 250_000,
    "Patriot str": 200_000,
    "S-300PS 40B6MD sr": 150_000,
    "RLS_19J6": 150_000,
    "S-300PS 64H6E sr": 160_000,
    "SA-11 Buk SR 9S18M1": 120_000,
}

_GT_NAME = re.compile(
    r"\bGT\.Name\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)\s*;"
)
_GT_COUNTRIES = re.compile(
    r"\bGT\.Countries\s*=\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_SHORT_STRING = re.compile(r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)")


def gci_evidence_report(dcs_root: Path) -> dict[str, Any]:
    """Return compact current-install GCI construction evidence."""

    root = dcs_root.resolve()
    if not root.is_dir():
        raise ValueError("DCS root does not exist or is not a directory")

    declarations = _station_declarations(root)
    training_root = (
        root
        / "Mods"
        / "aircraft"
        / "MiG-29-Fulcrum"
        / "Missions"
        / "Training"
    )
    observations: list[dict[str, Any]] = []
    training_seen = 0
    training_parsed = 0
    if training_root.is_dir():
        for path in sorted(training_root.rglob("*.miz")):
            training_seen += 1
            observation = _training_observation(path)
            if observation is None:
                continue
            training_parsed += 1
            if observation["activate_gci_actions"]:
                observations.append(observation)

    manual = (
        root
        / "Mods"
        / "aircraft"
        / "MiG-29-Fulcrum"
        / "Doc"
        / "DCS MiG-29A Flight Manual EN.pdf"
    )
    manual_source = (
        _relative(manual, root) if manual.is_file() else None
    )
    manual_sha256 = _sha256(manual) if manual.is_file() else None

    task_chains = sorted(
        {
            tuple(chain)
            for observation in observations
            for chain in observation["task_chains"]
        }
    )
    parameter_field_sets = sorted(
        {
            tuple(fields)
            for observation in observations
            for fields in observation["parameter_field_sets"]
        }
    )
    channels = sorted(
        {
            channel
            for observation in observations
            for channel in observation["channels"]
        }
    )
    radii = sorted(
        {
            radius
            for observation in observations
            for radius in observation["radii_m"]
        }
    )
    country_ids = sorted(
        {
            country_id
            for observation in observations
            for country_id in observation["station_country_ids"]
        }
    )
    radar_types = sorted(
        {
            unit_type
            for observation in observations
            for unit_type in observation["compatible_radar_types"]
        }
    )

    return {
        "schema": "dcsmizzer.dcs-mig29-gci/v1",
        "authority": (
            "current_install_static_declaration_official_training_and_manual"
        ),
        "dcs_started": False,
        "coverage": {
            "matching_station_declarations": len(declarations),
            "training_miz_seen": training_seen,
            "training_miz_parsed": training_parsed,
            "gci_training_missions_observed": len(observations),
        },
        "station_declarations": declarations,
        "official_training_observations": {
            "station_type": GCI_STATION_TYPE,
            "activate_gci_action": GCI_ACTION_ID,
            "activate_gci_actions": sum(
                observation["activate_gci_actions"]
                for observation in observations
            ),
            "task_chains": [list(value) for value in task_chains],
            "parameter_field_sets": [
                list(value) for value in parameter_field_sets
            ],
            "channels": channels,
            "radii_m": radii,
            "station_country_ids": country_ids,
            "compatible_radar_types": radar_types,
        },
        "construction_requirements": {
            "station_unit_type": GCI_STATION_TYPE,
            "activate_action_id": GCI_ACTION_ID,
            "activate_action_parameters": [
                "unitId",
                "channel",
                "radius",
                "x",
                "y",
            ],
            "task_chain": ["ComboTask", "WrappedAction", GCI_ACTION_ID],
            "compatible_radar_link_radius_m": (
                GCI_RADAR_LINK_RADIUS_METERS
            ),
            "compatible_radars": [
                {
                    "unit_type": unit_type,
                    "manual_detection_range_m": detection_range,
                }
                for unit_type, detection_range in GCI_COMPATIBLE_RADARS.items()
            ],
            "maximum_interceptors_per_channel": (
                GCI_MAX_INTERCEPTORS_PER_CHANNEL
            ),
            "player_guidance_supported": True,
            "ai_guidance_supported": False,
        },
        "manual": {
            "source": manual_source,
            "source_sha256": manual_sha256,
            "relevant_printed_pages": [177, 178, 179, 180, 181],
        },
        "limitations": [
            "The construction requirements are bound to the installed "
            "MiG-29A manual and official training mission surveyed on "
            "2026-07-28.",
            "The compatible-radar internal names are current static names; "
            "future DCS versions may change the list or identifiers.",
            "Static structure cannot prove line of sight, terrain masking, "
            "radio reception, target assignment, or gameplay behavior.",
            "The installed manual states that instrument GCI guides players, "
            "not AI aircraft.",
            "No Lua code was executed and no DCS or Mission Editor process "
            "was started.",
        ],
    }


def gci_report_complete(report: dict[str, Any]) -> bool:
    """Return whether the current-install report has both evidence layers."""

    coverage = report["coverage"]
    return bool(
        coverage["matching_station_declarations"]
        and coverage["gci_training_missions_observed"]
    )


def _station_declarations(root: Path) -> list[dict[str, Any]]:
    search_root = root / "CoreMods" / "tech"
    if not search_root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(search_root.rglob("GCI_station_MAZ.lua")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        name_match = _GT_NAME.search(text)
        if name_match is None or name_match.group("value") != GCI_STATION_TYPE:
            continue
        countries_match = _GT_COUNTRIES.search(text)
        countries = (
            [
                match.group("value")
                for match in _SHORT_STRING.finditer(
                    countries_match.group("body")
                )
            ]
            if countries_match is not None
            else []
        )
        result.append(
            {
                "unit_type": GCI_STATION_TYPE,
                "countries": countries,
                "source": _relative(path, root),
                "source_sha256": _sha256(path),
            }
        )
    return result


def _training_observation(path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(path) as archive:
            data = archive.read("mission")
        if (
            GCI_STATION_TYPE.encode("ascii") not in data
            or GCI_ACTION_ID.encode("ascii") not in data
        ):
            return None
        parsed = parse_lua_bytes(data)
    except (
        KeyError,
        OSError,
        zipfile.BadZipFile,
        LuaDataError,
    ):
        return None
    mission = parsed.document.get("mission")
    if not isinstance(mission, LuaTable):
        return None

    units = _mission_units(mission)
    station_ids = {
        unit["unit_id"]
        for unit in units
        if unit["unit_type"] == GCI_STATION_TYPE
    }
    station_country_ids = sorted(
        {
            unit["country_id"]
            for unit in units
            if (
                unit["unit_type"] == GCI_STATION_TYPE
                and _is_number(unit["country_id"])
            )
        }
    )
    actions = _activate_gci_actions(mission)
    matched_actions = [
        action
        for action in actions
        if action["unit_id"] in station_ids
    ]
    return {
        "activate_gci_actions": len(matched_actions),
        "task_chains": [
            action["task_chain"] for action in matched_actions
        ],
        "parameter_field_sets": [
            action["parameter_fields"] for action in matched_actions
        ],
        "channels": [
            action["channel"]
            for action in matched_actions
            if isinstance(action["channel"], int)
            and not isinstance(action["channel"], bool)
        ],
        "radii_m": [
            action["radius"]
            for action in matched_actions
            if _is_number(action["radius"])
        ],
        "station_country_ids": station_country_ids,
        "compatible_radar_types": sorted(
            {
                unit["unit_type"]
                for unit in units
                if unit["unit_type"] in GCI_COMPATIBLE_RADARS
            }
        ),
    }


def _mission_units(mission: LuaTable) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country_value in numeric_values(side.get("country")):
            country = table(country_value)
            country_id = country.get("id")
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group_value in numeric_values(category_table.get("group")):
                    group = table(group_value)
                    for unit in numeric_tables(group.get("units")):
                        unit_type = unit.get("type")
                        if not isinstance(unit_type, str):
                            continue
                        result.append(
                            {
                                "unit_id": unit.get("unitId"),
                                "unit_type": unit_type,
                                "country_id": country_id,
                            }
                        )
    return result


def _activate_gci_actions(mission: LuaTable) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country_value in numeric_values(side.get("country")):
            country = table(country_value)
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group_value in numeric_values(category_table.get("group")):
                    group = table(group_value)
                    route = table(group.get("route"))
                    for point in numeric_tables(route.get("points")):
                        _collect_gci_actions(
                            point.get("task"),
                            chain=(),
                            output=result,
                        )
    return result


def _collect_gci_actions(
    value: Any,
    *,
    chain: tuple[str, ...],
    output: list[dict[str, Any]],
) -> None:
    if not isinstance(value, LuaTable):
        return
    task_id = value.get("id")
    next_chain = (
        (*chain, task_id) if isinstance(task_id, str) else chain
    )
    if task_id == GCI_ACTION_ID:
        params = value.get("params")
        if isinstance(params, LuaTable):
            output.append(
                {
                    "unit_id": params.get("unitId"),
                    "channel": params.get("channel"),
                    "radius": params.get("radius"),
                    "parameter_fields": sorted(
                        str(field.key) for field in params.fields
                    ),
                    "task_chain": list(next_chain),
                }
            )
    for field in value.fields:
        if isinstance(field.value, LuaTable):
            _collect_gci_actions(
                field.value,
                chain=next_chain,
                output=output,
            )


def compatible_radar_distance(
    station: dict[str, Any],
    radar: dict[str, Any],
) -> float | None:
    """Return planar distance when both records have finite coordinates."""

    station_x = station.get("x")
    station_y = station.get("y")
    radar_x = radar.get("x")
    radar_y = radar.get("y")
    if not all(
        _is_number(value)
        for value in (station_x, station_y, radar_x, radar_y)
    ):
        return None
    return math.hypot(radar_x - station_x, radar_y - station_y)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
