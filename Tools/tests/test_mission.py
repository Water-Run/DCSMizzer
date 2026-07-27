from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.mission import (  # noqa: E402
    analyse_miz,
    observe_miz_without_member_reads,
)


def _encrypted_core_miz(path: Path) -> bytes:
    members = {
        "mission": b"mission = { version = 23, theatre = 'FixtureMap' }",
        "options": b"options = {}",
        "warehouses": b"warehouses = { airports = {}, warehouses = {} }",
        "l10n/DEFAULT/dictionary": b"dictionary = {}",
        "l10n/DEFAULT/mapResource": b"mapResource = {}",
    }
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
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
    return bytes(payload)


class MissionAnalysisTests(unittest.TestCase):
    def test_encrypted_members_are_structured_parse_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "encrypted.miz"
            payload = _encrypted_core_miz(path)
            report = analyse_miz(io.BytesIO(payload))

        self.assertFalse(report.parse_valid)
        self.assertEqual(len(report.members), 5)
        for member in report.members:
            self.assertTrue(member.present)
            self.assertFalse(member.parsed)
            self.assertEqual(member.error_code, "encrypted_member")

    def test_blocked_observation_never_opens_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blocked.miz"
            _encrypted_core_miz(path)
            with mock.patch.object(
                zipfile.ZipFile,
                "open",
                side_effect=AssertionError("member open must not run"),
            ) as archive_open:
                report = observe_miz_without_member_reads(path)

        self.assertFalse(report.parse_valid)
        self.assertTrue(
            all(
                member.error_code == "encrypted_member"
                for member in report.members
            )
        )
        archive_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
