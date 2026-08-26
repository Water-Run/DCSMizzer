"""Machine-readable product capability and refusal matrix."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CAPABILITIES: dict[str, Any] = {
    "schema": "dcsmizzer.capabilities/v3",
    "survey_basis": "2026-07-30",
    "implementation_reviewed_on": "2026-08-26",
    "inspect_miz": {
        "status": "implemented",
        "archive_policy": {
            "max_members": 4096,
            "max_member_uncompressed_bytes": 134217728,
            "max_total_uncompressed_bytes": 536870912,
            "max_compression_ratio": 250.0,
            "crc_expansion_after_pre_crc_archive_error": False,
            "member_parsing_after_archive_error": False,
        },
        "validation_levels": [
            "archive",
            "parse",
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
            "static plugin IDs and literal flyable-to-module mappings",
            "literal country/year service-life filters",
            "country identifiers",
            "default payload index and per-unit presets",
            "whole-payload fingerprints and exact observed-preset matching",
            "literal GUI cloud-preset IDs",
            "version-scoped Mission Editor weather presets plus statically "
            "extracted precipitation, temperature, fog, and dust constraints",
            "terrain airfield IDs encoded by static radio/beacon sources",
            "beacon-validated terrain coordinate conversion",
            "current MiG-29 GCI station, task, radar, and country evidence",
            "sanitized current Mission Editor options template",
            "current-literal unlimited airport warehouse templates",
        ],
        "coverage_is_explicit": True,
    },
    "official_terrain_catalog": {
        "status": "implemented_dated_snapshot",
        "provides": [
            "18 official terrain product cards surveyed on 2026-07-30",
            "14 unique current mission.theatre identities",
            "explicit canonical, regional-entitlement, and legacy-product "
            "relationships",
            "announced future regions kept separate from current product cards",
        ],
        "does_not_provide": [
            "live product availability",
            "terrain ownership",
            "physical terrain, scenery, airport, or runtime validity",
        ],
    },
    "commit_bound_upstream_queries": {
        "status": "implemented",
        "provides": [
            "generated pydcs airport centers, runways, and parking slots",
            "generated pydcs declarations across five unit categories",
            "generated pydcs plane/helicopter pylon/store/task declarations",
            "11 pydcs terrain packages with projection and center diagnostics",
            "14 BriefingRoom DCS theatre IDs, 802 airbases, parking, and "
            "bounded streamed planning-point queries",
            "validated commit-bound BriefingRoom airbase-centre coordinate "
            "fits for 13 of 14 theatre IDs; Afghanistan fails closed",
            "commit-bound BriefingRoom planning sea-mask minimum-distance "
            "and exact perpendicular land/water offset checks",
            "upstream remote, branch, commit, cleanliness, and source hashes",
        ],
        "authority": "lower_than_version_matched_installed_or_observed_data",
        "upstream_python_executed": False,
    },
    "acknowledged_upstream_cache": {
        "status": "implemented_explicit_opt_in_with_promotion_audit",
        "commands": [
            "upstream-status",
            "upstream-prepare",
            "upstream-promotion-audit",
        ],
        "provides": [
            "immutable pydcs and BriefingRoom origin, branch, commit, root "
            "tree, license, and required-path profiles",
            "read-only cache status with privacy-safe paths and remotes",
            "safe clone/fetch/detached-checkout preparation for clean "
            "recognized repositories",
            "offline use of an already available pinned commit object",
            "read-only fast-forward, full path-diff, license, and consumed-data "
            "model review before a candidate may enter repository regression",
        ],
        "boundaries": [
            "caller must always supply --cache-root",
            "no implicit .develope path",
            "upstream-status never writes",
            "a passing promotion audit never edits or authorizes editing a pin",
            "dirty, wrong-remote, linked, and reparse checkouts fail closed",
            "authority remains below version-matched installed DCS data",
        ],
    },
    "evidence_lifecycle": {
        "status": "implemented_bundle_drift_and_bound_attestation_gate",
        "commands": [
            "evidence-snapshot",
            "evidence-verify",
            "evidence-diff",
            "evidence-readiness",
        ],
        "provides": [
            "two-pass stable current-install and optional locked-upstream "
            "collection",
            "local-only content-addressed bundles with exact report hashes",
            "canonical manifest, producer commit, source authority, coverage, "
            "and collection outcome binding",
            "tamper, extra-file, source-drift, partial-coverage, and dirty-"
            "producer failure gates",
            "machine-readable historical installation/domain comparison",
            "current, stale, incomparable, absent, partial, and blocked "
            "readiness states",
            "revalidated runtime-manifest attestations with absolute paths and "
            "raw logs omitted",
            "validated physical-terrain attestations binding the full external "
            "source hash and finite coverage",
        ],
        "boundaries": [
            "bundle verification authenticates bytes and bindings, not who "
            "originally produced a report",
            "current static evidence does not become initialized registry or "
            "runtime evidence",
            "dirty or partial bundles cannot pass a required readiness gate",
            "raw local evidence bundles remain ignored and unredistributed",
            "physical-terrain attestations bind but do not embed raw local "
            "physical records",
            "runtime or terrain inputs absent from a current readiness pass "
            "remain current-check unavailable",
        ],
    },
    "observed_miz_registry": {
        "status": "implemented",
        "provides": [
            "anonymous observed identity occurrence distributions and "
            "structural field-count shapes",
            "anonymous unit-to-payload station/store relationships",
            "anonymous task, skill, action, predicate, and start observations",
            "airfield ID, parking, coordinate, and theatre-ref observations",
            "matching mission date, time, and anonymous weather "
            "schema/range observations",
            "anonymous trigger and goal structure/predicate counts",
            "anonymous options/requiredModules/warehouse shapes and "
            "airdrome-reference coverage",
            "caller-supplied exact theatre/unit filters echoed only when "
            "explicitly requested",
        ],
        "privacy_preserving": True,
        "raw_miz_strings_returned": False,
        "content_hashes_returned": False,
        "complete_registry_implied": False,
        "archive_handling": {
            "policy_checked_before_snapshot_copy": True,
            "raw_container_reads_bounded": True,
            "stable_snapshot_crc_checked_before_parse": True,
        },
    },
    "terrain_coordinate_conversion": {
        "status": "implemented_tiered",
        "method": (
            "WGS84 Transverse Mercator independently fitted and residual-"
            "validated against current installed static beacon pairs, with "
            "leave-one-airfield-out prediction, sample-domain diagnostics, "
            "and bounded WGS84 geodesic offsets"
        ),
        "lower_authority_method": (
            "WGS84 Transverse Mercator independently fitted with forward, "
            "inverse, candidate-separation, and leave-one-out checks against "
            "same-record BriefingRoom World.lat/lon and DCS.x/z airbase "
            "centres parsed from HEAD-bound airbase/theatre decision sources "
            "in a clean commit-bound export"
        ),
        "briefingroom_fit_coverage": {
            "validated_theatres": 13,
            "failed_closed_theatres": ["Afghanistan"],
            "runtime_validity": "never_implied",
        },
        "does_not_provide": [
            "terrain height or land-cover validation",
            "airport centers, runways, or parking",
            "unit placement validity",
            "minimum distance to authoritative current-DCS coastline geometry",
        ],
    },
    "coastline_planning_geometry": {
        "status": "implemented_commit_bound_planning_only",
        "command": "br-coastline",
        "provides": [
            "global minimum distance from an anchor to BriefingRoom "
            "water-exclusion landMasses segments",
            "exact perpendicular offsets whose requested land/water mask side "
            "is unique",
            "global remeasurement against every planning land-mass boundary",
            "bounded parsing of exact upstream theatre/bounds commit blobs plus "
            "source hashing",
        ],
        "does_not_provide": [
            "an authoritative or current initialized-DCS coastline",
            "terrain height, surface, collision, or placement validity",
            "safe ship, aircraft, or ground-unit placement",
        ],
        "runtime_validity": "requires_separate_exact_point_DCS_surface_evidence",
    },
    "terrain_physical_evidence": {
        "status": "implemented_probe_and_bounded_consumers",
        "provides": [
            "bounded initialized-theatre physical evidence schema with "
            "declared-version provenance and explicit runtime attestation",
            "manual mission-scripting probe generation without launching DCS",
            "verified disposable MIZ instrumentation that binds the exact "
            "generated probe script to a mission-start trigger",
            "sandbox-compatible env.info log framing and extraction",
            "height and surface point queries",
            "oriented sampled placement slope/surface plus conservative "
            "scenery-bound checks when a producer explicitly declares "
            "ground-placement-complete coverage",
            "three-trace sampled MSL route-corridor terrain-clearance checks",
            "scenery landmark instance search",
            "complete Mission Editor airfield-inventory consumption for "
            "runway, parking, and taxi geometry when such evidence is supplied",
            "commit-bound BriefingRoom runway and conservative parking "
            "planning envelopes for noninstalled maps",
        ],
        "validation_tiers": [
            "catalogued",
            "projection_valid",
            "terrain_sampled",
            "sampled_placement_or_corridor_passed",
            "dcs_runtime_verified",
        ],
        "current_runtime_exports_committed": 0,
        "does_not_provide": [
            "automatic DCS or Mission Editor launch",
            "continuous full-map elevation raster",
            "official airport boundary polygons",
            "mission-scripting runway, parking, or taxi geometry",
            "ground-placement collision completeness from the mission-"
            "scripting probe",
            "physical proof for an unqueried or uninstalled theatre",
        ],
    },
    "weather_registry": {
        "status": "implemented_current_install_static",
        "survey_install_snapshot": {
            "surveyed_on": "2026-07-30",
            "dcs_product_version": "2.9.28.26385",
            "preset_sources": 17,
            "parsed_presets": 17,
            "consistent_presets": 17,
        },
        "provides": [
            "data-only static and dynamic Mission Editor weather presets",
            "precipitation density and temperature eligibility",
            "fog mode IDs",
            "fog/dust mutual exclusion and enabled-dust minimum",
            "terrain/date temperature-override evidence",
        ],
        "runtime_validity": "never_implied",
    },
    "mission_generation": {
        "status": "implemented_low_level",
        "input": "dcsmizzer.miz-build-spec/v1",
        "provides": [
            "deterministic data-only Lua serialization",
            "deterministic MIZ archive assembly",
            "binary resource packaging",
            "full core-table round-trip comparison",
            "limited mission-structure consistency checks",
            "technical-fixture and strict complete-scenario quality profiles",
            "observed current runtime-shell and coalition-side shape checks",
            "current-profile AI waypoint task semantics and group references",
            "exact seven-pair first-waypoint start semantics",
            "official-pattern air-route locks: both first-point locks true "
            "and no later double-lock",
            "airborne lead heading aligned to a first route leg longer than one metre",
            "separate time-of-day and mission-elapsed route semantics, "
            "including zero-offset, non-late-activated human starts",
            "nonnegative air speeds with positive airborne-start and "
            "non-landing enroute speeds",
            "conservative Bombing activation-waypoint distance checks",
            "caller-declared scenario constraint checks",
            "group-ID-bound scenario role contracts",
            "conservative scenario-contract coverage warnings",
            "finite compilation of common trigger and goal predicates",
            "complete-scenario terminal flag guard/order checks that reject "
            "startup-phase writers and reset/other-value writes",
            "dictionary-backed timed guidance text actions",
            "open-handle-bound candidate validation and atomic final "
            "filesystem path update",
        ],
        "publication": {
            "atomic": False,
            "filesystem_path_update_atomic": True,
            "candidate_identity_bound_to_open_handle": True,
            "trusted_directory_required": True,
        },
        "resource_inputs": {
            "identity_bound_to_open_handles": True,
            "content_bound_to_sha256": True,
            "rechecked_before_completion": True,
        },
        "does_not_provide": [
            "natural-language scenario planning",
            "identifier inference",
            "compatibility inference",
            "complete per-aircraft Mission Editor unit-shell defaults",
            "arbitrary trigger scripts or event triggers",
            "runtime-validity claims",
        ],
    },
    "mission_verification": {
        "status": "implemented",
        "levels": [
            "archive",
            "CRC",
            "parse",
            "core-table round-trip",
            "limited mission structure",
            "complete-scenario warning gate",
            "static resource",
            "declared scenario contract",
        ],
        "runtime_validity": "never_implied",
    },
    "model_context_interfaces": {
        "status": "implemented",
        "provides": [
            "bounded catalog summaries under a 12 KiB UTF-8 output budget",
            "explicit nested-value truncation counts in bounded summaries",
            "explicit full/detail views for complete underlying reports",
            "bounded summaries of saved audit, build, verify, inspection, "
            "and evidence reports with recognized schema identifiers",
        ],
        "does_not_provide": [
            "semantic replacement for reading a failed report's relevant "
            "detailed fields",
            "saved-report authenticity or complete schema-shape validation",
            "validation reruns when summarizing a saved report",
        ],
    },
    "build_spec_evidence_audit": {
        "status": "implemented",
        "provides": [
            "current country-ID resolution",
            "installed cloud preset and base-range checks",
            "installed Mission Editor precipitation, temperature, fog, and "
            "dust relationship checks when that source is available",
            "full upstream terrain identity and provenance gates",
            "five-category exact type checks",
            "plane main-task namespace and capability checks",
            "complete current-preset composition fingerprints plus "
            "current-preset or commit-bound station/CLSID checks",
            "literal service-life conflict checks",
            "per-airport and per-slot primary-to-secondary evidence fallback",
            "pydcs slot-version-aware parking resolution",
            "pydcs/BriefingRoom cross-source parking dimension/capability "
            "conflict warnings",
            "complete authored route, unit, bullseye, zone, Bombing, "
            "AttackMapObject, EngageTargetsInZone, and structured "
            "ActivateGCI coordinate inventory; BombingRunway by runwayId",
            "source-self-consistent upstream bounds checks",
            "runway-task airport evidence checks",
            "fuel/countermeasure bounds and aircraft-property declaration checks",
            "current MiG-29 GCI station country checks",
        ],
        "does_not_provide": [
            "scenario-intent judgment",
            "terrain height or tactical-placement validation",
            "AI-behavior or runtime-validity claims",
        ],
    },
    "mig29_native_gci": {
        "status": "implemented_static_and_observed",
        "provides": [
            "current GCI station type and declared countries",
            "official training-mission ActivateGCI task shape",
            "manual-bound compatible radar types and link radius",
            "limited structural station/action/radar linkage checks",
        ],
        "runtime_validity": "never_implied",
        "ai_guidance_supported": False,
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
        "partial_static_evidence": [
            "current installed default payload observations",
            "commit-bound generated pydcs station/store declarations",
        ],
    },
    "whole_payload_matching": {
        "status": "implemented_observed_presets",
        "provides": [
            "deterministic full station-to-CLSID payload fingerprints",
            "exact, ambiguous, custom-composition, unknown-pair, metadata-"
            "mismatch, duplicate-station, source-incomplete, and missing-unit "
            "classifications",
            "current executable/Steam identity when readable, a bounded known "
            "source-scope digest, and explicit per-query completeness",
        ],
        "complete_compatibility": False,
        "reason": (
            "Exact default-preset observation is stronger than pairwise "
            "composition, but remains below a version-matched initialized "
            "aircraft/store compatibility export."
        ),
    },
    "airbase_runway_parking": {
        "status": "implemented_commit_bound_planning_all_14_theatres",
        "partial_static_evidence": [
            "radio/beacon-encoded named airfield IDs",
            "airfield and parking observations from parsed MIZ files",
            "commit-bound generated pydcs runway and parking declarations",
            "commit-bound BriefingRoom coverage for three additional theatres",
            "derived runway polygons and conservative parking envelopes",
        ],
        "current_initialized_registry": "requires_per_terrain_runtime_export",
    },
    "mission_editor_resave": {
        "status": "not_implemented",
    },
    "dcs_runtime_validation": {
        "status": "implemented_explicit_opt_in",
        "commands": [
            "runtime-prepare",
            "runtime-run",
            "runtime-collect",
        ],
        "provides": [
            "new disposable Saved Games DCSMizzer-* profiles",
            "dry-run command previews and explicit one-run launch authorization",
            "Steam and standalone launch paths with exact process identity binding",
            "Steam appmanifest preparation hashes plus launch-stable semantic "
            "app/build/install/state revalidation",
            "hash-bound aggregate initialized-registry evidence",
            "exact-MIZ load/start/bounded smoke and DCS Export coordinate checks",
            "timeout and post-result cleanup limited to the re-attested process",
        ],
        "does_not_imply": [
            "runtime validity without a passing collection for the exact artifact",
            "AI behaviour, every trigger path, or a human playtest",
            "Mission Editor resave",
        ],
    },
    "dcs_launch": {
        "status": "implemented_explicit_opt_in_dcs_only",
        "dry_run_default": True,
        "ordinary_saved_games_profiles_modified": False,
        "mission_editor_launch": "not_implemented",
    },
}


def capabilities_report() -> dict[str, Any]:
    """Return an isolated copy suitable for JSON output."""

    return deepcopy(_CAPABILITIES)
