from __future__ import annotations

import copy
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

from dcsmizzer import cli as cli_module  # noqa: E402, RUF100
from dcsmizzer import construction_replay as replay_module  # noqa: E402, RUF100


class ConstructionReplayCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_snapshot_command_defaults_to_v2_and_hides_absolute_inputs(self) -> None:
        self.assertIs(
            cli_module.create_construction_snapshot,
            replay_module.create_construction_snapshot,
        )
        report = {
            "schema": replay_module.CONSTRUCTION_SNAPSHOT_SCHEMA,
            "dcs_started": False,
            "validation": {
                "bundle_valid": True,
                "audit_passed": True,
                "audit_decision_replay_available": True,
                "audit_decision_replay_performed": True,
                "audit_decision_replay_passed": True,
                "build_passed": True,
                "verify_passed": True,
                "artifact_rebuild_performed": True,
                "artifact_rebuilt_exact": True,
                "verification_replay_performed": True,
                "verification_replayed": True,
                "replay_producer_matches": True,
                "fully_reproducible": True,
                "evidence_ready_for_static_release": True,
                "static_release_ready": True,
                "runtime_valid": None,
            },
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(
            cli_module,
            "create_construction_snapshot",
            return_value=copy.deepcopy(report),
        ) as snapshot:
            exit_code = cli_module.main(
                [
                    "construction-snapshot",
                    str(self.root / "private-spec.json"),
                    "--construction-root",
                    str(self.root / "private-construction-root"),
                    "--evidence-bundle",
                    str(self.root / "private-evidence-bundle"),
                    "--dcs-root",
                    str(self.root / "private-DCS"),
                    "--cache-root",
                    str(self.root / "private-cache"),
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        snapshot.assert_called_once()
        rendered = stdout.getvalue()
        self.assertEqual(
            json.loads(rendered)["schema"],
            replay_module.CONSTRUCTION_SNAPSHOT_SCHEMA,
        )
        self.assertNotIn(str(self.root), rendered)

    def test_verify_dispatch_accepts_a_static_valid_v1_report(self) -> None:
        self.assertIs(
            cli_module.verify_construction_bundle,
            replay_module.verify_construction_bundle,
        )
        report = {
            "schema": "dcsmizzer.construction-verification/v1",
            "validation": {
                "bundle_valid": True,
                "pipeline_continuity_valid": True,
                "replay_producer_matches": False,
                "artifact_rebuilt_exact": False,
                "verification_replayed": False,
            },
        }
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "verify_construction_bundle",
            return_value=report,
        ) as verify:
            exit_code = cli_module.main(
                ["construction-verify", str(self.root / "historical-v1")],
                stdout=stdout,
                stderr=io.StringIO(),
            )

        self.assertEqual(exit_code, 0)
        verify.assert_called_once_with(self.root / "historical-v1")
        self.assertNotIn(str(self.root), stdout.getvalue())

    def test_exact_v2_replay_failure_exits_one_for_each_stage(self) -> None:
        base = self._v2_verification()
        failures = {
            "audit_decision_replay_passed": "audit_decision_replay_performed",
            "artifact_rebuilt_exact": "artifact_rebuild_performed",
            "verification_replayed": "verification_replay_performed",
        }
        for result_field, performed_field in failures.items():
            with self.subTest(result_field=result_field):
                report = copy.deepcopy(base)
                report["validation"][result_field] = False
                report["validation"][performed_field] = True
                report["validation"]["fully_reproducible"] = False
                stdout = io.StringIO()
                stderr = io.StringIO()
                with patch.object(
                    cli_module,
                    "verify_construction_bundle",
                    return_value=report,
                ):
                    exit_code = cli_module.main(
                        ["construction-verify", str(self.root / "exact-v2")],
                        stdout=stdout,
                        stderr=stderr,
                    )

                self.assertEqual(exit_code, 1)
                self.assertEqual(stderr.getvalue(), "")
                self.assertFalse(
                    json.loads(stdout.getvalue())["validation"][result_field]
                )

    def test_historical_v2_wrong_producer_is_a_successful_static_verify(self) -> None:
        report = self._v2_verification()
        report["validation"].update(
            replay_producer_matches=False,
            audit_decision_replay_performed=False,
            audit_decision_replay_passed=None,
            artifact_rebuild_performed=False,
            artifact_rebuilt_exact=None,
            verification_replay_performed=False,
            verification_replayed=None,
            fully_reproducible=False,
        )
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "verify_construction_bundle",
            return_value=report,
        ):
            exit_code = cli_module.main(
                ["construction-verify", str(self.root / "historical-v2")],
                stdout=stdout,
                stderr=io.StringIO(),
            )

        self.assertEqual(exit_code, 0)
        rendered = json.loads(stdout.getvalue())
        self.assertIsNone(rendered["validation"]["audit_decision_replay_passed"])
        self.assertFalse(rendered["validation"]["static_release_ready"])
        self.assertNotIn(str(self.root), stdout.getvalue())

    def test_construction_help_describes_v2_and_historical_dispatch(self) -> None:
        parser = cli_module._build_parser()
        subparsers = next(
            action for action in parser._actions if action.dest == "command"
        )
        snapshot_help = subparsers.choices["construction-snapshot"].description
        verify_help = subparsers.choices["construction-verify"].description

        self.assertIn("construction-bundle/v2", snapshot_help)
        self.assertIn("offline audit", snapshot_help)
        self.assertIn("construction-bundle/v1 or /v2", verify_help)
        self.assertIn("historical verification", verify_help)

    @staticmethod
    def _v2_verification() -> dict[str, object]:
        return {
            "schema": replay_module.CONSTRUCTION_VERIFICATION_SCHEMA,
            "validation": {
                "bundle_valid": True,
                "pipeline_continuity_valid": True,
                "replay_producer_matches": True,
                "audit_decision_replay_available": True,
                "audit_decision_replay_performed": True,
                "audit_decision_replay_passed": True,
                "artifact_rebuild_performed": True,
                "artifact_rebuilt_exact": True,
                "verification_replay_performed": True,
                "verification_replayed": True,
                "fully_reproducible": True,
                "static_release_ready": False,
                "runtime_valid": None,
            },
        }


if __name__ == "__main__":
    unittest.main()
