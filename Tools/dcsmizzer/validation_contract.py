"""Machine-readable validation ladder and exact runtime-tier derivation."""

from __future__ import annotations

from typing import Any


CONTRACT_SCHEMA = "dcsmizzer.validation-contract/v1"
TIERS_SCHEMA = "dcsmizzer.validation-tiers/v1"
TIER_NAMES = ("V0", "V1", "V2", "V3", "V4", "V5")
_V3_ONLY_REASONS = frozenset(
    {
        "smoke_interval_incomplete",
        "smoke_required_interval_mismatch",
        "smoke_observed_interval_invalid",
        "coordinate_check_count_mismatch",
        "coordinate_check_failed",
        "coordinate_checks_not_passed",
        "runtime_event_missing:simulation_start",
        "runtime_event_missing:smoke_interval_complete",
    }
)


def validation_contract_report() -> dict[str, Any]:
    """Publish the stable V0-V5 meanings without claiming observed evidence."""

    levels = [
        {
            "level": "V0",
            "name": "static_validity",
            "minimum_evidence": "schema_and_authored_spec_audit_pass",
            "does_not_imply": ["archive_validity", "DCS_load"],
        },
        {
            "level": "V1",
            "name": "archive_validity",
            "minimum_evidence": (
                "safe_archive_required_members_parse_and_readback_pass"
            ),
            "does_not_imply": ["DCS_load", "simulation_start"],
        },
        {
            "level": "V2",
            "name": "DCS_load_validity",
            "minimum_evidence": (
                "exact_version_and_hash_bound_artifact_loads_in_DCS"
            ),
            "does_not_imply": ["stable_interval", "AI_behaviour"],
        },
        {
            "level": "V3",
            "name": "simulation_smoke_validity",
            "minimum_evidence": (
                "V2_plus_simulation_start_and_declared_stable_interval"
            ),
            "does_not_imply": ["behavioural_checkpoints", "human_playtest"],
        },
        {
            "level": "V4",
            "name": "behavioural_checkpoint_validity",
            "minimum_evidence": (
                "V3_plus_exact_contract_bound_checkpoint_observations"
            ),
            "does_not_imply": ["unobserved_behaviour", "human_playtest"],
        },
        {
            "level": "V5",
            "name": "human_playtest_validity",
            "minimum_evidence": "recorded_scoped_human_playtest",
            "does_not_imply": ["unplayed_paths", "another_artifact_or_version"],
        },
    ]
    return {
        "schema": CONTRACT_SCHEMA,
        "levels": levels,
        "ordering": list(TIER_NAMES),
        "rules": {
            "lower_never_implies_higher": True,
            "artifact_and_version_specific": True,
            "unobserved_is_never_passed": True,
            "registry_probe_is_not_mission_V2_or_V3": True,
            "ordinary_CI_can_publish_only_offline_evidence": True,
        },
        "human_summary": [
            f"{item['level']} {item['name']}: {item['minimum_evidence']}"
            for item in levels
        ],
        "runtime_work_performed": False,
    }


def runtime_tier_report(
    manifest: dict[str, Any],
    result: dict[str, Any] | None,
    failure_reasons: list[str] | tuple[str, ...],
    *,
    inputs_unchanged: bool,
) -> dict[str, Any]:
    """Partition one revalidated collection into conservative mission tiers."""

    mode = manifest.get("mode")
    if mode != "mission-smoke":
        levels = [
            _level(
                name,
                "not_applicable",
                "registry_probe_is_not_mission_validation",
            )
            for name in TIER_NAMES
        ]
        return {
            "schema": TIERS_SCHEMA,
            "scope": "registry-probe",
            "highest_achieved": None,
            "levels": levels,
        }

    mission = manifest.get("inputs", {}).get("mission")
    v1_reasons: list[str] = []
    if not isinstance(mission, dict):
        v1_reasons.append("mission_input_missing")
    else:
        if mission.get("archive_valid") is not True:
            v1_reasons.append("prepared_archive_not_valid")
        if mission.get("parse_valid") is not True:
            v1_reasons.append("prepared_archive_not_parse_valid")
    if not inputs_unchanged:
        v1_reasons.append("runtime_inputs_changed")

    all_reasons = sorted(set(failure_reasons))
    v2_reasons = [
        reason for reason in all_reasons if reason not in _V3_ONLY_REASONS
    ]
    if result is None and "runtime_result_missing" not in v2_reasons:
        v2_reasons.append("runtime_result_missing")
        v2_reasons.sort()

    v1_passed = not v1_reasons
    v2_passed = v1_passed and not v2_reasons
    v3_passed = v2_passed and not all_reasons
    levels = [
        _level(
            "V0",
            "not_evaluated",
            "authored_spec_audit_not_part_of_runtime_collection",
        ),
        _level(
            "V1",
            "passed" if v1_passed else "failed",
            "prepared_exact_archive_and_parse_revalidated",
            v1_reasons,
        ),
        _level(
            "V2",
            "passed" if v2_passed else "failed",
            "exact_DCS_load_and_mission_identity_collection",
            v2_reasons,
        ),
        _level(
            "V3",
            "passed" if v3_passed else "failed",
            "simulation_start_stable_interval_and_coordinate_collection",
            all_reasons,
        ),
        _level(
            "V4",
            "not_evaluated",
            "no_behavioural_checkpoint_contract_was_collected",
        ),
        _level(
            "V5",
            "not_evaluated",
            "no_human_playtest_record_was_collected",
        ),
    ]
    highest = "V3" if v3_passed else "V2" if v2_passed else "V1" if v1_passed else None
    return {
        "schema": TIERS_SCHEMA,
        "scope": "exact-mission",
        "highest_achieved": highest,
        "levels": levels,
    }


def _level(
    level: str,
    status: str,
    basis: str,
    failure_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "level": level,
        "status": status,
        "basis": basis,
        "failure_reasons": list(failure_reasons or []),
    }
