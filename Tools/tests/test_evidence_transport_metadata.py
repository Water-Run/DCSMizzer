from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.evidence import compare_evidence  # noqa: E402


class EvidenceTransportMetadataTests(unittest.TestCase):
    def test_top_level_evidence_ref_does_not_change_standalone_semantics(
        self,
    ) -> None:
        reports = {
            "weather": {
                "schema": "dcsmizzer.dcs-weather-presets/v1",
                "authority": "current_install_static_weather_sources",
                "dcs_started": False,
                "parse_failures": 0,
                "coverage": {"usable_presets": 1},
                "presets": [{"id": "Fixture"}],
            },
            "capabilities": {
                "schema": "dcsmizzer.capabilities/v3",
                "authority": "declared_and_tested_project_capabilities",
                "dcs_started": False,
                "capabilities": [{"id": "fixture", "status": "tested"}],
                "validation": {"complete": True},
            },
        }
        evidence_ref = {
            "schema": "dcsmizzer.report-evidence-ref/v1",
            "status": "unbound",
            "bundle": None,
            "validation": {
                "usable_for_current_production_decision": False,
            },
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, original in reports.items():
                with self.subTest(domain=name):
                    plain = root / f"{name}-plain.json"
                    adorned = root / f"{name}-adorned.json"
                    plain.write_text(json.dumps(original), encoding="utf-8")
                    adorned.write_text(
                        json.dumps({**original, "evidence_ref": evidence_ref}),
                        encoding="utf-8",
                    )

                    comparison = compare_evidence(plain, adorned)

                    self.assertNotEqual(
                        comparison["before"]["sha256"],
                        comparison["after"]["sha256"],
                    )
                    self.assertEqual(
                        comparison["invalidation"]["invalidated_domains"],
                        [],
                    )
                    self.assertEqual(len(comparison["domains"]), 1)
                    domain = comparison["domains"][0]
                    self.assertEqual(domain["domain"], name)
                    self.assertEqual(domain["status"], "unchanged")
                    self.assertEqual(
                        domain["before_fingerprint"],
                        domain["after_fingerprint"],
                    )

    def test_nested_evidence_ref_remains_semantic_report_content(self) -> None:
        original = {
            "schema": "dcsmizzer.dcs-weather-presets/v1",
            "authority": "current_install_static_weather_sources",
            "dcs_started": False,
            "parse_failures": 0,
            "coverage": {"usable_presets": 1},
            "presets": [{"id": "Fixture"}],
        }
        changed = {
            **original,
            "presets": [
                {
                    "id": "Fixture",
                    "evidence_ref": {"status": "domain-content"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(json.dumps(original), encoding="utf-8")
            after.write_text(json.dumps(changed), encoding="utf-8")

            comparison = compare_evidence(before, after)

        self.assertEqual(comparison["domains"][0]["status"], "changed")
        self.assertEqual(
            comparison["invalidation"]["invalidated_domains"],
            ["weather"],
        )


if __name__ == "__main__":
    unittest.main()
