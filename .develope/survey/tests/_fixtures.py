from __future__ import annotations

import warnings
import zipfile
from collections.abc import Mapping
from pathlib import Path


CORE_MEMBERS: dict[str, bytes] = {
    "mission": b"mission = {}\n",
    "options": b"options = {}\n",
    "warehouses": b"warehouses = {}\n",
    "l10n/DEFAULT/dictionary": b"dictionary = {}\n",
    "l10n/DEFAULT/mapResource": b"mapResource = {}\n",
}


def write_miz(
    path: Path,
    *,
    members: Mapping[str, bytes] | None = None,
    duplicate_member: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> None:
    payloads = dict(CORE_MEMBERS if members is None else members)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, payload in payloads.items():
            archive.writestr(name, payload)
        if duplicate_member is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(duplicate_member, b"duplicate")


def corrupt_stored_member(path: Path, marker: bytes) -> None:
    content = bytearray(path.read_bytes())
    offset = content.find(marker)
    if offset < 0 or content.find(marker, offset + 1) >= 0:
        raise AssertionError("marker must occur exactly once in the ZIP")
    content[offset] ^= 0x01
    path.write_bytes(content)
