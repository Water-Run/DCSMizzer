from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.cli import main, parse_root_spec
from dcsmizzer_survey.model import EvidenceRoot, RootKind, SurveyConfig
from dcsmizzer_survey.report import manifest_to_json
from dcsmizzer_survey.survey import survey_evidence

from ._fixtures import write_miz


FIXED_TIME = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)


class EvidenceSurveyTests(unittest.TestCase):
    def test_instances_unique_content_and_cross_root_overlap_are_distinct(self) -> None:
        # Would fail if path instances and content identities share one counter.
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            install = base / "install"
            saved = base / "saved"
            first = install / "private-alpha.miz"
            second = saved / "PRIVATE-BETA.MIZ"
            campaign = install / "campaign.cmp"
            write_miz(first)
            second.parent.mkdir(parents=True)
            shutil.copyfile(first, second)
            campaign.write_text("campaign = {}", encoding="utf-8")
            result = survey_evidence(
                SurveyConfig(
                    roots=(
                        EvidenceRoot(
                            name="install",
                            kind=RootKind.DCS_INSTALL,
                            path=install,
                            version="2.9-test",
                        ),
                        EvidenceRoot(
                            name="saved",
                            kind=RootKind.SAVED_GAMES,
                            path=saved,
                        ),
                    ),
                    verify_crc=True,
                    collected_at=FIXED_TIME,
                )
            )

            report = result.to_dict()

        self.assertEqual(report["schema"], "dcsmizzer.corpus-survey/v1")
        self.assertEqual(report["collected_at"], "2026-07-27T08:30:00Z")
        self.assertEqual(
            report["totals"],
            {
                "file_instances": 3,
                "unique_content": 2,
                "miz_instances": 2,
                "cmp_instances": 1,
            },
        )
        self.assertEqual(report["roots"][0]["file_instances"], 2)
        self.assertEqual(report["roots"][0]["root_unique_content"], 2)
        self.assertEqual(report["roots"][0]["net_new_content"], 2)
        self.assertEqual(report["roots"][1]["file_instances"], 1)
        self.assertEqual(report["roots"][1]["root_unique_content"], 1)
        self.assertEqual(report["roots"][1]["net_new_content"], 0)
        self.assertEqual(
            report["overlaps"],
            [{"left": "install", "right": "saved", "shared_content": 1}],
        )
        self.assertEqual(report["roots"][0]["version"], "2.9-test")
        self.assertEqual(report["roots"][0]["archive"]["valid_zip"], 1)
        self.assertEqual(report["roots"][0]["archive"]["crc_passed"], 1)

    def test_default_json_omits_paths_filenames_and_content_hashes(self) -> None:
        # Would fail if default aggregate output leaks private mission identity.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "secret-root"
            mission = root / "private-mission-name.miz"
            write_miz(mission)
            expected_hash = hashlib.sha256(mission.read_bytes()).hexdigest()
            result = survey_evidence(
                SurveyConfig(
                    roots=(EvidenceRoot("saved", RootKind.SAVED_GAMES, root),),
                    verify_crc=False,
                    collected_at=FIXED_TIME,
                )
            )

            rendered = manifest_to_json(result)

        self.assertNotIn(str(root), rendered)
        self.assertNotIn("private-mission-name", rendered)
        self.assertNotIn(expected_hash, rendered)
        self.assertNotIn('"files"', rendered)

    def test_detail_mode_contains_relative_paths_but_not_absolute_root(self) -> None:
        # Would fail if an explicit local detail report includes absolute roots.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "evidence"
            mission = root / "nested" / "sample.miz"
            write_miz(mission)
            expected_hash = hashlib.sha256(mission.read_bytes()).hexdigest()
            result = survey_evidence(
                SurveyConfig(
                    roots=(EvidenceRoot("sample", RootKind.OTHER, root),),
                    verify_crc=False,
                    collected_at=FIXED_TIME,
                )
            )

            report = result.to_dict(include_file_details=True)
            rendered = manifest_to_json(result, include_file_details=True)

        self.assertEqual(report["files"][0]["relative_path"], "nested/sample.miz")
        self.assertEqual(report["files"][0]["sha256"], expected_hash)
        self.assertNotIn(str(root), rendered)

    def test_missing_root_does_not_suppress_available_root(self) -> None:
        # Would fail if one unavailable source aborts the whole evidence scan.
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            available = base / "available"
            write_miz(available / "sample.miz")
            result = survey_evidence(
                SurveyConfig(
                    roots=(
                        EvidenceRoot("missing", RootKind.OTHER, base / "missing"),
                        EvidenceRoot("available", RootKind.OTHER, available),
                    ),
                    verify_crc=False,
                    collected_at=FIXED_TIME,
                )
            )

            report = result.to_dict()

        self.assertFalse(report["roots"][0]["exists"])
        self.assertEqual(report["roots"][0]["errors"], 1)
        self.assertTrue(report["roots"][1]["exists"])
        self.assertEqual(report["totals"]["file_instances"], 1)


class CliTests(unittest.TestCase):
    def test_root_spec_preserves_windows_drive_colon(self) -> None:
        # Would fail if the drive letter is parsed as the evidence kind.
        root = parse_root_spec(r"install:dcs_install=D:\DCS World")

        self.assertEqual(root.name, "install")
        self.assertEqual(root.kind, RootKind.DCS_INSTALL)
        self.assertEqual(root.path, Path(r"D:\DCS World"))

    def test_cli_prints_private_summary_and_source_version(self) -> None:
        # Would fail if CLI wiring bypasses privacy or version metadata.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "missions"
            write_miz(root / "sample.miz")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "corpus",
                    "--root",
                    f"sample:other={root}",
                    "--source-version",
                    "sample=fixture-v1",
                    "--skip-crc",
                ],
                stdout=stdout,
                stderr=stderr,
                now=lambda: FIXED_TIME,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(report["roots"][0]["version"], "fixture-v1")
        self.assertEqual(report["totals"]["miz_instances"], 1)
        self.assertNotIn("sample.miz", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
