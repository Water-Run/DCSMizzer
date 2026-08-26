from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.upstream_cache import (  # noqa: E402
    GIT_MUTATION_TIMEOUT_SECONDS,
    MAX_GIT_DIAGNOSTIC_BYTES,
    AcknowledgedUpstream,
    RequiredPath,
    _GitResult,
    _run_git_without_checkout,
    prepare_upstreams,
    upstream_report_usable,
    upstream_source_lock_status,
    upstream_status_report,
)


class UpstreamCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.bare = self.root / "fixture.git"
        self.seed.mkdir()
        self._git("init", "--quiet", "--initial-branch=main", cwd=self.seed)
        self._git(
            "config",
            "user.email",
            "fixture@example.invalid",
            cwd=self.seed,
        )
        self._git("config", "user.name", "Fixture", cwd=self.seed)
        (self.seed / "data").mkdir()
        (self.seed / "data" / "record.txt").write_text(
            "record\n",
            encoding="utf-8",
        )
        (self.seed / "payload.txt").write_text(
            "payload\n",
            encoding="utf-8",
        )
        (self.seed / ".gitignore").write_text(
            "__pycache__/\n",
            encoding="utf-8",
        )
        license_payload = b"Fixture license text\n"
        (self.seed / "LICENSE").write_bytes(license_payload)
        self._git("add", ".", cwd=self.seed)
        self._git("commit", "--quiet", "-m", "fixture", cwd=self.seed)
        self.commit = self._git_output(
            "rev-parse",
            "HEAD",
            cwd=self.seed,
        )
        self.tree = self._git_output(
            "rev-parse",
            "HEAD^{tree}",
            cwd=self.seed,
        )
        self._git(
            "clone",
            "--quiet",
            "--bare",
            str(self.seed),
            str(self.bare),
            cwd=self.root,
        )
        self.source = AcknowledgedUpstream(
            name="fixture",
            remote="https://example.invalid/fixture.git",
            branch="main",
            commit=self.commit,
            tree=self.tree,
            directory="fixture-upstream",
            license_id="MIT",
            license_path="LICENSE",
            license_sha256=hashlib.sha256(
                license_payload.replace(b"\n", b"\r\n")
            ).hexdigest(),
            required_paths=(
                RequiredPath("data", "directory"),
                RequiredPath("payload.txt", "file"),
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_status_missing_is_read_only_and_fails_gate(self) -> None:
        cache = self.root / "missing-cache"

        with self._patched_manifest():
            report = upstream_status_report(cache)

        self.assertFalse(cache.exists())
        self.assertFalse(upstream_report_usable(report))
        self.assertEqual(report["schema"], "dcsmizzer.acknowledged-upstream-cache/v1")
        self.assertFalse(report["cache"]["present"])
        self.assertEqual(
            report["sources"][0]["errors"][0]["code"],
            "checkout_missing",
        )

    def test_status_accepts_exact_clean_profile(self) -> None:
        cache = self.root / "cache"
        cache.mkdir()
        checkout = cache / self.source.directory
        self._git(
            "clone",
            "--quiet",
            str(self.bare),
            str(checkout),
            cwd=cache,
        )
        self._git(
            "remote",
            "set-url",
            "origin",
            self.source.remote,
            cwd=checkout,
        )

        with self._patched_manifest():
            report = upstream_status_report(cache)

        record = report["sources"][0]
        self.assertTrue(upstream_report_usable(report))
        self.assertTrue(record["validation"]["exact_pin"])
        self.assertTrue(record["validation"]["tree_matches"])
        self.assertTrue(record["validation"]["license_matches"])
        self.assertTrue(record["validation"]["required_paths_complete"])
        self.assertEqual(
            record["actual"]["remote"],
            self.source.remote,
        )
        self._assert_private_paths_absent(report)

    def test_single_source_lock_accepts_exact_root_without_siblings(self) -> None:
        cache, checkout = self._cloned_cache()

        report = upstream_source_lock_status(
            checkout,
            self.source.name,
            manifest=(self.source,),
        )

        self.assertTrue(report["acknowledged"])
        self.assertTrue(report["validation"]["usable"])
        self.assertEqual(report["actual"]["head"], self.commit)
        self.assertEqual(report["actual"]["tree"], self.tree)
        self.assertEqual(
            report["schema"],
            "dcsmizzer.acknowledged-upstream-source-lock/v1",
        )
        self.assertFalse(
            (cache / "some-other-acknowledged-source").exists()
        )
        self._assert_private_paths_absent(report)

    def test_default_manifest_single_source_status_is_structured_and_private(
        self,
    ) -> None:
        checkout = self.root / "missing-pydcs"

        report = upstream_source_lock_status(checkout, "pydcs")

        self.assertEqual(report["source"], "pydcs")
        self.assertFalse(report["acknowledged"])
        self.assertEqual(
            report["failure_reasons"],
            ["checkout_missing"],
        )
        self.assertRegex(report["expected"]["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(report["expected"]["tree"], r"^[0-9a-f]{40}$")
        self.assertFalse(report["privacy"]["local_paths_exposed"])
        self._assert_private_paths_absent(report)

    def test_status_rejects_wrong_remote_without_exposing_it(self) -> None:
        cache, checkout = self._cloned_cache()
        wrong_remote = self.root / "private-other.git"
        self._git(
            "remote",
            "set-url",
            "origin",
            str(wrong_remote),
            cwd=checkout,
        )

        with self._patched_manifest():
            report = upstream_status_report(cache)
            source_lock = upstream_source_lock_status(
                checkout,
                self.source.name,
            )

        record = report["sources"][0]
        self.assertFalse(upstream_report_usable(report))
        self.assertFalse(source_lock["acknowledged"])
        self.assertFalse(source_lock["validation"]["remote_matches"])
        self.assertFalse(record["validation"]["remote_matches"])
        self.assertIn(
            "remote_mismatch",
            {error["code"] for error in record["errors"]},
        )
        rendered = json.dumps(report)
        self.assertNotIn(str(wrong_remote), rendered)
        self.assertNotIn(
            str(wrong_remote).replace("\\", "\\\\"),
            rendered,
        )
        self._assert_private_paths_absent(source_lock)

    def test_status_and_prepare_reject_dirty_checkout(self) -> None:
        cache, checkout = self._cloned_cache()
        dirty = checkout / "private-untracked.txt"
        dirty.write_text("do not overwrite\n", encoding="utf-8")
        before = self._git_output("rev-parse", "HEAD", cwd=checkout)

        with self._patched_manifest():
            status_report = upstream_status_report(cache)
            prepared = prepare_upstreams(cache)

        self.assertFalse(status_report["sources"][0]["actual"]["clean"])
        self.assertFalse(upstream_report_usable(prepared))
        self.assertEqual(
            prepared["preparation"]["operations"][0]["reason"],
            "existing_checkout_not_clean",
        )
        self.assertTrue(dirty.exists())
        self.assertEqual(
            self._git_output("rev-parse", "HEAD", cwd=checkout),
            before,
        )

    def test_status_rejects_hidden_index_flags_and_ignored_files(self) -> None:
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                _, checkout = self._cloned_cache()
                self._git("update-index", flag, "payload.txt", cwd=checkout)
                (checkout / "payload.txt").write_text(
                    "hidden modification\n",
                    encoding="utf-8",
                )

                with self._patched_manifest():
                    report = upstream_status_report(checkout.parent)

                record = report["sources"][0]
                self.assertFalse(record["validation"]["index_flags_safe"])
                self.assertFalse(record["validation"]["usable"])
                self.assertIn(
                    "unsafe_index_flags",
                    {error["code"] for error in record["errors"]},
                )

        _, checkout = self._cloned_cache()
        ignored = checkout / "data" / "__pycache__" / "projection.pyc"
        ignored.parent.mkdir()
        ignored.write_bytes(b"ignored executable fixture")
        with self._patched_manifest():
            report = upstream_status_report(checkout.parent)

        record = report["sources"][0]
        self.assertFalse(record["actual"]["clean"])
        self.assertFalse(record["validation"]["usable"])
        self.assertIn(
            "dirty_worktree",
            {error["code"] for error in record["errors"]},
        )

    def test_status_isolates_hostile_git_environment_and_fsmonitor(self) -> None:
        _, checkout = self._cloned_cache()
        (checkout / "payload.txt").write_text(
            "visible modification\n",
            encoding="utf-8",
        )
        hostile = {
            "GIT_WORK_TREE": str(self.seed),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "hostile-fsmonitor-command",
        }
        with self._patched_manifest(), patch.dict(
            os.environ,
            hostile,
            clear=False,
        ):
            report = upstream_status_report(checkout.parent)

        record = report["sources"][0]
        self.assertFalse(record["actual"]["clean"])
        self.assertFalse(record["validation"]["usable"])
        self.assertIn(
            "dirty_worktree",
            {error["code"] for error in record["errors"]},
        )

    def test_status_rejects_worktree_filter_and_info_attributes(self) -> None:
        _, checkout = self._cloned_cache()
        self._git(
            "config",
            "--local",
            "extensions.worktreeConfig",
            "true",
            cwd=checkout,
        )
        self._git(
            "config",
            "--worktree",
            "filter.hide.clean",
            "git show HEAD:payload.txt",
            cwd=checkout,
        )
        (checkout / ".git" / "info" / "attributes").write_text(
            "payload.txt filter=hide\n",
            encoding="utf-8",
        )
        (checkout / "payload.txt").write_text(
            "hidden modification\n",
            encoding="utf-8",
        )
        with self._patched_manifest():
            report = upstream_status_report(checkout.parent)

        record = report["sources"][0]
        self.assertFalse(record["validation"]["local_config_safe"])
        self.assertFalse(record["validation"]["usable"])
        self.assertIn(
            "unsafe_local_git_config",
            {error["code"] for error in record["errors"]},
        )

    def test_prepare_refuses_dangerous_local_git_config(self) -> None:
        cache, checkout = self._cloned_cache()
        self._git(
            "config",
            "--local",
            "filter.fixture.smudge",
            "private-command --argument",
            cwd=checkout,
        )

        with self._patched_manifest():
            status_report = upstream_status_report(cache)
            prepared = prepare_upstreams(cache)

        record = status_report["sources"][0]
        self.assertFalse(record["validation"]["local_config_safe"])
        self.assertIn(
            "unsafe_local_git_config",
            {error["code"] for error in record["errors"]},
        )
        self.assertEqual(
            prepared["preparation"]["operations"][0]["reason"],
            "existing_checkout_local_config_unsafe",
        )

    def test_offline_prepare_refuses_missing_commit_object(self) -> None:
        cache, checkout = self._cloned_cache()
        missing = AcknowledgedUpstream(
            name=self.source.name,
            remote=self.source.remote,
            branch=self.source.branch,
            commit="1" * 40,
            tree="2" * 40,
            directory=self.source.directory,
            license_id=self.source.license_id,
            license_path=self.source.license_path,
            license_sha256=self.source.license_sha256,
            required_paths=self.source.required_paths,
        )
        before = self._git_output("rev-parse", "HEAD", cwd=checkout)

        with patch(
            "dcsmizzer.upstream_cache.ACKNOWLEDGED_UPSTREAMS",
            (missing,),
        ):
            report = prepare_upstreams(cache, offline=True)

        operation = report["preparation"]["operations"][0]
        self.assertFalse(upstream_report_usable(report))
        self.assertEqual(operation["reason"], "offline_pinned_object_missing")
        self.assertEqual(
            self._git_output("rev-parse", "HEAD", cwd=checkout),
            before,
        )

    def test_online_prepare_clones_and_detaches_at_pin(self) -> None:
        cache = self.root / "prepared-cache"

        with (
            self._patched_manifest(),
            patch(
                "dcsmizzer.upstream_cache._run_git_without_checkout",
                side_effect=self._local_clone_without_network,
            ),
        ):
            report = prepare_upstreams(cache)

        self.assertTrue(upstream_report_usable(report))
        self.assertEqual(
            report["preparation"]["operations"][0]["result"],
            "completed",
        )
        record = report["sources"][0]
        self.assertTrue(record["actual"]["detached"])
        self.assertEqual(record["actual"]["head"], self.commit)
        self.assertEqual(record["actual"]["tree"], self.tree)
        self._assert_private_paths_absent(report)

    def test_status_and_prepare_cli_share_gate_and_require_explicit_root(
        self,
    ) -> None:
        missing_stdout = io.StringIO()
        missing_stderr = io.StringIO()
        with (
            self._patched_manifest(),
            patch(
                "dcsmizzer.upstream_cache._run_git_without_checkout",
                side_effect=self._local_clone_without_network,
            ),
        ):
            missing_exit = main(
                [
                    "upstream-status",
                    "--cache-root",
                    str(self.root / "missing-cli-cache"),
                ],
                stdout=missing_stdout,
                stderr=missing_stderr,
            )
            prepared_stdout = io.StringIO()
            prepared_exit = main(
                [
                    "upstream-prepare",
                    "--cache-root",
                    str(self.root / "cli-cache"),
                ],
                stdout=prepared_stdout,
                stderr=io.StringIO(),
            )
            status_stdout = io.StringIO()
            status_exit = main(
                [
                    "upstream-status",
                    "--cache-root",
                    str(self.root / "cli-cache"),
                ],
                stdout=status_stdout,
                stderr=io.StringIO(),
            )

        self.assertEqual(missing_exit, 1)
        self.assertEqual(missing_stderr.getvalue(), "")
        self.assertEqual(prepared_exit, 0)
        self.assertEqual(status_exit, 0)
        self.assertEqual(
            json.loads(prepared_stdout.getvalue())["validation"],
            json.loads(status_stdout.getvalue())["validation"],
        )

        error = io.StringIO()
        self.assertEqual(
            main(["upstream-status"], stdout=io.StringIO(), stderr=error),
            2,
        )
        self.assertIn("--cache-root", error.getvalue())

    def test_help_states_authority_and_no_implicit_develope(self) -> None:
        for command in ("upstream-status", "upstream-prepare"):
            with self.subTest(command=command):
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = main([command, "--help"])
                rendered = output.getvalue()
                self.assertEqual(exit_code, 0)
                self.assertIn("Authority:", rendered)
                self.assertIn("--cache-root", rendered)
                self.assertIn(".develope", rendered)

    def test_root_and_recognized_child_symlinks_are_rejected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "cache-alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")

        with self._patched_manifest():
            with self.assertRaisesRegex(ValueError, "symbolic link|reparse"):
                upstream_status_report(alias)

        cache = self.root / "real-cache"
        cache.mkdir()
        child = cache / self.source.directory
        child.symlink_to(outside, target_is_directory=True)
        with self._patched_manifest():
            with self.assertRaisesRegex(ValueError, "symbolic link|reparse"):
                prepare_upstreams(cache)

    def test_failed_git_diagnostic_is_redacted_and_byte_bounded(self) -> None:
        cache = self.root / "diagnostic-cache"
        private = str(self.root / "private-source")
        huge_error = f"fatal: {private} " + ("界" * 3000)
        failure = _GitResult(
            returncode=128,
            stdout="",
            stderr=huge_error,
            timed_out=True,
        )

        with (
            self._patched_manifest(),
            patch(
                "dcsmizzer.upstream_cache._run_git_without_checkout",
                return_value=failure,
            ),
        ):
            report = prepare_upstreams(cache)

        error = report["preparation"]["operations"][0]["git_error"]
        self.assertEqual(error["kind"], "timeout")
        self.assertLessEqual(
            len(error["diagnostic"].encode("utf-8")),
            MAX_GIT_DIAGNOSTIC_BYTES,
        )
        self.assertTrue(error["diagnostic"].endswith("... [truncated]"))
        rendered = json.dumps(report)
        self.assertNotIn(private, rendered)
        self.assertNotIn(private.replace("\\", "\\\\"), rendered)

    def test_clone_is_https_only_and_ignores_system_global_config(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        with (
            patch.dict(
                os.environ,
                {
                    "GIT_ATTR_NOSYSTEM": "0",
                    "GIT_ATTR_SOURCE": "private-attribute-source",
                    "GIT_CONFIG_GLOBAL": "private-global-config",
                    "GIT_CONFIG_PARAMETERS": "'protocol.file.allow'='always'",
                },
            ),
            patch(
                "dcsmizzer.upstream_cache.subprocess.run",
                return_value=completed,
            ) as runner,
        ):
            result = _run_git_without_checkout(
                self.source,
                self.root / "target",
                self.root / "empty-template",
                redactions=(self.root,),
            )

        self.assertEqual(result.returncode, 0)
        command = runner.call_args.args[0]
        environment = runner.call_args.kwargs["env"]
        self.assertGreaterEqual(GIT_MUTATION_TIMEOUT_SECONDS, 900)
        self.assertIn("protocol.allow=never", command)
        self.assertIn("protocol.https.allow=always", command)
        self.assertEqual(environment["GIT_ALLOW_PROTOCOL"], "https")
        self.assertEqual(environment["GIT_ATTR_NOSYSTEM"], "1")
        self.assertNotIn("GIT_ATTR_SOURCE", environment)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertNotIn("GIT_CONFIG_PARAMETERS", environment)
        self.assertFalse(runner.call_args.kwargs["shell"])

    def _cloned_cache(self) -> tuple[Path, Path]:
        cache = self.root / f"cache-{len(list(self.root.glob('cache-*')))}"
        cache.mkdir()
        checkout = cache / self.source.directory
        self._git(
            "clone",
            "--quiet",
            str(self.bare),
            str(checkout),
            cwd=cache,
        )
        self._git(
            "remote",
            "set-url",
            "origin",
            self.source.remote,
            cwd=checkout,
        )
        return cache, checkout

    def _local_clone_without_network(
        self,
        source: AcknowledgedUpstream,
        target: Path,
        template_directory: Path,
        *,
        redactions: object,
    ) -> _GitResult:
        del template_directory, redactions
        self._git(
            "clone",
            "--quiet",
            str(self.bare),
            str(target),
            cwd=target.parent,
        )
        self._git(
            "remote",
            "set-url",
            "origin",
            source.remote,
            cwd=target,
        )
        return _GitResult(returncode=0, stdout="", stderr="")

    def _patched_manifest(self):
        return patch(
            "dcsmizzer.upstream_cache.ACKNOWLEDGED_UPSTREAMS",
            (self.source,),
        )

    def _assert_private_paths_absent(self, report: dict[str, object]) -> None:
        rendered = json.dumps(report)
        for private in (str(self.root), str(self.bare)):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private.replace("\\", "\\\\"), rendered)

    def _git(self, *arguments: str, cwd: Path) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
            },
        )

    def _git_output(self, *arguments: str, cwd: Path) -> str:
        result = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
