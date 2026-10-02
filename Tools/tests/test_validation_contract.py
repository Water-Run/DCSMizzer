from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.validation_contract import (  # noqa: E402
    CONTRACT_SCHEMA,
    TIERS_SCHEMA,
    runtime_tier_report,
    validation_contract_report,
)


def mission_manifest() -> dict[str, object]:
    return {
        "mode": "mission-smoke",
        "inputs": {
            "mission": {
                "archive_valid": True,
                "parse_valid": True,
            }
        },
    }


class ValidationContractTests(unittest.TestCase):
    def test_contract_publishes_all_levels_without_claiming_runtime(self) -> None:
        report = validation_contract_report()

        self.assertEqual(report["schema"], CONTRACT_SCHEMA)
        self.assertEqual(report["ordering"], ["V0", "V1", "V2", "V3", "V4", "V5"])
        self.assertEqual(
            [item["level"] for item in report["levels"]],
            report["ordering"],
        )
        self.assertTrue(report["rules"]["lower_never_implies_higher"])
        self.assertFalse(report["runtime_work_performed"])

    def test_successful_mission_collection_partitions_static_and_runtime(self) -> None:
        report = runtime_tier_report(
            mission_manifest(),
            {"status": "ok"},
            [],
            inputs_unchanged=True,
        )
        statuses = {item["level"]: item["status"] for item in report["levels"]}

        self.assertEqual(report["schema"], TIERS_SCHEMA)
        self.assertEqual(report["highest_achieved"], "V3")
        self.assertEqual(statuses["V0"], "not_evaluated")
        self.assertEqual(statuses["V1"], "passed")
        self.assertEqual(statuses["V2"], "passed")
        self.assertEqual(statuses["V3"], "passed")
        self.assertEqual(statuses["V4"], "not_evaluated")
        self.assertEqual(statuses["V5"], "not_evaluated")

    def test_smoke_only_failure_preserves_V2_but_not_V3(self) -> None:
        report = runtime_tier_report(
            mission_manifest(),
            {"status": "ok"},
            ["smoke_interval_incomplete"],
            inputs_unchanged=True,
        )
        statuses = {item["level"]: item["status"] for item in report["levels"]}

        self.assertEqual(report["highest_achieved"], "V2")
        self.assertEqual(statuses["V2"], "passed")
        self.assertEqual(statuses["V3"], "failed")

    def test_load_or_binding_failure_blocks_V2_and_V3(self) -> None:
        report = runtime_tier_report(
            mission_manifest(),
            {"status": "error"},
            ["runtime_result_status_not_ok"],
            inputs_unchanged=True,
        )
        levels = {item["level"]: item for item in report["levels"]}

        self.assertEqual(report["highest_achieved"], "V1")
        self.assertEqual(levels["V2"]["status"], "failed")
        self.assertEqual(levels["V3"]["status"], "failed")
        self.assertIn(
            "runtime_result_status_not_ok",
            levels["V2"]["failure_reasons"],
        )

    def test_changed_inputs_block_every_current_exact_mission_tier(self) -> None:
        report = runtime_tier_report(
            mission_manifest(),
            {"status": "ok"},
            [],
            inputs_unchanged=False,
        )
        statuses = {item["level"]: item["status"] for item in report["levels"]}

        self.assertIsNone(report["highest_achieved"])
        self.assertEqual(statuses["V1"], "failed")
        self.assertEqual(statuses["V2"], "failed")
        self.assertEqual(statuses["V3"], "failed")

    def test_registry_probe_never_claims_mission_tiers(self) -> None:
        report = runtime_tier_report(
            {"mode": "registry-probe"},
            {"status": "ok"},
            [],
            inputs_unchanged=True,
        )

        self.assertIsNone(report["highest_achieved"])
        self.assertEqual(report["scope"], "registry-probe")
        self.assertEqual(
            {item["status"] for item in report["levels"]},
            {"not_applicable"},
        )

    def test_cli_contract_is_unbound_and_runtime_free(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["validation-contract"],
            stdout=stdout,
            stderr=stderr,
        )
        report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(report["schema"], CONTRACT_SCHEMA)
        self.assertFalse(report["runtime_work_performed"])
        self.assertEqual(report["evidence_ref"]["status"], "unbound")


if __name__ == "__main__":
    unittest.main()
