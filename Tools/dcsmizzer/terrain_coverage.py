"""One bounded view of all commit-bound DCS theatre evidence sources."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .br_static import br_terrain_report
from .pydcs_static import pydcs_terrain_report


def combined_terrain_report(
    pydcs_root: Path,
    br_root: Path,
    *,
    terrain: str | None = None,
) -> dict[str, Any]:
    """Associate unambiguous identities without overwriting source records."""

    pydcs = pydcs_terrain_report(pydcs_root)
    briefingroom = br_terrain_report(br_root)
    records = [
        _briefingroom_record(item, index)
        for index, item in enumerate(briefingroom["terrains"])
    ]
    identity_conflicts: list[dict[str, Any]] = []

    br_lookups = _briefingroom_lookups(briefingroom["terrains"])
    br_duplicate_reasons = _record_duplicate_briefingroom_identities(
        briefingroom["terrains"],
        br_lookups,
        identity_conflicts,
    )
    for index, reasons in enumerate(br_duplicate_reasons):
        for reason in reasons:
            _reject_record(records[index], reason)

    pydcs_duplicate_reasons, pydcs_identity_conflicts = (
        _pydcs_duplicate_identities(pydcs["terrains"])
    )
    identity_conflicts.extend(pydcs_identity_conflicts)

    for index, item in enumerate(pydcs["terrains"]):
        pydcs_record = _pydcs_record(item, index)
        duplicate_reasons = pydcs_duplicate_reasons[index]
        candidates, methods = _briefingroom_candidates(item, br_lookups)
        if duplicate_reasons:
            _reject_record(
                pydcs_record,
                "duplicate_pydcs_identity",
            )
            identity_conflicts.append(
                {
                    "code": "pydcs_identity_mapping_rejected",
                    "pydcs_record": _pydcs_identity(item, index),
                    "reasons": duplicate_reasons,
                    "briefingroom_candidate_indexes": sorted(candidates),
                    "resolution": "rejected_without_merge",
                }
            )
            for candidate in candidates:
                _reject_record(
                    records[candidate],
                    "ambiguous_pydcs_identity_claim",
                )
            records.append(pydcs_record)
            continue
        if len(candidates) > 1:
            _reject_record(
                pydcs_record,
                "ambiguous_briefingroom_identity_mapping",
            )
            conflict = {
                "code": "cross_source_identity_mapping_rejected",
                "pydcs_record": _pydcs_identity(item, index),
                "matching_methods": methods,
                "briefingroom_candidates": [
                    _briefingroom_identity(
                        briefingroom["terrains"][candidate],
                        candidate,
                    )
                    for candidate in sorted(candidates)
                ],
                "resolution": "rejected_without_merge",
            }
            identity_conflicts.append(conflict)
            for candidate in candidates:
                _reject_record(
                    records[candidate],
                    "ambiguous_cross_source_identity_mapping",
                )
            records.append(pydcs_record)
            continue
        if not candidates:
            records.append(pydcs_record)
            continue

        candidate = next(iter(candidates))
        target = records[candidate]
        if (
            target["pydcs"] is not None
            or target["identity_resolution"]["status"] == "rejected"
        ):
            _reject_record(pydcs_record, "target_identity_already_claimed")
            _reject_record(target, "multiple_pydcs_records_claim_identity")
            identity_conflicts.append(
                {
                    "code": "cross_source_identity_mapping_rejected",
                    "pydcs_record": _pydcs_identity(item, index),
                    "briefingroom_candidates": [
                        _briefingroom_identity(
                            briefingroom["terrains"][candidate],
                            candidate,
                        )
                    ],
                    "resolution": "rejected_without_merge",
                }
            )
            records.append(pydcs_record)
            continue

        target["pydcs"] = pydcs_record["pydcs"]
        target["identity_resolution"] = {
            "status": "matched",
            "matching_methods": methods,
            "rejection_reasons": [],
        }
        declared_theatre = item["miz_theatre_name"]
        identity_disagrees = declared_theatre != target["dcs_theatre"]
        target["theatre_identity_conflict"] = identity_disagrees
        target["selected_parking_authority"] = (
            "briefingroom" if identity_disagrees else "pydcs"
        )
        if identity_disagrees:
            target["identity_resolution"]["status"] = (
                "matched_with_declared_dcs_id_disagreement"
            )
            identity_conflicts.append(
                {
                    "code": "cross_source_declared_dcs_id_disagreement",
                    "pydcs_record": _pydcs_identity(item, index),
                    "briefingroom_record": _briefingroom_identity(
                        briefingroom["terrains"][candidate],
                        candidate,
                    ),
                    "resolution": (
                        "associated_by_unambiguous_alias; BriefingRoom DCSID "
                        "retained without rewriting pydcs declaration"
                    ),
                }
            )

    records.sort(key=_record_sort_key)
    selected = [
        record
        for record in records
        if _terrain_matches(record, terrain)
    ]
    usable_records = [
        record for record in records if _record_usable(record)
    ]
    usable_selected = [
        record for record in selected if _record_usable(record)
    ]
    unique_dcs_ids = {
        record["dcs_theatre"].casefold()
        for record in usable_records
        if isinstance(record["dcs_theatre"], str)
    }
    dual_source = sum(
        record["pydcs"] is not None
        and record["briefingroom"] is not None
        for record in usable_records
    )
    rejected = sum(
        record["identity_resolution"]["status"] == "rejected"
        for record in records
    )
    pydcs_upstream = pydcs["upstream"]
    br_upstream = briefingroom["upstream"]
    source_parse_incomplete = bool(
        pydcs["coverage"]["terrain_packages_unresolved"]
        or pydcs["coverage"]["airport_parse_failures"]
        or briefingroom["coverage"]["terrain_bounds_unresolved"]
    )
    source_lock_failures: list[dict[str, Any]] = []
    for source, upstream in (
        ("pydcs", pydcs_upstream),
        ("briefingroom", br_upstream),
    ):
        failure = _source_lock_failure(source, upstream)
        if failure is not None:
            source_lock_failures.append(failure)
    source_locks_commit_bound = not source_lock_failures
    provenances = {
        pydcs_upstream.get("provenance"),
        br_upstream.get("provenance"),
    }
    if source_locks_commit_bound and provenances == {"commit_bound"}:
        authority = "explicit_multi_source_commit_bound_catalog"
    elif "dirty_worktree_snapshot" in provenances:
        authority = "explicit_multi_source_dirty_snapshot_catalog"
    elif "clean_unacknowledged_snapshot" in provenances:
        authority = (
            "explicit_multi_source_clean_unacknowledged_snapshot_catalog"
        )
    else:
        authority = "explicit_multi_source_unversioned_snapshot_catalog"
    return {
        "schema": "dcsmizzer.terrain-coverage/v2",
        "authority": authority,
        "dcs_started": False,
        "filters": {"terrain": terrain},
        "sources": {
            "pydcs": pydcs_upstream,
            "briefingroom": br_upstream,
            "pydcs_authority": pydcs["authority"],
            "briefingroom_authority": briefingroom["authority"],
            "briefingroom_project_version": briefingroom[
                "upstream_project_version"
            ],
        },
        "source_lock": {
            "required_sources": ["pydcs", "briefingroom"],
            "all_sources_commit_bound": source_locks_commit_bound,
            "failure_reasons": source_lock_failures,
        },
        "source_coverage": {
            "pydcs": pydcs["coverage"],
            "briefingroom": briefingroom["coverage"],
        },
        "coverage": {
            "dcs_theatres": len(unique_dcs_ids),
            "terrain_records": len(records),
            "dual_source_theatres": dual_source,
            "pydcs_only_theatres": sum(
                record["pydcs"] is not None
                and record["briefingroom"] is None
                for record in usable_records
            ),
            "briefingroom_only_theatres": sum(
                record["pydcs"] is None
                and record["briefingroom"] is not None
                for record in usable_records
            ),
            "matching_theatres": len(usable_selected),
            "matching_records_including_rejected": len(selected),
            "exact_query_usable": (
                None
                if terrain is None
                else (
                    len(usable_selected) == 1
                    and len(selected) == 1
                    and not source_parse_incomplete
                    and source_locks_commit_bound
                )
            ),
            "theatre_identity_conflicts": sum(
                record["theatre_identity_conflict"]
                for record in records
            ),
            "identity_conflict_records": len(identity_conflicts),
            "identity_mappings_rejected": rejected,
            "source_parse_incomplete": source_parse_incomplete,
        },
        "identity_conflicts": identity_conflicts,
        "terrains": selected,
        "selection_policy": [
            "Exact current installed evidence remains higher authority when "
            "the terrain is locally installed.",
            "For dual-source noninstalled terrain, pydcs is selected for "
            "airport/parking construction and BriefingRoom is retained as an "
            "independent conflict check; source fields are never overwritten.",
            "If one unambiguous alias links records whose declared DCS theatre "
            "IDs differ, BriefingRoom's exact DCSID remains selected and both "
            "source declarations remain visible.",
            "Duplicate or ambiguous identities are rejected without merging; "
            "their source records and candidate mappings remain separate.",
            "BriefingRoom supplies DCS theatre IDs absent from the reported "
            "pydcs snapshot only when the source record parsed successfully.",
        ],
        "limitations": [
            "This is a catalog of two reported upstream source snapshots, not an "
            "initialized current DCS registry or proof of terrain ownership.",
            "The BriefingRoom project-level target version is not compared "
            "with an installed DCS version by this command and is not per-file "
            "version evidence; do not call these exports version-matched.",
            "Different airport counts or fields may reflect version conflict; "
            "use exact airbase queries and review cross-source warnings.",
            "BriefingRoom polygons and spawn types are planning data, not "
            "terrain collision or surface validation.",
            "No upstream code, DCS, or Mission Editor process was executed.",
        ],
    }


def _source_lock_failure(
    source: str,
    upstream: dict[str, Any],
) -> dict[str, Any] | None:
    if (
        upstream.get("provenance") == "commit_bound"
        and upstream.get("acknowledged") is True
    ):
        return None
    source_lock = upstream.get("source_lock")
    failure_reasons = (
        source_lock.get("failure_reasons", [])
        if isinstance(source_lock, dict)
        else ["source_lock_status_unavailable"]
    )
    if not isinstance(failure_reasons, list):
        failure_reasons = ["source_lock_status_invalid"]
    return {
        "source": source,
        "provenance": upstream.get("provenance"),
        "acknowledged": upstream.get("acknowledged") is True,
        "reasons": [
            reason
            for reason in failure_reasons
            if isinstance(reason, str)
        ]
        or ["source_not_acknowledged_commit_bound"],
    }


def _briefingroom_record(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "record_key": f"briefingroom:{index}",
        "dcs_theatre": item["dcs_id"],
        "display_name": item["display_name"],
        "pydcs": None,
        "briefingroom": {
            "declaration_id": item["declaration_id"],
            "airbases": item["airbases"],
            "sea_mask_planning_geometry": item[
                "sea_mask_planning_geometry"
            ],
            "sources": item["sources"],
        },
        "selected_parking_authority": "briefingroom",
        "theatre_identity_conflict": False,
        "identity_resolution": {
            "status": "briefingroom_only",
            "matching_methods": [],
            "rejection_reasons": [],
        },
    }


def _pydcs_record(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "record_key": f"pydcs:{index}",
        "dcs_theatre": item["miz_theatre_name"],
        "display_name": None,
        "pydcs": {
            "terrain_package": item["terrain_package"],
            "terrain_class": item["terrain_class"],
            "declared_miz_theatre_name": item["miz_theatre_name"],
            "airports": item["airport_summary"]["airports_parsed"],
            "parking_slots": item["airport_summary"]["parking_slots"],
            "airport_parse_failures": item["airport_summary"][
                "airport_parse_failures"
            ],
            "bounds": item["bounds"],
            "declared_bounds_consistency": item[
                "declared_bounds_consistency"
            ],
            "projection": item["projection"],
            "declared_center_wgs84": item["declared_center_wgs84"],
            "declared_center_diagnostic": item[
                "declared_center_diagnostic"
            ],
            "sources": item["sources"],
        },
        "briefingroom": None,
        "selected_parking_authority": "pydcs",
        "theatre_identity_conflict": False,
        "identity_resolution": {
            "status": "pydcs_only",
            "matching_methods": [],
            "rejection_reasons": [],
        },
    }


def _briefingroom_lookups(
    items: list[dict[str, Any]],
) -> dict[str, dict[str, set[int]]]:
    result: dict[str, dict[str, set[int]]] = {
        "dcs_id": defaultdict(set),
        "declaration_id": defaultdict(set),
        "display_name": defaultdict(set),
    }
    for index, item in enumerate(items):
        for namespace in result:
            value = item[namespace]
            if isinstance(value, str) and value:
                result[namespace][value.casefold()].add(index)
    return result


def _record_duplicate_briefingroom_identities(
    items: list[dict[str, Any]],
    lookups: dict[str, dict[str, set[int]]],
    conflicts: list[dict[str, Any]],
) -> list[list[str]]:
    reasons: list[list[str]] = [[] for _item in items]
    for namespace, index in lookups.items():
        for folded_value, indexes in sorted(index.items()):
            if len(indexes) < 2:
                continue
            code = f"duplicate_briefingroom_{namespace}"
            conflicts.append(
                {
                    "code": code,
                    "normalized_identity": folded_value,
                    "briefingroom_records": [
                        _briefingroom_identity(items[item_index], item_index)
                        for item_index in sorted(indexes)
                    ],
                    "resolution": "rejected_without_merge",
                }
            )
            for item_index in indexes:
                reasons[item_index].append(code)
    return reasons


def _pydcs_duplicate_identities(
    items: list[dict[str, Any]],
) -> tuple[list[list[str]], list[dict[str, Any]]]:
    lookups: dict[str, dict[str, set[int]]] = {
        "terrain_package": defaultdict(set),
        "terrain_class": defaultdict(set),
        "miz_theatre_name": defaultdict(set),
    }
    for index, item in enumerate(items):
        for namespace in lookups:
            value = item[namespace]
            if isinstance(value, str) and value:
                lookups[namespace][value.casefold()].add(index)
    reasons: list[list[str]] = [[] for _item in items]
    conflicts: list[dict[str, Any]] = []
    for namespace, lookup in lookups.items():
        for normalized, indexes in sorted(lookup.items()):
            if len(indexes) < 2:
                continue
            conflict = {
                "code": f"duplicate_pydcs_{namespace}",
                "normalized_identity": normalized,
                "pydcs_records": [
                    _pydcs_identity(items[item_index], item_index)
                    for item_index in sorted(indexes)
                ],
                "resolution": "retained_as_separate_source_records",
            }
            conflicts.append(conflict)
            for item_index in indexes:
                reasons[item_index].append(conflict["code"])
    return reasons, conflicts


def _briefingroom_candidates(
    item: dict[str, Any],
    lookups: dict[str, dict[str, set[int]]],
) -> tuple[set[int], list[str]]:
    query_by_namespace = {
        "dcs_id": item["miz_theatre_name"],
        "declaration_id": item["terrain_package"],
        "display_name": item["miz_theatre_name"],
    }
    candidates: set[int] = set()
    methods: list[str] = []
    for namespace, query in query_by_namespace.items():
        matches = lookups[namespace].get(query.casefold(), set())
        if matches:
            candidates.update(matches)
            methods.append(namespace)
    return candidates, methods


def _reject_record(record: dict[str, Any], reason: str) -> None:
    record["selected_parking_authority"] = None
    record["theatre_identity_conflict"] = True
    resolution = record["identity_resolution"]
    resolution["status"] = "rejected"
    reasons = resolution["rejection_reasons"]
    if reason not in reasons:
        reasons.append(reason)


def _pydcs_identity(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "record_key": f"pydcs:{index}",
        "terrain_package": item["terrain_package"],
        "declared_miz_theatre_name": item["miz_theatre_name"],
    }


def _briefingroom_identity(
    item: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    return {
        "record_key": f"briefingroom:{index}",
        "declaration_id": item["declaration_id"],
        "dcs_id": item["dcs_id"],
        "display_name": item["display_name"],
    }


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    theatre = record["dcs_theatre"]
    return (
        theatre.casefold() if isinstance(theatre, str) else "",
        record["record_key"],
    )


def _record_usable(record: dict[str, Any]) -> bool:
    if record["identity_resolution"]["status"] == "rejected":
        return False
    pydcs = record.get("pydcs")
    return not (
        isinstance(pydcs, dict)
        and pydcs.get("airport_parse_failures") != 0
    )


def _terrain_matches(
    record: dict[str, Any],
    terrain: str | None,
) -> bool:
    if terrain is None:
        return True
    folded = terrain.casefold()
    values: list[Any] = [
        record["dcs_theatre"],
        record["display_name"],
    ]
    if record["pydcs"] is not None:
        values.extend(
            (
                record["pydcs"]["terrain_package"],
                record["pydcs"]["terrain_class"],
                record["pydcs"]["declared_miz_theatre_name"],
            )
        )
    if record["briefingroom"] is not None:
        values.append(record["briefingroom"]["declaration_id"])
    return any(
        isinstance(value, str) and value.casefold() == folded
        for value in values
    )
