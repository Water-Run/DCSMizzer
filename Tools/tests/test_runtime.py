from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer import runtime  # noqa: E402


VERSION = "2.9.28.26385"
PRODUCER_COMMIT = "a" * 40
REAL_GIT_IDENTITY = runtime._git_identity
PROVENANCE_COMMANDS = frozenset(
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


class _CompletedProcess:
    pid = 4242

    def poll(self) -> int:
        return 0


class _TimeoutProcess:
    pid = 4343

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self) -> None:
        return -9 if self.killed else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> int:
        if not self.killed:
            raise subprocess.TimeoutExpired("DCS.exe", timeout)
        return -9


class _ExitProcess:
    def __init__(self, return_code: int) -> None:
        self.pid = 4545
        self.return_code = return_code

    def poll(self) -> int:
        return self.return_code


class _UnstoppableProcess:
    pid = 4646

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> int:
        raise subprocess.TimeoutExpired("DCS.exe", timeout)


class RuntimeBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dcs_root = (
            self.root / "steamapps" / "common" / "DCSWorld"
        )
        executable = self.dcs_root / "bin-mt" / "DCS.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"fixture dcs executable")
        api = self.dcs_root / "API" / "Sim_ControlAPI.md"
        api.parent.mkdir()
        api.write_text("Sim.setUserCallbacks\n", encoding="utf-8")
        (self.root / "steamapps" / "appmanifest_223750.acf").write_text(
            '"appid" "223750"\n'
            '"StateFlags" "4"\n'
            '"installdir" "DCSWorld"\n'
            '"LauncherPath" "C:\\\\Steam\\\\Steam.exe"\n'
            '"buildid" "24431605"\n',
            encoding="utf-8",
        )
        self.saved_games = self.root / "Saved Games"
        self.saved_games.mkdir()
        self.version_patcher = patch(
            "dcsmizzer.runtime._windows_product_version",
            return_value=VERSION,
        )
        self.version_patcher.start()
        self.current_producer = {
            "commit": PRODUCER_COMMIT,
            "dirty": False,
        }
        self.git_identity_patcher = patch(
            "dcsmizzer.runtime._git_identity",
            side_effect=lambda root: dict(self.current_producer),
        )
        self.git_identity_patcher.start()

    def tearDown(self) -> None:
        self.git_identity_patcher.stop()
        self.version_patcher.stop()
        self.temporary.cleanup()

    def test_git_identity_rejects_assume_unchanged_source_edits(self) -> None:
        repository = self.root / "producer"
        source_root = repository / "Tools"
        source_root.mkdir(parents=True)

        def git(*arguments: str) -> None:
            subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        source = source_root / "producer.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        git("add", "Tools/producer.py")
        git("commit", "--quiet", "-m", "fixture")
        with patch.dict(
            os.environ,
            {
                "GIT_ATTR_NOSYSTEM": "0",
                "GIT_ATTR_SOURCE": "refs/heads/does-not-exist",
            },
        ):
            self.assertFalse(REAL_GIT_IDENTITY(repository)["dirty"])

        git("update-index", "--assume-unchanged", "Tools/producer.py")
        source.write_text("VALUE = 2\n", encoding="utf-8")

        self.assertTrue(REAL_GIT_IDENTITY(repository)["dirty"])

    def test_git_identity_rejects_ignored_import_shadow(self) -> None:
        repository = self.root / "shadow-producer"
        source_root = repository / "Tools"
        source_root.mkdir(parents=True)

        def git(*arguments: str) -> None:
            subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        (source_root / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
        git("add", "Tools/entry.py")
        git("commit", "--quiet", "-m", "fixture")
        exclude = repository / ".git" / "info" / "exclude"
        exclude.write_text(
            "Tools/json.py\nTools/__pycache__/\n",
            encoding="utf-8",
        )
        self.assertFalse(REAL_GIT_IDENTITY(repository)["dirty"])

        (source_root / "json.py").write_text(
            "raise RuntimeError('shadow')\n",
            encoding="utf-8",
        )

        self.assertTrue(REAL_GIT_IDENTITY(repository)["dirty"])

    def test_git_identity_rejects_ignored_bytecode_cache(self) -> None:
        repository = self.root / "bytecode-producer"
        source_root = repository / "Tools"
        source_root.mkdir(parents=True)

        def git(*arguments: str) -> None:
            subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        (source_root / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
        git("add", "Tools/entry.py")
        git("commit", "--quiet", "-m", "fixture")
        exclude = repository / ".git" / "info" / "exclude"
        exclude.write_text("Tools/__pycache__/\n", encoding="utf-8")
        cache = source_root / "__pycache__"
        cache.mkdir()
        (cache / "entry.cpython-fixture.pyc").write_bytes(b"cache")

        self.assertTrue(REAL_GIT_IDENTITY(repository)["dirty"])

    def test_git_identity_rejects_filter_hidden_source_edit(self) -> None:
        repository = self.root / "filtered-producer"
        source_root = repository / "Tools"
        source_root.mkdir(parents=True)

        def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        source = source_root / "producer.py"
        source.write_text("VALUE = 'TRUSTED'\n", encoding="utf-8")
        git("add", "Tools/producer.py")
        git("commit", "--quiet", "-m", "fixture")
        git(
            "config",
            "--local",
            "filter.hide.clean",
            "git show HEAD:Tools/producer.py",
        )
        attributes = repository / ".git" / "info" / "attributes"
        attributes.write_text(
            "Tools/producer.py filter=hide\n",
            encoding="utf-8",
        )
        source.write_text("VALUE = 'HOSTILE'\n", encoding="utf-8")

        self.assertEqual(
            git("status", "--porcelain=v1").stdout,
            b"",
        )
        self.assertTrue(REAL_GIT_IDENTITY(repository)["dirty"])

    def test_runtime_chain_requires_the_same_clean_producer_commit(self) -> None:
        invalid_identities = (
            ("dirty", {"commit": PRODUCER_COMMIT, "dirty": True}),
            ("missing", {"commit": None, "dirty": False}),
            ("malformed", {"commit": "not-a-commit", "dirty": False}),
        )
        for label, identity in invalid_identities:
            with self.subTest(identity=label):
                self.current_producer.clear()
                self.current_producer.update(identity)
                with self.assertRaisesRegex(
                    ValueError,
                    "clean commit-bound producer",
                ):
                    runtime.prepare_runtime(
                        self.dcs_root,
                        self.saved_games,
                        run_id=f"{label}-producer",
                        mode="registry-probe",
                    )
                self.assertFalse(
                    (
                        self.saved_games
                        / f"DCSMizzer-{label}-producer"
                    ).exists()
                )

        self.current_producer.clear()
        self.current_producer.update(
            {"commit": PRODUCER_COMMIT, "dirty": False}
        )
        manifest_path = self._prepare_registry("producer-drift")
        self.current_producer["commit"] = "b" * 40
        for operation in (
            runtime.runtime_preview,
            runtime.run_runtime,
            runtime.collect_runtime,
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "producer does not match"):
                    operation(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile = Path(manifest["profile"]["absolute_path"])
        execution = profile / manifest["artifacts"]["execution_relative_path"]
        self.assertFalse(execution.exists())

    def test_prepare_retracts_manifest_if_producer_changes_during_publish(
        self,
    ) -> None:
        identities = iter(
            (
                {"commit": PRODUCER_COMMIT, "dirty": False},
                {"commit": PRODUCER_COMMIT, "dirty": False},
                {"commit": "b" * 40, "dirty": False},
            )
        )
        with (
            patch(
                "dcsmizzer.runtime._git_identity",
                side_effect=lambda root: next(identities),
            ),
            self.assertRaisesRegex(ValueError, "changed during publication"),
        ):
            runtime.prepare_runtime(
                self.dcs_root,
                self.saved_games,
                run_id="producer-publish-drift",
                mode="registry-probe",
            )

        manifest = (
            self.saved_games
            / "DCSMizzer-producer-publish-drift"
            / "DCSMizzer"
            / "manifest.json"
        )
        self.assertFalse(manifest.exists())

    def test_cli_entrypoint_does_not_read_or_publish_local_bytecode(self) -> None:
        repository = self.root / "fresh-cli"
        tools = repository / "Tools"
        shutil.copytree(
            TOOLS_ROOT / "dcsmizzer",
            tools / "dcsmizzer",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(TOOLS_ROOT / "dcsmizzer.py", tools / "dcsmizzer.py")
        (repository / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n",
            encoding="utf-8",
        )

        def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        git("add", ".")
        git("commit", "--quiet", "-m", "fixture")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["GIT_ATTR_NOSYSTEM"] = "0"
        environment["GIT_ATTR_SOURCE"] = "refs/heads/does-not-exist"
        completed = subprocess.run(
            [
                sys.executable,
                str(tools / "dcsmizzer.py"),
                "capabilities",
                "--details",
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(list(tools.rglob("__pycache__")), [])
        self.assertEqual(
            git(
                "status",
                "--porcelain=v1",
                "--ignored=matching",
                "--untracked-files=all",
            ).stdout,
            b"",
        )

        gated = subprocess.run(
            [
                sys.executable,
                str(tools / "dcsmizzer.py"),
                "capabilities",
                "--details",
                "--evidence-bundle",
                str(repository / "missing-bundle"),
                "--evidence-current-dcs-root",
                str(repository / "missing-dcs"),
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(gated.returncode, 2)
        self.assertNotIn(b"bootstrap error", gated.stderr.lower())

        (repository / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n# deliberate ordinary-command dirt\n",
            encoding="utf-8",
        )
        terminator_path = subprocess.run(
            [
                sys.executable,
                str(tools / "dcsmizzer.py"),
                "inspect",
                "--",
                "--evidence-bundle=ordinary-file-name",
            ],
            cwd=repository,
            check=False,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(terminator_path.returncode, 2)
        self.assertNotIn(b"bootstrap error", terminator_path.stderr.lower())

    def test_cli_bootstrap_rejects_ignored_import_shadow_before_import(self) -> None:
        repository = self.root / "shadow-cli"
        tools = repository / "Tools"
        shutil.copytree(
            TOOLS_ROOT / "dcsmizzer",
            tools / "dcsmizzer",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(TOOLS_ROOT / "dcsmizzer.py", tools / "dcsmizzer.py")
        (repository / ".gitignore").write_text(
            "__pycache__/\n*.pyc\nTools/json.py\n",
            encoding="utf-8",
        )

        def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=True,
                capture_output=True,
            )

        git("init", "--quiet", "--initial-branch=main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        git("add", ".")
        git("commit", "--quiet", "-m", "fixture")
        marker = repository / "shadow-executed.txt"
        (tools / "json.py").write_text(
            f"open({str(marker)!r}, 'w').write('executed')\n"
            "raise RuntimeError('ignored import shadow executed')\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        entrypoint_tree = ast.parse(
            (TOOLS_ROOT / "dcsmizzer.py").read_text(encoding="utf-8")
        )
        declared: frozenset[str] | None = None
        for statement in entrypoint_tree.body:
            if (
                isinstance(statement, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "_PROVENANCE_COMMANDS"
                    for target in statement.targets
                )
                and isinstance(statement.value, ast.Call)
                and statement.value.args
            ):
                declared = frozenset(ast.literal_eval(statement.value.args[0]))
                break
        self.assertEqual(declared, PROVENANCE_COMMANDS)
        cases = (
            [
                "capabilities",
                "--details",
                "--evidence-bundle",
                str(repository / "missing-bundle"),
                "--evidence-current-dcs-root",
                str(repository / "missing-dcs"),
            ],
            [
                "capabilities",
                f"--evidence-bundle={repository / 'missing-bundle'}",
                "--evidence-current-dcs-root",
                str(repository / "missing-dcs"),
            ],
            ["--", "runtime-prepare"],
            *([command] for command in sorted(PROVENANCE_COMMANDS)),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(tools / "dcsmizzer.py"), *arguments],
                    cwd=repository,
                    check=False,
                    capture_output=True,
                    env=environment,
                )

                self.assertEqual(completed.returncode, 2)
                self.assertIn(b"ignored or untracked", completed.stderr)
                self.assertFalse(marker.exists())
        self.assertEqual(list(tools.rglob("__pycache__")), [])

    def test_prepare_registry_isolated_hash_bound_and_dry_run(self) -> None:
        steam = self.root / "Steam" / "Steam.exe"
        steam.parent.mkdir()
        steam.write_bytes(b"fixture steam launcher")
        (self.dcs_root / "_DCS_Steam").write_text("1\n", encoding="ascii")
        manifest = self.root / "steamapps" / "appmanifest_223750.acf"
        manifest.write_text(
            '"appid" "223750"\n'
            '"StateFlags" "4"\n'
            '"installdir" "DCSWorld"\n'
            f'"LauncherPath" "{str(steam).replace(chr(92), chr(92) * 2)}"\n'
            '"buildid" "24431605"\n',
            encoding="utf-8",
        )
        report = runtime.prepare_runtime(
            self.dcs_root,
            self.saved_games,
            run_id="registry-fixture",
            mode="registry-probe",
        )
        manifest_path = Path(report["manifest"]["absolute_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hook = (
            Path(manifest["profile"]["absolute_path"])
            / manifest["artifacts"]["hook"]["relative_path"]
        )
        preview = runtime.runtime_preview(manifest_path)

        self.assertFalse(report["dcs_started"])
        self.assertEqual(manifest["schema"], runtime.MANIFEST_SCHEMA)
        self.assertEqual(manifest["dcs"]["product_version"], VERSION)
        self.assertEqual(manifest["dcs"]["distribution"], "steam")
        self.assertEqual(manifest["dcs"]["distribution_build"], "24431605")
        self.assertEqual(
            manifest["dcs"]["distribution_manifest"]["semantic_identity"],
            {
                "schema": runtime.STEAM_MANIFEST_IDENTITY_SCHEMA,
                "app_id": "223750",
                "build_id": "24431605",
                "install_dir_casefold": "dcsworld",
                "state_flags": 4,
            },
        )
        self.assertEqual(
            manifest["dcs"]["distribution_manifest"]["verification"],
            {
                "raw_hash_scope": "preparation_observation_only",
                "current_check": "selected_semantic_identity",
            },
        )
        self.assertTrue(manifest["profile"]["isolated"])
        self.assertFalse(manifest["safety"]["unsafe_dostring_enabled"])
        hook_text = hook.read_text(encoding="utf-8")
        self.assertNotIn("@@", hook_text)
        self.assertNotIn("net.dostring_in", hook_text)
        self.assertIn('local MODE = "registry-probe"', hook_text)
        self.assertFalse(preview["validation"]["runtime_started"])
        self.assertEqual(preview["command_preview"][1:4], [
            "-applaunch", "223750", "--server"
        ])
        self.assertEqual(preview["command_preview"][-2:], [
            "-w", "DCSMizzer-registry-fixture"
        ])
        self.assertTrue(
            preview["interaction"][
                "steam_custom_arguments_confirmation_may_be_required"
            ]
        )
        self.assertEqual(preview["interaction"]["confirmation_deadline_seconds"], 120)
        self.assertTrue(
            (Path(manifest["profile"]["absolute_path"]) / "Tracks").is_dir()
        )

    def test_steam_manifest_volatile_metadata_drift_is_allowed(self) -> None:
        manifest_path, prepared = self._prepare_steam("steam-volatile")
        app_manifest = self.root / "steamapps" / "appmanifest_223750.acf"
        original_hash = prepared["dcs"]["distribution_manifest"]["sha256"]
        app_manifest.write_text(
            app_manifest.read_text(encoding="utf-8")
            + '"LastPlayed" "1787736735"\n',
            encoding="utf-8",
        )

        preview = runtime.runtime_preview(manifest_path)

        self.assertTrue(preview["validation"]["inputs_unchanged"])
        self.assertNotEqual(
            original_hash,
            hashlib.sha256(app_manifest.read_bytes()).hexdigest(),
        )

    def test_steam_manifest_semantic_drift_is_rejected(self) -> None:
        cases = (
            ("appid", '"appid" "223750"', '"appid" "999999"', "app or build"),
            (
                "state",
                '"StateFlags" "4"',
                '"StateFlags" "6"',
                "fully installed",
            ),
            (
                "install-dir",
                '"installdir" "DCSWorld"',
                '"installdir" "OtherWorld"',
                "install directory",
            ),
        )
        for index, (label, before, after, message) in enumerate(cases):
            with self.subTest(label=label):
                manifest_path, _manifest = self._prepare_steam(
                    f"steam-semantic-{index}"
                )
                app_manifest = (
                    self.root / "steamapps" / "appmanifest_223750.acf"
                )
                app_manifest.write_text(
                    app_manifest.read_text(encoding="utf-8").replace(
                        before,
                        after,
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, message):
                    runtime.runtime_preview(manifest_path)

    def test_steam_manifest_duplicate_semantic_field_is_rejected(self) -> None:
        manifest_path, _manifest = self._prepare_steam("steam-duplicate")
        app_manifest = self.root / "steamapps" / "appmanifest_223750.acf"
        app_manifest.write_text(
            app_manifest.read_text(encoding="utf-8")
            + '"appid" "223750"\n',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            runtime.runtime_preview(manifest_path)

    def test_prepare_rejects_existing_profile_and_hook_tampering(self) -> None:
        report = runtime.prepare_runtime(
            self.dcs_root,
            self.saved_games,
            run_id="tamper-fixture",
            mode="registry-probe",
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            runtime.prepare_runtime(
                self.dcs_root,
                self.saved_games,
                run_id="tamper-fixture",
                mode="registry-probe",
            )
        manifest_path = Path(report["manifest"]["absolute_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hook = (
            Path(manifest["profile"]["absolute_path"])
            / manifest["artifacts"]["hook"]["relative_path"]
        )
        hook.write_text(hook.read_text(encoding="utf-8") + "-- changed\n")
        with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
            runtime.runtime_preview(manifest_path)

    def test_preview_reconstructs_hook_instead_of_trusting_manifest_hash(self) -> None:
        manifest_path = self._prepare_registry("self-consistent-tamper")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile = Path(manifest["profile"]["absolute_path"])
        hook = profile / manifest["artifacts"]["hook"]["relative_path"]
        payload = hook.read_bytes() + b"-- attacker-controlled change\n"
        hook.write_bytes(payload)
        manifest["artifacts"]["hook"]["size_bytes"] = len(payload)
        manifest["artifacts"]["hook"]["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "trusted rendered product resource"):
            runtime.runtime_preview(manifest_path)

    def test_run_defaults_to_preview_without_launch(self) -> None:
        manifest_path = self._prepare_registry("dry-run")
        called = False

        def forbidden_popen(*args: object, **kwargs: object) -> None:
            nonlocal called
            called = True
            raise AssertionError("process launch was not authorized")

        report = runtime.run_runtime(
            manifest_path,
            _popen=forbidden_popen,  # type: ignore[arg-type]
        )

        self.assertFalse(called)
        self.assertEqual(report["classification"], "authorization_required")
        self.assertFalse(report["validation"]["runtime_authorized"])

    def test_launch_error_and_direct_exit_outcomes_are_classified(self) -> None:
        launch_error_manifest = self._prepare_registry("launch-error")

        def fail_launch(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("simulated missing executable")

        launch_error = runtime.run_runtime(
            launch_error_manifest,
            authorize=True,
            _popen=fail_launch,  # type: ignore[arg-type]
            _running_pids=list,
        )
        self.assertEqual(launch_error["classification"], "process_not_started")
        self.assertFalse(launch_error["dcs_started"])

        for suffix, return_code, expected in (
            ("clean-no-result", 0, "exited_without_result"),
            ("nonzero", 23, "crash_or_nonzero_exit"),
        ):
            with self.subTest(suffix=suffix):
                manifest_path = self._prepare_registry(suffix)
                report = runtime.run_runtime(
                    manifest_path,
                    authorize=True,
                    _popen=lambda *args, code=return_code, **kwargs: _ExitProcess(code),  # type: ignore[arg-type]
                    _running_pids=list,
                )
                self.assertEqual(report["classification"], expected)
                self.assertFalse(report["validation"]["completed"])

    def test_authorized_registry_run_and_collect(self) -> None:
        manifest_path = self._prepare_registry("complete")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result_path = (
            Path(manifest["profile"]["absolute_path"])
            / manifest["artifacts"]["result_relative_path"]
        )

        def completed_process(*args: object, **kwargs: object) -> _CompletedProcess:
            result_path.write_text(
                json.dumps(self._registry_result(manifest["run_id"])),
                encoding="utf-8",
            )
            return _CompletedProcess()

        run = runtime.run_runtime(
            manifest_path,
            authorize=True,
            _popen=completed_process,  # type: ignore[arg-type]
            _running_pids=lambda: [],
        )
        collected = runtime.collect_runtime(manifest_path)

        self.assertEqual(run["classification"], "normal_completion")
        self.assertTrue(run["validation"]["completed"])
        self.assertTrue(collected["validation"]["runtime_valid"])
        self.assertEqual(collected["validation"]["failure_reasons"], [])
        self.assertEqual(collected["producer"], manifest["producer"])
        self.assertEqual(collected["prepared_utc"], manifest["created_utc"])

        execution_file = (
            Path(manifest["profile"]["absolute_path"])
            / manifest["artifacts"]["execution_relative_path"]
        )
        execution = json.loads(execution_file.read_text(encoding="utf-8"))
        execution["manifest_sha256"] = "0" * 64
        execution_file.write_text(json.dumps(execution), encoding="utf-8")
        tampered = runtime.collect_runtime(manifest_path)
        self.assertIn(
            "runtime_execution_manifest_hash_mismatch",
            tampered["validation"]["failure_reasons"],
        )
        self.assertFalse(tampered["validation"]["runtime_valid"])

    def test_steam_launch_binds_the_one_new_dcs_pid(self) -> None:
        steam = self.root / "Steam" / "Steam.exe"
        steam.parent.mkdir()
        steam.write_bytes(b"fixture steam launcher")
        (self.dcs_root / "_DCS_Steam").write_text("1\n", encoding="ascii")
        (self.root / "steamapps" / "appmanifest_223750.acf").write_text(
            '"appid" "223750"\n'
            '"StateFlags" "4"\n'
            '"installdir" "DCSWorld"\n'
            f'"LauncherPath" "{str(steam).replace(chr(92), chr(92) * 2)}"\n'
            '"buildid" "24431605"\n',
            encoding="utf-8",
        )
        manifest_path = self._prepare_registry("steam-run")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile = Path(manifest["profile"]["absolute_path"])
        result_path = profile / manifest["artifacts"]["result_relative_path"]

        def launch(*args: object, **kwargs: object) -> _CompletedProcess:
            result_path.write_text(
                json.dumps(self._registry_result(manifest["run_id"])),
                encoding="utf-8",
            )
            return _CompletedProcess()

        pid_states = iter(([], [9001], []))
        report = runtime.run_runtime(
            manifest_path,
            authorize=True,
            _popen=launch,  # type: ignore[arg-type]
            _running_pids=lambda: next(pid_states),
            _process_identity_func=lambda pid: {
                "pid": pid,
                "executable_path": manifest["dcs"]["executable"][
                    "absolute_path"
                ],
                "command_line": (
                    "DCS.exe --server --norender -w "
                    "DCSMizzer-steam-run"
                ),
            },
            _sleep=lambda value: None,
        )

        self.assertEqual(report["classification"], "normal_completion")
        self.assertEqual(report["process"]["pid"], 9001)
        self.assertEqual(report["process"]["launcher_pid"], 4242)
        self.assertEqual(report["process"]["launcher_kind"], "steam_applaunch")
        self.assertTrue(report["process"]["process_identity_attested"])
        self.assertTrue(report["validation"]["exact_started_process_cleaned_up"])

    def test_steam_rejects_new_process_with_wrong_profile_identity(self) -> None:
        manifest_path, manifest = self._prepare_steam("wrong-steam-process")
        pid_states = iter(([], [9002]))
        report = runtime.run_runtime(
            manifest_path,
            authorize=True,
            _popen=lambda *args, **kwargs: _CompletedProcess(),  # type: ignore[arg-type]
            _running_pids=lambda: next(pid_states),
            _process_identity_func=lambda pid: {
                "pid": pid,
                "executable_path": manifest["dcs"]["executable"][
                    "absolute_path"
                ],
                "command_line": "DCS.exe --server -w DCS",
            },
            _sleep=lambda value: None,
        )

        self.assertEqual(report["classification"], "untrusted_started_process")
        self.assertFalse(report["process"]["process_identity_attested"])
        self.assertFalse(report["validation"]["completed"])

    def test_steam_rejects_ambiguous_new_dcs_processes(self) -> None:
        manifest_path, _manifest = self._prepare_steam("ambiguous-steam-process")
        pid_states = iter(([], [9005, 9006]))
        report = runtime.run_runtime(
            manifest_path,
            authorize=True,
            _popen=lambda *args, **kwargs: _CompletedProcess(),  # type: ignore[arg-type]
            _running_pids=lambda: next(pid_states),
            _process_identity_func=lambda pid: None,
            _sleep=lambda value: None,
        )

        self.assertEqual(report["classification"], "ambiguous_started_process")
        self.assertFalse(report["dcs_started"])
        self.assertFalse(report["validation"]["completed"])

    def test_result_grace_cleans_only_reattested_steam_process(self) -> None:
        manifest_path, manifest = self._prepare_steam("result-cleanup")
        profile = Path(manifest["profile"]["absolute_path"])
        result_path = profile / manifest["artifacts"]["result_relative_path"]
        state = {"running": False, "terminated": [], "killed": []}

        def launch(*args: object, **kwargs: object) -> _CompletedProcess:
            state["running"] = True
            result_path.write_text(
                json.dumps(self._registry_result(manifest["run_id"])),
                encoding="utf-8",
            )
            return _CompletedProcess()

        def terminate(pid: int, force: bool) -> None:
            state["running"] = False
            state["killed" if force else "terminated"].append(pid)

        identity = lambda pid: {  # noqa: E731
            "pid": pid,
            "executable_path": manifest["dcs"]["executable"]["absolute_path"],
            "command_line": (
                "DCS.exe --server --norender -w DCSMizzer-result-cleanup"
            ),
        }
        with patch("dcsmizzer.runtime.RESULT_EXIT_GRACE_SECONDS", 0.0):
            report = runtime.run_runtime(
                manifest_path,
                authorize=True,
                _popen=launch,  # type: ignore[arg-type]
                _running_pids=lambda: [9003] if state["running"] else [],
                _process_identity_func=identity,
                _terminate_pid_func=terminate,
                _sleep=lambda value: None,
            )

        self.assertEqual(report["classification"], "normal_completion")
        self.assertTrue(report["process"]["completion_cleanup_requested"])
        self.assertEqual(state["terminated"], [9003])
        self.assertEqual(state["killed"], [])

    def test_cleanup_refuses_process_after_identity_changes(self) -> None:
        manifest_path, manifest = self._prepare_steam("identity-change")
        profile = Path(manifest["profile"]["absolute_path"])
        result_path = profile / manifest["artifacts"]["result_relative_path"]

        def launch(*args: object, **kwargs: object) -> _CompletedProcess:
            result_path.write_text(
                json.dumps(self._registry_result(manifest["run_id"])),
                encoding="utf-8",
            )
            return _CompletedProcess()

        identities = iter(
            (
                {
                    "pid": 9007,
                    "executable_path": manifest["dcs"]["executable"][
                        "absolute_path"
                    ],
                    "command_line": (
                        "DCS.exe --server --norender -w "
                        "DCSMizzer-identity-change"
                    ),
                },
                {
                    "pid": 9007,
                    "executable_path": str(self.root / "unrelated.exe"),
                    "command_line": "unrelated.exe",
                },
            )
        )
        pid_states = iter(([], [9007], [9007], [9007]))
        with patch("dcsmizzer.runtime.RESULT_EXIT_GRACE_SECONDS", 0.0):
            report = runtime.run_runtime(
                manifest_path,
                authorize=True,
                _popen=launch,  # type: ignore[arg-type]
                _running_pids=lambda: next(pid_states),
                _process_identity_func=lambda pid: next(identities),
                _terminate_pid_func=lambda pid, force: self.fail(
                    "identity-changed process must not be terminated"
                ),
                _sleep=lambda value: None,
            )

        self.assertEqual(report["classification"], "cleanup_identity_lost")
        self.assertFalse(report["validation"]["exact_started_process_cleaned_up"])

    def test_steam_process_attestation_requires_exact_mission_argument(self) -> None:
        manifest = {
            "dcs": {
                "executable": {
                    "absolute_path": str(self.dcs_root / "bin-mt" / "DCS.exe"),
                    "sha256": "a" * 64,
                }
            },
            "profile": {"name": "DCSMizzer-mission"},
            "inputs": {
                "mission": {"absolute_path": str(self.root / "exact mission.miz")}
            },
        }
        base = {
            "pid": 99,
            "executable_path": manifest["dcs"]["executable"]["absolute_path"],
            "command_line": "DCS.exe -w DCSMizzer-mission wrong.miz",
        }
        self.assertIsNone(runtime._attest_steam_process(base, manifest))
        base["command_line"] = (
            'DCS.exe -w "DCSMizzer-mission" '
            f'"{manifest["inputs"]["mission"]["absolute_path"]}.bak"'
        )
        self.assertIsNone(runtime._attest_steam_process(base, manifest))
        base["command_line"] = (
            'DCS.exe -w "DCSMizzer-mission" '
            f'"{manifest["inputs"]["mission"]["absolute_path"]}"'
        )
        attested = runtime._attest_steam_process(base, manifest)
        self.assertIsNotNone(attested)
        self.assertTrue(attested["mission_argument_attested"])

    def test_collect_rejects_mismatched_run_id_and_corrupt_json(self) -> None:
        for suffix, payload, expected in (
            (
                "mismatch",
                json.dumps(self._registry_result("wrong-run")),
                "runtime_result_run_id_mismatch",
            ),
            ("corrupt", "{not json", "not valid JSON"),
        ):
            with self.subTest(suffix=suffix):
                manifest_path = self._prepare_registry(suffix)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                profile = Path(manifest["profile"]["absolute_path"])
                execution = profile / manifest["artifacts"]["execution_relative_path"]
                execution.write_text(
                    json.dumps(
                        {
                            "schema": "dcsmizzer.runtime-execution/v1",
                            "run_id": manifest["run_id"],
                            "classification": "normal_completion",
                            "pid": 1,
                        }
                    ),
                    encoding="utf-8",
                )
                result = profile / manifest["artifacts"]["result_relative_path"]
                result.write_text(payload, encoding="utf-8")
                if suffix == "corrupt":
                    with self.assertRaisesRegex(ValueError, expected):
                        runtime.collect_runtime(manifest_path)
                else:
                    report = runtime.collect_runtime(manifest_path)
                    self.assertIn(expected, report["validation"]["failure_reasons"])

    def test_timeout_terminates_and_kills_only_started_process(self) -> None:
        manifest_path = self._prepare_registry("timeout")
        process = _TimeoutProcess()
        ticks = iter((0.0, 6.0, 6.5))

        report = runtime.run_runtime(
            manifest_path,
            authorize=True,
            timeout_seconds=5,
            terminate_grace_seconds=0.1,
            _popen=lambda *args, **kwargs: process,  # type: ignore[arg-type]
            _clock=lambda: next(ticks),
            _sleep=lambda value: None,
            _running_pids=lambda: [],
        )

        self.assertEqual(report["classification"], "timeout")
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertTrue(
            report["validation"]["exact_started_process_cleaned_up"]
        )

    def test_timeout_reports_cleanup_failure_if_child_survives_kill(self) -> None:
        manifest_path = self._prepare_registry("unstoppable")
        process = _UnstoppableProcess()
        ticks = iter((0.0, 6.0, 7.0))

        report = runtime.run_runtime(
            manifest_path,
            authorize=True,
            timeout_seconds=5,
            terminate_grace_seconds=0.1,
            _popen=lambda *args, **kwargs: process,  # type: ignore[arg-type]
            _clock=lambda: next(ticks),
            _sleep=lambda value: None,
            _running_pids=list,
        )

        self.assertEqual(report["classification"], "cleanup_failed")
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertFalse(
            report["validation"]["exact_started_process_cleaned_up"]
        )

    def test_coordinate_checks_are_bounded_and_rendered_for_mission(self) -> None:
        mission = self.root / "fixture.miz"
        mission.write_bytes(b"PK fixture bytes")
        checks = self.root / "checks.json"
        checks.write_text(
            json.dumps(
                {
                    "schema": runtime.COORDINATE_CHECKS_SCHEMA,
                    "terrain": "SinaiMap",
                    "checks": [
                        {
                            "label": "great-pyramid",
                            "latitude": 29.97915,
                            "longitude": 31.1342194444,
                            "expected_x": -7373.176364,
                            "expected_y": -10781.869447,
                            "tolerance_m": 25,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        archive = SimpleNamespace(valid_zip=True, safe=True, crc_status="passed")
        analysis = SimpleNamespace(
            parse_valid=True,
            theatre="SinaiMap",
            stats=SimpleNamespace(
                groups={"plane": 2},
                units={"plane": 3},
                human_slots={"Player": 1},
            ),
        )
        with (
            patch("dcsmizzer.runtime.inspect_miz", return_value=archive),
            patch("dcsmizzer.runtime.analyse_miz", return_value=analysis),
        ):
            report = runtime.prepare_runtime(
                self.dcs_root,
                self.saved_games,
                run_id="sinai-coordinate",
                mode="mission-smoke",
                mission=mission,
                coordinate_checks=checks,
                smoke_seconds=5,
            )
        manifest = json.loads(
            Path(report["manifest"]["absolute_path"]).read_text(encoding="utf-8")
        )
        profile = Path(manifest["profile"]["absolute_path"])
        hook = profile / manifest["artifacts"]["hook"]["relative_path"]
        hook_text = hook.read_text(encoding="utf-8")

        self.assertEqual(manifest["inputs"]["coordinate_checks"]["checks"], 1)
        self.assertIn("great-pyramid", hook_text)
        self.assertIn("29.97915", hook_text)
        self.assertIn("local EXPECTED_GROUPS = 2", hook_text)
        self.assertEqual(manifest["inputs"]["mission"]["expected_units"], 3)
        self.assertEqual(report["command_preview"][-1], str(mission.resolve()))

    def test_coordinate_checks_reject_wrong_terrain_duplicate_and_nonfinite(
        self,
    ) -> None:
        base = {
            "schema": runtime.COORDINATE_CHECKS_SCHEMA,
            "terrain": "Sinai",
            "checks": [
                {
                    "label": "one",
                    "latitude": 30,
                    "longitude": 31,
                    "expected_x": 0,
                    "expected_y": 0,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            runtime._validate_coordinate_checks(base, expected_theatre="Caucasus")
        duplicate = json.loads(json.dumps(base))
        duplicate["checks"].append(dict(duplicate["checks"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            runtime._validate_coordinate_checks(duplicate, expected_theatre="Sinai")
        nonfinite = json.loads(json.dumps(base))
        nonfinite["checks"][0]["expected_x"] = float("inf")
        with self.assertRaisesRegex(ValueError, "between"):
            runtime._validate_coordinate_checks(nonfinite, expected_theatre="Sinai")

    def test_runtime_coordinate_record_is_recomputed_not_self_attested(self) -> None:
        expected = {
            "label": "great-pyramid",
            "latitude": 29.97915,
            "longitude": 31.1342194444,
            "expected_x": -7373.176364,
            "expected_y": -10781.869447,
            "tolerance_m": 25.0,
        }
        observed = {
            **expected,
            "runtime_x": -7373.126364,
            "runtime_y": -10781.869447,
            "error_m": 0.05,
            "passed": True,
        }
        self.assertTrue(runtime._runtime_coordinate_record_valid(observed, expected))
        observed["runtime_x"] = 100_000.0
        self.assertFalse(runtime._runtime_coordinate_record_valid(observed, expected))
        observed["runtime_x"] = -7363.60
        observed["error_m"] = 0.0
        self.assertFalse(runtime._runtime_coordinate_record_valid(observed, expected))

    def test_rendered_mission_hook_runs_bounded_smoke_in_lua(self) -> None:
        lua = shutil.which("lua55") or shutil.which("lua")
        if lua is None:
            self.skipTest("Lua interpreter is unavailable")
        mission = self.root / "fixture-smoke.miz"
        mission.write_bytes(b"PK fixture bytes")
        checks = self.root / "smoke-checks.json"
        checks.write_text(
            json.dumps(
                {
                    "schema": runtime.COORDINATE_CHECKS_SCHEMA,
                    "terrain": "SinaiMap",
                    "checks": [
                        {
                            "label": "great-pyramid",
                            "latitude": 29.97915,
                            "longitude": 31.1342194444,
                            "expected_x": -7373.176364,
                            "expected_y": -10781.869447,
                            "tolerance_m": 0.1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        analysis = SimpleNamespace(
            parse_valid=True,
            theatre="SinaiMap",
            stats=SimpleNamespace(
                groups={"plane": 2},
                units={"plane": 3},
                human_slots={"Player": 1},
            ),
        )
        with (
            patch(
                "dcsmizzer.runtime.inspect_miz",
                return_value=SimpleNamespace(
                    valid_zip=True,
                    safe=True,
                    crc_status="passed",
                ),
            ),
            patch("dcsmizzer.runtime.analyse_miz", return_value=analysis),
        ):
            prepared = runtime.prepare_runtime(
                self.dcs_root,
                self.saved_games,
                run_id="lua-smoke",
                mode="mission-smoke",
                mission=mission,
                coordinate_checks=checks,
                smoke_seconds=5,
            )
        manifest = json.loads(
            Path(prepared["manifest"]["absolute_path"]).read_text(encoding="utf-8")
        )
        profile = Path(manifest["profile"]["absolute_path"])
        hook = profile / manifest["artifacts"]["hook"]["relative_path"]
        write_root = profile.as_posix() + "/"
        bootstrap = f'''
package.preload["lfs"] = function()
  return {{ writedir = function() return {json.dumps(write_root)} end,
            mkdir = function() return true end }}
end
package.preload["log"] = function()
  return {{ INFO = 1, ERROR = 2, write = function(_, _, message)
    io.stderr:write(message .. "\\n")
  end }}
end
local now = 0
local callbacks = nil
local exited = false
Export = {{
  LoGetVersionInfo = function() return {{ ProductVersion = {{2, 9, 28, 26385}} }} end,
  LoGeoCoordinatesToLoCoordinates = function(longitude, latitude)
    return {{ x = -7373.176364, z = -10781.869447 }}
  end,
}}
Sim = {{
  setUserCallbacks = function(value) callbacks = value end,
  getRealTime = function() return now end,
  getCurrentMission = function()
    return {{ theatre = "SinaiMap", coalition = {{ blue = {{ country = {{
      {{ plane = {{ group = {{
        {{ units = {{ {{}}, {{}} }} }},
        {{ units = {{ {{}} }} }},
      }} }} }}
    }} }} }} }}
  end,
  getMissionName = function() return "fixture" end,
  getMissionFilename = function() return "C:/fixture-smoke.miz" end,
  getAvailableCoalitions = function() return {{ [1] = true }} end,
  getAvailableSlots = function() return {{ [1] = {{}} }} end,
  getMissionResult = function() return 0 end,
  exitProcess = function() exited = true end,
}}
assert(loadfile({json.dumps(hook.as_posix())}))()
assert(callbacks ~= nil)
callbacks.onMissionLoadBegin()
callbacks.onMissionLoadEnd()
callbacks.onSimulationStart()
now = 6
callbacks.onSimulationFrame()
assert(exited)
'''
        completed = subprocess.run(
            [lua, "-e", bootstrap],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result_path = profile / "DCSMizzer" / "runtime-result.json"
        self.assertTrue(
            result_path.is_file(),
            "Lua hook produced no result; stderr=%r stdout=%r files=%r"
            % (
                completed.stderr,
                completed.stdout,
                [str(path.relative_to(profile)) for path in profile.rglob("*")],
            ),
        )
        result = json.loads(
            result_path.read_text(encoding="utf-8")
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mission"]["groups"], 2)
        self.assertEqual(result["mission"]["units"], 3)
        self.assertTrue(result["coordinate_checks_passed"])
        self.assertEqual(runtime._validate_runtime_result(result, manifest), [])

    def _prepare_registry(self, run_id: str) -> Path:
        report = runtime.prepare_runtime(
            self.dcs_root,
            self.saved_games,
            run_id=run_id,
            mode="registry-probe",
        )
        return Path(report["manifest"]["absolute_path"])

    def _prepare_steam(self, run_id: str) -> tuple[Path, dict[str, object]]:
        steam = self.root / "Steam" / "Steam.exe"
        steam.parent.mkdir(exist_ok=True)
        steam.write_bytes(b"fixture steam launcher")
        (self.dcs_root / "_DCS_Steam").write_text("1\n", encoding="ascii")
        (self.root / "steamapps" / "appmanifest_223750.acf").write_text(
            '"appid" "223750"\n'
            '"StateFlags" "4"\n'
            '"installdir" "DCSWorld"\n'
            f'"LauncherPath" "{str(steam).replace(chr(92), chr(92) * 2)}"\n'
            '"buildid" "24431605"\n',
            encoding="utf-8",
        )
        manifest_path = self._prepare_registry(run_id)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest_path, manifest

    @staticmethod
    def _registry_result(run_id: str) -> dict[str, object]:
        return {
            "schema": runtime.RESULT_SCHEMA,
            "run_id": run_id,
            "mode": "registry-probe",
            "status": "ok",
            "dcs": {
                "expected_product_version": VERSION,
                "runtime_product_version": VERSION,
                "runtime_identity_attested": True,
            },
            "registry": {
                "initialized": True,
                "aggregate_only": True,
                "counts": {
                    "countries": 80,
                    "unit_types": 1000,
                    "weapons_by_clsid": 2000,
                    "task_definitions": 40,
                    "planes": 300,
                    "pylon_launcher_edges": 5000,
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
