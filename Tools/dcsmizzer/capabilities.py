"""Machine-readable product capability and refusal matrix."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CAPABILITIES: dict[str, Any] = {
    "schema": "dcsmizzer.capabilities/v1",
    "survey_basis": "2026-07-27",
    "inspect_miz": {
        "status": "implemented",
        "validation_levels": [
            "archive",
            "parse",
            "static-structure",
        ],
        "runtime_validity": "never_implied",
    },
    "inspect_cmp": {
        "status": "implemented",
        "validation_levels": [
            "parse",
            "static-reference",
        ],
        "runtime_validity": "never_implied",
    },
    "dcs_static_sources": {
        "status": "implemented",
        "provides": [
            "installed module directories",
            "country identifiers",
            "default payload presets",
        ],
    },
    "mission_generation": {
        "status": "not_implemented",
        "reason": "No product mission assembler or serializer exists yet.",
    },
    "campaign_generation": {
        "status": "not_implemented",
        "reason": "No product campaign assembler or serializer exists yet.",
    },
    "complete_unit_registry": {
        "status": "requires_version_matched_runtime_export",
    },
    "complete_pylon_compatibility": {
        "status": "requires_version_matched_runtime_export",
    },
    "airbase_runway_parking": {
        "status": "requires_per_terrain_runtime_export",
    },
    "mission_editor_resave": {
        "status": "not_implemented",
    },
    "dcs_runtime_validation": {
        "status": "not_implemented",
    },
    "dcs_launch": {
        "status": "not_implemented",
        "reason": "Product tools are read-only and never start DCS or Mission Editor.",
    },
}


def capabilities_report() -> dict[str, Any]:
    """Return an isolated copy suitable for JSON output."""

    return deepcopy(_CAPABILITIES)
