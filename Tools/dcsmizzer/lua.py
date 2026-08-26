from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


class LuaDataError(ValueError):
    """Base class for safe Lua data parsing errors."""


class LuaEncodingError(LuaDataError):
    """The byte stream is not one of the accepted mission encodings."""


class LuaSyntaxError(LuaDataError):
    """The input is outside the accepted data-only Lua subset."""


class LuaLimitError(LuaDataError):
    """A configured parser resource limit was exceeded."""


@dataclass(frozen=True)
class LuaLimits:
    max_input_bytes: int = 512 * 1024 * 1024
    max_depth: int = 512
    max_nodes: int = 10_000_000
    max_string_chars: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_depth", self.max_depth),
            ("max_nodes", self.max_nodes),
            ("max_string_chars", self.max_string_chars),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class LuaField:
    key: str | int | float
    value: Any
    implicit: bool = False


_MISSING = object()


@dataclass(frozen=True)
class LuaTable:
    fields: tuple[LuaField, ...]

    def get(self, key: str | int | float, default: Any = None) -> Any:
        result = _MISSING
        for field in self.fields:
            if field.key == key:
                result = field.value
        return default if result is _MISSING else result

    def has(self, key: str | int | float) -> bool:
        return any(field.key == key for field in self.fields)

    def numeric_items(self) -> tuple[LuaField, ...]:
        return tuple(
            sorted(
                (
                    field
                    for field in self.fields
                    if isinstance(field.key, (int, float))
                    and not isinstance(field.key, bool)
                ),
                key=lambda field: field.key,
            )
        )


@dataclass(frozen=True)
class LuaAssignment:
    name: str
    value: Any
    local: bool


@dataclass(frozen=True)
class LuaDocument:
    assignments: tuple[LuaAssignment, ...]
    returned: Any = None

    def get(self, name: str, default: Any = None) -> Any:
        result = _MISSING
        for assignment in self.assignments:
            if assignment.name == name:
                result = assignment.value
        return default if result is _MISSING else result


@dataclass(frozen=True)
class ParsedLuaBytes:
    encoding: str
    document: LuaDocument


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(
    r"""
    [+-]?
    (?:
        0[xX][0-9A-Fa-f]+
        |
        (?:
            (?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)
            (?:[eE][+-]?[0-9]+)?
        )
    )
    """,
    re.VERBOSE,
)


def parse_lua(
    text: str,
    *,
    limits: LuaLimits | None = None,
) -> LuaDocument:
    selected_limits = limits or LuaLimits()
    input_size = len(text.encode("utf-8"))
    parser = _Parser(text, selected_limits, input_size)
    return parser.parse_document()


def parse_lua_bytes(
    data: bytes,
    *,
    limits: LuaLimits | None = None,
) -> ParsedLuaBytes:
    selected_limits = limits or LuaLimits()
    if len(data) > selected_limits.max_input_bytes:
        raise LuaLimitError("input byte limit exceeded")

    if data.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as error:
            raise LuaEncodingError("invalid UTF-8 BOM input") from error
    else:
        try:
            text = data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            try:
                text = data.decode("cp1251")
                encoding = "cp1251"
            except UnicodeDecodeError as error:
                raise LuaEncodingError(
                    "input is neither UTF-8 nor CP1251"
                ) from error

    parser = _Parser(text, selected_limits, len(data))
    return ParsedLuaBytes(
        encoding=encoding,
        document=parser.parse_document(),
    )


class _Parser:
    def __init__(self, text: str, limits: LuaLimits, input_size: int) -> None:
        if input_size > limits.max_input_bytes:
            raise LuaLimitError("input byte limit exceeded")
        self.text = text
        self.length = len(text)
        self.position = 0
        self.limits = limits
        self.nodes = 0
        self.variables: dict[str, Any] = {}
        self.assignments: list[LuaAssignment] = []

    def parse_document(self) -> LuaDocument:
        returned: Any = None
        saw_return = False
        self._skip_trivia()
        while not self._at_end():
            if saw_return:
                self._syntax("return must be the final statement")

            local = False
            name = self._parse_identifier()
            if name == "local":
                local = True
                self._skip_trivia()
                name = self._parse_identifier()
            elif name == "return":
                self._skip_trivia()
                returned = self._parse_value(depth=0)
                saw_return = True
                self._skip_trivia()
                if self._peek(";"):
                    self.position += 1
                    self._skip_trivia()
                continue
            elif name in {"function", "do", "if", "for", "while", "repeat"}:
                self._syntax(f"executable statement {name!r} is not allowed")

            self._skip_trivia()
            self._expect("=")
            self._skip_trivia()
            value = self._parse_value(depth=0)
            self.variables[name] = value
            self.assignments.append(
                LuaAssignment(
                    name=name,
                    value=value,
                    local=local,
                )
            )
            self._skip_trivia()
            if self._peek(";"):
                self.position += 1
                self._skip_trivia()

        return LuaDocument(
            assignments=tuple(self.assignments),
            returned=returned,
        )

    def _parse_value(self, *, depth: int) -> Any:
        self._skip_trivia()
        if self._at_end():
            self._syntax("expected value, reached end of input")
        character = self.text[self.position]

        if character == "{":
            return self._parse_table(depth=depth + 1)
        if character in {'"', "'"}:
            value = self._parse_short_string()
            self._bump_node()
            return value
        if self._long_bracket_level(self.position) is not None:
            value = self._parse_long_string()
            self._bump_node()
            return value
        if character.isdigit() or character in "+-.":
            value = self._parse_number()
            self._bump_node()
            return value

        identifier = self._parse_identifier()
        if identifier == "true":
            self._bump_node()
            return True
        if identifier == "false":
            self._bump_node()
            return False
        if identifier == "nil":
            self._bump_node()
            return None
        if identifier == "_":
            return self._parse_identity_wrapper(depth=depth)

        self._skip_trivia()
        if self._peek("(") or self._peek(".") or self._peek(":"):
            self._syntax(f"function or member access {identifier!r} is not allowed")
        if identifier not in self.variables:
            self._syntax(f"undefined identifier {identifier!r}")
        return self.variables[identifier]

    def _parse_table(self, *, depth: int) -> LuaTable:
        if depth > self.limits.max_depth:
            raise LuaLimitError("table depth limit exceeded")
        self._bump_node()
        self._expect("{")
        self._skip_trivia()
        fields: list[LuaField] = []
        implicit_index = 1

        while not self._peek("}"):
            if self._at_end():
                self._syntax("unterminated table")

            if self._peek("[") and self._long_bracket_level(self.position) is None:
                self.position += 1
                key = self._parse_value(depth=depth)
                if not isinstance(key, (str, int, float)) or isinstance(key, bool):
                    self._syntax("table key must be a string or number")
                self._skip_trivia()
                self._expect("]")
                self._skip_trivia()
                self._expect("=")
                self._skip_trivia()
                value = self._parse_value(depth=depth)
                fields.append(LuaField(key=key, value=value))
            else:
                bare_key = self._try_bare_key()
                if bare_key is not None:
                    self._skip_trivia()
                    self._expect("=")
                    self._skip_trivia()
                    value = self._parse_value(depth=depth)
                    fields.append(LuaField(key=bare_key, value=value))
                else:
                    value = self._parse_value(depth=depth)
                    fields.append(
                        LuaField(
                            key=implicit_index,
                            value=value,
                            implicit=True,
                        )
                    )
                    implicit_index += 1

            self._skip_trivia()
            if self._peek(",") or self._peek(";"):
                self.position += 1
                self._skip_trivia()
            elif not self._peek("}"):
                self._syntax("expected ',', ';', or '}' after table field")

        self.position += 1
        return LuaTable(fields=tuple(fields))

    def _try_bare_key(self) -> str | None:
        saved = self.position
        match = _IDENTIFIER.match(self.text, self.position)
        if match is None:
            return None
        name = match.group(0)
        self.position = match.end()
        self._skip_trivia()
        if self._peek("="):
            return name
        self.position = saved
        return None

    def _parse_identity_wrapper(self, *, depth: int) -> str:
        self._skip_trivia()
        self._expect("(")
        self._skip_trivia()
        if self._at_end() or self.text[self.position] not in {'"', "'"}:
            self._syntax("_() accepts one quoted string only")
        value = self._parse_short_string()
        self._bump_node()
        self._skip_trivia()
        self._expect(")")
        return value

    def _parse_number(self) -> int | float:
        match = _NUMBER.match(self.text, self.position)
        if match is None:
            self._syntax("invalid number")
        raw = match.group(0)
        self.position = match.end()
        if raw.lower().lstrip("+-").startswith("0x"):
            sign = -1 if raw.startswith("-") else 1
            digits = raw.lstrip("+-")[2:]
            return sign * int(digits, 16)
        value = float(raw)
        if not math.isfinite(value):
            self._syntax("non-finite number")
        return (
            int(value)
            if value.is_integer() and "." not in raw and "e" not in raw.lower()
            else value
        )

    def _parse_short_string(self) -> str:
        quote = self.text[self.position]
        self.position += 1
        result: list[str] = []
        length = 0

        while not self._at_end():
            character = self.text[self.position]
            self.position += 1
            if character == quote:
                return "".join(result)
            if character in "\r\n":
                self._syntax("newline in quoted string")
            if character != "\\":
                result.append(character)
                length += 1
                self._check_string_length(length)
                continue
            if self._at_end():
                self._syntax("unterminated string escape")
            escaped = self.text[self.position]
            self.position += 1
            simple = {
                "a": "\a",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "v": "\v",
                "\\": "\\",
                '"': '"',
                "'": "'",
            }
            if escaped in simple:
                decoded = simple[escaped]
            elif escaped == "z":
                self._skip_whitespace_only()
                decoded = ""
            elif escaped == "x":
                digits = self.text[self.position : self.position + 2]
                if len(digits) != 2 or not all(
                    character in "0123456789abcdefABCDEF" for character in digits
                ):
                    self._syntax("invalid hexadecimal string escape")
                self.position += 2
                decoded = chr(int(digits, 16))
            elif escaped == "u":
                if not self._peek("{"):
                    self._syntax("invalid Unicode string escape")
                closing = self.text.find("}", self.position + 1)
                if closing < 0:
                    self._syntax("unterminated Unicode string escape")
                digits = self.text[self.position + 1 : closing]
                if not digits or not all(
                    character in "0123456789abcdefABCDEF" for character in digits
                ):
                    self._syntax("invalid Unicode string escape")
                self.position = closing + 1
                decoded = chr(int(digits, 16))
            elif escaped.isdigit():
                digits = escaped
                while (
                    len(digits) < 3
                    and not self._at_end()
                    and self.text[self.position].isdigit()
                ):
                    digits += self.text[self.position]
                    self.position += 1
                value = int(digits, 10)
                if value > 255:
                    self._syntax("decimal string escape exceeds 255")
                decoded = chr(value)
            elif escaped == "\n":
                decoded = "\n"
            elif escaped == "\r":
                if self._peek("\n"):
                    self.position += 1
                decoded = "\n"
            else:
                self._syntax(f"unsupported string escape \\{escaped}")
            result.append(decoded)
            length += len(decoded)
            self._check_string_length(length)

        self._syntax("unterminated quoted string")

    def _parse_long_string(self) -> str:
        level = self._long_bracket_level(self.position)
        if level is None:
            self._syntax("invalid long string")
        opener_length = level + 2
        self.position += opener_length
        if self._peek("\r\n"):
            self.position += 2
        elif self._peek("\n") or self._peek("\r"):
            self.position += 1
        closing = "]" + ("=" * level) + "]"
        end = self.text.find(closing, self.position)
        if end < 0:
            self._syntax("unterminated long string")
        value = self.text[self.position:end]
        self._check_string_length(len(value))
        self.position = end + len(closing)
        return value

    def _parse_identifier(self) -> str:
        self._skip_trivia()
        match = _IDENTIFIER.match(self.text, self.position)
        if match is None:
            self._syntax("expected identifier")
        self.position = match.end()
        return match.group(0)

    def _skip_trivia(self) -> None:
        while True:
            self._skip_whitespace_only()
            if not self._peek("--"):
                return
            self.position += 2
            level = self._long_bracket_level(self.position)
            if level is None:
                newline = self.text.find("\n", self.position)
                self.position = self.length if newline < 0 else newline + 1
                continue
            opener_length = level + 2
            self.position += opener_length
            closing = "]" + ("=" * level) + "]"
            end = self.text.find(closing, self.position)
            if end < 0:
                self._syntax("unterminated block comment")
            self.position = end + len(closing)

    def _skip_whitespace_only(self) -> None:
        while not self._at_end() and self.text[self.position].isspace():
            self.position += 1

    def _long_bracket_level(self, position: int) -> int | None:
        if position >= self.length or self.text[position] != "[":
            return None
        cursor = position + 1
        while cursor < self.length and self.text[cursor] == "=":
            cursor += 1
        if cursor < self.length and self.text[cursor] == "[":
            return cursor - position - 1
        return None

    def _expect(self, value: str) -> None:
        if not self._peek(value):
            self._syntax(f"expected {value!r}")
        self.position += len(value)

    def _peek(self, value: str) -> bool:
        return self.text.startswith(value, self.position)

    def _at_end(self) -> bool:
        return self.position >= self.length

    def _bump_node(self) -> None:
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise LuaLimitError("node limit exceeded")

    def _check_string_length(self, length: int) -> None:
        if length > self.limits.max_string_chars:
            raise LuaLimitError("string length limit exceeded")

    def _syntax(self, message: str) -> None:
        line = self.text.count("\n", 0, self.position) + 1
        last_newline = self.text.rfind("\n", 0, self.position)
        column = self.position - last_newline
        raise LuaSyntaxError(f"{message} at line {line}, column {column}")
