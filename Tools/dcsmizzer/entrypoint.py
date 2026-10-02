"""Installed CLI with the source checkout's provenance gate preserved."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


# Keep this boundary aligned with the pre-import gate in Tools/dcsmizzer.py.
# That bootstrap deliberately cannot import product code to discover the list.
_PROVENANCE_COMMANDS = frozenset(
    {
        "construction-snapshot",
        "construction-verify",
        "evidence-diff",
        "evidence-readiness",
        "evidence-snapshot",
        "evidence-verify",
        "report-summary",
        "runtime-collect",
        "runtime-prepare",
        "runtime-run",
        "terrain-probe-extract",
        "terrain-probe-instrument",
        "terrain-probe-script",
    }
)


def _requires_checkout_gate(arguments: list[str]) -> bool:
    command_index = 1 if arguments[:1] == ["--"] else 0
    option_tokens = arguments[command_index + 1 :]
    if "--" in option_tokens:
        option_tokens = option_tokens[: option_tokens.index("--")]
    if any(token in {"-h", "--help"} for token in option_tokens):
        return False
    return bool(
        (
            len(arguments) > command_index
            and arguments[command_index] in _PROVENANCE_COMMANDS
        )
        or any(
            token == "--evidence-bundle" or token.startswith("--evidence-bundle=")
            for token in option_tokens
        )
    )


def _source_bootstrap() -> Path | None:
    tools = Path(__file__).resolve().parent.parent
    bootstrap = tools / "dcsmizzer.py"
    return bootstrap if tools.name == "Tools" and bootstrap.is_file() else None


def main(argv: Sequence[str] | None = None) -> int:
    """Run ordinary commands or delegate to the isolated source bootstrap."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if _requires_checkout_gate(arguments):
        bootstrap = _source_bootstrap()
        if bootstrap is None:
            sys.stderr.write(
                "DCSMizzer error: this command requires a clean standalone Git "
                "source checkout. Run python Tools/dcsmizzer.py with these "
                "arguments from that checkout; an installed wheel has no "
                "verified Git producer identity.\n"
            )
            return 2
        try:
            return subprocess.run(
                [sys.executable, str(bootstrap), *arguments],
                check=False,
            ).returncode
        except OSError:
            sys.stderr.write("DCSMizzer error: could not start the source bootstrap.\n")
            return 2

    from .cli import main as cli_main

    return cli_main(arguments, stdout=sys.stdout, stderr=sys.stderr)
