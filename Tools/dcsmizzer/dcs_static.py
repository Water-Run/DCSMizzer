from __future__ import annotations

import hashlib
import ctypes
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .lua import LuaDataError, LuaTable, parse_lua_bytes


_COUNTRY_ADD = re.compile(
    r"""\bcountry\s*:\s*add\s*\(\s*(['"])(?P<key>.*?)\1""",
    re.DOTALL,
)
_STATE = re.compile(r"""\bstate\s*=\s*(['"])(.*?)\1""")
_SELF_ID = re.compile(
    r"""\blocal\s+self_ID\s*=\s*(['"])(.*?)\1"""
)


def countries_report(dcs_root: Path) -> dict[str, Any]:
    path = dcs_root / "Scripts" / "Database" / "db_countries.lua"
    if not path.is_file():
        raise ValueError("DCS country source is missing")
    text = path.read_text(encoding="utf-8-sig")
    identifiers = [match.group("key") for match in _COUNTRY_ADD.finditer(text)]
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
        "duplicate_identifiers": duplicates,
    }


def payload_report(dcs_root: Path, unit_type: str) -> dict[str, Any]:
    root = (
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "UnitPayloads"
    )
    if not root.is_dir():
        raise ValueError("DCS default payload directory is missing")
    matches: list[dict[str, Any]] = []
    parse_failures = 0
    for path in sorted(root.glob("*.lua"), key=lambda item: item.name.casefold()):
        try:
            parsed = parse_lua_bytes(path.read_bytes())
            table = parsed.document.returned
            if not isinstance(table, LuaTable):
                table = parsed.document.get("unitPayloads")
            if not isinstance(table, LuaTable):
                parse_failures += 1
                continue
        except (OSError, LuaDataError):
            parse_failures += 1
            continue
        if table.get("name") != unit_type:
            continue
        for preset in _numeric_tables(table.get("payloads")):
            pylons: list[dict[str, Any]] = []
            for pylon in _numeric_tables(preset.get("pylons")):
                record: dict[str, Any] = {}
                clsid = pylon.get("CLSID")
                station = pylon.get("num")
                if isinstance(clsid, str):
                    record["CLSID"] = clsid
                if (
                    isinstance(station, (int, float))
                    and not isinstance(station, bool)
                ):
                    record["num"] = station
                pylons.append(record)
            tasks = [
                field.value
                for field in _table(preset.get("tasks")).numeric_items()
                if (
                    isinstance(field.value, (int, float))
                    and not isinstance(field.value, bool)
                )
            ]
            matches.append(
                {
                    "name": _string(preset.get("name")),
                    "display_name": _string(preset.get("displayName")),
                    "pylons": pylons,
                    "tasks": tasks,
                }
            )
    return {
        "schema": "dcsmizzer.dcs-default-payloads/v1",
        "authority": "current_install_static_default_presets",
        "dcs_started": False,
        "unit_type": unit_type,
        "compatibility_complete": False,
        "compatibility_warning": (
            "Default presets prove observed preset assignments only; they do "
            "not enumerate every store allowed on every station."
        ),
        "files_scanned": len(list(root.glob("*.lua"))),
        "parse_failures": parse_failures,
        "presets": matches,
    }


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
    payload_root = (
        dcs_root
        / "MissionEditor"
        / "data"
        / "scripts"
        / "UnitPayloads"
    )
    payload_files = len(list(payload_root.glob("*.lua"))) if payload_root.is_dir() else 0
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
        "default_payload_files": payload_files,
        "runtime_required_for": [
            "initialized unit registry",
            "complete task capability matrix",
            "complete store-to-station compatibility",
            "per-terrain airbase, runway, and parking registry",
            "mission load and Mission Editor resave validation",
        ],
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
        for field in _table(value).numeric_items()
        if isinstance(field.value, LuaTable)
    ]


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
