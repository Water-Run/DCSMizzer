"""Run the complete ordinary repository validation without source-tree caches."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BYTECODE_ROOTS = (Path("Tools"), Path(".develope/survey"))


def validation_commands(
    compile_cache: Path,
    *,
    interpreter: str = sys.executable,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the explicit, shell-free ordinary validation matrix."""

    python = (interpreter, "-B")
    return (
        (
            "Product unit tests",
            (*python, "-m", "unittest", "discover", "-s", "Tools/tests"),
        ),
        (
            "Maintainer survey tests",
            (
                *python,
                "-m",
                "unittest",
                "discover",
                "-s",
                ".develope/survey",
                "-t",
                ".develope/survey",
                "-p",
                "test_*.py",
            ),
        ),
        (
            "Repository document links",
            (*python, "Tools/validate_document_links.py"),
        ),
        (
            "Bilingual Prompt samples",
            (*python, "Tools/validate_prompt_samples.py"),
        ),
        (
            "Required Ruff rules",
            (
                *python,
                "-m",
                "ruff",
                "check",
                "--select",
                "E,F,B",
                ".github/validate_repository.py",
                "Tools/dcsmizzer.py",
                "Tools/dcsmizzer",
                "Tools/tests",
            ),
        ),
        (
            "Product and survey bytecode compilation",
            (
                interpreter,
                "-X",
                f"pycache_prefix={compile_cache}",
                "-m",
                "compileall",
                "-q",
                ".github/validate_repository.py",
                "Tools",
                ".develope/survey",
            ),
        ),
    )


def bytecode_artifacts(repository_root: Path) -> tuple[Path, ...]:
    """Return Python cache artifacts that would poison the CLI trust gate."""

    artifacts: list[Path] = []
    for relative_root in BYTECODE_ROOTS:
        root = repository_root / relative_root
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (path.is_dir() and path.name == "__pycache__") or (
                path.is_file() and path.suffix.casefold() in {".pyc", ".pyo"}
            ):
                artifacts.append(path)
    return tuple(sorted(artifacts))


def _report_bytecode_artifacts(
    repository_root: Path,
    artifacts: Sequence[Path],
    *,
    phase: str,
) -> None:
    print(
        f"Repository validation refused {phase}: Python cache artifacts exist",
        file=sys.stderr,
    )
    for path in artifacts[:20]:
        print(
            f"  {path.relative_to(repository_root).as_posix()}",
            file=sys.stderr,
        )
    if len(artifacts) > 20:
        print(f"  ... and {len(artifacts) - 20} more", file=sys.stderr)
    print(
        "Remove or relocate only the identified generated caches, then retry.",
        file=sys.stderr,
    )


def run_validation(repository_root: Path = REPOSITORY_ROOT) -> int:
    """Run every ordinary gate and preserve a cache-free source tree."""

    before = bytecode_artifacts(repository_root)
    if before:
        _report_bytecode_artifacts(repository_root, before, phase="before start")
        return 2

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    result = 0
    with tempfile.TemporaryDirectory(prefix="dcsmizzer-compile-") as cache:
        for name, command in validation_commands(Path(cache)):
            print(f"\n== {name} ==", flush=True)
            try:
                completed = subprocess.run(
                    command,
                    cwd=repository_root,
                    env=environment,
                    check=False,
                )
            except OSError as error:
                print(
                    f"Could not start validation command: {type(error).__name__}",
                    file=sys.stderr,
                )
                result = 2
                break
            if completed.returncode != 0:
                result = completed.returncode
                break

    after = bytecode_artifacts(repository_root)
    if after:
        _report_bytecode_artifacts(repository_root, after, phase="after execution")
        return 2
    return result


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: validate_repository.py", file=sys.stderr)
        return 2
    return run_validation()


if __name__ == "__main__":
    raise SystemExit(main())
