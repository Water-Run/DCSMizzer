from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Tools.validate_document_links import (
    _default_documents,
    _git_tracked_paths,
    validate_document_links,
)


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

    def test_default_documents_include_nested_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "Docs" / "reference" / "details.md"
            reference.parent.mkdir(parents=True)
            reference.write_text("# Details\n", encoding="utf-8")

            documents = _default_documents(root)

        self.assertIn(reference, documents)

    def test_accepts_existing_markdown_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guide = root / "guide.md"
            guide.write_text(
                "# Complete-profile runtime shell\n\n"
                "## Repeated heading\n\n"
                "## Repeated heading\n",
                encoding="utf-8",
            )
            readme = root / "README.md"
            readme.write_text(
                "[Shell](guide.md#complete-profile-runtime-shell)\n"
                "[Second](guide.md#repeated-heading-1)\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertEqual([], issues)

    def test_accepts_same_document_and_html_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(
                "# Start here\n\n"
                '<a id="explicit-target"></a>\n\n'
                "[Heading](#start-here)\n"
                "[Explicit](#explicit-target)\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertEqual([], issues)

    def test_rejects_missing_markdown_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guide = root / "guide.md"
            guide.write_text("# Existing\n", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                "[Missing](guide.md#not-present)\n",
                encoding="utf-8",
            )

            issues = validate_document_links([readme])

        self.assertTrue(
            any("missing local fragment" in issue for issue in issues),
            issues,
        )

    def test_release_mode_rejects_existing_untracked_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            target = root / "local-only.md"
            readme.write_text("[Local](local-only.md)\n", encoding="utf-8")
            target.write_text("# Local only\n", encoding="utf-8")

            issues = validate_document_links(
                [readme],
                tracked_paths=frozenset({readme.resolve()}),
            )

        self.assertTrue(
            any("target is not tracked" in issue for issue in issues),
            issues,
        )

    def test_release_mode_accepts_tracked_document_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            target = root / "guide.md"
            readme.write_text("[Guide](guide.md#guide)\n", encoding="utf-8")
            target.write_text("# Guide\n", encoding="utf-8")

            issues = validate_document_links(
                [readme],
                tracked_paths=frozenset(
                    {readme.resolve(), target.resolve()}
                ),
            )

        self.assertEqual([], issues)

    def test_repository_index_enumeration_contains_validator(self) -> None:
        root = Path(__file__).resolve().parents[2]

        tracked = _git_tracked_paths(root)

        self.assertIn(
            (root / "Tools" / "validate_document_links.py").resolve(),
            tracked,
        )


if __name__ == "__main__":
    unittest.main()
