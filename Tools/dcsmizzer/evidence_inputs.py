"""Privacy-safe bindings for runtime and physical-terrain evidence inputs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .runtime import (
    MAX_COORDINATE_CHECKS,
    MAX_LOG_HASH_BYTES,
    MAX_MISSION_BYTES,
    MAX_SOURCE_BYTES,
    RESULT_SCHEMA,
    STEAM_MANIFEST_IDENTITY_SCHEMA,
    STEAM_STATE_FAILURE_REASON,
    collect_runtime,
)
from .terrain_physical import (
    MAX_AIRFIELDS,
    MAX_EVIDENCE_BYTES,
    MAX_OBJECT_SEARCHES,
    MAX_OBJECTS,
    MAX_SAMPLES,
    terrain_evidence_document,
)

RUNTIME_ATTESTATION_SCHEMA = "dcsmizzer.runtime-attestation/v1"
TERRAIN_ATTESTATION_SCHEMA = "dcsmizzer.terrain-evidence-attestation/v1"
MAX_BOUND_INPUTS_PER_KIND = 16
_HASH = re.compile(r"\A[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"\A[a-z0-9][a-z0-9-]{0,47}\Z")
_COMMIT = re.compile(r"\A[0-9a-f]{40,64}\Z")
_COUNT_NAME = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z")
_WINDOWS_ABSOLUTE = re.compile(r"\A(?:[a-zA-Z]:[\\/]|\\\\)")
_MAX_REGISTRY_COUNTS = 64
_MAX_REGISTRY_COUNT = 100_000_000
_MAX_RUNTIME_EVENTS = 64
_PHYSICAL_EXPORT_KINDS = frozenset(
    {
        "dcs_terrain_api_runtime_export",
        "dcs_mission_editor_terrain_api_export",
        "dcs_mission_scripting_runtime_export",
    }
)


def runtime_attestation(manifest_path: Path) -> dict[str, Any]:
    """Revalidate one exact prepared run and return a path-free binding."""

    collection = collect_runtime(Path(manifest_path))
    if collection.get("schema") != "dcsmizzer.runtime-collection/v1":
        raise ValueError("runtime collection schema is not supported")
    run_id = _text(collection.get("run_id"), "runtime run ID", maximum=48)
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("runtime collection run ID is invalid")
    mode = collection.get("mode")
    if mode not in {"registry-probe", "mission-smoke"}:
        raise ValueError("runtime collection mode is invalid")
    producer = _producer(collection.get("producer"))
    evidence = _mapping(collection.get("evidence"), "runtime evidence")
    dcs = _runtime_dcs(evidence.get("dcs"))
    mission = _runtime_mission(evidence.get("mission"))
    validation = _runtime_validation(collection.get("validation"))
    execution = _runtime_execution(collection.get("execution"))
    result_summary = _runtime_result_summary(collection.get("result"), mode)
    bound_evidence = {
        "collection_schema": collection["schema"],
        "collection_sha256": _semantic_hash(collection),
        "manifest_sha256": _digest(
            evidence.get("manifest_sha256"),
            "runtime manifest hash",
        ),
        "execution_sha256": _digest(
            evidence.get("execution_sha256"),
            "runtime execution hash",
        ),
        "result_sha256": _optional_digest(
            evidence.get("result_sha256"),
            "runtime result hash",
        ),
        "dcs_log": _optional_file_record(
            evidence.get("dcs_log"),
            "runtime DCS log",
        ),
    }
    report = {
        "schema": RUNTIME_ATTESTATION_SCHEMA,
        "authority": "revalidated_hash_bound_runtime_collection",
        "dcs_started": False,
        "runtime_observed": collection.get("dcs_started") is True,
        "run_id": run_id,
        "mode": mode,
        "prepared_utc": _text(
            collection.get("prepared_utc"),
            "runtime preparation timestamp",
            maximum=40,
        ),
        "producer": producer,
        "dcs": dcs,
        "mission": mission,
        "evidence": bound_evidence,
        "execution": execution,
        "result_summary": result_summary,
        "validation": validation,
        "privacy": {
            "absolute_paths_recorded": False,
            "raw_logs_recorded": False,
            "raw_manifest_recorded": False,
            "raw_execution_recorded": False,
        },
        "limitations": [
            (
                "The attestation binds a revalidated runtime collection but "
                "omits absolute local paths and raw logs."
            ),
            (
                "Registry mode records bounded aggregates, not complete "
                "registry records or compatibility relationships."
            ),
            (
                "Mission smoke validity does not prove AI tactics, every "
                "trigger path, or a human playthrough."
            ),
        ],
    }
    validate_runtime_attestation(report)
    return report


def terrain_attestation(evidence_path: Path) -> dict[str, Any]:
    """Validate one physical-evidence document and bind its full raw hash."""

    data, source = terrain_evidence_document(Path(evidence_path))
    terrain = _text(data.get("terrain"), "terrain identity", maximum=512)
    dcs_input = _mapping(data.get("dcs"), "terrain DCS identity")
    export_input = _mapping(data.get("export"), "terrain export")
    coverage_input = _mapping(data.get("coverage"), "terrain coverage")
    export_kind = _text(
        export_input.get("kind"),
        "terrain export kind",
        maximum=512,
    )
    runtime_initialized = export_input.get("runtime_initialized") is True
    physical_authority = (
        export_kind in _PHYSICAL_EXPORT_KINDS and runtime_initialized
    )
    version_basis = dcs_input.get(
        "product_version_basis",
        dcs_input.get("product_version_source", "unspecified"),
    )
    version_basis = _text(
        version_basis,
        "terrain product-version basis",
        maximum=512,
    )
    runtime_version_attested = dcs_input.get(
        "runtime_identity_attested",
        version_basis == "runtime_attested",
    ) is True
    authority = (
        (
            "version_bound_initialized_dcs_terrain_api_export"
            if runtime_version_attested
            else "initialized_dcs_terrain_api_export_with_declared_version"
        )
        if physical_authority
        else "nonphysical_planning_or_uninitialized_evidence"
    )
    samples = _list(data.get("samples"), "terrain samples")
    objects = _list(data.get("objects"), "terrain objects")
    airfields = _list(data.get("airfields"), "terrain airfields")
    object_searches = _list(
        coverage_input.get("object_searches", []),
        "terrain object searches",
    )
    report = {
        "schema": TERRAIN_ATTESTATION_SCHEMA,
        "authority": authority,
        "dcs_started": False,
        "terrain": terrain,
        "dcs": {
            "product_version": _text(
                dcs_input.get("product_version"),
                "terrain DCS product version",
                maximum=64,
            ),
            "steam_build_id": _optional_text(
                dcs_input.get("steam_build_id"),
                "terrain Steam build",
                maximum=32,
            ),
            "product_version_basis": version_basis,
            "runtime_identity_attested": runtime_version_attested,
            "identity_source": _optional_text(
                dcs_input.get("identity_source"),
                "terrain identity source",
                maximum=512,
            ),
        },
        "export": {
            "kind": export_kind,
            "runtime_initialized": runtime_initialized,
            "created_utc": _optional_text(
                export_input.get("created_utc"),
                "terrain export timestamp",
                maximum=40,
            ),
        },
        "source": {
            "schema": source["schema"],
            "size_bytes": source["size_bytes"],
            "sha256": source["sha256"],
        },
        "coverage": {
            "sampling_design_present": coverage_input.get("sampling_design")
            is not None,
            "sampling_design_sha256": _semantic_hash(
                coverage_input.get("sampling_design")
            ),
            "sample_spacing_m": coverage_input.get("sample_spacing_m"),
            "sample_match_tolerance_m": coverage_input.get(
                "sample_match_tolerance_m"
            ),
            "object_inventory_complete": coverage_input.get(
                "object_inventory_complete",
                False,
            ),
            "object_search_complete": coverage_input.get(
                "object_search_complete",
                False,
            ),
            "object_search_complete_for_ground_placement": coverage_input.get(
                "object_search_complete_for_ground_placement",
                False,
            ),
            "airfield_inventory_complete": coverage_input.get(
                "airfield_inventory_complete",
                False,
            ),
            "object_searches": len(object_searches),
            "object_searches_sha256": _semantic_hash(object_searches),
            "samples": len(samples),
            "samples_sha256": _semantic_hash(samples),
            "objects": len(objects),
            "objects_sha256": _semantic_hash(objects),
            "airfields": len(airfields),
            "airfields_sha256": _semantic_hash(airfields),
        },
        "validation": {
            "source_schema_valid": True,
            "physical_authority": physical_authority,
            "runtime_version_attested": runtime_version_attested,
        },
        "privacy": {
            "absolute_paths_recorded": False,
            "raw_physical_records_embedded": False,
        },
        "limitations": [
            (
                "The attestation binds the full raw evidence hash but does not "
                "embed the potentially proprietary physical records."
            ),
            (
                "Coverage applies only to the source document's declared "
                "samples, search volumes, and exported airfields; unsampled "
                "space remains unknown."
            ),
        ],
    }
    validate_terrain_attestation(report)
    return report


def runtime_artifact_name(report: dict[str, Any]) -> str:
    validate_runtime_attestation(report)
    return f"runtime.{report['run_id']}"


def terrain_artifact_name(report: dict[str, Any]) -> str:
    validate_terrain_attestation(report)
    qualifier = re.sub(
        r"[^a-z0-9-]+",
        "-",
        report["terrain"].casefold(),
    ).strip("-")
    if not qualifier:
        raise ValueError("terrain identity cannot form an artifact name")
    return f"terrain.{qualifier[:48]}.{report['source']['sha256'][:16]}"


def runtime_coverage(report: dict[str, Any]) -> tuple[str, str]:
    validate_runtime_attestation(report)
    if report["validation"]["runtime_valid"] is not True:
        return "blocked", "the exact runtime collection did not validate"
    producer = report["producer"]
    if producer["git_dirty"] is not False or producer["git_commit"] is None:
        return "blocked", "the runtime producer was not a clean bound commit"
    return "complete", "the exact hash-bound runtime collection validated"


def terrain_coverage(report: dict[str, Any]) -> tuple[str, str]:
    validate_terrain_attestation(report)
    validation = report["validation"]
    if validation["physical_authority"] is not True:
        return "blocked", "the source is not an initialized DCS physical export"
    if validation["runtime_version_attested"] is not True:
        return "partial", "the initialized export has only a declared DCS version"
    return (
        "complete",
        "the initialized version-attested export is complete for its finite scope",
    )


def validate_runtime_attestation(value: Any) -> None:
    report = _mapping(value, "runtime attestation")
    required = {
        "schema",
        "authority",
        "dcs_started",
        "runtime_observed",
        "run_id",
        "mode",
        "prepared_utc",
        "producer",
        "dcs",
        "mission",
        "evidence",
        "execution",
        "result_summary",
        "validation",
        "privacy",
        "limitations",
    }
    if set(report) != required or report.get("schema") != RUNTIME_ATTESTATION_SCHEMA:
        raise ValueError("runtime attestation shape or schema is invalid")
    if report.get("authority") != "revalidated_hash_bound_runtime_collection":
        raise ValueError("runtime attestation authority is invalid")
    if report.get("dcs_started") is not False or not isinstance(
        report.get("runtime_observed"),
        bool,
    ):
        raise ValueError("runtime attestation process flags are invalid")
    run_id = _text(report.get("run_id"), "runtime run ID", maximum=48)
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("runtime attestation run ID is invalid")
    if report.get("mode") not in {"registry-probe", "mission-smoke"}:
        raise ValueError("runtime attestation mode is invalid")
    _text(report.get("prepared_utc"), "runtime preparation timestamp", maximum=40)
    _producer(report.get("producer"))
    _validate_runtime_dcs(report.get("dcs"))
    _validate_runtime_mission(report.get("mission"))
    evidence = _mapping(report.get("evidence"), "runtime bound evidence")
    if set(evidence) != {
        "collection_schema",
        "collection_sha256",
        "manifest_sha256",
        "execution_sha256",
        "result_sha256",
        "dcs_log",
    }:
        raise ValueError("runtime bound evidence shape is invalid")
    if evidence.get("collection_schema") != "dcsmizzer.runtime-collection/v1":
        raise ValueError("runtime bound collection schema is invalid")
    for field in ("collection_sha256", "manifest_sha256", "execution_sha256"):
        _digest(evidence.get(field), f"runtime {field}")
    _optional_digest(evidence.get("result_sha256"), "runtime result hash")
    _optional_file_record(evidence.get("dcs_log"), "runtime DCS log")
    execution = _mapping(report.get("execution"), "runtime execution summary")
    if set(execution) != {
        "classification",
        "elapsed_seconds",
        "timed_out",
        "terminated",
        "killed",
        "dcs_exit_observed",
        "result_exists",
        "process_attested",
        "profile_argument_attested",
        "mission_argument_attested",
        "executable_sha256",
    }:
        raise ValueError("runtime execution summary shape is invalid")
    _text(execution.get("classification"), "runtime classification", maximum=64)
    if not isinstance(execution.get("elapsed_seconds"), (int, float)) or isinstance(
        execution.get("elapsed_seconds"),
        bool,
    ):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "runtime elapsed time is invalid"
        )
    if not math.isfinite(float(execution["elapsed_seconds"])) or execution[
        "elapsed_seconds"
    ] < 0:
        raise ValueError("runtime elapsed time is invalid")
    for field in (
        "timed_out",
        "terminated",
        "killed",
        "dcs_exit_observed",
        "result_exists",
        "process_attested",
        "profile_argument_attested",
    ):
        if not isinstance(execution.get(field), bool):
            raise ValueError(  # noqa: TRY004 - external evidence value
                "runtime execution Boolean is invalid"
            )
    if execution.get("mission_argument_attested") is not None and not isinstance(
        execution.get("mission_argument_attested"),
        bool,
    ):
        raise ValueError("runtime mission argument attestation is invalid")
    _optional_digest(
        execution.get("executable_sha256"),
        "runtime process executable hash",
    )
    validation = _runtime_validation(report.get("validation"))
    _validate_runtime_result_summary(
        report.get("result_summary"),
        report=report,
        runtime_valid=validation["runtime_valid"],
    )
    reasons = validation["failure_reasons"]
    if validation["runtime_valid"] is not (not reasons):
        raise ValueError("runtime validity and failure reasons are inconsistent")
    steam_state_failure = STEAM_STATE_FAILURE_REASON in reasons
    inputs_changed = validation["inputs_unchanged"] is False
    if (
        inputs_changed is not steam_state_failure
        or (steam_state_failure and report["dcs"]["distribution"] != "steam")
        or (inputs_changed and validation["runtime_valid"] is not False)
    ):
        raise ValueError(
            "runtime input drift is not the bounded Steam state failure"
        )
    if validation["runtime_valid"] is True and (
        report["runtime_observed"] is not True
        or evidence["result_sha256"] is None
        or report["result_summary"] is None
        or execution["classification"] != "normal_completion"
        or execution["dcs_exit_observed"] is not True
        or execution["result_exists"] is not True
        or execution["process_attested"] is not True
        or execution["profile_argument_attested"] is not True
        or (
            report["mode"] == "mission-smoke"
            and execution["mission_argument_attested"] is not True
        )
        or execution["executable_sha256"]
        != report["dcs"]["executable"]["sha256"]
        or any(
            validation[field] is not True
            for field in (
                "manifest_valid",
                "inputs_unchanged",
                "hook_unchanged",
                "execution_bound",
                "result_present",
                "run_id_matched",
                "mode_matched",
                "runtime_version_matched",
            )
        )
    ):
        raise ValueError("valid runtime attestation has inconsistent evidence")
    if (report["mode"] == "mission-smoke") is not (report["mission"] is not None):
        raise ValueError("runtime mode and mission binding are inconsistent")
    if report.get("privacy") != {
        "absolute_paths_recorded": False,
        "raw_logs_recorded": False,
        "raw_manifest_recorded": False,
        "raw_execution_recorded": False,
    }:
        raise ValueError("runtime attestation privacy policy is invalid")
    _limitations(report.get("limitations"), "runtime attestation")
    _assert_path_free(report)


def _validate_runtime_result_summary(
    value: Any,
    *,
    report: dict[str, Any],
    runtime_valid: bool,
) -> None:
    if value is None:
        if runtime_valid:
            raise ValueError("valid runtime attestation omits its result summary")
        return
    summary = _mapping(value, "runtime result summary")
    common_fields = {
        "schema",
        "run_id",
        "mode",
        "status",
        "created_utc",
        "dcs",
    }
    expected_fields = (
        common_fields | {"registry", "failure_present"}
        if report["mode"] == "registry-probe"
        else common_fields
        | {
            "mission",
            "smoke",
            "coordinate_checks",
            "coordinate_checks_passed",
            "events",
        }
    )
    if set(summary) != expected_fields:
        raise ValueError("runtime result summary shape is invalid")
    for field, maximum in (
        ("schema", 128),
        ("run_id", 48),
        ("mode", 32),
        ("status", 32),
        ("created_utc", 40),
    ):
        _text(summary.get(field), f"runtime result {field}", maximum=maximum)
    normalized_dcs = _runtime_result_dcs(summary.get("dcs"))
    if normalized_dcs != summary["dcs"]:
        raise ValueError("runtime result DCS summary shape is invalid")
    if report["mode"] == "registry-probe":
        if not isinstance(summary.get("failure_present"), bool):
            raise ValueError("runtime result failure-presence flag is invalid")
        registry = summary.get("registry")
        if registry is not None and _runtime_registry_summary(registry) != registry:
            raise ValueError("runtime registry summary shape is invalid")
    else:
        mission = summary.get("mission")
        if mission is not None and _runtime_mission_result_summary(mission) != mission:
            raise ValueError("runtime mission result summary shape is invalid")
        smoke = summary.get("smoke")
        if smoke is not None and _runtime_smoke_summary(smoke) != smoke:
            raise ValueError("runtime smoke summary shape is invalid")
        checks = _list(
            summary.get("coordinate_checks"),
            "runtime coordinate checks",
        )
        if len(checks) > MAX_COORDINATE_CHECKS or any(
            _runtime_coordinate_summary(record) != record for record in checks
        ):
            raise ValueError("runtime coordinate-check summary shape is invalid")
        if len({record["label"] for record in checks}) != len(checks):
            raise ValueError("runtime coordinate-check labels are duplicated")
        if not isinstance(summary.get("coordinate_checks_passed"), bool):
            raise ValueError("runtime coordinate-check result is invalid")
        events = _list(summary.get("events"), "runtime events")
        if len(events) > _MAX_RUNTIME_EVENTS or any(
            _text(event, "runtime event name", maximum=64) != event
            for event in events
        ):
            raise ValueError("runtime event summary shape is invalid")
    if not runtime_valid:
        return
    dcs = summary["dcs"]
    if (
        summary["schema"] != RESULT_SCHEMA
        or summary["run_id"] != report["run_id"]
        or summary["mode"] != report["mode"]
        or summary["status"] != "ok"
        or dcs["expected_product_version"] != report["dcs"]["product_version"]
        or dcs["runtime_product_version"] != report["dcs"]["product_version"]
        or dcs["runtime_identity_attested"] is not True
    ):
        raise ValueError("valid runtime result identity is inconsistent")
    if report["mode"] == "registry-probe":
        registry = summary["registry"]
        required_counts = {
            "countries",
            "unit_types",
            "weapons_by_clsid",
            "task_definitions",
            "planes",
            "pylon_launcher_edges",
        }
        if (
            registry is None
            or summary["failure_present"] is not False
            or registry["initialized"] is not True
            or registry["aggregate_only"] is not True
            or any(registry["counts"].get(name, 0) <= 0 for name in required_counts)
        ):
            raise ValueError("valid registry result summary is inconsistent")
        return
    result_mission = summary["mission"]
    smoke = summary["smoke"]
    prepared_mission = report["mission"]
    if result_mission is None or smoke is None or prepared_mission is None:
        raise ValueError("valid mission result summary is incomplete")
    if (
        result_mission["expected_name"] != prepared_mission["name"]
        or result_mission["runtime_filename_name"] != prepared_mission["name"]
        or result_mission["expected_theatre"] != prepared_mission["theatre"]
        or result_mission["runtime_theatre"] != prepared_mission["theatre"]
        or result_mission["expected_groups"]
        != prepared_mission["expected_groups"]
        or result_mission["groups"] != prepared_mission["expected_groups"]
        or result_mission["expected_units"] != prepared_mission["expected_units"]
        or result_mission["units"] != prepared_mission["expected_units"]
        or result_mission["expected_player_slots"]
        != prepared_mission["expected_player_slots"]
        or (
            prepared_mission["expected_player_slots"] > 0
            and result_mission["available_slots"] < 1
        )
        or smoke["interval_completed"] is not True
        or smoke["observed_seconds"] < smoke["required_seconds"]
        or summary["coordinate_checks_passed"] is not True
        or any(check["passed"] is not True for check in summary["coordinate_checks"])
    ):
        raise ValueError("valid mission result summary is inconsistent")
    event_names = set(summary["events"])
    if not {
        "mission_load_end",
        "simulation_start",
        "smoke_interval_complete",
    } <= event_names:
        raise ValueError("valid mission result event summary is incomplete")


def validate_terrain_attestation(value: Any) -> None:
    report = _mapping(value, "terrain attestation")
    required = {
        "schema",
        "authority",
        "dcs_started",
        "terrain",
        "dcs",
        "export",
        "source",
        "coverage",
        "validation",
        "privacy",
        "limitations",
    }
    if set(report) != required or report.get("schema") != TERRAIN_ATTESTATION_SCHEMA:
        raise ValueError("terrain attestation shape or schema is invalid")
    if report.get("authority") not in {
        "version_bound_initialized_dcs_terrain_api_export",
        "initialized_dcs_terrain_api_export_with_declared_version",
        "nonphysical_planning_or_uninitialized_evidence",
    }:
        raise ValueError("terrain attestation authority is invalid")
    if report.get("dcs_started") is not False:
        raise ValueError("terrain attestation process flag is invalid")
    _text(report.get("terrain"), "terrain identity", maximum=512)
    dcs = _mapping(report.get("dcs"), "terrain DCS identity")
    if set(dcs) != {
        "product_version",
        "steam_build_id",
        "product_version_basis",
        "runtime_identity_attested",
        "identity_source",
    }:
        raise ValueError("terrain attestation DCS identity shape is invalid")
    _text(dcs.get("product_version"), "terrain DCS product version", maximum=64)
    _optional_text(dcs.get("steam_build_id"), "terrain Steam build", maximum=32)
    _text(dcs.get("product_version_basis"), "terrain version basis", maximum=512)
    if not isinstance(dcs.get("runtime_identity_attested"), bool):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "terrain runtime identity flag is invalid"
        )
    _optional_text(dcs.get("identity_source"), "terrain identity source", maximum=512)
    export = _mapping(report.get("export"), "terrain export")
    if set(export) != {"kind", "runtime_initialized", "created_utc"}:
        raise ValueError("terrain attestation export shape is invalid")
    _text(export.get("kind"), "terrain export kind", maximum=512)
    if not isinstance(export.get("runtime_initialized"), bool):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "terrain runtime initialization flag is invalid"
        )
    _optional_text(export.get("created_utc"), "terrain export timestamp", maximum=40)
    source = _mapping(report.get("source"), "terrain source")
    if set(source) != {"schema", "size_bytes", "sha256"} or source.get(
        "schema"
    ) != "dcsmizzer.terrain-physical-evidence/v1":
        raise ValueError("terrain attestation source shape is invalid")
    _positive_integer(
        source.get("size_bytes"),
        "terrain source size",
        maximum=MAX_EVIDENCE_BYTES,
    )
    _digest(source.get("sha256"), "terrain source hash")
    coverage = _mapping(report.get("coverage"), "terrain coverage")
    expected_coverage = {
        "sampling_design_present",
        "sampling_design_sha256",
        "sample_spacing_m",
        "sample_match_tolerance_m",
        "object_inventory_complete",
        "object_search_complete",
        "object_search_complete_for_ground_placement",
        "airfield_inventory_complete",
        "object_searches",
        "object_searches_sha256",
        "samples",
        "samples_sha256",
        "objects",
        "objects_sha256",
        "airfields",
        "airfields_sha256",
    }
    if set(coverage) != expected_coverage:
        raise ValueError("terrain attestation coverage shape is invalid")
    if not isinstance(coverage.get("sampling_design_present"), bool):
        raise ValueError(  # noqa: TRY004 - external evidence value
            "terrain sampling-design presence is invalid"
        )
    _digest(
        coverage.get("sampling_design_sha256"),
        "terrain sampling-design hash",
    )
    for field in (
        "object_inventory_complete",
        "object_search_complete",
        "object_search_complete_for_ground_placement",
        "airfield_inventory_complete",
    ):
        if not isinstance(coverage.get(field), bool):
            raise ValueError(  # noqa: TRY004 - external evidence value
                "terrain coverage Boolean is invalid"
            )
    coverage_limits = {
        "object_searches": MAX_OBJECT_SEARCHES,
        "samples": MAX_SAMPLES,
        "objects": MAX_OBJECTS,
        "airfields": MAX_AIRFIELDS,
    }
    for field, maximum in coverage_limits.items():
        _nonnegative_integer(
            coverage.get(field),
            f"terrain coverage {field}",
            maximum=maximum,
        )
        _digest(coverage.get(f"{field}_sha256"), f"terrain coverage {field} hash")
    validation = _mapping(report.get("validation"), "terrain validation")
    if set(validation) != {
        "source_schema_valid",
        "physical_authority",
        "runtime_version_attested",
    } or any(not isinstance(value, bool) for value in validation.values()):
        raise ValueError("terrain attestation validation is invalid")
    expected_physical = (
        export["kind"] in _PHYSICAL_EXPORT_KINDS
        and export["runtime_initialized"] is True
    )
    if (
        validation["source_schema_valid"] is not True
        or validation["physical_authority"] is not expected_physical
        or validation["runtime_version_attested"]
        is not dcs["runtime_identity_attested"]
    ):
        raise ValueError("terrain attestation validation claims are inconsistent")
    expected_authority = (
        (
            "version_bound_initialized_dcs_terrain_api_export"
            if dcs["runtime_identity_attested"]
            else "initialized_dcs_terrain_api_export_with_declared_version"
        )
        if expected_physical
        else "nonphysical_planning_or_uninitialized_evidence"
    )
    if report["authority"] != expected_authority:
        raise ValueError("terrain attestation authority is inconsistent")
    if report.get("privacy") != {
        "absolute_paths_recorded": False,
        "raw_physical_records_embedded": False,
    }:
        raise ValueError("terrain attestation privacy policy is invalid")
    _limitations(report.get("limitations"), "terrain attestation")
    _assert_path_free(report)


def _runtime_dcs(value: Any) -> dict[str, Any]:
    source = _mapping(value, "runtime DCS identity")
    executable = _source_record(source.get("executable"), "runtime executable")
    api = _optional_source_record(
        source.get("sim_control_api"),
        "runtime API",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    distribution_manifest = _optional_runtime_distribution_manifest(
        source.get("distribution_manifest"),
    )
    launcher_input = source.get("distribution_launcher")
    launcher = None
    if launcher_input is not None:
        launcher_source = _mapping(launcher_input, "runtime launcher")
        launcher = {
            "size_bytes": _positive_integer(
                launcher_source.get("size_bytes"),
                "runtime launcher size",
                maximum=MAX_MISSION_BYTES,
            ),
            "sha256": _digest(
                launcher_source.get("sha256"),
                "runtime launcher hash",
            ),
        }
    return {
        "distribution": _text(
            source.get("distribution"),
            "runtime distribution",
            maximum=32,
        ),
        "distribution_build": _optional_text(
            source.get("distribution_build"),
            "runtime distribution build",
            maximum=32,
        ),
        "distribution_manifest": distribution_manifest,
        "distribution_launcher": launcher,
        "product_version": _text(
            source.get("product_version"),
            "runtime product version",
            maximum=64,
        ),
        "executable": executable,
        "sim_control_api": api,
    }


def _validate_runtime_dcs(value: Any) -> None:
    source = _mapping(value, "runtime DCS identity")
    if set(source) != {
        "distribution",
        "distribution_build",
        "distribution_manifest",
        "distribution_launcher",
        "product_version",
        "executable",
        "sim_control_api",
    }:
        raise ValueError("runtime DCS identity shape is invalid")
    distribution = source.get("distribution")
    if distribution not in {"steam", "standalone"}:
        raise ValueError("runtime distribution is invalid")
    if distribution == "standalone" and any(
        source.get(field) is not None
        for field in (
            "distribution_build",
            "distribution_manifest",
            "distribution_launcher",
        )
    ):
        raise ValueError("standalone runtime DCS identity contains Steam data")
    _optional_text(
        source.get("distribution_build"),
        "runtime distribution build",
        maximum=32,
    )
    distribution_manifest = _optional_runtime_distribution_manifest(
        source.get("distribution_manifest"),
    )
    if distribution_manifest != source.get("distribution_manifest"):
        raise ValueError("runtime distribution manifest shape is invalid")
    launcher = source.get("distribution_launcher")
    if launcher is not None:
        launcher_value = _mapping(launcher, "runtime launcher")
        if set(launcher_value) != {"size_bytes", "sha256"}:
            raise ValueError("runtime launcher shape is invalid")
        _positive_integer(
            launcher_value.get("size_bytes"),
            "runtime launcher size",
            maximum=MAX_MISSION_BYTES,
        )
        _digest(launcher_value.get("sha256"), "runtime launcher hash")
    _text(source.get("product_version"), "runtime product version", maximum=64)
    _source_record(source.get("executable"), "runtime executable")
    _optional_source_record(
        source.get("sim_control_api"),
        "runtime API",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    if distribution == "steam" and (
        source["distribution_build"] is None
        or distribution_manifest is None
        or launcher is None
    ):
        raise ValueError("Steam runtime DCS identity is incomplete")
    if (
        distribution == "steam"
        and distribution_manifest["relative_path"]
        != "appmanifest_223750.acf"
    ):
        raise ValueError("Steam runtime manifest identity is invalid")
    if distribution == "steam" and (
        distribution_manifest["semantic_identity"]["build_id"]
        != source["distribution_build"]
    ):
        raise ValueError("Steam runtime build identity is inconsistent")


def _runtime_mission(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    source = _mapping(value, "runtime mission")
    fields = (
        "name",
        "size_bytes",
        "sha256",
        "archive_valid",
        "parse_valid",
        "theatre",
        "expected_groups",
        "expected_units",
        "expected_player_slots",
    )
    return {field: source.get(field) for field in fields}


def _validate_runtime_mission(value: Any) -> None:
    if value is None:
        return
    mission = _mapping(value, "runtime mission")
    if set(mission) != {
        "name",
        "size_bytes",
        "sha256",
        "archive_valid",
        "parse_valid",
        "theatre",
        "expected_groups",
        "expected_units",
        "expected_player_slots",
    }:
        raise ValueError("runtime mission shape is invalid")
    _text(mission.get("name"), "runtime mission name", maximum=256)
    _positive_integer(
        mission.get("size_bytes"),
        "runtime mission size",
        maximum=MAX_MISSION_BYTES,
    )
    _digest(mission.get("sha256"), "runtime mission hash")
    if (
        mission.get("archive_valid") is not True
        or mission.get("parse_valid") is not True
    ):
        raise ValueError("runtime mission preparation validity is invalid")
    _text(mission.get("theatre"), "runtime mission theatre", maximum=256)
    for field in ("expected_groups", "expected_units", "expected_player_slots"):
        _nonnegative_integer(mission.get(field), f"runtime mission {field}")


def _runtime_execution(value: Any) -> dict[str, Any]:
    source = _mapping(value, "runtime execution")
    attestation = source.get("process_attestation")
    attested = attestation if isinstance(attestation, dict) else {}
    return {
        "classification": _text(
            source.get("classification"),
            "runtime classification",
            maximum=64,
        ),
        "elapsed_seconds": source.get("elapsed_seconds"),
        "timed_out": source.get("timed_out") is True,
        "terminated": source.get("terminated") is True,
        "killed": source.get("killed") is True,
        "dcs_exit_observed": source.get("dcs_exit_observed") is True,
        "result_exists": source.get("result_exists") is True,
        "process_attested": attested.get("attested") is True,
        "profile_argument_attested": (
            attested.get("profile_argument_attested") is True
        ),
        "mission_argument_attested": attested.get("mission_argument_attested"),
        "executable_sha256": _optional_digest(
            attested.get("executable_sha256"),
            "runtime process executable hash",
        ),
    }


def _runtime_result_summary(value: Any, mode: str) -> dict[str, Any] | None:
    if value is None:
        return None
    result = _mapping(value, "runtime result")
    common = {
        "schema": _text(
            result.get("schema"),
            "runtime result schema",
            maximum=128,
        ),
        "run_id": _text(
            result.get("run_id"),
            "runtime result run ID",
            maximum=48,
        ),
        "mode": _text(
            result.get("mode"),
            "runtime result mode",
            maximum=32,
        ),
        "status": _text(
            result.get("status"),
            "runtime result status",
            maximum=32,
        ),
        "created_utc": _text(
            result.get("created_utc"),
            "runtime result timestamp",
            maximum=40,
        ),
        "dcs": _runtime_result_dcs(result.get("dcs")),
    }
    if mode == "registry-probe":
        registry = result.get("registry")
        common["registry"] = (
            None if registry is None else _runtime_registry_summary(registry)
        )
        common["failure_present"] = result.get("failure") is not None
    else:
        mission = result.get("mission")
        smoke = result.get("smoke")
        common["mission"] = (
            None if mission is None else _runtime_mission_result_summary(mission)
        )
        common["smoke"] = (
            None if smoke is None else _runtime_smoke_summary(smoke)
        )
        coordinate_checks = _list(
            result.get("coordinate_checks"),
            "runtime coordinate checks",
        )
        if len(coordinate_checks) > MAX_COORDINATE_CHECKS:
            raise ValueError("runtime coordinate-check count is invalid")
        summaries = [
            _runtime_coordinate_summary(record) for record in coordinate_checks
        ]
        if len({record["label"] for record in summaries}) != len(summaries):
            raise ValueError("runtime coordinate-check labels are duplicated")
        common["coordinate_checks"] = summaries
        if not isinstance(result.get("coordinate_checks_passed"), bool):
            raise ValueError("runtime coordinate-check result is invalid")
        common["coordinate_checks_passed"] = result[
            "coordinate_checks_passed"
        ]
        events = _list(result.get("events"), "runtime events")
        if len(events) > _MAX_RUNTIME_EVENTS:
            raise ValueError("runtime event count is invalid")
        common["events"] = [_runtime_event_summary(event) for event in events]
    _assert_path_free(common)
    return common


def _runtime_result_dcs(value: Any) -> dict[str, Any]:
    source = _mapping(value, "runtime result DCS identity")
    return {
        "expected_product_version": _text(
            source.get("expected_product_version"),
            "runtime result expected DCS version",
            maximum=64,
        ),
        "runtime_product_version": _text(
            source.get("runtime_product_version"),
            "runtime result observed DCS version",
            maximum=64,
        ),
        "runtime_identity_attested": source.get("runtime_identity_attested")
        is True,
    }


def _runtime_registry_summary(value: Any) -> dict[str, Any]:
    registry = _mapping(value, "runtime registry summary")
    counts = _mapping(registry.get("counts"), "runtime registry counts")
    if len(counts) > _MAX_REGISTRY_COUNTS:
        raise ValueError("runtime registry count shape is invalid")
    normalized_counts: dict[str, int] = {}
    for name, count in sorted(counts.items()):
        if not isinstance(name, str) or _COUNT_NAME.fullmatch(name) is None:
            raise ValueError("runtime registry count name is invalid")
        normalized_counts[name] = _nonnegative_integer(
            count,
            f"runtime registry count {name}",
            maximum=_MAX_REGISTRY_COUNT,
        )
    if not isinstance(registry.get("initialized"), bool) or not isinstance(
        registry.get("aggregate_only"),
        bool,
    ):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "runtime registry flags are invalid"
        )
    return {
        "initialized": registry["initialized"],
        "aggregate_only": registry["aggregate_only"],
        "counts": normalized_counts,
    }


def _runtime_mission_result_summary(value: Any) -> dict[str, Any]:
    mission = _mapping(value, "runtime mission result")
    return {
        "expected_name": _text(
            mission.get("expected_name"),
            "runtime expected mission name",
            maximum=256,
        ),
        "runtime_filename_name": _text(
            mission.get("runtime_filename_name"),
            "runtime mission filename",
            maximum=256,
        ),
        "expected_theatre": _text(
            mission.get("expected_theatre"),
            "runtime expected theatre",
            maximum=256,
        ),
        "runtime_theatre": _text(
            mission.get("runtime_theatre"),
            "runtime observed theatre",
            maximum=256,
        ),
        "expected_groups": _nonnegative_integer(
            mission.get("expected_groups"),
            "runtime expected group count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
        "expected_units": _nonnegative_integer(
            mission.get("expected_units"),
            "runtime expected unit count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
        "expected_player_slots": _nonnegative_integer(
            mission.get("expected_player_slots"),
            "runtime expected player-slot count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
        "groups": _nonnegative_integer(
            mission.get("groups"),
            "runtime observed group count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
        "units": _nonnegative_integer(
            mission.get("units"),
            "runtime observed unit count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
        "available_slots": _nonnegative_integer(
            mission.get("available_slots"),
            "runtime available slot count",
            maximum=_MAX_REGISTRY_COUNT,
        ),
    }


def _runtime_smoke_summary(value: Any) -> dict[str, Any]:
    smoke = _mapping(value, "runtime smoke summary")
    required = _nonnegative_finite_number(
        smoke.get("required_seconds"),
        "runtime required smoke interval",
    )
    observed = _nonnegative_finite_number(
        smoke.get("observed_seconds"),
        "runtime observed smoke interval",
    )
    if not isinstance(smoke.get("interval_completed"), bool):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "runtime smoke completion flag is invalid"
        )
    return {
        "required_seconds": required,
        "observed_seconds": observed,
        "interval_completed": smoke["interval_completed"],
    }


def _runtime_coordinate_summary(value: Any) -> dict[str, Any]:
    record = _mapping(value, "runtime coordinate result")
    if not isinstance(record.get("passed"), bool):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            "runtime coordinate pass flag is invalid"
        )
    summary = {
        "label": _text(
            record.get("label"),
            "runtime coordinate label",
            maximum=128,
        ),
        "latitude": _bounded_finite_number(
            record.get("latitude"),
            "runtime coordinate latitude",
            minimum=-90.0,
            maximum=90.0,
        ),
        "longitude": _bounded_finite_number(
            record.get("longitude"),
            "runtime coordinate longitude",
            minimum=-180.0,
            maximum=180.0,
        ),
        "expected_x": _bounded_finite_number(
            record.get("expected_x"),
            "runtime coordinate expected x",
            minimum=-100_000_000.0,
            maximum=100_000_000.0,
        ),
        "expected_y": _bounded_finite_number(
            record.get("expected_y"),
            "runtime coordinate expected y",
            minimum=-100_000_000.0,
            maximum=100_000_000.0,
        ),
        "runtime_x": _optional_finite_number(
            record.get("runtime_x"),
            "runtime coordinate observed x",
        ),
        "runtime_y": _optional_finite_number(
            record.get("runtime_y"),
            "runtime coordinate observed y",
        ),
        "error_m": _optional_nonnegative_finite_number(
            record.get("error_m"),
            "runtime coordinate error",
        ),
        "tolerance_m": _bounded_finite_number(
            record.get("tolerance_m"),
            "runtime coordinate tolerance",
            minimum=0.001,
            maximum=10_000.0,
        ),
        "passed": record["passed"],
    }
    if summary["passed"] is True:
        runtime_x = summary["runtime_x"]
        runtime_y = summary["runtime_y"]
        reported_error = summary["error_m"]
        if runtime_x is None or runtime_y is None or reported_error is None:
            raise ValueError("passed runtime coordinate result is incomplete")
        calculated_error = math.hypot(
            float(runtime_x) - float(summary["expected_x"]),
            float(runtime_y) - float(summary["expected_y"]),
        )
        if reported_error > summary["tolerance_m"] or not math.isclose(
            float(reported_error),
            calculated_error,
            rel_tol=1e-12,
            abs_tol=1e-6,
        ):
            raise ValueError("passed runtime coordinate result is inconsistent")
    return summary


def _runtime_event_summary(value: Any) -> str:
    event = _mapping(value, "runtime event")
    return _text(
        event.get("name"),
        "runtime event name",
        maximum=64,
    )


def _runtime_validation(value: Any) -> dict[str, Any]:
    validation = _mapping(value, "runtime collection validation")
    required = {
        "manifest_valid",
        "inputs_unchanged",
        "hook_unchanged",
        "execution_bound",
        "result_present",
        "run_id_matched",
        "mode_matched",
        "runtime_version_matched",
        "failure_reasons",
        "runtime_valid",
    }
    if set(validation) != required:
        raise ValueError("runtime collection validation shape is invalid")
    for field in required - {"failure_reasons"}:
        if not isinstance(validation.get(field), bool):
            raise ValueError(  # noqa: TRY004 - external evidence value
                "runtime collection validation Boolean is invalid"
            )
    reasons = _list(validation.get("failure_reasons"), "runtime failure reasons")
    if len(reasons) > 256 or any(
        not isinstance(reason, str) or not 1 <= len(reason) <= 256
        for reason in reasons
    ):
        raise ValueError("runtime failure reasons are invalid")
    return {**validation, "failure_reasons": list(reasons)}


def _producer(value: Any) -> dict[str, Any]:
    producer = _mapping(value, "runtime producer")
    if set(producer) != {"name", "version", "git_commit", "git_dirty"}:
        raise ValueError("runtime producer shape is invalid")
    if producer.get("name") != "DCSMizzer":
        raise ValueError("runtime producer name is invalid")
    _text(producer.get("version"), "runtime producer version", maximum=64)
    commit = producer.get("git_commit")
    if commit is not None and (
        not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None
    ):
        raise ValueError("runtime producer commit is invalid")
    dirty = producer.get("git_dirty")
    if dirty is not None and not isinstance(dirty, bool):
        raise ValueError("runtime producer cleanliness is invalid")
    return dict(producer)


def _source_record(
    value: Any,
    label: str,
    *,
    maximum_bytes: int = MAX_MISSION_BYTES,
) -> dict[str, Any]:
    source = _mapping(value, label)
    relative = _text(source.get("relative_path"), f"{label} path", maximum=256)
    if (
        relative.startswith("/")
        or "\\" in relative
        or ":" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValueError(f"{label} relative path is invalid")
    return {
        "relative_path": relative,
        "size_bytes": _positive_integer(
            source.get("size_bytes"),
            f"{label} size",
            maximum=maximum_bytes,
        ),
        "sha256": _digest(source.get("sha256"), f"{label} hash"),
    }


def _runtime_distribution_manifest(value: Any) -> dict[str, Any]:
    source = _mapping(value, "runtime distribution manifest")
    if set(source) != {
        "relative_path",
        "size_bytes",
        "sha256",
        "semantic_identity",
        "verification",
    }:
        raise ValueError("runtime distribution manifest shape is invalid")
    base = _source_record(
        source,
        "runtime distribution manifest",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    semantic = _mapping(
        source.get("semantic_identity"),
        "runtime Steam semantic identity",
    )
    if set(semantic) != {
        "schema",
        "app_id",
        "build_id",
        "install_dir_casefold",
        "state_flags",
    } or semantic.get("schema") != STEAM_MANIFEST_IDENTITY_SCHEMA:
        raise ValueError("runtime Steam semantic identity shape is invalid")
    if semantic.get("app_id") != "223750":
        raise ValueError("runtime Steam app identity is invalid")
    build = _text(
        semantic.get("build_id"),
        "runtime Steam build ID",
        maximum=32,
    )
    if re.fullmatch(r"[0-9]+", build) is None:
        raise ValueError("runtime Steam build ID is invalid")
    install_dir = _text(
        semantic.get("install_dir_casefold"),
        "runtime Steam install directory",
        maximum=255,
    )
    if (
        install_dir != install_dir.casefold()
        or install_dir in {".", ".."}
        or any(character in install_dir for character in "/\\:")
    ):
        raise ValueError("runtime Steam install directory is invalid")
    if semantic.get("state_flags") != 4:
        raise ValueError("runtime Steam installed state is invalid")
    verification = source.get("verification")
    if verification != {
        "raw_hash_scope": "preparation_observation_only",
        "current_check": "selected_semantic_identity",
    }:
        raise ValueError("runtime Steam manifest verification policy is invalid")
    return {
        **base,
        "semantic_identity": {
            "schema": STEAM_MANIFEST_IDENTITY_SCHEMA,
            "app_id": "223750",
            "build_id": build,
            "install_dir_casefold": install_dir,
            "state_flags": 4,
        },
        "verification": dict(verification),
    }


def _optional_runtime_distribution_manifest(
    value: Any,
) -> dict[str, Any] | None:
    return None if value is None else _runtime_distribution_manifest(value)


def _optional_source_record(
    value: Any,
    label: str,
    *,
    maximum_bytes: int = MAX_MISSION_BYTES,
) -> dict[str, Any] | None:
    return (
        None
        if value is None
        else _source_record(value, label, maximum_bytes=maximum_bytes)
    )


def _optional_file_record(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    source = _mapping(value, label)
    if set(source) != {"name", "size_bytes", "sha256"}:
        raise ValueError(f"{label} shape is invalid")
    name = _text(source.get("name"), f"{label} name", maximum=256)
    if name in {".", ".."} or "/" in name or "\\" in name or ":" in name:
        raise ValueError(f"{label} name is invalid")
    size = source.get("size_bytes")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 <= size <= MAX_LOG_HASH_BYTES
    ):
        raise ValueError(f"{label} size is invalid")
    return {
        "name": name,
        "size_bytes": size,
        "sha256": _digest(source.get("sha256"), f"{label} hash"),
    }


def _limitations(value: Any, label: str) -> None:
    items = _list(value, f"{label} limitations")
    if not 1 <= len(items) <= 16 or any(
        not isinstance(item, str) or not 1 <= len(item) <= 1024 for item in items
    ):
        raise ValueError(f"{label} limitations are invalid")


def _assert_path_free(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and (
            _WINDOWS_ABSOLUTE.match(current) is not None
            or current.startswith("/")
        ):
            raise ValueError("evidence attestation contains an absolute path")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            f"{label} must be an object"
        )
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(  # noqa: TRY004 - malformed external evidence value
            f"{label} must be an array"
        )
    return value


def _text(value: Any, label: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _optional_text(value: Any, label: str, *, maximum: int) -> str | None:
    return None if value is None else _text(value, label, maximum=maximum)


def _finite_number(value: Any, label: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _nonnegative_finite_number(value: Any, label: str) -> int | float:
    number = _finite_number(value, label)
    if number < 0:
        raise ValueError(f"{label} is invalid")
    return number


def _bounded_finite_number(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> int | float:
    number = _finite_number(value, label)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} is invalid")
    return number


def _optional_finite_number(value: Any, label: str) -> int | float | None:
    return None if value is None else _finite_number(value, label)


def _optional_nonnegative_finite_number(
    value: Any,
    label: str,
) -> int | float | None:
    return None if value is None else _nonnegative_finite_number(value, label)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _optional_digest(value: Any, label: str) -> str | None:
    return None if value is None else _digest(value, label)


def _positive_integer(
    value: Any,
    label: str,
    *,
    maximum: int | None = None,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or (maximum is not None and value > maximum)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _nonnegative_integer(
    value: Any,
    label: str,
    *,
    maximum: int | None = None,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or (maximum is not None and value > maximum)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _semantic_hash(value: Any) -> str:
    return hashlib.sha256(
        (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
