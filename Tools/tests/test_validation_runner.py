from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / ".github" / "validate_repository.py"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dcsmizzer_validation_runner_tests",
        RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("validation runner could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryValidationRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = _load_runner()

    def test_bytecode_artifacts_are_detected_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Tools" / "package" / "__pycache__"
            cache.mkdir(parents=True)
            bytecode = cache / "module.cpython-fixture.pyc"
            bytecode.write_bytes(b"fixture")

            artifacts = self.runner.bytecode_artifacts(root)

            self.assertIn(cache, artifacts)
            self.assertIn(bytecode, artifacts)
            self.assertTrue(bytecode.is_file())

    def test_clean_fixture_has_no_bytecode_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tools" / "package" / "module.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")

            self.assertEqual(self.runner.bytecode_artifacts(root), ())

    def test_preexisting_cache_refuses_before_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Tools" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "entry.pyc").write_bytes(b"fixture")

            with mock.patch.object(self.runner.subprocess, "run") as run:
                result = self.runner.run_validation(root)

            self.assertEqual(result, 2)
            run.assert_not_called()

    def test_first_command_failure_is_returned_without_cache_pollution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Tools").mkdir()
            (root / ".develope" / "survey").mkdir(parents=True)
            failed = subprocess.CompletedProcess(("python",), 7)

            with mock.patch.object(
                self.runner.subprocess,
                "run",
                return_value=failed,
            ) as run:
                result = self.runner.run_validation(root)

            self.assertEqual(result, 7)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(self.runner.bytecode_artifacts(root), ())


if __name__ == "__main__":
    unittest.main()
