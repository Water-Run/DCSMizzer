"""Validate links in repository-facing documentation."""

from __future__ import annotations

import argparse
import html
import re
import string
import subprocess
import sys
import unicodedata
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
ATX_HEADING_RE = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]+(?P<body>.*?)"
    r"(?:[ \t]+#+[ \t]*)?$"
)
SETEXT_HEADING_RE = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})")
HTML_ANCHOR_RE = re.compile(
    r"""(?is)<[a-z][^>]*\b(?:id|name)\s*=\s*"""
    r"""["'](?P<anchor>[^"']+)["'][^>]*>"""
)
INLINE_HTML_RE = re.compile(r"(?s)<[^>]+>")
INLINE_MARKDOWN_LINK_RE = re.compile(
    r"!?\[(?P<label>[^\]\n]*)\]\([^)\n]*\)"
)


def _local_target(document: Path, target: str) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path:
        return document.resolve() if parsed.fragment else None
    return (document.parent / unquote(parsed.path)).resolve()


def _default_documents(root: Path) -> list[Path]:
    paths = [
        root / "README.md",
        root / "README-zh.md",
        root / "PROMPT-SAMPLE.adoc",
        root / "PROMPT-SAMPLE-zh.adoc",
    ]
    paths.extend(sorted((root / "Docs").rglob("*.md")))
    paths.extend(sorted((root / "Docs").rglob("*.txt")))
    return paths


def _heading_slug(value: str) -> str:
    value = INLINE_MARKDOWN_LINK_RE.sub(
        lambda match: match.group("label"),
        value,
    )
    value = INLINE_HTML_RE.sub("", value)
    value = html.unescape(value).lower()
    slug: list[str] = []
    for character in value:
        if character.isspace():
            slug.append("-")
        elif character in "-_":
            slug.append(character)
        elif (
            character in string.punctuation
            or unicodedata.category(character)[0] in {"C", "P"}
        ):
            continue
        else:
            slug.append(character)
    return "".join(slug)


def _markdown_anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    anchors = {
        html.unescape(unquote(match.group("anchor")))
        for match in HTML_ANCHOR_RE.finditer(text)
    }
    used_slugs: set[str] = set()
    previous_line: str | None = None
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines():
        fence = FENCE_RE.match(line)
        if fence is not None:
            marker = fence.group("fence")
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            previous_line = None
            continue
        if fence_character is not None:
            continue

        heading = ATX_HEADING_RE.match(line)
        heading_text: str | None = None
        if heading is not None:
            heading_text = heading.group("body")
        elif (
            previous_line is not None
            and previous_line.strip()
            and SETEXT_HEADING_RE.match(line) is not None
        ):
            heading_text = previous_line.strip()

        if heading_text is not None:
            base = _heading_slug(heading_text)
            if base:
                slug = base
                suffix = 1
                while slug in used_slugs:
                    slug = f"{base}-{suffix}"
                    suffix += 1
                used_slugs.add(slug)
                anchors.add(slug)
            previous_line = None
        else:
            previous_line = line
    return anchors


def validate_document_links(
    paths: Sequence[Path],
    *,
    tracked_paths: frozenset[Path] | None = None,
) -> list[str]:
    """Return link issues found in the supplied documentation files."""
    issues: list[str] = []
    anchor_cache: dict[Path, set[str] | None] = {}
    for path in paths:
        path = Path(path)
        if tracked_paths is not None and path.resolve() not in tracked_paths:
            issues.append(f"{path}: document is not tracked in Git")
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
            raw_target = link.group("target")
            target = _local_target(path, raw_target)
            if target is None:
                continue
            line_number = text.count("\n", 0, link.start()) + 1
            if not target.exists():
                issues.append(
                    f"{path}: line {line_number}: missing local target "
                    f"{raw_target!r}"
                )
                continue
            if tracked_paths is not None and target.resolve() not in tracked_paths:
                issues.append(
                    f"{path}: line {line_number}: local target is not tracked "
                    f"in Git {raw_target!r}"
                )
                continue

            fragment = unquote(urlsplit(raw_target).fragment)
            if not fragment or target.suffix.casefold() != ".md":
                continue
            resolved_target = target.resolve()
            if resolved_target not in anchor_cache:
                try:
                    anchor_cache[resolved_target] = _markdown_anchors(
                        resolved_target
                    )
                except (OSError, UnicodeError):
                    anchor_cache[resolved_target] = None
            anchors = anchor_cache[resolved_target]
            if anchors is None:
                issues.append(
                    f"{path}: line {line_number}: cannot read local fragment "
                    f"target {raw_target!r}"
                )
            elif fragment not in anchors:
                issues.append(
                    f"{path}: line {line_number}: missing local fragment "
                    f"{raw_target!r}"
                )
    return issues


def _git_tracked_paths(root: Path) -> frozenset[Path]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--"],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError("cannot enumerate the repository Git index") from error
    if len(completed.stdout) > 16 * 1024 * 1024:
        raise ValueError("repository Git index listing exceeds the byte limit")
    try:
        names = completed.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as error:
        raise ValueError("repository Git index paths are not UTF-8") from error
    tracked: set[Path] = set()
    for name in names:
        if not name:
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("repository Git index contains an unsafe path")
        tracked.add((root / relative).resolve())
    return frozenset(tracked)


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

    try:
        tracked_paths = _git_tracked_paths(root)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    issues = validate_document_links(paths, tracked_paths=tracked_paths)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1

    print(f"Document links OK: {len(paths)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
