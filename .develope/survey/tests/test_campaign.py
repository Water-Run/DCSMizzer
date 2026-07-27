from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.campaign import analyse_cmp


CAMPAIGN = r'''
campaign = {
    version = 1,
    startStage = 1,
    ["name_СS"] = "confusable key is preserved",
    stages = {
        [1] = {
            missions = {
                [1] = {
                    file = "one.miz",
                    fullpath = "ignored absolute hint",
                    interval = { 0, 50 },
                    description = "private text not returned",
                },
                [2] = {
                    file = "two.miz",
                    interval = { 51, 100 },
                    description = "private text not returned",
                },
            },
        },
        [2] = {
            missions = {
                [1] = {
                    file = "missing.miz",
                    interval = { 0, 60 },
                },
                [2] = {
                    file = "one.miz",
                    interval = { 50, 100 },
                },
            },
        },
    },
}
'''


class CampaignAnalysisTests(unittest.TestCase):
    def test_campaign_counts_refs_resolves_relative_paths_and_checks_intervals(self) -> None:
        # Would fail if fullpath is trusted or score overlaps are not detected.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "campaign.cmp"
            path.write_text(CAMPAIGN, encoding="utf-8")
            (root / "one.miz").write_bytes(b"one")
            (root / "two.miz").write_bytes(b"two")

            observation = analyse_cmp(path)

        self.assertTrue(observation.parse_valid)
        self.assertEqual(observation.encoding, "utf-8")
        self.assertEqual(observation.version, 1)
        self.assertEqual(observation.start_stage, 1)
        self.assertTrue(observation.start_stage_exists)
        self.assertEqual(observation.stage_count, 2)
        self.assertEqual(observation.mission_references, 4)
        self.assertEqual(observation.resolved_references, 3)
        self.assertEqual(observation.missing_references, 1)
        self.assertEqual(observation.interval_overlaps, 1)
        self.assertEqual(observation.interval_gaps, 0)
        self.assertIn("name_СS", observation.top_level_keys)
        self.assertNotIn("private text", repr(observation))
        self.assertNotIn("ignored absolute hint", repr(observation))

    def test_campaign_reports_missing_start_stage_and_score_gap(self) -> None:
        # Would fail if structural validity is inferred only from Lua parse success.
        text = r'''
        campaign = {
            version = 1,
            startStage = 9,
            stages = {
                [1] = {
                    missions = {
                        [1] = { file = "one.miz", interval = { 10, 90 } },
                    },
                },
            },
        }
        '''
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "campaign.cmp"
            path.write_text(text, encoding="utf-8")
            (root / "one.miz").write_bytes(b"one")

            observation = analyse_cmp(path)

        self.assertTrue(observation.parse_valid)
        self.assertFalse(observation.start_stage_exists)
        self.assertEqual(observation.interval_gaps, 2)


if __name__ == "__main__":
    unittest.main()
