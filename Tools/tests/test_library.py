from __future__ import annotations

import io
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import dcsmizzer  # noqa: E402


class PublicLibraryTests(unittest.TestCase):
    def test_import_does_not_load_cli_or_change_process_configuration(self) -> None:
        script = """
import sys
sys.path.insert(0, sys.argv[1])
before = (
    sys.path[:], sys.stdout.encoding, sys.stderr.encoding, sys.dont_write_bytecode
)
import dcsmizzer
assert before == (
    sys.path, sys.stdout.encoding, sys.stderr.encoding, sys.dont_write_bytecode
)
assert 'dcsmizzer.cli' not in sys.modules
assert 'dcsmizzer.builder' not in sys.modules
assert callable(dcsmizzer.inspect_miz)
assert 'dcsmizzer.cli' not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(TOOLS_ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_api_inspects_and_parses_an_in_memory_miz(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("mission", 'mission = {version=23, theatre="FixtureMap"}')
            archive.writestr("options", "options = {}")
            archive.writestr("warehouses", "warehouses = {}")
            archive.writestr("l10n/DEFAULT/dictionary", "dictionary = {}")
            archive.writestr("l10n/DEFAULT/mapResource", "mapResource = {}")

        inspection = dcsmizzer.inspect_miz(stream, policy=dcsmizzer.ArchivePolicy())
        observation = dcsmizzer.analyse_miz(stream, limits=dcsmizzer.LuaLimits())

        self.assertTrue(inspection.safe)
        self.assertEqual(inspection.crc_status, "passed")
        self.assertTrue(observation.parse_valid)
        self.assertEqual(observation.theatre, "FixtureMap")

    def test_public_inspection_reports_invalid_input(self) -> None:
        inspection = dcsmizzer.inspect_miz(io.BytesIO(b"not a ZIP archive"))
        self.assertFalse(inspection.valid_zip)
        self.assertFalse(inspection.safe)

    def test_capability_reports_are_independent(self) -> None:
        report = dcsmizzer.capabilities_report()
        report["inspect_miz"]["status"] = "changed by caller"
        self.assertEqual(
            dcsmizzer.capabilities_report()["inspect_miz"]["status"], "implemented"
        )

    def test_public_exports_are_discoverable_and_unknown_attributes_fail(self) -> None:
        self.assertTrue(set(dcsmizzer.__all__).issubset(dir(dcsmizzer)))
        with self.assertRaises(AttributeError):
            _ = dcsmizzer.missing_api
        for name in dcsmizzer.__all__:
            self.assertIsNotNone(getattr(dcsmizzer, name))


if __name__ == "__main__":
    unittest.main()
