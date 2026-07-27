"""Deterministic serialization for DCS data-only Lua tables."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .lua import LuaField, LuaTable


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FIELD_WRAPPER = "$fields"


class LuaSerializationError(ValueError):
    """A value cannot be represented safely and deterministically."""


def json_to_lua(value: Any, *, path: str = "$") -> Any:
    """Convert decoded JSON into the explicit Lua data model.

    JSON objects normally become string-keyed Lua tables and JSON arrays
    become one-based numeric tables. A ``{"$fields": [...]}`` wrapper can
    represent sparse numeric or mixed-key tables.
    """

    if value is None:
        raise LuaSerializationError(f"{path}: null/nil table values are forbidden")
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LuaSerializationError(f"{path}: non-finite number is forbidden")
        return value
    if isinstance(value, Mapping):
        if _FIELD_WRAPPER in value:
            if len(value) != 1:
                raise LuaSerializationError(
                    f"{path}: {_FIELD_WRAPPER!r} cannot have sibling keys"
                )
            return _explicit_fields(value[_FIELD_WRAPPER], path=path)
        fields: list[LuaField] = []
        for key, child in value.items():
            if not isinstance(key, str):
                raise LuaSerializationError(
                    f"{path}: ordinary JSON object keys must be strings"
                )
            fields.append(
                LuaField(
                    key=key,
                    value=json_to_lua(child, path=f"{path}.{key}"),
                )
            )
        return LuaTable(tuple(fields))
    if isinstance(value, Sequence) and not isinstance(
        value,
        bytes | bytearray | memoryview | str,
    ):
        return LuaTable(
            tuple(
                LuaField(
                    key=index,
                    value=json_to_lua(child, path=f"{path}[{index}]"),
                )
                for index, child in enumerate(value, start=1)
            )
        )
    raise LuaSerializationError(
        f"{path}: unsupported value type {type(value).__name__}"
    )


def dump_lua_assignment(name: str, value: Any) -> bytes:
    """Serialize one global assignment as canonical UTF-8 Lua data."""

    if _IDENTIFIER.fullmatch(name) is None:
        raise LuaSerializationError(f"invalid Lua assignment name: {name!r}")
    body = _dump_value(value, depth=0)
    return f"{name} = {body}\n".encode("utf-8")


def _explicit_fields(value: Any, *, path: str) -> LuaTable:
    if not isinstance(value, list):
        raise LuaSerializationError(f"{path}.{_FIELD_WRAPPER}: expected an array")
    fields: list[LuaField] = []
    keys: set[str | int | float] = set()
    for index, record in enumerate(value):
        record_path = f"{path}.{_FIELD_WRAPPER}[{index}]"
        if not isinstance(record, Mapping):
            raise LuaSerializationError(f"{record_path}: expected an object")
        if set(record) != {"key", "value"}:
            raise LuaSerializationError(
                f"{record_path}: expected exactly 'key' and 'value'"
            )
        key = record["key"]
        if (
            not isinstance(key, str | int | float)
            or isinstance(key, bool)
            or (isinstance(key, float) and not math.isfinite(key))
        ):
            raise LuaSerializationError(
                f"{record_path}.key: expected a finite string or number"
            )
        if key in keys:
            raise LuaSerializationError(f"{record_path}.key: duplicate key {key!r}")
        keys.add(key)
        fields.append(
            LuaField(
                key=key,
                value=json_to_lua(record["value"], path=f"{record_path}.value"),
            )
        )
    return LuaTable(tuple(fields))


def _dump_value(value: Any, *, depth: int) -> str:
    if isinstance(value, LuaTable):
        return _dump_table(value, depth=depth)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LuaSerializationError("non-finite number is forbidden")
        return repr(value)
    if isinstance(value, str):
        return f'"{_escape_string(value)}"'
    if value is None:
        raise LuaSerializationError("nil table values are forbidden")
    raise LuaSerializationError(
        f"unsupported Lua value type {type(value).__name__}"
    )


def _dump_table(table: LuaTable, *, depth: int) -> str:
    if not table.fields:
        return "{}"
    indent = "    " * depth
    child_indent = "    " * (depth + 1)
    lines = ["{"]
    for field in table.fields:
        key = _dump_key(field.key)
        child = _dump_value(field.value, depth=depth + 1)
        if isinstance(field.value, LuaTable) and field.value.fields:
            child_lines = child.splitlines()
            lines.append(f"{child_indent}[{key}] = {child_lines[0]}")
            lines.extend(child_lines[1:-1])
            lines.append(f"{child_lines[-1]},")
        else:
            lines.append(f"{child_indent}[{key}] = {child},")
    lines.append(f"{indent}}}")
    return "\n".join(lines)


def _dump_key(key: str | int | float) -> str:
    if isinstance(key, bool):
        raise LuaSerializationError("boolean table key is forbidden")
    if isinstance(key, str):
        return f'"{_escape_string(key)}"'
    if isinstance(key, int):
        return str(key)
    if isinstance(key, float) and math.isfinite(key):
        return repr(key)
    raise LuaSerializationError("table key must be a finite string or number")


def _escape_string(value: str) -> str:
    replacements = {
        "\\": "\\\\",
        '"': '\\"',
        "\a": "\\a",
        "\b": "\\b",
        "\f": "\\f",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\v": "\\v",
    }
    result: list[str] = []
    for character in value:
        replacement = replacements.get(character)
        if replacement is not None:
            result.append(replacement)
            continue
        codepoint = ord(character)
        if codepoint < 32 or codepoint == 127:
            result.append(f"\\{codepoint:03d}")
        else:
            result.append(character)
    return "".join(result)
