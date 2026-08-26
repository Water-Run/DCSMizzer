from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import (  # noqa: E402
    _EVIDENCE_BINDING_DOMAINS,
    _build_parser,
    _preflight_evidence_binding,
    main,
)


class CliEvidenceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dcs = self.root / "DCSWorld"
        self.dcs.mkdir()
        self.cache = self.root / "upstream"
        (self.cache / "pydcs").mkdir(parents=True)
        (self.cache / "briefing-room-for-dcs").mkdir()
        self.bundle = self.root / "bundle"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_policy_exhaustively_partitions_every_command(self) -> None:
        denied = {
            "evidence-snapshot",
            "evidence-verify",
            "evidence-diff",
            "evidence-readiness",
            "upstream-prepare",
            "upstream-promotion-audit",
            "report-summary",
            "runtime-prepare",
            "runtime-run",
            "runtime-collect",
            "inspect",
            "dcs-cloud-presets",
            "dcs-gci",
            "dcs-options-template",
            "dcs-warehouse-template",
            "terrain-catalog",
            "terrain-probe-script",
            "terrain-probe-extract",
            "terrain-probe-instrument",
            "audit-spec",
            "miz-registry",
            "build-miz",
            "verify-miz",
        }
        parser = _build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        commands = set(subparsers.choices)

        self.assertEqual(len(_EVIDENCE_BINDING_DOMAINS), 27)
        self.assertEqual(commands, set(_EVIDENCE_BINDING_DOMAINS) | denied)
        self.assertFalse(set(_EVIDENCE_BINDING_DOMAINS) & denied)
        for name, command_parser in subparsers.choices.items():
            option_strings = {
                option
                for action in command_parser._actions
                for option in action.option_strings
            }
            self.assertEqual(
                "--evidence-bundle" in option_strings,
                name in _EVIDENCE_BINDING_DOMAINS,
                name,
            )
        self.assertEqual(
            _EVIDENCE_BINDING_DOMAINS["dcs-payloads"],
            ("installation", "payloads"),
        )
        self.assertEqual(
            _EVIDENCE_BINDING_DOMAINS["dcs-payload-match"],
            ("installation", "payloads"),
        )

    def test_writer_and_launcher_bindings_are_rejected_before_dispatch(self) -> None:
        cases = (
            (
                [
                    "evidence-snapshot",
                    "--dcs-root",
                    str(self.dcs),
                    "--bundle-root",
                    str(self.root / "out"),
                    "--evidence-bundle",
                    str(self.bundle),
                ],
                "dcsmizzer.cli.create_evidence_snapshot",
            ),
            (
                [
                    "runtime-run",
                    "--manifest",
                    str(self.root / "run.json"),
                    "--authorize-dcs-launch",
                    "--evidence-bundle",
                    str(self.bundle),
                ],
                "dcsmizzer.cli.run_runtime",
            ),
            (
                [
                    "terrain-probe-script",
                    "--request",
                    str(self.root / "request.json"),
                    "--dcs-root",
                    str(self.dcs),
                    "--output",
                    str(self.root / "probe.lua"),
                    "--evidence-bundle",
                    str(self.bundle),
                ],
                "dcsmizzer.cli.generate_terrain_probe_script",
            ),
            (
                [
                    "build-miz",
                    "--spec",
                    str(self.root / "spec.json"),
                    "--output",
                    str(self.root / "mission.miz"),
                    "--evidence-bundle",
                    str(self.bundle),
                ],
                "dcsmizzer.cli.build_miz",
            ),
            (
                [
                    "upstream-prepare",
                    "--cache-root",
                    str(self.cache),
                    "--evidence-bundle",
                    str(self.bundle),
                ],
                "dcsmizzer.cli.prepare_upstreams",
            ),
        )

        for argv, target in cases:
            with self.subTest(command=argv[0]), patch(target) as handler:
                stdout = io.StringIO()
                stderr = io.StringIO()

                exit_code = main(argv, stdout=stdout, stderr=stderr)

                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn("unrecognized arguments", stderr.getvalue())
                handler.assert_not_called()

    def test_supplemental_binding_option_without_bundle_is_predispatch(self) -> None:
        with patch("dcsmizzer.cli.capabilities_report") as handler:
            stderr = io.StringIO()
            exit_code = main(
                [
                    "capabilities",
                    "--evidence-current-dcs-root",
                    str(self.dcs),
                ],
                stdout=io.StringIO(),
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("require --evidence-bundle", stderr.getvalue())
        handler.assert_not_called()

    def test_mandatory_domains_are_union_not_caller_replacement(self) -> None:
        args = _build_parser().parse_args(
            [
                "dcs-static",
                "--dcs-root",
                str(self.dcs),
                "--evidence-bundle",
                str(self.bundle),
                "--evidence-current-dcs-root",
                str(self.dcs / "."),
                "--evidence-required-domain",
                "weather",
            ]
        )
        with patch(
            "dcsmizzer.cli.current_report_evidence_reference",
            return_value=self._reference(
                ("countries", "installation", "modules", "payloads", "weather")
            ),
        ) as reference:
            plan = _preflight_evidence_binding(args)

        self.assertEqual(
            plan["required_domains"],
            ("countries", "installation", "modules", "payloads", "weather"),
        )
        self.assertEqual(
            reference.call_args.kwargs["mandatory_domains"],
            ("countries", "installation", "modules", "payloads"),
        )
        self.assertEqual(
            reference.call_args.kwargs["required_domains"],
            plan["required_domains"],
        )

    def test_mismatched_dcs_root_and_nonfinite_query_fail_before_collection(
        self,
    ) -> None:
        sibling = self.root / "DCSWorld-copy"
        sibling.mkdir()
        base = [
            "dcs-coordinates",
            "--dcs-root",
            str(sibling),
            "--terrain",
            "FixtureMap",
            "--latitude",
            "1",
            "--longitude",
            "2",
            "--evidence-bundle",
            str(self.bundle),
            "--evidence-current-dcs-root",
            str(self.dcs),
        ]
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "does not match"),
        ):
            _preflight_evidence_binding(_build_parser().parse_args(base))
        reference.assert_not_called()

        base[base.index(str(sibling))] = str(self.dcs)
        base[base.index("1")] = "nan"
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "non-canonical"),
        ):
            _preflight_evidence_binding(_build_parser().parse_args(base))
        reference.assert_not_called()

    def test_upstream_query_roots_must_be_exact_cache_children(self) -> None:
        sibling = self.root / "pydcs-copy"
        sibling.mkdir()
        argv = [
            "pydcs-units",
            "--pydcs-root",
            str(sibling),
            "--evidence-bundle",
            str(self.bundle),
            "--evidence-current-dcs-root",
            str(self.dcs),
            "--evidence-current-cache-root",
            str(self.cache),
        ]
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "does not match"),
        ):
            _preflight_evidence_binding(_build_parser().parse_args(argv))
        reference.assert_not_called()

        argv[argv.index(str(sibling))] = str(self.cache / "pydcs")
        with patch(
            "dcsmizzer.cli.current_report_evidence_reference",
            return_value=self._reference(("upstream",)),
        ):
            plan = _preflight_evidence_binding(_build_parser().parse_args(argv))
        self.assertEqual(plan["mandatory_domains"], ("upstream",))

    def test_service_life_module_binding_fails_before_collection(self) -> None:
        args = _build_parser().parse_args(
            [
                "dcs-modules",
                "--dcs-root",
                str(self.dcs),
                "--unit-type",
                "Fixture",
                "--evidence-bundle",
                str(self.bundle),
                "--evidence-current-dcs-root",
                str(self.dcs),
            ]
        )
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "service-life"),
        ):
            _preflight_evidence_binding(args)
        reference.assert_not_called()

    def test_physical_binding_uses_file_identity_and_rejects_duplicates(
        self,
    ) -> None:
        evidence = self.root / "terrain.json"
        evidence.write_text('{"fixture":true}', encoding="utf-8")
        copied = self.root / "terrain-copy.json"
        copied.write_bytes(evidence.read_bytes())
        argv = self._physical_argv(evidence, copied)
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "must match"),
        ):
            _preflight_evidence_binding(_build_parser().parse_args(argv))
        reference.assert_not_called()

        argv = self._physical_argv(evidence, evidence)
        with patch(
            "dcsmizzer.cli.current_report_evidence_reference",
            return_value=self._reference(("installation", "terrain")),
        ):
            plan = _preflight_evidence_binding(_build_parser().parse_args(argv))
        self.assertRegex(plan["query_sha256"], r"^[0-9a-f]{64}$")

        argv.extend(["--evidence-current-terrain-evidence", str(evidence)])
        with (
            patch("dcsmizzer.cli.current_report_evidence_reference") as reference,
            self.assertRaisesRegex(ValueError, "duplicate file identity"),
        ):
            _preflight_evidence_binding(_build_parser().parse_args(argv))
        reference.assert_not_called()

    def test_pre_and_post_fence_rejects_drift_after_read_only_dispatch(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch(
                "dcsmizzer.cli.current_report_evidence_reference",
                side_effect=[{"sequence": 1}, {"sequence": 2}],
            ),
            patch(
                "dcsmizzer.cli.capabilities_report",
                return_value={"schema": "dcsmizzer.capabilities/v3"},
            ) as handler,
        ):
            exit_code = main(
                self._capabilities_argv(),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("changed while the report was produced", stderr.getvalue())
        handler.assert_called_once_with()

    def test_success_failed_query_and_unready_binding_are_distinct(self) -> None:
        with (
            patch(
                "dcsmizzer.cli.current_report_evidence_reference",
                side_effect=self._reference_for_call,
            ),
            patch(
                "dcsmizzer.cli.capabilities_report",
                return_value={"schema": "dcsmizzer.capabilities/v3"},
            ),
        ):
            stdout = io.StringIO()
            success_code = main(self._capabilities_argv(), stdout=stdout)
        successful = json.loads(stdout.getvalue())
        self.assertEqual(success_code, 0)
        self.assertEqual(successful["evidence_ref"]["status"], "bundle-current")
        self.assertTrue(
            successful["evidence_ref"]["validation"][
                "usable_for_current_production_decision"
            ]
        )
        self.assertIsNone(
            successful["evidence_ref"]["report_authority"]["runtime_valid"]
        )
        self.assertRegex(
            successful["evidence_ref"]["report_binding"][
                "intrinsic_report_sha256"
            ],
            r"^[0-9a-f]{64}$",
        )

        argv = [
            "dcs-payload-match",
            "--dcs-root",
            str(self.dcs),
            "--unit-type",
            "Fixture",
            "--empty",
            "--details",
            "--evidence-bundle",
            str(self.bundle),
            "--evidence-current-dcs-root",
            str(self.dcs),
        ]
        with (
            patch(
                "dcsmizzer.cli.current_report_evidence_reference",
                side_effect=self._reference_for_call,
            ),
            patch(
                "dcsmizzer.cli.payload_match_report",
                return_value={
                    "schema": "dcsmizzer.dcs-payload-match/v1",
                    "verified_exact_observed_preset": False,
                    "validation": {"runtime_valid": False},
                },
            ),
        ):
            stdout = io.StringIO()
            failed_code = main(argv, stdout=stdout)
        failed_output = json.loads(stdout.getvalue())
        self.assertEqual(failed_code, 1)
        self.assertEqual(failed_output["evidence_ref"]["status"], "unbound")
        self.assertFalse(
            failed_output["evidence_ref"]["validation"]["report_gate_passed"]
        )
        self.assertFalse(
            failed_output["evidence_ref"]["report_authority"]["runtime_valid"]
        )

        with (
            patch(
                "dcsmizzer.cli.current_report_evidence_reference",
                side_effect=lambda *args, **kwargs: self._reference_for_call(
                    *args,
                    ready=False,
                    **kwargs,
                ),
            ),
            patch(
                "dcsmizzer.cli.capabilities_report",
                return_value={"schema": "dcsmizzer.capabilities/v3"},
            ),
        ):
            stdout = io.StringIO()
            unready_code = main(self._capabilities_argv(), stdout=stdout)
        unready_output = json.loads(stdout.getvalue())
        self.assertEqual(unready_code, 1)
        self.assertEqual(unready_output["evidence_ref"]["status"], "unbound")
        self.assertTrue(
            unready_output["evidence_ref"]["validation"]["report_gate_passed"]
        )
        self.assertFalse(
            unready_output["evidence_ref"]["validation"][
                "usable_for_current_production_decision"
            ]
        )

    def _capabilities_argv(self) -> list[str]:
        return [
            "capabilities",
            "--details",
            "--evidence-bundle",
            str(self.bundle),
            "--evidence-current-dcs-root",
            str(self.dcs),
        ]

    def _physical_argv(self, query: Path, current: Path) -> list[str]:
        return [
            "terrain-point",
            "--evidence",
            str(query),
            "--x",
            "1",
            "--y",
            "2",
            "--terrain",
            "FixtureMap",
            "--dcs-version",
            "2.9.0",
            "--evidence-bundle",
            str(self.bundle),
            "--evidence-current-dcs-root",
            str(self.dcs),
            "--evidence-current-terrain-evidence",
            str(current),
        ]

    @staticmethod
    def _reference(
        domains: tuple[str, ...],
        *,
        ready: bool = True,
        command: str = "capabilities",
        query_sha256: str = "f" * 64,
        mandatory_domains: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        commit = "c" * 40
        required = {name: ready for name in sorted(domains)}
        return {
            "schema": "dcsmizzer.report-evidence-ref/v1",
            "status": "bundle-current" if ready else "unbound",
            "bundle": {"id": "a" * 64, "manifest_sha256": "b" * 64},
            "authority_tier": (
                "current_verified_binding_context" if ready else "report_intrinsic_only"
            ),
            "producer": {
                role: {
                    "name": "DCSMizzer",
                    "version": "0.9.0",
                    "git_commit": commit,
                    "git_dirty": False,
                }
                for role in ("bundle", "current")
            },
            "required_domains": required,
            "domain_artifact_bindings": {name: "d" * 64 for name in sorted(domains)},
            "current_readiness": {
                "schema": "dcsmizzer.evidence-readiness/v1",
                "canonical_sha256": "e" * 64,
                "live_collection_passes": 2,
                "stable_across_passes": True,
                "live_collection_failures": 0,
            },
            "report_binding": {
                "command": command,
                "query_sha256": query_sha256,
                "mandatory_domains": list(mandatory_domains or (sorted(domains)[0],)),
                "source_roots_matched": True,
            },
            "limitations": ["Fixture limitation."],
            "validation": {
                "bundle_reference_present": True,
                "bundle_integrity_verified": True,
                "bundle_stable_during_binding": True,
                "current_state_revalidated": True,
                "required_domains_ready": ready,
                "reproducible_current_producer": True,
                "current_producer_matches_bundle": True,
                "evidence_ready_for_binding": ready,
            },
        }

    def _reference_for_call(
        self,
        *_args: object,
        ready: bool = True,
        **kwargs: object,
    ) -> dict[str, object]:
        return self._reference(
            tuple(kwargs["required_domains"]),
            ready=ready,
            command=str(kwargs["report_command"]),
            query_sha256=str(kwargs["query_sha256"]),
            mandatory_domains=tuple(kwargs["mandatory_domains"]),
        )


if __name__ == "__main__":
    unittest.main()
