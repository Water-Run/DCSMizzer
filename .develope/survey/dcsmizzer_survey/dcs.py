from __future__ import annotations

import ctypes
import hashlib
import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .lua import LuaDataError, LuaTable, parse_lua_bytes


_KV_TOKEN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')
_COUNTRY_ADD = re.compile(
    r"""\bcountry\s*:\s*add\s*\(\s*(['"])(?P<key>.*?)\1""",
    re.DOTALL,
)
_QUOTED_FIELDS = {
    "state": re.compile(r"""\bstate\s*=\s*(['"])(.*?)\1"""),
    "update_id": re.compile(r"""\bupdate_id\s*=\s*(['"])(.*?)\1"""),
}
_SELF_ID = re.compile(
    r"""\blocal\s+self_ID\s*=\s*(['"])(.*?)\1"""
)
_STATIC_PATTERNS: dict[str, bytes] = {
    "aircraft_registration_files": b"add_aircraft",
    "surface_unit_registration_files": b"add_surface_unit",
    "weapon_declaration_files": b"declare_weapon",
    "loadout_declaration_files": b"declare_loadout",
    "pylon_declaration_files": b"pylon(",
    "task_declaration_files": b"Tasks",
}


def parse_steam_appmanifest(text: str) -> dict[str, Any]:
    tokens: list[str] = []
    for match in _KV_TOKEN.finditer(text):
        if match.group(1) is not None:
            tokens.append(
                match.group(1).replace(r"\\", "\\").replace(r"\"", '"')
            )
        else:
            tokens.append(match.group(2))
    if not tokens:
        raise ValueError("Steam app manifest is empty")

    index = 0

    def parse_object() -> dict[str, Any]:
        nonlocal index
        result: dict[str, Any] = {}
        while index < len(tokens) and tokens[index] != "}":
            key = tokens[index]
            index += 1
            if key in {"{", "}"} or index >= len(tokens):
                raise ValueError("malformed Steam app manifest")
            if tokens[index] == "{":
                index += 1
                value: Any = parse_object()
                if index >= len(tokens) or tokens[index] != "}":
                    raise ValueError("unterminated Steam app manifest object")
                index += 1
            else:
                value = tokens[index]
                index += 1
            result[key] = value
        return result

    root = parse_object()
    if "AppState" in root and isinstance(root["AppState"], dict):
        app_state = root["AppState"]
    elif (
        len(tokens) >= 2
        and tokens[0] == "AppState"
        and tokens[1] == "{"
    ):
        index = 2
        app_state = parse_object()
    else:
        app_state = root

    depots: list[dict[str, str]] = []
    raw_depots = app_state.get("InstalledDepots", {})
    if isinstance(raw_depots, dict):
        for depot_id, raw_depot in sorted(raw_depots.items()):
            if not isinstance(raw_depot, dict):
                continue
            depot = {"depot_id": depot_id}
            for field in ("manifest", "size", "dlcappid"):
                value = raw_depot.get(field)
                if isinstance(value, str):
                    depot[field] = value
            depots.append(depot)

    public: dict[str, Any] = {}
    for field in (
        "appid",
        "name",
        "installdir",
        "lastupdated",
        "SizeOnDisk",
        "buildid",
        "UpdateResult",
        "TargetBuildID",
    ):
        value = app_state.get(field)
        if isinstance(value, str):
            public[_snake_case(field)] = value
    public["installed_depots"] = depots
    return public


def survey_dcs_installation(
    dcs_root: Path,
    steam_manifest: Path,
    *,
    collected_at: datetime,
    version_reader: Callable[[Path], str] | None = None,
    official_release: dict[str, str] | None = None,
) -> dict[str, Any]:
    if collected_at.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    executable = dcs_root / "bin" / "DCS.exe"
    if not executable.is_file():
        raise ValueError("DCS executable is missing")
    if not steam_manifest.is_file():
        raise ValueError("Steam app manifest is missing")
    reader = version_reader or read_windows_product_version
    product_version = reader(executable)

    countries_path = dcs_root / "Scripts" / "Database" / "db_countries.lua"
    countries = _inspect_countries(countries_path)
    payloads = _inspect_payload_presets(
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "UnitPayloads"
    )
    modules = {
        "aircraft": _module_inventory(dcs_root / "Mods" / "aircraft"),
        "terrains": _module_inventory(dcs_root / "Mods" / "terrains"),
        "campaigns": _module_inventory(dcs_root / "Mods" / "campaigns"),
    }
    static_definitions = _inspect_static_definitions(dcs_root)
    airfield_sources = _inspect_airfield_sources(
        dcs_root / "Mods" / "terrains"
    )
    steam = parse_steam_appmanifest(
        steam_manifest.read_text(encoding="utf-8-sig")
    )

    terrain_names = [
        item["directory"]
        for item in modules["terrains"]
    ]
    release_cross_check: dict[str, Any]
    if official_release is None:
        release_cross_check = {"status": "not_recorded"}
    else:
        required_release_fields = {"version", "release_date", "url"}
        if set(official_release) != required_release_fields:
            raise ValueError(
                "official release needs version, release_date, and url"
            )
        release_cross_check = {
            **official_release,
            "status": (
                "matches_official_release"
                if official_release["version"] == product_version
                else "version_mismatch"
            ),
        }
    return {
        "schema": "dcsmizzer.dcs-installation-survey/v1",
        "collected_at": collected_at.isoformat(),
        "dcs": {
            "edition": "Steam",
            "product_version": product_version,
            "executable_sha256": _sha256(executable),
        },
        "steam": steam,
        "release_cross_check": release_cross_check,
        "installed_module_directories": modules,
        "countries": countries,
        "payload_presets": payloads,
        "static_definition_evidence": static_definitions,
        "airfield_static_evidence": airfield_sources,
        "coverage": {
            "installed_modules": {
                "status": "filesystem_and_entry_state_verified",
                "limitation": (
                    "Directory presence and entry.lua state do not prove "
                    "account entitlement or runtime activation."
                ),
            },
            "country_identifiers": {
                "status": "current_install_static_source_verified",
                "source": "Scripts/Database/db_countries.lua",
                "count": countries["count"],
            },
            "unit_type_registry": {
                "status": "runtime_registry_export_required",
                "reason": (
                    "Definitions are executable plugin Lua assembled by DCS; "
                    "static file presence is not the initialized registry."
                ),
            },
            "task_capabilities": {
                "status": "runtime_registry_export_required",
                "reason": (
                    "Task tables and per-unit capabilities are resolved in "
                    "the initialized Mission Editor database."
                ),
            },
            "weapon_pylon_compatibility": {
                "status": "runtime_registry_export_required",
                "presets_are_compatibility": False,
                "verified_preset_files": payloads["parsed"],
                "reason": (
                    "UnitPayloads are exact default presets, but they are not "
                    "the authoritative store-to-station compatibility matrix."
                ),
            },
            "airbases_runways_parking": {
                "status": "per_terrain_runtime_export_required",
                "terrains": terrain_names,
                "reason": (
                    "Installed terrain packages do not expose a complete "
                    "uniform plaintext airfield database; DCS runtime APIs "
                    "must be queried for each terrain."
                ),
            },
        },
        "authority_order": [
            "initialized DCS/Mission Editor database at recorded version",
            "current installed DCS static source where data-only",
            "current parsed missions for observed compatibility",
            "commit-bound upstream references",
            "legacy frozen reference snapshots",
        ],
    }


def read_windows_product_version(executable: Path) -> str:
    if not hasattr(ctypes, "windll"):
        raise OSError("Windows version API is unavailable")

    size = ctypes.windll.version.GetFileVersionInfoSizeW(
        str(executable),
        None,
    )
    if size == 0:
        raise OSError("DCS executable has no readable version resource")
    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(
        str(executable),
        0,
        size,
        buffer,
    ):
        raise OSError("failed to read DCS executable version resource")

    value_pointer = ctypes.c_void_p()
    value_length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(
        buffer,
        "\\",
        ctypes.byref(value_pointer),
        ctypes.byref(value_length),
    ):
        raise OSError("DCS executable fixed version info is missing")

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

    info = ctypes.cast(
        value_pointer,
        ctypes.POINTER(FixedFileInfo),
    ).contents
    return ".".join(
        str(value)
        for value in (
            info.product_version_ms >> 16,
            info.product_version_ms & 0xFFFF,
            info.product_version_ls >> 16,
            info.product_version_ls & 0xFFFF,
        )
    )


def _inspect_countries(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("DCS country database is missing")
    text = path.read_text(encoding="utf-8-sig")
    identifiers = [match.group("key") for match in _COUNTRY_ADD.finditer(text)]
    duplicates = sorted(
        key for key, count in Counter(identifiers).items() if count > 1
    )
    return {
        "source": "Scripts/Database/db_countries.lua",
        "source_sha256": _sha256(path),
        "calls": len(identifiers),
        "count": len(set(identifiers)),
        "identifiers": identifiers,
        "duplicate_identifiers": duplicates,
    }


def _inspect_payload_presets(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*.lua")) if root.is_dir() else []
    encodings: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    parsed = 0
    presets = 0
    pylon_assignments = 0
    clsids: set[str] = set()
    task_ids: set[int | float] = set()

    for path in files:
        try:
            result = parse_lua_bytes(path.read_bytes())
            table = result.document.returned
            if not isinstance(table, LuaTable):
                table = result.document.get("unitPayloads")
            if not isinstance(table, LuaTable):
                raise ValueError("unitPayloads table is missing")
            parsed += 1
            encodings[result.encoding] += 1
            payload_table = table.get("payloads")
            for payload in _numeric_tables(payload_table):
                presets += 1
                for pylon in _numeric_tables(payload.get("pylons")):
                    pylon_assignments += 1
                    clsid = pylon.get("CLSID")
                    if isinstance(clsid, str) and clsid:
                        clsids.add(clsid)
                tasks = payload.get("tasks")
                if isinstance(tasks, LuaTable):
                    for field in tasks.numeric_items():
                        if (
                            isinstance(field.value, (int, float))
                            and not isinstance(field.value, bool)
                        ):
                            task_ids.add(field.value)
        except (OSError, LuaDataError, ValueError) as error:
            failures[type(error).__name__] += 1

    return {
        "source": "MissionEditor/data/scripts/UnitPayloads/*.lua",
        "files": len(files),
        "parsed": parsed,
        "encodings": dict(sorted(encodings.items())),
        "failures": dict(sorted(failures.items())),
        "presets": presets,
        "pylon_assignments": pylon_assignments,
        "unique_clsids": len(clsids),
        "task_ids": sorted(task_ids),
    }


def _module_inventory(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for directory in sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.name.casefold(),
    ):
        entry = directory / "entry.lua"
        record: dict[str, Any] = {
            "directory": directory.name,
            "entry_present": entry.is_file(),
            "declared_state": None,
            "self_ids": [],
            "update_ids": [],
        }
        if entry.is_file():
            try:
                text = entry.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                text = ""
            state = _QUOTED_FIELDS["state"].search(text)
            record["declared_state"] = state.group(2) if state else None
            record["self_ids"] = sorted(
                {match.group(2) for match in _SELF_ID.finditer(text)}
            )
            record["update_ids"] = sorted(
                {
                    match.group(2)
                    for match in _QUOTED_FIELDS["update_id"].finditer(text)
                }
            )
        result.append(record)
    return result


def _inspect_static_definitions(dcs_root: Path) -> dict[str, int]:
    counts = {key: 0 for key in _STATIC_PATTERNS}
    counts["lua_files"] = 0
    for relative_root in ("Scripts", "CoreMods", "Mods"):
        root = dcs_root / relative_root
        if not root.is_dir():
            continue
        for path in root.rglob("*.lua"):
            try:
                content = path.read_bytes()
            except OSError:
                continue
            counts["lua_files"] += 1
            for key, marker in _STATIC_PATTERNS.items():
                if marker in content:
                    counts[key] += 1
    return counts


def _inspect_airfield_sources(terrain_root: Path) -> list[dict[str, Any]]:
    if not terrain_root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    markers = ("airport", "airfield", "runway", "parking")
    for terrain in sorted(
        (item for item in terrain_root.iterdir() if item.is_dir()),
        key=lambda item: item.name.casefold(),
    ):
        candidates = 0
        for path in terrain.rglob("*"):
            if (
                path.is_file()
                and path.suffix.casefold() in {".lua", ".json"}
                and any(marker in path.name.casefold() for marker in markers)
            ):
                candidates += 1
        result.append(
            {
                "terrain": terrain.name,
                "plaintext_candidate_files": candidates,
            }
        )
    return result


def _numeric_tables(value: Any) -> list[LuaTable]:
    if not isinstance(value, LuaTable):
        return []
    return [
        field.value
        for field in value.numeric_items()
        if isinstance(field.value, LuaTable)
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snake_case(value: str) -> str:
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()
