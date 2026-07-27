from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.dcs_static import (  # noqa: E402
    payload_fingerprint,
    payload_index_report,
    payload_match_report,
    payload_report,
)
from dcsmizzer import dcs_static as dcs_static_module  # noqa: E402


PAYLOADS = """
local unitPayloads = {
  name = "Fixture Plane",
  payloads = {
    [1] = {
      name = "Intercept",
      displayName = _("Ready alert"),
      category = "Air-to-Air",
      pylons = {
        [1] = { CLSID = "{A}", num = 1 },
        [2] = { CLSID = "{B}", num = 2 },
      },
      tasks = { [1] = 11, },
    },
    [2] = {
      name = "Alert",
      displayName = _("Alternate alert"),
      category = "Air-to-Air",
      pylons = {
        [1] = { CLSID = "{B}", num = 2 },
        [2] = { CLSID = "{A}", num = 1 },
      },
      tasks = { [2] = 11, [1] = 18, },
    },
    [3] = {
      name = "Strike",
      pylons = {
        [1] = { CLSID = "{A}", num = 1 },
        [2] = { CLSID = "{C}", num = 3 },
      },
      tasks = { [1] = 31, },
    },
    [5] = {
      name = "Configured weapon",
      pylons = {
        [1] = {
          CLSID = "{F}",
          num = 6,
          settings = {
            GUI_fuze_type = 1,
            arm_delay = 0.5,
          },
        },
      },
      tasks = { [1] = 32, },
    },
  },
}
return unitPayloads
"""

BROKEN_PAYLOADS = """
local unitPayloads = {
  name = "Fixture Plane",
  payloads = {
    [1] = {
      name = "Broken duplicate station",
      pylons = {
        [1] = { CLSID = "{D}", num = 5 },
        [2] = { CLSID = "{E}", num = 5 },
      },
      tasks = { [1] = 31, },
    },
  },
}
return unitPayloads
"""

SHADOWED_PAYLOADS = """
local unitPayloads = {
  name = "Shadow Plane",
  payloads = {
    [1] = {
      name = "Overwritten preset",
      pylons = {
        [1] = { CLSID = "{OLD}", num = 1 },
      },
      tasks = { [1] = 11, },
    },
    [1] = {
      name = "Effective preset",
      pylons = {
        [1] = { CLSID = "{SHADOWED}", num = 1 },
        [1] = { CLSID = "{EFFECTIVE}", num = 2 },
      },
      tasks = {
        [1] = 33,
        [1] = 31,
      },
    },
  },
}
return unitPayloads
"""

AMBIGUOUS_CONFIGURED_PAYLOADS = """
local unitPayloads = {
  name = "Configured Plane",
  payloads = {
    [1] = {
      name = "Fuze A",
      pylons = {
        [1] = {
          CLSID = "{CONFIGURED}",
          num = 1,
          settings = { fuze = 1 },
        },
      },
      tasks = { [1] = 11 },
    },
    [2] = {
      name = "Fuze B",
      pylons = {
        [1] = {
          CLSID = "{CONFIGURED}",
          num = 1,
          settings = { fuze = 2 },
        },
      },
      tasks = { [1] = 11 },
    },
  },
}
return unitPayloads
"""


def _fixture_root(temp_dir: str) -> Path:
    steamapps = Path(temp_dir) / "steamapps"
    dcs_root = steamapps / "common" / "DCSWorld"
    payload_root = (
        dcs_root / "MissionEditor" / "data" / "scripts" / "UnitPayloads"
    )
    payload_root.mkdir(parents=True)
    (payload_root / "Fixture.lua").write_text(PAYLOADS, encoding="utf-8")
    (steamapps / "appmanifest_223750.acf").write_text(
        '"AppState" { "buildid" "424242" }',
        encoding="utf-8",
    )
    return dcs_root


class PayloadFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_order_independent_but_metadata_bound(self) -> None:
        first = payload_fingerprint(
            "Fixture Plane",
            [
                {"num": 2, "CLSID": "{B}"},
                {"num": 1, "CLSID": "{A}"},
            ],
            tasks=[18, 11, 18],
            preset_name="Alert",
            display_name="Alternate alert",
            category="Air-to-Air",
        )
        reordered = payload_fingerprint(
            "Fixture Plane",
            {
                1: "{A}",
                2: "{B}",
            },
            tasks=[11, 18],
            preset_name="Alert",
            display_name="Alternate alert",
            category="Air-to-Air",
        )
        renamed = payload_fingerprint(
            "Fixture Plane",
            {1: "{A}", 2: "{B}"},
            tasks=[11, 18],
            preset_name="Different name",
            display_name="Alternate alert",
            category="Air-to-Air",
        )

        self.assertEqual(first, reordered)
        self.assertEqual(
            first["normalized"]["pylons"],
            [
                {"num": 1, "CLSID": "{A}"},
                {"num": 2, "CLSID": "{B}"},
            ],
        )
        self.assertEqual(first["normalized"]["tasks"], [11, 18])
        self.assertEqual(
            first["composition_sha256"],
            renamed["composition_sha256"],
        )
        self.assertNotEqual(first["preset_sha256"], renamed["preset_sha256"])
        self.assertEqual(len(first["composition_sha256"]), 64)
        self.assertEqual(len(first["preset_sha256"]), 64)
        clean = payload_fingerprint("Fixture Plane", {7: ""})
        self.assertEqual(
            clean["normalized"]["pylons"],
            [{"num": 7, "CLSID": ""}],
        )
        configured = payload_fingerprint(
            "Fixture Plane",
            [
                {
                    "num": 1,
                    "CLSID": "{A}",
                    "settings": {"fuze": 1},
                },
                {"num": 2, "CLSID": "{B}"},
            ],
            tasks=[11, 18],
            preset_name="Alert",
            display_name="Alternate alert",
            category="Air-to-Air",
        )
        self.assertEqual(
            configured["composition_sha256"],
            first["composition_sha256"],
        )
        self.assertNotEqual(
            configured["configured_composition_sha256"],
            first["configured_composition_sha256"],
        )

    def test_fingerprint_rejects_duplicate_station(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate_station"):
            payload_fingerprint(
                "Fixture Plane",
                [
                    {"num": 1, "CLSID": "{A}"},
                    {"num": 1, "CLSID": "{A}"},
                ],
            )

    def test_fingerprint_rejects_nonfinite_and_oversize_settings(self) -> None:
        for settings in (
            {"delay": float("nan")},
            {"label": "x" * (16 * 1024)},
        ):
            with self.subTest(settings=list(settings)):
                with self.assertRaisesRegex(ValueError, "invalid_settings"):
                    payload_fingerprint(
                        "Fixture Plane",
                        [
                            {
                                "num": 1,
                                "CLSID": "{A}",
                                "settings": settings,
                            }
                        ],
                    )


class PayloadMatchTests(unittest.TestCase):
    def test_exact_match_is_full_preset_and_source_version_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            report = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {2: "{B}", 1: "{A}"},
                tasks=[11],
                preset_name="Intercept",
                display_name="Ready alert",
                category="Air-to-Air",
            )

        self.assertEqual(report["classification"], "exact_observed_preset")
        self.assertTrue(report["verified_exact_observed_preset"])
        self.assertEqual(report["exact_match_count"], 1)
        self.assertEqual(report["matches"][0]["name"], "Intercept")
        self.assertEqual(report["dcs"]["steam_build_id"], "424242")
        self.assertIsNone(report["dcs"]["product_version"])
        binding = report["source_binding"]
        self.assertEqual(binding["files_scanned"], 1)
        self.assertEqual(len(binding["payload_inventory_sha256"]), 64)
        self.assertEqual(
            binding["unit_type_sources"][0]["source"],
            "MissionEditor/data/scripts/UnitPayloads/Fixture.lua",
        )
        self.assertNotIn(temp_dir, json.dumps(report))

    def test_ambiguous_exact_composition_can_be_disambiguated_by_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            ambiguous = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
            )
            selected = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
                preset_name="Alert",
                tasks=[18, 11],
            )

        self.assertEqual(
            ambiguous["classification"],
            "ambiguous_observed_preset",
        )
        self.assertEqual(ambiguous["exact_match_count"], 2)
        self.assertFalse(ambiguous["verified_exact_observed_preset"])
        self.assertEqual(selected["classification"], "exact_observed_preset")
        self.assertEqual(selected["matches"][0]["name"], "Alert")

    def test_custom_composition_and_unknown_pair_are_not_overclaimed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            custom = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {2: "{B}", 3: "{C}"},
            )
            unknown = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {2: "{NOT-OBSERVED}"},
            )

        self.assertEqual(custom["classification"], "custom_composition_only")
        self.assertEqual(custom["unknown_pairs"], [])
        self.assertTrue(
            all(item["observed"] for item in custom["pair_evidence"])
        )
        self.assertEqual(unknown["classification"], "unknown_pair")
        self.assertEqual(
            unknown["unknown_pairs"],
            [{"num": 2, "CLSID": "{NOT-OBSERVED}"}],
        )
        self.assertFalse(unknown["pair_evidence"][0]["observed"])

    def test_metadata_mismatch_is_distinct_from_custom_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            report = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 3: "{C}"},
                tasks=[11],
            )

        self.assertEqual(
            report["classification"],
            "observed_composition_metadata_mismatch",
        )
        self.assertEqual(report["exact_composition_candidate_count"], 1)
        self.assertEqual(report["exact_match_count"], 0)

    def test_duplicate_query_and_source_station_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            payload_root = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            (payload_root / "Broken.lua").write_text(
                BROKEN_PAYLOADS,
                encoding="utf-8",
            )
            (payload_root / "InvalidTable.lua").write_text(
                """
                local unitPayloads = {
                    name = "Fixture Plane",
                    payloads = 42,
                }
                return unitPayloads
                """,
                encoding="utf-8",
            )
            duplicate = payload_match_report(
                dcs_root,
                "Fixture Plane",
                [
                    {"num": 1, "CLSID": "{A}"},
                    {"num": 1, "CLSID": "{B}"},
                ],
            )
            otherwise_exact = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
                tasks=[11],
                preset_name="Intercept",
                display_name="Ready alert",
                category="Air-to-Air",
            )
            presets = payload_report(dcs_root, "Fixture Plane")

        self.assertEqual(duplicate["classification"], "duplicate_station")
        self.assertFalse(duplicate["query"]["valid"])
        self.assertEqual(
            duplicate["query"]["issues"][0]["code"],
            "duplicate_station",
        )
        self.assertEqual(presets["source_integrity"]["invalid_presets"], 1)
        self.assertEqual(
            presets["source_integrity"]["invalid_payload_tables"],
            1,
        )
        self.assertFalse(
            presets["source_binding"]["candidate_enumeration_complete"]
        )
        self.assertEqual(
            otherwise_exact["classification"],
            "source_evidence_incomplete",
        )
        self.assertEqual(otherwise_exact["exact_match_count"], 1)
        self.assertFalse(otherwise_exact["verified_exact_observed_preset"])
        self.assertEqual(
            otherwise_exact["source_binding"][
                "unit_type_invalid_payload_tables"
            ],
            1,
        )
        self.assertEqual(
            otherwise_exact["source_binding"]["unit_type_invalid_presets"],
            1,
        )
        broken = next(
            preset
            for preset in presets["presets"]
            if preset["name"] == "Broken duplicate station"
        )
        self.assertFalse(broken["integrity"]["valid"])
        self.assertEqual(
            broken["integrity"]["issues"][0]["code"],
            "duplicate_station",
        )
        self.assertNotIn("fingerprints", broken)

    def test_store_settings_are_part_of_strict_preset_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            unspecified = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {6: "{F}"},
                tasks=[32],
                preset_name="Configured weapon",
            )
            mismatch = payload_match_report(
                dcs_root,
                "Fixture Plane",
                [
                    {
                        "num": 6,
                        "CLSID": "{F}",
                        "settings": {
                            "GUI_fuze_type": 2,
                            "arm_delay": 0.5,
                        },
                    }
                ],
                tasks=[32],
                preset_name="Configured weapon",
            )
            exact = payload_match_report(
                dcs_root,
                "Fixture Plane",
                [
                    {
                        "num": 6,
                        "CLSID": "{F}",
                        "settings": {
                            "arm_delay": 0.5,
                            "GUI_fuze_type": 1,
                        },
                    }
                ],
                tasks=[32],
                preset_name="Configured weapon",
            )

        self.assertEqual(
            unspecified["classification"],
            "observed_composition_configuration_unspecified",
        )
        self.assertEqual(
            unspecified["configuration_unspecified_stations"],
            [6],
        )
        self.assertEqual(
            mismatch["classification"],
            "observed_composition_configuration_mismatch",
        )
        self.assertEqual(exact["classification"], "exact_observed_preset")
        self.assertTrue(exact["verified_exact_observed_preset"])

    def test_unit_type_missing_and_limits_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            missing = payload_match_report(
                dcs_root,
                "Missing Plane",
                {1: "{A}"},
            )
            with self.assertRaisesRegex(ValueError, "at most 128"):
                payload_match_report(
                    dcs_root,
                    "Fixture Plane",
                    [
                        {"num": index + 1, "CLSID": f"{{{index}}}"}
                        for index in range(129)
                    ],
                )

        self.assertEqual(
            missing["classification"],
            "unit_type_not_observed",
        )
        self.assertEqual(missing["source_binding"]["unit_type_sources"], [])

    def test_inventory_binding_matches_the_static_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Fixture.lua"
            )
            report = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 3: "{C}"},
                preset_name="Strike",
            )
            expected_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

        source_record = report["source_binding"]["unit_type_sources"][0]
        self.assertEqual(
            source_record["source_sha256"],
            expected_sha256,
        )

    def test_duplicate_lua_table_keys_use_last_write_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Shadow.lua"
            )
            source.write_text(SHADOWED_PAYLOADS, encoding="utf-8")
            presets = payload_report(dcs_root, "Shadow Plane")
            index = payload_index_report(dcs_root)
            effective = payload_match_report(
                dcs_root,
                "Shadow Plane",
                {2: "{EFFECTIVE}"},
                tasks=[31],
                preset_name="Effective preset",
            )
            shadowed = payload_match_report(
                dcs_root,
                "Shadow Plane",
                {1: "{SHADOWED}"},
            )

        self.assertEqual(len(presets["presets"]), 1)
        preset = presets["presets"][0]
        self.assertEqual(preset["name"], "Effective preset")
        self.assertEqual(preset["pylons"][0]["num"], 2)
        self.assertEqual(preset["tasks"], [31])
        self.assertEqual(
            presets["source_integrity"][
                "shadowed_preset_table_assignments"
            ],
            1,
        )
        self.assertEqual(
            preset["normalization_evidence"],
            {
                "shadowed_pylon_table_assignments": 1,
                "shadowed_task_table_assignments": 1,
            },
        )
        self.assertEqual(
            index["normalization_evidence"],
            {
                "lua_table_semantics": (
                    "last assignment to a duplicate key wins"
                ),
                "shadowed_preset_table_assignments": 1,
                "shadowed_pylon_table_assignments": 1,
                "shadowed_task_table_assignments": 1,
            },
        )
        self.assertEqual(
            effective["classification"],
            "exact_observed_preset",
        )
        self.assertEqual(shadowed["classification"], "unknown_pair")

    def test_ambiguous_settings_candidates_are_not_exact_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Configured.lua"
            )
            source.write_text(
                AMBIGUOUS_CONFIGURED_PAYLOADS,
                encoding="utf-8",
            )

            report = payload_match_report(
                dcs_root,
                "Configured Plane",
                {1: "{CONFIGURED}"},
            )

        self.assertEqual(
            report["classification"],
            "observed_composition_configuration_unspecified",
        )
        self.assertEqual(report["configuration_candidate_count"], 2)
        self.assertEqual(report["configuration_gap_candidate_count"], 2)
        self.assertEqual(report["exact_match_count"], 0)
        self.assertEqual(report["configuration_unspecified_stations"], [1])
        self.assertFalse(report["verified_exact_observed_preset"])

    def test_parse_failure_completeness_is_scoped_by_safe_name_hint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            payload_root = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            (payload_root / "Procedural.lua").write_text(
                """
                local unitPayloads = {
                    name = "Procedural Plane",
                    payloads = BuildPayloads(),
                }
                return unitPayloads
                """,
                encoding="utf-8",
            )

            exact = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
                tasks=[11],
                preset_name="Intercept",
                display_name="Ready alert",
                category="Air-to-Air",
            )
            procedural = payload_match_report(
                dcs_root,
                "Procedural Plane",
                [],
            )

        self.assertEqual(exact["classification"], "exact_observed_preset")
        self.assertTrue(
            exact["source_binding"]["candidate_enumeration_complete"]
        )
        self.assertEqual(
            exact["source_binding"]["relevant_parse_failure_count"],
            0,
        )
        self.assertEqual(
            exact["source_binding"]["parse_failure_sources"][0][
                "unit_type_hint"
            ],
            "Procedural Plane",
        )
        self.assertEqual(
            procedural["classification"],
            "source_evidence_incomplete",
        )
        self.assertFalse(
            procedural["source_binding"]["candidate_enumeration_complete"]
        )
        self.assertEqual(
            procedural["source_binding"]["relevant_parse_failure_count"],
            1,
        )

    def test_unknown_parse_failure_blocks_strict_exact_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Unknown.lua"
            )
            source.write_text(
                'os.execute("not allowed")',
                encoding="utf-8",
            )

            report = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
                tasks=[11],
                preset_name="Intercept",
                display_name="Ready alert",
                category="Air-to-Air",
            )

        self.assertEqual(
            report["classification"],
            "source_evidence_incomplete",
        )
        self.assertEqual(report["exact_match_count"], 1)
        self.assertFalse(report["verified_exact_observed_preset"])
        self.assertFalse(
            report["source_binding"]["candidate_enumeration_complete"]
        )

    def test_payload_hash_and_parse_use_one_verified_byte_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source_bytes = PAYLOADS.replace(
                "Fixture Plane",
                "Snapshot Plane",
            ).encode("utf-8")
            source_path = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Fixture.lua"
            )
            original_reader = dcs_static_module._read_payload_source

            def snapshot_reader(path: Path) -> bytes:
                if path == source_path:
                    return source_bytes
                return original_reader(path)

            with patch(
                "dcsmizzer.dcs_static._read_payload_source",
                side_effect=snapshot_reader,
            ):
                report = payload_report(dcs_root, "Snapshot Plane")

        self.assertEqual(len(report["presets"]), 4)
        self.assertEqual(
            report["unit_type_sources"][0]["source_sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )

    def test_oversize_or_symlink_source_blocks_strict_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            payload_root = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            (payload_root / "Oversize.lua").write_bytes(
                b"x" * (512 * 1024 + 1)
            )

            oversize = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
            )

        self.assertEqual(
            oversize["classification"],
            "source_evidence_incomplete",
        )
        self.assertFalse(
            oversize["source_binding"]["candidate_enumeration_complete"]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            payload_root = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
            )
            target = Path(temp_dir) / "outside.lua"
            target.write_text(PAYLOADS, encoding="utf-8")
            link = payload_root / "Linked.lua"
            try:
                link.symlink_to(target)
            except OSError as error:
                self.skipTest(f"file symlinks unavailable: {error}")

            linked = payload_match_report(
                dcs_root,
                "Fixture Plane",
                {1: "{A}", 2: "{B}"},
            )

        self.assertEqual(
            linked["classification"],
            "source_evidence_incomplete",
        )
        self.assertFalse(
            linked["source_binding"]["candidate_enumeration_complete"]
        )

    def test_payload_source_count_is_bounded_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = _fixture_root(temp_dir)
            source = (
                dcs_root
                / "MissionEditor"
                / "data"
                / "scripts"
                / "UnitPayloads"
                / "Second.lua"
            )
            source.write_text(PAYLOADS, encoding="utf-8")

            with patch(
                "dcsmizzer.dcs_static._MAX_PAYLOAD_SOURCE_FILES",
                1,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "source count exceeds",
                ):
                    payload_report(dcs_root, "Fixture Plane")


if __name__ == "__main__":
    unittest.main()
