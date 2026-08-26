from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.report_views import report_summary  # noqa: E402
from dcsmizzer.upstream_cache import (  # noqa: E402
    AcknowledgedUpstream,
    RequiredPath,
)
from dcsmizzer.upstream_promotion import (  # noqa: E402
    _compare_models,
    _parse_name_status,
    upstream_promotion_report,
)


class UpstreamPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.bare = self.root / "source.git"
        self.seed.mkdir()
        self._git("init", "--quiet", "--initial-branch=main", cwd=self.seed)
        self._configure_identity(self.seed)
        (self.seed / "dcs").mkdir()
        (self.seed / "dcs" / "planes.py").write_text(
            "baseline = True\n",
            encoding="utf-8",
        )
        license_payload = b"Fixture license\n"
        (self.seed / "LICENSE").write_bytes(license_payload)
        self._git("add", ".", cwd=self.seed)
        self._git("commit", "--quiet", "-m", "baseline", cwd=self.seed)
        self.commit = self._git_output("rev-parse", "HEAD", cwd=self.seed)
        self.tree = self._git_output("rev-parse", "HEAD^{tree}", cwd=self.seed)
        self._git(
            "clone",
            "--quiet",
            "--bare",
            str(self.seed),
            str(self.bare),
            cwd=self.root,
        )
        self.source = AcknowledgedUpstream(
            name="pydcs",
            remote="https://example.invalid/pydcs.git",
            branch="main",
            commit=self.commit,
            tree=self.tree,
            directory="pydcs",
            license_id="MIT",
            license_path="LICENSE",
            license_sha256=hashlib.sha256(
                license_payload.replace(b"\n", b"\r\n")
            ).hexdigest(),
            required_paths=(RequiredPath("dcs/planes.py", "file"),),
        )
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.baseline = self.cache / self.source.directory
        self._clone(self.baseline)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_same_revision_is_a_private_no_change_audit(self) -> None:
        candidate = self._candidate("candidate-same")
        pycache = candidate / "dcs" / "terrain" / "__pycache__"
        pycache.mkdir(parents=True)
        (candidate / ".git" / "info" / "exclude").write_text(
            "dcs/terrain/__pycache__/\n",
            encoding="utf-8",
        )
        (pycache / "terrain.cpython-fixture.pyc").write_bytes(b"cache")

        report = upstream_promotion_report(
            self.cache,
            candidate,
            "pydcs",
            manifest=(self.source,),
        )

        self.assertTrue(report["validation"]["promotion_audit_passed"])
        self.assertEqual(report["decision"]["recommendation"], "no_revision_change")
        self.assertEqual(report["revision"]["diff"]["changed_path_count"], 0)
        self.assertFalse(report["decision"]["lock_update_authorized"])
        self._assert_private_paths_absent(report)

    def test_irrelevant_fast_forward_retains_pin_without_parser_run(self) -> None:
        candidate = self._candidate("candidate-docs")
        (candidate / "notes.txt").write_text("review\n", encoding="utf-8")
        self._commit(candidate, "irrelevant")

        with patch(
            "dcsmizzer.upstream_promotion._compatibility_snapshot"
        ) as snapshot:
            report = upstream_promotion_report(
                self.cache,
                candidate,
                "pydcs",
                manifest=(self.source,),
            )

        snapshot.assert_not_called()
        self.assertTrue(report["validation"]["promotion_audit_passed"])
        self.assertEqual(
            report["decision"]["recommendation"],
            "retain_pin_consumed_model_unchanged",
        )
        self.assertEqual(report["revision"]["diff"]["changed_path_count"], 1)
        self.assertEqual(
            report["revision"]["diff"]["consumer_changes"]["count"],
            0,
        )

    def test_relevant_fast_forward_runs_both_models_and_requires_regression(
        self,
    ) -> None:
        candidate = self._candidate("candidate-model")
        (candidate / "dcs" / "planes.py").write_text(
            "baseline = False\n",
            encoding="utf-8",
        )
        self._commit(candidate, "model")

        with patch(
            "dcsmizzer.upstream_promotion._compatibility_snapshot",
            side_effect=lambda root, _source, **_kwargs: self._model(
                "a" * 64 if Path(root).name == "pydcs" else "b" * 64
            ),
        ) as snapshot:
            report = upstream_promotion_report(
                self.cache,
                candidate,
                "pydcs",
                manifest=(self.source,),
            )

        self.assertEqual(snapshot.call_count, 4)
        self.assertTrue(report["validation"]["promotion_audit_passed"])
        self.assertEqual(
            report["compatibility"]["comparison"]["changed_components"],
            ["units"],
        )
        self.assertTrue(report["decision"]["repository_regression_required"])
        self.assertEqual(
            report["decision"]["recommendation"],
            "candidate_requires_repository_regression",
        )
        self.assertFalse(report["decision"]["automatic_pin_update"])

    def test_quality_regression_blocks_candidate(self) -> None:
        candidate = self._candidate("candidate-regression")
        (candidate / "dcs" / "planes.py").write_text(
            "baseline = False\n",
            encoding="utf-8",
        )
        self._commit(candidate, "regression")

        def model(root: Path, _source: str, **_kwargs: object) -> dict[str, object]:
            if Path(root).name == "pydcs":
                return self._model("a" * 64, unresolved=0)
            return self._model("b" * 64, unresolved=1)

        with patch(
            "dcsmizzer.upstream_promotion._compatibility_snapshot",
            side_effect=model,
        ):
            report = upstream_promotion_report(
                self.cache,
                candidate,
                "pydcs",
                manifest=(self.source,),
            )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertEqual(report["decision"]["recommendation"], "reject_candidate")
        self.assertIn(
            "candidate_consumer_model_quality_regressed",
            report["failure_reasons"],
        )

    def test_consumer_model_race_fails_closed(self) -> None:
        candidate = self._candidate("candidate-model-race")
        (candidate / "dcs" / "planes.py").write_text(
            "baseline = False\n",
            encoding="utf-8",
        )
        self._commit(candidate, "model race")
        baseline = self._model("a" * 64)
        candidate_first = self._model("b" * 64)
        candidate_second = self._model("c" * 64)

        with patch(
            "dcsmizzer.upstream_promotion._compatibility_snapshot",
            side_effect=(
                baseline,
                candidate_first,
                baseline,
                candidate_second,
            ),
        ):
            report = upstream_promotion_report(
                self.cache,
                candidate,
                "pydcs",
                manifest=(self.source,),
            )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_consumer_model_unstable",
            report["failure_reasons"],
        )

    def test_dirty_and_license_changed_candidates_fail_closed(self) -> None:
        dirty = self._candidate("candidate-dirty")
        (dirty / "dcs" / "planes.py").write_text("dirty = True\n", encoding="utf-8")

        dirty_report = upstream_promotion_report(
            self.cache,
            dirty,
            "pydcs",
            manifest=(self.source,),
        )

        self.assertFalse(dirty_report["validation"]["promotion_audit_passed"])
        self.assertIn("candidate_clean_failed", dirty_report["failure_reasons"])

        relicensed = self._candidate("candidate-license")
        (relicensed / "LICENSE").write_text("Different license\n", encoding="utf-8")
        self._commit(relicensed, "license")
        license_report = upstream_promotion_report(
            self.cache,
            relicensed,
            "pydcs",
            manifest=(self.source,),
        )
        self.assertFalse(license_report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_license_matches_failed",
            license_report["failure_reasons"],
        )

    def test_wrong_remote_and_non_fast_forward_history_fail_closed(self) -> None:
        wrong_remote = self._candidate("candidate-remote")
        self._git(
            "remote",
            "set-url",
            "origin",
            "https://example.invalid/wrong.git",
            cwd=wrong_remote,
        )
        remote_report = upstream_promotion_report(
            self.cache,
            wrong_remote,
            "pydcs",
            manifest=(self.source,),
        )
        self.assertFalse(remote_report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_remote_matches_failed",
            remote_report["failure_reasons"],
        )

        diverged = self._candidate("candidate-diverged")
        self._git("checkout", "--quiet", "--orphan", "diverged", cwd=diverged)
        (diverged / "dcs" / "planes.py").write_text(
            "diverged = True\n",
            encoding="utf-8",
        )
        self._commit(diverged, "diverged")
        self._git("checkout", "--quiet", "--detach", "HEAD", cwd=diverged)
        diverged_report = upstream_promotion_report(
            self.cache,
            diverged,
            "pydcs",
            manifest=(self.source,),
        )
        self.assertFalse(diverged_report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_is_not_fast_forward_from_lock",
            diverged_report["failure_reasons"],
        )

    def test_stability_failure_prevents_promotion_audit_pass(self) -> None:
        candidate = self._candidate("candidate-race")
        unstable = {
            "stable": False,
            "baseline_unchanged": True,
            "candidate_unchanged": False,
            "passes": 2,
            "failure_reasons": ["candidate_changed_during_audit"],
        }

        with patch(
            "dcsmizzer.upstream_promotion._stability_check",
            return_value=unstable,
        ):
            report = upstream_promotion_report(
                self.cache,
                candidate,
                "pydcs",
                manifest=(self.source,),
            )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertFalse(report["validation"]["inputs_stable_across_audit"])
        self.assertIn(
            "candidate_changed_during_audit",
            report["failure_reasons"],
        )

    def test_replace_refs_fail_closed_even_when_the_tree_is_unchanged(self) -> None:
        candidate = self._candidate("candidate-replace")
        replacement = self._git_output(
            "commit-tree",
            self.tree,
            "-m",
            "replacement",
            cwd=candidate,
        )
        self._git(
            "update-ref",
            f"refs/replace/{self.commit}",
            replacement,
            cwd=candidate,
        )

        report = upstream_promotion_report(
            self.cache,
            candidate,
            "pydcs",
            manifest=(self.source,),
        )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_repository_replace_refs_absent_failed",
            report["failure_reasons"],
        )

    def test_ignored_consumer_input_fails_closed(self) -> None:
        candidate = self._candidate("candidate-ignored")
        terrain = candidate / "dcs" / "terrain"
        terrain.mkdir()
        (candidate / ".git" / "info" / "exclude").write_text(
            "dcs/terrain/rogue.py\n",
            encoding="utf-8",
        )
        (terrain / "rogue.py").write_text(
            "hidden = True\n",
            encoding="utf-8",
        )

        report = upstream_promotion_report(
            self.cache,
            candidate,
            "pydcs",
            manifest=(self.source,),
        )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_consumer_ignored_inputs_may_affect_model",
            report["failure_reasons"],
        )

    def test_assume_unchanged_consumer_input_fails_closed(self) -> None:
        candidate = self._candidate("candidate-assume-unchanged")
        self._git(
            "update-index",
            "--assume-unchanged",
            "dcs/planes.py",
            cwd=candidate,
        )
        (candidate / "dcs" / "planes.py").write_text(
            "hidden = True\n",
            encoding="utf-8",
        )

        report = upstream_promotion_report(
            self.cache,
            candidate,
            "pydcs",
            manifest=(self.source,),
        )

        self.assertFalse(report["validation"]["promotion_audit_passed"])
        self.assertIn(
            "candidate_consumer_index_flags_are_not_safe",
            report["failure_reasons"],
        )

    def test_name_status_parser_rejects_renames_and_unsafe_paths(self) -> None:
        self.assertEqual(
            _parse_name_status(b"M\0dcs/planes.py\0A\0notes.txt\0"),
            [
                {"status": "M", "path": "dcs/planes.py"},
                {"status": "A", "path": "notes.txt"},
            ],
        )
        for payload in (
            b"R100\0old\0new\0",
            b"M\0../escape\0",
            b"M\0line\nfeed\0",
            b"M\0incomplete",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                _parse_name_status(payload)

    def test_model_comparison_separates_metadata_from_consumed_data(self) -> None:
        baseline = {
            **self._model("a" * 64),
            "component_sha256": {
                "airbases": "1" * 64,
                "project_version": "2" * 64,
            },
        }
        metadata = {
            **self._model("b" * 64),
            "component_sha256": {
                "airbases": "1" * 64,
                "project_version": "3" * 64,
            },
        }
        data = {
            **metadata,
            "component_sha256": {
                "airbases": "4" * 64,
                "project_version": "3" * 64,
            },
        }

        metadata_comparison = _compare_models(baseline, metadata)
        data_comparison = _compare_models(baseline, data)

        self.assertTrue(metadata_comparison["model_changed"])
        self.assertFalse(metadata_comparison["data_model_changed"])
        self.assertTrue(data_comparison["data_model_changed"])

    def test_cli_uses_audit_gate_and_requires_explicit_roots(self) -> None:
        passing = {
            "schema": "dcsmizzer.upstream-promotion-audit/v1",
            "validation": {"promotion_audit_passed": True},
        }
        output = io.StringIO()
        with patch(
            "dcsmizzer.cli.upstream_promotion_report",
            return_value=passing,
        ) as audit:
            exit_code = main(
                [
                    "upstream-promotion-audit",
                    "--cache-root",
                    "cache",
                    "--candidate-root",
                    "candidate",
                    "--source",
                    "pydcs",
                ],
                stdout=output,
                stderr=io.StringIO(),
            )

        self.assertEqual(exit_code, 0)
        audit.assert_called_once_with(Path("cache"), Path("candidate"), "pydcs")
        self.assertEqual(json.loads(output.getvalue()), passing)
        error = io.StringIO()
        self.assertEqual(
            main(
                ["upstream-promotion-audit", "--source", "pydcs"],
                stdout=io.StringIO(),
                stderr=error,
            ),
            2,
        )
        self.assertIn("--cache-root", error.getvalue())

    def test_saved_audit_has_a_schema_specific_bounded_summary(self) -> None:
        path = self.root / "audit.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "dcsmizzer.upstream-promotion-audit/v1",
                    "validation": {"promotion_audit_passed": True},
                    "failure_reasons": [],
                    "decision": {"recommendation": "no_revision_change"},
                }
            ),
            encoding="utf-8",
        )

        summary = report_summary(path)

        self.assertEqual(
            summary["reported_status"],
            {
                "passed": True,
                "basis": "promotion_audit_passed",
                "runtime_valid": None,
            },
        )

    def _candidate(self, name: str) -> Path:
        candidate = self.root / name
        self._clone(candidate)
        self._configure_identity(candidate)
        return candidate

    def _clone(self, target: Path) -> None:
        self._git("clone", "--quiet", str(self.bare), str(target), cwd=self.root)
        self._git(
            "remote",
            "set-url",
            "origin",
            self.source.remote if hasattr(self, "source") else "https://example.invalid/pydcs.git",
            cwd=target,
        )

    def _commit(self, root: Path, message: str) -> None:
        self._git("add", ".", cwd=root)
        self._git("commit", "--quiet", "-m", message, cwd=root)

    def _configure_identity(self, root: Path) -> None:
        self._git("config", "user.email", "fixture@example.invalid", cwd=root)
        self._git("config", "user.name", "Fixture", cwd=root)

    def _git(self, *arguments: str, cwd: Path) -> None:
        subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )

    def _git_output(self, *arguments: str, cwd: Path) -> str:
        result = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return result.stdout.strip()

    def _model(self, fingerprint: str, *, unresolved: int = 0) -> dict[str, object]:
        return {
            "schema": "dcsmizzer.pydcs-consumer-model/v1",
            "complete": True,
            "fingerprint_sha256": fingerprint,
            "component_sha256": {"units": fingerprint},
            "summary": {"units_total": 1},
            "quality": {"unresolved_pylon_assignments": unresolved},
        }

    def _assert_private_paths_absent(self, report: dict[str, object]) -> None:
        rendered = json.dumps(report)
        for value in (self.root, self.cache, self.baseline):
            private = str(value)
            self.assertNotIn(private, rendered)
            self.assertNotIn(private.replace("\\", "\\\\"), rendered)


if __name__ == "__main__":
    unittest.main()
