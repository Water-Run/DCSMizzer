from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from .archive import inspect_miz
from .campaign import analyse_cmp
from .capabilities import capabilities_report
from .dcs_static import (
    countries_report,
    payload_report,
    static_install_report,
)
from .mission import MissionStats, analyse_miz


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if args.command is None:
        parser.print_help(stderr)
        return 2

    try:
        if args.command == "capabilities":
            report = capabilities_report()
            exit_code = 0
        elif args.command == "inspect":
            report, exit_code = _inspect(args.path, skip_crc=args.skip_crc)
        elif args.command == "dcs-static":
            report = static_install_report(args.dcs_root)
            exit_code = 0
        elif args.command == "dcs-countries":
            report = countries_report(args.dcs_root)
            exit_code = 0
        else:
            report = payload_report(args.dcs_root, args.unit_type)
            exit_code = 0 if report["presets"] else 1
        stdout.write(_json(report))
        return exit_code
    except (OSError, ValueError) as error:
        stderr.write(f"dcsmizzer tool error: {error}\n")
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcsmizzer.py",
        description="Read-only, model-facing DCSMizzer tools",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("capabilities")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--skip-crc", action="store_true")

    static = commands.add_parser("dcs-static")
    static.add_argument("--dcs-root", type=Path, required=True)

    countries = commands.add_parser("dcs-countries")
    countries.add_argument("--dcs-root", type=Path, required=True)

    payloads = commands.add_parser("dcs-payloads")
    payloads.add_argument("--dcs-root", type=Path, required=True)
    payloads.add_argument("--unit-type", required=True)
    return parser


def _inspect(path: Path, *, skip_crc: bool) -> tuple[dict[str, Any], int]:
    if not path.is_file():
        raise ValueError("input file does not exist")
    extension = path.suffix.casefold()
    if extension == ".miz":
        archive = inspect_miz(path, verify_crc=not skip_crc)
        mission = analyse_miz(path)
        archive_valid = bool(
            archive.valid_zip
            and archive.safe
            and (archive.crc_status in {"passed", "skipped"})
        )
        parse_valid = mission.parse_valid
        report = {
            "schema": "dcsmizzer.miz-inspection/v1",
            "input": str(path),
            "kind": "miz",
            "archive": archive.to_dict(),
            "mission": {
                "parse_valid": mission.parse_valid,
                "version": mission.mission_version,
                "theatre": mission.theatre,
                "core_members": [asdict(item) for item in mission.members],
                "stats": _mission_stats(mission.stats),
            },
            "validation": {
                "archive_valid": archive_valid,
                "crc_verified": archive.crc_status == "passed",
                "parse_valid": parse_valid,
                "static_structure_valid": archive_valid and parse_valid,
                "runtime_valid": None,
            },
            "limitations": [
                "No Lua code was executed.",
                "No DCS or Mission Editor process was started.",
                "Runtime validity is unknown until DCS loads the mission.",
            ],
        }
        return report, 0 if archive_valid and parse_valid else 1
    if extension == ".cmp":
        campaign = analyse_cmp(path)
        static_reference_valid = bool(
            campaign.parse_valid
            and campaign.start_stage_exists
            and campaign.missing_references == 0
            and campaign.invalid_intervals == 0
        )
        report = {
            "schema": "dcsmizzer.cmp-inspection/v1",
            "input": str(path),
            "kind": "cmp",
            "campaign": {
                **asdict(campaign),
                "top_level_keys": list(campaign.top_level_keys),
            },
            "validation": {
                "parse_valid": campaign.parse_valid,
                "static_reference_valid": static_reference_valid,
                "runtime_valid": None,
            },
            "limitations": [
                "Referenced MIZ files were checked for presence only.",
                "No DCS or Mission Editor process was started.",
            ],
        }
        return report, 0 if static_reference_valid else 1
    raise ValueError("inspect supports only .miz and .cmp files")


def _mission_stats(stats: MissionStats) -> dict[str, Any]:
    return {
        "groups": stats.groups,
        "units": stats.units,
        "waypoints": stats.waypoints,
        "human_slots": stats.human_slots,
        "pylon_assignments": stats.pylon_assignments,
        "pylons_with_clsid": stats.pylons_with_clsid,
        "payload_unique_clsids": len(stats.payload_clsids),
        "payload_clsids": sorted(stats.payload_clsids),
        "trigger_rules": stats.trigger_rules,
        "trigger_conditions": stats.trigger_conditions,
        "trigger_actions": stats.trigger_actions,
        "script_actions": stats.script_actions,
        "goals": stats.goals,
        "dictionary_entries": stats.dictionary_entries,
        "resource_mappings": stats.resource_mappings,
        "briefing_characters": stats.briefing_characters,
        "resource_extensions": stats.resource_extensions,
        "missing_resource_members": stats.missing_resource_members,
        "referenced_missing_resources": stats.referenced_missing_resources,
        "unreferenced_missing_resources": stats.unreferenced_missing_resources,
        "warehouse_airports": stats.warehouse_airports,
        "warehouse_objects": stats.warehouse_objects,
        "late_activation_groups": stats.late_activation_groups,
        "uncontrolled_groups": stats.uncontrolled_groups,
        "uncontrollable_groups": stats.uncontrollable_groups,
        "modern_fields": stats.modern_fields,
        "waypoint_actions": stats.waypoint_actions,
        "waypoint_task_ids": stats.waypoint_task_ids,
        "top_level_fields": list(stats.top_level_fields),
    }


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
