from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from .archive import inspect_miz
from .br_static import (
    br_airbase_report,
    br_spawnpoint_report,
    br_terrain_report,
)
from .br_coordinates import br_coordinate_report
from .builder import build_miz, verify_miz
from .campaign import analyse_cmp
from .capabilities import capabilities_report
from .coastline import br_coastline_report
from .coordinates import coordinate_report
from .dcs_static import (
    airbase_beacon_report,
    countries_report,
    module_index_report,
    payload_index_report,
    payload_match_report,
    payload_report,
    static_install_report,
)
from .evidence import (
    compare_evidence,
    create_evidence_snapshot,
    evidence_readiness,
    required_evidence_domains,
    verify_evidence_bundle,
)
from .gci import gci_evidence_report, gci_report_complete
from .mission import (
    MissionStats,
    analyse_miz,
    observe_miz_without_member_reads,
)
from .observed import ObservedRoot, build_observed_registry
from .pydcs_static import (
    pydcs_aircraft_report,
    pydcs_airport_report,
    pydcs_terrain_report,
    pydcs_unit_report,
)
from .report_views import (
    VIEW_COMMANDS,
    output_view,
    report_summary,
)
from .spec_audit import audit_build_spec
from .templates import options_template_report, warehouse_template_report
from .terrain_catalog import terrain_catalog_report
from .terrain_coverage import combined_terrain_report
from .terrain_physical import (
    airfield_footprint_report,
    br_airfield_footprint_report,
    landmark_report,
    physical_point_report,
    placement_report,
    terrain_corridor_report,
)
from .runtime import collect_runtime, prepare_runtime, run_runtime
from .terrain_probe import (
    extract_terrain_probe,
    generate_terrain_probe_script,
)
from .terrain_probe_miz import instrument_terrain_probe_miz
from .upstream_cache import (
    prepare_upstreams,
    upstream_report_usable,
    upstream_status_report,
)
from .weather import cloud_preset_report, weather_registry_report


DEFAULT_EXACT_PARKING_LIMIT = 8
MAX_CLI_ERROR_BYTES = 2 * 1024
_CLI_ERROR_PREFIX = "dcsmizzer tool error: "
_CLI_ERROR_SUFFIX = "… [truncated]\n"


class _CliArgumentError(ValueError):
    """An argparse failure that has not yet written to a process stream."""


class _BoundedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliArgumentError(message)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _CliArgumentError as error:
        _write_tool_error(stderr, f"argument error: {error}")
        return 2
    except SystemExit as error:
        return int(error.code)
    if args.command is None:
        parser.print_help(stderr)
        return 2

    try:
        if args.command == "capabilities":
            report = capabilities_report()
            exit_code = 0
        elif args.command == "evidence-snapshot":
            report = create_evidence_snapshot(
                args.dcs_root,
                args.bundle_root,
                cache_root=args.cache_root,
                runtime_manifests=args.runtime_manifest,
                terrain_evidence=args.terrain_evidence,
            )
            exit_code = (
                0
                if report["validation"]["bundle_valid"] is True
                and report["validation"]["reproducible_producer"] is True
                and report["validation"]["collection_complete"] is True
                and report["validation"]["coverage_unblocked"] is True
                else 1
            )
        elif args.command == "evidence-verify":
            report = verify_evidence_bundle(args.bundle)
            exit_code = 0 if report["validation"]["bundle_valid"] is True else 1
        elif args.command == "evidence-diff":
            report = compare_evidence(args.before, args.after)
            exit_code = 0
        elif args.command == "evidence-readiness":
            report = evidence_readiness(
                args.bundle,
                args.dcs_root,
                cache_root=args.cache_root,
                required_domains=args.required_domain,
                runtime_manifests=args.runtime_manifest,
                terrain_evidence=args.terrain_evidence,
            )
            exit_code = (
                0
                if report["validation"]["all_required_domains_ready"] is True
                else 1
            )
        elif args.command == "upstream-status":
            report = upstream_status_report(args.cache_root)
            exit_code = 0 if upstream_report_usable(report) else 1
        elif args.command == "upstream-prepare":
            report = prepare_upstreams(
                args.cache_root,
                offline=args.offline,
            )
            exit_code = 0 if upstream_report_usable(report) else 1
        elif args.command == "report-summary":
            report = report_summary(args.path)
            exit_code = 0
        elif args.command == "runtime-prepare":
            report = prepare_runtime(
                args.dcs_root,
                args.saved_games_root,
                run_id=args.run_id,
                mode=args.mode,
                mission=args.mission,
                coordinate_checks=args.coordinate_checks,
                smoke_seconds=args.smoke_seconds,
            )
            exit_code = 0
        elif args.command == "runtime-run":
            report = run_runtime(
                args.manifest,
                authorize=args.authorize_dcs_launch,
                timeout_seconds=args.timeout,
                terminate_grace_seconds=args.terminate_grace,
            )
            exit_code = 0 if report["validation"]["completed"] is True else 1
        elif args.command == "runtime-collect":
            report = collect_runtime(args.manifest)
            exit_code = 0 if report["validation"]["runtime_valid"] is True else 1
        elif args.command == "inspect":
            report, exit_code = _inspect(args.path, skip_crc=args.skip_crc)
        elif args.command == "dcs-static":
            report = static_install_report(args.dcs_root)
            exit_code = 0
        elif args.command == "dcs-countries":
            report = countries_report(args.dcs_root)
            exit_code = 0
        elif args.command == "dcs-payloads":
            report = payload_report(args.dcs_root, args.unit_type)
            exit_code = 0 if report["presets"] else 1
        elif args.command == "dcs-payload-index":
            report = payload_index_report(args.dcs_root)
            exit_code = 0
        elif args.command == "dcs-payload-match":
            report = payload_match_report(
                args.dcs_root,
                args.unit_type,
                (
                    []
                    if args.empty
                    else _parse_payload_pylons(args.pylon)
                ),
                tasks=args.task,
                preset_name=args.preset_name,
                display_name=args.display_name,
                category=args.category,
            )
            exit_code = (
                0 if report["verified_exact_observed_preset"] else 1
            )
        elif args.command == "dcs-modules":
            report = module_index_report(
                args.dcs_root,
                module=args.module,
                unit_type=args.unit_type,
                service_country=args.service_country,
                service_year=args.service_year,
            )
            filtered = args.module is not None or args.unit_type is not None
            service_query = (
                report["unit_type_resolution"]["service_life_query"]
                if report["unit_type_resolution"] is not None
                else None
            )
            exit_code = (
                1
                if (filtered and report["coverage"]["matching_modules"] == 0)
                or (
                    service_query is not None
                    and service_query["requested"]
                    and not service_query["matched"]
                )
                else 0
            )
        elif args.command == "dcs-cloud-presets":
            report = cloud_preset_report(
                args.dcs_root,
                preset=args.preset,
            )
            exit_code = (
                1
                if args.preset is not None
                and report["coverage"]["matching_presets"] == 0
                else 0
            )
        elif args.command == "dcs-airbases":
            report = airbase_beacon_report(
                args.dcs_root,
                args.terrain,
                airdrome_id=args.airdrome_id,
            )
            exit_code = 0 if report["airbases"] or args.airdrome_id is None else 1
        elif args.command == "dcs-coordinates":
            report = coordinate_report(
                args.dcs_root,
                args.terrain,
                latitude=args.latitude,
                longitude=args.longitude,
                map_x=args.map_x,
                map_y=args.map_y,
                offset_bearing_deg=args.offset_bearing,
                offset_distance_m=args.offset_distance,
            )
            exit_code = 0
        elif args.command == "dcs-gci":
            report = gci_evidence_report(args.dcs_root)
            exit_code = 0 if gci_report_complete(report) else 1
        elif args.command == "dcs-options-template":
            report = options_template_report(
                args.dcs_root,
                player_name=args.player_name,
                full_sim=args.full_sim,
            )
            exit_code = 0
        elif args.command == "dcs-warehouse-template":
            report = warehouse_template_report(
                args.dcs_root,
                args.airdrome_id,
                coalition=args.coalition,
            )
            exit_code = 0
        elif args.command == "pydcs-terrains":
            report = pydcs_terrain_report(
                args.pydcs_root,
                terrain=args.terrain,
                latitude=args.latitude,
                longitude=args.longitude,
                map_x=args.map_x,
                map_y=args.map_y,
            )
            exit_code = (
                1
                if (
                    (
                        args.terrain is not None
                        and report["coverage"].get("exact_query_usable") is not True
                    )
                    or report["coverage"]["terrain_packages_unresolved"]
                    or report["coverage"]["airport_parse_failures"]
                )
                else 0
            )
        elif args.command == "pydcs-units":
            report = pydcs_unit_report(
                args.pydcs_root,
                unit_type=args.unit_type,
                category=args.category,
                search=args.search,
                limit=args.limit,
            )
            exit_code = (
                1
                if (
                    (args.unit_type is not None or args.search is not None)
                    and report["coverage"]["matching_units"] == 0
                )
                else 0
            )
        elif args.command == "pydcs-airports":
            exact_airport = args.airport is not None or args.airdrome_id is not None
            parking_limit = _model_facing_parking_limit(
                exact_airport=exact_airport,
                exact_parking=args.parking is not None,
                details=args.details,
                requested_limit=args.limit,
            )
            report = pydcs_airport_report(
                args.pydcs_root,
                args.terrain,
                airport=args.airport,
                airdrome_id=args.airdrome_id,
                parking=args.parking,
                airplane_only=args.airplane_only,
                limit=parking_limit,
            )
            exit_code = (
                1
                if (
                    exact_airport
                    and report["coverage"].get("exact_airport_query_usable") is not True
                )
                or (
                    args.parking is not None
                    and report["coverage"].get("exact_parking_query_usable") is not True
                )
                or report["coverage"]["source_parse_complete"] is not True
                else 0
            )
        elif args.command == "pydcs-aircraft":
            report = pydcs_aircraft_report(
                args.pydcs_root,
                args.unit_type,
                station=args.station,
                clsid=args.clsid,
            )
            compatibility = report["compatibility_query"]
            exit_code = (
                1
                if report["coverage"]["matching_aircraft"] == 0
                or (compatibility is not None and not compatibility["matched"])
                else 0
            )
        elif args.command == "br-terrains":
            report = br_terrain_report(
                args.br_root,
                terrain=args.terrain,
            )
            exit_code = (
                1
                if (
                    (
                        args.terrain is not None
                        and report["coverage"].get("exact_query_usable") is not True
                    )
                    or report["coverage"]["terrain_bounds_unresolved"]
                )
                else 0
            )
        elif args.command == "br-coordinates":
            report = br_coordinate_report(
                args.br_root,
                args.terrain,
                latitude=args.latitude,
                longitude=args.longitude,
                map_x=args.map_x,
                map_y=args.map_y,
            )
            exit_code = 0 if report["validation"]["validated"] is True else 1
        elif args.command == "br-coastline":
            report = br_coastline_report(
                args.br_root,
                args.terrain,
                map_x=args.map_x,
                map_y=args.map_y,
                offset_distance_m=args.offset_distance,
                target_side=args.side,
            )
            exit_code = (
                0 if report["validation"]["usable_for_generation"] is True else 1
            )
        elif args.command == "br-airbases":
            exact_airbase = args.airport is not None or args.airdrome_id is not None
            parking_limit = _model_facing_parking_limit(
                exact_airport=exact_airbase,
                exact_parking=args.parking is not None,
                details=args.details,
                requested_limit=args.limit,
            )
            report = br_airbase_report(
                args.br_root,
                args.terrain,
                airport=args.airport,
                airdrome_id=args.airdrome_id,
                parking=args.parking,
                airplane_only=args.airplane_only,
                helicopter_only=args.helicopter_only,
                limit=parking_limit,
            )
            parking_filtered = (
                args.parking is not None or args.airplane_only or args.helicopter_only
            )
            exit_code = (
                1
                if (
                    exact_airbase
                    and report["coverage"].get("exact_airbase_query_usable") is not True
                )
                or (
                    args.parking is not None
                    and report["coverage"].get("exact_parking_query_usable") is not True
                )
                or (
                    parking_filtered
                    and args.parking is None
                    and report["coverage"]["matching_parking_slots"] == 0
                )
                or report["coverage"]["airbase_parse_failures"] > 0
                else 0
            )
        elif args.command == "br-spawnpoints":
            report = br_spawnpoint_report(
                args.br_root,
                args.terrain,
                spawn_type=args.spawn_type,
                near_x=args.map_x,
                near_y=args.map_y,
                radius_m=args.radius,
                limit=args.limit,
            )
            exit_code = 0 if report["coverage"]["returned_points"] > 0 else 1
        elif args.command == "terrain-catalog":
            report = terrain_catalog_report(
                terrain=args.terrain,
                product=args.product,
                search=args.search,
                limit=args.limit,
            )
            filtered = (
                args.terrain is not None
                or args.product is not None
                or args.search is not None
            )
            exit_code = (
                1
                if filtered and report["coverage"]["matching_theatres"] == 0
                else 0
            )
        elif args.command == "dcs-weather":
            report = weather_registry_report(
                args.dcs_root,
                preset=args.preset,
            )
            selected_unusable = any(
                (
                    item.get("validation", {}).get("fields_complete")
                    is not True
                    or item.get("validation", {}).get("consistent")
                    is not True
                )
                for item in report["presets"]
            )
            exit_code = (
                1
                if report["coverage"]["parse_failures"] > 0
                or (
                    args.preset is not None
                    and report["coverage"]["matching_presets"] == 0
                )
                or selected_unusable
                else 0
            )
        elif args.command == "terrain-point":
            report = physical_point_report(
                args.evidence,
                args.map_x,
                args.map_y,
                terrain=args.terrain,
                dcs_version=args.dcs_version,
                tolerance_m=args.tolerance,
            )
            exit_code = (
                0 if report["validation"]["evidence_usable"] is True else 1
            )
        elif args.command == "placement-check":
            report = placement_report(
                args.evidence,
                x=args.map_x,
                y=args.map_y,
                heading_deg=args.heading,
                length_m=args.length,
                width_m=args.width,
                required_surface=args.surface,
                max_slope_deg=args.max_slope,
                clearance_m=args.clearance,
                avoid_airfields=args.avoid_airfields,
                taxi_buffer_m=args.taxi_buffer,
                terrain=args.terrain,
                dcs_version=args.dcs_version,
            )
            exit_code = (
                0
                if report["validation"]["sampled_placement_valid"] is True
                else 1
            )
        elif args.command == "terrain-corridor":
            report = terrain_corridor_report(
                args.evidence,
                route=_parse_route_points(args.point),
                half_width_m=args.half_width,
                step_m=args.step,
                minimum_clearance_m=args.minimum_clearance,
                limit=args.limit,
                terrain=args.terrain,
                dcs_version=args.dcs_version,
            )
            exit_code = (
                0
                if report["validation"]["sampled_corridor_clear"] is True
                else 1
            )
        elif args.command == "landmark-search":
            report = landmark_report(
                args.evidence,
                query=args.query,
                near_x=args.near_x,
                near_y=args.near_y,
                radius_m=args.radius,
                limit=args.limit,
                terrain=args.terrain,
                dcs_version=args.dcs_version,
            )
            exit_code = (
                0
                if report["validation"]["exact_query_usable"] is True
                else 1
            )
        elif args.command == "airfield-footprint":
            report = airfield_footprint_report(
                args.evidence,
                airfield=args.airfield,
                taxi_buffer_m=args.taxi_buffer,
                terrain=args.terrain,
                dcs_version=args.dcs_version,
            )
            exit_code = (
                0
                if report["validation"]["exact_airfield_usable"] is True
                else 1
            )
        elif args.command == "br-airfield-footprint":
            report = br_airfield_footprint_report(
                args.br_root,
                args.terrain,
                args.airfield,
                limit=args.limit,
            )
            exit_code = (
                0
                if report["validation"]["planning_footprint_usable"] is True
                else 1
            )
        elif args.command == "terrain-probe-script":
            report = generate_terrain_probe_script(
                args.request,
                args.dcs_root,
                args.output,
                force=args.force,
            )
            exit_code = (
                0 if report["validation"]["script_generated"] is True else 1
            )
        elif args.command == "terrain-probe-extract":
            report = extract_terrain_probe(
                args.log,
                args.request,
                args.output,
                force=args.force,
            )
            exit_code = (
                0 if report["validation"]["evidence_valid"] is True else 1
            )
        elif args.command == "terrain-probe-instrument":
            report = instrument_terrain_probe_miz(
                args.mission,
                args.request,
                args.script,
                args.output,
                force=args.force,
            )
            exit_code = 0
        elif args.command == "terrain-coverage":
            report = combined_terrain_report(
                args.pydcs_root,
                args.br_root,
                terrain=args.terrain,
            )
            exit_code = (
                1
                if (
                    (
                        args.terrain is not None
                        and report["coverage"].get("exact_query_usable") is not True
                    )
                    or report["coverage"]["source_parse_incomplete"]
                )
                else 0
            )
        elif args.command == "audit-spec":
            report, valid = audit_build_spec(
                args.spec,
                dcs_root=args.dcs_root,
                installed_terrain=args.installed_terrain,
                pydcs_root=args.pydcs_root,
                pydcs_terrain=args.pydcs_terrain,
                br_root=args.br_root,
                require_acknowledged_upstreams=True,
            )
            exit_code = 0 if valid else 1
        elif args.command == "miz-registry":
            roots = _observed_roots(args.root)
            report = build_observed_registry(
                roots,
                theatre=args.theatre,
                unit_type=args.unit_type,
                category=args.category,
            )
            filtered = (
                args.theatre is not None
                or args.unit_type is not None
                or args.category is not None
            )
            exit_code = (
                1
                if filtered and report["coverage"]["missions_matching_filters"] == 0
                else 0
            )
        elif args.command == "build-miz":
            report, valid = build_miz(
                args.spec,
                args.output,
                force=args.force,
            )
            exit_code = 0 if valid else 1
        else:
            report, valid = verify_miz(args.path, args.spec)
            exit_code = 0 if valid else 1
        if args.command in VIEW_COMMANDS:
            view = output_view(
                args.command,
                report,
                details=getattr(args, "details", False),
                search=getattr(args, "search", None),
                preset=(
                    getattr(args, "preset", None)
                    if args.command in {"dcs-payloads", "dcs-weather"}
                    else None
                ),
                limit=(
                    None
                    if args.command in {"pydcs-airports", "br-airbases"}
                    else getattr(args, "limit", None)
                ),
            )
            report = view.report
            if view.query_matched is False:
                exit_code = 1
        stdout.write(_json(report))
        return exit_code
    except OSError as error:
        details = type(error).__name__
        if error.errno is not None:
            details += f", errno={error.errno}"
        _write_tool_error(
            stderr,
            f"filesystem operation failed ({details})",
        )
        return 2
    except ValueError as error:
        _write_tool_error(stderr, str(error))
        return 2


def _write_tool_error(stderr: TextIO, message: str) -> None:
    """Write one single-line UTF-8 error within the model-facing byte budget."""

    payload = bytearray(_CLI_ERROR_PREFIX.encode("utf-8"))
    full_limit = MAX_CLI_ERROR_BYTES - 1
    truncated = False
    for character in message:
        token = _visible_error_token(character)
        encoded = token.encode("utf-8", errors="backslashreplace")
        if len(payload) + len(encoded) > full_limit:
            truncated = True
            break
        payload.extend(encoded)
    if not truncated:
        stderr.write(payload.decode("utf-8") + "\n")
        return
    suffix_bytes = _CLI_ERROR_SUFFIX.encode("utf-8")
    available = MAX_CLI_ERROR_BYTES - len(suffix_bytes)
    clipped = payload[:available].decode("utf-8", errors="ignore")
    stderr.write(f"{clipped}{_CLI_ERROR_SUFFIX}")


def _visible_error_token(character: str) -> str:
    codepoint = ord(character)
    named = {
        0x09: "\\t",
        0x0A: "\\n",
        0x0D: "\\r",
        0x85: "\\u0085",
        0x2028: "\\u2028",
        0x2029: "\\u2029",
    }
    if codepoint in named:
        return named[codepoint]
    if codepoint < 0x20 or codepoint == 0x7F:
        return f"\\x{codepoint:02x}"
    if 0xD800 <= codepoint <= 0xDFFF:
        return f"\\u{codepoint:04x}"
    return character


def _model_facing_parking_limit(
    *,
    exact_airport: bool,
    exact_parking: bool,
    details: bool,
    requested_limit: int | None,
) -> int | None:
    if exact_airport and not exact_parking and not details and requested_limit is None:
        return DEFAULT_EXACT_PARKING_LIMIT
    return requested_limit


def _parse_route_points(values: Sequence[str]) -> list[dict[str, float]]:
    if len(values) > 1_000:
        raise ValueError("terrain corridor accepts at most 1000 --point values")
    route: list[dict[str, float]] = []
    for index, value in enumerate(values):
        fields = value.split(",")
        if len(fields) != 3:
            raise ValueError(
                f"--point {index + 1} must use X,Y,ALT_MSL syntax"
            )
        try:
            x, y, altitude = (float(field.strip()) for field in fields)
        except ValueError as error:
            raise ValueError(
                f"--point {index + 1} must use numeric X,Y,ALT_MSL syntax"
            ) from error
        route.append({"x": x, "y": y, "altitude_msl": altitude})
    return route


def _parse_payload_pylons(
    values: Sequence[str],
) -> list[dict[str, int | str]]:
    if not values:
        raise ValueError("--pylon must be supplied at least once")
    if len(values) > 128:
        raise ValueError("--pylon may be supplied at most 128 times")
    assignments: list[dict[str, int | str]] = []
    for value in values:
        if len(value) > 4096 or "=" not in value:
            raise ValueError(
                "--pylon must use the bounded STATION=CLSID form"
            )
        station_text, clsid = value.split("=", 1)
        try:
            station = int(station_text, 10)
        except ValueError as error:
            raise ValueError(
                "--pylon station must be a base-10 integer"
            ) from error
        assignments.append({"num": station, "CLSID": clsid})
    return assignments


def _build_parser() -> argparse.ArgumentParser:
    parser = _BoundedArgumentParser(
        prog="dcsmizzer.py",
        description="Model-facing DCS evidence, construction, and validation",
        epilog=(
            "Recommended model workflow:\n"
            "  capabilities -> evidence-readiness -> evidence queries -> "
            "audit-spec -> build-miz -> verify-miz -> inspect\n"
            "  Redirect full audit/build/verify/inspect JSON to files; review "
            "them with report-summary.\n"
            "  Report any unavailable runtime checks.\n\n"
            "Exit codes:\n"
            "  0  Query succeeded, or every available requested check "
            "passed.\n"
            "  1  Input was read, but an exact lookup had no match or a "
            "validation/build check failed.\n"
            "  2  Usage, path, source, or unsafe/invalid input error."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        title="commands",
    )

    def add_command(name: str, description: str) -> argparse.ArgumentParser:
        return commands.add_parser(
            name,
            help=description,
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

    details_help = (
        "Emit complete records for the current filters and any source-side "
        "limit. Detailed output can be very large; redirect stdout to a JSON "
        "file and use report-summary or a narrower exact query. Alias: --full."
    )

    def add_view_options(
        command: argparse.ArgumentParser,
        *,
        search: bool = False,
        preset: bool = False,
        limit: bool = False,
    ) -> None:
        command.add_argument(
            "--details",
            "--full",
            dest="details",
            action="store_true",
            help=details_help,
        )
        if search:
            command.add_argument(
                "--search",
                help="Case-insensitive bounded catalog search.",
            )
        if preset:
            command.add_argument(
                "--preset",
                help="Exact preset ID; returns one full supported-field record.",
            )
        if limit:
            command.add_argument(
                "--limit",
                type=int,
                help=(
                    "Maximum matching records to return (1-100); bounded "
                    "summaries default to 20."
                ),
            )

    dcs_root_help = "Root of a DCS World installation; read only by this command."
    pydcs_root_help = (
        "Root of an acknowledged pydcs checkout; parsed without importing or "
        "executing upstream Python."
    )
    br_root_help = (
        "Root of an acknowledged BriefingRoom checkout; exported data is "
        "parsed without executing upstream code."
    )
    physical_evidence_help = (
        "JSON declared from an initialized DCS terrain API, including terrain "
        "and product-version metadata; read only by this command. The report "
        "keeps the version identity basis explicit, and a planning snapshot "
        "cannot pass physical validation."
    )

    def add_physical_evidence_options(
        command: argparse.ArgumentParser,
    ) -> None:
        command.add_argument(
            "--evidence",
            type=Path,
            required=True,
            help=physical_evidence_help,
        )
        command.add_argument(
            "--terrain",
            required=True,
            help="Require this exact mission.theatre identity in the evidence.",
        )
        command.add_argument(
            "--dcs-version",
            required=True,
            help=(
                "Require this exact declared product version in the evidence; "
                "this does not upgrade its runtime-attestation basis."
            ),
        )

    capabilities = add_command(
        "capabilities",
        "Show the implemented, partial, and unavailable feature gate. "
        "Authority: product-declared capability matrix.",
    )
    add_view_options(capabilities)

    evidence_snapshot = add_command(
        "evidence-snapshot",
        "Collect two stable read-only passes over the current DCS static "
        "evidence and optional locked upstream cache, then write one local "
        "content-addressed bundle. Authority: exact collected bytes and "
        "reported finite source scopes; no DCS process is started.",
    )
    evidence_snapshot.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    evidence_snapshot.add_argument(
        "--bundle-root",
        type=Path,
        required=True,
        help=(
            "Explicit local-only output root. A missing final root is created "
            "only when its safe parent already exists."
        ),
    )
    evidence_snapshot.add_argument(
        "--cache-root",
        type=Path,
        help=(
            "Optional explicit acknowledged-upstream cache to bind into the "
            "same snapshot; it is read only."
        ),
    )
    evidence_snapshot.add_argument(
        "--runtime-manifest",
        type=Path,
        action="append",
        default=[],
        help=(
            "Optional exact prepared runtime manifest to revalidate and bind "
            "without recording absolute paths; repeat for distinct runs."
        ),
    )
    evidence_snapshot.add_argument(
        "--terrain-evidence",
        type=Path,
        action="append",
        default=[],
        help=(
            "Optional initialized physical-terrain evidence file to validate "
            "and bind by full raw hash; repeat for distinct exports."
        ),
    )

    evidence_verify = add_command(
        "evidence-verify",
        "Verify a content-addressed evidence bundle's safe file set, exact "
        "hashes, schemas, authority labels, manifest binding, and directory "
        "identity without trusting report claims.",
    )
    evidence_verify.add_argument(
        "bundle",
        type=Path,
        help="Exact content-addressed evidence bundle directory.",
    )

    evidence_diff = add_command(
        "evidence-diff",
        "Compare two verified evidence bundles or recognized installation "
        "reports and identify version, source-scope, and domain invalidation "
        "without silently treating incomparable coverage as equal.",
    )
    evidence_diff.add_argument(
        "before",
        type=Path,
        help="Earlier evidence bundle directory or recognized JSON report.",
    )
    evidence_diff.add_argument(
        "after",
        type=Path,
        help="Later evidence bundle directory or recognized JSON report.",
    )

    evidence_ready = add_command(
        "evidence-readiness",
        "Verify a bundle and compare its normalized domains with two matching "
        "read-only passes over the current DCS/upstream state. Current but "
        "partial static authority remains partial and cannot pass a required "
        "production decision.",
    )
    evidence_ready.add_argument(
        "bundle",
        type=Path,
        help="Exact content-addressed evidence bundle directory.",
    )
    evidence_ready.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    evidence_ready.add_argument(
        "--cache-root",
        type=Path,
        help="Optional current acknowledged-upstream cache to compare read only.",
    )
    evidence_ready.add_argument(
        "--runtime-manifest",
        type=Path,
        action="append",
        default=[],
        help=(
            "Current exact runtime manifest for a bundled runtime domain; "
            "repeat for distinct runs. DCS is not started."
        ),
    )
    evidence_ready.add_argument(
        "--terrain-evidence",
        type=Path,
        action="append",
        default=[],
        help=(
            "Current raw physical-terrain evidence for a bundled terrain "
            "domain; repeat for distinct exports."
        ),
    )
    evidence_ready.add_argument(
        "--require",
        dest="required_domain",
        action="append",
        choices=required_evidence_domains(),
        default=[],
        help=(
            "Required decision domain; repeat as needed. The default gates "
            "installation, countries, modules, payloads, weather, and airfields."
        ),
    )

    upstream_status = add_command(
        "upstream-status",
        "Read-only status gate for the immutable acknowledged pydcs and "
        "BriefingRoom pins in an explicit cache. Authority: exact origin "
        "URL, commit, root tree, license hash, required paths, and clean "
        "checkout state; lower than version-matched installed DCS data.",
    )
    upstream_status.add_argument(
        "--cache-root",
        type=Path,
        required=True,
        help=(
            "Explicit optional-upstream cache root. No .develope or other "
            "implicit default is used, and local paths are not echoed."
        ),
    )

    upstream_prepare = add_command(
        "upstream-prepare",
        "Safely clone or detach clean recognized checkouts at immutable "
        "acknowledged pins in an explicit cache. Authority: the same exact "
        "identity/profile gate as upstream-status; this is the only upstream "
        "cache command that writes.",
    )
    upstream_prepare.add_argument(
        "--cache-root",
        type=Path,
        required=True,
        help=(
            "Explicit cache root to create or update. No .develope or other "
            "implicit default is used."
        ),
    )
    upstream_prepare.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Do not clone or fetch; only detach a clean recognized checkout "
            "when the acknowledged commit object already exists."
        ),
    )

    report_summary_command = add_command(
        "report-summary",
        "Summarize one saved JSON report with a recognized dcsmizzer schema "
        "identifier under strict size and parse limits. Authority: the named "
        "report bytes; extracted claims are marked reported/unverified, "
        "schema shape/authenticity are not proved, and no validation is rerun.",
    )
    report_summary_command.add_argument(
        "path",
        type=Path,
        help=(
            "JSON report with a recognized dcsmizzer schema identifier, up to 16 MiB."
        ),
    )

    inspect_command = add_command(
        "inspect",
        "Inspect a MIZ or CMP archive and its parse-level structure. "
        "This emits a complete report: redirect stdout to a JSON file and "
        "review it with report-summary. Authority: artifact bytes; no DCS "
        "runtime validation.",
    )
    inspect_command.add_argument(
        "path",
        type=Path,
        help="MIZ or CMP artifact to inspect.",
    )
    inspect_command.add_argument(
        "--skip-crc",
        action="store_true",
        help="Skip ZIP CRC verification; weakens inspection and must be reported.",
    )

    static = add_command(
        "dcs-static",
        "Summarize installed DCS static evidence and coverage gaps. "
        "Authority: safely parsed current-install files.",
    )
    static.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )

    countries = add_command(
        "dcs-countries",
        "Resolve exact country identifiers and numeric IDs. "
        "Authority: current installed db_countries.lua ordering.",
    )
    countries.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    add_view_options(countries, search=True, limit=True)

    payloads = add_command(
        "dcs-payloads",
        "Query default payload presets for one exact unit type. "
        "Authority: current-install preset observations, not a complete "
        "compatibility matrix.",
    )
    payloads.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    payloads.add_argument(
        "--unit-type",
        required=True,
        help="Exact DCS internal unit type.",
    )
    add_view_options(
        payloads,
        search=True,
        preset=True,
        limit=True,
    )

    payload_index = add_command(
        "dcs-payload-index",
        "Discover unit types represented in safe default-payload sources. "
        "Authority: current-install data-only preset files.",
    )
    payload_index.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )

    runtime_prepare = add_command(
        "runtime-prepare",
        "Create one hash-bound disposable DCS profile, supported Hook, and "
        "command preview without launching DCS. Authority: current install, "
        "exact inputs, and generated evidence manifest.",
    )
    runtime_prepare.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help="Root of the DCS installation used by the later authorized run.",
    )
    runtime_prepare.add_argument(
        "--saved-games-root",
        type=Path,
        required=True,
        help="Existing Saved Games root in which to create one DCSMizzer-* profile.",
    )
    runtime_prepare.add_argument(
        "--run-id",
        required=True,
        help="Unique lowercase run ID: [a-z0-9][a-z0-9-]{0,47}.",
    )
    runtime_prepare.add_argument(
        "--mode",
        choices=("registry-probe", "mission-smoke"),
        required=True,
        help="Bounded aggregate registry initialization or exact-MIZ smoke run.",
    )
    runtime_prepare.add_argument(
        "--mission",
        type=Path,
        help="Exact safe MIZ required by mission-smoke and forbidden otherwise.",
    )
    runtime_prepare.add_argument(
        "--coordinate-checks",
        type=Path,
        help=(
            "Optional dcsmizzer.runtime-coordinate-checks/v1 JSON, bound to "
            "the mission theatre and checked through the DCS Export API."
        ),
    )
    runtime_prepare.add_argument(
        "--smoke-seconds",
        type=float,
        default=10.0,
        help="Required stable simulation interval in seconds (1-600; default: 10).",
    )

    runtime_run = add_command(
        "runtime-run",
        "Validate a prepared manifest and preview its exact command by default. "
        "Only --authorize-dcs-launch starts DCS; timeout cleanup is limited to "
        "the exact process this command started.",
    )
    runtime_run.add_argument(
        "manifest",
        type=Path,
        help="Prepared disposable profile's DCSMizzer/manifest.json.",
    )
    runtime_run.add_argument(
        "--authorize-dcs-launch",
        action="store_true",
        help="Explicitly authorize this one external DCS process launch.",
    )
    runtime_run.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Overall process timeout in seconds (5-7200; default: 600).",
    )
    runtime_run.add_argument(
        "--terminate-grace",
        type=float,
        default=15.0,
        help="Grace after exact-process termination before kill (0.1-120).",
    )

    runtime_collect = add_command(
        "runtime-collect",
        "Validate the exact run-ID/version/hash-bound RuntimeResult emitted by "
        "a prepared run. Authority: immutable manifest, execution record, "
        "runtime-attested DCS version, and bounded result bytes.",
    )
    runtime_collect.add_argument(
        "manifest",
        type=Path,
        help="Prepared disposable profile's DCSMizzer/manifest.json.",
    )
    add_view_options(payload_index, search=True, limit=True)

    payload_match = add_command(
        "dcs-payload-match",
        "Strictly match one complete payload against a single observed "
        "current-install default preset. Authority: source-bound complete "
        "preset fingerprints; exit 1 includes ambiguous and custom results.",
    )
    payload_match.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    payload_match.add_argument(
        "--unit-type",
        required=True,
        help="Exact DCS internal unit type.",
    )
    payload_input = payload_match.add_mutually_exclusive_group(required=True)
    payload_input.add_argument(
        "--pylon",
        action="append",
        metavar="STATION=CLSID",
        help=(
            "One authored station/CLSID assignment; repeat for the whole "
            "payload. Use the Python API when per-store settings are present."
        ),
    )
    payload_input.add_argument(
        "--empty",
        action="store_true",
        help="Query a complete payload containing no pylon assignments.",
    )
    payload_match.add_argument(
        "--task",
        action="append",
        type=int,
        help="Optional exact numeric preset task; repeat when needed.",
    )
    payload_match.add_argument(
        "--preset-name",
        help="Optional exact internal preset name used to disambiguate.",
    )
    payload_match.add_argument(
        "--display-name",
        help="Optional exact translated display-name source literal.",
    )
    payload_match.add_argument(
        "--category",
        help="Optional exact preset category literal.",
    )
    add_view_options(payload_match)

    modules = add_command(
        "dcs-modules",
        "Resolve module, plugin, flyable, payload, and literal service records. "
        "Authority: current-install static declarations; entitlement is not "
        "proved.",
    )
    modules.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    modules.add_argument(
        "--module",
        help="Exact module directory key or module name filter.",
    )
    modules.add_argument(
        "--unit-type",
        help="Exact DCS internal unit type to resolve.",
    )
    modules.add_argument(
        "--service-country",
        help="Exact literal service-country string; use with --unit-type.",
    )
    modules.add_argument(
        "--service-year",
        type=int,
        help="Service year to test against literal declarations.",
    )
    add_view_options(modules, search=True, limit=True)

    cloud_presets = add_command(
        "dcs-cloud-presets",
        "List or resolve exact cloud-preset IDs and base ranges. "
        "Authority: current installed GUI cloud preset declarations.",
    )
    cloud_presets.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    cloud_presets.add_argument(
        "--preset",
        help="Exact internal cloud-preset ID; omit to list all parsed presets.",
    )
    add_view_options(cloud_presets, search=True, limit=True)

    weather = add_command(
        "dcs-weather",
        "List or resolve complete Mission Editor weather presets and validate "
        "their precipitation, temperature, fog, and dust relationships. "
        "Authority: current-install data-only presets plus statically "
        "extracted Mission Editor weather constraints.",
    )
    weather.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    add_view_options(
        weather,
        search=True,
        preset=True,
        limit=True,
    )

    airbases = add_command(
        "dcs-airbases",
        "Query terrain airfield IDs and names encoded in radio/beacon sources. "
        "Authority: current-install static files; not a complete airbase "
        "registry.",
    )
    airbases.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    airbases.add_argument(
        "--terrain",
        required=True,
        help="Exact installed terrain directory name.",
    )
    airbases.add_argument(
        "--airdrome-id",
        type=int,
        help="Exact numeric DCS airdrome ID; omit for a terrain summary.",
    )
    add_view_options(airbases, search=True, limit=True)

    coordinates = add_command(
        "dcs-coordinates",
        "Fit or apply a terrain WGS84-to-mission projection. "
        "Authority: independently fitted current-install beacon pairs; no "
        "terrain-height proof.",
    )
    coordinates.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    coordinates.add_argument(
        "--terrain",
        required=True,
        help="Exact installed terrain directory name.",
    )
    coordinates.add_argument(
        "--latitude",
        type=float,
        help="WGS84 latitude; provide together with --longitude.",
    )
    coordinates.add_argument(
        "--longitude",
        type=float,
        help="WGS84 longitude; provide together with --latitude.",
    )
    coordinates.add_argument(
        "--x",
        dest="map_x",
        type=float,
        help="Mission-local x; provide together with --y for inverse conversion.",
    )
    coordinates.add_argument(
        "--y",
        dest="map_y",
        type=float,
        help="Mission-local y; provide together with --x for inverse conversion.",
    )
    coordinates.add_argument(
        "--offset-bearing",
        type=float,
        help=(
            "Initial true bearing in degrees for a WGS84 geodesic offset; "
            "requires latitude, longitude, and --offset-distance."
        ),
    )
    coordinates.add_argument(
        "--offset-distance",
        type=float,
        help=(
            "WGS84 geodesic distance in metres (0-20000000); requires "
            "latitude, longitude, and --offset-bearing."
        ),
    )

    gci = add_command(
        "dcs-gci",
        "Query native MiG-29A GCI declarations and observed task shape. "
        "Authority: current install, official training mission, and installed "
        "manual evidence.",
    )
    gci.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )

    options_template = add_command(
        "dcs-options-template",
        "Emit a sanitized build-spec options table. "
        "Authority: current installed data-only Mission Editor default plus "
        "reported policy overrides.",
    )
    options_template.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    options_template.add_argument(
        "--player-name",
        default="DCSMizzer",
        help="Nonempty playerName value to place in the template.",
    )
    options_template.add_argument(
        "--full-sim",
        action="store_true",
        help="Apply the command's documented full-simulation difficulty overrides.",
    )

    warehouse_template = add_command(
        "dcs-warehouse-template",
        "Emit bounded unlimited airport warehouse records for a build spec. "
        "Authority: verified current-install Mission Editor literals; caller "
        "must verify airdrome IDs.",
    )
    warehouse_template.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    warehouse_template.add_argument(
        "--airdrome-id",
        type=int,
        action="append",
        required=True,
        help="Verified numeric airdrome ID; repeat for multiple airports.",
    )
    warehouse_template.add_argument(
        "--coalition",
        default="NEUTRAL",
        help="Authored initial warehouse coalition (default: NEUTRAL).",
    )

    pydcs_terrains = add_command(
        "pydcs-terrains",
        "Discover terrain IDs, projection metadata, and coordinate conversion. "
        "Authority: provenance-gated generated pydcs declarations parsed without "
        "upstream execution.",
    )
    pydcs_terrains.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    pydcs_terrains.add_argument(
        "--terrain",
        help="Exact pydcs terrain package, class, or MIZ theatre filter.",
    )
    pydcs_terrains.add_argument(
        "--latitude",
        type=float,
        help="WGS84 latitude; provide together with --longitude.",
    )
    pydcs_terrains.add_argument(
        "--longitude",
        type=float,
        help="WGS84 longitude; provide together with --latitude.",
    )
    pydcs_terrains.add_argument(
        "--x",
        dest="map_x",
        type=float,
        help="Mission-local x; provide together with --y for inverse conversion.",
    )
    pydcs_terrains.add_argument(
        "--y",
        dest="map_y",
        type=float,
        help="Mission-local y; provide together with --x for inverse conversion.",
    )
    add_view_options(pydcs_terrains, search=True, limit=True)

    pydcs_units = add_command(
        "pydcs-units",
        "Discover generated unit type declarations across DCS categories. "
        "Authority: provenance-gated pydcs source parsed without execution; not a "
        "current runtime registry.",
    )
    pydcs_units.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    pydcs_units.add_argument(
        "--unit-type",
        help="Exact DCS internal unit type.",
    )
    pydcs_units.add_argument(
        "--category",
        choices=("plane", "helicopter", "vehicle", "ship", "static"),
        help="Restrict discovery to one DCS unit category.",
    )
    pydcs_units.add_argument(
        "--search",
        help="Text search over generated unit records.",
    )
    pydcs_units.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum discovery records to return (default: 20).",
    )
    add_view_options(pydcs_units)

    pydcs_airports = add_command(
        "pydcs-airports",
        "Query runway and parking declarations for one terrain. "
        "Authority: provenance-gated generated pydcs source; lower than "
        "version-matched installed or observed evidence.",
    )
    pydcs_airports.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    pydcs_airports.add_argument(
        "--terrain",
        required=True,
        help="Exact pydcs terrain package, class, or MIZ theatre selector.",
    )
    pydcs_airports.add_argument(
        "--airport",
        help="Exact generated airport name.",
    )
    pydcs_airports.add_argument(
        "--airdrome-id",
        type=int,
        help="Exact numeric DCS airdrome ID.",
    )
    pydcs_airports.add_argument(
        "--parking",
        help="Exact slot_name or decimal crossroad_idx; requires one airport.",
    )
    pydcs_airports.add_argument(
        "--airplane-only",
        action="store_true",
        help="Return only airplane-capable parking records.",
    )
    pydcs_airports.add_argument(
        "--limit",
        type=int,
        help=(
            "Return at most this many parking records; requires one airport. "
            "Without --details or an exact --parking query, an exact airport "
            f"defaults to {DEFAULT_EXACT_PARKING_LIMIT} records."
        ),
    )
    add_view_options(pydcs_airports, search=True)

    pydcs_aircraft = add_command(
        "pydcs-aircraft",
        "Resolve generated aircraft tasks and station/store relationships. "
        "Authority: provenance-gated pydcs declarations; cross-check current "
        "installed or observed evidence.",
    )
    pydcs_aircraft.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    pydcs_aircraft.add_argument(
        "--unit-type",
        required=True,
        help="Exact DCS internal aircraft type.",
    )
    pydcs_aircraft.add_argument(
        "--station",
        type=int,
        help="Exact numeric pylon station for a compatibility query.",
    )
    pydcs_aircraft.add_argument(
        "--clsid",
        help="Exact store CLSID; combine with --station.",
    )
    add_view_options(pydcs_aircraft, search=True, limit=True)

    br_terrains = add_command(
        "br-terrains",
        "Discover DCS theatre IDs and coarse planning geometry. "
        "Authority: provenance-gated BriefingRoom exported database; not current "
        "terrain runtime data.",
    )
    br_terrains.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_terrains.add_argument(
        "--terrain",
        help="Exact BriefingRoom declaration ID or DCS theatre ID.",
    )
    add_view_options(br_terrains, search=True, limit=True)

    br_coordinates = add_command(
        "br-coordinates",
        "Fit or apply one BriefingRoom airbase-centre WGS84-to-mission "
        "projection. Authority: validated commit-bound exported coordinate "
        "pairs; lower than current installed terrain evidence.",
    )
    br_coordinates.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_coordinates.add_argument(
        "--terrain",
        required=True,
        help="Exact BriefingRoom declaration ID or DCS theatre ID.",
    )
    br_coordinates.add_argument(
        "--latitude",
        type=float,
        help="WGS84 latitude; provide together with --longitude.",
    )
    br_coordinates.add_argument(
        "--longitude",
        type=float,
        help="WGS84 longitude; provide together with --latitude.",
    )
    br_coordinates.add_argument(
        "--x",
        dest="map_x",
        type=float,
        help="Mission-local x; provide together with --y for inverse conversion.",
    )
    br_coordinates.add_argument(
        "--y",
        dest="map_y",
        type=float,
        help="Mission-local y; provide together with --x for inverse conversion.",
    )

    br_coastline = add_command(
        "br-coastline",
        "Measure or construct an exact perpendicular offset from the nearest "
        "BriefingRoom water-exclusion land-mass boundary. Authority: commit-"
        "bound planning sea-mask geometry, never a current DCS coastline.",
    )
    br_coastline.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_coastline.add_argument(
        "--terrain",
        required=True,
        help="Exact BriefingRoom declaration ID or DCS theatre ID.",
    )
    br_coastline.add_argument(
        "--x",
        dest="map_x",
        type=float,
        required=True,
        help="Mission-local anchor x used to select the nearest planning boundary.",
    )
    br_coastline.add_argument(
        "--y",
        dest="map_y",
        type=float,
        required=True,
        help="Mission-local anchor y used to select the nearest planning boundary.",
    )
    br_coastline.add_argument(
        "--offset-distance",
        type=float,
        help=(
            "Optional perpendicular distance in metres (0.001-2000000). "
            "Without it, report only the anchor's minimum boundary distance."
        ),
    )
    br_coastline.add_argument(
        "--side",
        choices=("water", "land"),
        default="water",
        help="Required planning-mask side for an offset destination (default: water).",
    )

    br_airbases = add_command(
        "br-airbases",
        "Query exported airbase, runway, radio, and parking records. "
        "Authority: provenance-gated BriefingRoom database; cross-check installed "
        "or observed evidence when available.",
    )
    br_airbases.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_airbases.add_argument(
        "--terrain",
        required=True,
        help="Exact BriefingRoom declaration ID or DCS theatre ID.",
    )
    br_airbases.add_argument(
        "--airport",
        help="Exact exported airbase name.",
    )
    br_airbases.add_argument(
        "--airdrome-id",
        type=int,
        help="Exact numeric DCS airdrome ID.",
    )
    br_airbases.add_argument(
        "--parking",
        help="Exact slot name or decimal parking ID; requires one airbase.",
    )
    br_airbases.add_argument(
        "--airplane-only",
        action="store_true",
        help="Return only airplane-capable parking records.",
    )
    br_airbases.add_argument(
        "--helicopter-only",
        action="store_true",
        help="Return only helicopter-capable parking records.",
    )
    br_airbases.add_argument(
        "--limit",
        type=int,
        help=(
            "Return at most this many parking records; requires one airbase. "
            "Without --details or an exact --parking query, an exact airbase "
            f"defaults to {DEFAULT_EXACT_PARKING_LIMIT} records."
        ),
    )
    add_view_options(br_airbases, search=True)

    br_spawnpoints = add_command(
        "br-spawnpoints",
        "Find bounded candidate ground-placement points near a coordinate. "
        "Authority: provenance-gated BriefingRoom planning export; no terrain, "
        "collision, road, or tactical validity proof.",
    )
    br_spawnpoints.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_spawnpoints.add_argument(
        "--terrain",
        required=True,
        help="Exact BriefingRoom declaration ID or DCS theatre ID.",
    )
    br_spawnpoints.add_argument(
        "--type",
        dest="spawn_type",
        help="Exact exported spawn-point type such as LandSmall.",
    )
    br_spawnpoints.add_argument(
        "--x",
        dest="map_x",
        type=float,
        help="Mission-local search-center x; use with --y and --radius.",
    )
    br_spawnpoints.add_argument(
        "--y",
        dest="map_y",
        type=float,
        help="Mission-local search-center y; use with --x and --radius.",
    )
    br_spawnpoints.add_argument(
        "--radius",
        type=float,
        help="Search radius in metres around --x/--y.",
    )
    br_spawnpoints.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum points to return (default: 20).",
    )

    terrain_catalog = add_command(
        "terrain-catalog",
        "Distinguish dated official terrain product cards, regional "
        "entitlements, and unique mission.theatre identities. Authority: "
        "dated official product-page survey plus locally verified mission "
        "identity literals; no physical terrain claim.",
    )
    terrain_catalog.add_argument(
        "--terrain",
        help="Exact mission.theatre identity or display name.",
    )
    terrain_catalog.add_argument(
        "--product",
        help="Exact official product name or product-page slug.",
    )
    terrain_catalog.add_argument(
        "--search",
        help="Case-insensitive bounded search across theatres and products.",
    )
    terrain_catalog.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum matching theatre records to return (1-100; default: 20).",
    )

    terrain_point = add_command(
        "terrain-point",
        "Resolve one height and surface sample. Authority: an initialized DCS "
        "terrain API export matched to requested theatre/version metadata.",
    )
    add_physical_evidence_options(terrain_point)
    terrain_point.add_argument(
        "--x",
        dest="map_x",
        type=float,
        required=True,
        help="Mission-local x coordinate in metres.",
    )
    terrain_point.add_argument(
        "--y",
        dest="map_y",
        type=float,
        required=True,
        help="Mission-local y coordinate in metres.",
    )
    terrain_point.add_argument(
        "--tolerance",
        type=float,
        help="Maximum sample-match distance in metres.",
    )

    placement_check = add_command(
        "placement-check",
        "Check sampled terrain points, sampled slope/surface, conservative "
        "scenery bounds, and derived "
        "airfield conflicts for one oriented footprint. Authority: complete "
        "relevant coverage in initialized DCS terrain evidence; tactical "
        "suitability is separate.",
    )
    add_physical_evidence_options(placement_check)
    placement_check.add_argument(
        "--x",
        dest="map_x",
        type=float,
        required=True,
        help="Footprint center mission-local x in metres.",
    )
    placement_check.add_argument(
        "--y",
        dest="map_y",
        type=float,
        required=True,
        help="Footprint center mission-local y in metres.",
    )
    placement_check.add_argument(
        "--heading",
        type=float,
        required=True,
        help="Footprint heading in degrees.",
    )
    placement_check.add_argument(
        "--length",
        type=float,
        required=True,
        help="Footprint length in metres.",
    )
    placement_check.add_argument(
        "--width",
        type=float,
        required=True,
        help="Footprint width in metres.",
    )
    placement_check.add_argument(
        "--surface",
        choices=(
            "land",
            "water",
            "shallow_water",
            "sea",
            "lake",
            "river",
            "road",
            "runway",
        ),
        default="land",
        help="Required surface classification (default: land).",
    )
    placement_check.add_argument(
        "--max-slope",
        type=float,
        default=5.0,
        help="Maximum sampled footprint slope in degrees (default: 5).",
    )
    placement_check.add_argument(
        "--clearance",
        type=float,
        default=0.0,
        help="Extra obstacle clearance around the footprint in metres.",
    )
    placement_check.add_argument(
        "--taxi-buffer",
        type=float,
        default=15.0,
        help=(
            "Conservative half-width around exported taxi routes in metres "
            "(default: 15)."
        ),
    )
    placement_check.add_argument(
        "--allow-airfield",
        dest="avoid_airfields",
        action="store_false",
        help=(
            "Explicitly waive the airfield-inventory/overlap gate. This "
            "weakens the placement result and must be reported."
        ),
    )

    terrain_corridor = add_command(
        "terrain-corridor",
        "Sample a route centerline and two lateral edges for terrain clearance. "
        "Authority: an initialized DCS terrain API export; three lateral traces "
        "do not prove continuous terrain or aircraft performance.",
    )
    add_physical_evidence_options(terrain_corridor)
    terrain_corridor.add_argument(
        "--point",
        action="append",
        required=True,
        metavar="X,Y,ALT_MSL",
        help=(
            "Route point as mission-local X,Y,ALT_MSL metres; repeat in route "
            "order at least twice."
        ),
    )
    terrain_corridor.add_argument(
        "--half-width",
        type=float,
        required=True,
        help="Lateral half-width sampled on both sides in metres.",
    )
    terrain_corridor.add_argument(
        "--step",
        type=float,
        required=True,
        help="Maximum along-route sample spacing in metres.",
    )
    terrain_corridor.add_argument(
        "--minimum-clearance",
        type=float,
        required=True,
        help="Required terrain clearance in metres.",
    )
    terrain_corridor.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum worst hazards returned (1-100; default: 20).",
    )

    landmark_search = add_command(
        "landmark-search",
        "Find bounded DCS scenery-object instances by model or display name. "
        "Authority: an initialized DCS terrain API object export, not a "
        "real-world coordinate guess.",
    )
    add_physical_evidence_options(landmark_search)
    landmark_search.add_argument(
        "--query",
        required=True,
        help="Case-insensitive model or scenery-object name fragment.",
    )
    landmark_search.add_argument(
        "--near-x",
        type=float,
        help="Optional mission-local search-center x; requires --near-y.",
    )
    landmark_search.add_argument(
        "--near-y",
        type=float,
        help="Optional mission-local search-center y; requires --near-x.",
    )
    landmark_search.add_argument(
        "--radius",
        type=float,
        help="Optional search radius in metres; requires --near-x/--near-y.",
    )
    landmark_search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum scenery-object instances returned (1-100; default: 20).",
    )

    airfield_footprint = add_command(
        "airfield-footprint",
        "Derive runway, parking, taxi-corridor, and envelope geometry for one "
        "airfield. Authority: initialized DCS exports plus explicitly derived "
        "operational geometry; never an official airport boundary.",
    )
    add_physical_evidence_options(airfield_footprint)
    airfield_footprint.add_argument(
        "--airfield",
        required=True,
        help="Exact exported airfield name or numeric airdrome ID.",
    )
    airfield_footprint.add_argument(
        "--taxi-buffer",
        type=float,
        default=15.0,
        help="Taxi-route half-width used for derived corridors (default: 15).",
    )

    br_airfield_footprint = add_command(
        "br-airfield-footprint",
        "Derive a bounded runway and conservative parking planning envelope "
        "for an upstream airfield. Authority: commit-bound BriefingRoom "
        "geometry; this is not physical terrain validation or an official "
        "airport boundary.",
    )
    br_airfield_footprint.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    br_airfield_footprint.add_argument(
        "--terrain",
        required=True,
        help="Exact BriefingRoom terrain or mission.theatre identity.",
    )
    br_airfield_footprint.add_argument(
        "--airfield",
        required=True,
        help="Exact exported airfield name.",
    )
    br_airfield_footprint.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum parking clearance circles returned (1-100; default: 20).",
    )

    terrain_probe_script = add_command(
        "terrain-probe-script",
        "Generate a bounded mission-scripting Lua probe for explicit terrain "
        "points and scenery searches. Authority: validated request plus "
        "script-generation installation identity; this command does not start "
        "DCS and performs no runtime validation.",
    )
    terrain_probe_script.add_argument(
        "--request",
        type=Path,
        required=True,
        help="dcsmizzer.terrain-probe-request/v1 JSON input.",
    )
    terrain_probe_script.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    terrain_probe_script.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Lua file to load through a DCS mission DO SCRIPT FILE action.",
    )
    terrain_probe_script.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing safe regular output file.",
    )

    terrain_probe_extract = add_command(
        "terrain-probe-extract",
        "Extract and validate the latest complete matching marker run from a "
        "DCS log. Authority: hash-bound log framing and evidence schema; log "
        "producer identity is not cryptographically attested.",
    )
    terrain_probe_extract.add_argument(
        "--log",
        type=Path,
        required=True,
        help="DCS log containing a complete matching marker run.",
    )
    terrain_probe_extract.add_argument(
        "--request",
        type=Path,
        required=True,
        help="The exact request bytes used to generate the probe script.",
    )
    terrain_probe_extract.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Validated dcsmizzer.terrain-physical-evidence/v1 JSON output.",
    )
    terrain_probe_extract.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing safe regular output file.",
    )

    terrain_probe_instrument = add_command(
        "terrain-probe-instrument",
        "Create a verified disposable derivative of one safe MIZ with a "
        "hash-bound generated terrain-probe script. This command never edits "
        "the source mission and never launches DCS.",
    )
    terrain_probe_instrument.add_argument(
        "--mission",
        type=Path,
        required=True,
        help="Safe source MIZ to copy and instrument locally.",
    )
    terrain_probe_instrument.add_argument(
        "--request",
        type=Path,
        required=True,
        help="Exact dcsmizzer.terrain-probe-request/v1 JSON used for the script.",
    )
    terrain_probe_instrument.add_argument(
        "--script",
        type=Path,
        required=True,
        help="Exact Lua output previously produced by terrain-probe-script.",
    )
    terrain_probe_instrument.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New disposable instrumented MIZ output path.",
    )
    terrain_probe_instrument.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing safe regular output file.",
    )

    terrain_coverage = add_command(
        "terrain-coverage",
        "Combine pydcs and BriefingRoom theatre discovery without merging "
        "conflicts. Authority: explicit catalog of two provenance-gated "
        "upstream snapshots, not an installed DCS runtime registry.",
    )
    terrain_coverage.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    terrain_coverage.add_argument(
        "--br-root",
        type=Path,
        required=True,
        help=br_root_help,
    )
    terrain_coverage.add_argument(
        "--terrain",
        help=(
            "Exact DCS theatre ID, display name, or pydcs package; omit for "
            "the combined catalog."
        ),
    )
    add_view_options(terrain_coverage, search=True, limit=True)

    audit = add_command(
        "audit-spec",
        "Audit a complete build spec against installed and upstream evidence. "
        "This emits a complete report: redirect stdout to a JSON file and "
        "review it with report-summary. Authority: finite technical "
        "cross-checks; no tactical or DCS runtime validity claim.",
    )
    audit.add_argument(
        "spec",
        type=Path,
        help="Complete dcsmizzer.miz-build-spec/v1 JSON file.",
    )
    audit.add_argument(
        "--dcs-root",
        type=Path,
        required=True,
        help=dcs_root_help,
    )
    audit.add_argument(
        "--installed-terrain",
        help="Exact installed terrain directory for current-data cross-checks.",
    )
    audit.add_argument(
        "--pydcs-root",
        type=Path,
        required=True,
        help=pydcs_root_help,
    )
    audit.add_argument(
        "--pydcs-terrain",
        help="pydcs terrain override; defaults to mission.theatre.",
    )
    audit.add_argument(
        "--br-root",
        type=Path,
        help=(
            "Optional BriefingRoom checkout for an additional provenance-gated "
            "terrain/airbase cross-check."
        ),
    )

    registry = add_command(
        "miz-registry",
        "Build a privacy-preserving registry of real-MIZ structural patterns. "
        "Authority: observations from parsed artifacts; never a complete "
        "runtime registry.",
    )
    registry.add_argument(
        "--root",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help=(
            "Anonymous LABEL=PATH input root; repeat for multiple roots. "
            "Labels must not contain private paths or mission titles."
        ),
    )
    registry.add_argument(
        "--theatre",
        help=(
            "Exact mission.theatre filter; this caller-supplied value may be "
            "echoed, while unfiltered observed identity strings are omitted."
        ),
    )
    registry.add_argument(
        "--unit-type",
        help=(
            "Exact DCS internal unit type filter; this caller-supplied value "
            "may be echoed."
        ),
    )
    registry.add_argument(
        "--category",
        choices=("plane", "helicopter", "vehicle", "ship", "static"),
        help="Exact DCS unit category; use plane for aircraft research.",
    )
    registry_view = registry.add_mutually_exclusive_group()
    registry_view.add_argument(
        "--details",
        "--full",
        dest="details",
        action="store_true",
        help=details_help,
    )
    registry_view.add_argument(
        "--summary-only",
        action="store_true",
        help=("Compatibility alias for the default bounded anonymous summary."),
    )

    build = add_command(
        "build-miz",
        "Assemble and read back a deterministic low-level MIZ from a spec. "
        "This emits a complete report: redirect stdout to a JSON file and "
        "review it with report-summary. Authority: complete caller input plus "
        "finite static checks; no DCS runtime validation.",
    )
    build.add_argument(
        "spec",
        type=Path,
        help="Complete dcsmizzer.miz-build-spec/v1 JSON file.",
    )
    build.add_argument(
        "output",
        type=Path,
        help="Exact output .miz path.",
    )
    build.add_argument(
        "--force",
        action="store_true",
        help="Replace only the requested existing output after input checks.",
    )

    verify = add_command(
        "verify-miz",
        "Verify a built MIZ byte-for-byte and structurally against its spec. "
        "This emits a complete report: redirect stdout to a JSON file and "
        "review it with report-summary. Authority: artifact/spec comparison "
        "and finite static checks; no DCS runtime validation.",
    )
    verify.add_argument(
        "path",
        type=Path,
        help="Built MIZ artifact to verify.",
    )
    verify.add_argument(
        "--spec",
        type=Path,
        required=True,
        help="Original complete build-spec JSON used for comparison.",
    )
    return parser


def _inspect(path: Path, *, skip_crc: bool) -> tuple[dict[str, Any], int]:
    if not path.is_file():
        raise ValueError("input file does not exist")
    extension = path.suffix.casefold()
    if extension == ".miz":
        archive = inspect_miz(path, verify_crc=not skip_crc)
        content_read_blocked = bool(
            not archive.valid_zip
            or not archive.safe
            or archive.crc_status in {"failed", "not_checked"}
        )
        mission = (
            observe_miz_without_member_reads(path)
            if content_read_blocked
            else analyse_miz(path)
        )
        archive_valid = bool(
            archive.valid_zip
            and archive.safe
            and (archive.crc_status in {"passed", "skipped"})
        )
        parse_valid = mission.parse_valid
        report = {
            "schema": "dcsmizzer.miz-inspection/v1",
            "input": path.name,
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
                "archive_content_read_blocked": content_read_blocked,
                "parse_valid": parse_valid,
                "limited_structure_checked": False,
                "limited_structure_valid": None,
                "runtime_valid": None,
            },
            "limitations": [
                "No Lua code was executed.",
                "The general inspector did not run the builder's limited "
                "mission-structure checks.",
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
            "input": path.name,
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


def _observed_roots(values: list[str]) -> tuple[ObservedRoot, ...]:
    roots: list[ObservedRoot] = []
    for value in values:
        if "=" not in value:
            raise ValueError("each --root must use LABEL=PATH syntax")
        label, path = value.split("=", 1)
        if not label.strip() or not path.strip():
            raise ValueError("each --root must have a nonempty label and path")
        roots.append(ObservedRoot(label.strip(), Path(path)))
    return tuple(roots)


def _registry_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "dcsmizzer.observed-miz-summary/v1",
        "authority": report["authority"],
        "dcs_started": report["dcs_started"],
        "filters": report["filters"],
        "coverage": report["coverage"],
        "theatres": report["theatres"],
        "privacy": report["privacy"],
        "limitations": report["limitations"],
    }


def _json(value: object) -> str:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
