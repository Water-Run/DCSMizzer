"""Validate one MIZ or CMP with the currently implemented read-only checks."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from dcsmizzer.cli import main as dcsmizzer_main


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return dcsmizzer_main(["inspect", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
