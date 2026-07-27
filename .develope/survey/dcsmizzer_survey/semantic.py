from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .campaign import CampaignObservation, analyse_cmp
from .mission import MissionStats, MizObservation, analyse_miz
from .model import Diagnostic, EvidenceRoot
from .survey import discover_evidence_files


@dataclass(frozen=True)
class SemanticSurveyConfig:
    roots: tuple[EvidenceRoot, ...]
    collected_at: datetime

    def __post_init__(self) -> None:
        if not self.roots:
            raise ValueError("at least one evidence root is required")
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        names = [root.name for root in self.roots]
        if len(names) != len(set(names)):
            raise ValueError("evidence root names must be unique")


@dataclass
class _CoreMemberAggregate:
    present: int = 0
    parsed: int = 0
    encodings: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)

    def add(self, member: Any) -> None:
        self.present += int(member.present)
        self.parsed += int(member.parsed)
        if member.encoding is not None:
            self.encodings[member.encoding] += 1
        if member.error_code is not None:
            self.errors[member.error_code] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "parsed": self.parsed,
            "encodings": dict(sorted(self.encodings.items())),
            "errors": dict(sorted(self.errors.items())),
        }


@dataclass
class _MissionStatsAggregate:
    groups: Counter[str] = field(default_factory=Counter)
    units: Counter[str] = field(default_factory=Counter)
    waypoints: Counter[str] = field(default_factory=Counter)
    human_slots: Counter[str] = field(default_factory=Counter)
    pylon_assignments: int = 0
    pylons_with_clsid: int = 0
    payload_clsids: set[str] = field(default_factory=set)
    trigger_rules: int = 0
    trigger_conditions: int = 0
    trigger_actions: int = 0
    script_actions: int = 0
    goals: int = 0
    dictionary_entries: int = 0
    resource_mappings: int = 0
    briefing_characters: int = 0
    resource_extensions: Counter[str] = field(default_factory=Counter)
    missing_resource_members: int = 0
    referenced_missing_resources: int = 0
    unreferenced_missing_resources: int = 0
    warehouse_airports: int = 0
    warehouse_objects: int = 0
    late_activation_groups: int = 0
    uncontrolled_groups: int = 0
    uncontrollable_groups: int = 0
    modern_fields: Counter[str] = field(default_factory=Counter)
    waypoint_actions: Counter[str] = field(default_factory=Counter)
    waypoint_task_ids: Counter[str] = field(default_factory=Counter)
    top_level_fields: Counter[str] = field(default_factory=Counter)

    def add(self, stats: MissionStats) -> None:
        self.groups.update(stats.groups)
        self.units.update(stats.units)
        self.waypoints.update(stats.waypoints)
        self.human_slots.update(stats.human_slots)
        self.pylon_assignments += stats.pylon_assignments
        self.pylons_with_clsid += stats.pylons_with_clsid
        self.payload_clsids.update(stats.payload_clsids)
        self.trigger_rules += stats.trigger_rules
        self.trigger_conditions += stats.trigger_conditions
        self.trigger_actions += stats.trigger_actions
        self.script_actions += stats.script_actions
        self.goals += stats.goals
        self.dictionary_entries += stats.dictionary_entries
        self.resource_mappings += stats.resource_mappings
        self.briefing_characters += stats.briefing_characters
        self.resource_extensions.update(stats.resource_extensions)
        self.missing_resource_members += stats.missing_resource_members
        self.referenced_missing_resources += stats.referenced_missing_resources
        self.unreferenced_missing_resources += stats.unreferenced_missing_resources
        self.warehouse_airports += stats.warehouse_airports
        self.warehouse_objects += stats.warehouse_objects
        self.late_activation_groups += stats.late_activation_groups
        self.uncontrolled_groups += stats.uncontrolled_groups
        self.uncontrollable_groups += stats.uncontrollable_groups
        self.modern_fields.update(stats.modern_fields)
        self.waypoint_actions.update(stats.waypoint_actions)
        self.waypoint_task_ids.update(stats.waypoint_task_ids)
        self.top_level_fields.update(stats.top_level_fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": _sorted_counter(self.groups),
            "units": _sorted_counter(self.units),
            "waypoints": _sorted_counter(self.waypoints),
            "human_slots": _sorted_counter(self.human_slots),
            "pylon_assignments": self.pylon_assignments,
            "pylons_with_clsid": self.pylons_with_clsid,
            "payload_unique_clsids": len(self.payload_clsids),
            "trigger_rules": self.trigger_rules,
            "trigger_conditions": self.trigger_conditions,
            "trigger_actions": self.trigger_actions,
            "script_actions": self.script_actions,
            "goals": self.goals,
            "dictionary_entries": self.dictionary_entries,
            "resource_mappings": self.resource_mappings,
            "briefing_characters": self.briefing_characters,
            "resource_extensions": _sorted_counter(self.resource_extensions),
            "missing_resource_members": self.missing_resource_members,
            "referenced_missing_resources": self.referenced_missing_resources,
            "unreferenced_missing_resources": self.unreferenced_missing_resources,
            "warehouse_airports": self.warehouse_airports,
            "warehouse_objects": self.warehouse_objects,
            "late_activation_groups": self.late_activation_groups,
            "uncontrolled_groups": self.uncontrolled_groups,
            "uncontrollable_groups": self.uncontrollable_groups,
            "modern_fields": _sorted_counter(self.modern_fields),
            "waypoint_actions": _sorted_counter(self.waypoint_actions),
            "waypoint_task_ids": _sorted_counter(self.waypoint_task_ids),
            "top_level_fields": _sorted_counter(self.top_level_fields),
        }


@dataclass
class _MizAggregate:
    instances: int = 0
    parse_valid: int = 0
    core_members: dict[str, _CoreMemberAggregate] = field(default_factory=dict)
    versions: Counter[int | float] = field(default_factory=Counter)
    theatres: Counter[str] = field(default_factory=Counter)
    stats: _MissionStatsAggregate = field(default_factory=_MissionStatsAggregate)

    def add(self, observation: MizObservation) -> None:
        self.instances += 1
        self.parse_valid += int(observation.parse_valid)
        for member in observation.members:
            self.core_members.setdefault(
                member.name,
                _CoreMemberAggregate(),
            ).add(member)
        if observation.mission_version is not None:
            self.versions[observation.mission_version] += 1
        if observation.theatre is not None:
            self.theatres[observation.theatre] += 1
        self.stats.add(observation.stats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instances": self.instances,
            "parse_valid": self.parse_valid,
            "core_members": {
                name: aggregate.to_dict()
                for name, aggregate in sorted(self.core_members.items())
            },
            "versions": {
                _number_key(key): value
                for key, value in sorted(
                    self.versions.items(),
                    key=lambda item: float(item[0]),
                )
            },
            "theatres": _sorted_counter(self.theatres),
            "stats": self.stats.to_dict(),
        }


@dataclass
class _CampaignAggregate:
    instances: int = 0
    parse_valid: int = 0
    encodings: Counter[str] = field(default_factory=Counter)
    versions: Counter[int | float] = field(default_factory=Counter)
    stages: int = 0
    mission_references: int = 0
    resolved_references: int = 0
    missing_references: int = 0
    interval_overlaps: int = 0
    interval_gaps: int = 0
    invalid_intervals: int = 0
    missing_start_stage: int = 0
    top_level_keys: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)

    def add(self, observation: CampaignObservation) -> None:
        self.instances += 1
        self.parse_valid += int(observation.parse_valid)
        if observation.encoding is not None:
            self.encodings[observation.encoding] += 1
        if observation.version is not None:
            self.versions[observation.version] += 1
        self.stages += observation.stage_count
        self.mission_references += observation.mission_references
        self.resolved_references += observation.resolved_references
        self.missing_references += observation.missing_references
        self.interval_overlaps += observation.interval_overlaps
        self.interval_gaps += observation.interval_gaps
        self.invalid_intervals += observation.invalid_intervals
        if observation.parse_valid and not observation.start_stage_exists:
            self.missing_start_stage += 1
        self.top_level_keys.update(observation.top_level_keys)
        if observation.error_code is not None:
            self.errors[observation.error_code] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "instances": self.instances,
            "parse_valid": self.parse_valid,
            "encodings": _sorted_counter(self.encodings),
            "versions": {
                _number_key(key): value
                for key, value in sorted(
                    self.versions.items(),
                    key=lambda item: float(item[0]),
                )
            },
            "stages": self.stages,
            "mission_references": self.mission_references,
            "resolved_references": self.resolved_references,
            "missing_references": self.missing_references,
            "interval_overlaps": self.interval_overlaps,
            "interval_gaps": self.interval_gaps,
            "invalid_intervals": self.invalid_intervals,
            "missing_start_stage": self.missing_start_stage,
            "top_level_keys": _sorted_counter(self.top_level_keys),
            "errors": _sorted_counter(self.errors),
        }


@dataclass
class _SemanticRoot:
    source: EvidenceRoot
    exists: bool
    errors: list[Diagnostic] = field(default_factory=list)
    miz: _MizAggregate = field(default_factory=_MizAggregate)
    cmp: _CampaignAggregate = field(default_factory=_CampaignAggregate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.source.name,
            "kind": self.source.kind.value,
            "version": self.source.version,
            "exists": self.exists,
            "errors": len(self.errors),
            "miz": self.miz.to_dict(),
            "cmp": self.cmp.to_dict(),
        }


@dataclass(frozen=True)
class SemanticSurveyResult:
    collected_at: datetime
    roots: tuple[_SemanticRoot, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "dcsmizzer.semantic-survey/v1",
            "collected_at": _format_utc(self.collected_at),
            "totals": {
                "miz_instances": sum(root.miz.instances for root in self.roots),
                "miz_parse_valid": sum(root.miz.parse_valid for root in self.roots),
                "cmp_instances": sum(root.cmp.instances for root in self.roots),
                "cmp_parse_valid": sum(root.cmp.parse_valid for root in self.roots),
            },
            "roots": [root.to_dict() for root in self.roots],
        }

    def has_errors(self) -> bool:
        return any(
            root.errors
            or root.miz.parse_valid != root.miz.instances
            or root.cmp.parse_valid != root.cmp.instances
            for root in self.roots
        )


def survey_semantics(config: SemanticSurveyConfig) -> SemanticSurveyResult:
    roots: list[_SemanticRoot] = []
    for source in config.roots:
        result = _SemanticRoot(
            source=source,
            exists=source.path.is_dir(),
        )
        roots.append(result)
        if not result.exists:
            result.errors.append(
                Diagnostic(
                    "root_unavailable",
                    layer="discovery",
                )
            )
            continue
        paths = discover_evidence_files(source.path, result.errors)
        for path in paths:
            if path.suffix.lower() == ".miz":
                result.miz.add(analyse_miz(path))
            elif path.suffix.lower() == ".cmp":
                result.cmp.add(analyse_cmp(path))
    return SemanticSurveyResult(
        collected_at=config.collected_at,
        roots=tuple(roots),
    )


def semantic_to_json(result: SemanticSurveyResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"


def _sorted_counter(counter: Counter[Any]) -> dict[str, int]:
    return {
        str(key): value
        for key, value in sorted(counter.items(), key=lambda item: str(item[0]))
    }


def _number_key(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_utc(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
