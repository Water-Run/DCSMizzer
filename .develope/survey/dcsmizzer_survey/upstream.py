from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UpstreamRepository:
    name: str
    path: Path


@dataclass(frozen=True)
class UpstreamObservation:
    name: str
    valid_git: bool
    branch: str | None
    head: str | None
    commit_time: str | None
    clean: bool
    remote_kind: str | None
    remote_url: str | None
    remote_checked: bool
    remote_head: str | None
    in_sync: bool | None
    license_evidence: tuple[str, ...]
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "valid_git": self.valid_git,
            "branch": self.branch,
            "head": self.head,
            "commit_time": self.commit_time,
            "clean": self.clean,
            "remote_kind": self.remote_kind,
            "remote_url": self.remote_url,
            "remote_checked": self.remote_checked,
            "remote_head": self.remote_head,
            "in_sync": self.in_sync,
            "license_evidence": list(self.license_evidence),
            "error_code": self.error_code,
        }


def inspect_repository(
    repository: UpstreamRepository,
    *,
    check_remote: bool,
) -> UpstreamObservation:
    try:
        inside = _git(repository.path, "rev-parse", "--is-inside-work-tree")
        if inside != "true":
            return _invalid(repository.name, "not_git")
        branch = _git(repository.path, "branch", "--show-current") or None
        head = _git(repository.path, "rev-parse", "HEAD")
        commit_time = _git(repository.path, "log", "-1", "--format=%cI")
        clean = not bool(_git(repository.path, "status", "--porcelain"))
        remote = _git_optional(repository.path, "remote", "get-url", "origin")
        remote_kind, public_remote = _classify_remote(remote)
        license_evidence = _license_evidence(repository.path)

        remote_head: str | None = None
        in_sync: bool | None = None
        remote_checked = False
        if check_remote and remote and branch:
            remote_checked = True
            line = _git(
                repository.path,
                "ls-remote",
                "origin",
                f"refs/heads/{branch}",
            )
            remote_head = line.split(maxsplit=1)[0] if line else None
            in_sync = remote_head == head if remote_head is not None else False

        return UpstreamObservation(
            name=repository.name,
            valid_git=True,
            branch=branch,
            head=head,
            commit_time=commit_time,
            clean=clean,
            remote_kind=remote_kind,
            remote_url=public_remote,
            remote_checked=remote_checked,
            remote_head=remote_head,
            in_sync=in_sync,
            license_evidence=license_evidence,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return _invalid(repository.name, "git_unavailable")


def _git(path: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _git_optional(path: Path, *arguments: str) -> str | None:
    try:
        value = _git(path, *arguments)
    except subprocess.CalledProcessError:
        return None
    return value or None


def _classify_remote(remote: str | None) -> tuple[str | None, str | None]:
    if remote is None:
        return None, None
    if remote.startswith(("https://", "http://", "ssh://", "git://", "git@")):
        return "network", remote
    return "local", None


def _license_evidence(path: Path) -> tuple[str, ...]:
    evidence = [
        item.name
        for item in path.iterdir()
        if item.is_file()
        and item.name.casefold().startswith(
            ("license", "copying", "copyright")
        )
    ]
    package = path / "package.json"
    if package.is_file():
        try:
            value = json.loads(package.read_text(encoding="utf-8")).get("license")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, str) and value:
            evidence.append(f"package.json#license={value}")
    return tuple(sorted(evidence, key=str.casefold))


def _invalid(name: str, code: str) -> UpstreamObservation:
    return UpstreamObservation(
        name=name,
        valid_git=False,
        branch=None,
        head=None,
        commit_time=None,
        clean=False,
        remote_kind=None,
        remote_url=None,
        remote_checked=False,
        remote_head=None,
        in_sync=None,
        license_evidence=(),
        error_code=code,
    )
