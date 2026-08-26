"""Isolated CLI bootstrap with a pre-import producer-integrity gate."""

import sys


def _lexical_absolute_path(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    drive = ""
    if normalized.startswith("//"):
        prefix = "//"
        remainder = normalized[2:]
    elif normalized.startswith("/"):
        prefix = "/"
        remainder = normalized[1:]
    elif len(normalized) >= 3 and normalized[1:3] == ":/":
        drive = normalized[:2].casefold()
        prefix = drive + "/"
        remainder = normalized[3:]
    else:
        return None
    parts: list[str] = []
    for part in remainder.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return prefix + "/".join(parts)


_SCRIPT_PATH = _lexical_absolute_path(__file__)
if _SCRIPT_PATH is None or "/" not in _SCRIPT_PATH:
    raise SystemExit("DCSMizzer bootstrap error: entrypoint path is not absolute")
_TOOLS_ROOT = _SCRIPT_PATH.rsplit("/", 1)[0]
_REPOSITORY_ROOT = _TOOLS_ROOT.rsplit("/", 1)[0]
_PYTHON_BASE = _lexical_absolute_path(sys.base_prefix)
if _PYTHON_BASE is None:
    raise SystemExit("DCSMizzer bootstrap error: Python base path is not absolute")


def _path_key(value: str) -> str:
    return value.casefold() if sys.platform == "win32" else value


# Resolve bootstrap-only standard-library imports without consulting the
# repository, PYTHONPATH, user site-packages, or the script directory.
_python_base_key = _path_key(_PYTHON_BASE)
sys.path[:] = [
    entry
    for entry in sys.path
    if (
        (normalized := _lexical_absolute_path(entry)) is not None
        and (
            _path_key(normalized) == _python_base_key
            or _path_key(normalized).startswith(_python_base_key + "/")
        )
        and "/site-packages" not in normalized.casefold()
    )
]

import hashlib  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402


_TOOLS_ROOT = os.path.realpath(_TOOLS_ROOT)
_REPOSITORY_ROOT = os.path.realpath(_REPOSITORY_ROOT)
_GIT_DIRECTORY = os.path.join(_REPOSITORY_ROOT, ".git")
_MAX_TRACKED_FILE_BYTES = 64 * 1024 * 1024
_MAX_TRACKED_TREE_BYTES = 256 * 1024 * 1024
_PROVENANCE_COMMANDS = frozenset(
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


def _bootstrap_error(message: str) -> None:
    sys.stderr.write(f"DCSMizzer bootstrap error: {message}\n")
    raise SystemExit(2)


def _is_reparse(status_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(status_result, "st_file_attributes", 0) & reparse_flag)


def _safe_regular_file(path: str, *, maximum_bytes: int) -> bytes | None:
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or _is_reparse(before)
            or not 0 <= before.st_size <= maximum_bytes
        ):
            return None
        with open(path, "rb") as handle:
            payload = handle.read(maximum_bytes + 1)
        after = os.lstat(path)
    except OSError:
        return None
    if len(payload) > maximum_bytes:
        return None
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity:
        return None
    return payload


def _provenance_sensitive_invocation(arguments: list[str]) -> bool:
    command_index = 1 if arguments[:1] == ["--"] else 0
    option_tokens = arguments[command_index + 1 :]
    if "--" in option_tokens:
        option_tokens = option_tokens[: option_tokens.index("--")]
    if any(token in {"-h", "--help"} for token in option_tokens):
        return False
    return bool(
        (
            len(arguments) > command_index
            and arguments[command_index] in _PROVENANCE_COMMANDS
        )
        or any(
            argument == "--evidence-bundle"
            or argument.startswith("--evidence-bundle=")
            for argument in option_tokens
        )
    )


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith(("GIT_ATTR_", "GIT_CONFIG_")) or key in {
            "GIT_CONFIG",
            "GIT_CONFIG_PARAMETERS",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_COMMON_DIR",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        }:
            environment.pop(key, None)
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
        }
    )
    return environment


def _git(*arguments: str, input_payload: bytes | None = None) -> bytes | None:
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "core.ignoreStat=false",
        "-c",
        "core.trustctime=true",
        "-c",
        "core.checkStat=default",
        "-c",
        f"core.autocrlf={'true' if os.name == 'nt' else 'false'}",
        f"--git-dir={_GIT_DIRECTORY}",
        f"--work-tree={_REPOSITORY_ROOT}",
        *arguments,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            input=input_payload,
            capture_output=True,
            cwd=_REPOSITORY_ROOT,
            timeout=30,
            env=_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _git_text(*arguments: str) -> str | None:
    payload = _git(*arguments)
    if payload is None:
        return None
    try:
        return payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None


def _dangerous_local_config(payload: bytes | None) -> bool:
    if payload is None:
        return True
    try:
        keys = [
            value.decode("utf-8").casefold()
            for value in payload.split(b"\0")
            if value
        ]
    except UnicodeDecodeError:
        return True
    exact = {
        "core.attributesfile",
        "core.checkstat",
        "core.fsmonitor",
        "core.ignorestat",
        "core.trustctime",
        "core.worktree",
        "extensions.worktreeconfig",
    }
    return any(
        key.startswith(("filter.", "include.", "includeif.")) or key in exact
        for key in keys
    )


def _metadata_file_empty(relative: str) -> bool:
    path = os.path.join(_GIT_DIRECTORY, *relative.split("/"))
    try:
        status_result = os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not stat.S_ISREG(status_result.st_mode) or _is_reparse(status_result):
        return False
    payload = _safe_regular_file(path, maximum_bytes=64 * 1024)
    return payload == b""


def _ignored_tools_are_absent(payload: bytes | None) -> bool:
    if payload is None:
        return False
    try:
        records = [record for record in payload.decode("utf-8").split("\0") if record]
    except UnicodeDecodeError:
        return False
    for record in records:
        if not record.startswith(("!! ", "?? ")):
            continue
        relative = record[3:].replace("\\", "/")
        if relative == "Tools" or relative.startswith("Tools/"):
            return False
    return True


def _safe_tracked_relative_path(relative: str) -> bool:
    parts = relative.split("/")
    return bool(
        parts
        and all(part not in {"", ".", ".."} for part in parts)
        and not relative.startswith("/")
        and (
            os.name != "nt"
            or ("\\" not in relative and ":" not in relative)
        )
        and "\r" not in relative
        and "\n" not in relative
        and "\0" not in relative
    )


def _tracked_tree(payload: bytes | None) -> list[tuple[str, str]] | None:
    if payload is None:
        return None
    records: list[tuple[str, str]] = []
    try:
        for raw_record in payload.split(b"\0"):
            if not raw_record:
                continue
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode, kind, digest = metadata.decode("ascii").split(" ", 2)
            relative = raw_path.decode("utf-8")
            if (
                kind != "blob"
                or mode not in {"100644", "100755"}
                or not _safe_tracked_relative_path(relative)
            ):
                return None
            records.append((relative, digest))
    except (UnicodeError, ValueError):
        return None
    return records or None


def _git_blobs(
    payload: bytes | None,
    expected: list[str],
    object_format: str,
) -> dict[str, bytes] | None:
    if payload is None or object_format not in {"sha1", "sha256"}:
        return None
    output: dict[str, bytes] = {}
    offset = 0
    total = 0
    try:
        for requested in expected:
            header_end = payload.index(b"\n", offset)
            raw_digest, kind, raw_size = payload[offset:header_end].split(b" ", 2)
            digest = raw_digest.decode("ascii")
            size = int(raw_size)
            if (
                digest != requested
                or kind != b"blob"
                or not 0 <= size <= _MAX_TRACKED_FILE_BYTES
            ):
                return None
            offset = header_end + 1
            end = offset + size
            if end >= len(payload) or payload[end : end + 1] != b"\n":
                return None
            blob = payload[offset:end]
            header = f"blob {len(blob)}\0".encode("ascii")
            if hashlib.new(object_format, header + blob).hexdigest() != digest:
                return None
            output[digest] = blob
            total += len(blob)
            if total > _MAX_TRACKED_TREE_BYTES:
                return None
            offset = end + 1
    except (UnicodeError, ValueError):
        return None
    if offset != len(payload):
        return None
    return output


def _worktree_matches(
    records: list[tuple[str, str]],
    blobs: dict[str, bytes],
    object_format: str,
) -> bool:
    verified_directories = {_REPOSITORY_ROOT}
    total = 0
    for relative, digest in records:
        current = _REPOSITORY_ROOT
        parts = relative.split("/")
        for part in parts[:-1]:
            current = os.path.join(current, part)
            if current in verified_directories:
                continue
            try:
                directory_status = os.lstat(current)
            except OSError:
                return False
            if not stat.S_ISDIR(directory_status.st_mode) or _is_reparse(
                directory_status
            ):
                return False
            verified_directories.add(current)
        path = os.path.join(current, parts[-1])
        try:
            common = os.path.commonpath(
                (_REPOSITORY_ROOT, os.path.realpath(path))
            )
            if common != _REPOSITORY_ROOT:
                return False
        except ValueError:
            return False
        worktree = _safe_regular_file(path, maximum_bytes=_MAX_TRACKED_FILE_BYTES)
        blob = blobs.get(digest)
        if worktree is None or blob is None:
            return False
        total += len(worktree)
        if total > _MAX_TRACKED_TREE_BYTES:
            return False
    request = b"".join(
        relative.encode("utf-8") + b"\n" for relative, _ in records
    )
    canonical_hashes = _git(
        "hash-object",
        "--stdin-paths",
        input_payload=request,
    )
    if canonical_hashes is None:
        return False
    try:
        actual = canonical_hashes.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return False
    expected = [digest for _, digest in records]
    digest_length = 40 if object_format == "sha1" else 64
    return bool(
        len(actual) == len(expected)
        and all(len(digest) == digest_length for digest in actual)
        and actual == expected
    )


def _verify_exact_checkout() -> None:
    try:
        repository_status = os.lstat(_REPOSITORY_ROOT)
        git_status = os.lstat(_GIT_DIRECTORY)
    except OSError:
        _bootstrap_error("repository metadata is unavailable")
    if (
        not stat.S_ISDIR(repository_status.st_mode)
        or _is_reparse(repository_status)
        or not stat.S_ISDIR(git_status.st_mode)
        or _is_reparse(git_status)
    ):
        _bootstrap_error("repository or Git metadata is indirect")

    local_config = _git(
        "config",
        "--local",
        "--no-includes",
        "--null",
        "--name-only",
        "--list",
    )
    if _dangerous_local_config(local_config):
        _bootstrap_error("local Git configuration can alter producer bytes")
    if not _metadata_file_empty("info/attributes") or not _metadata_file_empty(
        "config.worktree"
    ):
        _bootstrap_error("worktree-specific attributes or configuration are active")

    commit = _git_text("rev-parse", "--verify", "HEAD^{commit}")
    object_format = _git_text("rev-parse", "--show-object-format")
    normal = _git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    ignored = _git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        "--ignore-submodules=none",
    )
    index = _git("ls-files", "-v", "-z", "--cached", "--")
    if commit is None or object_format is None or normal != b"":
        _bootstrap_error("checkout is missing, unreadable, or not clean")
    if not _ignored_tools_are_absent(ignored):
        _bootstrap_error("ignored or untracked executable content exists under Tools")
    if index is None:
        _bootstrap_error("Git index is unavailable")
    index_records = [record for record in index.split(b"\0") if record]
    if not index_records or not all(
        record.startswith(b"H ") for record in index_records
    ):
        _bootstrap_error("Git index contains hidden worktree flags")

    tree = _tracked_tree(_git("ls-tree", "-r", "-z", commit))
    if tree is None:
        _bootstrap_error("commit tree is unsupported or unavailable")
    digests = sorted({digest for _, digest in tree})
    request = b"".join(digest.encode("ascii") + b"\n" for digest in digests)
    blobs = _git_blobs(
        _git("cat-file", "--batch", input_payload=request),
        digests,
        object_format,
    )
    if blobs is None or not _worktree_matches(tree, blobs, object_format):
        _bootstrap_error(
            "worktree canonical content does not match the acknowledged commit"
        )

    commit_after = _git_text("rev-parse", "--verify", "HEAD^{commit}")
    normal_after = _git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    ignored_after = _git(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        "--ignore-submodules=none",
    )
    index_after = _git("ls-files", "-v", "-z", "--cached", "--")
    if (
        commit_after != commit
        or normal_after != b""
        or not _ignored_tools_are_absent(ignored_after)
        or index_after != index
    ):
        _bootstrap_error("checkout changed during producer verification")


# Re-enter in Python's isolated, no-site mode before loading product code.  The
# interpreter executable and its startup are part of the documented trust base.
if not sys.flags.isolated or not sys.flags.no_site:
    try:
        isolated_argv = [
            sys.executable,
            "-I",
            "-S",
            _SCRIPT_PATH,
            *sys.argv[1:],
        ]
        if os.name == "nt":
            isolated_returncode = subprocess.run(
                isolated_argv,
                check=False,
            ).returncode
        else:
            os.execv(sys.executable, isolated_argv)
            _bootstrap_error("isolated Python replacement unexpectedly returned")
    except OSError as error:
        _bootstrap_error(f"could not enter isolated Python: {type(error).__name__}")
    raise SystemExit(isolated_returncode)

sys.dont_write_bytecode = True
sys.pycache_prefix = os.path.join(
    os.environ.get("TEMP", os.getcwd()),
    f".dcsmizzer-no-bytecode-{os.getpid()}-{time.time_ns()}",
)

if _provenance_sensitive_invocation(sys.argv[1:]):
    _verify_exact_checkout()

sys.path.insert(0, _TOOLS_ROOT)

from dcsmizzer.cli import main  # noqa: E402


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

raise SystemExit(main())
