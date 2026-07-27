from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.observed import (  # noqa: E402
    ObservedRoot,
    build_observed_registry,
)
import dcsmizzer.observed as observed_module  # noqa: E402


MISSION = b"""
mission = {
  version = 23,
  theatre = "FixtureMap",
  requiredModules = {},
  date = { Year = 1988, Month = 7, Day = 28 },
  start_time = 50400,
  weather = {
    atmosphere_type = 0,
    clouds = {
      base = 500,
      thickness = 1200,
      density = 9,
      preset = "FixturePreset",
    },
    wind = {
      atGround = { speed = 15, dir = 240 },
    },
  },
  coalition = {
    blue = {
      country = {
        [1] = {
          id = 2,
          name = "Private Country Label",
          plane = {
            group = {
              [1] = {
                name = "Private Group Name",
                task = "CAP",
                groupId = 10,
                route = {
                  points = {
                    [1] = {
                      type = "TakeOffParking",
                      action = "From Parking Area",
                      airdromeId = 7,
                      x = 1000,
                      y = 2000,
                      alt = 50,
                      task = {
                        id = "ComboTask",
                        params = {
                          tasks = {
                            [1] = { id = "EngageTargets", params = {}, },
                          },
                        },
                      },
                    },
                  },
                },
                units = {
                  [1] = {
                    name = "Private Lead",
                    unitId = 1,
                    type = "Fixture Plane",
                    skill = "Player",
                    parking = 12,
                    parking_id = "36",
                    x = 1000,
                    y = 2000,
                    alt = 50,
                    heading = 1.5,
                    payload = {
                      pylons = {
                        [1] = { CLSID = "{ONE}", },
                        [4] = { CLSID = "{TANK}", },
                      },
                    },
                  },
                  [2] = {
                    name = "Private Wingman",
                    unitId = 2,
                    type = "Fixture Plane",
                    skill = "Excellent",
                    parking = 13,
                    parking_id = "37",
                    x = 1010,
                    y = 2010,
                    alt = 50,
                    heading = 1.5,
                    payload = {
                      pylons = {
                        [1] = { CLSID = "{ONE}", },
                        [4] = { CLSID = "{TANK}", },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  },
  triggers = {
    zones = {
      [1] = {
        zoneId = 1,
        name = "Private Zone Name",
        radius = 10000,
        x = 5000,
        y = 6000,
        type = 0,
      },
    },
  },
  trigrules = {
    [1] = {
      comment = "Private Trigger Comment",
      rules = {
        [1] = { predicate = "return(c_time_after(60))", },
      },
      actions = {
        [1] = { predicate = "a_set_mission_result(100)", },
      },
    },
  },
  goals = {
    [1] = {
      side = 0,
      score = 100,
      predicate = "return(c_flag_is_true(1))",
    },
  },
}
"""


def write_miz(path: Path, *, mission: bytes = MISSION) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mission", mission)
        archive.writestr(
            "options",
            b"""
            options = {
              playerName = "Private Pilot",
              difficulty = { easyFlight = false },
              sound = { main_output = "{PRIVATE-DEVICE-GUID}" },
              plugins = {},
            }
            """,
        )
        archive.writestr(
            "warehouses",
            b"""
            warehouses = {
              airports = {
                [7] = {
                  coalition = "BLUE",
                  unlimitedFuel = true,
                },
              },
              warehouses = {},
            }
            """,
        )
        archive.writestr("l10n/DEFAULT/dictionary", b"dictionary = {}")
        archive.writestr("l10n/DEFAULT/mapResource", b"mapResource = {}")


class ObservedRegistryTests(unittest.TestCase):
    def test_registry_links_unit_payload_start_and_parking_without_private_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_root = root / "official"
            second_root = root / "mirror"
            first_root.mkdir()
            second_root.mkdir()
            first = first_root / "Private Mission Name.miz"
            duplicate = second_root / "Another Private Name.miz"
            write_miz(first)
            shutil.copyfile(first, duplicate)

            report = build_observed_registry(
                (
                    ObservedRoot("installed", first_root),
                    ObservedRoot("mirror", second_root),
                )
            )

        encoded = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["coverage"]["file_instances"], 2)
        self.assertEqual(report["coverage"]["unique_missions"], 1)
        self.assertEqual(report["coverage"]["duplicate_instances"], 1)
        self.assertEqual(
            report["theatres"],
            [
                {
                    "theatre_ref": "observed-theatre-1",
                    "identity_source": "anonymous_observation",
                    "missions": 1,
                }
            ],
        )
        unit = report["unit_types"][0]
        self.assertEqual(unit["unit_type_ref"], "observed-unit-type-1")
        self.assertEqual(unit["identity_source"], "anonymous_observation")
        self.assertEqual(unit["units_observed"], 2)
        self.assertEqual(unit["missions_observed"], 1)
        self.assertEqual(unit["start_modes"], {"cold_parking": 1})
        payload = report["payloads"][0]
        self.assertEqual(
            payload["assignments"],
            [
                {
                    "station": 1,
                    "station_evidence": "table_key",
                    "store_ref": "observed-store-1",
                    "store_identity_source": "anonymous_observation",
                },
                {
                    "station": 4,
                    "station_evidence": "table_key",
                    "store_ref": "observed-store-2",
                    "store_identity_source": "anonymous_observation",
                },
            ],
        )
        airbase = report["airbases"][0]
        self.assertEqual(airbase["airdrome_id"], 7)
        self.assertEqual(len(airbase["parkings"]), 2)
        environment = report["environment"]
        self.assertEqual(environment["missions_observed"], 1)
        self.assertEqual(environment["weather"]["missions_present"], 1)
        self.assertTrue(
            all(
                item["path_ref"].startswith("weather-scalar-")
                for item in environment["weather"]["scalars"]
            )
        )
        logic = environment["logic"]
        self.assertEqual(
            logic["condition_predicate_functions"],
            {
                "distinct": 1,
                "occurrences": 1,
                "frequency_distribution": [
                    {
                        "occurrences_per_identity": 1,
                        "identities": 1,
                    }
                ],
                "identities_returned": False,
            },
        )
        self.assertEqual(
            logic["action_predicate_functions"]["occurrences"],
            1,
        )
        self.assertEqual(
            logic["goal_predicate_functions"]["occurrences"],
            1,
        )
        core = report["core_tables"]
        self.assertEqual(core["required_modules"]["missions_empty"], 1)
        self.assertEqual(core["options"]["player_name_nonempty"], 1)
        self.assertEqual(
            core["options"]["nonempty_audio_device_field_counts"],
            {"main_output": 1},
        )
        self.assertFalse(core["options"]["private_values_returned"])
        self.assertEqual(
            core["warehouses"]["route_airdrome_references_missing"],
            0,
        )
        self.assertEqual(
            core["warehouses"]["route_airdrome_references_resolved"],
            1,
        )
        self.assertNotIn("Private Mission Name", encoded)
        self.assertNotIn("Private Group Name", encoded)
        self.assertNotIn("Private Lead", encoded)
        self.assertNotIn("Private Trigger Comment", encoded)
        self.assertNotIn("Private Zone Name", encoded)
        self.assertNotIn("Private Pilot", encoded)
        self.assertNotIn("PRIVATE-DEVICE-GUID", encoded)
        self.assertNotIn("FixtureMap", encoded)
        self.assertNotIn("Fixture Plane", encoded)
        self.assertNotIn("{ONE}", encoded)
        self.assertNotIn("{TANK}", encoded)
        self.assertNotIn("c_time_after", encoded)
        self.assertNotIn(str(first_root), encoded)
        self.assertFalse(report["coverage"]["content_identity_returned"])

    def test_registry_filters_exact_theatre_and_unit_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_miz(root / "fixture.miz")

            matching = build_observed_registry(
                (ObservedRoot("sample", root),),
                theatre="FixtureMap",
                unit_type="Fixture Plane",
                category="plane",
            )
            missing = build_observed_registry(
                (ObservedRoot("sample", root),),
                unit_type="Missing Plane",
            )

        self.assertEqual(len(matching["unit_types"]), 1)
        self.assertEqual(matching["coverage"]["missions_matching_filters"], 1)
        self.assertEqual(
            matching["theatres"][0]["theatre_ref"],
            "FixtureMap",
        )
        self.assertEqual(
            matching["unit_types"][0]["unit_type_ref"],
            "Fixture Plane",
        )
        self.assertEqual(
            matching["unit_types"][0]["identity_source"],
            "caller_exact_filter",
        )
        self.assertEqual(missing["unit_types"], [])
        self.assertEqual(missing["coverage"]["missions_matching_filters"], 0)

    def test_registry_reports_archive_failure_reason_without_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "Private Duplicate.miz"
            write_miz(path)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "a") as archive:
                    archive.writestr("mission", MISSION)
            with patch.object(
                observed_module,
                "_snapshot_and_hash_bound_stream",
                side_effect=AssertionError(
                    "policy-rejected archives must not be copied or hashed"
                ),
            ) as snapshot:
                report = build_observed_registry(
                    (ObservedRoot("sample", root),)
                )

        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"archive_duplicate_members": 1},
        )
        self.assertNotIn("Private Duplicate", json.dumps(report))
        snapshot.assert_not_called()

    def test_registry_rejects_raw_container_over_policy_before_opening(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "PRIVATE_OVERSIZED_INPUT.miz"
            write_miz(path)
            policy = observed_module.ArchivePolicy(
                max_total_uncompressed=path.stat().st_size - 1,
            )
            with (
                patch.object(
                    observed_module,
                    "ArchivePolicy",
                    return_value=policy,
                ),
                patch.object(
                    observed_module.os,
                    "open",
                    side_effect=AssertionError(
                        "over-policy input must not be opened"
                    ),
                ) as open_file,
                patch.object(
                    observed_module,
                    "inspect_miz",
                    side_effect=AssertionError(
                        "over-policy input must not reach ZIP inspection"
                    ),
                ) as inspect,
            ):
                report = build_observed_registry(
                    (ObservedRoot("sample", root),)
                )

        self.assertEqual(report["coverage"]["file_instances"], 1)
        self.assertEqual(report["coverage"]["unique_contents_seen"], 0)
        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"archive_policy_input_size_limit": 1},
        )
        self.assertNotIn("PRIVATE_OVERSIZED_INPUT", json.dumps(report))
        open_file.assert_not_called()
        inspect.assert_not_called()

    def test_registry_inspects_then_hashes_bound_stream_without_unbounded_read(
        self,
    ) -> None:
        events: list[tuple[str, int | None]] = []

        class TrackingStream:
            def __init__(self, wrapped: object) -> None:
                self.wrapped = wrapped

            def read(self, size: int = -1) -> bytes:
                events.append(("read", size))
                if size is None or size < 0:
                    raise AssertionError("raw MIZ reads must be bounded")
                return self.wrapped.read(size)  # type: ignore[attr-defined]

            def __enter__(self) -> TrackingStream:
                return self

            def __exit__(self, *args: object) -> object:
                return self.wrapped.__exit__(*args)  # type: ignore[attr-defined]

            def __getattr__(self, name: str) -> object:
                return getattr(self.wrapped, name)

        original_fdopen = observed_module.os.fdopen
        original_inspect = observed_module.inspect_miz

        def tracking_fdopen(*args: object, **kwargs: object) -> TrackingStream:
            return TrackingStream(original_fdopen(*args, **kwargs))

        def tracking_inspect(*args: object, **kwargs: object) -> object:
            events.append(("inspect", None))
            return original_inspect(*args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_miz(root / "fixture.miz")
            with (
                patch.object(
                    observed_module.os,
                    "fdopen",
                    side_effect=tracking_fdopen,
                ),
                patch.object(
                    observed_module,
                    "inspect_miz",
                    side_effect=tracking_inspect,
                ),
            ):
                report = build_observed_registry(
                    (ObservedRoot("sample", root),)
                )

        self.assertEqual(report["coverage"]["unique_missions"], 1)
        self.assertEqual(events[0], ("inspect", None))
        raw_read_sizes = [
            size for event, size in events if event == "read"
        ]
        self.assertTrue(raw_read_sizes)
        self.assertTrue(
            all(size is not None and size >= 0 for size in raw_read_sizes)
        )

    def test_registry_crc_failure_never_parses_snapshot(self) -> None:
        verify_crc_calls: list[bool] = []
        original_inspect = observed_module.inspect_miz

        def fail_snapshot_crc(
            path: object,
            *,
            policy: object = None,
            verify_crc: bool = True,
        ) -> object:
            verify_crc_calls.append(verify_crc)
            report = original_inspect(
                path,
                policy=policy,
                verify_crc=verify_crc,
            )
            if verify_crc:
                return replace(report, crc_status="failed")
            return report

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_miz(root / "PRIVATE_CRC_FAILURE.miz")
            with (
                patch.object(
                    observed_module,
                    "inspect_miz",
                    side_effect=fail_snapshot_crc,
                ),
                patch.object(
                    observed_module,
                    "parse_lua_bytes",
                    side_effect=AssertionError(
                        "snapshot members must not parse before CRC passes"
                    ),
                ) as parser,
            ):
                report = build_observed_registry(
                    (ObservedRoot("sample", root),)
                )

        self.assertEqual(verify_crc_calls, [False, True])
        parser.assert_not_called()
        self.assertEqual(report["coverage"]["unique_missions"], 0)
        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"archive_crc_failed": 1},
        )
        self.assertNotIn("PRIVATE_CRC_FAILURE", json.dumps(report))

    def test_registry_rejects_path_like_source_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "anonymous ASCII tokens"):
                build_observed_registry(
                    (ObservedRoot("C:\\Private\\Missions", Path(temp_dir)),)
                )

    def test_registry_never_returns_attacker_controlled_miz_strings(
        self,
    ) -> None:
        private = b"PRIVATE_PATIENT_NAME"
        injected = MISSION.replace(
            b"mission = {",
            b'mission = { PRIVATE_PATIENT_NAME = "PRIVATE_PATIENT_NAME",',
            1,
        )
        for original in (
            b"FixtureMap",
            b"FixturePreset",
            b"Private Country Label",
            b"Private Group Name",
            b"Private Lead",
            b"Private Wingman",
            b"Fixture Plane",
            b"CAP",
            b"Player",
            b"Excellent",
            b"TakeOffParking",
            b"From Parking Area",
            b"ComboTask",
            b"EngageTargets",
            b"{ONE}",
            b"{TANK}",
            b"Private Zone Name",
            b"Private Trigger Comment",
            b"c_time_after",
            b"a_set_mission_result",
            b"c_flag_is_true",
        ):
            injected = injected.replace(original, private)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "PRIVATE_PATIENT_NAME.miz"
            write_miz(
                path,
                mission=injected,
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            reports = (
                (
                    set(),
                    build_observed_registry(
                        (ObservedRoot("sample", root),)
                    ),
                ),
                (
                    {private.decode("ascii")},
                    build_observed_registry(
                        (ObservedRoot("sample", root),),
                        theatre=private.decode("ascii"),
                    ),
                ),
                (
                    {private.decode("ascii")},
                    build_observed_registry(
                        (ObservedRoot("sample", root),),
                        unit_type=private.decode("ascii"),
                    ),
                ),
            )

            for allowed_private_strings, report in reports:
                self.assertEqual(
                    report["coverage"]["missions_matching_filters"],
                    1,
                )
                observed_strings: list[str] = []

                def collect(value: object) -> None:
                    if isinstance(value, dict):
                        for key, child in value.items():
                            observed_strings.append(str(key))
                            collect(child)
                    elif isinstance(value, list):
                        for child in value:
                            collect(child)
                    elif isinstance(value, str):
                        observed_strings.append(value)

                collect(report)
                returned_private_strings = {
                    value
                    for value in observed_strings
                    if private.decode("ascii") in value
                }
                self.assertEqual(
                    returned_private_strings,
                    allowed_private_strings,
                )
                rendered = json.dumps(report)
                self.assertNotIn(str(root), rendered)
                self.assertNotIn(path.name, rendered)
                self.assertNotIn(digest, rendered)

    def test_registry_skips_file_and_directory_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_miz(outside / "PRIVATE_PATIENT_NAME.miz")
            try:
                (root / "linked.miz").symlink_to(
                    outside / "PRIVATE_PATIENT_NAME.miz"
                )
                (root / "linked-directory").symlink_to(
                    outside,
                    target_is_directory=True,
                )
            except OSError as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

            report = build_observed_registry(
                (ObservedRoot("sample", root),)
            )

        source = report["coverage"]["sources"][0]
        self.assertEqual(source["files_seen"], 0)
        self.assertEqual(
            source["errors"],
            {
                "discovery_directory_link_skipped": 1,
                "discovery_file_link_skipped": 1,
            },
        )
        self.assertNotIn("PRIVATE_PATIENT_NAME", json.dumps(report))

    def test_registry_rejects_a_root_file_link_without_disclosing_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            outside = base / "PRIVATE_PATIENT_NAME.miz"
            linked = base / "linked.miz"
            write_miz(outside)
            try:
                linked.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

            with self.assertRaisesRegex(
                ValueError,
                (
                    r"^observed root paths must not contain symbolic links, "
                    r"junctions, or reparse points$"
                ),
            ) as caught:
                build_observed_registry(
                    (ObservedRoot("sample", linked),)
                )

        self.assertNotIn("PRIVATE_PATIENT_NAME", str(caught.exception))

    def test_registry_rejects_links_in_root_path_ancestors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            outside = base / "outside"
            real_root = outside / "real-root"
            real_root.mkdir(parents=True)
            write_miz(real_root / "PRIVATE_PATIENT_NAME.miz")
            alias = base / "alias"
            try:
                alias.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(
                    f"symbolic links unavailable: {type(error).__name__}"
                )

            for supplied_root in (
                alias,
                alias / "real-root",
                alias / "real-root" / "PRIVATE_PATIENT_NAME.miz",
            ):
                with self.subTest(supplied_root=supplied_root.name):
                    with self.assertRaisesRegex(
                        ValueError,
                        "must not contain symbolic links",
                    ) as caught:
                        build_observed_registry(
                            (ObservedRoot("sample", supplied_root),)
                        )
                    self.assertNotIn(
                        "PRIVATE_PATIENT_NAME",
                        str(caught.exception),
                    )

    def test_registry_binds_discovered_directory_chain_before_read(
        self,
    ) -> None:
        outside_mission = MISSION.replace(
            b"FixtureMap",
            b"PRIVATE_OUTSIDE_THEATRE",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "root"
            source_directory = root / "source"
            outside = base / "outside"
            source_directory.mkdir(parents=True)
            outside.mkdir()
            write_miz(source_directory / "candidate.miz")
            write_miz(
                outside / "candidate.miz",
                mission=outside_mission,
            )
            moved = root / "source-before-swap"
            original_discover = observed_module._discover_miz

            def discover_then_swap(
                root_snapshot: object,
                errors: object,
            ) -> object:
                discovered = original_discover(root_snapshot, errors)
                source_directory.rename(moved)
                source_directory.symlink_to(
                    outside,
                    target_is_directory=True,
                )
                return discovered

            try:
                with patch.object(
                    observed_module,
                    "_discover_miz",
                    side_effect=discover_then_swap,
                ):
                    report = build_observed_registry(
                        (ObservedRoot("sample", root),)
                    )
            except OSError as error:
                self.skipTest(
                    f"symbolic links unavailable: {type(error).__name__}"
                )
            finally:
                if source_directory.is_symlink():
                    source_directory.unlink()
                if moved.exists():
                    moved.rename(source_directory)

        self.assertEqual(report["coverage"]["file_instances"], 1)
        self.assertEqual(report["coverage"]["unique_contents_seen"], 0)
        self.assertEqual(report["coverage"]["unique_missions"], 0)
        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"discovery_file_changed_skipped": 1},
        )
        self.assertNotIn("PRIVATE_OUTSIDE_THEATRE", json.dumps(report))

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_registry_rejects_root_and_nested_junctions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            outside = base / "outside"
            real_root = outside / "real-root"
            scanned = base / "scanned"
            real_root.mkdir(parents=True)
            scanned.mkdir()
            write_miz(real_root / "PRIVATE_PATIENT_NAME.miz")
            root_alias = base / "root-junction"
            nested_alias = scanned / "nested-junction"
            self._make_junction(root_alias, outside)
            self._make_junction(nested_alias, outside)

            with self.assertRaisesRegex(
                ValueError,
                "must not contain symbolic links",
            ):
                build_observed_registry(
                    (ObservedRoot("sample", root_alias / "real-root"),)
                )
            report = build_observed_registry(
                (ObservedRoot("sample", scanned),)
            )

        self.assertEqual(report["coverage"]["file_instances"], 0)
        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"discovery_directory_link_skipped": 1},
        )
        self.assertNotIn("PRIVATE_PATIENT_NAME", json.dumps(report))

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_registry_binds_discovered_chain_across_junction_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "root"
            source_directory = root / "source"
            outside = base / "outside"
            source_directory.mkdir(parents=True)
            outside.mkdir()
            write_miz(source_directory / "candidate.miz")
            write_miz(
                outside / "candidate.miz",
                mission=MISSION.replace(
                    b"FixtureMap",
                    b"PRIVATE_OUTSIDE_THEATRE",
                ),
            )
            moved = root / "source-before-swap"
            original_discover = observed_module._discover_miz

            def discover_then_swap(
                root_snapshot: object,
                errors: object,
            ) -> object:
                discovered = original_discover(root_snapshot, errors)
                source_directory.rename(moved)
                self._make_junction(source_directory, outside)
                return discovered

            try:
                with patch.object(
                    observed_module,
                    "_discover_miz",
                    side_effect=discover_then_swap,
                ):
                    report = build_observed_registry(
                        (ObservedRoot("sample", root),)
                    )
            finally:
                if source_directory.is_junction():
                    source_directory.rmdir()
                if moved.exists():
                    moved.rename(source_directory)

        self.assertEqual(report["coverage"]["unique_contents_seen"], 0)
        self.assertEqual(report["coverage"]["unique_missions"], 0)
        self.assertEqual(
            report["coverage"]["sources"][0]["errors"],
            {"discovery_file_changed_skipped": 1},
        )
        self.assertNotIn("PRIVATE_OUTSIDE_THEATRE", json.dumps(report))

    def _make_junction(self, link: Path, target: Path) -> None:
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(target),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("Windows junction creation unavailable")


if __name__ == "__main__":
    unittest.main()
