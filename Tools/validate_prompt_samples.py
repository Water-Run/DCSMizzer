"""Validate structure and audience boundaries in bilingual Prompt examples."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


SOURCE_MARKER = "[source,text]"
SOURCE_BLOCK_RE = re.compile(
    r"(?ms)^\[source,text\]\n----\n(.*?)\n----$"
)
HEADING_RE = re.compile(r"(?m)^(=+)\s+\S.*$")
INTERNAL_TERMS = (
    re.compile(r"\bCLSID(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bDocs/Tools\b", re.IGNORECASE),
    re.compile(r"\bRead Docs\b", re.IGNORECASE),
    re.compile(r"\bproject data\b", re.IGNORECASE),
    re.compile(r"项目数据"),
    re.compile(r"\bmanifest\b", re.IGNORECASE),
    re.compile(r"\bOOB(?:s)?\b"),
    re.compile(r"\bdependency graph\b", re.IGNORECASE),
    re.compile(r"依赖图"),
    re.compile(r"\bvalidation-reports\b", re.IGNORECASE),
    re.compile(r"\boutput/campaigns\b", re.IGNORECASE),
    re.compile(r"\bImage Gen\b", re.IGNORECASE),
    re.compile(r"\blong-running model\b", re.IGNORECASE),
    re.compile(r"长程模型"),
    re.compile(r"\bFable\b"),
    re.compile(r"\bGPT-5\.6-Ultra\b", re.IGNORECASE),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _control_character_issues(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    for offset, character in enumerate(text):
        if ord(character) >= 32 or character in "\t\n\r":
            continue
        line_number = text.count("\n", 0, offset) + 1
        previous_newline = text.rfind("\n", 0, offset)
        column = offset - previous_newline
        issues.append(
            f"{path}: line {line_number}, column {column}: "
            f"disallowed control character U+{ord(character):04X}"
        )
    return issues


def _source_blocks(path: Path, text: str) -> tuple[list[str], list[str]]:
    blocks = SOURCE_BLOCK_RE.findall(text)
    marker_count = sum(
        line == SOURCE_MARKER for line in text.splitlines()
    )
    issues: list[str] = []
    if marker_count != len(blocks):
        issues.append(
            f"{path}: source block markers={marker_count}, "
            f"well-formed source blocks={len(blocks)}"
        )
    return blocks, issues


def _internal_term_issues(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    for pattern in INTERNAL_TERMS:
        match = pattern.search(text)
        if match is None:
            continue
        line_number = text.count("\n", 0, match.start()) + 1
        issues.append(
            f"{path}: line {line_number}: internal engineering term "
            f"{match.group(0)!r}"
        )
    return issues


def validate_catalog_pair(zh_path: Path, en_path: Path) -> list[str]:
    zh_path = Path(zh_path)
    en_path = Path(en_path)
    issues: list[str] = []

    try:
        zh_text = _read_text(zh_path)
    except (OSError, UnicodeError) as error:
        return [f"{zh_path}: cannot read UTF-8 catalog: {error}"]

    try:
        en_text = _read_text(en_path)
    except (OSError, UnicodeError) as error:
        return [f"{en_path}: cannot read UTF-8 catalog: {error}"]

    for path, text in ((zh_path, zh_text), (en_path, en_text)):
        issues.extend(_control_character_issues(path, text))
        _, block_issues = _source_blocks(path, text)
        issues.extend(block_issues)
        issues.extend(_internal_term_issues(path, text))

    zh_blocks, _ = _source_blocks(zh_path, zh_text)
    en_blocks, _ = _source_blocks(en_path, en_text)
    if len(zh_blocks) != len(en_blocks):
        issues.append(
            "catalog source block counts differ: "
            f"Chinese={len(zh_blocks)}, English={len(en_blocks)}"
        )

    zh_heading_levels = [
        len(match.group(1)) for match in HEADING_RE.finditer(zh_text)
    ]
    en_heading_levels = [
        len(match.group(1)) for match in HEADING_RE.finditer(en_text)
    ]
    if zh_heading_levels != en_heading_levels:
        issues.append(
            "catalog heading-level sequences differ: "
            f"Chinese={zh_heading_levels}, English={en_heading_levels}"
        )

    return issues


def _catalog_counts(path: Path) -> tuple[int, int]:
    text = _read_text(path)
    return len(SOURCE_BLOCK_RE.findall(text)), len(HEADING_RE.findall(text))


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Validate the bilingual user-facing Prompt catalogs."
    )
    parser.add_argument(
        "--zh",
        type=Path,
        default=root / "PROMPT-SAMPLE-zh.adoc",
        help="Chinese Prompt catalog",
    )
    parser.add_argument(
        "--en",
        type=Path,
        default=root / "PROMPT-SAMPLE.adoc",
        help="English Prompt catalog",
    )
    arguments = parser.parse_args(argv)

    issues = validate_catalog_pair(arguments.zh, arguments.en)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1

    zh_blocks, zh_headings = _catalog_counts(arguments.zh)
    en_blocks, en_headings = _catalog_counts(arguments.en)
    print(
        "Prompt samples OK: "
        f"Chinese={zh_blocks} blocks/{zh_headings} headings, "
        f"English={en_blocks} blocks/{en_headings} headings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
