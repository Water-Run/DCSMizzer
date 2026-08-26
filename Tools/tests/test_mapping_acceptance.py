from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOLS_ROOT.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.br_coordinates import br_coordinate_report  # noqa: E402
from dcsmizzer.br_static import (  # noqa: E402
    _airbase_record,
    _load_airbases,
)
from dcsmizzer.coastline import (  # noqa: E402
    MAX_BOUNDS_BYTES,
    _load_geometry,
    _nearest_boundary,
    _offset_from_boundary,
    br_coastline_report,
)
from dcsmizzer.pydcs_static import pydcs_terrain_report  # noqa: E402
from dcsmizzer.terrain_coverage import combined_terrain_report  # noqa: E402
from dcsmizzer.terrain_probe import _read_regular_file  # noqa: E402
from dcsmizzer.upstream_cache import (  # noqa: E402
    upstream_report_usable,
    upstream_status_report,
)


UPSTREAM_ROOT_ENV = "DCSMIZZER_MAPPING_ACCEPTANCE_UPSTREAM_ROOT"
EXPECTED_TERRAINS = {
    "Afghanistan": (29, None),
    "Caucasus": (21, 21),
    "Falklands": (27, 26),
    "GermanyCW": (227, 227),
    "Iraq": (20, None),
    "Kola": (37, 37),
    "MarianaIslands": (8, 8),
    "MarianaIslandsWWII": (11, None),
    "Nevada": (17, 17),
    "Normandy": (82, 89),
    "PersianGulf": (30, 29),
    "SinaiMap": (56, 55),
    "Syria": (225, 224),
    "TheChannel": (12, 12),
}
EXPECTED_BR_COORDINATE_SAMPLES = {
    terrain: briefingroom_airbases
    for terrain, (briefingroom_airbases, _pydcs_airports) in (
        EXPECTED_TERRAINS.items()
    )
}
EXPECTED_BR_COORDINATE_SAMPLES["Afghanistan"] = 27
EXPECTED_COASTLINE_SUCCESSES = frozenset(
    {
        *(f"Afghanistan:land:{distance}" for distance in (100, 1000, 100000)),
        "Caucasus:land:100",
        "Caucasus:land:1000",
        "Caucasus:water:100000",
        "Falklands:water:100000",
        *(f"Falklands:land:{distance}" for distance in (100, 1000, 100000)),
        "GermanyCW:land:100",
        "GermanyCW:land:1000",
        *(f"Iraq:land:{distance}" for distance in (100, 1000, 100000)),
        *(f"Kola:land:{distance}" for distance in (100, 1000, 100000)),
        *(
            f"MarianaIslands:{side}:{distance}"
            for side in ("water", "land")
            for distance in (100, 1000)
        ),
        *(
            f"MarianaIslandsWWII:{side}:{distance}"
            for side in ("water", "land")
            for distance in (100, 1000)
        ),
        "Normandy:water:100",
        "Normandy:water:1000",
        "PersianGulf:water:100000",
        *(f"PersianGulf:land:{distance}" for distance in (100, 1000, 100000)),
        "SinaiMap:water:100000",
        *(f"SinaiMap:land:{distance}" for distance in (100, 1000, 100000)),
        "Syria:land:100",
        "Syria:land:1000",
        "TheChannel:land:100",
        "TheChannel:land:1000",
    }
)


class LockedMappingAcceptanceTests(unittest.TestCase):
    """Local, data-backed acceptance checks without redistributing upstream data."""

    @classmethod
    def setUpClass(cls) -> None:
        explicit_root = os.environ.get(UPSTREAM_ROOT_ENV)
        cls.cache_root = (
            Path(explicit_root)
            if explicit_root
            else REPOSITORY_ROOT / ".develope" / "upstream"
        )
        status = upstream_status_report(cls.cache_root)
        if not upstream_report_usable(status):
            reasons = ", ".join(
                f"{source['name']}="
                + (
                    "+".join(
                        error["code"]
                        for error in source.get("errors", [])
                        if isinstance(error, dict)
                        and isinstance(error.get("code"), str)
                    )
                    or "unavailable"
                )
                for source in status.get("sources", [])
                if isinstance(source, dict)
            )
            message = (
                "exact acknowledged mapping cache is unavailable "
                f"({reasons or 'no usable sources'}); populate "
                ".develope/upstream or set "
                f"{UPSTREAM_ROOT_ENV} to a complete locked cache"
            )
            if explicit_root:
                raise AssertionError(message)
            raise unittest.SkipTest(message)

        cls.pydcs_root = cls.cache_root / "pydcs"
        cls.br_root = cls.cache_root / "briefing-room-for-dcs"

    def test_locked_fourteen_theatre_aggregate(self) -> None:
        report = combined_terrain_report(self.pydcs_root, self.br_root)

        self.assertEqual(
            report["authority"],
            "explicit_multi_source_commit_bound_catalog",
        )
        self.assertTrue(report["source_lock"]["all_sources_commit_bound"])
        self.assertEqual(report["source_lock"]["failure_reasons"], [])
        self.assertEqual(
            report["coverage"],
            {
                "dcs_theatres": 14,
                "terrain_records": 14,
                "dual_source_theatres": 11,
                "pydcs_only_theatres": 0,
                "briefingroom_only_theatres": 3,
                "matching_theatres": 14,
                "matching_records_including_rejected": 14,
                "exact_query_usable": None,
                "theatre_identity_conflicts": 1,
                "identity_conflict_records": 1,
                "identity_mappings_rejected": 0,
                "source_parse_incomplete": False,
            },
        )
        self.assertEqual(
            report["source_coverage"]["pydcs"],
            {
                "terrain_packages_discovered": 11,
                "terrain_packages_parsed": 11,
                "terrain_packages_unresolved": [],
                "matching_terrains": 11,
                "matching_unresolved_packages": [],
                "duplicate_identities": [],
                "selected_identity_ambiguous": False,
                "exact_query_usable": True,
                "airports_parsed": 745,
                "airport_parse_failures": 0,
                "parking_slots_parsed": 22661,
            },
        )
        self.assertEqual(
            report["source_coverage"]["briefingroom"],
            {
                "theatre_declarations": 14,
                "matching_theatres": 14,
                "theatres_parsed": 14,
                "terrain_bounds_unresolved": [],
                "duplicate_dcs_ids": [],
                "airbases_indexed": 802,
                "exact_query_usable": True,
            },
        )

        actual = {
            item["dcs_theatre"]: (
                item["briefingroom"]["airbases"],
                (
                    item["pydcs"]["airports"]
                    if item["pydcs"] is not None
                    else None
                ),
            )
            for item in report["terrains"]
        }
        self.assertEqual(actual, EXPECTED_TERRAINS)
        self.assertEqual(
            report["identity_conflicts"],
            [
                {
                    "code": "cross_source_declared_dcs_id_disagreement",
                    "pydcs_record": {
                        "record_key": "pydcs:8",
                        "terrain_package": "sinai",
                        "declared_miz_theatre_name": "Sinai",
                    },
                    "briefingroom_record": {
                        "record_key": "briefingroom:11",
                        "declaration_id": "SinaiMap",
                        "dcs_id": "SinaiMap",
                        "display_name": "Sinai",
                    },
                    "resolution": (
                        "associated_by_unambiguous_alias; BriefingRoom DCSID "
                        "retained without rewriting pydcs declaration"
                    ),
                }
            ],
        )

    def test_locked_coordinate_models_are_thirteen_valid_one_rejected(self) -> None:
        validated: set[str] = set()
        rejected: set[str] = set()
        reports = {}
        for terrain in EXPECTED_TERRAINS:
            report = br_coordinate_report(self.br_root, terrain)
            reports[terrain] = report
            self.assertEqual(
                report["authority"],
                "derived_commit_bound_br_airbase_export_projection",
            )
            self.assertFalse(report["dcs_started"])
            self.assertIsNone(report["runtime_valid"])
            self.assertTrue(
                report["decision_source_binding"][
                    "all_required_sources_bound_to_head"
                ]
            )
            self.assertTrue(report["coverage"]["all_unique_finite_samples_used"])
            self.assertEqual(report["coverage"]["invalid_coordinate_records"], 0)
            self.assertEqual(
                report["coverage"]["unique_finite_coordinate_samples"],
                EXPECTED_BR_COORDINATE_SAMPLES[terrain],
            )
            if report["validation"]["validated"]:
                validated.add(terrain)
                self.assertEqual(report["validation"]["failure_reasons"], [])
                self.assertIsNotNone(report["model"])
            else:
                rejected.add(terrain)
                self.assertIsNone(report["model"])
                self.assertIsNone(report["conversion"])

        self.assertEqual(validated, set(EXPECTED_TERRAINS) - {"Afghanistan"})
        self.assertEqual(rejected, {"Afghanistan"})
        afghanistan = reports["Afghanistan"]
        self.assertEqual(afghanistan["coverage"]["duplicate_coordinate_records"], 2)
        self.assertEqual(
            afghanistan["duplicate_coordinate_diagnostics"]["groups_total"],
            1,
        )
        duplicate = afghanistan["duplicate_coordinate_diagnostics"]["groups"][0]
        self.assertEqual(duplicate["occurrences"], 3)
        self.assertEqual(
            {item["airdrome_id"] for item in duplicate["record_references"]},
            {26, 27, 28},
        )
        self.assertEqual(
            set(afghanistan["validation"]["failure_reasons"]),
            {
                "best_candidate_scale_factor_out_of_range",
                "best_candidate_forward_error_exceeds_limit",
                "best_candidate_inverse_error_exceeds_limit",
                "leave_one_out_forward_error_exceeds_limit",
                "leave_one_out_inverse_error_exceeds_limit",
            },
        )

    def test_locked_coastline_matrix_is_forty_passes_and_forty_four_failures(
        self,
    ) -> None:
        airbases, _source = _load_airbases(self.br_root)
        first_centres = {}
        for terrain in EXPECTED_TERRAINS:
            first = next(
                item for item in airbases if item.get("theatre") == terrain
            )
            first_centres[terrain] = _airbase_record(first)["center"]

        successes: set[str] = set()
        failures: dict[str, str] = {}
        for terrain, centre in first_centres.items():
            bounds = (
                self.br_root
                / "DatabaseJSON"
                / "TheaterTerrainBounds"
                / f"{terrain}.json"
            )
            try:
                geometry = _load_geometry(
                    _read_regular_file(bounds, MAX_BOUNDS_BYTES)
                )
                nearest = _nearest_boundary(
                    (centre["x"], centre["y"]),
                    geometry["landMasses"],
                )
            except ValueError as error:
                for side in ("water", "land"):
                    for distance in (100, 1000, 100000):
                        failures[f"{terrain}:{side}:{distance}"] = str(error)
                continue

            for side in ("water", "land"):
                for distance in (100, 1000, 100000):
                    case = f"{terrain}:{side}:{distance}"
                    try:
                        result = _offset_from_boundary(
                            nearest,
                            geometry,
                            float(distance),
                            side,
                        )
                    except ValueError as error:
                        failures[case] = str(error)
                        continue
                    successes.add(case)
                    self.assertTrue(result["satisfied"])
                    self.assertEqual(result["target_side"], side)
                    self.assertEqual(result["mask_classification"], side)
                    self.assertLessEqual(
                        result["distance_residual_m"],
                        result["distance_tolerance_m"],
                    )

        self.assertEqual(successes, set(EXPECTED_COASTLINE_SUCCESSES))
        self.assertEqual(len(successes), 40)
        self.assertEqual(len(failures), 44)
        self.assertEqual(set(successes) & set(failures), set())
        self.assertEqual(set(successes) | set(failures), {
            f"{terrain}:{side}:{distance}"
            for terrain in EXPECTED_TERRAINS
            for side in ("water", "land")
            for distance in (100, 1000, 100000)
        })
        self.assertTrue(
            all(
                message == "terrain bounds contain no land-mass planning boundary"
                for case, message in failures.items()
                if case.startswith("Nevada:")
            )
        )
        self.assertTrue(
            all(
                "no unique exact candidate" in message
                for case, message in failures.items()
                if not case.startswith("Nevada:")
            )
        )

        caucasus = br_coastline_report(
            self.br_root,
            "Caucasus",
            map_x=-148274.51145593636,
            map_y=444041.02616748563,
            offset_distance_m=100000.0,
            target_side="water",
        )
        self.assertEqual(
            caucasus["decision_source_binding"]["head_commit"],
            "4d8773e9eec0215edb5cd9f576c085ee9f1bf7a7",
        )
        self.assertEqual(
            caucasus["decision_source_binding"]["sources"]["terrain_bounds"][
                "git_blob_oid"
            ],
            "41ad5fc6bb549c0be2b743887f3c61c8c8b7c822",
        )
        self.assertAlmostEqual(
            caucasus["nearest_planning_land_mass_boundary"]["minimum_distance_m"],
            453.74655896091326,
            places=6,
        )
        self.assertAlmostEqual(
            caucasus["offset"]["destination"]["x"],
            -222687.86225051357,
            places=6,
        )
        self.assertAlmostEqual(
            caucasus["offset"]["destination"]["y"],
            376560.59625439823,
            places=6,
        )
        self.assertTrue(caucasus["validation"]["usable_for_generation"])
        self.assertFalse(caucasus["dcs_started"])

    def test_great_pyramid_static_sources_agree_without_runtime_upgrade(
        self,
    ) -> None:
        latitude = 29.97915
        longitude = 31.134219444444445
        pydcs = pydcs_terrain_report(
            self.pydcs_root,
            terrain="Sinai",
            latitude=latitude,
            longitude=longitude,
        )
        briefingroom = br_coordinate_report(
            self.br_root,
            "SinaiMap",
            latitude=latitude,
            longitude=longitude,
        )

        self.assertEqual(pydcs["coverage"]["matching_terrains"], 1)
        self.assertTrue(pydcs["coverage"]["exact_query_usable"])
        self.assertFalse(
            pydcs["conversion"]["independently_validated_against_current_install"]
        )
        self.assertTrue(briefingroom["validation"]["validated"])
        self.assertFalse(briefingroom["extrapolation"]["outside_sample_envelope"])
        self.assertIsNone(briefingroom["runtime_valid"])
        self.assertFalse(briefingroom["dcs_started"])

        pydcs_point = pydcs["conversion"]["output"]
        briefingroom_point = briefingroom["conversion"]["output"]
        documented_install_fit = {
            "x": -7373.176363856532,
            "y": -10781.869446930854,
        }
        self.assertLess(
            math.hypot(
                pydcs_point["x"] - briefingroom_point["x"],
                pydcs_point["y"] - briefingroom_point["y"],
            ),
            0.001,
        )
        for point in (pydcs_point, briefingroom_point):
            self.assertLess(
                math.hypot(
                    point["x"] - documented_install_fit["x"],
                    point["y"] - documented_install_fit["y"],
                ),
                0.01,
            )


if __name__ == "__main__":
    unittest.main()
