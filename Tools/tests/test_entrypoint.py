from __future__ import annotations

import ast
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.entrypoint import _PROVENANCE_COMMANDS, main  # noqa: E402


class InstalledEntrypointTests(unittest.TestCase):
    def test_ordinary_command_works_without_a_source_checkout(self) -> None:
        output = io.StringIO()
        with patch("dcsmizzer.entrypoint._source_bootstrap", return_value=None):
            with redirect_stdout(output):
                result = main(["capabilities"])
        self.assertEqual(result, 0)
        self.assertIn("schema", json.loads(output.getvalue()))

    def test_wheel_refuses_provenance_work_before_loading_cli(self) -> None:
        script = """
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from dcsmizzer.entrypoint import main
with patch('dcsmizzer.entrypoint._source_bootstrap', return_value=None):
    assert main(['evidence-snapshot']) == 2
assert 'dcsmizzer.cli' not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(TOOLS_ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("installed wheel", result.stderr)

    def test_wheel_refuses_every_sensitive_command_and_external_binding(self) -> None:
        cases = [
            *([command] for command in sorted(_PROVENANCE_COMMANDS)),
            ["capabilities", "--evidence-bundle", "fixture"],
            ["capabilities", "--evidence-bundle=fixture"],
            ["--", "evidence-snapshot"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                errors = io.StringIO()
                with (
                    patch("dcsmizzer.entrypoint._source_bootstrap", return_value=None),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    result = main(arguments)
                self.assertEqual(result, 2)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("source checkout", errors.getvalue())

    def test_help_remains_available_for_checkout_commands(self) -> None:
        output = io.StringIO()
        with patch("dcsmizzer.entrypoint._source_bootstrap", return_value=None):
            with redirect_stdout(output):
                result = main(["runtime-prepare", "--help"])
        self.assertEqual(result, 0)
        self.assertIn("--dcs-root", output.getvalue())

    def test_source_install_preserves_bootstrap_arguments_and_failure(self) -> None:
        arguments = ["evidence-snapshot", "--dcs-root", "a path with spaces"]
        bootstrap = TOOLS_ROOT / "dcsmizzer.py"
        with (
            patch("dcsmizzer.entrypoint._source_bootstrap", return_value=bootstrap),
            patch(
                "dcsmizzer.entrypoint.subprocess.run",
                return_value=subprocess.CompletedProcess([], 2),
            ) as run,
        ):
            self.assertEqual(main(arguments), 2)
        run.assert_called_once_with(
            [sys.executable, str(bootstrap), *arguments], check=False
        )

    def test_command_boundary_stays_in_sync_with_the_isolated_bootstrap(self) -> None:
        tree = ast.parse((TOOLS_ROOT / "dcsmizzer.py").read_text(encoding="utf-8"))
        assignments = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_PROVENANCE_COMMANDS"
                for target in node.targets
            )
        ]
        self.assertEqual(len(assignments), 1)
        value = assignments[0].value
        self.assertIsInstance(value, ast.Call)
        self.assertEqual(
            frozenset(ast.literal_eval(value.args[0])), _PROVENANCE_COMMANDS
        )


if __name__ == "__main__":
    unittest.main()
