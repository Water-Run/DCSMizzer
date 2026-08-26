"""Isolated, version-bound DCS runtime preparation, execution, and collection."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .archive import inspect_miz
from .dcs_static import _windows_product_version
from .mission import analyse_miz


MANIFEST_SCHEMA = "dcsmizzer.evidence-manifest/v1"
RESULT_SCHEMA = "dcsmizzer.runtime-result/v1"
COORDINATE_CHECKS_SCHEMA = "dcsmizzer.runtime-coordinate-checks/v1"
STEAM_MANIFEST_IDENTITY_SCHEMA = "dcsmizzer.steam-app-identity/v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_COORDINATE_CHECKS_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_MISSION_BYTES = 512 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_LOG_HASH_BYTES = 512 * 1024 * 1024
MAX_COORDINATE_CHECKS = 100
MIN_SMOKE_SECONDS = 1.0
MAX_SMOKE_SECONDS = 600.0
MIN_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 7200.0
RESULT_EXIT_GRACE_SECONDS = 10.0
PROFILE_PREFIX = "DCSMizzer-"
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_MODES = frozenset({"registry-probe", "mission-smoke"})


def prepare_runtime(
    dcs_root: Path,
    saved_games_root: Path,
    *,
    run_id: str,
    mode: str,
    mission: Path | None = None,
    coordinate_checks: Path | None = None,
    smoke_seconds: float = 10.0,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Create one new disposable DCS profile and its immutable run manifest."""

    run_id_value = _validate_run_id(run_id)
    if mode not in _MODES:
        raise ValueError("runtime mode must be registry-probe or mission-smoke")
    smoke_value = _bounded_number(
        smoke_seconds,
        "smoke_seconds",
        MIN_SMOKE_SECONDS,
        MAX_SMOKE_SECONDS,
    )
    dcs_root_value = _existing_directory(Path(dcs_root), "DCS root")
    saved_games_value = _existing_directory(
        Path(saved_games_root),
        "Saved Games root",
    )
    distribution, distribution_build, distribution_launcher = (
        _distribution_identity(dcs_root_value)
    )
    executable = _select_dcs_executable(
        dcs_root_value,
        prefer_steam_target=distribution == "steam",
    )
    product_version = _windows_product_version(executable)
    if not product_version:
        raise ValueError("DCS executable product version is unavailable")

    mission_record: dict[str, Any] | None = None
    mission_path: Path | None = None
    expected_theatre: str | None = None
    expected_groups = 0
    expected_units = 0
    expected_player_slots = 0
    if mode == "mission-smoke":
        if mission is None:
            raise ValueError("mission-smoke requires --mission")
        mission_path = _existing_regular_file(
            Path(mission),
            "mission",
            maximum_bytes=MAX_MISSION_BYTES,
        )
        archive = inspect_miz(mission_path)
        analysis = analyse_miz(mission_path)
        if not archive.valid_zip or not archive.safe or archive.crc_status != "passed":
            raise ValueError("mission archive did not pass ZIP safety and CRC checks")
        if not analysis.parse_valid or not analysis.theatre:
            raise ValueError("mission core tables could not be parsed")
        expected_theatre = analysis.theatre
        expected_groups = sum(analysis.stats.groups.values())
        expected_units = sum(analysis.stats.units.values())
        expected_player_slots = sum(analysis.stats.human_slots.values())
        mission_record = {
            "absolute_path": str(mission_path),
            "name": mission_path.name,
            "size_bytes": mission_path.stat().st_size,
            "sha256": _sha256_file(mission_path, MAX_MISSION_BYTES),
            "archive_valid": True,
            "parse_valid": True,
            "theatre": expected_theatre,
            "expected_groups": expected_groups,
            "expected_units": expected_units,
            "expected_player_slots": expected_player_slots,
        }
    elif mission is not None:
        raise ValueError("registry-probe does not accept a mission")

    coordinate_records: list[dict[str, Any]] = []
    coordinate_source: dict[str, Any] | None = None
    if coordinate_checks is not None:
        if mode != "mission-smoke":
            raise ValueError("coordinate checks require mission-smoke mode")
        coordinate_path = _existing_regular_file(
            Path(coordinate_checks),
            "coordinate checks",
            maximum_bytes=MAX_COORDINATE_CHECKS_BYTES,
        )
        coordinate_data, coordinate_payload = _load_json_file(
            coordinate_path,
            MAX_COORDINATE_CHECKS_BYTES,
            "coordinate checks",
        )
        coordinate_records = _validate_coordinate_checks(
            coordinate_data,
            expected_theatre=expected_theatre,
        )
        coordinate_source = {
            "schema": COORDINATE_CHECKS_SCHEMA,
            "name": coordinate_path.name,
            "sha256": hashlib.sha256(coordinate_payload).hexdigest(),
            "checks": len(coordinate_records),
            "terrain": coordinate_data["terrain"],
            "records": coordinate_records,
        }

    profile_name = PROFILE_PREFIX + run_id_value
    profile_root = saved_games_value / profile_name
    if profile_root.exists() or profile_root.is_symlink():
        raise ValueError("disposable runtime profile already exists")
    if profile_root.parent.resolve() != saved_games_value.resolve():
        raise ValueError("runtime profile escaped the Saved Games root")

    product_root = profile_root / "DCSMizzer"
    hooks_root = profile_root / "Scripts" / "Hooks"
    hooks_root.mkdir(parents=True)
    product_root.mkdir()
    # A headless DCS run still tries to create its temporary track.  Seed the
    # otherwise-empty disposable profile so that this unrelated write does not
    # add a false runtime error to the evidence log.
    (profile_root / "Tracks").mkdir()
    hook_path = hooks_root / "DCSMizzerRuntime.lua"
    result_path = product_root / "runtime-result.json"
    execution_path = product_root / "execution.json"

    hook_template = _runtime_hook_template()
    rendered_hook = _render_runtime_hook(
        hook_template,
        run_id=run_id_value,
        mode=mode,
        product_version=product_version,
        mission_name=mission_path.name if mission_path is not None else "",
        theatre=expected_theatre or "",
        smoke_seconds=smoke_value if mode == "mission-smoke" else 10.0,
        coordinate_checks=coordinate_records,
        expected_groups=expected_groups,
        expected_units=expected_units,
        expected_player_slots=expected_player_slots,
    ).encode("utf-8")
    _write_new_file(hook_path, rendered_hook)

    repository = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    source_api = dcs_root_value / "API" / "Sim_ControlAPI.md"
    source_api_record = _optional_source_record(source_api, dcs_root_value)
    distribution_manifest_record = (
        _steam_app_manifest_record(
            dcs_root_value.parent.parent / "appmanifest_223750.acf",
            dcs_root_value.parent.parent,
            expected_build=distribution_build,
            expected_install_dir=dcs_root_value.name,
        )
        if distribution == "steam"
        else None
    )
    git = _git_identity(repository)
    created = _utc_now()
    launcher_record: dict[str, Any] | None = None
    if distribution == "steam":
        if distribution_launcher is None:
            raise ValueError("Steam DCS installation has no usable launcher path")
        launcher = _existing_regular_file(
            distribution_launcher,
            "Steam launcher",
            maximum_bytes=MAX_MISSION_BYTES,
        )
        launcher_record = {
            "absolute_path": str(launcher),
            "size_bytes": launcher.stat().st_size,
            "sha256": _sha256_file(launcher, MAX_MISSION_BYTES),
        }
        command = [
            str(launcher),
            "-applaunch",
            "223750",
            "--server",
            "--norender",
            "-w",
            profile_name,
        ]
        working_directory = launcher.parent
    else:
        command = [
            str(executable),
            "--server",
            "--norender",
            "-w",
            profile_name,
        ]
        working_directory = dcs_root_value
    if mission_path is not None:
        command.append(str(mission_path))

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "run_id": run_id_value,
        "created_utc": created,
        "mode": mode,
        "producer": {
            "name": "DCSMizzer",
            "version": __version__,
            "git_commit": git["commit"],
            "git_dirty": git["dirty"],
        },
        "dcs": {
            "distribution": distribution,
            "distribution_build": distribution_build,
            "distribution_manifest": distribution_manifest_record,
            "distribution_launcher": launcher_record,
            "product_version": product_version,
            "executable": {
                "absolute_path": str(executable),
                "relative_path": executable.relative_to(dcs_root_value).as_posix(),
                "size_bytes": executable.stat().st_size,
                "sha256": _sha256_file(executable, MAX_MISSION_BYTES),
            },
            "sim_control_api": source_api_record,
        },
        "profile": {
            "name": profile_name,
            "absolute_path": str(profile_root),
            "ordinary_profile": False,
            "isolated": True,
        },
        "inputs": {
            "mission": mission_record,
            "coordinate_checks": coordinate_source,
            "smoke_seconds": smoke_value if mode == "mission-smoke" else None,
        },
        "artifacts": {
            "hook": {
                "relative_path": hook_path.relative_to(profile_root).as_posix(),
                "size_bytes": len(rendered_hook),
                "sha256": hashlib.sha256(rendered_hook).hexdigest(),
                "template_sha256": hashlib.sha256(hook_template).hexdigest(),
            },
            "result_relative_path": result_path.relative_to(profile_root).as_posix(),
            "execution_relative_path": execution_path.relative_to(
                profile_root
            ).as_posix(),
        },
        "command": {
            "argv": command,
            "working_directory": str(working_directory),
            "launcher_kind": "steam_applaunch" if distribution == "steam" else "direct",
            "steam_custom_arguments_confirmation_may_be_required": (
                distribution == "steam"
            ),
            "dry_run_default": True,
            "authorization_flag_required": True,
        },
        "safety": {
            "writes_to_dcs_installation": False,
            "writes_to_ordinary_saved_games_profiles": False,
            "unsafe_dostring_enabled": False,
            "mission_scripting_desanitized": False,
            "cleanup_scope": "exact_process_started_by_runtime-run",
        },
    }
    manifest_payload = _json_bytes(manifest)
    if len(manifest_payload) > MAX_MANIFEST_BYTES:
        raise ValueError("runtime manifest exceeds the byte limit")
    manifest_path = product_root / "manifest.json"
    _write_new_file(manifest_path, manifest_payload)
    return {
        "schema": "dcsmizzer.runtime-preparation/v1",
        "run_id": run_id_value,
        "mode": mode,
        "dcs_started": False,
        "profile": {
            "name": profile_name,
            "absolute_path": str(profile_root),
        },
        "manifest": {
            "absolute_path": str(manifest_path),
            "sha256": hashlib.sha256(manifest_payload).hexdigest(),
        },
        "command_preview": command,
        "interaction": {
            "steam_custom_arguments_confirmation_may_be_required": (
                distribution == "steam"
            ),
            "confirmation_deadline_seconds": 120 if distribution == "steam" else None,
        },
        "validation": {
            "profile_isolated": True,
            "manifest_valid": True,
            "hook_hash_bound": True,
            "mission_hash_bound": mission_record is not None,
            "runtime_authorized": False,
            "runtime_started": False,
        },
    }


def runtime_preview(manifest_path: Path) -> dict[str, Any]:
    """Validate a prepared run and return its exact non-executing command."""

    manifest, manifest_payload, paths = _load_and_verify_manifest(manifest_path)
    return {
        "schema": "dcsmizzer.runtime-preview/v1",
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "dcs_started": False,
        "manifest": {
            "name": Path(manifest_path).name,
            "sha256": hashlib.sha256(manifest_payload).hexdigest(),
        },
        "profile": manifest["profile"],
        "command_preview": manifest["command"]["argv"],
        "interaction": {
            "steam_custom_arguments_confirmation_may_be_required": manifest[
                "command"
            ].get("steam_custom_arguments_confirmation_may_be_required", False),
            "confirmation_deadline_seconds": (
                120
                if manifest["command"]["launcher_kind"] == "steam_applaunch"
                else None
            ),
        },
        "validation": {
            "manifest_valid": True,
            "inputs_unchanged": True,
            "hook_unchanged": True,
            "result_absent": not paths["result"].exists(),
            "runtime_authorized": False,
            "runtime_started": False,
        },
    }


def run_runtime(
    manifest_path: Path,
    *,
    authorize: bool = False,
    timeout_seconds: float = 600.0,
    terminate_grace_seconds: float = 15.0,
    _popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    _clock: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], None] = time.sleep,
    _running_pids: Callable[[], list[int]] | None = None,
    _process_identity_func: Callable[[int], dict[str, Any] | None] | None = None,
    _terminate_pid_func: Callable[[int, bool], None] | None = None,
) -> dict[str, Any]:
    """Launch exactly one prepared DCS process, or preview when unauthorized."""

    timeout = _bounded_number(
        timeout_seconds,
        "timeout_seconds",
        MIN_TIMEOUT_SECONDS,
        MAX_TIMEOUT_SECONDS,
    )
    grace = _bounded_number(
        terminate_grace_seconds,
        "terminate_grace_seconds",
        0.1,
        120.0,
    )
    manifest, manifest_payload, paths = _load_and_verify_manifest(manifest_path)
    if not authorize:
        preview = runtime_preview(manifest_path)
        preview["schema"] = "dcsmizzer.runtime-run/v1"
        preview["classification"] = "authorization_required"
        preview["validation"]["completed"] = False
        return preview
    if paths["result"].exists() or paths["execution"].exists():
        raise ValueError("prepared runtime has already produced run artifacts")
    pid_query = _running_pids or _running_dcs_pids
    existing_pids = pid_query()
    if existing_pids:
        raise ValueError("another DCS process is already running")

    started_utc = _utc_now()
    start = _clock()
    process: subprocess.Popen[Any] | None = None
    dcs_pid: int | None = None
    timed_out = False
    terminated = False
    killed = False
    return_code: int | None = None
    launcher_return_code: int | None = None
    launch_error: str | None = None
    dcs_exit_observed = False
    ambiguous_new_pids: list[int] = []
    unattested_new_pids: list[int] = []
    untrusted_new_pids: list[int] = []
    process_attestation: dict[str, Any] | None = None
    completion_cleanup_requested = False
    cleanup_identity_lost = False
    cleanup_failed = False
    launcher_kind = manifest["command"]["launcher_kind"]
    stdout_path = paths["product_root"] / "process-stdout.log"
    stderr_path = paths["product_root"] / "process-stderr.log"
    stdout_handle = stdout_path.open("xb")
    stderr_handle = stderr_path.open("xb")
    try:
        try:
            process = _popen(
                manifest["command"]["argv"],
                cwd=manifest["command"]["working_directory"],
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
        except OSError as error:
            launch_error = type(error).__name__
        if process is not None and launcher_kind == "direct":
            dcs_pid = process.pid
            process_attestation = _direct_process_attestation(manifest, dcs_pid)
            while True:
                return_code = process.poll()
                if return_code is not None:
                    break
                if _clock() - start >= timeout:
                    timed_out = True
                    try:
                        process.terminate()
                        terminated = True
                        try:
                            return_code = process.wait(timeout=grace)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            killed = True
                            try:
                                return_code = process.wait(timeout=grace)
                            except subprocess.TimeoutExpired:
                                cleanup_failed = True
                    except OSError:
                        cleanup_failed = True
                    break
                _sleep(0.25)
            dcs_exit_observed = return_code is not None
        elif process is not None:
            startup_limit = min(timeout, 120.0)
            known = set(existing_pids)
            terminate_pid = _terminate_pid_func or _terminate_dcs_pid
            identity_query = _process_identity_func or _windows_process_identity
            result_seen_at: float | None = None

            def cleanup_bound_process() -> None:
                nonlocal terminated, killed, dcs_exit_observed
                nonlocal cleanup_identity_lost, cleanup_failed
                if dcs_pid is None:
                    cleanup_failed = True
                    return
                current_before = set(pid_query())
                if dcs_pid not in current_before:
                    dcs_exit_observed = True
                    return
                refreshed = identity_query(dcs_pid)
                if _attest_steam_process(refreshed, manifest) is None:
                    cleanup_identity_lost = True
                    return
                try:
                    terminate_pid(dcs_pid, False)
                except (OSError, ValueError):
                    cleanup_failed = True
                    return
                terminated = True
                grace_start = _clock()
                while (
                    dcs_pid in set(pid_query())
                    and _clock() - grace_start < grace
                ):
                    _sleep(0.25)
                if dcs_pid in set(pid_query()):
                    refreshed = identity_query(dcs_pid)
                    if _attest_steam_process(refreshed, manifest) is None:
                        cleanup_identity_lost = True
                        return
                    try:
                        terminate_pid(dcs_pid, True)
                    except (OSError, ValueError):
                        cleanup_failed = True
                        return
                    killed = True
                dcs_exit_observed = dcs_pid not in set(pid_query())

            while True:
                launcher_return_code = process.poll()
                current = set(pid_query())
                if dcs_pid is None:
                    new_pids = sorted(current - known)
                    if len(new_pids) == 1:
                        candidate_pid = new_pids[0]
                        candidate_identity = identity_query(candidate_pid)
                        if candidate_identity is None:
                            unattested_new_pids = new_pids
                        else:
                            candidate_attestation = _attest_steam_process(
                                candidate_identity,
                                manifest,
                            )
                            if candidate_attestation is None:
                                untrusted_new_pids = new_pids
                                break
                            dcs_pid = candidate_pid
                            process_attestation = candidate_attestation
                            unattested_new_pids = []
                    elif len(new_pids) > 1:
                        ambiguous_new_pids = new_pids
                        break
                elif dcs_pid not in current:
                    dcs_exit_observed = True
                    break
                elapsed_now = _clock() - start
                if dcs_pid is not None and paths["result"].is_file():
                    if result_seen_at is None:
                        result_seen_at = _clock()
                    elif _clock() - result_seen_at >= RESULT_EXIT_GRACE_SECONDS:
                        completion_cleanup_requested = True
                        cleanup_bound_process()
                        break
                if elapsed_now >= timeout:
                    timed_out = True
                    if dcs_pid is not None:
                        cleanup_bound_process()
                    break
                if dcs_pid is None and elapsed_now >= startup_limit:
                    break
                _sleep(0.5)
    finally:
        stdout_handle.close()
        stderr_handle.close()

    elapsed = max(0.0, _clock() - start)
    result_exists = paths["result"].is_file()
    runtime_started = dcs_pid is not None
    if launch_error is not None:
        classification = "process_not_started"
    elif ambiguous_new_pids:
        classification = "ambiguous_started_process"
    elif untrusted_new_pids:
        classification = "untrusted_started_process"
    elif cleanup_identity_lost:
        classification = "cleanup_identity_lost"
    elif cleanup_failed:
        classification = "cleanup_failed"
    elif timed_out:
        classification = "timeout"
    elif result_exists and (
        (launcher_kind == "direct" and return_code == 0)
        or (launcher_kind == "steam_applaunch" and dcs_exit_observed)
    ):
        classification = "normal_completion"
    elif launcher_kind == "direct" and return_code not in (None, 0):
        classification = "crash_or_nonzero_exit"
    elif runtime_started and dcs_exit_observed:
        classification = "exited_without_result"
    elif not runtime_started:
        classification = (
            "steam_confirmation_or_startup_pending"
            if launcher_kind == "steam_applaunch" and launcher_return_code == 0
            else "process_not_started"
        )
    else:
        classification = "unknown_process_outcome"
    execution = {
        "schema": "dcsmizzer.runtime-execution/v1",
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "started_utc": started_utc,
        "finished_utc": _utc_now(),
        "elapsed_seconds": elapsed,
        "pid": dcs_pid,
        "launcher_pid": process.pid if process is not None else None,
        "launcher_kind": launcher_kind,
        "launcher_return_code": launcher_return_code,
        "return_code": return_code,
        "classification": classification,
        "timed_out": timed_out,
        "terminated": terminated,
        "killed": killed,
        "launch_error_type": launch_error,
        "ambiguous_new_dcs_pids": ambiguous_new_pids,
        "unattested_new_dcs_pids": unattested_new_pids,
        "untrusted_new_dcs_pids": untrusted_new_pids,
        "process_attestation": process_attestation,
        "completion_cleanup_requested": completion_cleanup_requested,
        "cleanup_identity_lost": cleanup_identity_lost,
        "cleanup_failed": cleanup_failed,
        "dcs_exit_observed": dcs_exit_observed,
        "result_exists": result_exists,
        "stdout": _file_record_if_present(stdout_path),
        "stderr": _file_record_if_present(stderr_path),
    }
    execution_payload = _json_bytes(execution)
    _write_new_file(paths["execution"], execution_payload)
    completed = classification == "normal_completion"
    return {
        "schema": "dcsmizzer.runtime-run/v1",
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "dcs_started": runtime_started,
        "classification": classification,
        "process": {
            "pid": dcs_pid,
            "launcher_pid": process.pid if process is not None else None,
            "launcher_kind": launcher_kind,
            "launcher_return_code": launcher_return_code,
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "timed_out": timed_out,
            "terminated": terminated,
            "killed": killed,
            "completion_cleanup_requested": completion_cleanup_requested,
            "cleanup_failed": cleanup_failed,
            "process_identity_attested": (
                process_attestation is not None
                and process_attestation.get("attested") is True
            ),
        },
        "artifacts": {
            "execution": _file_record_if_present(paths["execution"]),
            "result": _file_record_if_present(paths["result"]),
        },
        "validation": {
            "manifest_valid": True,
            "inputs_unchanged": True,
            "hook_unchanged": True,
            "runtime_authorized": True,
            "runtime_started": runtime_started,
            "exact_started_process_cleaned_up": (
                not runtime_started or dcs_exit_observed
            ),
            "completed": completed,
        },
    }


def collect_runtime(manifest_path: Path) -> dict[str, Any]:
    """Validate and bind the exact runtime result for one prepared run."""

    manifest, manifest_payload, paths = _load_and_verify_manifest(manifest_path)
    if not paths["execution"].is_file():
        raise ValueError("runtime execution record is missing")
    execution, execution_payload = _load_json_file(
        paths["execution"],
        MAX_RESULT_BYTES,
        "runtime execution",
    )
    if execution.get("schema") != "dcsmizzer.runtime-execution/v1":
        raise ValueError("runtime execution schema is not supported")
    if execution.get("run_id") != manifest["run_id"]:
        raise ValueError("runtime execution run ID does not match")
    if not paths["result"].is_file():
        return _collection_report(
            manifest,
            manifest_payload,
            execution,
            execution_payload,
            result=None,
            result_payload=None,
            paths=paths,
            failure_reasons=["runtime_result_missing"],
        )
    result, result_payload = _load_json_file(
        paths["result"],
        MAX_RESULT_BYTES,
        "runtime result",
    )
    failure_reasons = _validate_runtime_result(result, manifest)
    return _collection_report(
        manifest,
        manifest_payload,
        execution,
        execution_payload,
        result=result,
        result_payload=result_payload,
        paths=paths,
        failure_reasons=failure_reasons,
    )


def _collection_report(
    manifest: dict[str, Any],
    manifest_payload: bytes,
    execution: dict[str, Any],
    execution_payload: bytes,
    *,
    result: dict[str, Any] | None,
    result_payload: bytes | None,
    paths: dict[str, Path],
    failure_reasons: list[str],
) -> dict[str, Any]:
    expected_manifest_hash = hashlib.sha256(manifest_payload).hexdigest()
    if execution.get("manifest_sha256") != expected_manifest_hash:
        failure_reasons.append("runtime_execution_manifest_hash_mismatch")
    if execution.get("mode") != manifest["mode"]:
        failure_reasons.append("runtime_execution_mode_mismatch")
    if execution.get("classification") != "normal_completion":
        failure_reasons.append("runtime_execution_not_normal")
    if execution.get("result_exists") is not (result is not None):
        failure_reasons.append("runtime_execution_result_presence_mismatch")
    if execution.get("dcs_exit_observed") is not True:
        failure_reasons.append("runtime_process_exit_not_observed")
    elapsed = execution.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or elapsed < 0
    ):
        failure_reasons.append("runtime_execution_elapsed_invalid")
    attestation = execution.get("process_attestation")
    if not isinstance(attestation, dict) or attestation.get("attested") is not True:
        failure_reasons.append("runtime_process_identity_not_attested")
    else:
        if attestation.get("pid") != execution.get("pid"):
            failure_reasons.append("runtime_process_pid_mismatch")
        if (
            attestation.get("executable_sha256")
            != manifest["dcs"]["executable"]["sha256"]
        ):
            failure_reasons.append("runtime_process_executable_hash_mismatch")
        if attestation.get("profile_argument_attested") is not True:
            failure_reasons.append("runtime_process_profile_not_attested")
        if manifest["inputs"]["mission"] is not None and (
            attestation.get("mission_argument_attested") is not True
        ):
            failure_reasons.append("runtime_process_mission_not_attested")
    log_path = paths["profile_root"] / "Logs" / "dcs.log"
    log_record = _file_record_if_present(log_path, maximum_bytes=MAX_LOG_HASH_BYTES)
    valid = not failure_reasons
    return {
        "schema": "dcsmizzer.runtime-collection/v1",
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "authority": "run_id_and_content_hash_bound_dcs_runtime_result",
        "dcs_started": execution.get("pid") is not None,
        "prepared_utc": manifest["created_utc"],
        "producer": manifest["producer"],
        "evidence": {
            "manifest_sha256": expected_manifest_hash,
            "execution_sha256": hashlib.sha256(execution_payload).hexdigest(),
            "result_sha256": (
                hashlib.sha256(result_payload).hexdigest()
                if result_payload is not None
                else None
            ),
            "dcs_log": log_record,
            "dcs": manifest["dcs"],
            "mission": manifest["inputs"]["mission"],
        },
        "execution": execution,
        "result": result,
        "validation": {
            "manifest_valid": True,
            "inputs_unchanged": True,
            "hook_unchanged": True,
            "execution_bound": True,
            "result_present": result is not None,
            "run_id_matched": result is not None
            and result.get("run_id") == manifest["run_id"],
            "mode_matched": result is not None
            and result.get("mode") == manifest["mode"],
            "runtime_version_matched": result is not None
            and result.get("dcs", {}).get("runtime_product_version")
            == manifest["dcs"]["product_version"],
            "failure_reasons": sorted(set(failure_reasons)),
            "runtime_valid": valid,
        },
        "limitations": [
            "Runtime validity is bound only to this exact DCS version, run ID, "
            "mode, hook, and mission hash when a mission was supplied.",
            "A registry aggregate run proves initialization and counts, not "
            "the correctness of every unexported registry record.",
            "A mission smoke run proves load/start/bounded stability and its "
            "declared coordinate checks; it does not prove AI behaviour, all "
            "trigger paths, or a human playthrough.",
        ],
    }


def _validate_runtime_result(
    result: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if result.get("schema") != RESULT_SCHEMA:
        reasons.append("runtime_result_schema_mismatch")
    if result.get("run_id") != manifest["run_id"]:
        reasons.append("runtime_result_run_id_mismatch")
    if result.get("mode") != manifest["mode"]:
        reasons.append("runtime_result_mode_mismatch")
    if result.get("status") != "ok":
        reasons.append("runtime_result_status_not_ok")
    dcs = result.get("dcs")
    if not isinstance(dcs, dict):
        reasons.append("runtime_identity_missing")
    else:
        if dcs.get("runtime_identity_attested") is not True:
            reasons.append("runtime_identity_not_attested")
        if dcs.get("expected_product_version") != manifest["dcs"]["product_version"]:
            reasons.append("runtime_expected_product_version_mismatch")
        if dcs.get("runtime_product_version") != manifest["dcs"]["product_version"]:
            reasons.append("runtime_product_version_mismatch")
    if manifest["mode"] == "registry-probe":
        registry = result.get("registry")
        counts = registry.get("counts") if isinstance(registry, dict) else None
        if not isinstance(registry, dict) or registry.get("initialized") is not True:
            reasons.append("registry_not_initialized")
        if not isinstance(counts, dict):
            reasons.append("registry_counts_missing")
        else:
            for name in (
                "countries",
                "unit_types",
                "weapons_by_clsid",
                "task_definitions",
                "planes",
                "pylon_launcher_edges",
            ):
                value = counts.get(name)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    reasons.append(f"registry_count_invalid:{name}")
    else:
        mission = result.get("mission")
        smoke = result.get("smoke")
        if not isinstance(mission, dict):
            reasons.append("runtime_mission_summary_missing")
        else:
            expected = manifest["inputs"]["mission"]
            if mission.get("expected_name") != expected["name"]:
                reasons.append("runtime_expected_mission_name_mismatch")
            if mission.get("expected_theatre") != expected["theatre"]:
                reasons.append("runtime_expected_mission_theatre_mismatch")
            if mission.get("expected_groups") != expected["expected_groups"]:
                reasons.append("runtime_expected_mission_group_count_mismatch")
            if mission.get("expected_units") != expected["expected_units"]:
                reasons.append("runtime_expected_mission_unit_count_mismatch")
            if (
                mission.get("expected_player_slots")
                != expected["expected_player_slots"]
            ):
                reasons.append("runtime_expected_mission_player_slots_mismatch")
            if mission.get("runtime_theatre") != expected["theatre"]:
                reasons.append("runtime_mission_theatre_mismatch")
            if mission.get("runtime_filename_name") != expected["name"]:
                reasons.append("runtime_mission_filename_mismatch")
            if mission.get("groups") != expected["expected_groups"]:
                reasons.append("runtime_mission_group_count_mismatch")
            if mission.get("units") != expected["expected_units"]:
                reasons.append("runtime_mission_unit_count_mismatch")
            runtime_slots = mission.get("available_slots")
            if expected["expected_player_slots"] > 0 and (
                isinstance(runtime_slots, bool)
                or not isinstance(runtime_slots, int)
                or runtime_slots < 1
            ):
                reasons.append("runtime_mission_player_slots_missing")
        if not isinstance(smoke, dict) or smoke.get("interval_completed") is not True:
            reasons.append("smoke_interval_incomplete")
        else:
            required_seconds = manifest["inputs"]["smoke_seconds"]
            observed_seconds = smoke.get("observed_seconds")
            if smoke.get("required_seconds") != required_seconds:
                reasons.append("smoke_required_interval_mismatch")
            if (
                isinstance(observed_seconds, bool)
                or not isinstance(observed_seconds, (int, float))
                or not math.isfinite(float(observed_seconds))
                or observed_seconds < required_seconds
            ):
                reasons.append("smoke_observed_interval_invalid")
        expected_checks = manifest["inputs"]["coordinate_checks"]
        checks = result.get("coordinate_checks")
        expected_count = expected_checks["checks"] if expected_checks else 0
        if not isinstance(checks, list) or len(checks) != expected_count:
            reasons.append("coordinate_check_count_mismatch")
        else:
            expected_records = expected_checks["records"] if expected_checks else []
            for expected_record, observed_record in zip(
                expected_records,
                checks,
                strict=True,
            ):
                if not _runtime_coordinate_record_valid(
                    observed_record,
                    expected_record,
                ):
                    reasons.append("coordinate_check_failed")
                    break
        if result.get("coordinate_checks_passed") is not True:
            reasons.append("coordinate_checks_not_passed")
        events = result.get("events")
        names = {
            item.get("name")
            for item in events
            if isinstance(item, dict)
        } if isinstance(events, list) else set()
        for required in (
            "mission_load_end",
            "simulation_start",
            "smoke_interval_complete",
        ):
            if required not in names:
                reasons.append(f"runtime_event_missing:{required}")
    return reasons


def _runtime_coordinate_record_valid(
    observed: Any,
    expected: dict[str, Any],
) -> bool:
    if not isinstance(observed, dict) or observed.get("passed") is not True:
        return False
    for name in (
        "label",
        "latitude",
        "longitude",
        "expected_x",
        "expected_y",
        "tolerance_m",
    ):
        if observed.get(name) != expected[name]:
            return False
    runtime_x = observed.get("runtime_x")
    runtime_y = observed.get("runtime_y")
    reported_error = observed.get("error_m")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in (runtime_x, runtime_y, reported_error)
    ):
        return False
    calculated_error = math.hypot(
        float(runtime_x) - expected["expected_x"],
        float(runtime_y) - expected["expected_y"],
    )
    return (
        calculated_error <= expected["tolerance_m"]
        and math.isclose(
            float(reported_error),
            calculated_error,
            rel_tol=1e-12,
            abs_tol=1e-6,
        )
    )


def _load_and_verify_manifest(
    manifest_path: Path,
) -> tuple[dict[str, Any], bytes, dict[str, Path]]:
    manifest, payload = _load_json_file(
        Path(manifest_path),
        MAX_MANIFEST_BYTES,
        "runtime manifest",
    )
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("runtime manifest schema is not supported")
    run_id = _validate_run_id(manifest.get("run_id"))
    if manifest.get("mode") not in _MODES:
        raise ValueError("runtime manifest mode is invalid")
    producer = manifest.get("producer")
    if (
        not isinstance(producer, dict)
        or producer.get("name") != "DCSMizzer"
        or producer.get("version") != __version__
    ):
        raise ValueError("runtime manifest producer is not this DCSMizzer version")
    profile = manifest.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("runtime manifest profile is missing")
    expected_profile_name = PROFILE_PREFIX + run_id
    if profile.get("name") != expected_profile_name:
        raise ValueError("runtime manifest profile name is invalid")
    if (
        profile.get("ordinary_profile") is not False
        or profile.get("isolated") is not True
    ):
        raise ValueError("runtime manifest does not declare an isolated profile")
    profile_root = _existing_directory(
        Path(_required_text(profile.get("absolute_path"), "profile.absolute_path")),
        "runtime profile",
    )
    if profile_root.name != expected_profile_name:
        raise ValueError("runtime profile path does not match the run ID")
    manifest_actual = Path(manifest_path).resolve()
    product_root = profile_root / "DCSMizzer"
    expected_manifest = product_root / "manifest.json"
    if manifest_actual != expected_manifest.resolve():
        raise ValueError("runtime manifest is not inside its disposable profile")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("hook"), dict):
        raise ValueError("runtime manifest artifacts are invalid")
    hook_relative = _safe_relative(
        artifacts["hook"].get("relative_path"),
        "artifacts.hook.relative_path",
    )
    hook = _contained(profile_root, hook_relative, "runtime hook")
    _verify_file_record(hook, artifacts["hook"], MAX_SOURCE_BYTES, "runtime hook")
    result_relative = _safe_relative(
        artifacts.get("result_relative_path"),
        "artifacts.result_relative_path",
    )
    execution_relative = _safe_relative(
        artifacts.get("execution_relative_path"),
        "artifacts.execution_relative_path",
    )
    result = _contained(profile_root, result_relative, "runtime result")
    execution = _contained(profile_root, execution_relative, "runtime execution")

    dcs = manifest.get("dcs")
    if not isinstance(dcs, dict) or not isinstance(dcs.get("executable"), dict):
        raise ValueError("runtime manifest DCS identity is invalid")
    executable = Path(
        _required_text(dcs["executable"].get("absolute_path"), "DCS executable")
    )
    _verify_file_record(
        executable,
        dcs["executable"],
        MAX_MISSION_BYTES,
        "DCS executable",
    )
    current_version = _windows_product_version(executable)
    if current_version != dcs.get("product_version"):
        raise ValueError("DCS executable product version changed after preparation")
    dcs_root = executable.parent.parent.resolve()
    current_distribution, current_build, current_launcher = _distribution_identity(
        dcs_root
    )
    if current_distribution != dcs.get("distribution"):
        raise ValueError("DCS distribution identity changed after preparation")
    if current_build != dcs.get("distribution_build"):
        raise ValueError("DCS distribution build changed after preparation")

    api_record = dcs.get("sim_control_api")
    api_path = dcs_root / "API" / "Sim_ControlAPI.md"
    if api_path.is_file():
        if not isinstance(api_record, dict):
            raise ValueError("runtime manifest omitted the available Sim Control API")
        api_relative = _safe_relative(
            api_record.get("relative_path"),
            "dcs.sim_control_api.relative_path",
        )
        if api_relative.as_posix() != "API/Sim_ControlAPI.md":
            raise ValueError("runtime manifest Sim Control API path is invalid")
        _verify_file_record(
            _contained(dcs_root, api_relative, "Sim Control API"),
            api_record,
            MAX_SOURCE_BYTES,
            "Sim Control API",
        )
    elif api_record is not None:
        raise ValueError("runtime manifest Sim Control API is no longer present")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("runtime manifest inputs are invalid")
    mission = inputs.get("mission")
    coordinate_records: list[dict[str, Any]] = []
    if manifest["mode"] == "mission-smoke":
        if not isinstance(mission, dict):
            raise ValueError("mission-smoke manifest is missing its mission")
        mission_path = Path(
            _required_text(mission.get("absolute_path"), "mission.absolute_path")
        )
        _verify_file_record(mission_path, mission, MAX_MISSION_BYTES, "mission")
        for field_name in (
            "expected_groups",
            "expected_units",
            "expected_player_slots",
        ):
            value = mission.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"mission.{field_name} is invalid")
        archive = inspect_miz(mission_path)
        analysis = analyse_miz(mission_path)
        if not archive.valid_zip or not archive.safe or archive.crc_status != "passed":
            raise ValueError("mission no longer passes ZIP safety and CRC checks")
        if not analysis.parse_valid or analysis.theatre != mission.get("theatre"):
            raise ValueError("mission parse or theatre identity changed")
        observed_counts = {
            "expected_groups": sum(analysis.stats.groups.values()),
            "expected_units": sum(analysis.stats.units.values()),
            "expected_player_slots": sum(analysis.stats.human_slots.values()),
        }
        if any(mission.get(name) != value for name, value in observed_counts.items()):
            raise ValueError("mission entity counts changed after preparation")
    elif mission is not None:
        raise ValueError("registry manifest unexpectedly contains a mission")

    coordinate_source = inputs.get("coordinate_checks")
    if coordinate_source is not None:
        if manifest["mode"] != "mission-smoke" or not isinstance(
            coordinate_source,
            dict,
        ):
            raise ValueError("runtime manifest coordinate checks are invalid")
        if coordinate_source.get("schema") != COORDINATE_CHECKS_SCHEMA:
            raise ValueError("runtime manifest coordinate-check schema is invalid")
        _required_text(coordinate_source.get("name"), "coordinate checks name", 255)
        coordinate_hash = _required_text(
            coordinate_source.get("sha256"),
            "coordinate checks SHA-256",
            64,
        )
        if re.fullmatch(r"[0-9a-f]{64}", coordinate_hash) is None:
            raise ValueError("runtime manifest coordinate-check hash is invalid")
        coordinate_records = _validate_coordinate_checks(
            {
                "schema": coordinate_source.get("schema"),
                "terrain": coordinate_source.get("terrain"),
                "checks": coordinate_source.get("records"),
            },
            expected_theatre=(
                mission.get("theatre") if isinstance(mission, dict) else None
            ),
        )
        if coordinate_source.get("checks") != len(coordinate_records):
            raise ValueError("runtime manifest coordinate-check count is invalid")
    smoke_seconds = inputs.get("smoke_seconds")
    if manifest["mode"] == "mission-smoke":
        smoke_seconds = _bounded_number(
            smoke_seconds,
            "runtime manifest smoke_seconds",
            MIN_SMOKE_SECONDS,
            MAX_SMOKE_SECONDS,
        )
    elif smoke_seconds is not None:
        raise ValueError("registry manifest unexpectedly contains a smoke interval")

    command = manifest.get("command")
    if not isinstance(command, dict) or not isinstance(command.get("argv"), list):
        raise ValueError("runtime manifest command is invalid")
    launcher_kind = command.get("launcher_kind")
    if dcs.get("distribution") == "steam":
        distribution_manifest = dcs.get("distribution_manifest")
        if not isinstance(distribution_manifest, dict):
            raise ValueError("Steam runtime manifest source record is missing")
        manifest_relative = _safe_relative(
            distribution_manifest.get("relative_path"),
            "Steam manifest relative_path",
        )
        if manifest_relative.as_posix() != "appmanifest_223750.acf":
            raise ValueError("Steam runtime manifest source path is invalid")
        _verify_steam_app_manifest_record(
            _contained(
                dcs_root.parent.parent,
                manifest_relative,
                "Steam app manifest",
            ),
            distribution_manifest,
            expected_build=dcs.get("distribution_build"),
            expected_install_dir=dcs_root.name,
        )
        launcher_record = dcs.get("distribution_launcher")
        if not isinstance(launcher_record, dict):
            raise ValueError("Steam runtime manifest launcher is missing")
        launcher = Path(
            _required_text(
                launcher_record.get("absolute_path"),
                "Steam launcher absolute_path",
            )
        )
        _verify_file_record(
            launcher,
            launcher_record,
            MAX_MISSION_BYTES,
            "Steam launcher",
        )
        if current_launcher is None or (
            str(current_launcher.resolve()).casefold()
            != str(launcher.resolve()).casefold()
        ):
            raise ValueError("Steam launcher identity changed after preparation")
        if launcher_kind != "steam_applaunch":
            raise ValueError("Steam runtime command launcher kind is invalid")
        if (
            command.get("steam_custom_arguments_confirmation_may_be_required")
            is not True
        ):
            raise ValueError("Steam runtime command confirmation policy is invalid")
        expected_argv = [
            str(launcher.resolve()),
            "-applaunch",
            "223750",
            "--server",
            "--norender",
            "-w",
            expected_profile_name,
        ]
        expected_working_directory = launcher.parent.resolve()
    else:
        if dcs.get("distribution_manifest") is not None:
            raise ValueError("standalone runtime manifest contains a Steam manifest")
        if launcher_kind != "direct":
            raise ValueError("direct runtime command launcher kind is invalid")
        if (
            command.get("steam_custom_arguments_confirmation_may_be_required")
            is not False
        ):
            raise ValueError("direct runtime command confirmation policy is invalid")
        expected_argv = [
            str(executable),
            "--server",
            "--norender",
            "-w",
            expected_profile_name,
        ]
        expected_working_directory = executable.parent.parent.resolve()
    if isinstance(mission, dict):
        expected_argv.append(mission["absolute_path"])
    if command["argv"] != expected_argv:
        raise ValueError("runtime command differs from the prepared command")
    working_directory = Path(
        _required_text(command.get("working_directory"), "command.working_directory")
    ).resolve()
    if expected_working_directory != working_directory:
        raise ValueError("runtime command working directory is invalid")
    if command.get("dry_run_default") is not True or (
        command.get("authorization_flag_required") is not True
    ):
        raise ValueError("runtime command authorization policy is invalid")

    expected_safety = {
        "writes_to_dcs_installation": False,
        "writes_to_ordinary_saved_games_profiles": False,
        "unsafe_dostring_enabled": False,
        "mission_scripting_desanitized": False,
        "cleanup_scope": "exact_process_started_by_runtime-run",
    }
    if manifest.get("safety") != expected_safety:
        raise ValueError("runtime manifest safety policy is invalid")

    hook_template = _runtime_hook_template()
    if artifacts["hook"].get("template_sha256") != hashlib.sha256(
        hook_template
    ).hexdigest():
        raise ValueError("runtime hook template differs from this product version")
    expected_hook = _render_runtime_hook(
        hook_template,
        run_id=run_id,
        mode=manifest["mode"],
        product_version=dcs["product_version"],
        mission_name=mission["name"] if isinstance(mission, dict) else "",
        theatre=mission["theatre"] if isinstance(mission, dict) else "",
        smoke_seconds=float(smoke_seconds) if smoke_seconds is not None else 10.0,
        coordinate_checks=coordinate_records,
        expected_groups=(
            mission["expected_groups"] if isinstance(mission, dict) else 0
        ),
        expected_units=(mission["expected_units"] if isinstance(mission, dict) else 0),
        expected_player_slots=(
            mission["expected_player_slots"] if isinstance(mission, dict) else 0
        ),
    ).encode("utf-8")
    if _read_regular_file(hook, MAX_SOURCE_BYTES, "runtime hook") != expected_hook:
        raise ValueError("runtime hook is not the trusted rendered product resource")
    return manifest, payload, {
        "profile_root": profile_root,
        "product_root": product_root,
        "hook": hook,
        "result": result,
        "execution": execution,
        "executable": executable,
    }


def _validate_coordinate_checks(
    data: dict[str, Any],
    *,
    expected_theatre: str | None,
) -> list[dict[str, Any]]:
    if data.get("schema") != COORDINATE_CHECKS_SCHEMA:
        raise ValueError("runtime coordinate-check schema is not supported")
    terrain = _required_text(data.get("terrain"), "coordinate checks terrain")
    if expected_theatre is None or terrain.casefold() != expected_theatre.casefold():
        raise ValueError("coordinate checks terrain does not match the mission")
    values = data.get("checks")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_COORDINATE_CHECKS:
        raise ValueError("coordinate checks must contain 1 to 100 records")
    records: list[dict[str, Any]] = []
    labels: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"coordinate checks[{index}] must be an object")
        label = _required_text(value.get("label"), f"checks[{index}].label", 128)
        if label in labels:
            raise ValueError("coordinate check labels must be unique")
        labels.add(label)
        latitude = _bounded_number(
            value.get("latitude"), f"checks[{index}].latitude", -90.0, 90.0
        )
        longitude = _bounded_number(
            value.get("longitude"), f"checks[{index}].longitude", -180.0, 180.0
        )
        expected_x = _bounded_number(
            value.get("expected_x"), f"checks[{index}].expected_x", -1e8, 1e8
        )
        expected_y = _bounded_number(
            value.get("expected_y"), f"checks[{index}].expected_y", -1e8, 1e8
        )
        tolerance = _bounded_number(
            value.get("tolerance_m", 25.0),
            f"checks[{index}].tolerance_m",
            0.001,
            10_000.0,
        )
        records.append(
            {
                "label": label,
                "latitude": latitude,
                "longitude": longitude,
                "expected_x": expected_x,
                "expected_y": expected_y,
                "tolerance_m": tolerance,
            }
        )
    return records


def _render_runtime_hook(
    template: bytes,
    *,
    run_id: str,
    mode: str,
    product_version: str,
    mission_name: str,
    theatre: str,
    smoke_seconds: float,
    coordinate_checks: list[dict[str, Any]],
    expected_groups: int,
    expected_units: int,
    expected_player_slots: int,
) -> str:
    rendered_checks = []
    for item in coordinate_checks:
        rendered_checks.append(
            "    { label = %s, latitude = %.17g, longitude = %.17g, "
            "expected_x = %.17g, expected_y = %.17g, tolerance_m = %.17g },"
            % (
                _lua_string(item["label"]),
                item["latitude"],
                item["longitude"],
                item["expected_x"],
                item["expected_y"],
                item["tolerance_m"],
            )
        )
    replacements = {
        "@@RUN_ID@@": _lua_string(run_id),
        "@@MODE@@": _lua_string(mode),
        "@@EXPECTED_VERSION@@": _lua_string(product_version),
        "@@EXPECTED_MISSION_NAME@@": _lua_string(mission_name),
        "@@EXPECTED_THEATRE@@": _lua_string(theatre),
        "@@SMOKE_SECONDS@@": f"{smoke_seconds:.17g}",
        "@@EXPECTED_GROUPS@@": str(expected_groups),
        "@@EXPECTED_UNITS@@": str(expected_units),
        "@@EXPECTED_PLAYER_SLOTS@@": str(expected_player_slots),
        "@@COORDINATE_CHECKS@@": "\n".join(rendered_checks),
    }
    text = template.decode("utf-8")
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    if "@@" in text:
        raise ValueError("runtime hook template rendering is incomplete")
    return text


def _runtime_hook_template() -> bytes:
    path = Path(__file__).with_name("resources") / "runtime_hook.lua"
    return _read_regular_file(path, MAX_SOURCE_BYTES, "runtime hook template")


def _select_dcs_executable(
    dcs_root: Path,
    *,
    prefer_steam_target: bool = False,
) -> Path:
    relatives = (
        (Path("bin") / "DCS.exe", Path("bin-mt") / "DCS.exe")
        if prefer_steam_target
        else (Path("bin-mt") / "DCS.exe", Path("bin") / "DCS.exe")
    )
    for relative in relatives:
        candidate = dcs_root / relative
        try:
            return _existing_regular_file(
                candidate,
                "DCS executable",
                maximum_bytes=MAX_MISSION_BYTES,
            )
        except ValueError:
            continue
    raise ValueError("DCS executable is missing from bin-mt and bin")


def _distribution_identity(
    dcs_root: Path,
) -> tuple[str, str | None, Path | None]:
    if (dcs_root / "_DCS_Steam").is_file():
        manifest = dcs_root.parent.parent / "appmanifest_223750.acf"
        build: str | None = None
        launcher: Path | None = None
        if manifest.is_file():
            payload = _read_regular_file(manifest, MAX_SOURCE_BYTES, "Steam manifest")
            match = re.search(rb'"buildid"\s*"([0-9]+)"', payload)
            if match is not None:
                build = match.group(1).decode("ascii")
            launcher_match = re.search(
                rb'"LauncherPath"\s*"([^"\r\n]+)"',
                payload,
            )
            if launcher_match is not None:
                try:
                    launcher_text = launcher_match.group(1).decode("utf-8")
                except UnicodeDecodeError:
                    launcher_text = ""
                if launcher_text:
                    launcher = Path(launcher_text.replace("\\\\", "\\"))
        return "steam", build, launcher
    return "standalone", None, None


def _git_identity(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _running_dcs_pids() -> list[int]:
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq DCS.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(
            "could not determine whether DCS is already running"
        ) from error
    if result.returncode != 0:
        raise ValueError("could not determine whether DCS is already running")
    pids: list[int] = []
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) >= 2 and row[0].casefold() == "dcs.exe":
            try:
                pids.append(int(row[1]))
            except ValueError:
                continue
    return sorted(set(pids))


def _windows_process_identity(pid: int) -> dict[str, Any] | None:
    """Return bounded identity fields for one Windows PID without a shell."""

    if os.name != "nt" or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("DCS process identity requires one positive Windows PID")
    script = (
        "$OutputEncoding=[Console]::OutputEncoding="
        "[System.Text.UTF8Encoding]::new($false);"
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' "
        "-ErrorAction SilentlyContinue;"
        "if($null -ne $p){[pscustomobject]@{"
        "pid=[int]$p.ProcessId;"
        "executable_path=[string]$p.ExecutablePath;"
        "command_line=[string]$p.CommandLine} | ConvertTo-Json -Compress}"
    )
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("could not attest the started DCS process") from error
    if result.returncode != 0:
        raise ValueError("could not attest the started DCS process")
    payload = result.stdout.decode("utf-8-sig", errors="strict").strip()
    if not payload:
        return None
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("DCS process identity was not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("DCS process identity was not an object")
    return value


def _direct_process_attestation(
    manifest: dict[str, Any],
    pid: int,
) -> dict[str, Any]:
    executable = manifest["dcs"]["executable"]
    return {
        "attested": True,
        "source": "direct_child_process",
        "pid": pid,
        "executable_path": executable["absolute_path"],
        "executable_sha256": executable["sha256"],
        "profile_argument_attested": True,
        "mission_argument_attested": (
            True if manifest["inputs"]["mission"] is not None else None
        ),
    }


def _attest_steam_process(
    identity: dict[str, Any] | None,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Bind a Steam-created process to the prepared executable and inputs."""

    if not isinstance(identity, dict):
        return None
    pid = identity.get("pid")
    executable_path = identity.get("executable_path")
    command_line = identity.get("command_line")
    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 0
        or not isinstance(executable_path, str)
        or not executable_path
        or not isinstance(command_line, str)
        or not command_line
    ):
        return None
    expected_executable = Path(manifest["dcs"]["executable"]["absolute_path"])
    try:
        actual_resolved = Path(executable_path).resolve()
        expected_resolved = expected_executable.resolve()
    except OSError:
        return None
    if str(actual_resolved).casefold() != str(expected_resolved).casefold():
        return None
    profile_name = manifest["profile"]["name"]
    profile_pattern = re.compile(
        rf"(?:^|\s)-w\s+\"?{re.escape(profile_name)}\"?(?=\s|$)",
        re.IGNORECASE,
    )
    if profile_pattern.search(command_line) is None:
        return None
    mission = manifest["inputs"]["mission"]
    mission_attested: bool | None = None
    if isinstance(mission, dict):
        mission_attested = _command_line_has_exact_argument(
            command_line,
            str(mission["absolute_path"]),
        )
        if not mission_attested:
            return None
    executable = manifest["dcs"]["executable"]
    return {
        "attested": True,
        "source": "windows_process_identity",
        "pid": pid,
        "executable_path": str(actual_resolved),
        "executable_sha256": executable["sha256"],
        "profile_argument_attested": True,
        "mission_argument_attested": mission_attested,
    }


def _command_line_has_exact_argument(command_line: str, expected: str) -> bool:
    """Match one complete quoted or whitespace-free Windows argument."""

    quoted = re.compile(
        rf'(?:^|\s)"{re.escape(expected)}"(?=\s|$)',
        re.IGNORECASE,
    )
    if quoted.search(command_line) is not None:
        return True
    if any(character.isspace() for character in expected):
        return False
    unquoted = re.compile(
        rf"(?:^|\s){re.escape(expected)}(?=\s|$)",
        re.IGNORECASE,
    )
    return unquoted.search(command_line) is not None


def _terminate_dcs_pid(pid: int, force: bool) -> None:
    if os.name != "nt" or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("DCS process termination requires one positive Windows PID")
    command = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    try:
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("exact DCS process cleanup failed") from error


def _load_json_file(
    path: Path,
    maximum_bytes: int,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular_file(path, maximum_bytes, label)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains a non-finite JSON number")

    try:
        value = json.loads(
            payload.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} root must be an object")
    _validate_json_graph(value, label)
    return value, payload


def _validate_json_graph(root: Any, label: str) -> None:
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"{label} exceeds the JSON depth limit")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite JSON number")


def _read_regular_file(path: Path, maximum_bytes: int, label: str) -> bytes:
    candidate = _existing_regular_file(path, label, maximum_bytes=maximum_bytes)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(candidate, flags)
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the byte limit")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(payload) > maximum_bytes:
            raise ValueError(f"{label} exceeds the byte limit")
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{label} changed while being read")
        if len(payload) != before.st_size:
            raise ValueError(f"{label} could not be read completely")
        return payload
    finally:
        os.close(descriptor)


def _existing_regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int,
) -> Path:
    candidate = Path(path).absolute()
    try:
        status_result = candidate.lstat()
    except OSError as error:
        raise ValueError(f"{label} is missing") from error
    if not stat.S_ISREG(status_result.st_mode) or _is_reparse(status_result):
        raise ValueError(f"{label} is not a safe regular file")
    if status_result.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the byte limit")
    return candidate.resolve()


def _existing_directory(path: Path, label: str) -> Path:
    candidate = Path(path).absolute()
    try:
        status_result = candidate.lstat()
    except OSError as error:
        raise ValueError(f"{label} is missing") from error
    if not stat.S_ISDIR(status_result.st_mode) or _is_reparse(status_result):
        raise ValueError(f"{label} is not a safe directory")
    return candidate.resolve()


def _verify_file_record(
    path: Path,
    record: dict[str, Any],
    maximum_bytes: int,
    label: str,
) -> None:
    candidate = _existing_regular_file(path, label, maximum_bytes=maximum_bytes)
    if candidate.stat().st_size != record.get("size_bytes"):
        raise ValueError(f"{label} size changed after preparation")
    if _sha256_file(candidate, maximum_bytes) != record.get("sha256"):
        raise ValueError(f"{label} hash changed after preparation")


def _sha256_file(path: Path, maximum_bytes: int) -> str:
    payload = _read_regular_file(path, maximum_bytes, path.name)
    return hashlib.sha256(payload).hexdigest()


def _optional_source_record(path: Path, root: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    candidate = _existing_regular_file(path, path.name, maximum_bytes=MAX_SOURCE_BYTES)
    return {
        "relative_path": candidate.relative_to(root).as_posix(),
        "size_bytes": candidate.stat().st_size,
        "sha256": _sha256_file(candidate, MAX_SOURCE_BYTES),
    }


def _steam_app_manifest_record(
    path: Path,
    root: Path,
    *,
    expected_build: Any,
    expected_install_dir: str,
) -> dict[str, Any]:
    candidate = _existing_regular_file(
        path,
        "Steam app manifest",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    payload = _read_regular_file(
        candidate,
        MAX_SOURCE_BYTES,
        "Steam app manifest",
    )
    return {
        "relative_path": candidate.relative_to(root).as_posix(),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "semantic_identity": _steam_app_manifest_identity(
            payload,
            expected_build=expected_build,
            expected_install_dir=expected_install_dir,
        ),
        "verification": {
            "raw_hash_scope": "preparation_observation_only",
            "current_check": "selected_semantic_identity",
        },
    }


def _verify_steam_app_manifest_record(
    path: Path,
    record: dict[str, Any],
    *,
    expected_build: Any,
    expected_install_dir: str,
) -> None:
    if set(record) != {
        "relative_path",
        "size_bytes",
        "sha256",
        "semantic_identity",
        "verification",
    }:
        raise ValueError("Steam app manifest record shape is invalid")
    size = record.get("size_bytes")
    digest = record.get("sha256")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= MAX_SOURCE_BYTES
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise ValueError("Steam app manifest preparation identity is invalid")
    if record.get("verification") != {
        "raw_hash_scope": "preparation_observation_only",
        "current_check": "selected_semantic_identity",
    }:
        raise ValueError("Steam app manifest verification policy is invalid")
    candidate = _existing_regular_file(
        path,
        "Steam app manifest",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    payload = _read_regular_file(
        candidate,
        MAX_SOURCE_BYTES,
        "Steam app manifest",
    )
    current_identity = _steam_app_manifest_identity(
        payload,
        expected_build=expected_build,
        expected_install_dir=expected_install_dir,
    )
    if record.get("semantic_identity") != current_identity:
        raise ValueError("Steam app manifest semantic identity changed")


def _steam_app_manifest_identity(
    payload: bytes,
    *,
    expected_build: Any,
    expected_install_dir: str,
) -> dict[str, Any]:
    build = _required_text(expected_build, "Steam build ID", 32)
    if re.fullmatch(r"[0-9]+", build) is None:
        raise ValueError("Steam build ID is invalid")
    app_id = _steam_app_manifest_field(payload, "appid", maximum=32)
    observed_build = _steam_app_manifest_field(payload, "buildid", maximum=32)
    install_dir = _steam_app_manifest_field(payload, "installdir", maximum=255)
    state_flags_text = _steam_app_manifest_field(
        payload,
        "StateFlags",
        maximum=16,
    )
    if app_id != "223750" or observed_build != build:
        raise ValueError("Steam app manifest app or build identity is invalid")
    if install_dir.casefold() != expected_install_dir.casefold():
        raise ValueError("Steam app manifest install directory is invalid")
    if re.fullmatch(r"[0-9]+", state_flags_text) is None:
        raise ValueError("Steam app manifest state flags are invalid")
    state_flags = int(state_flags_text)
    if state_flags != 4:
        raise ValueError("Steam DCS app is not in the fully installed state")
    return {
        "schema": STEAM_MANIFEST_IDENTITY_SCHEMA,
        "app_id": app_id,
        "build_id": observed_build,
        "install_dir_casefold": install_dir.casefold(),
        "state_flags": state_flags,
    }


def _steam_app_manifest_field(
    payload: bytes,
    name: str,
    *,
    maximum: int,
) -> str:
    key = re.escape(name.encode("ascii"))
    matches = re.findall(
        rb'"' + key + rb'"\s*"([^"\r\n]*)"',
        payload,
        flags=re.IGNORECASE,
    )
    if len(matches) != 1:
        raise ValueError(f"Steam app manifest {name} field is missing or ambiguous")
    try:
        value = matches[0].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Steam app manifest {name} field is not UTF-8") from error
    if (
        not 1 <= len(value) <= maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ValueError(f"Steam app manifest {name} field is invalid")
    return value


def _file_record_if_present(
    path: Path,
    *,
    maximum_bytes: int = MAX_RESULT_BYTES,
) -> dict[str, Any] | None:
    try:
        candidate = _existing_regular_file(
            path,
            path.name,
            maximum_bytes=maximum_bytes,
        )
    except ValueError:
        return None
    return {
        "name": candidate.name,
        "size_bytes": candidate.stat().st_size,
        "sha256": _sha256_file(candidate, maximum_bytes),
    }


def _write_new_file(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _contained(root: Path, relative: Path, label: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escaped its declared root") from error
    return candidate


def _safe_relative(value: Any, label: str) -> Path:
    text = _required_text(value, label, 256)
    candidate = Path(text)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError(f"{label} is not a safe relative path")
    return candidate


def _required_text(value: Any, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a nonempty bounded string")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} contains a control character")
    return value


def _validate_run_id(value: Any) -> str:
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValueError("run ID must match [a-z0-9][a-z0-9-]{0,47}")
    return value


def _bounded_number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def _is_reparse(status_result: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status_result, "st_file_attributes", 0)
    return bool(attribute and file_attributes & attribute)


def _lua_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
