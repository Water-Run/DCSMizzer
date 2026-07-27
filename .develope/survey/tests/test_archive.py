from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.archive import ArchivePolicy, inspect_miz

from ._fixtures import CORE_MEMBERS, corrupt_stored_member, write_miz


class ArchiveInspectionTests(unittest.TestCase):
    def test_valid_miz_reports_core_members_and_passed_crc(self) -> None:
        # Would fail if a core member is skipped or an unchecked CRC is called passed.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "valid.miz"
            write_miz(path)

            report = inspect_miz(path, verify_crc=True)

        self.assertTrue(report.valid_zip)
        self.assertTrue(report.safe)
        self.assertEqual(report.member_count, 5)
        self.assertEqual(report.crc_status, "passed")
        self.assertEqual(report.present_core_members, tuple(CORE_MEMBERS))
        self.assertEqual(report.diagnostics, ())

    def test_duplicate_member_is_reported_without_rejecting_archive(self) -> None:
        # Would fail if names are reduced to a set before duplicate detection.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate.miz"
            write_miz(path, duplicate_member="mission")

            report = inspect_miz(path, verify_crc=False)

        self.assertTrue(report.valid_zip)
        self.assertTrue(report.safe)
        self.assertEqual(report.duplicate_member_extras, 1)
        self.assertEqual(report.crc_status, "skipped")
        self.assertEqual(
            [item.code for item in report.diagnostics],
            ["duplicate_member"],
        )

    def test_unsafe_member_paths_cover_posix_and_windows_forms(self) -> None:
        # Would fail if validation only handles forward-slash `..`.
        members = {
            **CORE_MEMBERS,
            "../escape.lua": b"x",
            "/absolute.lua": b"x",
            r"C:\escape.lua": b"x",
            r"folder\..\escape.lua": b"x",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsafe.miz"
            write_miz(path, members=members)

            report = inspect_miz(path, verify_crc=False)

        self.assertTrue(report.valid_zip)
        self.assertFalse(report.safe)
        self.assertEqual(report.unsafe_path_entries, 4)
        self.assertEqual(
            [item.code for item in report.diagnostics],
            ["unsafe_member_path"] * 4,
        )

    def test_policy_limits_member_size_and_compression_ratio(self) -> None:
        # Would fail if untrusted ZIP sizes are collected but not enforced.
        members = {**CORE_MEMBERS, "large.txt": b"A" * 4_096}
        policy = ArchivePolicy(
            max_members=100,
            max_member_uncompressed=1_024,
            max_total_uncompressed=20_000,
            max_compression_ratio=10.0,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "limited.miz"
            write_miz(path, members=members)

            report = inspect_miz(path, policy=policy, verify_crc=False)

        codes = [item.code for item in report.diagnostics]
        self.assertFalse(report.safe)
        self.assertIn("member_size_limit", codes)
        self.assertIn("compression_ratio_limit", codes)

    def test_bad_crc_is_distinct_from_bad_zip_structure(self) -> None:
        # Would fail if CRC corruption is swallowed as a generic bad ZIP.
        marker = b"UNIQUE_CRC_PAYLOAD_27072026"
        members = {**CORE_MEMBERS, "payload.bin": marker}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "crc-bad.miz"
            write_miz(path, members=members, compression=zipfile.ZIP_STORED)
            corrupt_stored_member(path, marker)

            report = inspect_miz(path, verify_crc=True)

        self.assertTrue(report.valid_zip)
        self.assertFalse(report.safe)
        self.assertEqual(report.crc_status, "failed")
        self.assertEqual([item.code for item in report.diagnostics], ["bad_crc"])

    def test_malformed_zip_returns_structured_diagnostic(self) -> None:
        # Would fail if malformed archives abort the entire corpus scan.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.miz"
            path.write_bytes(b"not a zip")

            report = inspect_miz(path, verify_crc=True)

        self.assertFalse(report.valid_zip)
        self.assertFalse(report.safe)
        self.assertEqual(report.crc_status, "not_checked")
        self.assertEqual([item.code for item in report.diagnostics], ["bad_zip"])


if __name__ == "__main__":
    unittest.main()
