from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ReleaseBoundaryTests(unittest.TestCase):
    def test_product_python_does_not_reference_development_tree(self) -> None:
        offenders: list[str] = []
        product_paths = [
            *(REPOSITORY_ROOT / "Tools").glob("*.py"),
            *(REPOSITORY_ROOT / "Tools" / "dcsmizzer").rglob("*.py"),
        ]
        for path in sorted(product_paths):
            text = path.read_text(encoding="utf-8")
            if re.search(r"""["']\.develope[\\/]""", text):
                offenders.append(path.relative_to(REPOSITORY_ROOT).as_posix())

        self.assertEqual(offenders, [])

    def test_document_command_blocks_do_not_reference_development_tree(
        self,
    ) -> None:
        documents = [
            REPOSITORY_ROOT / "README.md",
            REPOSITORY_ROOT / "README-zh.md",
            *(REPOSITORY_ROOT / "Docs").rglob("*.md"),
        ]
        offenders: list[str] = []
        for path in sorted(documents):
            in_fence = False
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence and ".develope" in line:
                    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                    offenders.append(f"{relative}:{line_number}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
