from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Tools.validate_prompt_samples import validate_catalog_pair


ZH_HEADER = """\
= 示例

== 开始

=== 简短

[source,text]
----
{prompt}
----
"""

EN_HEADER = """\
= Examples

== Start

=== Short

[source,text]
----
{prompt}
----
"""


class PromptSampleValidationTests(unittest.TestCase):
    def validate_texts(self, zh_text: str, en_text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zh_path = root / "PROMPT-SAMPLE-zh.adoc"
            en_path = root / "PROMPT-SAMPLE.adoc"
            zh_path.write_text(zh_text, encoding="utf-8")
            en_path.write_text(en_text, encoding="utf-8")
            return validate_catalog_pair(zh_path, en_path)

    def test_accepts_parallel_user_facing_catalogs(self) -> None:
        issues = self.validate_texts(
            ZH_HEADER.format(prompt="生成一个高加索拦截任务。"),
            EN_HEADER.format(prompt="Generate a Caucasus interception mission."),
        )

        self.assertEqual([], issues)

    def test_rejects_control_characters(self) -> None:
        issues = self.validate_texts(
            ZH_HEADER.format(prompt="生成完整简报。\x08\x07\x0b"),
            EN_HEADER.format(prompt="Generate a complete briefing."),
        )

        for codepoint in ("U+0008", "U+0007", "U+000B"):
            with self.subTest(codepoint=codepoint):
                self.assertTrue(
                    any(codepoint in issue for issue in issues),
                    issues,
                )

    def test_rejects_mismatched_bilingual_structure(self) -> None:
        issues = self.validate_texts(
            ZH_HEADER.format(prompt="生成一个任务。"),
            EN_HEADER.format(prompt="Generate a mission.").replace(
                "=== Short", "==== Short"
            ),
        )

        self.assertTrue(
            any("heading-level sequence" in issue for issue in issues),
            issues,
        )

    def test_rejects_internal_engineering_language(self) -> None:
        issues = self.validate_texts(
            ZH_HEADER.format(prompt="生成一个任务。"),
            EN_HEADER.format(
                prompt="Read Docs/Tools and never invent a CLSID."
            ),
        )

        self.assertTrue(
            any("internal engineering term" in issue for issue in issues),
            issues,
        )

    def test_rejects_unbalanced_source_blocks(self) -> None:
        issues = self.validate_texts(
            ZH_HEADER.format(prompt="生成一个任务。"),
            EN_HEADER.format(prompt="Generate a mission.").replace(
                "\n----\n", "\n", 1
            ),
        )

        self.assertTrue(
            any("source block" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
