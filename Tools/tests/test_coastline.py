from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.coastline import br_coastline_report  # noqa: E402


ACKNOWLEDGED = {
    "remote": "https://example.invalid/briefing-room.git",
    "branch": "main",
    "commit": "a" * 40,
    "clean": True,
    "git_available": True,
    "exact_checkout_root": True,
    "provenance": "commit_bound",
    "acknowledged": True,
}


class BriefingRoomCoastlineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        theatres = self.root / "Database" / "Theaters"
        theatres.mkdir(parents=True)
        (theatres / "Fixture.ini").write_text(
            "[GUI]\nDisplayName=Fixture terrain\n\n"
            "[Theater]\nDCSID=FixtureMap\nDefaultMapCenter=0,0\n",
            encoding="utf-8",
        )
        database = self.root / "DatabaseJSON"
        bounds = database / "TheaterTerrainBounds"
        bounds.mkdir(parents=True)
        (database / "TheatersAirbases.json").write_text("[]", encoding="utf-8")
        self.bounds_path = bounds / "FixtureMap.json"
        self._write_geometry()
        self.git_patcher = patch(
            "dcsmizzer.coastline._git_state",
            return_value=dict(ACKNOWLEDGED),
        )
        self.git_patcher.start()
        self.blob_patcher = patch(
            "dcsmizzer.coastline._git_source_payload",
            side_effect=self._fixture_git_source,
        )
        self.blob_patcher.start()

    def tearDown(self) -> None:
        self.blob_patcher.stop()
        self.git_patcher.stop()
        self.temporary.cleanup()

    def test_exact_water_offset_uses_global_minimum_boundary_distance(self) -> None:
        report = br_coastline_report(
            self.root,
            "Fixture terrain",
            map_x=10,
            map_y=50,
            offset_distance_m=25,
            target_side="water",
        )

        self.assertEqual(report["schema"], "dcsmizzer.br-coastline/v1")
        self.assertEqual(report["terrain"], "FixtureMap")
        self.assertEqual(report["input"]["mask_classification"], "land")
        self.assertAlmostEqual(
            report["nearest_planning_land_mass_boundary"]["minimum_distance_m"],
            10.0,
        )
        self.assertEqual(
            report["offset"]["destination"],
            {"x": -25.0, "y": 50.0},
        )
        self.assertEqual(report["offset"]["mask_classification"], "water")
        self.assertAlmostEqual(report["offset"]["minimum_distance_m"], 25.0)
        self.assertEqual(report["offset"]["distance_residual_m"], 0.0)
        self.assertTrue(report["validation"]["usable_for_generation"])
        self.assertEqual(len(report["source"]["sha256"]), 64)
        self.assertEqual(report["source"]["sha256_scope"], "git_HEAD_blob_bytes")
        self.assertTrue(report["source"]["worktree_matches_parsed_source"])
        self.assertTrue(report["decision_source_binding"]["bound_to_head"])
        self.assertEqual(
            report["decision_source_binding"]["parsed_from_head_blobs"],
            2,
        )
        self.assertEqual(
            report["theatre_declaration_source"]["sha256_scope"],
            "git_HEAD_blob_bytes",
        )
        self.assertFalse(report["dcs_started"])
        self.assertLess(
            len(json.dumps(report, ensure_ascii=False).encode("utf-8")),
            12 * 1024,
        )

    def test_exact_land_offset_selects_opposite_normal(self) -> None:
        report = br_coastline_report(
            self.root,
            "FixtureMap",
            map_x=10,
            map_y=50,
            offset_distance_m=25,
            target_side="land",
        )

        self.assertEqual(
            report["offset"]["destination"],
            {"x": 25.0, "y": 50.0},
        )
        self.assertEqual(report["offset"]["mask_classification"], "land")
        self.assertAlmostEqual(report["offset"]["minimum_distance_m"], 25.0)

    def test_measure_only_reports_nearest_boundary_without_offset(self) -> None:
        report = br_coastline_report(
            self.root,
            "FixtureMap",
            map_x=-40,
            map_y=50,
        )

        self.assertEqual(report["input"]["mask_classification"], "water")
        self.assertAlmostEqual(
            report["nearest_planning_land_mass_boundary"]["minimum_distance_m"],
            40.0,
        )
        self.assertIsNone(report["offset"])
        self.assertTrue(report["validation"]["usable_for_generation"])

    def test_repeated_vertex_does_not_select_a_degenerate_segment(self) -> None:
        self._write_geometry(
            land=[[[0, 0], [0, 0], [100, 0], [100, 100], [0, 100]]]
        )

        report = br_coastline_report(
            self.root,
            "FixtureMap",
            map_x=50,
            map_y=-5,
            offset_distance_m=10,
            target_side="water",
        )

        self.assertEqual(report["offset"]["destination"], {"x": 50.0, "y": -10.0})
        self.assertTrue(report["offset"]["satisfied"])

    def test_other_land_mass_prevents_false_exact_offset(self) -> None:
        self._write_geometry(
            land=[
                [[0, 0], [100, 0], [100, 100], [0, 100]],
                [[-20, 40], [-10, 40], [-10, 60], [-20, 60]],
            ]
        )

        with self.assertRaisesRegex(ValueError, "no unique exact candidate"):
            br_coastline_report(
                self.root,
                "FixtureMap",
                map_x=10,
                map_y=50,
                offset_distance_m=25,
                target_side="water",
            )

    def test_offset_requires_requested_planning_mask_side(self) -> None:
        self._write_geometry(waters=[])

        with self.assertRaisesRegex(ValueError, "no unique exact candidate"):
            br_coastline_report(
                self.root,
                "FixtureMap",
                map_x=10,
                map_y=50,
                offset_distance_m=25,
                target_side="water",
            )

    def test_unacknowledged_source_is_reported_but_not_generation_usable(self) -> None:
        with patch(
            "dcsmizzer.coastline._git_state",
            return_value={**ACKNOWLEDGED, "acknowledged": False},
        ):
            report = br_coastline_report(
                self.root,
                "FixtureMap",
                map_x=10,
                map_y=50,
            )

        self.assertIn("unacknowledged", report["authority"])
        self.assertFalse(report["validation"]["source_commit_bound"])
        self.assertFalse(report["validation"]["usable_for_generation"])

    def test_acknowledged_checkout_without_head_blob_fails_closed(self) -> None:
        with patch(
            "dcsmizzer.coastline._git_source_payload",
            side_effect=lambda root, source, payload, upstream, maximum_bytes: (
                payload,
                self._source_binding(
                    bound=False,
                    relative=source.relative_to(root).as_posix(),
                ),
            ),
        ):
            report = br_coastline_report(
                self.root,
                "FixtureMap",
                map_x=10,
                map_y=50,
            )

        self.assertIn("unacknowledged", report["authority"])
        self.assertFalse(report["decision_source_binding"]["bound_to_head"])
        self.assertFalse(report["validation"]["usable_for_generation"])

    def test_malformed_geometry_and_invalid_numbers_fail_closed(self) -> None:
        malformed_payloads = (
            '{"waters": [], "waters": [], "landMasses": [[[0,0],[1,0],[0,1]]]}',
            json.dumps({"waters": [], "landMasses": [[[0, 0], [1, 0], [0, 0]]]}),
            json.dumps({"waters": [], "landMasses": []}),
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload[:40]):
                self.bounds_path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    br_coastline_report(
                        self.root,
                        "FixtureMap",
                        map_x=0,
                        map_y=0,
                    )

        self._write_geometry()
        for invalid in (True, float("nan"), 100_000_001, 10**400):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    br_coastline_report(
                        self.root,
                        "FixtureMap",
                        map_x=invalid,
                        map_y=0,
                    )

        with self.assertRaises(ValueError):
            br_coastline_report(
                self.root,
                "FixtureMap",
                map_x=0,
                map_y=0,
                offset_distance_m=10**400,
            )

    def test_cli_emits_full_report_and_exit_status_tracks_authority(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = main(
                [
                    "br-coastline",
                    "--br-root",
                    str(self.root),
                    "--terrain",
                    "FixtureMap",
                    "--x",
                    "10",
                    "--y",
                    "50",
                    "--offset-distance",
                    "25",
                    "--side",
                    "water",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["schema"], "dcsmizzer.br-coastline/v1")
        self.assertTrue(report["validation"]["usable_for_generation"])

    def _write_geometry(
        self,
        *,
        waters: list[list[list[float]]] | None = None,
        land: list[list[list[float]]] | None = None,
    ) -> None:
        self.bounds_path.write_text(
            json.dumps(
                {
                    "waters": waters
                    if waters is not None
                    else [[[-200, -200], [200, -200], [200, 200], [-200, 200]]],
                    "landMasses": land
                    if land is not None
                    else [[[0, 0], [100, 0], [100, 100], [0, 100]]],
                }
            ),
            encoding="utf-8",
        )

    def _fixture_git_source(
        self,
        root: Path,
        source: Path,
        payload: bytes,
        upstream: dict[str, object],
        *,
        maximum_bytes: int,
    ) -> tuple[bytes, dict[str, object]]:
        del maximum_bytes
        bound = upstream.get("acknowledged") is True
        return payload, self._source_binding(
            bound=bound,
            relative=source.relative_to(root).as_posix(),
        )

    @staticmethod
    def _source_binding(*, bound: bool, relative: str) -> dict[str, object]:
        return {
            "basis": "fixture exact Git blob",
            "head_commit": "a" * 40,
            "relative_path": relative,
            "git_tree_read": bound,
            "git_mode": "100644" if bound else None,
            "git_blob_oid": "b" * 40 if bound else None,
            "worktree_regular_file": True,
            "parsed_from": "git_HEAD_blob" if bound else "unbound_worktree_file",
            "bound_to_head": bound,
        }


if __name__ == "__main__":
    unittest.main()
