"""Cross-check a build spec against current static and commit-bound evidence."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .br_static import br_airbase_report, br_terrain_report
from .builder import _require_build_spec_unchanged, load_build_spec
from .dcs_static import (
    airbase_beacon_report,
    countries_report,
    module_index_report,
    payload_fingerprint,
    payload_match_report,
    payload_report,
    _windows_product_version,
)
from .facts import CATEGORIES, classify_start_mode, numeric_tables, table
from .gci import (
    GCI_ACTION_ID,
    GCI_STATION_TYPE,
    gci_evidence_report,
    gci_report_complete,
)
from .lua import LuaTable
from .pydcs_static import (
    pydcs_airport_report,
    pydcs_terrain_report,
    pydcs_unit_report,
)
from .terrain_coverage import combined_terrain_report
from .weather import (
    cloud_preset_report,
    validate_weather_consistency,
    weather_constraints_report,
)


def audit_build_spec(
    spec_path: Path,
    *,
    dcs_root: Path,
    installed_terrain: str | None,
    pydcs_root: Path,
    pydcs_terrain: str | None,
    br_root: Path | None = None,
    require_acknowledged_upstreams: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Audit exact technical relationships without executing DCS or upstream."""

    spec = load_build_spec(spec_path, require_resource_files=True)
    mission = spec.tables["mission"]
    mission_year = table(mission.get("date")).get("Year")
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    country_data = countries_report(dcs_root)
    countries_by_id = {
        item["id"]: item["identifier"] for item in country_data["entries"]
    }
    groups = _mission_groups(mission)
    for group in groups:
        country_id = group["country_id"]
        identifier = countries_by_id.get(country_id)
        _check(
            checks,
            f"{group['path']}.country_id",
            identifier is not None,
            authority="current_install_country_source",
            actual=country_id,
            expected="known current country ID",
        )
        group["country_identifier"] = identifier
        authored_name = group["country_name"]
        if (
            identifier is not None
            and isinstance(authored_name, str)
            and authored_name.casefold() != identifier.casefold()
        ):
            warnings.append(
                {
                    "id": f"{group['path']}.country_name",
                    "code": "country_name_differs_from_installed_identifier",
                    "actual": authored_name,
                    "installed_identifier": identifier,
                }
            )

    gci_units = _gci_units(mission)
    gci_data: dict[str, Any] | None = None
    if gci_units:
        gci_data = gci_evidence_report(dcs_root)
        _check(
            checks,
            "gci.current_install_evidence",
            gci_report_complete(gci_data),
            authority=(
                "current_install_static_declaration_official_training_and_manual"
            ),
            actual=gci_data["coverage"],
            expected="station declaration and official training observation",
        )
        declared_countries = {
            country.casefold()
            for declaration in gci_data["station_declarations"]
            for country in declaration["countries"]
        }
        for unit in gci_units:
            identifier = countries_by_id.get(unit["country_id"])
            _check(
                checks,
                f"{unit['path']}.country",
                (
                    isinstance(identifier, str)
                    and identifier.casefold() in declared_countries
                ),
                authority="current_install_gci_station_declaration",
                actual={
                    "country_id": unit["country_id"],
                    "identifier": identifier,
                },
                expected=sorted(
                    {
                        country
                        for declaration in gci_data["station_declarations"]
                        for country in declaration["countries"]
                    }
                ),
            )

    weather_evidence = _audit_weather(
        mission,
        dcs_root,
        checks,
        warnings,
    )

    unit_types = sorted(
        {
            (group["category"], unit.get("type"))
            for group in groups
            for unit in group["units"]
            if isinstance(unit.get("type"), str)
            and unit.get("type") != GCI_STATION_TYPE
        },
        key=lambda item: (item[0], item[1]),
    )
    type_evidence: dict[tuple[str, str], dict[str, Any]] = {}
    pydcs_unit_upstream: dict[str, Any] | None = None
    for category, unit_type in unit_types:
        upstream = pydcs_unit_report(
            pydcs_root,
            unit_type=unit_type,
            category=category,
        )
        units = upstream["units"]
        if pydcs_unit_upstream is None:
            pydcs_unit_upstream = upstream["upstream"]
        flying = (
            units[0].get("flying_unit")
            if len(units) == 1 and category in {"plane", "helicopter"}
            else None
        )
        declared = (
            units[0].get("declared")
            if len(units) == 1 and isinstance(units[0], dict)
            else None
        )
        current_payload = (
            payload_report(dcs_root, unit_type)
            if category in {"plane", "helicopter"}
            else None
        )
        module = (
            module_index_report(dcs_root, unit_type=unit_type)
            if category in {"plane", "helicopter"}
            else None
        )
        current_match = bool(
            category in {"plane", "helicopter"}
            and (
                (current_payload is not None and current_payload["unit_type_sources"])
                or (module is not None and module["coverage"]["matching_modules"] > 0)
            )
        )
        _check(
            checks,
            f"unit_type.{category}.{unit_type}",
            current_match or len(units) == 1,
            authority=(
                "current_install_static_entry_or_default_payload_source"
                if current_match
                else upstream["authority"]
            ),
            actual={"category": category, "unit_type": unit_type},
            expected=(
                "one exact current-install flying-unit declaration or "
                "generated upstream unit declaration"
            ),
        )
        current_pairs = {
            (pylon["num"], pylon["CLSID"])
            for preset in (
                current_payload["presets"] if current_payload is not None else []
            )
            for pylon in preset["pylons"]
        }
        upstream_pairs = {
            (item["station"], item.get("CLSID"))
            for item in (
                flying["pylon_assignments"] if isinstance(flying, dict) else []
            )
            if isinstance(item.get("CLSID"), str)
        }
        task_names = {
            item["mission_group_task"]
            for item in (flying["tasks"] if isinstance(flying, dict) else [])
            if item.get("resolved") is True
        }
        service_records = (
            module["unit_type_resolution"]["service_life_records"]
            if module is not None and module["unit_type_resolution"] is not None
            else []
        )
        type_evidence[(category, unit_type)] = {
            "category": category,
            "exact_unit_match": len(units) == 1,
            "current_unit_match": current_match,
            "current_payload_sources": (
                current_payload["unit_type_sources"]
                if current_payload is not None
                else []
            ),
            "current_payload_candidate_enumeration_complete": (
                current_payload["source_binding"][
                    "candidate_enumeration_complete"
                ]
                if current_payload is not None
                else True
            ),
            "current_payload_relevant_parse_failures": (
                current_payload["unit_type_parse_failure_sources"]
                if current_payload is not None
                else []
            ),
            "current_payload_pairs": current_pairs,
            "upstream_pairs": upstream_pairs,
            "task_names": task_names,
            "service_records": service_records,
            "fuel_max": (flying.get("fuel_max") if isinstance(flying, dict) else None),
            "chaff_max": (flying.get("chaff") if isinstance(flying, dict) else None),
            "flare_max": (flying.get("flare") if isinstance(flying, dict) else None),
            "property_defaults": (
                flying.get("property_defaults", {}) if isinstance(flying, dict) else {}
            ),
            "aircraft_dimensions": {
                dimension: (flying.get(dimension) if isinstance(flying, dict) else None)
                for dimension in ("length", "width", "height")
            },
            "large_parking_slot": (
                declared.get("large_parking_slot", False)
                if isinstance(declared, dict)
                else None
            ),
            "pydcs_source_commit": upstream["upstream"]["commit"],
            "pydcs_source_authority": upstream["authority"],
        }

    mission_theatre = mission.get("theatre")
    terrain_query = pydcs_terrain or mission_theatre
    if not isinstance(terrain_query, str) or not terrain_query:
        raise ValueError(
            "the spec has no mission theatre and --pydcs-terrain was omitted"
        )
    if not isinstance(mission_theatre, str) or not mission_theatre:
        raise ValueError("the spec has no mission theatre")

    # Identity decisions are made from the unfiltered source graph.  An
    # exact package override may select a candidate, but cannot hide another
    # package which claims the same MIZ theatre identity.
    pydcs_terrain_data = pydcs_terrain_report(pydcs_root)
    all_pydcs_terrain_records = pydcs_terrain_data["terrains"]
    pydcs_override_matches = (
        [
            record
            for record in all_pydcs_terrain_records
            if _pydcs_terrain_matches(record, pydcs_terrain)
        ]
        if pydcs_terrain is not None
        else []
    )
    override_valid = pydcs_terrain is None or len(pydcs_override_matches) == 1
    if pydcs_terrain is not None:
        _check(
            checks,
            "terrain.pydcs_override",
            override_valid,
            authority="full_unfiltered_pydcs_identity_graph",
            actual={
                "query": pydcs_terrain,
                "matches": len(pydcs_override_matches),
            },
            expected="one exact package, Terrain class, or MIZ theatre",
        )

    br_terrain_query = mission_theatre
    br_terrain_data = br_terrain_report(br_root) if br_root is not None else None
    all_br_terrain_records = (
        br_terrain_data["terrains"] if br_terrain_data is not None else []
    )
    combined_data = (
        combined_terrain_report(pydcs_root, br_root) if br_root is not None else None
    )
    _gate_upstream_provenance(
        "pydcs",
        pydcs_terrain_data["upstream"],
        checks,
        warnings,
        required=require_acknowledged_upstreams,
    )
    if br_terrain_data is not None:
        _gate_upstream_provenance(
            "briefingroom",
            br_terrain_data["upstream"],
            checks,
            warnings,
            required=require_acknowledged_upstreams,
        )
    graph_candidates: list[dict[str, Any]]
    if combined_data is not None:
        if pydcs_terrain is not None and len(pydcs_override_matches) == 1:
            package = pydcs_override_matches[0]["terrain_package"]
            graph_candidates = [
                record
                for record in combined_data["terrains"]
                if isinstance(record.get("pydcs"), dict)
                and record["pydcs"]["terrain_package"] == package
            ]
        elif pydcs_terrain is not None:
            graph_candidates = []
        else:
            graph_candidates = [
                record
                for record in combined_data["terrains"]
                if _combined_terrain_matches(record, mission_theatre)
            ]
        usable_graph_candidates = [
            record
            for record in graph_candidates
            if _combined_terrain_record_usable(record)
        ]
        identity_graph_parse_complete = not combined_data["coverage"][
            "source_parse_incomplete"
        ]
    else:
        selected_pydcs_candidates = (
            pydcs_override_matches
            if pydcs_terrain is not None
            else [
                record
                for record in all_pydcs_terrain_records
                if _pydcs_terrain_matches(record, mission_theatre)
            ]
        )
        graph_candidates = [
            _pydcs_only_graph_record(record) for record in selected_pydcs_candidates
        ]
        duplicate_identities = pydcs_terrain_data["coverage"]["duplicate_identities"]
        usable_graph_candidates = [
            record
            for record in graph_candidates
            if not _pydcs_graph_record_has_duplicate_identity(
                record,
                duplicate_identities,
            )
            and record["pydcs"]["airport_parse_failures"] == 0
        ]
        identity_graph_parse_complete = not bool(
            pydcs_terrain_data["coverage"]["terrain_packages_unresolved"]
            or pydcs_terrain_data["coverage"]["airport_parse_failures"]
        )

    graph_record = (
        usable_graph_candidates[0]
        if override_valid
        and identity_graph_parse_complete
        and len(graph_candidates) == 1
        and len(usable_graph_candidates) == 1
        else None
    )
    pydcs_terrain_record = None
    br_terrain_record = None
    if graph_record is not None and isinstance(graph_record.get("pydcs"), dict):
        package = graph_record["pydcs"]["terrain_package"]
        pydcs_terrain_record = next(
            (
                record
                for record in all_pydcs_terrain_records
                if record["terrain_package"] == package
            ),
            None,
        )
    if graph_record is not None and isinstance(graph_record.get("briefingroom"), dict):
        declaration = graph_record["briefingroom"]["declaration_id"]
        br_terrain_record = next(
            (
                record
                for record in all_br_terrain_records
                if record["declaration_id"] == declaration
            ),
            None,
        )

    if (
        graph_record is not None
        and graph_record["identity_resolution"]["status"]
        == "matched_with_declared_dcs_id_disagreement"
    ):
        warnings.append(
            {
                "id": "terrain.identity_cross_source",
                "code": "terrain_dcs_id_cross_source_conflict",
                "mission_theatre": mission_theatre,
                "pydcs_declared_miz_theatre_name": pydcs_terrain_record[
                    "miz_theatre_name"
                ],
                "briefingroom_dcs_id": br_terrain_record["dcs_id"],
                "resolution": (
                    "select only the source whose exact declared DCS theatre "
                    "matches mission.theatre; do not rewrite either source"
                ),
            }
        )

    if graph_record is None:
        selected_terrain = None
    elif graph_record["selected_parking_authority"] == "pydcs":
        if pydcs_terrain_record is None:
            raise ValueError("selected pydcs terrain record is unavailable")
        selected_terrain = {
            "authority": pydcs_terrain_data["authority"],
            "theatre": pydcs_terrain_record["miz_theatre_name"],
            "parking_provider": "pydcs",
            "parking_terrain": pydcs_terrain_record["terrain_package"],
            "secondary_parking_provider": (
                "briefingroom" if br_terrain_record is not None else None
            ),
            "secondary_parking_terrain": (
                br_terrain_record["dcs_id"] if br_terrain_record is not None else None
            ),
            "declared_bounds": pydcs_terrain_record["bounds"],
            "declared_bounds_consistency": pydcs_terrain_record[
                "declared_bounds_consistency"
            ],
            "sources": pydcs_terrain_record["sources"],
            "upstream": pydcs_terrain_data["upstream"],
        }
    elif graph_record["selected_parking_authority"] == "briefingroom":
        if br_terrain_record is None or br_terrain_data is None:
            raise ValueError("selected BriefingRoom terrain record is unavailable")
        selected_terrain = {
            "authority": br_terrain_data["authority"],
            "theatre": br_terrain_record["dcs_id"],
            "parking_provider": "briefingroom",
            "parking_terrain": br_terrain_record["dcs_id"],
            "secondary_parking_provider": (
                "pydcs" if pydcs_terrain_record is not None else None
            ),
            "secondary_parking_terrain": (
                pydcs_terrain_record["terrain_package"]
                if pydcs_terrain_record is not None
                else None
            ),
            "declared_bounds": None,
            "declared_bounds_consistency": None,
            "sources": [
                *br_terrain_record["sources"],
                br_terrain_data["airbase_source"],
            ],
            "upstream": br_terrain_data["upstream"],
        }
    else:
        selected_terrain = None
    _check(
        checks,
        "terrain.evidence",
        selected_terrain is not None,
        authority="full_unfiltered_multi_source_identity_graph",
        actual={
            "query": terrain_query,
            "graph_candidates": len(graph_candidates),
            "usable_graph_candidates": len(usable_graph_candidates),
            "rejected_or_incomplete_candidates": (
                len(graph_candidates) - len(usable_graph_candidates)
            ),
            "identity_graph_parse_complete": identity_graph_parse_complete,
        },
        expected=(
            "one exact pydcs terrain package/MIZ theatre or one exact "
            "BriefingRoom DCS theatre"
        ),
    )
    if selected_terrain is not None:
        _check(
            checks,
            "$.theatre",
            mission_theatre == selected_terrain["theatre"],
            authority=selected_terrain["authority"],
            actual=mission_theatre,
            expected=selected_terrain["theatre"],
        )
    if installed_terrain is None:
        warnings.append(
            {
                "id": "terrain.installed",
                "code": "installed_terrain_crosscheck_not_run",
                "terrain": (
                    selected_terrain["theatre"]
                    if selected_terrain is not None
                    else terrain_query
                ),
            }
        )

    installed_product_version = _installed_product_version(dcs_root)
    br_project_version = (
        br_terrain_data["upstream_project_version"]
        if br_terrain_data is not None
        else None
    )
    br_target_version = (
        br_project_version.get("targeted_dcs_world_version")
        if isinstance(br_project_version, dict)
        else None
    )
    version_compatibility = _version_compatibility(
        installed_product_version,
        br_target_version,
    )
    if version_compatibility["status"] == "different_versions":
        warnings.append(
            {
                "id": "terrain.briefingroom_version",
                "code": "briefingroom_target_differs_from_installed_dcs",
                "installed_dcs_product_version": installed_product_version,
                "briefingroom_project_target_version": br_target_version,
                "scope": "project_target_not_per_export_file",
            }
        )

    payload_match_resolutions = _audit_mission_groups(
        groups,
        type_evidence,
        dcs_root=dcs_root,
        mission_year=mission_year,
        checks=checks,
        warnings=warnings,
    )
    coordinate_inventory = _mission_coordinate_inventory(mission, groups)
    if selected_terrain is not None:
        _audit_declared_bounds(
            coordinate_inventory,
            bounds=selected_terrain["declared_bounds"],
            consistency=selected_terrain["declared_bounds_consistency"],
            selected_authority=selected_terrain["authority"],
            checks=checks,
            warnings=warnings,
        )
    parking_resolutions: list[dict[str, Any]] = []
    if selected_terrain is not None:
        parking_resolutions = _audit_parking(
            groups,
            type_evidence=type_evidence,
            dcs_root=dcs_root,
            installed_terrain=installed_terrain,
            pydcs_root=pydcs_root,
            br_root=br_root,
            provider=selected_terrain["parking_provider"],
            terrain=selected_terrain["parking_terrain"],
            secondary_provider=selected_terrain["secondary_parking_provider"],
            secondary_terrain=selected_terrain["secondary_parking_terrain"],
            checks=checks,
            warnings=warnings,
        )
    runway_resolutions: list[dict[str, Any]] = []
    if selected_terrain is not None:
        runway_resolutions = _audit_bombing_runways(
            mission,
            dcs_root=dcs_root,
            installed_terrain=installed_terrain,
            pydcs_root=pydcs_root,
            br_root=br_root,
            provider=selected_terrain["parking_provider"],
            terrain=selected_terrain["parking_terrain"],
            secondary_provider=selected_terrain["secondary_parking_provider"],
            secondary_terrain=selected_terrain["secondary_parking_terrain"],
            checks=checks,
            warnings=warnings,
        )

    failed = [item for item in checks if not item["passed"]]
    _require_build_spec_unchanged(spec)
    report = {
        "schema": "dcsmizzer.build-spec-evidence-audit/v1",
        "input_spec": spec.path.name,
        "input_spec_sha256": spec.sha256,
        "input_spec_path_scope": "basename_only",
        "dcs_started": False,
        "upstream_python_executed": False,
        "filters": {
            "installed_terrain": installed_terrain,
            "terrain_query": terrain_query,
            "briefingroom_terrain_query": (
                br_terrain_query if br_root is not None else None
            ),
            "briefingroom_enabled": br_root is not None,
            "require_acknowledged_upstreams": (
                require_acknowledged_upstreams
            ),
        },
        "sources": {
            "country_source": country_data["source"],
            "country_source_sha256": country_data["source_sha256"],
            "pydcs_commits": sorted(
                {
                    evidence["pydcs_source_commit"]
                    for evidence in type_evidence.values()
                    if evidence["pydcs_source_commit"] is not None
                }
            ),
            "terrain_evidence": (
                {
                    "authority": selected_terrain["authority"],
                    "theatre": selected_terrain["theatre"],
                    "parking_provider": selected_terrain["parking_provider"],
                    "sources": selected_terrain["sources"],
                    "upstream": selected_terrain["upstream"],
                }
                if selected_terrain is not None
                else None
            ),
            "terrain_source_coverage": {
                "pydcs": pydcs_terrain_data["coverage"],
                "briefingroom": (
                    br_terrain_data["coverage"] if br_terrain_data is not None else None
                ),
            },
            "terrain_identity_graph": (
                {
                    "authority": combined_data["authority"],
                    "coverage": combined_data["coverage"],
                    "identity_conflicts": combined_data["identity_conflicts"],
                }
                if combined_data is not None
                else {
                    "authority": pydcs_terrain_data["authority"],
                    "coverage": {
                        "duplicate_identities": pydcs_terrain_data["coverage"][
                            "duplicate_identities"
                        ],
                        "terrain_packages_unresolved": pydcs_terrain_data["coverage"][
                            "terrain_packages_unresolved"
                        ],
                    },
                    "identity_conflicts": [],
                }
            ),
            "terrain_version_compatibility": version_compatibility,
            "weather_constraints": weather_evidence,
            "whole_payload_resolutions": payload_match_resolutions,
            "parking_source_resolutions": parking_resolutions,
            "bombing_runway_source_resolutions": runway_resolutions,
            "briefingroom_secondary_terrain_evidence": (
                {
                    "upstream": br_terrain_data["upstream"],
                    "project_version": br_terrain_data["upstream_project_version"],
                    "sources": (
                        [
                            *br_terrain_record["sources"],
                            br_terrain_data["airbase_source"],
                        ]
                        if br_terrain_record is not None
                        else []
                    ),
                }
                if br_terrain_data is not None
                else None
            ),
            "gci_declaration_sources": (
                [
                    {
                        "source": declaration["source"],
                        "source_sha256": declaration["source_sha256"],
                    }
                    for declaration in gci_data["station_declarations"]
                ]
                if gci_data is not None
                else []
            ),
        },
        "checks": checks,
        "warnings": warnings,
        "validation": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "warning_count": len(warnings),
            "evidence_consistent": not failed,
            "review_warnings_clear": not warnings,
            "runtime_valid": None,
        },
        "limitations": [
            "This audit covers current country IDs, literal cloud preset/base "
            "range, statically extracted Mission Editor weather consistency "
            "when its source is available, generated exact unit types across "
            "all five mission categories, flying-unit task names, complete "
            "current-preset payload composition, station/CLSID declarations, "
            "literal service-life conflicts, selected parking records, coarse "
            "declared rectangular terrain bounds, terrain/theatre identity, "
            "and MiG-29 GCI station country availability.",
            "Declared rectangular bounds can reject coordinates only after "
            "their source is internally airport-center consistent. They never "
            "prove terrain height, surface, collision, or land class.",
            "Parking checks mirror pydcs resolver v1/v2 declarations. "
            "BriefingRoom-only fields remain diagnostics; no result proves "
            "clearance, taxi access, or maneuvering room.",
            "Current default payloads are observations, not a compatibility "
            "matrix. For a unit represented by those sources, the complete "
            "authored composition must match one observed preset; otherwise "
            "a missing pair can be supported only by the reported "
            "provenance-gated pydcs snapshot.",
            "No check proves tactical design, AI behavior, historical scenario "
            "meaning, module entitlement, or DCS load.",
            (
                "The installed DCS product version and BriefingRoom "
                "project-level target were compared; a project target is not "
                "per-export-file provenance."
                if version_compatibility["status"]
                in {"same_version", "different_versions"}
                else "Installed DCS and BriefingRoom target versions could not "
                "both be read, so version compatibility was not established."
            ),
            (
                "Installed-terrain airbase name cross-checks were not run; "
                "parking and theatre evidence is upstream-snapshot only."
                if installed_terrain is None
                else "Installed-terrain airbase names were cross-checked "
                "against provenance-gated upstream airport records."
            ),
            "No Lua or upstream Python was executed, and no DCS or Mission "
            "Editor process was started.",
        ],
    }
    return report, not failed


def _pydcs_terrain_matches(
    record: dict[str, Any],
    query: str | None,
) -> bool:
    if not isinstance(query, str):
        return False
    folded = query.casefold()
    return any(
        isinstance(value, str) and value.casefold() == folded
        for value in (
            record.get("terrain_package"),
            record.get("terrain_class"),
            record.get("miz_theatre_name"),
        )
    )


def _gate_upstream_provenance(
    source: str,
    upstream: dict[str, Any],
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    required: bool,
) -> None:
    acknowledged = (
        upstream.get("provenance") == "commit_bound"
        and upstream.get("acknowledged") is True
    )
    source_lock = upstream.get("source_lock")
    lock_failure_reasons = (
        source_lock.get("failure_reasons", [])
        if isinstance(source_lock, dict)
        else ["source_lock_status_unavailable"]
    )
    actual = {
        "provenance": upstream.get("provenance"),
        "acknowledged": upstream.get("acknowledged") is True,
        "git_available": upstream.get("git_available"),
        "exact_checkout_root": upstream.get("exact_checkout_root"),
        "clean": upstream.get("clean"),
        "source_lock_failure_reasons": lock_failure_reasons,
    }
    if required:
        _check(
            checks,
            f"upstream.{source}.source_lock",
            acknowledged,
            authority="immutable_acknowledged_upstream_source_lock",
            actual=actual,
            expected=(
                "exact clean checkout at the acknowledged remote, commit, "
                "tree, license hash, and required source profile"
            ),
        )
        return
    if acknowledged:
        return
    warnings.append(
        {
            "id": f"upstream.{source}.provenance",
            "code": "upstream_source_not_commit_bound",
            "source": source,
            **actual,
        }
    )


def _combined_terrain_matches(
    record: dict[str, Any],
    query: str,
) -> bool:
    folded = query.casefold()
    values: list[Any] = [
        record.get("dcs_theatre"),
        record.get("display_name"),
    ]
    pydcs = record.get("pydcs")
    if isinstance(pydcs, dict):
        values.extend(
            (
                pydcs.get("terrain_package"),
                pydcs.get("terrain_class"),
                pydcs.get("declared_miz_theatre_name"),
            )
        )
    briefingroom = record.get("briefingroom")
    if isinstance(briefingroom, dict):
        values.append(briefingroom.get("declaration_id"))
    return any(
        isinstance(value, str) and value.casefold() == folded for value in values
    )


def _combined_terrain_record_usable(record: dict[str, Any]) -> bool:
    resolution = record.get("identity_resolution")
    if (
        not isinstance(resolution, dict)
        or resolution.get("status") == "rejected"
        or record.get("selected_parking_authority")
        not in {
            "pydcs",
            "briefingroom",
        }
    ):
        return False
    pydcs = record.get("pydcs")
    return not (isinstance(pydcs, dict) and pydcs.get("airport_parse_failures") != 0)


def _pydcs_only_graph_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dcs_theatre": record["miz_theatre_name"],
        "display_name": None,
        "pydcs": {
            "terrain_package": record["terrain_package"],
            "terrain_class": record["terrain_class"],
            "declared_miz_theatre_name": record["miz_theatre_name"],
            "airport_parse_failures": record["airport_summary"][
                "airport_parse_failures"
            ],
        },
        "briefingroom": None,
        "selected_parking_authority": "pydcs",
        "identity_resolution": {
            "status": "pydcs_only",
            "rejection_reasons": [],
        },
    }


def _pydcs_graph_record_has_duplicate_identity(
    record: dict[str, Any],
    duplicate_identities: list[dict[str, Any]],
) -> bool:
    pydcs = record["pydcs"]
    identities = {
        ("terrain_package", pydcs["terrain_package"].casefold()),
        ("terrain_class", pydcs["terrain_class"].casefold()),
        (
            "miz_theatre_name",
            pydcs["declared_miz_theatre_name"].casefold(),
        ),
    }
    return any(
        (
            duplicate.get("namespace"),
            duplicate.get("normalized_identity"),
        )
        in identities
        for duplicate in duplicate_identities
    )


def _mission_groups(mission: LuaTable) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country_field in table(side.get("country")).numeric_items():
            country = table(country_field.value)
            for category in CATEGORIES:
                category_table = table(country.get(category))
                for group_field in table(category_table.get("group")).numeric_items():
                    group = table(group_field.value)
                    points = numeric_tables(table(group.get("route")).get("points"))
                    result.append(
                        {
                            "path": (
                                f"$.coalition.{side_field.key}.country"
                                f"[{country_field.key}].{category}.group"
                                f"[{group_field.key}]"
                            ),
                            "category": category,
                            "country_id": country.get("id"),
                            "country_name": country.get("name"),
                            "task": group.get("task"),
                            "points": points,
                            "units": numeric_tables(group.get("units")),
                        }
                    )
    return result


def _gci_units(mission: LuaTable) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    coalition = table(mission.get("coalition"))
    for side_field in coalition.fields:
        side = table(side_field.value)
        for country_field in table(side.get("country")).numeric_items():
            country = table(country_field.value)
            vehicle = table(country.get("vehicle"))
            for group_field in table(vehicle.get("group")).numeric_items():
                group = table(group_field.value)
                group_path = (
                    f"$.coalition.{side_field.key}.country"
                    f"[{country_field.key}].vehicle.group[{group_field.key}]"
                )
                for unit_index, unit in enumerate(
                    numeric_tables(group.get("units")),
                    start=1,
                ):
                    if unit.get("type") != GCI_STATION_TYPE:
                        continue
                    result.append(
                        {
                            "path": f"{group_path}.units[{unit_index}]",
                            "country_id": country.get("id"),
                        }
                    )
    return result


def _audit_weather(
    mission: LuaTable,
    dcs_root: Path,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    weather = table(mission.get("weather"))
    constraints_source = (
        dcs_root / "MissionEditor" / "modules" / "me_weather.lua"
    )
    evidence: dict[str, Any] = {
        "authority": "current_install_static_mission_editor_source",
        "available": constraints_source.is_file(),
        "source": "MissionEditor/modules/me_weather.lua",
        "dcs_started": False,
    }
    if constraints_source.is_file():
        constraints = weather_constraints_report(dcs_root)
        consistency = validate_weather_consistency(weather, constraints)
        evidence.update(
            {
                "source_sha256": constraints["source_sha256"],
                "consistency": consistency,
            }
        )
        _check(
            checks,
            "$.weather.consistency",
            consistency["consistent"],
            authority="current_install_static_mission_editor_constraints",
            actual={
                "errors": consistency["errors"],
                "evaluated_fields": consistency["evaluated_fields"],
            },
            expected="all supplied weather relationships are consistent",
        )
        for item in consistency["warnings"]:
            warnings.append(
                {
                    "id": f"$.weather.{item['field']}",
                    "code": item["code"],
                    "requirement": item["requirement"],
                }
            )
    else:
        evidence["unavailable_reason"] = "source_missing"
        warnings.append(
            {
                "id": "$.weather.consistency",
                "code": "current_install_weather_constraints_unavailable",
                "source": "MissionEditor/modules/me_weather.lua",
                "requirement": (
                    "install the matching Mission Editor weather source "
                    "before claiming weather relationship validation"
                ),
            }
        )

    clouds = table(weather.get("clouds"))
    preset = clouds.get("preset")
    if not isinstance(preset, str):
        return evidence
    report = cloud_preset_report(dcs_root, preset=preset)
    records = report["presets"]
    _check(
        checks,
        "$.weather.clouds.preset",
        len(records) == 1,
        authority="current_install_static_cloud_source",
        actual=preset,
        expected="one exact installed literal preset",
    )
    if len(records) != 1:
        return evidence
    base = clouds.get("base")
    bounds = records[0]["base_altitude_range"]
    minimum = bounds["minimum"]
    maximum = bounds["maximum"]
    passed = (
        _is_number(base)
        and _is_number(minimum)
        and _is_number(maximum)
        and minimum <= base <= maximum
    )
    _check(
        checks,
        "$.weather.clouds.base",
        passed,
        authority="current_install_static_cloud_source",
        actual=base,
        expected={"minimum": minimum, "maximum": maximum},
    )
    return evidence


def _audit_mission_groups(
    groups: list[dict[str, Any]],
    type_evidence: dict[tuple[str, str], dict[str, Any]],
    *,
    dcs_root: Path,
    mission_year: Any,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    service_checked: set[tuple[str, str | None, int | float | None]] = set()
    payload_match_cache: dict[tuple[str, str], dict[str, Any]] = {}
    payload_match_resolutions: list[dict[str, Any]] = []
    for group in groups:
        for unit_index, unit in enumerate(group["units"], start=1):
            unit_type = unit.get("type")
            evidence = type_evidence.get((group["category"], unit_type))
            if (
                not isinstance(unit_type, str)
                or unit_type == GCI_STATION_TYPE
                or evidence is None
            ):
                continue
            if group["category"] not in {"plane", "helicopter"}:
                continue
            if evidence["task_names"]:
                _check(
                    checks,
                    f"{group['path']}.task",
                    group["task"] in evidence["task_names"],
                    authority=(
                        f"{evidence['pydcs_source_authority']}:task_declaration"
                    ),
                    actual=group["task"],
                    expected=sorted(evidence["task_names"]),
                )
            else:
                warnings.append(
                    {
                        "id": f"{group['path']}.task",
                        "code": "flying_unit_task_declaration_unresolved",
                        "unit_type": unit_type,
                        "actual": group["task"],
                    }
                )
            payload = table(unit.get("payload"))
            _audit_payload_quantities(
                payload,
                evidence,
                path=f"{group['path']}.units[{unit_index}].payload",
                checks=checks,
            )
            _audit_complete_payload(
                payload,
                unit_type=unit_type,
                evidence=evidence,
                dcs_root=dcs_root,
                path=f"{group['path']}.units[{unit_index}].payload",
                checks=checks,
                warnings=warnings,
                cache=payload_match_cache,
                resolutions=payload_match_resolutions,
            )
            for pylon_field in table(payload.get("pylons")).numeric_items():
                pylon = table(pylon_field.value)
                station = pylon.get("num")
                if not _is_number(station):
                    station = pylon_field.key
                clsid = pylon.get("CLSID")
                pair = (station, clsid)
                current = pair in evidence["current_payload_pairs"]
                upstream = pair in evidence["upstream_pairs"]
                _check(
                    checks,
                    (
                        f"{group['path']}.units[{unit_index}].payload"
                        f".pylons[{pylon_field.key}]"
                    ),
                    current or upstream,
                    authority=(
                        "current_install_default_payload_observation"
                        if current
                        else (f"{evidence['pydcs_source_authority']}:pylon_declaration")
                    ),
                    actual={"station": station, "CLSID": clsid},
                    expected="observed or generated exact station/CLSID pair",
                )
            _audit_aircraft_properties(
                unit,
                evidence,
                path=f"{group['path']}.units[{unit_index}]",
                checks=checks,
            )

            service_key = (
                unit_type,
                group["country_identifier"],
                mission_year,
            )
            if service_key in service_checked:
                continue
            service_checked.add(service_key)
            records = evidence["service_records"]
            if not records:
                warnings.append(
                    {
                        "id": f"unit_type.{unit_type}.service_life",
                        "code": "literal_service_life_not_declared",
                    }
                )
                continue
            country = group["country_identifier"]
            matched = any(
                isinstance(country, str)
                and record["country"].casefold() == country.casefold()
                and _is_number(mission_year)
                and record["start_year"] <= mission_year <= record["end_year"]
                for record in records
            )
            _check(
                checks,
                f"unit_type.{unit_type}.service_life",
                matched,
                authority="current_install_literal_service_life",
                actual={"country": country, "year": mission_year},
                expected=[
                    {
                        "country": record["country"],
                        "start_year": record["start_year"],
                        "end_year": record["end_year"],
                    }
                    for record in records
                ],
            )
    return payload_match_resolutions


def _audit_complete_payload(
    payload: LuaTable,
    *,
    unit_type: str,
    evidence: dict[str, Any],
    dcs_root: Path,
    path: str,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cache: dict[tuple[str, str], dict[str, Any]],
    resolutions: list[dict[str, Any]],
) -> None:
    if not evidence["current_payload_sources"]:
        if not evidence.get(
            "current_payload_candidate_enumeration_complete",
            True,
        ):
            _check(
                checks,
                f"{path}.complete_composition",
                False,
                authority="current_install_default_payload_source_scope",
                actual={
                    "unit_type": unit_type,
                    "relevant_parse_failures": evidence.get(
                        "current_payload_relevant_parse_failures",
                        [],
                    ),
                },
                expected=(
                    "the queried unit payload sources can be enumerated "
                    "without a matching or unknown parse failure"
                ),
            )
            return
        warnings.append(
            {
                "id": f"{path}.complete_composition",
                "code": "current_install_whole_payload_evidence_unavailable",
                "unit_type": unit_type,
                "fallback": evidence["pydcs_source_authority"],
            }
        )
        return

    assignments: list[dict[str, Any]] = []
    for pylon_field in table(payload.get("pylons")).numeric_items():
        pylon = table(pylon_field.value)
        station = pylon.get("num")
        if not _is_number(station):
            station = pylon_field.key
        assignment: dict[str, Any] = {
            "num": station,
            "CLSID": pylon.get("CLSID"),
        }
        if pylon.has("settings"):
            assignment["settings"] = pylon.get("settings")
        assignments.append(assignment)

    try:
        fingerprint = payload_fingerprint(unit_type, assignments)
    except ValueError as error:
        _check(
            checks,
            f"{path}.complete_composition",
            False,
            authority="current_install_default_payload_observation",
            actual={"error": str(error)},
            expected="one valid complete payload query",
        )
        return

    cache_key = (
        unit_type,
        fingerprint["configured_composition_sha256"],
    )
    match = cache.get(cache_key)
    if match is None:
        match = payload_match_report(
            dcs_root,
            unit_type,
            assignments,
        )
        cache[cache_key] = match
        resolution = {
            "unit_type": unit_type,
            "configured_composition_sha256": fingerprint[
                "configured_composition_sha256"
            ],
            "classification": match["classification"],
            "exact_composition_candidate_count": match[
                "exact_composition_candidate_count"
            ],
            "exact_match_count": match["exact_match_count"],
            "payload_inventory_sha256": match["source_binding"][
                "payload_inventory_sha256"
            ],
            "source_files_scanned": match["source_binding"]["files_scanned"],
            "candidate_enumeration_complete": match["source_binding"][
                "candidate_enumeration_complete"
            ],
            "unit_type_invalid_payload_tables": match["source_binding"].get(
                "unit_type_invalid_payload_tables",
                0,
            ),
            "unit_type_invalid_presets": match["source_binding"].get(
                "unit_type_invalid_presets",
                0,
            ),
            "relevant_parse_failure_count": match["source_binding"][
                "relevant_parse_failure_count"
            ],
            "configuration_unspecified_stations": match[
                "configuration_unspecified_stations"
            ],
        }
        resolutions.append(resolution)

    classification = match["classification"]
    complete_observation = classification == "exact_observed_preset" and (
        match["exact_match_count"] > 0
        and not match["configuration_unspecified_stations"]
        and match["source_binding"]["candidate_enumeration_complete"]
        is True
    )
    _check(
        checks,
        f"{path}.complete_composition",
        complete_observation,
        authority="current_install_complete_default_payload_observation",
        actual={
            "classification": classification,
            "configured_composition_sha256": fingerprint[
                "configured_composition_sha256"
            ],
            "exact_composition_candidate_count": match[
                "exact_composition_candidate_count"
            ],
            "exact_match_count": match["exact_match_count"],
            "configuration_unspecified_stations": match[
                "configuration_unspecified_stations"
            ],
            "candidate_enumeration_complete": match["source_binding"][
                "candidate_enumeration_complete"
            ],
            "unit_type_invalid_payload_tables": match["source_binding"].get(
                "unit_type_invalid_payload_tables",
                0,
            ),
            "unit_type_invalid_presets": match["source_binding"].get(
                "unit_type_invalid_presets",
                0,
            ),
        },
        expected=(
            "exactly one complete station/CLSID/settings composition from a "
            "semantically complete observed installed preset inventory"
        ),
    )
    if classification == "ambiguous_observed_preset":
        warnings.append(
            {
                "id": f"{path}.complete_composition",
                "code": "whole_payload_matches_multiple_observed_presets",
                "unit_type": unit_type,
                "exact_match_count": match["exact_match_count"],
            }
        )


def _audit_payload_quantities(
    payload: LuaTable,
    evidence: dict[str, Any],
    *,
    path: str,
    checks: list[dict[str, Any]],
) -> None:
    fuel = _numeric_or_numeric_string(payload.get("fuel"))
    fuel_max = evidence["fuel_max"]
    if payload.has("fuel") and _is_number(fuel_max):
        _check(
            checks,
            f"{path}.fuel",
            fuel is not None and 0 <= fuel <= fuel_max,
            authority=(f"{evidence['pydcs_source_authority']}:aircraft_declaration"),
            actual=payload.get("fuel"),
            expected={"minimum": 0, "maximum": fuel_max},
        )
    for field_name, evidence_name in (
        ("chaff", "chaff_max"),
        ("flare", "flare_max"),
    ):
        authored = payload.get(field_name)
        maximum = evidence[evidence_name]
        if payload.has(field_name) and _is_number(maximum):
            _check(
                checks,
                f"{path}.{field_name}",
                _is_number(authored) and 0 <= authored <= maximum,
                authority=(
                    f"{evidence['pydcs_source_authority']}:aircraft_declaration"
                ),
                actual=authored,
                expected={"minimum": 0, "maximum": maximum},
            )


def _audit_aircraft_properties(
    unit: LuaTable,
    evidence: dict[str, Any],
    *,
    path: str,
    checks: list[dict[str, Any]],
) -> None:
    properties = unit.get("AddPropAircraft")
    if not isinstance(properties, LuaTable):
        return
    defaults = evidence["property_defaults"]
    for field in properties.fields:
        expected = defaults.get(field.key)
        _check(
            checks,
            f"{path}.AddPropAircraft.{field.key}",
            (
                isinstance(field.key, str)
                and field.key in defaults
                and _same_scalar_type(field.value, expected)
            ),
            authority=(f"{evidence['pydcs_source_authority']}:aircraft_declaration"),
            actual={
                "field": field.key,
                "value_type": type(field.value).__name__,
            },
            expected={
                "declared_fields": sorted(defaults),
                "default_type": (
                    type(expected).__name__ if field.key in defaults else None
                ),
            },
        )


def _mission_coordinate_inventory(
    mission: LuaTable,
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coordinates: list[dict[str, Any]] = []
    for group in groups:
        for point_index, point in enumerate(group["points"], start=1):
            coordinates.append(
                {
                    "path": (f"{group['path']}.route.points[{point_index}]"),
                    "kind": "group_route_point",
                    "x": point.get("x"),
                    "y": point.get("y"),
                }
            )
        for unit_index, unit in enumerate(group["units"], start=1):
            coordinates.append(
                {
                    "path": f"{group['path']}.units[{unit_index}]",
                    "kind": "unit_position",
                    "x": unit.get("x"),
                    "y": unit.get("y"),
                }
            )

    coalition = table(mission.get("coalition"))
    for side in coalition.fields:
        side_table = table(side.value)
        bullseye = side_table.get("bullseye")
        if isinstance(bullseye, LuaTable):
            coordinates.append(
                {
                    "path": f"$.coalition.{side.key}.bullseye",
                    "kind": "coalition_bullseye",
                    "x": bullseye.get("x"),
                    "y": bullseye.get("y"),
                }
            )

    triggers = table(mission.get("triggers"))
    for field in table(triggers.get("zones")).numeric_items():
        if not isinstance(field.value, LuaTable):
            continue
        coordinates.append(
            {
                "path": f"$.triggers.zones[{field.key}]",
                "kind": "trigger_zone_center",
                "x": field.value.get("x"),
                "y": field.value.get("y"),
            }
        )

    coordinate_tasks = {
        "AttackMapObject",
        "Bombing",
        "EngageTargetsInZone",
        GCI_ACTION_ID,
    }
    for task, path in _walk_lua_tables(mission, "$"):
        if task.get("id") not in coordinate_tasks:
            continue
        params = task.get("params")
        if not isinstance(params, LuaTable):
            continue
        if not params.has("x") and not params.has("y"):
            continue
        coordinates.append(
            {
                "path": f"{path}.params",
                "kind": f"task_{task.get('id')}",
                "x": params.get("x"),
                "y": params.get("y"),
            }
        )

    unique: dict[str, dict[str, Any]] = {}
    for coordinate in coordinates:
        unique[coordinate["path"]] = coordinate
    return list(unique.values())


def _walk_lua_tables(
    value: Any,
    path: str,
) -> list[tuple[LuaTable, str]]:
    if not isinstance(value, LuaTable):
        return []
    result = [(value, path)]
    for field in value.fields:
        if not isinstance(field.value, LuaTable):
            continue
        child_path = (
            f"{path}.{field.key}"
            if isinstance(field.key, str)
            else f"{path}[{field.key}]"
        )
        result.extend(_walk_lua_tables(field.value, child_path))
    return result


def _audit_declared_bounds(
    coordinates: list[dict[str, Any]],
    *,
    bounds: dict[str, Any] | None,
    consistency: dict[str, Any] | None,
    selected_authority: str,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    normalized = _normalized_bounds(bounds)
    if normalized is None:
        warnings.append(
            {
                "id": "terrain.declared_bounds",
                "code": "rectangular_bounds_evidence_unavailable",
                "selected_terrain_authority": selected_authority,
                "surface_validity": "not_evaluated",
                "coordinates_discovered": len(coordinates),
            }
        )
        return
    minimum_x, maximum_x, minimum_y, maximum_y = normalized
    span = max(maximum_x - minimum_x, maximum_y - minimum_y)
    calculated_tolerance = max(1000.0, span * 0.001)
    reported_tolerance = (
        consistency.get("tolerance_m") if isinstance(consistency, dict) else None
    )
    tolerance = (
        float(reported_tolerance)
        if _is_number(reported_tolerance)
        else calculated_tolerance
    )
    expected = {
        "declared_rectangle": {
            "minimum_x": minimum_x,
            "maximum_x": maximum_x,
            "minimum_y": minimum_y,
            "maximum_y": maximum_y,
        },
        "obvious_outside_tolerance_m": tolerance,
        "scope": "coarse_declared_rectangle_not_surface_validation",
    }
    consistency_status = (
        consistency.get("status") if isinstance(consistency, dict) else "unavailable"
    )
    hard_check_allowed = bool(
        isinstance(consistency, dict)
        and consistency.get("hard_coordinate_rejection_allowed") is True
        and consistency_status == "consistent"
    )
    if not hard_check_allowed:
        warnings.append(
            {
                "id": "terrain.declared_bounds",
                "code": "rectangular_bounds_hard_check_suppressed",
                "selected_terrain_authority": selected_authority,
                "source_internal_consistency": consistency,
                "coordinates_discovered": len(coordinates),
                "coordinate_diagnostics": [
                    _coordinate_bounds_diagnostic(
                        coordinate,
                        normalized=normalized,
                        tolerance=tolerance,
                    )
                    for coordinate in coordinates
                ],
                "surface_validity": "not_evaluated",
            }
        )
        return
    for coordinate in coordinates:
        _audit_declared_bound_point(
            coordinate.get("x"),
            coordinate.get("y"),
            path=f"{coordinate['path']}.declared_bounds",
            normalized=normalized,
            tolerance=tolerance,
            expected=expected,
            authority=(f"{selected_authority}:declared_rectangle_coarse_sanity"),
            checks=checks,
            warnings=warnings,
        )


def _coordinate_bounds_diagnostic(
    coordinate: dict[str, Any],
    *,
    normalized: tuple[float, float, float, float],
    tolerance: float,
) -> dict[str, Any]:
    x = coordinate.get("x")
    y = coordinate.get("y")
    minimum_x, maximum_x, minimum_y, maximum_y = normalized
    evaluable = _is_number(x) and _is_number(y)
    return {
        "path": coordinate["path"],
        "kind": coordinate["kind"],
        "x": x,
        "y": y,
        "evaluable": evaluable,
        "would_be_within_coarse_tolerance": (
            minimum_x - tolerance <= x <= maximum_x + tolerance
            and minimum_y - tolerance <= y <= maximum_y + tolerance
            if evaluable
            else None
        ),
        "hard_rejection_applied": False,
    }


def _audit_declared_bound_point(
    x: Any,
    y: Any,
    *,
    path: str,
    normalized: tuple[float, float, float, float],
    tolerance: float,
    expected: dict[str, Any],
    authority: str,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if not _is_number(x) or not _is_number(y):
        warnings.append(
            {
                "id": path,
                "code": "coordinate_bounds_check_not_run",
                "actual": {"x": x, "y": y},
                "surface_validity": "not_evaluated",
            }
        )
        return
    minimum_x, maximum_x, minimum_y, maximum_y = normalized
    strictly_within = minimum_x <= x <= maximum_x and minimum_y <= y <= maximum_y
    within_coarse_tolerance = (
        minimum_x - tolerance <= x <= maximum_x + tolerance
        and minimum_y - tolerance <= y <= maximum_y + tolerance
    )
    _check(
        checks,
        path,
        within_coarse_tolerance,
        authority=authority,
        actual={
            "x": x,
            "y": y,
            "strictly_within_declared_rectangle": strictly_within,
            "surface_validity": "not_evaluated",
        },
        expected=expected,
    )
    if within_coarse_tolerance and not strictly_within:
        warnings.append(
            {
                "id": path,
                "code": "coordinate_slightly_outside_declared_bounds",
                "actual": {"x": x, "y": y},
                "tolerance_m": tolerance,
                "surface_validity": "not_evaluated",
            }
        )


def _normalized_bounds(
    bounds: dict[str, Any] | None,
) -> tuple[float, float, float, float] | None:
    if not isinstance(bounds, dict):
        return None
    values = [
        bounds.get("top"),
        bounds.get("bottom"),
        bounds.get("left"),
        bounds.get("right"),
    ]
    if not all(_is_number(value) for value in values):
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


def _audit_parking_size(
    slot: dict[str, Any],
    evidence: dict[str, Any] | None,
    *,
    path: str,
    authority: str,
    provider: str,
    slot_version: Any,
    category: str,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    aircraft_dimensions = (
        evidence.get("aircraft_dimensions") if isinstance(evidence, dict) else None
    )
    slot_dimensions = slot.get("dimensions")
    comparisons: dict[str, dict[str, float]] = {}
    missing_dimensions: list[str] = []
    for dimension in ("length", "width", "height"):
        aircraft_value = (
            aircraft_dimensions.get(dimension)
            if isinstance(aircraft_dimensions, dict)
            else None
        )
        slot_value = (
            slot_dimensions.get(dimension)
            if isinstance(slot_dimensions, dict)
            else None
        )
        if dimension == "height" and slot_value is None and provider == "pydcs":
            slot_value = 1000.0
        if (
            _is_number(aircraft_value)
            and aircraft_value > 0
            and _is_number(slot_value)
            and slot_value > 0
        ):
            comparisons[dimension] = {
                "aircraft_m": float(aircraft_value),
                "parking_m": float(slot_value),
            }
        else:
            missing_dimensions.append(dimension)
    aircraft_requires_large = (
        evidence.get("large_parking_slot") if isinstance(evidence, dict) else None
    )
    parking_is_large = slot.get("large")
    category_capable = (
        slot.get("airplanes") is True
        if category == "plane"
        else slot.get("heli", slot.get("helicopters")) is True
    )

    if provider != "pydcs":
        warnings.append(
            {
                "id": f"{path}.resolver",
                "code": "parking_resolver_semantics_unavailable",
                "provider": provider,
                "slot_version": None,
                "axis_aligned_dimension_diagnostic": comparisons,
                "missing_or_nonpositive_dimensions": missing_dimensions,
                "category_capable_flag": category_capable,
                "large_classification": {
                    "aircraft_requires_large_parking": (aircraft_requires_large),
                    "parking_is_large": parking_is_large,
                },
                "strict_pydcs_resolver_claimed": False,
            }
        )
        return

    if slot_version == 1:
        resolver_compatible = False
        evidence_complete = isinstance(aircraft_requires_large, bool) and isinstance(
            parking_is_large, bool
        )
        if evidence_complete:
            if aircraft_requires_large:
                resolver_compatible = parking_is_large
            elif category == "helicopter":
                resolver_compatible = parking_is_large or slot.get("heli") is True
            else:
                # Resolver v1 offers every free slot to a non-large plane;
                # its airplanes flag and dimensions are not consulted.
                resolver_compatible = True
        _check(
            checks,
            f"{path}.resolver_v1",
            evidence_complete and resolver_compatible,
            authority=f"{authority}:pydcs_parking_resolver_v1",
            actual={
                "aircraft_requires_large_parking": aircraft_requires_large,
                "aircraft_category": category,
                "parking_is_large": parking_is_large,
                "parking_heli": slot.get("heli"),
                "dimensions_consulted": False,
                "airplanes_flag_consulted": False,
            },
            expected=(
                "the exact upstream resolver-v1 large/helicopter "
                "classification accepts the slot"
            ),
        )
        return

    if slot_version == 2:
        evidence_complete = not missing_dimensions and len(comparisons) == 3
        strict_fit = evidence_complete and all(
            values["aircraft_m"] < values["parking_m"]
            for values in comparisons.values()
        )
        _check(
            checks,
            f"{path}.resolver_v2",
            evidence_complete and category_capable and strict_fit,
            authority=f"{authority}:pydcs_parking_resolver_v2",
            actual={
                "axis_aligned_declared_dimensions": comparisons,
                "strict_less_than": True,
                "missing_or_nonpositive_dimensions": missing_dimensions,
                "aircraft_category": category,
                "category_capable_flag": category_capable,
                "slot_height_null_default_m": 1000.0,
                "large_classification_consulted": False,
                "clearance_or_maneuvering_proven": False,
            },
            expected=(
                "aircraft length, width, and height are each strictly less "
                "than the slot envelope and its category flag is enabled"
            ),
        )
        return

    _check(
        checks,
        f"{path}.resolver_version",
        False,
        authority=f"{authority}:pydcs_parking_resolver",
        actual=slot_version,
        expected="known pydcs Airport.slot_version 1 or 2",
    )


def _audit_parking(
    groups: list[dict[str, Any]],
    *,
    type_evidence: dict[tuple[str, str], dict[str, Any]],
    dcs_root: Path,
    installed_terrain: str | None,
    pydcs_root: Path,
    br_root: Path | None,
    provider: str,
    terrain: str,
    secondary_provider: str | None,
    secondary_terrain: str | None,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resolutions: list[dict[str, Any]] = []
    by_airdrome: dict[int | float, list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        if group["category"] not in {"plane", "helicopter"}:
            continue
        if not group["points"]:
            continue
        first_point = group["points"][0]
        if classify_start_mode(first_point) not in {
            "cold_parking",
            "hot_parking",
        }:
            continue
        airdrome_id = first_point.get("airdromeId")
        if _is_number(airdrome_id):
            by_airdrome[airdrome_id].append(group)

    for airdrome_id, selected_groups in by_airdrome.items():
        primary = _airport_source_query(
            provider,
            terrain,
            airdrome_id=int(airdrome_id),
            pydcs_root=pydcs_root,
            br_root=br_root,
        )
        secondary = (
            _airport_source_query(
                secondary_provider,
                secondary_terrain,
                airdrome_id=int(airdrome_id),
                pydcs_root=pydcs_root,
                br_root=br_root,
            )
            if secondary_provider is not None and secondary_terrain is not None
            else None
        )
        primary_available = _airport_source_available(primary)
        secondary_available = _airport_source_available(secondary)
        selected_airport_source = (
            primary if primary_available else secondary if secondary_available else None
        )
        _check(
            checks,
            f"airdrome.{airdrome_id}.upstream",
            selected_airport_source is not None,
            authority="explicit_per_airdrome_source_resolution",
            actual={
                "primary_provider": provider,
                "primary_usable": primary_available,
                "secondary_provider": secondary_provider,
                "secondary_usable": secondary_available,
            },
            expected="one usable exact primary or explicit secondary airbase",
        )
        if selected_airport_source is None:
            continue
        if selected_airport_source is secondary:
            warnings.append(
                {
                    "id": f"airdrome.{airdrome_id}.source_fallback",
                    "code": "parking_airdrome_secondary_source_fallback",
                    "primary_provider": provider,
                    "secondary_provider": secondary_provider,
                    "primary_exact_usable": primary_available,
                    "secondary_exact_usable": secondary_available,
                }
            )

        primary_airport = primary["airports"][0] if primary_available else None
        secondary_airport = (
            secondary["airports"][0]
            if secondary_available and secondary is not None
            else None
        )
        selected_airport = selected_airport_source["airports"][0]
        if primary_airport is not None and secondary_airport is not None:
            primary_name = primary_airport["name"]
            secondary_name = secondary_airport["name"]
            if (
                not isinstance(primary_name, str)
                or not isinstance(secondary_name, str)
                or primary_name.casefold() != secondary_name.casefold()
            ):
                warnings.append(
                    {
                        "id": f"airdrome.{airdrome_id}.name_cross_source",
                        "code": "airbase_name_cross_source_conflict",
                        "selected_authority": primary["authority"],
                        "selected_name": primary_name,
                        "secondary_name": secondary_name,
                    }
                )
        installed_airbases: list[dict[str, Any]] = []
        if installed_terrain is not None:
            installed = airbase_beacon_report(
                dcs_root,
                installed_terrain,
                airdrome_id=int(airdrome_id),
            )
            installed_airbases = installed["airbases"]
            _check(
                checks,
                f"airdrome.{airdrome_id}.installed",
                len(installed_airbases) == 1,
                authority="current_install_static_terrain_radio_and_beacons",
                actual=len(installed_airbases),
                expected=1,
            )
            if len(installed_airbases) == 1:
                installed_record = installed_airbases[0]
                installed_names = {
                    name.casefold()
                    for field in ("names", "callsigns")
                    for name in installed_record[field]
                    if isinstance(name, str) and name
                }
                upstream_name = selected_airport["name"]
                _check(
                    checks,
                    f"airdrome.{airdrome_id}.name_crosscheck",
                    upstream_name.casefold() in installed_names,
                    authority="current_install_and_upstream_snapshot_crosscheck",
                    actual=upstream_name,
                    expected={
                        "names": sorted(installed_record["names"]),
                        "callsigns": sorted(installed_record["callsigns"]),
                    },
                )

        for group in selected_groups:
            for unit_index, unit in enumerate(group["units"], start=1):
                parking = unit.get("parking")
                parking_id = unit.get("parking_id")
                primary_matches = _airport_slot_matches(
                    primary_airport,
                    parking,
                    parking_id,
                )
                secondary_matches = _airport_slot_matches(
                    secondary_airport,
                    parking,
                    parking_id,
                )
                if len(primary_matches) == 1:
                    selected_source = primary
                    selected_match = primary_matches[0]
                    fallback_used = False
                elif len(secondary_matches) == 1:
                    selected_source = secondary
                    selected_match = secondary_matches[0]
                    fallback_used = True
                else:
                    selected_source = None
                    selected_match = None
                    fallback_used = False
                _check(
                    checks,
                    f"{group['path']}.units[{unit_index}].parking",
                    selected_match is not None,
                    authority="explicit_per_slot_source_resolution",
                    actual={
                        "parking": parking,
                        "parking_id": parking_id,
                        "primary_matches": len(primary_matches),
                        "secondary_matches": len(secondary_matches),
                    },
                    expected="one exact crossroad/slot-name pair in one source",
                )
                if selected_match is None or selected_source is None:
                    continue
                if fallback_used:
                    warnings.append(
                        {
                            "id": (
                                f"{group['path']}.units[{unit_index}].parking_source"
                            ),
                            "code": "parking_slot_secondary_source_fallback",
                            "primary_provider": provider,
                            "secondary_provider": selected_source["provider"],
                            "parking": parking,
                            "parking_id": parking_id,
                        }
                    )
                evidence = type_evidence.get((group["category"], unit.get("type")))
                _audit_parking_size(
                    selected_match,
                    evidence,
                    path=(f"{group['path']}.units[{unit_index}].parking"),
                    authority=selected_source["authority"],
                    provider=selected_source["provider"],
                    slot_version=selected_source["airports"][0].get("slot_version"),
                    category=group["category"],
                    checks=checks,
                    warnings=warnings,
                )
                if len(primary_matches) == 1 and len(secondary_matches) == 1:
                    differences = _parking_cross_source_differences(
                        primary_matches[0],
                        secondary_matches[0],
                    )
                    if differences:
                        warnings.append(
                            {
                                "id": (
                                    f"{group['path']}.units[{unit_index}]"
                                    ".parking_cross_source"
                                ),
                                "code": ("parking_cross_source_semantic_conflict"),
                                "selected_authority": primary["authority"],
                                "secondary_authority": secondary["authority"],
                                "differences": differences,
                                "fallback_allowed": False,
                            }
                        )
                    if selected_source["provider"] != "pydcs":
                        pydcs_source = (
                            primary if primary["provider"] == "pydcs" else secondary
                        )
                        pydcs_match = (
                            primary_matches[0]
                            if primary["provider"] == "pydcs"
                            else secondary_matches[0]
                        )
                        _audit_parking_size(
                            pydcs_match,
                            evidence,
                            path=(
                                f"{group['path']}.units[{unit_index}]"
                                ".parking.pydcs_crosscheck"
                            ),
                            authority=pydcs_source["authority"],
                            provider="pydcs",
                            slot_version=pydcs_source["airports"][0].get(
                                "slot_version"
                            ),
                            category=group["category"],
                            checks=checks,
                            warnings=warnings,
                        )
                elif primary_airport is not None and secondary_airport is not None:
                    warnings.append(
                        {
                            "id": (
                                f"{group['path']}.units[{unit_index}]"
                                ".parking_cross_source"
                            ),
                            "code": "parking_cross_source_pair_conflict",
                            "primary_matches": len(primary_matches),
                            "secondary_matches": len(secondary_matches),
                        }
                    )

                slot_position = selected_match["position"]
                x = unit.get("x")
                y = unit.get("y")
                position_matches = (
                    _is_number(x)
                    and _is_number(y)
                    and abs(x - slot_position["x"]) <= 0.01
                    and abs(y - slot_position["y"]) <= 0.01
                )
                _check(
                    checks,
                    f"{group['path']}.units[{unit_index}].parking_position",
                    position_matches,
                    authority=selected_source["authority"],
                    actual={"x": x, "y": y},
                    expected=slot_position,
                )
                resolutions.append(
                    {
                        "airdrome_id": int(airdrome_id),
                        "unit_path": (f"{group['path']}.units[{unit_index}]"),
                        "installed_airdrome_exact": (
                            len(installed_airbases) == 1
                            if installed_terrain is not None
                            else None
                        ),
                        "selected_parking_provider": selected_source["provider"],
                        "selected_parking_authority": selected_source["authority"],
                        "secondary_fallback_used": fallback_used,
                        "slot_version": selected_source["airports"][0].get(
                            "slot_version"
                        ),
                        "cross_source_exact_pair": (
                            len(primary_matches) == 1 and len(secondary_matches) == 1
                        ),
                    }
                )
    return resolutions


def _airport_source_query(
    provider: str | None,
    terrain: str | None,
    *,
    airdrome_id: int,
    pydcs_root: Path,
    br_root: Path | None,
) -> dict[str, Any] | None:
    if provider == "pydcs" and terrain is not None:
        report = pydcs_airport_report(
            pydcs_root,
            terrain,
            airdrome_id=airdrome_id,
        )
        return {
            "provider": "pydcs",
            "authority": report["authority"],
            "airports": report["airports"],
            "coverage": report["coverage"],
        }
    if provider == "briefingroom" and terrain is not None and br_root is not None:
        report = br_airbase_report(
            br_root,
            terrain,
            airdrome_id=airdrome_id,
        )
        return {
            "provider": "briefingroom",
            "authority": report["authority"],
            "airports": report["airbases"],
            "coverage": report["coverage"],
        }
    return None


def _airport_source_available(source: dict[str, Any] | None) -> bool:
    if not isinstance(source, dict):
        return False
    coverage = source["coverage"]
    key = (
        "exact_airport_query_usable"
        if source["provider"] == "pydcs"
        else "exact_airbase_query_usable"
    )
    return coverage.get(key) is True and len(source["airports"]) == 1


def _airport_slot_matches(
    airport: dict[str, Any] | None,
    parking: Any,
    parking_id: Any,
) -> list[dict[str, Any]]:
    if not isinstance(airport, dict):
        return []
    return [
        slot
        for slot in airport["parking"]
        if slot["crossroad_idx"] == parking and slot["slot_name"] == parking_id
    ]


def _parking_cross_source_differences(
    primary: dict[str, Any],
    secondary: dict[str, Any],
) -> dict[str, Any]:
    differences: dict[str, Any] = {}
    primary_position = primary["position"]
    secondary_position = secondary["position"]
    separation = (
        (primary_position["x"] - secondary_position["x"]) ** 2
        + (primary_position["y"] - secondary_position["y"]) ** 2
    ) ** 0.5
    if separation > 1.0:
        differences["position_separation_m"] = separation
    capability_fields = {
        "airplanes": (
            primary.get("airplanes"),
            secondary.get("airplanes"),
        ),
        "helicopters": (
            primary.get("heli", primary.get("helicopters")),
            secondary.get("heli", secondary.get("helicopters")),
        ),
    }
    capability_conflicts = {
        field: {"primary": values[0], "secondary": values[1]}
        for field, values in capability_fields.items()
        if values[0] != values[1]
    }
    if capability_conflicts:
        differences["capabilities"] = capability_conflicts
    primary_dimensions = primary.get("dimensions")
    secondary_dimensions = secondary.get("dimensions")
    dimension_conflicts = {
        dimension: {
            "primary": (
                primary_dimensions.get(dimension)
                if isinstance(primary_dimensions, dict)
                else None
            ),
            "secondary": (
                secondary_dimensions.get(dimension)
                if isinstance(secondary_dimensions, dict)
                else None
            ),
        }
        for dimension in ("length", "width", "height")
        if (
            (
                primary_dimensions.get(dimension)
                if isinstance(primary_dimensions, dict)
                else None
            )
            != (
                secondary_dimensions.get(dimension)
                if isinstance(secondary_dimensions, dict)
                else None
            )
        )
    }
    if dimension_conflicts:
        differences["dimensions"] = dimension_conflicts
    return differences


def _audit_bombing_runways(
    mission: LuaTable,
    *,
    dcs_root: Path,
    installed_terrain: str | None,
    pydcs_root: Path,
    br_root: Path | None,
    provider: str,
    terrain: str,
    secondary_provider: str | None,
    secondary_terrain: str | None,
    checks: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resolutions: list[dict[str, Any]] = []
    for task, path in _walk_lua_tables(mission, "$"):
        if task.get("id") != "BombingRunway":
            continue
        params = task.get("params")
        if not isinstance(params, LuaTable):
            continue
        runway_id = params.get("runwayId")
        if not _is_number(runway_id):
            continue
        primary = _airport_source_query(
            provider,
            terrain,
            airdrome_id=int(runway_id),
            pydcs_root=pydcs_root,
            br_root=br_root,
        )
        secondary = (
            _airport_source_query(
                secondary_provider,
                secondary_terrain,
                airdrome_id=int(runway_id),
                pydcs_root=pydcs_root,
                br_root=br_root,
            )
            if secondary_provider is not None and secondary_terrain is not None
            else None
        )
        primary_valid = _airport_source_has_runway(primary)
        secondary_valid = _airport_source_has_runway(secondary)
        selected = primary if primary_valid else secondary if secondary_valid else None
        _check(
            checks,
            f"{path}.params.runwayId",
            selected is not None,
            authority="explicit_per_runway_airdrome_source_resolution",
            actual={
                "runwayId": runway_id,
                "primary_provider": provider,
                "primary_has_runway": primary_valid,
                "secondary_provider": secondary_provider,
                "secondary_has_runway": secondary_valid,
            },
            expected=(
                "one exact airport with at least one runway in the primary "
                "source or an explicit secondary fallback"
            ),
        )
        if selected is None:
            continue
        fallback_used = selected is secondary
        if fallback_used:
            warnings.append(
                {
                    "id": f"{path}.params.runwayId.source_fallback",
                    "code": "bombing_runway_secondary_source_fallback",
                    "runwayId": runway_id,
                    "primary_provider": provider,
                    "secondary_provider": secondary_provider,
                }
            )
        if primary_valid and secondary_valid:
            primary_airport = primary["airports"][0]
            secondary_airport = secondary["airports"][0]
            if primary_airport["name"].casefold() != secondary_airport[
                "name"
            ].casefold() or len(primary_airport["runways"]) != len(
                secondary_airport["runways"]
            ):
                warnings.append(
                    {
                        "id": f"{path}.params.runwayId.cross_source",
                        "code": "bombing_runway_cross_source_conflict",
                        "runwayId": runway_id,
                        "primary_name": primary_airport["name"],
                        "secondary_name": secondary_airport["name"],
                        "primary_runway_count": len(primary_airport["runways"]),
                        "secondary_runway_count": len(secondary_airport["runways"]),
                    }
                )
        installed_exact: bool | None = None
        if installed_terrain is not None:
            installed = airbase_beacon_report(
                dcs_root,
                installed_terrain,
                airdrome_id=int(runway_id),
            )
            installed_exact = len(installed["airbases"]) == 1
            _check(
                checks,
                f"{path}.params.runwayId.installed",
                installed_exact,
                authority="current_install_static_terrain_radio_and_beacons",
                actual=len(installed["airbases"]),
                expected=1,
            )
        resolutions.append(
            {
                "task_path": path,
                "runwayId": int(runway_id),
                "selected_provider": selected["provider"],
                "selected_authority": selected["authority"],
                "secondary_fallback_used": fallback_used,
                "installed_airdrome_exact": installed_exact,
            }
        )
    return resolutions


def _airport_source_has_runway(source: dict[str, Any] | None) -> bool:
    return bool(
        _airport_source_available(source)
        and source is not None
        and source["airports"][0].get("runways")
    )


def _check(
    checks: list[dict[str, Any]],
    identifier: str,
    passed: bool,
    *,
    authority: str,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "id": identifier,
            "authority": authority,
            "actual": actual,
            "expected": expected,
            "passed": bool(passed),
        }
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _numeric_or_numeric_string(value: Any) -> float | None:
    if _is_number(value):
        try:
            result = float(value)
        except (OverflowError, ValueError):
            return None
        return result if result == result and abs(result) != float("inf") else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _same_scalar_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(value, bool)
    if _is_number(expected):
        return _is_number(value)
    if isinstance(expected, str):
        return isinstance(value, str)
    return False


def _installed_product_version(dcs_root: Path) -> str | None:
    executable = dcs_root / "bin" / "DCS.exe"
    if not executable.is_file():
        return None
    try:
        return _windows_product_version(executable)
    except OSError:
        return None


def _version_compatibility(
    installed_version: str | None,
    upstream_target_version: str | None,
) -> dict[str, Any]:
    if installed_version is None or upstream_target_version is None:
        status = "not_established"
    elif installed_version == upstream_target_version:
        status = "same_version"
    else:
        status = "different_versions"
    return {
        "installed_dcs_product_version": installed_version,
        "briefingroom_project_target_version": upstream_target_version,
        "briefingroom_version_scope": "project_target_not_per_export_file",
        "status": status,
        "project_target_string_matches_installed": status == "same_version",
        "version_matched_claim_allowed": False,
    }
