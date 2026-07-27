from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.upstream import (
    UpstreamRepository,
    inspect_repository,
)
from dcsmizzer_survey.cli import main, parse_repository_spec


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


class UpstreamInspectionTests(unittest.TestCase):
    def test_repository_spec_preserves_windows_drive_colon(self) -> None:
        # Would fail if a Windows drive is treated as descriptor syntax.
        repository = parse_repository_spec(r"pydcs=D:\upstream\pydcs")

        self.assertEqual(repository.name, "pydcs")
        self.assertEqual(repository.path, Path(r"D:\upstream\pydcs"))

    def test_git_state_remote_head_and_license_are_reproducible(self) -> None:
        # Would fail if status is inferred from a recorded commit instead of live Git.
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            origin = base / "origin.git"
            work = base / "work"
            subprocess.run(
                ["git", "init", "--bare", "--initial-branch=main", str(origin)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "init", "--initial-branch=main", str(work)],
                check=True,
                capture_output=True,
                text=True,
            )
            run_git(work, "config", "user.name", "Survey Test")
            run_git(work, "config", "user.email", "survey@example.invalid")
            (work / "README.md").write_text("fixture\n", encoding="utf-8")
            (work / "LICENSE").write_text("fixture license\n", encoding="utf-8")
            run_git(work, "add", "README.md", "LICENSE")
            run_git(work, "commit", "-m", "fixture")
            run_git(work, "remote", "add", "origin", str(origin))
            run_git(work, "push", "--set-upstream", "origin", "main")

            observation = inspect_repository(
                UpstreamRepository("fixture", work),
                check_remote=True,
            )

            (work / "README.md").write_text("dirty\n", encoding="utf-8")
            dirty = inspect_repository(
                UpstreamRepository("fixture", work),
                check_remote=False,
            )

        report = observation.to_dict()
        self.assertTrue(report["valid_git"])
        self.assertEqual(report["branch"], "main")
        self.assertEqual(len(report["head"]), 40)
        self.assertTrue(report["clean"])
        self.assertTrue(report["remote_checked"])
        self.assertTrue(report["in_sync"])
        self.assertEqual(report["remote_kind"], "local")
        self.assertIsNone(report["remote_url"])
        self.assertEqual(report["license_evidence"], ["LICENSE"])
        self.assertFalse(dirty.clean)
        self.assertNotIn(str(work), json.dumps(report))

    def test_package_license_is_evidence_when_root_license_file_is_absent(self) -> None:
        # Would fail if package metadata is silently upgraded to a license file.
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--initial-branch=main", str(work)],
                check=True,
                capture_output=True,
                text=True,
            )
            run_git(work, "config", "user.name", "Survey Test")
            run_git(work, "config", "user.email", "survey@example.invalid")
            (work / "package.json").write_text(
                '{"name":"fixture","license":"MIT"}\n',
                encoding="utf-8",
            )
            run_git(work, "add", "package.json")
            run_git(work, "commit", "-m", "fixture")

            observation = inspect_repository(
                UpstreamRepository("fixture", work),
                check_remote=False,
            )

        self.assertEqual(
            observation.license_evidence,
            ("package.json#license=MIT",),
        )
        self.assertFalse(observation.remote_checked)
        self.assertIsNone(observation.in_sync)

    def test_cli_upstream_command_outputs_current_git_state_without_local_path(self) -> None:
        # Would fail if the reproducible command leaks the local clone location.
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--initial-branch=main", str(work)],
                check=True,
                capture_output=True,
                text=True,
            )
            run_git(work, "config", "user.name", "Survey Test")
            run_git(work, "config", "user.email", "survey@example.invalid")
            (work / "LICENSE").write_text("fixture\n", encoding="utf-8")
            run_git(work, "add", "LICENSE")
            run_git(work, "commit", "-m", "fixture")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "upstream",
                    "--repo",
                    f"fixture={work}",
                    "--skip-remote",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(report["schema"], "dcsmizzer.upstream-survey/v1")
        self.assertEqual(report["repositories"][0]["name"], "fixture")
        self.assertNotIn(str(work), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
