from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Tools.validate_document_links import validate_document_links


class DocumentLinkValidationTests(unittest.TestCase):
    def test_rejects_markdown_link_inside_raw_html_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "README-zh.md"
            target.write_text("# 中文\n", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                '<p align="center">\n'
                "[中文 README](./README-zh.md)\n"
                "</p>\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertTrue(
            any("raw HTML block" in issue for issue in issues),
            issues,
        )

    def test_rejects_missing_local_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            readme.write_text(
                "Read the [guide](./Docs/guide.md).\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertTrue(
            any("missing local target" in issue for issue in issues),
            issues,
        )

    def test_rejects_missing_html_anchor_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            readme.write_text(
                '<p align="center">'
                '<a href="./README-zh.md">中文 README</a>'
                "</p>\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertTrue(
            any("README-zh.md" in issue for issue in issues),
            issues,
        )

    def test_rejects_missing_asciidoc_link_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "PROMPT-SAMPLE.adoc"
            catalog.write_text(
                "link:README.md[Back to README]\n",
                encoding="utf-8",
            )

            issues = validate_document_links([catalog])

        self.assertTrue(
            any("README.md" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
