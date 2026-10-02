from __future__ import annotations

import copy
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.initialized_registry import (  # noqa: E402
    REGISTRY_SCHEMA,
    REPORT_SCHEMA,
    initialized_registry_report,
    normalize_initialized_registry,
    validate_initialized_registry_file,
)


VERSION = "2.9.28.26385"


def registry_fixture(*, run_id: str = "registry-fixture") -> dict[str, object]:
    return {
        "schema": REGISTRY_SCHEMA,
        "identity": {
            "run_id": run_id,
            "product_version": VERSION,
            "source_schema": "dcsmizzer.runtime-result/v1",
        },
        "coverage": {
            "stages": [
                {
                    "name": name,
                    "complete": True,
                    "source_paths": [f"fixture/{name}.lua"],
                }
                for name in (
                    "countries",
                    "tasks",
                    "units",
                    "weapons",
                    "pylons",
                    "unit_shells",
                )
            ]
        },
        "countries": [{"id": 0, "name": "Fixture Country"}],
        "tasks": [{"id": 10, "name": "CAP"}],
        "units": [
            {
                "type_name": "Fixture Plane",
                "category": "planes",
                "country_ids": [0],
                "task_ids": [10],
                "default_task_id": 10,
                "flyable": True,
                "attributes": ["Air", "Planes"],
            }
        ],
        "weapons": [
            {
                "clsid": "{FIXTURE-WEAPON}",
                "type_name": "Fixture Weapon",
            }
        ],
        "launchers": [
            {
                "clsid": "{FIXTURE-LAUNCHER}",
                "weapon_clsid": "{FIXTURE-WEAPON}",
                "settings": {"arg_value": 1, "arg_name": "fixture"},
            }
        ],
        "pylon_edges": [
            {
                "unit_type": "Fixture Plane",
                "station": 1,
                "launcher_clsid": "{FIXTURE-LAUNCHER}",
                "settings": {"use_full_connector_position": True},
            }
        ],
        "unit_shells": [
            {
                "unit_type": "Fixture Plane",
                "fields": {"fuel_max": 1_000, "crew_size": 1},
            }
        ],
    }


class InitializedRegistryTests(unittest.TestCase):
    def test_valid_fixture_is_normalized_and_internally_complete(self) -> None:
        report = initialized_registry_report(registry_fixture())

        self.assertEqual(report["schema"], REPORT_SCHEMA)
        self.assertEqual(
            report["declared_identity"]["product_version"],
            VERSION,
        )
        self.assertEqual(
            report["counts"],
            {
                "countries": 1,
                "tasks": 1,
                "units": 1,
                "weapons": 1,
                "launchers": 1,
                "pylon_edges": 1,
                "unit_shells": 1,
            },
        )
        self.assertTrue(report["coverage"]["all_stages_complete"])
        self.assertEqual(
            report["referential_integrity"]["errors"],
            [],
        )
        self.assertTrue(report["validation"]["structural_valid"])
        self.assertTrue(
            report["validation"]["referential_integrity_valid"]
        )
        self.assertTrue(report["validation"]["registry_valid"])
        self.assertFalse(
            report["validation"]["runtime_attestation_verified"]
        )
        self.assertFalse(
            report["validation"]["usable_as_current_initialized_authority"]
        )
        self.assertEqual(report["authority"], "caller_supplied_structure_only")

    def test_canonical_hash_is_stable_across_record_and_key_order(self) -> None:
        original = registry_fixture()
        reordered = copy.deepcopy(original)
        reordered["coverage"]["stages"].reverse()
        reordered["units"][0]["attributes"].reverse()
        reordered["launchers"][0]["settings"] = {
            "arg_name": "fixture",
            "arg_value": 1,
        }
        reordered = dict(reversed(tuple(reordered.items())))

        first = initialized_registry_report(original)
        second = initialized_registry_report(reordered)

        self.assertEqual(first["canonical_registry"], second["canonical_registry"])
        self.assertEqual(
            normalize_initialized_registry(original),
            normalize_initialized_registry(reordered),
        )

    def test_incomplete_coverage_is_explicit_but_structure_remains_valid(self) -> None:
        registry = registry_fixture()
        registry["coverage"]["stages"][2]["complete"] = False

        report = initialized_registry_report(registry)

        self.assertFalse(report["coverage"]["all_stages_complete"])
        self.assertFalse(report["validation"]["coverage_complete"])
        self.assertTrue(report["validation"]["registry_valid"])

    def test_every_reference_domain_reports_unresolved_targets(self) -> None:
        registry = registry_fixture()
        unit = registry["units"][0]
        unit["country_ids"] = [999]
        unit["task_ids"] = [999]
        unit["default_task_id"] = 998
        registry["launchers"][0]["weapon_clsid"] = "{MISSING-WEAPON}"
        registry["pylon_edges"][0]["unit_type"] = "Missing Plane"
        registry["pylon_edges"][0]["launcher_clsid"] = "{MISSING-LAUNCHER}"
        registry["unit_shells"][0]["unit_type"] = "Missing Plane"

        report = initialized_registry_report(registry)
        integrity = report["referential_integrity"]

        self.assertEqual(
            {error["code"] for error in integrity["errors"]},
            {
                "unit_country_missing",
                "unit_task_missing",
                "unit_default_task_missing",
                "unit_default_task_not_supported",
                "launcher_weapon_unresolved",
                "pylon_unit_missing",
                "pylon_launcher_missing",
                "unit_shell_unit_missing",
            },
        )
        self.assertEqual(
            integrity["unresolved_launcher_clsids"],
            ["{FIXTURE-LAUNCHER}"],
        )
        self.assertEqual(integrity["error_count"], 8)
        self.assertFalse(report["validation"]["registry_valid"])

    def test_structural_failures_return_a_bounded_report(self) -> None:
        cases: dict[str, object] = {}

        unknown = registry_fixture()
        unknown["unexpected"] = True
        cases["unknown key"] = unknown

        duplicate = registry_fixture()
        duplicate["countries"].append(copy.deepcopy(duplicate["countries"][0]))
        cases["duplicate record"] = duplicate

        missing_stage = registry_fixture()
        missing_stage["coverage"]["stages"].pop()
        cases["missing stage"] = missing_stage

        wrong_schema = registry_fixture()
        wrong_schema["schema"] = "dcsmizzer.initialized-registry/v0"
        cases["wrong schema"] = wrong_schema

        for label, value in cases.items():
            with self.subTest(label=label):
                report = initialized_registry_report(value)
                self.assertFalse(report["validation"]["structural_valid"])
                self.assertFalse(report["validation"]["registry_valid"])
                self.assertEqual(report["canonical_registry"], None)
                self.assertEqual(len(report["validation"]["format_errors"]), 1)

    def test_programmatic_graph_limits_reject_non_json_or_unsafe_values(self) -> None:
        cyclic = registry_fixture()
        cyclic["extensions"] = cyclic
        cases = {
            "cycle": cyclic,
            "nonfinite": {**registry_fixture(), "extensions": {"x": math.nan}},
            "unsupported": {**registry_fixture(), "extensions": {"x": object()}},
            "nonstring key": {**registry_fixture(), "extensions": {1: "x"}},
        }

        for label, value in cases.items():
            with self.subTest(label=label):
                report = initialized_registry_report(value)
                self.assertFalse(report["validation"]["structural_valid"])

    def test_file_validation_records_exact_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            payload = json.dumps(
                registry_fixture(),
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            path.write_bytes(payload)

            report = validate_initialized_registry_file(path)

        self.assertEqual(report["source"]["name"], "registry.json")
        self.assertEqual(report["source"]["size_bytes"], len(payload))
        self.assertEqual(len(report["source"]["sha256"]), 64)
        self.assertTrue(report["validation"]["registry_valid"])

    def test_file_validation_rejects_duplicate_json_keys_and_nonfinite_numbers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {
                "duplicate.json": b'{"schema":"a","schema":"b"}',
                "nonfinite.json": b'{"value":NaN}',
            }
            for name, payload in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(payload)
                    with self.assertRaises(ValueError):
                        validate_initialized_registry_file(path)

    def test_cli_exit_codes_distinguish_valid_invalid_and_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid_path = root / "valid.json"
            invalid_path = root / "invalid.json"
            malformed_path = root / "malformed.json"
            valid_path.write_text(json.dumps(registry_fixture()), encoding="utf-8")
            invalid = registry_fixture()
            invalid["launchers"][0]["weapon_clsid"] = "{MISSING}"
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
            malformed_path.write_text("{", encoding="utf-8")

            for path, expected in (
                (valid_path, 0),
                (invalid_path, 1),
                (malformed_path, 2),
            ):
                with self.subTest(path=path.name):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    exit_code = main(
                        ["initialized-registry-validate", str(path)],
                        stdout=stdout,
                        stderr=stderr,
                    )
                    self.assertEqual(exit_code, expected)
                    if expected == 2:
                        self.assertEqual(stdout.getvalue(), "")
                        self.assertIn("tool error", stderr.getvalue())
                    else:
                        report = json.loads(stdout.getvalue())
                        self.assertEqual(report["schema"], REPORT_SCHEMA)
                        self.assertEqual(
                            report["evidence_ref"]["status"],
                            "unbound",
                        )
                        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
