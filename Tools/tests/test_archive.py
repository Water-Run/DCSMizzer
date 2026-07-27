from __future__ import annotations

import io
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.archive import ArchivePolicy, inspect_miz  # noqa: E402


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _mark_entries_encrypted(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    for signature, flag_offset in (
        (b"PK\x03\x04", 6),
        (b"PK\x01\x02", 8),
    ):
        start = 0
        while True:
            index = payload.find(signature, start)
            if index < 0:
                break
            flags_at = index + flag_offset
            flags = int.from_bytes(
                payload[flags_at : flags_at + 2],
                "little",
            )
            payload[flags_at : flags_at + 2] = (flags | 1).to_bytes(
                2,
                "little",
            )
            start = index + len(signature)
    path.write_bytes(payload)


class MizArchiveTests(unittest.TestCase):
    def test_default_policy_is_bounded_above_observed_official_corpus(
        self,
    ) -> None:
        policy = ArchivePolicy()

        self.assertEqual(policy.max_members, 4_096)
        self.assertEqual(policy.max_member_uncompressed, 128 * 1024 * 1024)
        self.assertEqual(policy.max_total_uncompressed, 512 * 1024 * 1024)
        self.assertEqual(policy.max_compression_ratio, 250.0)

    def test_policy_errors_skip_crc_instead_of_calling_testzip(self) -> None:
        cases = (
            (
                "member_count_limit",
                {"one": b"a", "two": b"b"},
                ArchivePolicy(max_members=1),
            ),
            (
                "member_size_limit",
                {"large": b"ab"},
                ArchivePolicy(max_member_uncompressed=1),
            ),
            (
                "total_size_limit",
                {"one": b"ab", "two": b"cd"},
                ArchivePolicy(max_total_uncompressed=3),
            ),
            (
                "compression_ratio_limit",
                {"compressed": b"a" * 4_096},
                ArchivePolicy(max_compression_ratio=1.0),
            ),
        )
        for code, members, policy in cases:
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "fixture.miz"
                    _write_zip(path, members)
                    with mock.patch.object(
                        zipfile.ZipFile,
                        "testzip",
                        side_effect=AssertionError("testzip must not run"),
                    ) as testzip:
                        report = inspect_miz(path, policy=policy)

                self.assertEqual(report.crc_status, "not_checked")
                self.assertFalse(report.safe)
                self.assertIn(
                    code,
                    [item.code for item in report.diagnostics],
                )
                testzip.assert_not_called()

    def test_encrypted_member_skips_crc_and_supports_open_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "encrypted.miz"
            _write_zip(path, {"mission": b"mission = {}"})
            _mark_entries_encrypted(path)
            stream = io.BytesIO(path.read_bytes())
            with mock.patch.object(
                zipfile.ZipFile,
                "testzip",
                side_effect=AssertionError("testzip must not run"),
            ) as testzip:
                report = inspect_miz(stream)

        self.assertTrue(report.valid_zip)
        self.assertFalse(report.safe)
        self.assertEqual(report.encrypted_entries, 1)
        self.assertEqual(report.crc_status, "not_checked")
        self.assertIn(
            "encrypted_member",
            [item.code for item in report.diagnostics],
        )
        testzip.assert_not_called()

    def test_unsafe_and_duplicate_members_skip_crc(self) -> None:
        cases = (
            ("unsafe_member_path", (("../escape", b"x"),)),
            (
                "duplicate_member",
                (("mission", b"one"), ("mission", b"two")),
            ),
        )
        for code, members in cases:
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "blocked.miz"
                    with zipfile.ZipFile(
                        path,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                    ) as archive:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            for name, payload in members:
                                archive.writestr(name, payload)
                    with mock.patch.object(
                        zipfile.ZipFile,
                        "testzip",
                        side_effect=AssertionError("testzip must not run"),
                    ) as testzip:
                        report = inspect_miz(path)

                self.assertFalse(report.safe)
                self.assertEqual(report.crc_status, "not_checked")
                self.assertIn(
                    code,
                    [item.code for item in report.diagnostics],
                )
                testzip.assert_not_called()


if __name__ == "__main__":
    unittest.main()
