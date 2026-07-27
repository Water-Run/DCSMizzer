from __future__ import annotations

import hashlib
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any


LEGACY_SOURCE_COMMITS: dict[str, str] = {
    "briefing_room": "a5893db7daece0e2c25403c34a104057b7365a59",
    "gtd": "d58c7a38d3f0a681bde67bed21868b6d3ecd9bb8",
    "mission_maker": "48b2841b4f72ba32be217f3e618cfa3cec6c8f28",
    "retribution": "b7493d016f3c2c65d3a1ba73efdf0861d9c2dd7e",
    "moose": "27fa920a8fd49c589565f819ede31914254b9e9e",
    "pydcs": "412952c5ad5688783d8d53830280f316dbe311ff",
}


_PYDCS_PATHS: dict[str, tuple[str, ...]] = {
    "airports-by-theatre.json": ("dcs/terrain/*/airports.py",),
    "countries.json": ("dcs/countries.py",),
    "helicopters.json": ("dcs/helicopters.py",),
    "planes.json": ("dcs/planes.py",),
    "projections.json": ("dcs/terrain/*/projection.py",),
    "pydcs-beacons-module-head.txt": ("dcs/beacons.py",),
    "pydcs-cloud-presets.json": ("dcs/cloud_presets.py",),
    "pydcs-weather-module-notes.txt": ("dcs/weather.py",),
    "ships.json": ("dcs/ships.py",),
    "statics.json": ("dcs/statics.py",),
    "vehicles.json": ("dcs/vehicles.py",),
    "weapons-aam.json": ("dcs/weapons_data.py",),
    "weapons-agm-bomb.json": ("dcs/weapons_data.py",),
    "weapons-index.json": ("dcs/weapons_data.py",),
}

_RETRIBUTION_PATHS: dict[str, tuple[str, ...]] = {
    "retribution-aircraft-files.json": ("resources/units/aircraft/*.yaml",),
    "retribution-customized-payloads-index.json": (
        "resources/customized_payloads/*.lua",
    ),
    "retribution-customized-payloads-priority.json": (
        "resources/customized_payloads/*.lua",
    ),
    "retribution-factions-index.json": ("resources/factions/*.json",),
    "retribution-payloads-index.json": (
        "resources/payloads/_directory_for_payloads",
    ),
    "retribution-payloads-priority.json": (
        "resources/payloads/_directory_for_payloads",
    ),
    "retribution-theater-info.yaml.json": (
        "resources/theaters/*/info.yaml",
    ),
}

_GTD_PATHS: dict[str, tuple[str, ...]] = {
    "gtd-caucasus-airbases.json": ("src/caucasus/aerodromes.json",),
    "gtd-caucasus-beacons.json": ("src/caucasus/beacons.json",),
    "gtd-geojson-schema-head.txt": ("scripts/geojson.schema.json",),
}

_MISSION_MAKER_PATHS: dict[str, tuple[str, ...]] = {
    "mission-maker-callnames.json": ("src/me_db.ts",),
    "mission-maker-me-db-planes.json": ("src/me_db.ts",),
}


def build_legacy_reference_manifest(data_root: Path) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for path in sorted(data_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file():
            continue
        sources = _sources_for(path.name)
        if not sources:
            unmapped.append(path.name)
        content = path.read_bytes()
        datasets.append(
            {
                "path": path.name,
                "status": "legacy_frozen",
                "frozen_at": "2026-07-25T10:18:57+08:00",
                "extractor": "legacy-one-off/unavailable",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "sources": [
                    {
                        "project": project,
                        "commit": LEGACY_SOURCE_COMMITS[project],
                        "paths": list(paths),
                    }
                    for project, paths in sources
                ],
            }
        )
    return {
        "schema": "dcsmizzer.reference-provenance/v1",
        "status": "legacy_frozen_not_current",
        "datasets": datasets,
        "unmapped": unmapped,
    }


def validate_legacy_source_paths(
    manifest: dict[str, Any],
    repositories: dict[str, Path],
) -> list[str]:
    trees: dict[tuple[str, str], tuple[str, ...]] = {}
    missing: list[str] = []
    for dataset in manifest["datasets"]:
        for source in dataset["sources"]:
            project = source["project"]
            commit = source["commit"]
            repository = repositories.get(project)
            if repository is None:
                missing.append(f"{dataset['path']}:{project}:<repository>")
                continue
            tree_key = (project, commit)
            if tree_key not in trees:
                try:
                    completed = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(repository),
                            "ls-tree",
                            "-r",
                            "--name-only",
                            commit,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    trees[tree_key] = tuple(completed.stdout.splitlines())
                except (
                    OSError,
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                ):
                    missing.append(
                        f"{dataset['path']}:{project}:<commit:{commit}>"
                    )
                    continue
            tree = trees[tree_key]
            for pattern in source["paths"]:
                if not any(fnmatchcase(path, pattern) for path in tree):
                    missing.append(
                        f"{dataset['path']}:{project}:{pattern}"
                    )
    return sorted(missing)


def _sources_for(
    filename: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if filename in _PYDCS_PATHS:
        return (("pydcs", _PYDCS_PATHS[filename]),)
    if filename in _RETRIBUTION_PATHS:
        return (("retribution", _RETRIBUTION_PATHS[filename]),)
    if filename in _GTD_PATHS:
        return (("gtd", _GTD_PATHS[filename]),)
    if filename in _MISSION_MAKER_PATHS:
        return (("mission_maker", _MISSION_MAKER_PATHS[filename]),)
    if filename.startswith("briefing-room-"):
        return (("briefing_room", _briefing_room_paths(filename)),)
    if filename == "theatre-coverage-matrix.json":
        return (
            ("pydcs", ("dcs/terrain/*",)),
            ("briefing_room", ("Database/Theaters/*.ini",)),
            ("retribution", ("resources/theaters/*/info.yaml",)),
        )
    if filename == "upstream-survey-meta.json":
        return (
            (
                "briefing_room",
                (
                    "Database/Theaters/*.ini",
                    "DatabaseJSON/TheaterTerrainBounds/*.json",
                ),
            ),
            (
                "retribution",
                (
                    "resources/factions/*.json",
                    "resources/units/aircraft/*.yaml",
                ),
            ),
            (
                "moose",
                ("Moose Development/Moose/**/*.lua",),
            ),
        )
    return ()


def _briefing_room_paths(filename: str) -> tuple[str, ...]:
    if filename == "briefing-room-airbases.json":
        return ("DatabaseJSON/TheatersAirbases.json",)
    if filename == "briefing-room-default-unit-lists.json":
        return ("Database/DefaultUnitLists/*.ini",)
    if filename == "briefing-room-situations-index.json":
        return ("DatabaseJSON/Situations/*.json",)
    if filename == "briefing-room-spawn-points-index.json":
        return ("DatabaseJSON/TheaterSpawnPoints/*.json.gz",)
    if filename == "briefing-room-terrain-bounds.json":
        return ("DatabaseJSON/TheaterTerrainBounds/*.json",)
    if filename == "briefing-room-theaters.json":
        return (
            "Database/Theaters/*.ini",
            "DatabaseJSON/TheaterTerrainBounds/*.json",
        )
    if filename == "briefing-room-weapons-by-date.json":
        return ("DatabaseJSON/WeaponsByDate.json",)
    if filename == "briefing-room-weather-presets.json":
        return ("Database/WeatherPresets/*.ini",)
    unit_sources = {
        "briefing-room-unit-cars.json": "DatabaseJSON/UnitCars.json",
        "briefing-room-unit-helicopters.json": (
            "DatabaseJSON/UnitHelicopters.json"
        ),
        "briefing-room-unit-planes-summary.json": (
            "DatabaseJSON/UnitPlanes.json"
        ),
        "briefing-room-unit-planes.json": "DatabaseJSON/UnitPlanes.json",
        "briefing-room-unit-ships.json": "DatabaseJSON/UnitShips.json",
        "briefing-room-unitcarsbrinfo.json": (
            "DatabaseJSON/UnitCarsBRInfo.json"
        ),
        "briefing-room-unithelicoptersbrinfo.json": (
            "DatabaseJSON/UnitHelicoptersBRInfo.json"
        ),
        "briefing-room-unitplanesbrinfo.json": (
            "DatabaseJSON/UnitPlanesBRInfo.json"
        ),
        "briefing-room-unitshipsbrinfo.json": (
            "DatabaseJSON/UnitShipsBRInfo.json"
        ),
    }
    source = unit_sources.get(filename.casefold())
    return (source,) if source is not None else ()
