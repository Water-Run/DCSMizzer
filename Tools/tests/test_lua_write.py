from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.lua import (  # noqa: E402
    LuaField,
    LuaSyntaxError,
    LuaTable,
    parse_lua_bytes,
)
from dcsmizzer.lua_write import (  # noqa: E402
    LuaSerializationError,
    dump_lua_assignment,
    json_to_lua,
)


class LuaWriterTests(unittest.TestCase):
    def test_parser_rejects_non_finite_decimal_numbers(self) -> None:
        for raw in (b"1e999", b"-1e999"):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(
                    LuaSyntaxError,
                    "non-finite number",
                ):
                    parse_lua_bytes(b"value = " + raw)

    def test_json_table_round_trips_sparse_numeric_keys_and_unicode(self) -> None:
        value = json_to_lua(
            {
                "name": "拦截\n任务",
                "pylons": {
                    "$fields": [
                        {"key": 1, "value": {"CLSID": "{ONE}"}},
                        {"key": 4, "value": {"CLSID": "{TANK}"}},
                        {"key": 7, "value": {"CLSID": "{SEVEN}"}},
                    ]
                },
                "enabled": True,
                "ratio": 1.25e-5,
            }
        )

        encoded = dump_lua_assignment("mission", value)
        parsed = parse_lua_bytes(encoded).document.get("mission")

        self.assertEqual(parsed, value)
        self.assertIn("拦截".encode(), encoded)
        self.assertIn(b"\\n", encoded)

    def test_json_arrays_become_one_based_lua_tables(self) -> None:
        value = json_to_lua(["first", "second"])

        self.assertEqual(
            value,
            LuaTable(
                (
                    LuaField(key=1, value="first"),
                    LuaField(key=2, value="second"),
                )
            ),
        )

    def test_writer_is_deterministic(self) -> None:
        value = json_to_lua({"z": 2, "a": 1})

        first = dump_lua_assignment("options", value)
        second = dump_lua_assignment("options", value)

        self.assertEqual(first, second)

    def test_writer_rejects_values_that_are_not_stable_lua_data(self) -> None:
        invalid_values = (
            None,
            math.nan,
            math.inf,
            {"$fields": [{"key": 1, "value": None}]},
            {
                "$fields": [
                    {"key": 1, "value": "a"},
                    {"key": 1, "value": "b"},
                ]
            },
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(LuaSerializationError):
                    json_to_lua(value)

    def test_writer_rejects_invalid_assignment_name(self) -> None:
        with self.assertRaises(LuaSerializationError):
            dump_lua_assignment("mission.name", LuaTable(()))


if __name__ == "__main__":
    unittest.main()
