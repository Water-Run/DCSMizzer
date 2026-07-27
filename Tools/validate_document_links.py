"""Validate links in repository-facing documentation."""

from __future__ import annotations

import argparse
import re
import sys
from itertools import chain
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote, urlsplit


MARKDOWN_LINK_RE = re.compile(
    r"(?P<image>!?)\[[^\]\n]+\]\("
    r"(?P<target>[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)
HTML_LINK_RE = re.compile(
    r"""(?is)<a\b[^>]*\bhref\s*=\s*["'](?P<target>[^"']+)["'][^>]*>"""
)
ASCIIDOC_LINK_RE = re.compile(
    r"(?m)(?:^|\s)(?:link|xref):(?P<target>[^\[\s]+)\[[^\]]*\]"
)
RAW_HTML_BLOCK_RE = re.compile(
    r"(?is)<(?P<tag>p|div)\b[^>]*>(?P<body>.*?)</(?P=tag)>"
)


def _local_target(document: Path, target: str) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return (document.parent / unquote(parsed.path)).resolve()


def _default_documents(root: Path) -> list[Path]:
    paths = [
        root / "README.md",
        root / "README-zh.md",
        root / "PROMPT-SAMPLE.adoc",
        root / "PROMPT-SAMPLE-zh.adoc",
    ]
    paths.extend(sorted((root / "Docs").glob("*.md")))
    paths.extend(sorted((root / "Docs").glob("*.txt")))
    return paths


def validate_document_links(paths: Sequence[Path]) -> list[str]:
    """Return link issues found in the supplied documentation files."""
    issues: list[str] = []
    for path in paths:
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            issues.append(f"{path}: cannot read UTF-8 document: {error}")
            continue
        for block in RAW_HTML_BLOCK_RE.finditer(text):
            for link in MARKDOWN_LINK_RE.finditer(block.group("body")):
                if link.group("image"):
                    continue
                link_offset = block.start("body") + link.start()
                line_number = text.count("\n", 0, link_offset) + 1
                issues.append(
                    f"{path}: line {line_number}: Markdown link inside a "
                    "raw HTML block will render as text"
                )
        links = chain(
            MARKDOWN_LINK_RE.finditer(text),
            HTML_LINK_RE.finditer(text),
            ASCIIDOC_LINK_RE.finditer(text),
        )
        for link in links:
            if link.groupdict().get("image"):
                continue
            target = _local_target(path, link.group("target"))
            if target is None or target.exists():
                continue
            line_number = text.count("\n", 0, link.start()) + 1
            issues.append(
                f"{path}: line {line_number}: missing local target "
                f"{link.group('target')!r}"
            )
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Validate repository-local documentation links."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Documents to check (defaults to repository-facing documents)",
    )
    arguments = parser.parse_args(argv)
    paths = arguments.paths or _default_documents(root)

    issues = validate_document_links(paths)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1

    print(f"Document links OK: {len(paths)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
