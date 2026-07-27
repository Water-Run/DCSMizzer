"""Safe, commit-bound queries over an acknowledged pydcs checkout.

The source files are parsed with :mod:`ast`; pydcs is never imported or
executed.  These reports are lower-authority upstream evidence and are meant
to complement, not replace, current installed DCS data.
"""

from __future__ import annotations

import ast
import hashlib
import ipaddress
import math
import re
import subprocess
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .coordinates import (
    ProjectionFit,
    _checked_latlon_to_map,
    _checked_map_to_latlon,
    _latlon_to_map,
    _map_to_latlon,
)
from .upstream_cache import upstream_source_lock_status


_PYLON_CLASS = re.compile(r"Pylon(?P<station>\d+)\Z")
_MINIMUM_BOUNDS_TOLERANCE_M = 1000.0
_BOUNDS_SPAN_TOLERANCE_RATIO = 0.001
_UNIT_SOURCE_FILES = {
    "plane": ("planes.py", "PlaneType"),
    "helicopter": ("helicopters.py", "HelicopterType"),
    "vehicle": ("vehicles.py", "VehicleType"),
    "ship": ("ships.py", "ShipType"),
    "static": ("statics.py", "StaticType"),
}


def pydcs_terrain_report(
    pydcs_root: Path,
    *,
    terrain: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    map_x: float | None = None,
    map_y: float | None = None,
) -> dict[str, Any]:
    """Catalog every terrain export and optionally convert one coordinate.

    This deliberately reads generated source with :mod:`ast` instead of
    importing pydcs.  It therefore works for terrain packages which are not
    installed in the user's current DCS tree, while retaining the lower
    authority of a commit-bound upstream export.
    """

    root = _validated_root(pydcs_root)
    upstream = _git_state(root)
    _validate_coordinate_query(
        terrain=terrain,
        latitude=latitude,
        longitude=longitude,
        map_x=map_x,
        map_y=map_y,
    )
    terrain_root = root / "dcs" / "terrain"
    packages = sorted(
        (
            path
            for path in terrain_root.iterdir()
            if path.is_dir()
            and (path / "airports.py").is_file()
            and (path / "projection.py").is_file()
        ),
        key=lambda path: path.name.casefold(),
    )

    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for package in packages:
        try:
            records.append(_terrain_package_record(root, package))
        except ValueError:
            unresolved.append(package.name)

    selected = [
        record
        for record in records
        if terrain is None
        or record["terrain_package"].casefold() == terrain.casefold()
        or record["terrain_class"].casefold() == terrain.casefold()
        or record["miz_theatre_name"].casefold() == terrain.casefold()
    ]
    duplicate_identities = _duplicate_terrain_identities(records)
    selected_keys = {
        (
            namespace,
            value.casefold(),
        )
        for record in selected
        for namespace, value in (
            ("terrain_package", record["terrain_package"]),
            ("terrain_class", record["terrain_class"]),
            ("miz_theatre_name", record["miz_theatre_name"]),
        )
        if isinstance(value, str)
    }
    selected_identity_ambiguous = any(
        (item["namespace"], item["normalized_identity"]) in selected_keys
        for item in duplicate_identities
    )
    unresolved_matching = (
        [
            package
            for package in unresolved
            if terrain is not None and package.casefold() == terrain.casefold()
        ]
        if terrain is not None
        else []
    )
    exact_query_usable = terrain is None or (
        len(selected) == 1
        and not selected_identity_ambiguous
        and not unresolved_matching
    )
    conversion: dict[str, Any] | None = None
    if terrain is not None and exact_query_usable:
        conversion = _pydcs_coordinate_conversion(
            selected[0],
            latitude=latitude,
            longitude=longitude,
            map_x=map_x,
            map_y=map_y,
        )

    return {
        "schema": "dcsmizzer.pydcs-terrains/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_generated_terrain_export",
        ),
        "dcs_started": False,
        "filters": {
            "terrain": terrain,
            "latitude": latitude,
            "longitude": longitude,
            "x": map_x,
            "y": map_y,
        },
        "upstream": upstream,
        "coverage": {
            "terrain_packages_discovered": len(packages),
            "terrain_packages_parsed": len(records),
            "terrain_packages_unresolved": unresolved,
            "matching_terrains": len(selected),
            "matching_unresolved_packages": unresolved_matching,
            "duplicate_identities": duplicate_identities,
            "selected_identity_ambiguous": selected_identity_ambiguous,
            "exact_query_usable": exact_query_usable,
            "airports_parsed": sum(
                record["airport_summary"]["airports_parsed"] for record in records
            ),
            "airport_parse_failures": sum(
                record["airport_summary"]["airport_parse_failures"]
                for record in records
            ),
            "parking_slots_parsed": sum(
                record["airport_summary"]["parking_slots"] for record in records
            ),
        },
        "terrains": selected,
        "conversion": conversion,
        "limitations": [
            "The catalog covers terrain packages present in the reported "
            "pydcs source snapshot; it is not a complete catalog of every current or "
            "announced DCS terrain.",
            "A listed terrain may be absent from the user's DCS installation "
            "or incompatible with the user's installed DCS version.",
            "Coordinate conversion uses the generated upstream projection "
            "parameters and was not independently fitted to current installed "
            "data for noninstalled terrains.",
            "declared_center_wgs84 is untrusted upstream class metadata. Its "
            "derived bounds diagnostic exposes placeholders and sign errors; "
            "it must not be treated as a verified map center.",
            "A converted point is not proof of terrain height, land cover, "
            "runway, parking, or unit-placement validity.",
            "Use pydcs-airports for exact airport, runway, and parking records.",
            "No Python from the upstream checkout was imported or executed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def pydcs_unit_report(
    pydcs_root: Path,
    *,
    unit_type: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Catalog or resolve exact unit declarations across all five categories."""

    root = _validated_root(pydcs_root)
    upstream = _git_state(root)
    if category is not None and category not in _UNIT_SOURCE_FILES:
        raise ValueError("unsupported pydcs unit category")
    if unit_type is not None and search is not None:
        raise ValueError("--unit-type and --search are mutually exclusive")
    if unit_type is not None and not unit_type:
        raise ValueError("--unit-type must not be empty")
    if search is not None and not search.strip():
        raise ValueError("--search must not be empty")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit < 1
        or limit > 100
    ):
        raise ValueError("--limit must be an integer from 1 to 100")

    selected_categories = (
        (category,) if category is not None else tuple(_UNIT_SOURCE_FILES)
    )
    indexes: dict[str, list[dict[str, Any]]] = {}
    sources: list[dict[str, Any]] = []
    for selected_category in selected_categories:
        filename, base_name = _UNIT_SOURCE_FILES[selected_category]
        source = root / "dcs" / filename
        if not source.is_file():
            raise ValueError(f"pydcs {selected_category} source is missing")
        indexes[selected_category] = _unit_declaration_index(
            source,
            category=selected_category,
            base_name=base_name,
        )
        sources.append(
            {
                "kind": selected_category,
                "source": source.relative_to(root).as_posix(),
                "source_sha256": _sha256(source),
            }
        )

    all_records = [
        record
        for selected_category in selected_categories
        for record in indexes[selected_category]
    ]
    exact_near_matches: list[dict[str, str]] = []
    if unit_type is not None:
        matches = [record for record in all_records if record["id"] == unit_type]
        exact_near_matches = [
            {
                "category": record["category"],
                "id": record["id"],
            }
            for record in all_records
            if record["id"] != unit_type
            and record["id"].casefold() == unit_type.casefold()
        ]
    elif search is not None:
        term = search.casefold()
        matches = [
            record
            for record in all_records
            if term in record["id"].casefold() or term in record["name"].casefold()
        ]
    else:
        matches = []

    returned = matches if unit_type is not None else matches[:limit]
    detailed = unit_type is not None
    output_units = [
        _unit_output_record(
            root,
            record,
            detailed=detailed,
        )
        for record in returned
    ]
    if detailed and any(
        record["category"] in {"plane", "helicopter"} for record in returned
    ):
        for filename, kind in (
            ("weapons_data.py", "weapons"),
            ("task.py", "tasks"),
        ):
            source = root / "dcs" / filename
            sources.append(
                {
                    "kind": kind,
                    "source": source.relative_to(root).as_posix(),
                    "source_sha256": _sha256(source),
                }
            )

    ids: dict[str, list[str]] = defaultdict(list)
    for record in all_records:
        ids[record["id"]].append(record["category"])
    duplicates = [
        {"id": identifier, "categories": categories}
        for identifier, categories in sorted(ids.items())
        if len(categories) > 1
    ]
    return {
        "schema": "dcsmizzer.pydcs-units/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_generated_unit_export",
        ),
        "dcs_started": False,
        "filters": {
            "unit_type": unit_type,
            "category": category,
            "search": search,
            "limit": limit,
        },
        "upstream": upstream,
        "sources": sources,
        "coverage": {
            "units_indexed": len(all_records),
            "units_by_category": {
                selected_category: len(indexes[selected_category])
                for selected_category in selected_categories
            },
            "duplicate_ids_across_selected_categories": duplicates,
            "matching_units": len(matches),
            "returned_units": len(output_units),
            "output_truncated": len(output_units) < len(matches),
            "case_only_near_matches": exact_near_matches,
        },
        "units": output_units,
        "limitations": [
            "The report covers generated declarations in the recorded pydcs "
            "commit; it is not the initialized registry of the user's current "
            "DCS version.",
            "An exact match does not prove country availability, module "
            "entitlement, activation, era suitability, AI behavior, or "
            "mission-load success.",
            "Flying-unit pylon and task detail is returned only for an exact "
            "--unit-type query.",
            "Use current installed default payloads and real-MIZ observations "
            "to cross-check selected flying-unit loadouts.",
            "No Python from the upstream checkout was imported or executed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def _resolve_pydcs_terrain_package(
    root: Path,
    query: str,
) -> tuple[Path, dict[str, str | None]]:
    """Resolve package, Terrain class, or declared MIZ theatre uniquely."""

    terrain_root = root / "dcs" / "terrain"
    packages = sorted(
        (path for path in terrain_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    direct = [
        package for package in packages if package.name.casefold() == query.casefold()
    ]
    if len(direct) > 1:
        raise ValueError("requested pydcs terrain package is ambiguous")
    identities: list[tuple[Path, dict[str, str | None]]] = []
    for package in packages:
        metadata = [
            record
            for source in package.glob("*.py")
            if source.name not in {"__init__.py", "airports.py", "projection.py"}
            and (record := _terrain_metadata(source)) is not None
        ]
        if len(metadata) != 1:
            if direct and package == direct[0]:
                return package, {
                    "terrain_package": package.name,
                    "terrain_class": None,
                    "miz_theatre_name": None,
                }
            continue
        record = metadata[0]
        identities.append(
            (
                package,
                {
                    "terrain_package": package.name,
                    "terrain_class": record["terrain_class"],
                    "miz_theatre_name": record["miz_theatre_name"],
                },
            )
        )
    folded = query.casefold()
    matches = [
        item
        for item in identities
        if any(
            isinstance(value, str) and value.casefold() == folded
            for value in item[1].values()
        )
    ]
    if not matches:
        raise ValueError(
            "requested pydcs terrain package/class/MIZ theatre does not exist"
        )
    if len(matches) != 1:
        raise ValueError(
            "requested pydcs terrain package/class/MIZ theatre is ambiguous"
        )
    return matches[0]


def _duplicate_terrain_identities(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    indexes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records:
        package = record["terrain_package"]
        for namespace, value in (
            ("terrain_package", package),
            ("terrain_class", record["terrain_class"]),
            ("miz_theatre_name", record["miz_theatre_name"]),
        ):
            indexes[(namespace, value.casefold())].append(package)
    return [
        {
            "namespace": namespace,
            "normalized_identity": normalized,
            "terrain_packages": sorted(packages, key=str.casefold),
        }
        for (namespace, normalized), packages in sorted(indexes.items())
        if len(packages) > 1
    ]


def pydcs_airport_report(
    pydcs_root: Path,
    terrain: str,
    *,
    airport: str | None = None,
    airdrome_id: int | None = None,
    parking: str | None = None,
    airplane_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read generated airport/runway/parking declarations without importing."""

    root = _validated_root(pydcs_root)
    upstream = _git_state(root)
    selected, terrain_identity = _resolve_pydcs_terrain_package(root, terrain)
    source = selected / "airports.py"
    if not source.is_file():
        raise ValueError("requested pydcs terrain has no airports.py")
    if parking is not None and airport is None and airdrome_id is None:
        raise ValueError("--parking requires --airport or --airdrome-id")
    if (airplane_only or limit is not None) and airport is None and airdrome_id is None:
        raise ValueError("--airplane-only/--limit requires --airport or --airdrome-id")
    if limit is not None and (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit < 1
        or limit > 100
    ):
        raise ValueError("--limit must be an integer from 1 to 100")

    tree = _parse_python(source)
    records: list[dict[str, Any]] = []
    parse_failures = 0
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _is_airport_class(node):
            continue
        values = _class_literal_assignments(node)
        identifier = values.get("id")
        name = values.get("name")
        if (
            not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or not isinstance(name, str)
            or not name
        ):
            parse_failures += 1
            continue
        try:
            record = _airport_class_record(node, identifier, name)
        except ValueError:
            parse_failures += 1
            continue
        if identifier in seen_ids or name in seen_names:
            raise ValueError("pydcs airport source contains duplicate IDs or names")
        seen_ids.add(identifier)
        seen_names.add(name)
        records.append(record)

    records.sort(key=lambda item: item["airdrome_id"])
    selected_records = [
        record
        for record in records
        if (
            (airport is None or record["name"].casefold() == airport.casefold())
            and (airdrome_id is None or record["airdrome_id"] == airdrome_id)
        )
    ]
    exact_filter = airport is not None or airdrome_id is not None
    result_airports: list[dict[str, Any]] = []
    parking_matches = 0
    returned_parking = 0
    for record in selected_records:
        output = {key: value for key, value in record.items() if key != "parking"}
        if exact_filter:
            selected_parking = [
                item
                for item in record["parking"]
                if (
                    (
                        parking is None
                        or str(item["crossroad_idx"]) == parking
                        or item["slot_name"] == parking
                    )
                    and (not airplane_only or item["airplanes"] is True)
                )
            ]
            parking_matches += len(selected_parking)
            if limit is not None:
                selected_parking = selected_parking[:limit]
            output["parking"] = selected_parking
            returned_parking += len(selected_parking)
        result_airports.append(output)

    relative = source.relative_to(root).as_posix()
    exact_query_usable = not exact_filter or (
        len(selected_records) == 1 and parse_failures == 0
    )
    exact_parking_usable = parking is None or (
        exact_query_usable and parking_matches == 1
    )
    return {
        "schema": "dcsmizzer.pydcs-airports/v1",
        "authority": _snapshot_authority(
            upstream,
            "upstream_generated_airport_export",
        ),
        "dcs_started": False,
        "source": relative,
        "source_sha256": _sha256(source),
        "upstream": upstream,
        "filters": {
            "terrain_query": terrain,
            "terrain_package": selected.name,
            "terrain_class": terrain_identity["terrain_class"],
            "miz_theatre_name": terrain_identity["miz_theatre_name"],
            "airport": airport,
            "airdrome_id": airdrome_id,
            "parking": parking,
            "airplane_only": airplane_only,
            "limit": limit,
        },
        "coverage": {
            "airports_parsed": len(records),
            "airport_parse_failures": parse_failures,
            "matching_airports": len(selected_records),
            "matching_parking_slots": parking_matches,
            "returned_parking_slots": returned_parking,
            "parking_output_truncated": returned_parking < parking_matches,
            "source_parse_complete": parse_failures == 0,
            "exact_airport_query_usable": exact_query_usable,
            "exact_parking_query_usable": exact_parking_usable,
        },
        "airports": result_airports,
        "limitations": [
            "The report parses generated pydcs declarations in the reported "
            "source snapshot; it is not an initialized export from the installed DCS "
            "runtime.",
            "Parking dimensions and airplane/heli flags are upstream export "
            "evidence, not proof that a particular aircraft will spawn there "
            "in the user's installed version.",
            "Cross-check airdrome ID/name against current installed radio or "
            "beacon sources and use real-MIZ observations when available.",
            "No Python from the upstream checkout was imported or executed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def pydcs_aircraft_report(
    pydcs_root: Path,
    unit_type: str,
    *,
    station: int | None = None,
    clsid: str | None = None,
) -> dict[str, Any]:
    """Read one generated plane declaration and resolve its pylon stores."""

    root = _validated_root(pydcs_root)
    upstream = _git_state(root)
    planes_source = root / "dcs" / "planes.py"
    weapons_source = root / "dcs" / "weapons_data.py"
    tasks_source = root / "dcs" / "task.py"
    if (
        not planes_source.is_file()
        or not weapons_source.is_file()
        or not tasks_source.is_file()
    ):
        raise ValueError("pydcs plane, weapon, or task source is missing")

    weapons, weapon_failures = _weapon_index(weapons_source)
    tasks = _task_index(tasks_source)
    plane_tree = _parse_python(planes_source)
    matching: list[ast.ClassDef] = []
    for node in plane_tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        values = _class_literal_assignments(node)
        if values.get("id") == unit_type:
            matching.append(node)
    if len(matching) > 1:
        raise ValueError("pydcs plane source contains a duplicate unit type")

    aircraft: dict[str, Any] | None = None
    compatibility_query: dict[str, Any] | None = None
    if matching:
        aircraft = _plane_class_record(matching[0], weapons, tasks)
        assignments = aircraft["pylon_assignments"]
        filtered = [
            item
            for item in assignments
            if (station is None or item["station"] == station)
            and (clsid is None or item.get("CLSID") == clsid)
        ]
        if station is not None or clsid is not None:
            compatibility_query = {
                "station": station,
                "CLSID": clsid,
                "matched": bool(filtered),
                "matches": filtered,
            }
            aircraft["pylon_assignments"] = filtered

    relative_planes = planes_source.relative_to(root).as_posix()
    relative_weapons = weapons_source.relative_to(root).as_posix()
    relative_tasks = tasks_source.relative_to(root).as_posix()
    return {
        "schema": "dcsmizzer.pydcs-aircraft/v2",
        "authority": _snapshot_authority(
            upstream,
            "upstream_generated_plane_weapon_export",
        ),
        "dcs_started": False,
        "unit_type": unit_type,
        "filters": {
            "station": station,
            "CLSID": clsid,
        },
        "sources": [
            {
                "source": relative_planes,
                "source_sha256": _sha256(planes_source),
            },
            {
                "source": relative_weapons,
                "source_sha256": _sha256(weapons_source),
            },
            {
                "source": relative_tasks,
                "source_sha256": _sha256(tasks_source),
            },
        ],
        "upstream": upstream,
        "coverage": {
            "matching_aircraft": len(matching),
            "weapon_records_resolved": len(weapons),
            "weapon_records_unresolved": weapon_failures,
            "main_task_records_resolved": len(tasks),
            "pylon_assignments_in_aircraft": (
                aircraft["pylon_assignment_count"] if aircraft else 0
            ),
            "unresolved_pylon_assignments": (
                aircraft["unresolved_pylon_assignments"] if aircraft else 0
            ),
            "unresolved_aircraft_tasks": (
                aircraft["unresolved_task_records"] if aircraft else 0
            ),
        },
        "compatibility_query": compatibility_query,
        "aircraft": aircraft,
        "limitations": [
            "The station/store relationship is generated pydcs evidence in "
            "the reported source snapshot, not an initialized registry from the "
            "installed DCS runtime.",
            "Cross-check selected assignments against current installed "
            "default payloads or version-matched real missions.",
            "A matching pylon declaration does not prove module entitlement, "
            "activation, or mission-load success.",
            "Use each task record's mission_group_task for group.task; the "
            "Python class and payload_internal_name are different namespaces.",
            "No Python from the upstream checkout was imported or executed.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def _terrain_package_record(root: Path, package: Path) -> dict[str, Any]:
    projection_source = package / "projection.py"
    airports_source = package / "airports.py"
    terrain_sources = sorted(
        path
        for path in package.glob("*.py")
        if path.name not in {"__init__.py", "airports.py", "projection.py"}
    )
    metadata: list[tuple[Path, dict[str, Any]]] = []
    for source in terrain_sources:
        parsed = _terrain_metadata(source)
        if parsed is not None:
            metadata.append((source, parsed))
    if len(metadata) != 1:
        raise ValueError("terrain package has no unique Terrain declaration")

    terrain_source, terrain = metadata[0]
    projection = _projection_parameters(projection_source)
    airport_summary = _airport_source_summary(
        airports_source,
        terrain["bounds"],
    )
    fit = ProjectionFit(
        central_meridian=projection["central_meridian"],
        scale_factor=projection["scale_factor"],
        false_easting=projection["false_easting"],
        false_northing=projection["false_northing"],
        rms_error_m=0.0,
        max_error_m=0.0,
    )
    origin_latitude, origin_longitude = _map_to_latlon(0.0, 0.0, fit)
    declared_center = terrain["center_wgs84"]
    declared_center_diagnostic: dict[str, Any] | None = None
    if declared_center is not None:
        center_x, center_y = _latlon_to_map(
            declared_center["latitude"],
            declared_center["longitude"],
            fit,
        )
        declared_center_diagnostic = {
            "derived_mission_local": {"x": center_x, "y": center_y},
            "within_declared_bounds": _point_within_bounds(
                terrain["bounds"],
                center_x,
                center_y,
            ),
            "independently_verified": False,
        }
    return {
        "terrain_package": package.name,
        "miz_theatre_name": terrain["miz_theatre_name"],
        "terrain_class": terrain["terrain_class"],
        "declared_center_wgs84": declared_center,
        "declared_center_diagnostic": declared_center_diagnostic,
        "bounds": terrain["bounds"],
        "declared_bounds_consistency": airport_summary["declared_bounds_consistency"],
        "projection": {
            "name": "WGS84 Transverse Mercator",
            **projection,
            "mission_origin_wgs84": {
                "latitude": origin_latitude,
                "longitude": origin_longitude,
            },
            "axis_mapping": {
                "mission_x": "projected_northing",
                "mission_y": "projected_easting",
            },
        },
        "airport_summary": airport_summary,
        "sources": [
            {
                "kind": "terrain",
                "source": terrain_source.relative_to(root).as_posix(),
                "source_sha256": _sha256(terrain_source),
            },
            {
                "kind": "projection",
                "source": projection_source.relative_to(root).as_posix(),
                "source_sha256": _sha256(projection_source),
            },
            {
                "kind": "airports",
                "source": airports_source.relative_to(root).as_posix(),
                "source_sha256": _sha256(airports_source),
            },
        ],
    }


def _unit_declaration_index(
    path: Path,
    *,
    category: str,
    base_name: str,
) -> list[dict[str, Any]]:
    tree = _parse_python(path)
    records: list[dict[str, Any]] = []

    def visit(statements: list[ast.stmt], namespace: tuple[str, ...]) -> None:
        for statement in statements:
            if not isinstance(statement, ast.ClassDef):
                continue
            declaration = (*namespace, statement.name)
            base_names = {
                _base_name(base)
                for base in statement.bases
                if _base_name(base) is not None
            }
            values = _class_literal_assignments(statement)
            identifier = values.get("id")
            if base_name in base_names and isinstance(identifier, str) and identifier:
                display_name = values.get("name")
                records.append(
                    {
                        "category": category,
                        "id": identifier,
                        "name": (
                            display_name
                            if isinstance(display_name, str) and display_name
                            else identifier
                        ),
                        "python_declaration": ".".join(declaration),
                        "source": path,
                        "node": statement,
                        "declared_values": values,
                    }
                )
            visit(statement.body, declaration)

    visit(tree.body, ())
    records.sort(key=lambda item: (item["id"], item["python_declaration"]))
    seen: set[str] = set()
    for record in records:
        if record["id"] in seen:
            raise ValueError(f"pydcs {category} source contains a duplicate unit ID")
        seen.add(record["id"])
    return records


def _unit_output_record(
    root: Path,
    record: dict[str, Any],
    *,
    detailed: bool,
) -> dict[str, Any]:
    category = record["category"]
    declared_values = record["declared_values"]
    scalar_names = (
        "flyable",
        "group_size_max",
        "large_parking_slot",
        "height",
        "width",
        "length",
        "fuel_max",
        "max_speed",
        "category",
        "detection_range",
        "threat_range",
        "air_weapon_dist",
        "eplrs",
        "plane_num",
        "helicopter_num",
        "parking",
        "shape_name",
        "rate",
        "sea_object",
        "can_cargo",
        "mass",
    )
    result: dict[str, Any] = {
        "unit_category": category,
        "id": record["id"],
        "name": record["name"],
        "python_declaration": record["python_declaration"],
        "source": record["source"].relative_to(root).as_posix(),
        "declared": {
            name: declared_values[name]
            for name in scalar_names
            if name in declared_values
        },
    }
    if not detailed or category not in {"plane", "helicopter"}:
        return result

    weapons_source = root / "dcs" / "weapons_data.py"
    tasks_source = root / "dcs" / "task.py"
    weapons, _failures = _weapon_index(weapons_source)
    tasks = _task_index(tasks_source)
    flying = _plane_class_record(record["node"], weapons, tasks)
    flying["unit_category"] = category
    result["flying_unit"] = flying
    return result


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _projection_parameters(path: Path) -> dict[str, int | float]:
    tree = _parse_python(path)
    parameters: ast.Call | None = None
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "PARAMETERS"
            and isinstance(statement.value, ast.Call)
            and _call_name(statement.value) == "TransverseMercator"
        ):
            parameters = statement.value
            break
    if parameters is None:
        raise ValueError("terrain projection has no literal PARAMETERS call")

    keyword_nodes = {
        item.arg: item.value for item in parameters.keywords if item.arg is not None
    }
    required = {
        "central_meridian",
        "false_easting",
        "false_northing",
        "scale_factor",
    }
    if not required.issubset(keyword_nodes):
        raise ValueError("terrain projection parameters are incomplete")
    values = {name: _number_expression(keyword_nodes[name]) for name in required}
    central_meridian = values["central_meridian"]
    if not float(central_meridian).is_integer():
        raise ValueError("terrain central meridian is not an integer")
    return {
        "central_meridian": int(central_meridian),
        "false_easting": values["false_easting"],
        "false_northing": values["false_northing"],
        "scale_factor": values["scale_factor"],
    }


def _terrain_metadata(path: Path) -> dict[str, Any] | None:
    tree = _parse_python(path)
    candidates: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not any(
            (isinstance(base, ast.Name) and base.id == "Terrain")
            or (isinstance(base, ast.Attribute) and base.attr == "Terrain")
            for base in node.bases
        ):
            continue
        initializer = next(
            (
                statement
                for statement in node.body
                if isinstance(statement, ast.FunctionDef)
                and statement.name == "__init__"
            ),
            None,
        )
        if initializer is None:
            continue
        super_calls = [
            call
            for call in ast.walk(initializer)
            if isinstance(call, ast.Call) and _is_super_init_call(call)
        ]
        if len(super_calls) != 1 or not super_calls[0].args:
            continue
        try:
            theatre = _literal(super_calls[0].args[0])
        except ValueError:
            continue
        if not isinstance(theatre, str) or not theatre:
            continue
        bounds_node = _call_argument(super_calls[0], 2, "bounds")
        if isinstance(bounds_node, ast.Name):
            bounds_node = _function_assignment(initializer, bounds_node.id)
        bounds = _rectangle(bounds_node) if bounds_node is not None else None
        center = _class_literal_assignments(node).get("center")
        center_wgs84 = (
            {
                "latitude": center["lat"],
                "longitude": center["long"],
            }
            if isinstance(center, dict)
            and _is_number(center.get("lat"))
            and _is_number(center.get("long"))
            else None
        )
        candidates.append(
            {
                "terrain_class": node.name,
                "miz_theatre_name": theatre,
                "center_wgs84": center_wgs84,
                "bounds": bounds,
            }
        )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("terrain source has multiple Terrain declarations")
    return candidates[0]


def _airport_source_summary(
    path: Path,
    bounds: dict[str, Any] | None,
) -> dict[str, Any]:
    tree = _parse_python(path)
    airports = 0
    failures = 0
    parking_slots = 0
    airplane_slots = 0
    helicopter_slots = 0
    airport_records: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _is_airport_class(node):
            continue
        values = _class_literal_assignments(node)
        identifier = values.get("id")
        name = values.get("name")
        if (
            not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or not isinstance(name, str)
            or not name
        ):
            failures += 1
            continue
        try:
            record = _airport_class_record(node, identifier, name)
        except ValueError:
            failures += 1
            continue
        airports += 1
        airport_records.append(record)
        parking_slots += record["parking_slot_count"]
        airplane_slots += record["airplane_parking_slots"]
        helicopter_slots += record["helicopter_parking_slots"]
    return {
        "airports_parsed": airports,
        "airport_parse_failures": failures,
        "parking_slots": parking_slots,
        "airplane_parking_slots": airplane_slots,
        "helicopter_parking_slots": helicopter_slots,
        "declared_bounds_consistency": _airport_bounds_consistency(
            bounds,
            airport_records,
            parse_failures=failures,
        ),
    }


def _pydcs_coordinate_conversion(
    terrain: dict[str, Any],
    *,
    latitude: float | None,
    longitude: float | None,
    map_x: float | None,
    map_y: float | None,
) -> dict[str, Any] | None:
    if latitude is None and map_x is None:
        return None
    projection = terrain["projection"]
    fit = ProjectionFit(
        central_meridian=projection["central_meridian"],
        scale_factor=projection["scale_factor"],
        false_easting=projection["false_easting"],
        false_northing=projection["false_northing"],
        rms_error_m=0.0,
        max_error_m=0.0,
    )
    if latitude is not None and longitude is not None:
        output_x, output_y = _checked_latlon_to_map(
            latitude,
            longitude,
            fit,
        )
        output = {"x": output_x, "y": output_y}
        return {
            "direction": "WGS84_to_mission_local",
            "input": {"latitude": latitude, "longitude": longitude},
            "output": output,
            "within_upstream_bounds": _point_within_bounds(
                terrain["bounds"],
                output_x,
                output_y,
            ),
            "independently_validated_against_current_install": False,
        }
    if map_x is None or map_y is None:
        return None
    output_latitude, output_longitude = _checked_map_to_latlon(
        map_x,
        map_y,
        fit,
    )
    return {
        "direction": "mission_local_to_WGS84",
        "input": {"x": map_x, "y": map_y},
        "output": {
            "latitude": output_latitude,
            "longitude": output_longitude,
        },
        "within_upstream_bounds": _point_within_bounds(
            terrain["bounds"],
            map_x,
            map_y,
        ),
        "independently_validated_against_current_install": False,
    }


def _validate_coordinate_query(
    *,
    terrain: str | None,
    latitude: float | None,
    longitude: float | None,
    map_x: float | None,
    map_y: float | None,
) -> None:
    forward_requested = latitude is not None or longitude is not None
    inverse_requested = map_x is not None or map_y is not None
    if (forward_requested or inverse_requested) and terrain is None:
        raise ValueError("coordinate conversion requires --terrain")
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
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if latitude is not None and not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if longitude is not None and not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")


def _call_argument(
    call: ast.Call,
    position: int,
    keyword: str,
) -> ast.AST | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[position] if len(call.args) > position else None


def _function_assignment(
    function: ast.FunctionDef,
    name: str,
) -> ast.AST | None:
    for statement in function.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ):
            return statement.value
    return None


def _rectangle(node: ast.AST) -> dict[str, float] | None:
    if not isinstance(node, ast.Call) or _call_name(node) != "Rectangle":
        return None
    if len(node.args) < 4:
        raise ValueError("terrain bounds rectangle is incomplete")
    values = [_number_expression(item) for item in node.args[:4]]
    top, left, bottom, right = values
    return {
        "top": top,
        "left": left,
        "bottom": bottom,
        "right": right,
        "center": {
            "x": (top + bottom) / 2.0,
            "y": (left + right) / 2.0,
        },
    }


def _point_within_bounds(
    bounds: dict[str, Any] | None,
    x: float,
    y: float,
) -> bool | None:
    if bounds is None:
        return None
    return min(bounds["top"], bounds["bottom"]) <= x <= max(
        bounds["top"], bounds["bottom"]
    ) and min(bounds["left"], bounds["right"]) <= y <= max(
        bounds["left"], bounds["right"]
    )


def _airport_bounds_consistency(
    bounds: dict[str, Any] | None,
    airports: list[dict[str, Any]],
    *,
    parse_failures: int,
) -> dict[str, Any]:
    """Check whether one generated source agrees with its own rectangle."""

    normalized = _normalized_rectangle(bounds)
    if normalized is None:
        return {
            "status": "unavailable",
            "hard_coordinate_rejection_allowed": False,
            "reason": "declared_rectangle_unavailable",
            "tolerance_m": None,
            "tolerance_rule": _bounds_tolerance_rule(),
            "airport_centers_parsed": len(airports),
            "airport_parse_failures": parse_failures,
            "strictly_within": 0,
            "within_tolerance": 0,
            "obviously_outside": 0,
            "obviously_outside_airports": [],
        }
    minimum_x, maximum_x, minimum_y, maximum_y = normalized
    tolerance = _bounds_tolerance(normalized)
    strictly_within = 0
    within_tolerance = 0
    outside: list[dict[str, Any]] = []
    for airport in airports:
        center = airport["center"]
        x = float(center["x"])
        y = float(center["y"])
        if minimum_x <= x <= maximum_x and minimum_y <= y <= maximum_y:
            strictly_within += 1
        if (
            minimum_x - tolerance <= x <= maximum_x + tolerance
            and minimum_y - tolerance <= y <= maximum_y + tolerance
        ):
            within_tolerance += 1
        else:
            outside.append(
                {
                    "airdrome_id": airport["airdrome_id"],
                    "name": airport["name"],
                    "center": {"x": x, "y": y},
                }
            )
    if not airports:
        status = "unavailable"
        reason = "no_airport_centers_parsed"
    elif parse_failures:
        status = "incomplete"
        reason = "airport_source_parse_incomplete"
    elif outside:
        status = "inconsistent"
        reason = "airport_centers_obviously_outside_declared_rectangle"
    else:
        status = "consistent"
        reason = None
    return {
        "status": status,
        "hard_coordinate_rejection_allowed": status == "consistent",
        "reason": reason,
        "tolerance_m": tolerance,
        "tolerance_rule": _bounds_tolerance_rule(),
        "airport_centers_parsed": len(airports),
        "airport_parse_failures": parse_failures,
        "strictly_within": strictly_within,
        "within_tolerance": within_tolerance,
        "obviously_outside": len(outside),
        "obviously_outside_airports": outside,
    }


def _normalized_rectangle(
    bounds: dict[str, Any] | None,
) -> tuple[float, float, float, float] | None:
    if not isinstance(bounds, dict):
        return None
    values = (
        bounds.get("top"),
        bounds.get("bottom"),
        bounds.get("left"),
        bounds.get("right"),
    )
    if not all(_is_number(value) and math.isfinite(value) for value in values):
        return None
    top, bottom, left, right = (float(value) for value in values)
    if top == bottom or left == right:
        return None
    return (
        min(top, bottom),
        max(top, bottom),
        min(left, right),
        max(left, right),
    )


def _bounds_tolerance(
    normalized: tuple[float, float, float, float],
) -> float:
    minimum_x, maximum_x, minimum_y, maximum_y = normalized
    span = max(maximum_x - minimum_x, maximum_y - minimum_y)
    return max(
        _MINIMUM_BOUNDS_TOLERANCE_M,
        span * _BOUNDS_SPAN_TOLERANCE_RATIO,
    )


def _bounds_tolerance_rule() -> dict[str, float]:
    return {
        "minimum_m": _MINIMUM_BOUNDS_TOLERANCE_M,
        "maximum_axis_span_ratio": _BOUNDS_SPAN_TOLERANCE_RATIO,
    }


def _is_super_init_call(call: ast.Call) -> bool:
    function = call.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "__init__"
        and isinstance(function.value, ast.Call)
        and isinstance(function.value.func, ast.Name)
        and function.value.func.id == "super"
    )


def _number_expression(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and _is_number(node.value):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op,
        (ast.UAdd, ast.USub),
    ):
        value = _number_expression(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(
        node.op,
        (ast.Add, ast.Sub, ast.Mult, ast.Div),
    ):
        left = _number_expression(node.left)
        right = _number_expression(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ValueError("numeric expression divides by zero")
        return left / right
    raise ValueError("expression is not a safe numeric literal")


def _airport_class_record(
    node: ast.ClassDef,
    identifier: int,
    name: str,
) -> dict[str, Any]:
    values = _class_literal_assignments(node)
    initializer = next(
        (
            item
            for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "__init__"
        ),
        None,
    )
    if initializer is None:
        raise ValueError("airport has no initializer")
    calls = sorted(
        (item for item in ast.walk(initializer) if isinstance(item, ast.Call)),
        key=lambda item: (item.lineno, item.col_offset),
    )
    point_calls = [item for item in calls if _call_name(item) == "Point"]
    if not point_calls:
        raise ValueError("airport has no center point")
    center = _point(point_calls[0])

    runways: list[dict[str, Any]] = []
    parking: list[dict[str, Any]] = []
    beacons: list[str] = []
    for call in calls:
        call_name = _call_name(call)
        if call_name == "Runway":
            fields = _call_keywords(call)
            runway_id = fields.get("id")
            runway_name = fields.get("name")
            if isinstance(runway_id, int) and isinstance(runway_name, str):
                runways.append({"id": runway_id, "name": runway_name})
        elif call_name == "ParkingSlot":
            parking.append(_parking_slot(call))
        elif call_name == "AirportBeacon":
            fields = _call_keywords(call)
            beacon_id = fields.get("id")
            if isinstance(beacon_id, str):
                beacons.append(beacon_id)

    return {
        "class": node.name,
        "airdrome_id": identifier,
        "name": name,
        "center": center,
        "civilian": values.get("civilian"),
        # Airport.slot_version defaults to 1 in upstream pydcs.  Generated
        # airport classes only override it when they use resolver v2.
        "slot_version": values.get("slot_version", 1),
        "runways": runways,
        "runway_count": len(runways),
        "beacon_ids": beacons,
        "parking_slot_count": len(parking),
        "airplane_parking_slots": sum(item["airplanes"] is True for item in parking),
        "helicopter_parking_slots": sum(item["heli"] is True for item in parking),
        "parking": parking,
    }


def _is_airport_class(node: ast.ClassDef) -> bool:
    """Return whether a top-level generated class declares an Airport."""

    return any(
        (isinstance(base, ast.Name) and base.id == "Airport")
        or (isinstance(base, ast.Attribute) and base.attr == "Airport")
        for base in node.bases
    )


def _parking_slot(call: ast.Call) -> dict[str, Any]:
    nodes = {item.arg: item.value for item in call.keywords if item.arg}
    required = {
        "crossroad_idx",
        "position",
        "large",
        "heli",
        "airplanes",
        "slot_name",
        "length",
        "width",
        "height",
        "shelter",
    }
    if not required.issubset(nodes):
        raise ValueError("parking declaration is incomplete")
    position_node = nodes["position"]
    if not isinstance(position_node, ast.Call) or _call_name(position_node) != "Point":
        raise ValueError("parking declaration has no literal point")
    values = {key: _literal(nodes[key]) for key in required - {"position"}}
    if (
        not isinstance(values["crossroad_idx"], int)
        or isinstance(values["crossroad_idx"], bool)
        or not isinstance(values["slot_name"], str)
    ):
        raise ValueError("parking declaration has invalid identifiers")
    return {
        "crossroad_idx": values["crossroad_idx"],
        "slot_name": values["slot_name"],
        "position": _point(position_node),
        "airplanes": values["airplanes"],
        "heli": values["heli"],
        "large": values["large"],
        "shelter": values["shelter"],
        "dimensions": {
            "length": values["length"],
            "width": values["width"],
            "height": values["height"],
        },
    }


def _plane_class_record(
    node: ast.ClassDef,
    weapons: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    values = _class_literal_assignments(node)
    scalar_names = (
        "id",
        "flyable",
        "height",
        "width",
        "length",
        "fuel_max",
        "max_speed",
        "chaff",
        "flare",
        "charge_total",
        "chaff_charge_size",
        "flare_charge_size",
        "category",
        "radio_frequency",
        "livery_name",
        "property_defaults",
    )
    result = {name: values[name] for name in scalar_names if name in values}
    task_classes = _attribute_list_assignment(node, "tasks")
    default_task_class = _attribute_assignment(node, "task_default")
    task_records = [
        tasks.get(
            class_name,
            {"class": class_name, "resolved": False},
        )
        for class_name in task_classes
    ]
    result["task_classes"] = task_classes
    result["tasks"] = task_records
    result["task_default_class"] = default_task_class
    result["task_default"] = (
        tasks.get(
            default_task_class,
            {"class": default_task_class, "resolved": False},
        )
        if default_task_class is not None
        else None
    )
    result["unresolved_task_records"] = sum(
        record.get("resolved") is not True for record in task_records
    )
    declared_pylons = values.get("pylons")
    result["declared_pylons"] = (
        sorted(declared_pylons)
        if isinstance(declared_pylons, set)
        and all(isinstance(value, int) for value in declared_pylons)
        else []
    )

    assignments: list[dict[str, Any]] = []
    unresolved = 0
    for child in node.body:
        if not isinstance(child, ast.ClassDef):
            continue
        class_match = _PYLON_CLASS.fullmatch(child.name)
        if class_match is None:
            continue
        class_station = int(class_match.group("station"))
        for statement in child.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            value = statement.value
            if (
                not isinstance(target, ast.Name)
                or not isinstance(value, ast.Tuple)
                or len(value.elts) != 2
            ):
                continue
            try:
                station = _literal(value.elts[0])
            except ValueError:
                unresolved += 1
                continue
            weapon_node = value.elts[1]
            if (
                not isinstance(station, int)
                or isinstance(station, bool)
                or not isinstance(weapon_node, ast.Attribute)
                or not isinstance(weapon_node.value, ast.Name)
            ):
                unresolved += 1
                continue
            weapon_namespace = weapon_node.value.id
            weapon_key = weapon_node.attr
            record: dict[str, Any] = {
                "station": station,
                "pylon_class_station": class_station,
                "declaration": target.id,
                "weapon_namespace": weapon_namespace,
                "weapon_key": weapon_key,
            }
            weapon = weapons.get(weapon_key) if weapon_namespace == "Weapons" else None
            if weapon is None:
                unresolved += 1
            else:
                record.update(
                    {
                        "CLSID": weapon.get("clsid"),
                        "name": weapon.get("name"),
                        "weight": weapon.get("weight"),
                    }
                )
            assignments.append(record)
    assignments.sort(
        key=lambda item: (
            item["station"],
            str(item.get("CLSID")),
            item["declaration"],
        )
    )
    result["pylon_assignment_count"] = len(assignments)
    result["unresolved_pylon_assignments"] = unresolved
    result["pylon_assignments"] = assignments
    return result


def _task_index(path: Path) -> dict[str, dict[str, Any]]:
    tree = _parse_python(path)
    records: dict[str, dict[str, Any]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(
            isinstance(base, ast.Name) and base.id == "MainTask" for base in node.bases
        ):
            continue
        values = _class_literal_assignments(node)
        identifier = values.get("id")
        mission_name = values.get("name")
        internal_name = values.get("internal_name")
        if (
            not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or not isinstance(mission_name, str)
            or not isinstance(internal_name, str)
        ):
            continue
        records[node.name] = {
            "class": node.name,
            "id": identifier,
            "mission_group_task": mission_name,
            "payload_internal_name": internal_name,
            "resolved": True,
        }
    return records


def _weapon_index(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    tree = _parse_python(path)
    weapons_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Weapons"
        ),
        None,
    )
    if weapons_class is None:
        raise ValueError("pydcs weapons source has no Weapons class")
    records: dict[str, dict[str, Any]] = {}
    failures = 0
    for statement in weapons_class.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = _literal(statement.value)
        except ValueError:
            failures += 1
            continue
        if not isinstance(value, dict) or not isinstance(value.get("clsid"), str):
            failures += 1
            continue
        records[target.id] = value
    return records, failures


def _class_literal_assignments(node: ast.ClassDef) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for statement in node.body:
        target: ast.Name | None = None
        value_node: ast.AST | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            if isinstance(statement.targets[0], ast.Name):
                target = statement.targets[0]
                value_node = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name):
                target = statement.target
                value_node = statement.value
        if target is None or value_node is None:
            continue
        try:
            values[target.id] = _literal(value_node)
        except ValueError:
            continue
    return values


def _attribute_list_assignment(node: ast.ClassDef, name: str) -> list[str]:
    value = _assignment_node(node, name)
    if not isinstance(value, (ast.List, ast.Tuple)):
        return []
    return [item.attr for item in value.elts if isinstance(item, ast.Attribute)]


def _attribute_assignment(node: ast.ClassDef, name: str) -> str | None:
    value = _assignment_node(node, name)
    return value.attr if isinstance(value, ast.Attribute) else None


def _assignment_node(node: ast.ClassDef, name: str) -> ast.AST | None:
    for statement in node.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ):
            return statement.value
    return None


def _call_keywords(call: ast.Call) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in call.keywords:
        if item.arg is None:
            continue
        try:
            result[item.arg] = _literal(item.value)
        except ValueError:
            continue
    return result


def _point(call: ast.Call) -> dict[str, int | float]:
    if len(call.args) < 2:
        raise ValueError("point declaration is incomplete")
    x = _literal(call.args[0])
    y = _literal(call.args[1])
    if not _is_number(x) or not _is_number(y):
        raise ValueError("point coordinates are not numeric literals")
    return {"x": x, "y": y}


def _call_name(call: ast.Call) -> str | None:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError) as error:
        raise ValueError("expression is not a literal") from error


def _parse_python(path: Path) -> ast.Module:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(
                path.read_text(encoding="utf-8-sig"),
                filename=str(path),
            )
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise ValueError(f"cannot parse pydcs generated source: {error}") from error


def _validated_root(path: Path) -> Path:
    root = path.absolute()
    if not (root / "dcs").is_dir():
        raise ValueError("pydcs root does not contain the dcs package")
    return root


def _git_state(root: Path) -> dict[str, Any]:
    source_lock = upstream_source_lock_status(root, "pydcs")
    actual = source_lock["actual"]
    exact_checkout_root = actual["exact_checkout_root"] is True
    if not exact_checkout_root:
        return {
            "commit": None,
            "branch": None,
            "remote": None,
            "remote_scope": "not_read_without_exact_checkout_root",
            "clean": None,
            "git_available": False,
            "exact_checkout_root": False,
            "provenance": "unversioned_snapshot",
            "source_lock": source_lock,
            "acknowledged": False,
        }
    commit = actual["head"]
    branch = actual["branch"]
    if branch is None and actual["detached"] is True:
        branch = ""
    clean = actual["clean"]
    acknowledged = source_lock["acknowledged"] is True
    if acknowledged:
        provenance = "commit_bound"
    elif commit is not None and clean is True:
        provenance = "clean_unacknowledged_snapshot"
    else:
        provenance = "dirty_worktree_snapshot"
    return {
        "commit": commit,
        "branch": branch,
        "remote": actual["remote"],
        "remote_scope": "sanitized_no_userinfo_query_or_fragment",
        "clean": clean,
        "git_available": commit is not None,
        "exact_checkout_root": True,
        "provenance": provenance,
        "source_lock": source_lock,
        "acknowledged": acknowledged,
    }


def _git(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _sanitize_git_remote(remote: str | None) -> str | None:
    """Return traceable public remote syntax without credentials or local paths."""

    if remote is None:
        return None
    value = remote.strip()
    if not value:
        return None
    if _looks_like_local_path(value):
        return "<redacted-local-remote>"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-local-or-unrecognized-remote>"
    if parsed.scheme:
        if parsed.scheme.casefold() == "file":
            return "file://<redacted-local-remote>"
        try:
            hostname = parsed.hostname
        except ValueError:
            return "<redacted-local-or-unrecognized-remote>"
        if _is_local_host(hostname) or _contains_windows_or_unc_path(parsed.path):
            return "<redacted-local-remote>"
        public_netloc = parsed.netloc.rsplit("@", 1)[-1]
        if not public_netloc:
            return f"{parsed.scheme}://<redacted-invalid-remote>"
        return urlunsplit(
            (
                parsed.scheme,
                public_netloc,
                parsed.path,
                "",
                "",
            )
        )
    scp_match = re.fullmatch(
        r"(?:[^@\s/:]+@)?(?P<host>[^@\s/:]+):"
        r"(?P<path>[^?#\s]+)(?:[?#].*)?",
        value,
    )
    if scp_match is not None:
        host = scp_match.group("host")
        path = scp_match.group("path")
        if _is_local_host(host) or _contains_windows_or_unc_path(path):
            return "<redacted-local-remote>"
        return f"{host}:{path}"
    public_path = re.fullmatch(
        r"(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})/"
        r"(?P<path>[^?#\s]+)(?:[?#].*)?",
        value,
    )
    if public_path is not None:
        host = public_path.group("host")
        path = public_path.group("path")
        if _is_local_host(host) or _contains_windows_or_unc_path(path):
            return "<redacted-local-remote>"
        return f"{host}/{path}"
    return "<redacted-local-or-unrecognized-remote>"


def _snapshot_authority(
    upstream: dict[str, Any],
    subject: str,
) -> str:
    provenance = upstream.get("provenance")
    if provenance == "commit_bound":
        return f"commit_bound_{subject}"
    if provenance == "dirty_worktree_snapshot":
        return f"dirty_worktree_snapshot_{subject}"
    if provenance == "clean_unacknowledged_snapshot":
        return f"clean_unacknowledged_snapshot_{subject}"
    return f"unversioned_snapshot_{subject}"


def _looks_like_local_path(value: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\", ".", "~"))
    )


def _is_local_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.rstrip(".").casefold()
    if (
        normalized == "localhost"
        or normalized == "localhost.localdomain"
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
        or "." not in normalized
    ):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
    )


def _contains_windows_or_unc_path(value: str) -> bool:
    normalized = value.replace("%5c", "\\").replace("%5C", "\\")
    normalized = normalized.replace("%2f", "/").replace("%2F", "/")
    normalized = normalized.replace("%3a", ":").replace("%3A", ":")
    return bool(
        normalized.startswith(("\\\\", "//"))
        or re.search(r"(?:^|[\\/])[A-Za-z]:[\\/]", normalized)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
