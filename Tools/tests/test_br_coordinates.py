from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.br_coordinates import (  # noqa: E402
    br_coordinate_report,
)
from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer.coordinates import (  # noqa: E402
    ProjectionFit,
    _latlon_to_map,
)


KNOWN_FIT = ProjectionFit(
    central_meridian=21,
    scale_factor=0.9996,
    false_easting=35_427.62,
    false_northing=-6_061_633.128,
    rms_error_m=0.0,
    max_error_m=0.0,
)
LOCATIONS = (
    (52.5200, 13.4050),
    (53.5511, 9.9937),
    (51.0504, 13.7373),
    (54.0924, 12.0991),
    (50.1109, 8.6821),
    (51.3397, 12.3731),
    (52.3759, 9.7320),
)


class BriefingRoomCoordinateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        theatre_dir = self.root / "Database" / "Theaters"
        theatre_dir.mkdir(parents=True)
        (theatre_dir / "Fixture.ini").write_text(
            "[GUI]\n"
            "DisplayName=Fixture terrain\n\n"
            "[Theater]\n"
            "DCSID=FixtureMap\n"
            "DefaultMapCenter=10,20\n",
            encoding="utf-8",
        )
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        source.parent.mkdir()
        source.write_text(
            json.dumps(self._synthetic_airbases()),
            encoding="utf-8",
        )
        project_source = self.root / "src" / "BriefingRoom" / "BriefingRoom.cs"
        project_source.parent.mkdir(parents=True)
        project_source.write_text(
            'const string TARGETED_DCS_WORLD_VERSION = "2.9.fixture";\n',
            encoding="utf-8",
        )
        self._git("init", "--quiet")
        self._commit_all("fixture")
        self.source_lock_patcher = patch(
            "dcsmizzer.br_static.upstream_source_lock_status",
            side_effect=self._fixture_source_lock,
        )
        self.source_lock_patcher.start()

    def tearDown(self) -> None:
        self.source_lock_patcher.stop()
        self.temporary.cleanup()

    def test_clean_commit_bound_projection_converts_and_stays_compact(
        self,
    ) -> None:
        report = br_coordinate_report(
            self.root,
            "Fixture terrain",
            latitude=60.0,
            longitude=30.0,
        )

        self.assertTrue(report["validation"]["validated"])
        self.assertTrue(report["upstream"]["acknowledged"])
        self.assertEqual(
            report["authority"],
            "derived_commit_bound_br_airbase_export_projection",
        )
        self.assertEqual(report["model"]["central_meridian"], 21)
        self.assertEqual(
            report["source_mapping"],
            {
                "latitude": "pos.World.lat",
                "longitude": "pos.World.lon",
                "mission_x": "pos.DCS.x",
                "mission_y": "pos.DCS.z",
                "ignored": ["pos.World.alt", "pos.DCS.y"],
            },
        )
        self.assertEqual(report["coverage"]["fit_samples"], len(LOCATIONS))
        self.assertTrue(report["coverage"]["all_unique_finite_samples_used"])
        self.assertTrue(report["validation"]["leave_one_out"]["same_central_meridian"])
        self.assertLess(
            report["validation"]["leave_one_out"]["maximum_forward_error_m"],
            0.01,
        )
        self.assertEqual(
            report["conversion"]["direction"],
            "WGS84_to_mission_local",
        )
        self.assertTrue(report["extrapolation"]["outside_sample_envelope"])
        self.assertIsNone(report["runtime_valid"])
        self.assertEqual(
            report["upstream_project_version"]["targeted_dcs_world_version"],
            "2.9.fixture",
        )
        self.assertEqual(len(report["source_sha256"]), 64)
        self.assertEqual(
            report["source_sha256_scope"],
            "git_HEAD_blob_bytes",
        )
        self.assertTrue(
            report["decision_source_binding"]["all_required_sources_bound_to_head"]
        )
        self.assertEqual(
            report["decision_source_binding"]["required_sources"],
            2,
        )
        self.assertEqual(
            report["decision_source_binding"]["parsed_from_head_blobs"],
            2,
        )
        self.assertLess(
            len(json.dumps(report, ensure_ascii=False).encode("utf-8")),
            12 * 1024,
        )

    def test_inverse_conversion_round_trips_a_sample(self) -> None:
        latitude, longitude = LOCATIONS[0]
        map_x, map_y = _latlon_to_map(latitude, longitude, KNOWN_FIT)

        report = br_coordinate_report(
            self.root,
            "FixtureMap",
            map_x=map_x,
            map_y=map_y,
        )

        self.assertTrue(report["validation"]["validated"])
        self.assertEqual(
            report["conversion"]["direction"],
            "mission_local_to_WGS84",
        )
        self.assertAlmostEqual(
            report["conversion"]["output"]["latitude"],
            latitude,
            places=5,
        )
        self.assertAlmostEqual(
            report["conversion"]["output"]["longitude"],
            longitude,
            places=5,
        )
        self.assertFalse(report["extrapolation"]["outside_sample_envelope"])

    def test_dirty_checkout_fails_closed_despite_good_fit(self) -> None:
        (self.root / "uncommitted.txt").write_text(
            "dirty",
            encoding="utf-8",
        )

        report = br_coordinate_report(
            self.root,
            "FixtureMap",
            latitude=52.52,
            longitude=13.405,
        )

        self.assertFalse(report["validation"]["validated"])
        self.assertIn(
            "upstream_checkout_not_clean_commit_bound",
            report["validation"]["failure_reasons"],
        )
        self.assertIsNone(report["model"])
        self.assertIsNone(report["conversion"])
        self.assertIsNotNone(report["validation"]["best_candidate"])

    def test_clean_checkout_rejects_ignored_untracked_airbase_export(
        self,
    ) -> None:
        source_relative = "DatabaseJSON/TheatersAirbases.json"
        self._git("rm", "--cached", "--quiet", source_relative)
        (self.root / ".gitignore").write_text(
            f"{source_relative}\n",
            encoding="utf-8",
        )
        self._commit_all("ignore decision source")

        report = br_coordinate_report(
            self.root,
            "FixtureMap",
            latitude=52.52,
            longitude=13.405,
        )

        self.assertEqual(report["upstream"]["provenance"], "commit_bound")
        self.assertFalse(report["validation"]["validated"])
        self.assertIn(
            "decision_sources_not_bound_to_head",
            report["validation"]["failure_reasons"],
        )
        self.assertEqual(
            report["authority"],
            "derived_unbound_br_airbase_export_projection_candidate",
        )
        self.assertFalse(
            report["decision_source_binding"]["all_required_sources_bound_to_head"]
        )
        self.assertEqual(
            report["decision_source_binding"]["unbound_sources"],
            [source_relative],
        )
        self.assertIsNone(report["model"])
        self.assertIsNone(report["conversion"])

    def test_too_few_unique_samples_fail_closed(self) -> None:
        self._write_airbases(self._synthetic_airbases()[:4])
        self._commit_all("too few")

        report = br_coordinate_report(
            self.root,
            "FixtureMap",
            latitude=52.52,
            longitude=13.405,
        )

        self.assertFalse(report["validation"]["validated"])
        self.assertEqual(
            report["validation"]["failure_reasons"],
            ["too_few_unique_finite_coordinate_samples"],
        )
        self.assertIsNone(report["model"])
        self.assertIsNone(report["conversion"])

    def test_invalid_coordinate_record_is_counted_but_not_fitted(
        self,
    ) -> None:
        airbases = self._synthetic_airbases()
        airbases.append(
            {
                "theatre": "FixtureMap",
                "ID": 99,
                "displayName": "Invalid coordinate",
                "pos": {
                    "DCS": {"x": 1.0, "z": None},
                    "World": {"lat": 52.0, "lon": 13.0},
                },
            }
        )
        self._write_airbases(airbases)
        self._commit_all("invalid coordinate evidence")

        report = br_coordinate_report(self.root, "FixtureMap")

        self.assertTrue(report["validation"]["validated"])
        self.assertEqual(report["coverage"]["invalid_coordinate_records"], 1)
        self.assertFalse(
            report["coverage"]["all_airbase_records_have_usable_coordinates"]
        )
        self.assertFalse(report["coverage"]["invalid_coordinate_records_used"])
        self.assertIn(
            "their presence does not independently fail",
            report["validation"]["invalid_coordinate_policy"],
        )

    def test_huge_integer_coordinate_is_invalid_without_overflow(
        self,
    ) -> None:
        airbases = self._synthetic_airbases()
        airbases.append(
            {
                "theatre": "FixtureMap",
                "ID": 99,
                "displayName": "Huge integer coordinate",
                "pos": {
                    "DCS": {"x": 10**400, "z": 1.0},
                    "World": {"lat": 52.0, "lon": 13.0},
                },
            }
        )
        self._write_airbases(airbases)
        self._commit_all("huge integer coordinate evidence")

        report = br_coordinate_report(self.root, "FixtureMap")

        self.assertTrue(report["validation"]["validated"])
        self.assertEqual(report["coverage"]["invalid_coordinate_records"], 1)

    def test_deep_airbase_json_fails_cleanly_at_cli_boundary(self) -> None:
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        source.write_text(
            "[" * 10_000 + "0" + "]" * 10_000,
            encoding="utf-8",
        )
        self._commit_all("deep airbase JSON")
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            [
                "br-coordinates",
                "--br-root",
                str(self.root),
                "--terrain",
                "FixtureMap",
            ],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("nesting-depth limit", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_airbase_export_record_limit_fails_closed(self) -> None:
        self._write_airbases([{} for _ in range(10_001)])
        self._commit_all("too many airbase records")

        with self.assertRaisesRegex(ValueError, "record limit"):
            br_coordinate_report(self.root, "FixtureMap")

    def test_duplicate_diagnostics_bound_untrusted_names_and_output(
        self,
    ) -> None:
        airbases = self._synthetic_airbases()
        for index, original in enumerate(list(airbases)[:5], start=100):
            duplicate = json.loads(json.dumps(original))
            duplicate["ID"] = index
            duplicate["displayName"] = "N" * 100_000
            airbases.append(duplicate)
        self._write_airbases(airbases)
        self._commit_all("large duplicate diagnostic names")

        report = br_coordinate_report(self.root, "FixtureMap")

        diagnostics = report["duplicate_coordinate_diagnostics"]
        self.assertEqual(diagnostics["groups_total"], 5)
        references = [
            reference
            for group in diagnostics["groups"]
            for reference in group["record_references"]
        ]
        self.assertTrue(any(item["name_truncated"] for item in references))
        self.assertTrue(all(len(item["name"]) <= 128 for item in references))
        encoded = (
            (
                json.dumps(
                    report,
                    allow_nan=False,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            .replace("\n", "\r\n")
            .encode("utf-8")
        )
        self.assertLessEqual(len(encoded), 12 * 1024)

    def test_repeated_placeholder_is_reported_and_not_removed(self) -> None:
        airbases = self._synthetic_airbases()
        placeholder = {
            "theatre": "FixtureMap",
            "pos": {
                "DCS": {
                    "x": -3_759_657.0,
                    "y": "ignored",
                    "z": -9_428_368.0,
                },
                "World": {
                    "lat": 0.0,
                    "lon": 0.0,
                    "alt": "ignored",
                },
            },
        }
        for index in range(3):
            airbases.append(
                {
                    **placeholder,
                    "ID": 100 + index,
                    "displayName": f"Placeholder {index}",
                }
            )
        self._write_airbases(airbases)
        self._commit_all("placeholder evidence")

        report = br_coordinate_report(
            self.root,
            "FixtureMap",
            latitude=52.52,
            longitude=13.405,
        )

        self.assertFalse(report["validation"]["validated"])
        self.assertEqual(
            report["coverage"]["unique_finite_coordinate_samples"],
            len(LOCATIONS) + 1,
        )
        self.assertEqual(report["coverage"]["duplicate_coordinate_records"], 2)
        self.assertEqual(
            report["validation"]["outlier_policy"],
            "exact duplicate tuples are collapsed; every distinct finite "
            "tuple is fitted; no outlier or placeholder candidate is removed",
        )
        duplicate = report["duplicate_coordinate_diagnostics"]["groups"][0]
        self.assertEqual(
            duplicate["classification"],
            "possible_repeated_placeholder_coordinate",
        )
        self.assertEqual(duplicate["occurrences"], 3)
        self.assertEqual(
            [item["airdrome_id"] for item in duplicate["record_references"]],
            [100, 101, 102],
        )
        self.assertIsNone(report["model"])
        self.assertIsNone(report["conversion"])
        self.assertTrue(
            any(
                reason.startswith("best_candidate_")
                or reason.startswith("leave_one_out_")
                for reason in report["validation"]["failure_reasons"]
            )
        )

    def test_ambiguous_theatre_identity_is_rejected(self) -> None:
        duplicate = self.root / "Database" / "Theaters" / "Duplicate.ini"
        duplicate.write_text(
            "[GUI]\n"
            "DisplayName=Duplicate\n\n"
            "[Theater]\n"
            "DCSID=FixtureMap\n"
            "DefaultMapCenter=0,0\n",
            encoding="utf-8",
        )
        self._commit_all("ambiguous theatre identity")

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            br_coordinate_report(self.root, "FixtureMap")

    def test_partial_or_nonfinite_conversion_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "supplied together"):
            br_coordinate_report(
                self.root,
                "FixtureMap",
                latitude=52.0,
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            br_coordinate_report(
                self.root,
                "FixtureMap",
                map_x=True,
                map_y=1.0,
            )
        with self.assertRaisesRegex(ValueError, "numeric range"):
            br_coordinate_report(
                self.root,
                "FixtureMap",
                map_x=1e308,
                map_y=1e308,
            )

    def _synthetic_airbases(self) -> list[dict[str, object]]:
        records = []
        for index, (latitude, longitude) in enumerate(LOCATIONS, start=1):
            map_x, map_y = _latlon_to_map(
                latitude,
                longitude,
                KNOWN_FIT,
            )
            records.append(
                {
                    "theatre": "FixtureMap",
                    "ID": index,
                    "displayName": f"Fixture {index}",
                    "pos": {
                        "DCS": {
                            "x": map_x,
                            "y": "deliberately ignored",
                            "z": map_y,
                        },
                        "World": {
                            "lat": latitude,
                            "lon": longitude,
                            "alt": "deliberately ignored",
                        },
                    },
                }
            )
        return records

    def _write_airbases(self, records: list[dict[str, object]]) -> None:
        source = self.root / "DatabaseJSON" / "TheatersAirbases.json"
        source.write_text(json.dumps(records), encoding="utf-8")

    def _commit_all(self, message: str) -> None:
        self._git("add", ".")
        self._git(
            "-c",
            "user.name=DCSMizzer Tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "--quiet",
            "-m",
            message,
        )

    @staticmethod
    def _fixture_source_lock(
        checkout_root: Path,
        source_key: str,
    ) -> dict[str, object]:
        def query(*arguments: str) -> str | None:
            result = subprocess.run(
                ["git", "-C", str(checkout_root), *arguments],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout.strip() if result.returncode == 0 else None

        commit = query("rev-parse", "HEAD")
        status = query("status", "--porcelain")
        clean = status == "" if status is not None else None
        branch = query("branch", "--show-current")
        acknowledged = commit is not None and clean is True
        return {
            "schema": "dcsmizzer.acknowledged-upstream-source-lock/v1",
            "source": source_key,
            "acknowledged": acknowledged,
            "actual": {
                "exact_checkout_root": True,
                "head": commit,
                "branch": branch,
                "detached": branch == "",
                "clean": clean,
                "remote": "https://example.invalid/briefing-room.git",
            },
            "validation": {"usable": acknowledged},
            "failure_reasons": [] if acknowledged else ["dirty_worktree"],
            "errors": [],
        }

    def _git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


if __name__ == "__main__":
    unittest.main()
