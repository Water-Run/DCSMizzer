from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from Tools.dcsmizzer.path_safety import canonical_existing_directory


class PathSafetyTests(unittest.TestCase):
    def test_regular_directory_is_returned_in_canonical_form(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)

            canonical = canonical_existing_directory(source, "fixture")

            self.assertEqual(canonical, source.resolve(strict=True))

    def test_lexical_parent_components_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            child = source / "child"
            child.mkdir()

            canonical = canonical_existing_directory(
                child / ".." / "child",
                "fixture",
            )

            self.assertEqual(canonical, child.resolve(strict=True))

    def test_linked_path_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            real = source / "real"
            real.mkdir()
            alias = source / "alias"
            try:
                os.symlink(real, alias, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "link|reparse"):
                canonical_existing_directory(alias, "fixture")

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 alias regression")
    def test_windows_short_path_alias_resolves_to_same_directory(self) -> None:
        import ctypes

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(strict=True)
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(
                str(source),
                buffer,
                len(buffer),
            )
            if length == 0 or length >= len(buffer):
                self.skipTest("Windows short paths are unavailable")
            short = Path(buffer.value)
            if os.path.normcase(str(short)) == os.path.normcase(str(source)):
                self.skipTest("fixture has no distinct Windows short alias")

            canonical = canonical_existing_directory(short, "fixture")

            self.assertEqual(canonical, source)
