from __future__ import annotations

import sys
import unittest
from pathlib import Path

SURVEY_ROOT = Path(__file__).resolve().parents[1]
if str(SURVEY_ROOT) not in sys.path:
    sys.path.insert(0, str(SURVEY_ROOT))

from dcsmizzer_survey.lua import (
    LuaEncodingError,
    LuaLimitError,
    LuaLimits,
    LuaSyntaxError,
    LuaTable,
    parse_lua,
    parse_lua_bytes,
)


class LuaDataParserTests(unittest.TestCase):
    def test_table_preserves_bare_numeric_string_implicit_and_duplicate_keys(self) -> None:
        # Would fail if raw Lua fields are collapsed into a Python dict.
        text = r'''
            -- data-only mission fragment
            mission = {
                Year = 1988,
                [4] = "numeric",
                ["СS"] = "confusable",
                "implicit",
                duplicate = "first",
                duplicate = "last",
                absent = nil,
            }
        '''

        document = parse_lua(text)
        mission = document.get("mission")

        self.assertIsInstance(mission, LuaTable)
        self.assertEqual(
            [field.key for field in mission.fields],
            ["Year", 4, "СS", 1, "duplicate", "duplicate", "absent"],
        )
        self.assertEqual(mission.get("Year"), 1988)
        self.assertEqual(mission.get(4), "numeric")
        self.assertEqual(mission.get("СS"), "confusable")
        self.assertEqual(mission.get(1), "implicit")
        self.assertEqual(mission.get("duplicate"), "last")
        self.assertIsNone(mission.get("absent"))

    def test_numbers_strings_comments_identity_wrapper_and_return_are_data_only(self) -> None:
        # Would fail if common serialized literals are mistaken for executable Lua.
        text = r'''
            --[=[ block comment ]=]
            local payload = {
                decimal = -12.5e+2;
                hex = 0x2A;
                escaped = "line\nquote\"slash\\";
                single = 'tab\t';
                translated = _("safe text");
                truth = true;
                lie = false;
            }
            return payload
        '''

        document = parse_lua(text)
        payload = document.returned

        self.assertIsInstance(payload, LuaTable)
        self.assertEqual(payload.get("decimal"), -1250.0)
        self.assertEqual(payload.get("hex"), 42)
        self.assertEqual(payload.get("escaped"), 'line\nquote"slash\\')
        self.assertEqual(payload.get("single"), "tab\t")
        self.assertEqual(payload.get("translated"), "safe text")
        self.assertIs(payload.get("truth"), True)
        self.assertIs(payload.get("lie"), False)

    def test_utf8_bom_and_cp1251_are_detected_without_loss(self) -> None:
        # Would fail if decoding silently replaces bytes or assumes UTF-8 only.
        utf8 = parse_lua_bytes(b"\xef\xbb\xbfmission = { text = \"ok\" }")
        cp1251_text = 'mission = { text = "Привет" }'
        cp1251 = parse_lua_bytes(cp1251_text.encode("cp1251"))

        self.assertEqual(utf8.encoding, "utf-8-sig")
        self.assertEqual(utf8.document.get("mission").get("text"), "ok")
        self.assertEqual(cp1251.encoding, "cp1251")
        self.assertEqual(cp1251.document.get("mission").get("text"), "Привет")

    def test_undecodable_input_has_distinct_encoding_error(self) -> None:
        # Would fail if undecodable bytes become a generic syntax error.
        with self.assertRaises(LuaEncodingError):
            parse_lua_bytes(b'mission = { text = "\x98" }')

    def test_function_calls_and_definitions_are_rejected_not_executed(self) -> None:
        # Would fail if the parser grows into a Lua evaluator.
        with self.assertRaises(LuaSyntaxError):
            parse_lua('mission = require("unsafe")')
        with self.assertRaises(LuaSyntaxError):
            parse_lua("function danger() return 1 end")
        with self.assertRaises(LuaSyntaxError):
            parse_lua('mission = os.execute("unsafe")')

    def test_depth_node_string_and_input_limits_are_distinct(self) -> None:
        # Would fail if hostile resource exhaustion bypasses parser limits.
        with self.assertRaises(LuaLimitError):
            parse_lua("value = {{{{1}}}}", limits=LuaLimits(max_depth=3))
        with self.assertRaises(LuaLimitError):
            parse_lua("value = {1, 2, 3}", limits=LuaLimits(max_nodes=3))
        with self.assertRaises(LuaLimitError):
            parse_lua('value = "abcd"', limits=LuaLimits(max_string_chars=3))
        with self.assertRaises(LuaLimitError):
            parse_lua_bytes(
                b"value = {1}",
                limits=LuaLimits(max_input_bytes=8),
            )


if __name__ == "__main__":
    unittest.main()
