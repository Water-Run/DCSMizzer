from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.dcsmizzer.terrain_physical import (
    airfield_footprint_report,
    br_airfield_footprint_report,
    landmark_report,
    placement_sample_points,
    physical_point_report,
    placement_report,
    terrain_corridor_report,
)

BINDING = {
    "terrain": "SinaiMap",
    "dcs_version": "2.9.28.26385",
}


def _evidence() -> dict[str, object]:
    samples: list[dict[str, object]] = []
    for x in (-2.0, 0.0, 2.0, 18.0, 20.0, 22.0):
        for y in (-2.0, 0.0, 2.0):
            samples.append(
                {
                    "x": x,
                    "y": y,
                    "height_msl": 100.0 + (x / 100.0),
                    "surface": "land",
                }
            )
    for x, height in ((0.0, 100.0), (25.0, 105.0), (50.0, 125.0)):
        for y in (-5.0, 0.0, 5.0):
            samples.append(
                {
                    "x": x,
                    "y": y,
                    "height_msl": height,
                    "surface": "land",
                }
            )
    return {
        "schema": "dcsmizzer.terrain-physical-evidence/v1",
        "terrain": "SinaiMap",
        "dcs": {
            "product_version": "2.9.28.26385",
            "product_version_basis": "runtime_attested",
            "steam_build_id": "24431605",
        },
        "export": {
            "kind": "dcs_terrain_api_runtime_export",
            "runtime_initialized": True,
            "created_utc": "2026-07-30T00:00:00Z",
        },
        "coverage": {
            "sample_spacing_m": 5.0,
            "sample_match_tolerance_m": 0.01,
            "object_searches": [
                {
                    "x": 0.0,
                    "y": 0.0,
                    "radius_m": 100.0,
                    "volume_kind": "box_3d",
                    "minimum_altitude_msl": -100_000.0,
                    "maximum_altitude_msl": 100_000.0,
                    "complete_for_ground_placement": True,
                }
            ],
            "object_search_complete": True,
            "object_search_complete_for_ground_placement": True,
            "object_inventory_complete": False,
            "airfield_inventory_complete": True,
        },
        "samples": samples,
        "objects": [
            {
                "model": "Heops_pyramid",
                "name": "Great Pyramid",
                "center": {"x": 20.0, "y": 0.0},
                "heading_deg": 0.0,
                "size_obb": {"length": 10.0, "width": 10.0},
                "radius": 8.0,
            }
        ],
        "airfields": [
            {
                "airdrome_id": 1,
                "name": "Fixture Airfield",
                "geometry_complete": True,
                "runways": [
                    {
                        "center": {"x": 1000.0, "y": 2000.0},
                        "heading_deg": 90.0,
                        "length": 2000.0,
                        "width": 50.0,
                    }
                ],
                "parking": [
                    {
                        "position": {"x": 950.0, "y": 2050.0},
                        "heading_deg": 90.0,
                        "length": 40.0,
                        "width": 30.0,
                    }
                ],
                "taxi_routes": [
                    [
                        {"x": 900.0, "y": 2050.0},
                        {"x": 1100.0, "y": 2050.0},
                    ]
                ],
            }
        ],
    }


class TerrainPhysicalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "terrain.json"
        self.path.write_text(json.dumps(_evidence()), encoding="utf-8")

    def test_point_query_is_version_and_terrain_bound(self) -> None:
        report = physical_point_report(
            self.path,
            0.0,
            0.0,
            terrain="SinaiMap",
            dcs_version="2.9.28.26385",
        )

        self.assertEqual(
            report["schema"],
            "dcsmizzer.terrain-point/v1",
        )
        self.assertTrue(report["validation"]["evidence_usable"])
        self.assertEqual(report["point"]["surface"], "land")
        self.assertEqual(report["point"]["height_msl"], 100.0)
        self.assertFalse(report["dcs_started"])

        with self.assertRaisesRegex(ValueError, "terrain"):
            physical_point_report(
                self.path,
                0,
                0,
                terrain="Syria",
                dcs_version=BINDING["dcs_version"],
            )
        with self.assertRaisesRegex(ValueError, "version"):
            physical_point_report(
                self.path,
                0,
                0,
                terrain=BINDING["terrain"],
                dcs_version="2.9.27",
            )

    def test_point_query_fails_closed_when_sample_is_too_far(self) -> None:
        report = physical_point_report(
            self.path,
            500.0,
            500.0,
            **BINDING,
        )

        self.assertFalse(report["validation"]["evidence_usable"])
        self.assertIsNone(report["point"])
        self.assertIn(
            "no_sample_within_tolerance",
            report["validation"]["failure_reasons"],
        )

    def test_placement_checks_slope_surface_and_object_obb(self) -> None:
        clear = placement_report(
            self.path,
            x=0.0,
            y=0.0,
            heading_deg=0.0,
            length_m=4.0,
            width_m=4.0,
            required_surface="land",
            max_slope_deg=5.0,
            **BINDING,
        )
        blocked = placement_report(
            self.path,
            x=20.0,
            y=0.0,
            heading_deg=0.0,
            length_m=4.0,
            width_m=4.0,
            required_surface="land",
            max_slope_deg=5.0,
            **BINDING,
        )

        self.assertIsNone(clear["validation"]["placement_valid"])
        self.assertTrue(clear["validation"]["sampled_placement_valid"])
        self.assertFalse(blocked["validation"]["placement_valid"])
        self.assertEqual(
            blocked["collisions"][0]["model"],
            "Heops_pyramid",
        )

    def test_placement_requires_object_and_airfield_coverage(self) -> None:
        data = _evidence()
        data["coverage"]["object_search_complete"] = False  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        no_objects = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )

        self.assertIsNone(no_objects["validation"]["placement_valid"])
        self.assertIn(
            "object_search_coverage_incomplete",
            no_objects["validation"]["failure_reasons"],
        )

        data = _evidence()
        search = data["coverage"]["object_searches"][0]  # type: ignore[index]
        for field in (
            "volume_kind",
            "minimum_altitude_msl",
            "maximum_altitude_msl",
            "complete_for_ground_placement",
        ):
            search.pop(field)  # type: ignore[union-attr]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        legacy_volume = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )
        self.assertIsNone(
            legacy_volume["validation"]["placement_valid"]
        )
        self.assertFalse(
            legacy_volume["coverage"]["object_search_covers_footprint"]
        )

        data = _evidence()
        data["coverage"]["airfield_inventory_complete"] = False  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        no_airfields = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )
        allowed = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            avoid_airfields=False,
            **BINDING,
        )

        self.assertIsNone(no_airfields["validation"]["placement_valid"])
        self.assertIn(
            "airfield_inventory_incomplete",
            no_airfields["validation"]["failure_reasons"],
        )
        self.assertIsNone(allowed["validation"]["placement_valid"])
        self.assertTrue(allowed["validation"]["sampled_placement_valid"])

    def test_placement_rejects_reused_samples_and_uses_pairwise_slope(self) -> None:
        data = _evidence()
        data["coverage"].update(  # type: ignore[union-attr]
            {
                "sample_match_tolerance_m": 1.0,
                "object_inventory_complete": True,
                "airfield_inventory_complete": True,
            }
        )
        data["samples"] = [
            {
                "x": 0.0,
                "y": 0.0,
                "height_msl": 100.0,
                "surface": "land",
            }
        ]
        data["objects"] = []
        data["airfields"] = []
        self.path.write_text(json.dumps(data), encoding="utf-8")

        reused = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=1,
            width_m=1,
            **BINDING,
        )

        self.assertIsNone(reused["validation"]["placement_valid"])
        self.assertIn(
            "footprint_samples_not_distinct",
            reused["validation"]["failure_reasons"],
        )

        points = placement_sample_points(
            x=0,
            y=0,
            heading_deg=0,
            length_m=100,
            width_m=2,
        )
        data["coverage"]["sample_match_tolerance_m"] = 0.01  # type: ignore[index]
        data["samples"] = [
            {
                **point,
                "height_msl": 101.0 if index == 0 else 100.0,
                "surface": "land",
            }
            for index, point in enumerate(points)
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        slope = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=100,
            width_m=2,
            max_slope_deg=0.8,
            **BINDING,
        )

        self.assertFalse(slope["validation"]["placement_valid"])
        self.assertGreater(
            slope["validation"]["maximum_sampled_slope_deg"],
            1.0,
        )

    def test_planning_snapshot_cannot_pass_physical_validation(self) -> None:
        data = _evidence()
        data["export"] = {
            "kind": "upstream_planning_snapshot",
            "runtime_initialized": False,
            "created_utc": "2026-07-30T00:00:00Z",
        }
        self.path.write_text(json.dumps(data), encoding="utf-8")

        report = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )

        self.assertIsNone(report["validation"]["placement_valid"])
        self.assertIn(
            "physical_authority_required",
            report["validation"]["failure_reasons"],
        )

    def test_corridor_returns_worst_clearance_and_detects_mountain(self) -> None:
        report = terrain_corridor_report(
            self.path,
            route=[
                {"x": 0.0, "y": 0.0, "altitude_msl": 130.0},
                {"x": 50.0, "y": 0.0, "altitude_msl": 130.0},
            ],
            half_width_m=5.0,
            step_m=25.0,
            minimum_clearance_m=20.0,
            limit=2,
            **BINDING,
        )

        self.assertFalse(report["validation"]["corridor_clear"])
        self.assertAlmostEqual(
            report["validation"]["minimum_observed_clearance_m"],
            5.0,
        )
        self.assertLessEqual(len(report["hazards"]), 2)
        self.assertTrue(report["coverage"]["hazards_output_truncated"])

    def test_corridor_rejects_unbounded_sample_expansion(self) -> None:
        with self.assertRaisesRegex(ValueError, "sample-query limit"):
            terrain_corridor_report(
                self.path,
                route=[
                    {"x": 0.0, "y": 0.0, "altitude_msl": 130.0},
                    {"x": 50.0, "y": 0.0, "altitude_msl": 130.0},
                ],
                half_width_m=5.0,
                step_m=0.0001,
                minimum_clearance_m=20.0,
                **BINDING,
            )

    def test_corridor_rejects_one_sample_reused_for_distinct_points(self) -> None:
        data = _evidence()
        data["coverage"]["sample_match_tolerance_m"] = 1.0  # type: ignore[index]
        data["samples"] = [
            {
                "x": 0.0,
                "y": 0.0,
                "height_msl": 100.0,
                "surface": "land",
            }
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        report = terrain_corridor_report(
            self.path,
            route=[
                {"x": 0.0, "y": 0.0, "altitude_msl": 200.0},
                {"x": 1.0, "y": 0.0, "altitude_msl": 200.0},
            ],
            half_width_m=0,
            step_m=0.5,
            minimum_clearance_m=20,
            **BINDING,
        )

        self.assertIsNone(report["validation"]["corridor_clear"])
        self.assertIn(
            "corridor_samples_not_distinct",
            report["validation"]["failure_reasons"],
        )

    def test_landmark_search_is_bounded_and_exact_model_seeded(self) -> None:
        report = landmark_report(
            self.path,
            query="pyramid",
            near_x=20.0,
            near_y=0.0,
            radius_m=100.0,
            limit=1,
            **BINDING,
        )

        self.assertTrue(report["validation"]["exact_query_usable"])
        self.assertEqual(report["landmarks"][0]["model"], "Heops_pyramid")
        self.assertEqual(report["landmarks"][0]["distance_m"], 0.0)

    def test_airfield_footprint_is_explicitly_derived(self) -> None:
        report = airfield_footprint_report(
            self.path,
            airfield="Fixture Airfield",
            taxi_buffer_m=15.0,
            **BINDING,
        )

        self.assertTrue(report["validation"]["exact_airfield_usable"])
        self.assertEqual(report["footprint"]["authority"], "derived_geometry")
        self.assertEqual(len(report["footprint"]["runway_polygons"]), 1)
        self.assertEqual(len(report["footprint"]["parking_polygons"]), 1)
        self.assertEqual(len(report["footprint"]["taxi_corridors"]), 1)
        self.assertFalse(report["footprint"]["official_airport_boundary"])

    def test_task_binding_and_sample_tolerance_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "terrain is required"):
            physical_point_report(self.path, 0, 0)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            physical_point_report(
                self.path,
                0.5,
                0,
                tolerance_m=1.0,
                **BINDING,
            )

        data = _evidence()
        data["coverage"]["sample_match_tolerance_m"] = 1.01  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "0.001 to 1.0"):
            physical_point_report(self.path, 0, 0, **BINDING)

    def test_clearance_requires_covering_expanded_rectangle_corners(
        self,
    ) -> None:
        data = _evidence()
        data["samples"] = [
            {
                **point,
                "height_msl": 0.0,
                "surface": "land",
            }
            for point in placement_sample_points(
                x=0,
                y=0,
                heading_deg=0,
                length_m=10,
                width_m=10,
            )
        ]
        data["objects"] = []
        data["airfields"] = []
        data["coverage"]["object_searches"][0]["radius_m"] = 108.0  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        report = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=10,
            width_m=10,
            clearance_m=100,
            **BINDING,
        )

        self.assertIsNone(report["validation"]["placement_valid"])
        self.assertFalse(
            report["coverage"]["object_search_covers_footprint"]
        )

    def test_airfield_collision_includes_taxi_and_unknown_parking_heading(
        self,
    ) -> None:
        data = _evidence()
        data["coverage"]["object_inventory_complete"] = True  # type: ignore[index]
        data["objects"] = []
        data["airfields"] = [
            {
                "name": "Taxi Airfield",
                "geometry_complete": True,
                "runways": [
                    {
                        "center": {"x": 1000.0, "y": 1000.0},
                        "heading_deg": 0.0,
                        "length": 100.0,
                        "width": 20.0,
                    }
                ],
                "parking": [],
                "taxi_routes": [
                    [{"x": -10.0, "y": 0.0}, {"x": 10.0, "y": 0.0}]
                ],
            }
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        taxi = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )
        self.assertFalse(taxi["validation"]["placement_valid"])
        self.assertEqual(
            taxi["airfield_conflicts"][0]["geometry"],
            "taxi_route",
        )

        data["samples"] = [
            {
                **point,
                "height_msl": 0.0,
                "surface": "land",
            }
            for point in placement_sample_points(
                x=0,
                y=40,
                heading_deg=0,
                length_m=4,
                width_m=4,
            )
        ]
        data["airfields"][0]["parking"] = [  # type: ignore[index]
            {
                "position": {"x": 0.0, "y": 0.0},
                "length": 100.0,
                "width": 2.0,
            }
        ]
        data["airfields"][0]["taxi_routes"] = []  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        parking = placement_report(
            self.path,
            x=0,
            y=40,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )
        self.assertFalse(parking["validation"]["placement_valid"])
        self.assertEqual(
            parking["airfield_conflicts"][0]["method"],
            "conservative_bounding_circle",
        )

    def test_airfield_geometry_completeness_is_required(self) -> None:
        data = _evidence()
        data["airfields"][0]["geometry_complete"] = False  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        placement = placement_report(
            self.path,
            x=0,
            y=0,
            heading_deg=0,
            length_m=4,
            width_m=4,
            **BINDING,
        )
        footprint = airfield_footprint_report(
            self.path,
            airfield="Fixture Airfield",
            **BINDING,
        )

        self.assertIsNone(placement["validation"]["placement_valid"])
        self.assertIn(
            "airfield_geometry_incomplete",
            placement["validation"]["failure_reasons"],
        )
        self.assertFalse(
            footprint["validation"]["exact_airfield_usable"]
        )
        self.assertIn(
            "airfield_geometry_incomplete",
            footprint["validation"]["failure_reasons"],
        )

    def test_complete_airfield_geometry_cannot_be_empty(self) -> None:
        data = _evidence()
        data["airfields"] = [
            {
                "name": "Empty Airfield",
                "geometry_complete": True,
                "runways": [],
                "parking": [],
                "taxi_routes": [],
            }
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError,
            "complete airfield geometry must contain at least one record",
        ):
            airfield_footprint_report(
                self.path,
                airfield="Empty Airfield",
                **BINDING,
            )

    def test_zero_length_taxi_segment_is_rejected(self) -> None:
        data = _evidence()
        data["airfields"][0]["taxi_routes"] = [  # type: ignore[index]
            [{"x": 1.0, "y": 1.0}, {"x": 1.0, "y": 1.0}]
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "zero-length"):
            airfield_footprint_report(
                self.path,
                airfield="Fixture Airfield",
                **BINDING,
            )

    def test_landmark_absence_requires_covering_object_search(self) -> None:
        data = _evidence()
        data["objects"] = []
        self.path.write_text(json.dumps(data), encoding="utf-8")

        incomplete = landmark_report(
            self.path,
            query="missing",
            near_x=1000,
            near_y=1000,
            radius_m=10,
            **BINDING,
        )
        covered = landmark_report(
            self.path,
            query="missing",
            near_x=0,
            near_y=0,
            radius_m=10,
            **BINDING,
        )
        unbounded_near = landmark_report(
            self.path,
            query="missing",
            near_x=0,
            near_y=0,
            **BINDING,
        )

        self.assertFalse(incomplete["validation"]["absence_proven"])
        self.assertIn(
            "object_search_coverage_incomplete",
            incomplete["validation"]["failure_reasons"],
        )
        self.assertTrue(covered["validation"]["absence_proven"])
        self.assertIn(
            "no_matching_scenery_object",
            covered["validation"]["failure_reasons"],
        )
        self.assertFalse(unbounded_near["validation"]["absence_proven"])
        self.assertIn(
            "object_search_coverage_incomplete",
            unbounded_near["validation"]["failure_reasons"],
        )

    def test_object_collision_uses_obb_and_radius_union(self) -> None:
        data = _evidence()
        data["coverage"]["object_inventory_complete"] = True  # type: ignore[index]
        data["samples"] = [
            {
                **point,
                "height_msl": 0.0,
                "surface": "land",
            }
            for point in placement_sample_points(
                x=10,
                y=0,
                heading_deg=0,
                length_m=2,
                width_m=2,
            )
        ]
        data["objects"] = [
            {
                "model": "conservative-object",
                "center": {"x": 0.0, "y": 0.0},
                "heading_deg": 0.0,
                "size_obb": {"length": 1.0, "width": 1.0},
                "radius": 10.0,
            }
        ]
        data["airfields"] = []
        self.path.write_text(json.dumps(data), encoding="utf-8")

        report = placement_report(
            self.path,
            x=10,
            y=0,
            heading_deg=0,
            length_m=2,
            width_m=2,
            **BINDING,
        )

        self.assertFalse(report["validation"]["placement_valid"])
        self.assertEqual(
            report["collisions"][0]["method"],
            "conservative_bounding_circle",
        )

    def test_object_obb_requires_heading(self) -> None:
        data = _evidence()
        data["objects"] = [
            {
                "model": "unoriented-object",
                "center": {"x": 0.0, "y": 0.0},
                "size_obb": {"length": 100.0, "width": 1.0},
            }
        ]
        self.path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError,
            "size_obb requires heading_deg",
        ):
            placement_report(
                self.path,
                x=0,
                y=40,
                heading_deg=0,
                length_m=2,
                width_m=2,
                **BINDING,
            )

    def test_physical_evidence_symlink_is_rejected(self) -> None:
        linked = Path(self.temp.name) / "linked.json"
        try:
            linked.symlink_to(self.path)
        except OSError as error:
            self.skipTest(f"file symlinks are unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "safe regular file"):
            physical_point_report(linked, 0, 0, **BINDING)

    def test_br_airfield_footprint_is_planning_only_and_conservative(
        self,
    ) -> None:
        upstream = {
            "schema": "dcsmizzer.br-airbases/v1",
            "authority": "commit_bound_upstream_exported_airbase_database",
            "coverage": {
                "exact_airbase_query_usable": True,
                "airbase_parse_failures": 0,
            },
            "source": "DatabaseJSON/TheatersAirbases.json",
            "source_sha256": "a" * 64,
            "upstream": {"commit": "fixture"},
            "upstream_project_version": {
                "targeted_dcs_world_version": "2.9.28.26283"
            },
            "airbases": [
                {
                    "name": "Fixture Airfield",
                    "airdrome_id": 7,
                    "runways": [
                        {
                            "position": {"x": 100.0, "y": 10.0, "z": 200.0},
                            "course_raw_radians": 0.0,
                            "length": 1000.0,
                            "width": 40.0,
                        }
                    ],
                    "parking": [
                        {
                            "position": {"x": 10.0, "y": 20.0},
                            "heading": None,
                            "dimensions": {"length": 60.0, "width": 52.0},
                            "slot_name": "01",
                        }
                    ],
                }
            ],
        }

        with patch(
            "Tools.dcsmizzer.terrain_physical.br_airbase_report",
            return_value=upstream,
        ) as query:
            report = br_airfield_footprint_report(
                Path("briefing-room"),
                "SinaiMap",
                "Fixture Airfield",
            )

        self.assertTrue(report["validation"]["planning_footprint_usable"])
        self.assertFalse(report["validation"]["physical_validation"])
        self.assertFalse(report["footprint"]["official_airport_boundary"])
        self.assertEqual(report["footprint"]["runway_polygons"][0]["heading_deg"], 0)
        self.assertEqual(
            report["footprint"]["parking_clearance_circles"][0]["method"],
            "conservative_circle_due_missing_heading",
        )
        query.assert_called_once_with(
            Path("briefing-room"),
            "SinaiMap",
            airport="Fixture Airfield",
            limit=None,
        )

        upstream["airbases"][0]["parking"][0]["dimensions"] = None
        with patch(
            "Tools.dcsmizzer.terrain_physical.br_airbase_report",
            return_value=upstream,
        ):
            incomplete = br_airfield_footprint_report(
                Path("briefing-room"),
                "SinaiMap",
                "Fixture Airfield",
            )
        self.assertFalse(
            incomplete["validation"]["planning_footprint_usable"]
        )
        self.assertIn(
            "parking_geometry_incomplete",
            incomplete["validation"]["failure_reasons"],
        )

    def test_rejects_duplicate_keys_and_non_finite_numbers(self) -> None:
        self.path.write_text(
            '{"schema":"dcsmizzer.terrain-physical-evidence/v1",'
            '"schema":"dcsmizzer.terrain-physical-evidence/v1"}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            physical_point_report(self.path, 0, 0, **BINDING)

        data = _evidence()
        data["samples"][0]["height_msl"] = math.inf  # type: ignore[index]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            physical_point_report(self.path, 0, 0, **BINDING)


if __name__ == "__main__":
    unittest.main()
