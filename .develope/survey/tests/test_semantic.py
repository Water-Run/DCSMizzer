from __future__ import annotations

import sys
import tempfile
import unittest
import io
import json
from datetime import UTC, datetime
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.model import EvidenceRoot, RootKind
from dcsmizzer_survey.cli import main
from dcsmizzer_survey.semantic import (
    SemanticSurveyConfig,
    semantic_to_json,
    survey_semantics,
)

from ._fixtures import write_miz
from .test_mission import (
    DICTIONARY,
    MAP_RESOURCE,
    MISSION,
    OPTIONS,
    WAREHOUSES,
)


FIXED_TIME = datetime(2026, 7, 27, 9, 45, tzinfo=UTC)


class SemanticSurveyTests(unittest.TestCase):
    def test_semantic_survey_aggregates_miz_and_cmp_without_private_values(self) -> None:
        # Would fail if per-file observations cannot be reproduced as an aggregate.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "private-root"
            members = {
                "mission": MISSION.encode(),
                "options": OPTIONS.encode(),
                "warehouses": WAREHOUSES.encode(),
                "l10n/DEFAULT/dictionary": DICTIONARY.encode(),
                "l10n/DEFAULT/mapResource": MAP_RESOURCE.encode(),
                "l10n/DEFAULT/voice.ogg": b"voice",
                "l10n/DEFAULT/image.PNG": b"image",
            }
            write_miz(root / "private-fixture.miz", members=members)
            (root / "private-campaign.cmp").write_text(
                r'''
                campaign = {
                    version = 1,
                    startStage = 1,
                    stages = {
                        [1] = {
                            missions = {
                                [1] = {
                                    file = "private-fixture.miz",
                                    interval = { 0, 100 },
                                    description = "private campaign description",
                                },
                            },
                        },
                    },
                }
                ''',
                encoding="utf-8",
            )
            result = survey_semantics(
                SemanticSurveyConfig(
                    roots=(
                        EvidenceRoot(
                            "fixture",
                            RootKind.OTHER,
                            root,
                            version="fixture-v1",
                        ),
                    ),
                    collected_at=FIXED_TIME,
                )
            )

            report = result.to_dict()
            rendered = semantic_to_json(result)

        self.assertEqual(report["schema"], "dcsmizzer.semantic-survey/v1")
        self.assertEqual(report["collected_at"], "2026-07-27T09:45:00Z")
        self.assertEqual(
            report["totals"],
            {
                "miz_instances": 1,
                "miz_parse_valid": 1,
                "cmp_instances": 1,
                "cmp_parse_valid": 1,
            },
        )
        root_report = report["roots"][0]
        self.assertEqual(root_report["version"], "fixture-v1")
        self.assertEqual(root_report["miz"]["versions"], {"23": 1})
        self.assertEqual(root_report["miz"]["theatres"], {"FixtureMap": 1})
        self.assertEqual(root_report["miz"]["stats"]["groups"], {"plane": 1, "vehicle": 1})
        self.assertEqual(root_report["miz"]["stats"]["payload_unique_clsids"], 2)
        self.assertEqual(root_report["cmp"]["stages"], 1)
        self.assertEqual(root_report["cmp"]["mission_references"], 1)
        self.assertEqual(root_report["cmp"]["resolved_references"], 1)
        self.assertNotIn(str(root), rendered)
        self.assertNotIn("private-fixture", rendered)
        self.assertNotIn("private campaign description", rendered)
        self.assertNotIn("{ONE}", rendered)

    def test_semantic_survey_counts_parse_failures_without_aborting_root(self) -> None:
        # Would fail if one malformed item prevents remaining evidence from being counted.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_miz(root / "valid.miz")
            (root / "broken.miz").write_bytes(b"not a zip")
            (root / "broken.cmp").write_bytes(b"\x98")

            result = survey_semantics(
                SemanticSurveyConfig(
                    roots=(EvidenceRoot("fixture", RootKind.OTHER, root),),
                    collected_at=FIXED_TIME,
                )
            )

            report = result.to_dict()

        self.assertEqual(report["totals"]["miz_instances"], 2)
        self.assertEqual(report["totals"]["miz_parse_valid"], 1)
        self.assertEqual(report["totals"]["cmp_instances"], 1)
        self.assertEqual(report["totals"]["cmp_parse_valid"], 0)

    def test_cli_semantic_command_uses_same_private_aggregate(self) -> None:
        # Would fail if the repeatable command is not wired to the tested analyzer.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_miz(root / "private-name.miz")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "semantic",
                    "--root",
                    f"fixture:other={root}",
                    "--source-version",
                    "fixture=fixture-v1",
                ],
                stdout=stdout,
                stderr=stderr,
                now=lambda: FIXED_TIME,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(report["schema"], "dcsmizzer.semantic-survey/v1")
        self.assertEqual(report["roots"][0]["version"], "fixture-v1")
        self.assertNotIn("private-name", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
