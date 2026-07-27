from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .dcs import survey_dcs_installation
from .model import EvidenceRoot, RootKind, SurveyConfig
from .reference import (
    build_legacy_reference_manifest,
    validate_legacy_source_paths,
)
from .report import manifest_to_json
from .semantic import SemanticSurveyConfig, semantic_to_json, survey_semantics
from .survey import survey_evidence
from .upstream import UpstreamRepository, inspect_repository


_ROOT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_root_spec(value: str) -> EvidenceRoot:
    try:
        descriptor, raw_path = value.split("=", 1)
        name, raw_kind = descriptor.split(":", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "root must use NAME:KIND=PATH"
        ) from error
    if not _ROOT_NAME.fullmatch(name):
        raise argparse.ArgumentTypeError(
            "root name must contain only letters, numbers, dot, dash, or underscore"
        )
    if not raw_path:
        raise argparse.ArgumentTypeError("root path must not be empty")
    try:
        kind = RootKind(raw_kind)
    except ValueError as error:
        choices = ", ".join(item.value for item in RootKind)
        raise argparse.ArgumentTypeError(
            f"unknown root kind {raw_kind!r}; expected one of: {choices}"
        ) from error
    return EvidenceRoot(name=name, kind=kind, path=Path(raw_path))


def parse_repository_spec(value: str) -> UpstreamRepository:
    try:
        name, raw_path = value.split("=", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "repository must use NAME=PATH"
        ) from error
    if not _ROOT_NAME.fullmatch(name):
        raise argparse.ArgumentTypeError(
            "repository name must contain only letters, numbers, dot, dash, "
            "or underscore"
        )
    if not raw_path:
        raise argparse.ArgumentTypeError("repository path must not be empty")
    return UpstreamRepository(name=name, path=Path(raw_path))


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    if args.command not in {
        "corpus",
        "semantic",
        "upstream",
        "legacy-reference",
        "dcs",
    }:
        parser.print_help(stderr)
        return 2

    try:
        collected_at = now()
        if args.command in {"corpus", "semantic"}:
            roots = _apply_versions(args.root, args.source_version)
        if args.command == "corpus":
            result = survey_evidence(
                SurveyConfig(
                    roots=tuple(roots),
                    verify_crc=not args.skip_crc,
                    collected_at=collected_at,
                )
            )
            rendered = manifest_to_json(
                result,
                include_file_details=args.include_file_details,
            )
        elif args.command == "semantic":
            result = survey_semantics(
                SemanticSurveyConfig(
                    roots=tuple(roots),
                    collected_at=collected_at,
                )
            )
            rendered = semantic_to_json(result)
        elif args.command == "upstream":
            observations = [
                inspect_repository(
                    repository,
                    check_remote=not args.skip_remote,
                )
                for repository in args.repo
            ]
            rendered = _json_report(
                {
                    "schema": "dcsmizzer.upstream-survey/v1",
                    "collected_at": collected_at.isoformat(),
                    "repositories": [
                        observation.to_dict()
                        for observation in observations
                    ],
                }
            )
            has_errors = any(
                not observation.valid_git
                or not observation.clean
                or not observation.license_evidence
                or (
                    observation.remote_checked
                    and observation.in_sync is not True
                )
                for observation in observations
            )
        elif args.command == "legacy-reference":
            manifest = build_legacy_reference_manifest(args.data_root)
            repositories = _legacy_repositories(args.upstream_root)
            source_errors = validate_legacy_source_paths(
                manifest,
                repositories,
            )
            manifest["source_path_errors"] = source_errors
            rendered = _json_report(manifest)
            has_errors = bool(manifest["unmapped"] or source_errors)
        else:
            version_reader = (
                (lambda _path: args.product_version)
                if args.product_version is not None
                else None
            )
            rendered = _json_report(
                survey_dcs_installation(
                    args.dcs_root,
                    args.steam_manifest,
                    collected_at=collected_at,
                    version_reader=version_reader,
                    official_release=_official_release(args),
                )
            )
            has_errors = False
        _write_report(rendered, args.output, stdout)
    except (OSError, ValueError, argparse.ArgumentTypeError) as error:
        stderr.write(f"survey error: {error}\n")
        return 2
    if args.command in {"corpus", "semantic"}:
        has_errors = result.has_errors()
    return 1 if has_errors else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_survey.py",
        description="Development-only DCSMizzer evidence survey",
    )
    subparsers = parser.add_subparsers(dest="command")
    corpus = subparsers.add_parser("corpus")
    _add_source_arguments(corpus)
    corpus.add_argument("--skip-crc", action="store_true")
    corpus.add_argument("--include-file-details", action="store_true")
    semantic = subparsers.add_parser("semantic")
    _add_source_arguments(semantic)
    upstream = subparsers.add_parser("upstream")
    upstream.add_argument(
        "--repo",
        type=parse_repository_spec,
        action="append",
        required=True,
        help="repeatable upstream clone as NAME=PATH",
    )
    upstream.add_argument("--skip-remote", action="store_true")
    upstream.add_argument("--output", type=Path)
    legacy = subparsers.add_parser("legacy-reference")
    legacy.add_argument("--data-root", type=Path, required=True)
    legacy.add_argument("--upstream-root", type=Path, required=True)
    legacy.add_argument("--output", type=Path)
    dcs = subparsers.add_parser("dcs")
    dcs.add_argument("--dcs-root", type=Path, required=True)
    dcs.add_argument("--steam-manifest", type=Path, required=True)
    dcs.add_argument(
        "--product-version",
        help="explicit test/override value; normally read from DCS.exe",
    )
    dcs.add_argument("--official-release-version")
    dcs.add_argument("--official-release-date")
    dcs.add_argument("--official-release-url")
    dcs.add_argument("--output", type=Path)
    return parser


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=parse_root_spec,
        action="append",
        required=True,
        help="repeatable evidence root as NAME:KIND=PATH",
    )
    parser.add_argument(
        "--source-version",
        action="append",
        default=[],
        metavar="NAME=VERSION",
    )
    parser.add_argument("--output", type=Path)


def _apply_versions(
    roots: list[EvidenceRoot],
    values: list[str],
) -> list[EvidenceRoot]:
    versions: dict[str, str] = {}
    for value in values:
        try:
            name, version = value.split("=", 1)
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                "source version must use NAME=VERSION"
            ) from error
        if not name or not version:
            raise argparse.ArgumentTypeError(
                "source version must use non-empty NAME=VERSION"
            )
        if name in versions:
            raise argparse.ArgumentTypeError(
                f"duplicate source version for {name!r}"
            )
        versions[name] = version

    root_names = {root.name for root in roots}
    unknown = sorted(set(versions) - root_names)
    if unknown:
        raise argparse.ArgumentTypeError(
            f"source version has no matching root: {', '.join(unknown)}"
        )
    return [
        replace(root, version=versions.get(root.name))
        for root in roots
    ]


def _legacy_repositories(upstream_root: Path) -> dict[str, Path]:
    return {
        "briefing_room": upstream_root / "briefing-room-for-dcs",
        "gtd": upstream_root / "dcs-global-terrain-database",
        "mission_maker": upstream_root / "dcs-mission-maker",
        "retribution": upstream_root / "dcs-retribution",
        "moose": upstream_root / "MOOSE",
        "pydcs": upstream_root / "pydcs",
    }


def _json_report(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _write_report(
    rendered: str,
    output: Path | None,
    stdout: TextIO,
) -> None:
    if output is None:
        stdout.write(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def _official_release(args: argparse.Namespace) -> dict[str, str] | None:
    values = (
        args.official_release_version,
        args.official_release_date,
        args.official_release_url,
    )
    if not any(values):
        return None
    if not all(values):
        raise argparse.ArgumentTypeError(
            "official release version, date, and URL must be supplied together"
        )
    return {
        "version": args.official_release_version,
        "release_date": args.official_release_date,
        "url": args.official_release_url,
    }
