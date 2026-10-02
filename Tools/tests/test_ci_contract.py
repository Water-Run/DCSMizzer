from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "product-ci.yml"
REQUIREMENTS = REPOSITORY_ROOT / ".github" / "requirements-ci.txt"
VALIDATION_RUNNER = REPOSITORY_ROOT / ".github" / "validate_repository.py"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
RUFF_SHA256 = "bcabe2f6d0fc7819f1431793005af4e4de7371927d037345bf941252b195b9fa"


def _load_validation_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dcsmizzer_validation_runner",
        VALIDATION_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("validation runner could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContinuousValidationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.requirements = REQUIREMENTS.read_text(encoding="utf-8")
        cls.runner_text = VALIDATION_RUNNER.read_text(encoding="utf-8")
        cls.runner = _load_validation_runner()

    def test_workflow_is_bounded_plain_text(self) -> None:
        self.assertLessEqual(len(self.workflow.encode("utf-8")), 32 * 1024)
        self.assertNotIn("\t", self.workflow)
        self.assertNotIn("\x00", self.workflow)

    def test_validation_runner_is_bounded_plain_text(self) -> None:
        self.assertLessEqual(len(self.runner_text.encode("utf-8")), 32 * 1024)
        self.assertNotIn("\t", self.runner_text)
        self.assertNotIn("\x00", self.runner_text)

    def test_external_actions_are_commit_pinned(self) -> None:
        uses = re.findall(r"^\s*uses:\s*(\S+)", self.workflow, flags=re.MULTILINE)
        self.assertEqual(
            uses,
            [
                f"actions/checkout@{CHECKOUT_SHA}",
                f"actions/setup-python@{SETUP_PYTHON_SHA}",
            ],
        )
        for action in uses:
            self.assertRegex(action, r"@[0-9a-f]{40}\Z")

    def test_permissions_and_triggers_are_read_only(self) -> None:
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotIn("pull_request_target", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s*[^#\n]+:\s*write\s*$")
        self.assertIn("persist-credentials: false", self.workflow)

    def test_runtime_and_mutating_upstream_commands_are_absent(self) -> None:
        ordinary_lane = self.workflow + "\n" + self.runner_text
        for forbidden in (
            "runtime-run",
            "upstream-prepare",
            "DCS.exe",
            "steam.exe",
            "--authorize-dcs-launch",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden.casefold(), ordinary_lane.casefold())

    def test_python_and_ruff_are_exactly_pinned(self) -> None:
        self.assertIn('python-version: "3.14.3"', self.workflow)
        self.assertEqual(self.requirements.count("ruff==0.16.2"), 1)
        self.assertIn(f"--hash=sha256:{RUFF_SHA256}", self.requirements)
        self.assertIn("--require-hashes", self.workflow)
        self.assertIn("--only-binary=:all:", self.workflow)
        self.assertIn("--no-deps", self.workflow)

    def test_release_matrix_has_one_cache_isolated_entrypoint(self) -> None:
        self.assertEqual(
            self.workflow.count("python -B .github\\validate_repository.py"),
            1,
        )

        commands = self.runner.validation_commands(
            Path("<compile-cache>"),
            interpreter="python",
        )
        self.assertEqual(
            tuple(name for name, _ in commands),
            (
                "Product unit tests",
                "Maintainer survey tests",
                "Repository document links",
                "Bilingual Prompt samples",
                "Required Ruff rules",
                "Product and survey bytecode compilation",
            ),
        )
        flattened = tuple(command for _, command in commands)
        self.assertIn(
            ("python", "-B", "-m", "unittest", "discover", "-s", "Tools/tests"),
            flattened,
        )
        self.assertIn(
            (
                "python",
                "-B",
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
            flattened,
        )
        self.assertTrue(
            any("Tools/validate_document_links.py" in command for command in flattened)
        )
        self.assertTrue(
            any("Tools/validate_prompt_samples.py" in command for command in flattened)
        )
        self.assertTrue(any("ruff" in command for command in flattened))
        self.assertTrue(any("compileall" in command for command in flattened))

    def test_job_has_timeout_and_concurrency_cancellation(self) -> None:
        self.assertIn("timeout-minutes: 20", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        self.assertIn("runs-on: windows-2025", self.workflow)

    def test_ci_requirement_has_no_unhashed_requirement(self) -> None:
        meaningful = [
            line.strip()
            for line in self.requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(len(meaningful), 2)
        self.assertTrue(meaningful[0].startswith("ruff==0.16.2"))
        self.assertEqual(meaningful[1], f"--hash=sha256:{RUFF_SHA256}")


if __name__ == "__main__":
    unittest.main()
