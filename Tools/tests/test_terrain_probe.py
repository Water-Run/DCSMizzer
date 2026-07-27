from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from Tools.dcsmizzer import terrain_probe as terrain_probe_module
from Tools.dcsmizzer.terrain_physical import physical_point_report
from Tools.dcsmizzer.terrain_probe import (
    extract_terrain_probe,
    generate_terrain_probe_script,
)


def _request() -> dict[str, object]:
    return {
        "schema": "dcsmizzer.terrain-probe-request/v1",
        "terrain": "SinaiMap",
        "sample_match_tolerance_m": 0.5,
        "samples": [
            {"x": 10.0, "y": 20.0},
            {"x": 12.0, "y": 20.0},
        ],
        "object_searches": [
            {"x": 100.0, "y": 200.0, "radius_m": 500.0},
        ],
        "max_objects": 25,
    }


def _evidence(request_hash: str) -> dict[str, Any]:
    return {
        "schema": "dcsmizzer.terrain-physical-evidence/v1",
        "terrain": "SinaiMap",
        "dcs": {
            "product_version": "2.9.28.26385",
            "steam_build_id": "24431605",
            "identity_source": "probe_generation_install",
            "product_version_source": "probe_generation_install",
            "runtime_identity_attested": False,
        },
        "export": {
            "kind": "dcs_mission_scripting_runtime_export",
            "runtime_initialized": True,
            "created_utc": "2026-07-30T00:00:00Z",
            "request_sha256": request_hash,
            "object_limit": 25,
            "object_limit_reached": False,
            "object_records_skipped_without_geometry": 0,
        },
        "coverage": {
            "sampling_design": "explicit_query_points",
            "sample_match_tolerance_m": 0.5,
            "object_searches": [
                {
                    "x": 100.0,
                    "y": 200.0,
                    "radius_m": 500.0,
                    "volume_kind": "box_3d",
                    "minimum_altitude_msl": -100_000.0,
                    "maximum_altitude_msl": 100_000.0,
                    "complete_for_ground_placement": False,
                },
            ],
            "object_search_complete": True,
            "object_search_complete_for_ground_placement": False,
            "airfield_inventory_complete": False,
        },
        "samples": [
            {
                "x": 10.0,
                "y": 20.0,
                "height_msl": 35.0,
                "surface": "water",
            },
            {
                "x": 12.0,
                "y": 20.0,
                "height_msl": 36.0,
                "surface": "land",
            },
        ],
        "objects": [],
        "airfields": [],
    }


def _log_marker_run(
    request_hash: str,
    evidence: dict[str, Any],
) -> str:
    payload = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = payload.hex()
    chunks = [
        encoded[index : index + 80]
        for index in range(0, len(encoded), 80)
    ]
    return "\n".join(
        [
            "2026-07-30 INFO unrelated line",
            (
                "2026-07-30 INFO DCSMIZZER_TERRAIN_PROBE_BEGIN "
                f"{request_hash} {len(chunks)}"
            ),
            *[
                (
                    "2026-07-30 INFO DCSMIZZER_TERRAIN_PROBE_CHUNK "
                    f"{request_hash} {index}/{len(chunks)} {chunk}"
                )
                for index, chunk in enumerate(chunks, start=1)
            ],
            (
                "2026-07-30 INFO DCSMIZZER_TERRAIN_PROBE_END "
                f"{request_hash} {len(chunks)}"
            ),
        ]
    )


class TerrainProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = self.root / "request.json"
        self.request.write_text(json.dumps(_request()), encoding="utf-8")

    def test_generates_sandbox_compatible_bounded_mission_script(self) -> None:
        output = self.root / "probe.lua"
        identity = {
            "product_version": "2.9.28.26385",
            "steam_build_id": "24431605",
        }

        with patch(
            "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
            return_value=identity,
        ):
            report = generate_terrain_probe_script(
                self.request,
                self.root / "DCSWorld",
                output,
            )

        script = output.read_text(encoding="utf-8")
        self.assertEqual(report["schema"], "dcsmizzer.terrain-probe-script/v1")
        self.assertFalse(report["dcs_started"])
        self.assertFalse(report["validation"]["runtime_test_performed"])
        self.assertFalse(
            report["validation"]["runtime_dcs_identity_attested"]
        )
        self.assertEqual(
            report["dcs"]["product_version_source"],
            "probe_generation_install",
        )
        self.assertEqual(report["request"]["sample_points"], 2)
        self.assertEqual(report["request"]["object_searches"], 1)
        self.assertIn("land.getHeight", script)
        self.assertIn("land.getSurfaceType", script)
        self.assertIn("world.searchObjects", script)
        self.assertIn("Object.Category.SCENERY", script)
        self.assertIn('"object_search_complete"', script)
        self.assertIn(
            '"object_search_complete_for_ground_placement"',
            script,
        )
        self.assertIn('"airfield_inventory_complete":false', script)
        self.assertIn('"product_version_source"', script)
        self.assertIn('"runtime_identity_attested":false', script)
        self.assertIn("env.info", script)
        self.assertIn("env.mission.theatre", script)
        for forbidden in ("io.", "os.", "loadfile", "dofile", "require("):
            self.assertNotIn(forbidden, script)
        self.assertEqual(
            report["output"]["sha256"],
            hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        lua = shutil.which("lua55")
        if lua is not None:
            syntax = subprocess.run(
                [
                    lua,
                    "-e",
                    f"assert(loadfile({json.dumps(str(output))}))",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                syntax.returncode,
                0,
                syntax.stderr or syntax.stdout,
            )
            runtime = subprocess.run(
                [
                    lua,
                    "-e",
                    "\n".join(
                        [
                            "env = { mission = { theatre = 'SinaiMap' } }",
                            "env.info = function(value) print(value) end",
                            "env.error = function(value) error(value) end",
                            (
                                "land = { SurfaceType = { LAND = 1, "
                                "WATER = 2, SHALLOW_WATER = 3, ROAD = 4, "
                                "RUNWAY = 5 } }"
                            ),
                            (
                                "land.getHeight = function(point) "
                                "return point.x + point.y end"
                            ),
                            (
                                "land.getSurfaceType = function(point) "
                                "return land.SurfaceType.LAND end"
                            ),
                            "Object = { Category = { SCENERY = 1 } }",
                            "world = { VolumeType = { BOX = 1 } }",
                            (
                                "world.searchObjects = function(category, "
                                "volume, visitor) return true end"
                            ),
                            (
                                "assert(loadfile("
                                f"{json.dumps(str(output))}))()"
                            ),
                        ]
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                runtime.returncode,
                0,
                runtime.stderr or runtime.stdout,
            )
            runtime_log = self.root / "mock-dcs.log"
            runtime_log.write_text(runtime.stdout, encoding="utf-8")
            runtime_evidence = self.root / "mock-evidence.json"
            runtime_report = extract_terrain_probe(
                runtime_log,
                self.request,
                runtime_evidence,
            )
            self.assertTrue(
                runtime_report["validation"]["object_search_complete"]
            )
            decoded = json.loads(
                runtime_evidence.read_text(encoding="utf-8")
            )
            search = decoded["coverage"]["object_searches"][0]
            self.assertEqual(search["x"], 100.0)
            self.assertEqual(search["y"], 200.0)
            self.assertEqual(search["radius_m"], 500.0)
            self.assertEqual(search["volume_kind"], "box_3d")
            self.assertFalse(search["complete_for_ground_placement"])
            self.assertFalse(
                decoded["coverage"]["airfield_inventory_complete"]
            )
            self.assertEqual(
                decoded["dcs"]["product_version_source"],
                "probe_generation_install",
            )
            self.assertFalse(decoded["dcs"]["runtime_identity_attested"])

    def test_request_limits_and_duplicate_keys_fail_before_output(self) -> None:
        output = self.root / "probe.lua"
        self.request.write_text(
            '{"schema":"dcsmizzer.terrain-probe-request/v1",'
            '"schema":"dcsmizzer.terrain-probe-request/v1"}',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "duplicate"):
            generate_terrain_probe_script(
                self.request,
                self.root,
                output,
            )
        self.assertFalse(output.exists())

        oversized = _request()
        oversized["max_objects"] = 10_001
        self.request.write_text(json.dumps(oversized), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "max_objects"):
            generate_terrain_probe_script(
                self.request,
                self.root,
                output,
            )
        self.assertFalse(output.exists())

    def test_runtime_probe_uses_box_and_fails_closed_on_bad_geometry(
        self,
    ) -> None:
        lua = shutil.which("lua55")
        if lua is None:
            self.skipTest("lua55 is unavailable")
        output = self.root / "geometry-probe.lua"
        with patch(
            "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
            return_value={
                "product_version": "2.9.28.26385",
                "steam_build_id": "24431605",
            },
        ):
            generate_terrain_probe_script(
                self.request,
                self.root,
                output,
            )

        bootstrap = "\n".join(
            [
                "env = { mission = { theatre = 'SinaiMap' } }",
                "env.info = function(value) print(value) end",
                "env.error = function(value) error(value) end",
                (
                    "land = { SurfaceType = { LAND = 1, WATER = 2, "
                    "SHALLOW_WATER = 3, ROAD = 4, RUNWAY = 5 } }"
                ),
                "land.getHeight = function(point) return 0 end",
                (
                    "land.getSurfaceType = function(point) "
                    "return land.SurfaceType.LAND end"
                ),
                "Object = { Category = { SCENERY = 1 } }",
                "world = { VolumeType = { BOX = 7 } }",
                (
                    "local bad = { "
                    "getPosition = function() error('bad position') end, "
                    "getDesc = function() return {} end, "
                    "getTypeName = function() return 'bad' end }"
                ),
                (
                    "local good = { "
                    "getPosition = function() return { "
                    "p = { x = 100, y = 0, z = 200 }, "
                    "x = { x = 0, z = 1 }, "
                    "z = { x = -1, z = 0 } } end, "
                    "getDesc = function() return { "
                    "typeName = 'asymmetric', displayName = 'Asymmetric', "
                    "box = { min = { x = 0, z = -1 }, "
                    "max = { x = 10, z = 1 } } } end, "
                    "getTypeName = function() return 'asymmetric' end }"
                ),
                (
                    "world.searchObjects = function(category, volume, visitor) "
                    "assert(volume.id == world.VolumeType.BOX); "
                    "assert(volume.params.min.y == -100000); "
                    "assert(volume.params.max.y == 100000); "
                    "visitor(bad); visitor(good); return true end"
                ),
                f"assert(loadfile({json.dumps(str(output))}))()",
            ]
        )
        runtime = subprocess.run(
            [lua, "-e", bootstrap],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            runtime.returncode,
            0,
            runtime.stderr or runtime.stdout,
        )
        log = self.root / "geometry.log"
        log.write_text(runtime.stdout, encoding="utf-8")
        evidence_path = self.root / "geometry.json"
        report = extract_terrain_probe(
            log,
            self.request,
            evidence_path,
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertFalse(report["validation"]["object_search_complete"])
        self.assertFalse(
            report["validation"][
                "object_search_complete_for_ground_placement"
            ]
        )
        self.assertEqual(
            evidence["export"]["object_records_skipped_without_geometry"],
            1,
        )
        self.assertEqual(len(evidence["objects"]), 1)
        exported = evidence["objects"][0]
        self.assertEqual(exported["center"], {"x": 100, "y": 205})
        self.assertNotIn("size_obb", exported)
        self.assertAlmostEqual(
            exported["radius"],
            math.sqrt(104) / 2,
        )

    def test_expands_placement_and_corridor_queries_with_shared_geometry(
        self,
    ) -> None:
        request = {
            "schema": "dcsmizzer.terrain-probe-request/v1",
            "terrain": "SinaiMap",
            "sample_match_tolerance_m": 1.0,
            "placements": [
                {
                    "x": 0.0,
                    "y": 0.0,
                    "heading_deg": 0.0,
                    "length_m": 4.0,
                    "width_m": 2.0,
                }
            ],
            "corridors": [
                {
                    "route": [
                        {"x": 0.0, "y": 0.0, "altitude_msl": 300.0},
                        {"x": 20.0, "y": 0.0, "altitude_msl": 300.0},
                    ],
                    "half_width_m": 5.0,
                    "step_m": 10.0,
                }
            ],
        }
        self.request.write_text(json.dumps(request), encoding="utf-8")
        output = self.root / "probe.lua"

        with patch(
            "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
            return_value={
                "product_version": "2.9.28.26385",
                "steam_build_id": None,
            },
        ):
            report = generate_terrain_probe_script(
                self.request,
                self.root,
                output,
            )

        self.assertEqual(report["request"]["placement_queries"], 1)
        self.assertEqual(report["request"]["corridor_queries"], 1)
        self.assertGreater(report["request"]["sample_points"], 5)
        self.assertLessEqual(report["request"]["sample_points"], 14)

    def test_extracts_complete_matching_log_run_and_validates_evidence(
        self,
    ) -> None:
        request_hash = hashlib.sha256(self.request.read_bytes()).hexdigest()
        log = self.root / "dcs.log"
        log.write_text(
            _log_marker_run(request_hash, _evidence(request_hash)),
            encoding="utf-8",
        )
        output = self.root / "terrain-evidence.json"

        report = extract_terrain_probe(
            log,
            self.request,
            output,
        )

        self.assertTrue(report["validation"]["evidence_valid"])
        self.assertTrue(report["validation"]["complete_marker_run"])
        self.assertFalse(report["dcs_started"])
        self.assertEqual(report["evidence"]["terrain"], "SinaiMap")
        self.assertTrue(report["evidence"]["object_search_complete"])
        self.assertFalse(report["evidence"]["airfield_inventory_complete"])
        self.assertTrue(
            report["validation"]["object_search_coverage_matched"]
        )
        self.assertFalse(
            report["validation"]["runtime_dcs_identity_attested"]
        )
        point = physical_point_report(
            output,
            10.0,
            20.0,
            terrain="SinaiMap",
            dcs_version="2.9.28.26385",
        )
        self.assertTrue(point["validation"]["evidence_usable"])
        self.assertEqual(point["point"]["surface"], "water")

    def test_extractor_rejects_inconsistent_coverage_claims(self) -> None:
        request_hash = hashlib.sha256(self.request.read_bytes()).hexdigest()
        cases: list[tuple[str, dict[str, Any], str]] = []

        mismatched_search = _evidence(request_hash)
        mismatched_search["coverage"]["object_searches"][0][
            "radius_m"
        ] = 501.0
        cases.append(("search", mismatched_search, "coverage does not match"))

        dishonest_complete = _evidence(request_hash)
        dishonest_complete["export"]["object_limit_reached"] = True
        cases.append(
            ("complete", dishonest_complete, "completeness is inconsistent")
        )

        dishonest_limit = _evidence(request_hash)
        dishonest_limit["objects"] = [
            {
                "model": f"object-{index}",
                "center": {"x": 100.0, "y": 200.0},
                "heading_deg": 0.0,
                "radius": 1.0,
            }
            for index in range(25)
        ]
        cases.append(
            ("limit", dishonest_limit, "object-limit status")
        )

        dishonest_airfields = _evidence(request_hash)
        dishonest_airfields["coverage"]["airfield_inventory_complete"] = True
        cases.append(
            ("airfield", dishonest_airfields, "airfield coverage")
        )

        dishonest_identity = _evidence(request_hash)
        dishonest_identity["dcs"]["runtime_identity_attested"] = True
        cases.append(("identity", dishonest_identity, "identity provenance"))

        dishonest_ground_clearance = _evidence(request_hash)
        dishonest_ground_clearance["coverage"][
            "object_search_complete_for_ground_placement"
        ] = True
        cases.append(
            (
                "ground-clearance",
                dishonest_ground_clearance,
                "ground-placement completeness",
            )
        )

        for name, evidence, message in cases:
            with self.subTest(name=name):
                log = self.root / f"{name}.log"
                log.write_text(
                    _log_marker_run(request_hash, evidence),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, message):
                    extract_terrain_probe(
                        log,
                        self.request,
                        self.root / f"{name}.json",
                    )

    def test_extractor_preserves_honest_incomplete_object_coverage(
        self,
    ) -> None:
        request_hash = hashlib.sha256(self.request.read_bytes()).hexdigest()
        evidence = _evidence(request_hash)
        evidence["export"]["object_records_skipped_without_geometry"] = 1
        evidence["coverage"]["object_search_complete"] = False
        evidence["coverage"][
            "object_search_complete_for_ground_placement"
        ] = False
        log = self.root / "incomplete.log"
        log.write_text(
            _log_marker_run(request_hash, evidence),
            encoding="utf-8",
        )

        report = extract_terrain_probe(
            log,
            self.request,
            self.root / "incomplete.json",
        )

        self.assertFalse(report["evidence"]["object_search_complete"])
        self.assertFalse(report["validation"]["object_search_complete"])

    def test_incomplete_or_mismatched_log_run_fails_closed(self) -> None:
        request_hash = hashlib.sha256(self.request.read_bytes()).hexdigest()
        log = self.root / "dcs.log"
        log.write_text(
            (
                "DCSMIZZER_TERRAIN_PROBE_BEGIN "
                f"{request_hash} 1\n"
                "DCSMIZZER_TERRAIN_PROBE_CHUNK "
                f"{request_hash} 1/1 7b7d\n"
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "complete matching"):
            extract_terrain_probe(
                log,
                self.request,
                self.root / "output.json",
            )

    def test_output_is_not_overwritten_without_force(self) -> None:
        output = self.root / "probe.lua"
        output.write_text("user data", encoding="utf-8")

        with patch(
            "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
            return_value={
                "product_version": "2.9.28.26385",
                "steam_build_id": None,
            },
        ):
            with self.assertRaisesRegex(ValueError, "already exists"):
                generate_terrain_probe_script(
                    self.request,
                    self.root,
                    output,
                )

        self.assertEqual(output.read_text(encoding="utf-8"), "user data")

    def test_concurrent_output_creation_is_not_overwritten(self) -> None:
        output = self.root / "probe.lua"
        original_open = terrain_probe_module.os.open
        competitor_created = False

        def open_with_competing_creation(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal competitor_created
            if (
                Path(path) == output
                and flags & os.O_CREAT
                and flags & os.O_EXCL
                and not competitor_created
            ):
                output.write_text(
                    "concurrent user data",
                    encoding="utf-8",
                )
                competitor_created = True
            if dir_fd is None:
                return original_open(path, flags, mode)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with (
            patch(
                "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
                return_value={
                    "product_version": "2.9.28.26385",
                    "steam_build_id": None,
                },
            ),
            patch(
                "Tools.dcsmizzer.terrain_probe.os.open",
                side_effect=open_with_competing_creation,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "already exists"):
                generate_terrain_probe_script(
                    self.request,
                    self.root,
                    output,
                )

        self.assertTrue(competitor_created)
        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "concurrent user data",
        )

    def test_failed_exclusive_write_removes_only_its_partial_output(self) -> None:
        output = self.root / "probe.lua"
        original_write = terrain_probe_module.os.write
        write_calls = 0

        def fail_after_partial_write(
            descriptor: int,
            payload: bytes,
        ) -> int:
            nonlocal write_calls
            write_calls += 1
            if write_calls == 1:
                return original_write(descriptor, payload[:16])
            raise OSError("simulated output failure")

        with (
            patch(
                "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
                return_value={
                    "product_version": "2.9.28.26385",
                    "steam_build_id": None,
                },
            ),
            patch(
                "Tools.dcsmizzer.terrain_probe.os.write",
                side_effect=fail_after_partial_write,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "written safely"):
                generate_terrain_probe_script(
                    self.request,
                    self.root,
                    output,
                )

        self.assertGreater(write_calls, 1)
        self.assertFalse(output.exists())

    def test_parent_identity_change_fails_and_removes_partial_output(
        self,
    ) -> None:
        output = self.root / "probe.lua"
        checks = 0

        def changing_parent(*args: object, **kwargs: object) -> None:
            nonlocal checks
            checks += 1
            if checks > 1:
                raise ValueError(
                    "output parent directory changed during write"
                )

        with (
            patch(
                "Tools.dcsmizzer.terrain_probe._installed_dcs_identity",
                return_value={
                    "product_version": "2.9.28.26385",
                    "steam_build_id": None,
                },
            ),
            patch(
                "Tools.dcsmizzer.terrain_probe._assert_directory_identity",
                side_effect=changing_parent,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "parent directory changed"):
                generate_terrain_probe_script(
                    self.request,
                    self.root,
                    output,
                )

        self.assertGreater(checks, 1)
        self.assertFalse(output.exists())

    def test_request_reparse_point_is_rejected_when_supported(self) -> None:
        real_request = self.root / "real-request.json"
        real_request.write_text(json.dumps(_request()), encoding="utf-8")
        linked_request = self.root / "linked-request.json"
        try:
            linked_request.symlink_to(real_request)
        except OSError as error:
            self.skipTest(f"file symlinks are unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "safe regular file"):
            generate_terrain_probe_script(
                linked_request,
                self.root,
                self.root / "probe.lua",
            )


if __name__ == "__main__":
    unittest.main()
