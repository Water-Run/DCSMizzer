from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.cli import main  # noqa: E402
from dcsmizzer import spec_audit as spec_audit_module  # noqa: E402
from dcsmizzer.builder import BuildSpecError  # noqa: E402
from dcsmizzer.lua import parse_lua_bytes  # noqa: E402
from dcsmizzer.lua_write import json_to_lua  # noqa: E402
from dcsmizzer.spec_audit import audit_build_spec  # noqa: E402
from tests.test_builder import fixture_spec  # noqa: E402


PAYLOAD = """
local unitPayloads = {
  name = "Fixture Plane",
  payloads = {
    [1] = {
      name = "CAP",
      pylons = {
        [1] = { CLSID = "{FIXTURE}", num = 1 },
      },
      tasks = { [1] = 11 },
    },
  },
}
return unitPayloads
"""

AIRPORTS = """
class Fixture(Airport):
    id = 7
    name = "Fixture Airbase"
    slot_version = 2

    def __init__(self):
        self.position = Point(1000, 2000)
        self.runways = [Runway(id=1, name="09-27")]
        self.parking_slots = [
            ParkingSlot(
                crossroad_idx=46,
                position=Point(1000, 2000),
                large=False,
                heli=True,
                airplanes=True,
                slot_name="01",
                length=40,
                width=20,
                height=8,
                shelter=False,
            ),
            ParkingSlot(
                crossroad_idx=47,
                position=Point(1010, 2010),
                large=False,
                heli=True,
                airplanes=True,
                slot_name="02",
                length=40,
                width=20,
                height=8,
                shelter=False,
            ),
        ]
        self.beacons = []
"""

PLANES = """
class FixturePlane(PlaneType):
    id = "Fixture Plane"
    flyable = True
    large_parking_slot = False
    height = 5
    width = 15
    length = 20
    fuel_max = 1000
    chaff = 30
    flare = 20
    property_defaults = {"Mode": 1, "Enabled": True}
    pylons = {1}
    tasks = [task.CAP]
    task_default = task.CAP

    class Pylon1:
        Fixture = (1, Weapons.Fixture_Store)
"""

WEAPONS = """
class Weapons:
    Fixture_Store = {
        "clsid": "{FIXTURE}",
        "name": "Fixture store",
        "weight": 123,
    }
"""

TASKS = """
class MainTask:
    pass

class CAP(MainTask):
    id = 11
    name = "CAP"
    internal_name = "CAP"
"""

PROJECTION = """
PARAMETERS = TransverseMercator(
    central_meridian=0,
    false_easting=0,
    false_northing=0,
    scale_factor=0.9996,
)
"""

TERRAIN = """
class FixtureTerrain(Terrain):
    def __init__(self):
        bounds = mapping.Rectangle(5000, 0, 0, 5000, self)
        super().__init__(
            "FixtureMap",
            PARAMETERS,
            bounds=bounds,
            map_view_default=None,
            utc_offset=None,
        )
"""

VEHICLES = """
class Armour:
    class FixtureVehicle(unittype.VehicleType):
        id = "Fixture Vehicle"
        name = "Fixture Vehicle"
        detection_range = 0
        threat_range = 1000
        air_weapon_dist = 1000
"""

BEACONS = """
beacons = {
  {
    display_name = _('Fixture Airbase');
    beaconId = 'airfield7_0';
    type = BEACON_TYPE_TACAN;
    callsign = 'FIX';
    position = { 1000, 50, 2000 };
    positionGeo = { latitude = 52.5, longitude = 13.4 };
  };
}
"""

CLOUDS = """
cloudsPresets =
{
    FixtureRain =
    {
        visibleInGUI = true,
        readableNameShort = _("Fixture rain"),
        precipitationPower = 0.3,
        presetAltMin = 400,
        presetAltMax = 1000,
        layers = {},
    },
}
"""


def _parking_spec() -> dict[str, object]:
    spec = fixture_spec()
    units = spec["mission"]["coalition"]["blue"]["country"][0]["plane"]["group"][0][
        "units"
    ]
    units[0].update({"parking": 46, "parking_id": "01"})
    units[1].update({"parking": 47, "parking_id": "02"})
    return spec


def _add_bombing_runway_task(
    spec: dict[str, object],
    runway_id: int,
) -> None:
    point = spec["mission"]["coalition"]["blue"]["country"][0]["plane"]["group"][0][
        "route"
    ]["points"][0]
    point["task"]["params"]["tasks"].append(
        {
            "id": "BombingRunway",
            "enabled": True,
            "number": 1,
            "auto": False,
            "params": {
                "runwayId": runway_id,
                "weaponType": 0,
            },
        }
    )


class BuildSpecEvidenceAuditTests(unittest.TestCase):
    def test_audit_rejects_spec_drift_and_never_rehashes_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            spec_path = root / "spec.json"
            original = json.dumps(fixture_spec()).encode("utf-8")
            spec_path.write_bytes(original)
            original_inventory = spec_audit_module._mission_coordinate_inventory

            def inventory_then_change_spec(*args: object, **kwargs: object) -> object:
                result = original_inventory(*args, **kwargs)
                spec_path.write_bytes(original + b" ")
                return result

            with (
                patch(
                    "dcsmizzer.spec_audit._mission_coordinate_inventory",
                    side_effect=inventory_then_change_spec,
                ),
                self.assertRaisesRegex(
                    BuildSpecError,
                    "build specification changed after it was loaded",
                ),
            ):
                audit_build_spec(
                    spec_path,
                    dcs_root=dcs_root,
                    installed_terrain="FixtureTerrain",
                    pydcs_root=pydcs_root,
                    pydcs_terrain="fixture",
                    br_root=br_root,
                )

    def test_strict_audit_and_cli_hard_fail_unacknowledged_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(fixture_spec()),
                encoding="utf-8",
            )

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
                require_acknowledged_upstreams=True,
            )
            stdout = io.StringIO()
            cli_exit = main(
                [
                    "audit-spec",
                    str(spec_path),
                    "--dcs-root",
                    str(dcs_root),
                    "--installed-terrain",
                    "FixtureTerrain",
                    "--pydcs-root",
                    str(pydcs_root),
                    "--pydcs-terrain",
                    "fixture",
                    "--br-root",
                    str(br_root),
                ],
                stdout=stdout,
            )

        failed = {
            item["id"] for item in report["checks"] if not item["passed"]
        }
        self.assertFalse(valid)
        self.assertIn("upstream.pydcs.source_lock", failed)
        self.assertIn("upstream.briefingroom.source_lock", failed)
        self.assertFalse(
            any(
                warning["code"] == "upstream_source_not_commit_bound"
                for warning in report["warnings"]
            )
        )
        self.assertTrue(
            report["filters"]["require_acknowledged_upstreams"]
        )
        self.assertEqual(cli_exit, 1)
        cli_report = json.loads(stdout.getvalue())
        self.assertTrue(
            cli_report["filters"]["require_acknowledged_upstreams"]
        )
        self.assertTrue(
            any(
                item["id"] == "upstream.pydcs.source_lock"
                and item["passed"] is False
                for item in cli_report["checks"]
            )
        )

    def test_missing_weather_constraint_source_is_an_explicit_warning(
        self,
    ) -> None:
        parsed = parse_lua_bytes(
            b"return { weather = { clouds = {} } }"
        )
        mission = parsed.document.returned
        assert mission is not None
        checks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []

        evidence = spec_audit_module._audit_weather(
            mission,
            Path("missing-dcs-root"),
            checks,
            warnings,
        )

        self.assertFalse(evidence["available"])
        self.assertEqual(evidence["unavailable_reason"], "source_missing")
        self.assertEqual(
            warnings,
            [
                {
                    "id": "$.weather.consistency",
                    "code": (
                        "current_install_weather_constraints_unavailable"
                    ),
                    "source": "MissionEditor/modules/me_weather.lua",
                    "requirement": (
                        "install the matching Mission Editor weather source "
                        "before claiming weather relationship validation"
                    ),
                }
            ],
        )

    def test_complete_payload_defensively_rejects_settings_gaps(
        self,
    ) -> None:
        parsed = parse_lua_bytes(
            b"""
            return {
                pylons = {
                    [1] = { num = 1, CLSID = "{CONFIGURED}" },
                },
            }
            """
        )
        payload = parsed.document.returned
        assert payload is not None
        checks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        match = {
            "classification": "ambiguous_observed_preset",
            "exact_composition_candidate_count": 2,
            "exact_match_count": 2,
            "configuration_unspecified_stations": [1],
            "source_binding": {
                "payload_inventory_sha256": "a" * 64,
                "files_scanned": 2,
                "candidate_enumeration_complete": True,
                "relevant_parse_failure_count": 0,
            },
        }

        with patch(
            "dcsmizzer.spec_audit.payload_match_report",
            return_value=match,
        ):
            spec_audit_module._audit_complete_payload(
                payload,
                unit_type="Configured Plane",
                evidence={
                    "current_payload_sources": [{"source": "fixture"}],
                },
                dcs_root=Path("DCS"),
                path="$.payload",
                checks=checks,
                warnings=warnings,
                cache={},
                resolutions=[],
            )

        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0]["passed"])
        self.assertEqual(
            checks[0]["actual"]["configuration_unspecified_stations"],
            [1],
        )

    def test_complete_payload_rejects_ambiguous_observed_presets(
        self,
    ) -> None:
        parsed = parse_lua_bytes(
            b"""
            return {
                pylons = {
                    [1] = { num = 1, CLSID = "{A}" },
                },
            }
            """
        )
        payload = parsed.document.returned
        assert payload is not None
        checks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        match = {
            "classification": "ambiguous_observed_preset",
            "exact_composition_candidate_count": 2,
            "exact_match_count": 2,
            "configuration_unspecified_stations": [],
            "source_binding": {
                "payload_inventory_sha256": "a" * 64,
                "files_scanned": 2,
                "candidate_enumeration_complete": True,
                "relevant_parse_failure_count": 0,
                "unit_type_invalid_payload_tables": 0,
                "unit_type_invalid_presets": 0,
            },
        }

        with patch(
            "dcsmizzer.spec_audit.payload_match_report",
            return_value=match,
        ):
            spec_audit_module._audit_complete_payload(
                payload,
                unit_type="Fixture Plane",
                evidence={
                    "current_payload_sources": [{"source": "fixture"}],
                },
                dcs_root=Path("DCS"),
                path="$.payload",
                checks=checks,
                warnings=warnings,
                cache={},
                resolutions=[],
            )

        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0]["passed"])
        self.assertEqual(
            checks[0]["actual"]["classification"],
            "ambiguous_observed_preset",
        )
        self.assertEqual(
            warnings[0]["code"],
            "whole_payload_matches_multiple_observed_presets",
        )

    def test_matching_or_unknown_payload_parse_failure_is_a_hard_check(
        self,
    ) -> None:
        parsed = parse_lua_bytes(b"return { pylons = {} }")
        payload = parsed.document.returned
        assert payload is not None
        checks: list[dict[str, object]] = []

        spec_audit_module._audit_complete_payload(
            payload,
            unit_type="Fixture Plane",
            evidence={
                "current_payload_sources": [],
                "current_payload_candidate_enumeration_complete": False,
                "current_payload_relevant_parse_failures": [
                    {
                        "source": "Unknown.lua",
                        "error_code": "executable_lua_rejected",
                        "unit_type_hint": None,
                    }
                ],
            },
            dcs_root=Path("DCS"),
            path="$.payload",
            checks=checks,
            warnings=[],
            cache={},
            resolutions=[],
        )

        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0]["passed"])
        self.assertEqual(
            checks[0]["id"],
            "$.payload.complete_composition",
        )

    def test_cross_checks_weather_tasks_pylons_service_and_parking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            spec = fixture_spec()
            units = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["units"]
            units[0].update({"parking": 46, "parking_id": "01"})
            units[1].update({"parking": 47, "parking_id": "02"})
            for unit in units:
                unit["payload"].update({"fuel": 1000, "chaff": 30, "flare": 20})
                unit["AddPropAircraft"] = {
                    "Mode": 1,
                    "Enabled": True,
                }
            spec["mission"]["coalition"]["blue"]["country"][0]["vehicle"] = {
                "group": [
                    {
                        "groupId": 2,
                        "name": "Fixture ground group",
                        "route": {
                            "points": [
                                {
                                    "type": "Turning Point",
                                    "action": "Off Road",
                                    "x": 3000,
                                    "y": 3000,
                                }
                            ]
                        },
                        "units": [
                            {
                                "unitId": 3,
                                "name": "Fixture ground unit",
                                "type": "Fixture Vehicle",
                                "x": 3000,
                                "y": 3000,
                                "heading": 0,
                            }
                        ],
                    }
                ]
            }
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
            )

            spec["mission"]["weather"]["clouds"]["base"] = 300
            invalid_path = root / "invalid.json"
            invalid_path.write_text(json.dumps(spec), encoding="utf-8")
            invalid_report, invalid = audit_build_spec(
                invalid_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )
            stdout = io.StringIO()
            cli_exit = main(
                [
                    "audit-spec",
                    str(invalid_path),
                    "--dcs-root",
                    str(dcs_root),
                    "--installed-terrain",
                    "FixtureTerrain",
                    "--pydcs-root",
                    str(pydcs_root),
                    "--pydcs-terrain",
                    "fixture",
                ],
                stdout=stdout,
            )

        self.assertTrue(valid)
        self.assertTrue(report["validation"]["evidence_consistent"])
        self.assertFalse(report["validation"]["review_warnings_clear"])
        self.assertEqual(
            {
                warning["id"]
                for warning in report["warnings"]
                if warning["code"] == "upstream_source_not_commit_bound"
            },
            {
                "upstream.pydcs.provenance",
                "upstream.briefingroom.provenance",
            },
        )
        self.assertIsNotNone(
            report["sources"]["briefingroom_secondary_terrain_evidence"]
        )
        self.assertFalse(invalid)
        self.assertEqual(cli_exit, 1)
        self.assertFalse(
            json.loads(stdout.getvalue())["validation"]["evidence_consistent"]
        )
        self.assertTrue(
            any(
                item["id"] == "unit_type.vehicle.Fixture Vehicle" and item["passed"]
                for item in report["checks"]
            )
        )
        self.assertTrue(
            any(
                item["id"].endswith(".payload.fuel") and item["passed"]
                for item in report["checks"]
            )
        )
        self.assertTrue(
            any(
                item["id"].endswith(".AddPropAircraft.Mode") and item["passed"]
                for item in report["checks"]
            )
        )
        failed_ids = {
            item["id"] for item in invalid_report["checks"] if not item["passed"]
        }
        self.assertEqual(failed_ids, {"$.weather.clouds.base"})

    def test_noninstalled_terrain_uses_upstream_parking_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            spec = fixture_spec()
            units = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["units"]
            units[0].update({"parking": 46, "parking_id": "01"})
            units[1].update({"parking": 47, "parking_id": "02"})
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="FixtureMap",
            )

        self.assertTrue(valid)
        self.assertFalse(report["validation"]["review_warnings_clear"])
        self.assertEqual(
            {item["code"] for item in report["warnings"]},
            {
                "current_install_weather_constraints_unavailable",
                "installed_terrain_crosscheck_not_run",
                "upstream_source_not_commit_bound",
            },
        )
        self.assertTrue(
            any(
                item["id"] == "$.theatre" and item["passed"]
                for item in report["checks"]
            )
        )

    def test_installed_airbase_callsign_can_crosscheck_upstream_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            beacon_path = (
                dcs_root / "Mods" / "terrains" / "FixtureTerrain" / "beacons.lua"
            )
            beacon_path.write_text(
                BEACONS.replace(
                    "display_name = _('Fixture Airbase');",
                    "display_name = _('ICAO_Fixture_Internal');",
                ).replace(
                    "callsign = 'FIX';",
                    "callsign = 'Fixture Airbase';",
                ),
                encoding="utf-8",
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(_parking_spec()),
                encoding="utf-8",
            )

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertTrue(valid)
        crosscheck = next(
            item
            for item in report["checks"]
            if item["id"] == "airdrome.7.name_crosscheck"
        )
        self.assertTrue(crosscheck["passed"])
        self.assertEqual(
            crosscheck["expected"],
            {
                "names": ["ICAO_Fixture_Internal"],
                "callsigns": ["Fixture Airbase"],
            },
        )

    def test_briefingroom_fills_terrain_and_parking_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            (pydcs_root / "dcs" / "planes.py").write_text(
                PLANES.replace("length = 20", "length = 50")
                .replace("width = 15", "width = 50")
                .replace("height = 5", "height = 50"),
                encoding="utf-8",
            )
            spec = fixture_spec()
            spec["mission"]["theatre"] = "RemoteMap"
            units = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["units"]
            units[0].update(
                {
                    "parking": 81,
                    "parking_id": "A01",
                    "x": 500,
                    "y": 600,
                }
            )
            units[1].update(
                {
                    "parking": 82,
                    "parking_id": "A02",
                    "x": 510,
                    "y": 610,
                }
            )
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain=None,
                br_root=br_root,
            )

        self.assertTrue(valid)
        terrain = report["sources"]["terrain_evidence"]
        self.assertEqual(terrain["theatre"], "RemoteMap")
        self.assertEqual(terrain["parking_provider"], "briefingroom")
        self.assertTrue(
            terrain["authority"].startswith(
                "unversioned_snapshot_upstream_exported_terrain"
            )
        )
        self.assertTrue(
            any(
                item["id"] == "airdrome.7.upstream" and item["passed"]
                for item in report["checks"]
            )
        )
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertIn(
            "rectangular_bounds_evidence_unavailable",
            warning_codes,
        )
        self.assertIn(
            "parking_resolver_semantics_unavailable",
            warning_codes,
        )

    def test_rejects_obvious_bounds_and_oversized_parking_envelope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            planes = pydcs_root / "dcs" / "planes.py"
            planes.write_text(
                PLANES.replace("length = 20", "length = 50"),
                encoding="utf-8",
            )
            spec = fixture_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["route"]["points"].append(
                {
                    "type": "Turning Point",
                    "action": "Turning Point",
                    "x": 7001,
                    "y": 2000,
                    "ETA": 5000,
                    "task": {
                        "id": "ComboTask",
                        "params": {"tasks": []},
                    },
                }
            )
            units = group["units"]
            units[0].update({"parking": 46, "parking_id": "01"})
            units[1].update({"parking": 47, "parking_id": "02"})
            spec_path = root / "private" / "oversized-spec.json"
            spec_path.parent.mkdir()
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertFalse(valid)
        failed = {item["id"]: item for item in report["checks"] if not item["passed"]}
        self.assertTrue(
            any(identifier.endswith(".declared_bounds") for identifier in failed)
        )
        self.assertEqual(
            sum(identifier.endswith(".parking.resolver_v2") for identifier in failed),
            2,
        )
        bounds_failure = next(
            item
            for identifier, item in failed.items()
            if identifier.endswith(".declared_bounds")
        )
        self.assertEqual(
            bounds_failure["actual"]["surface_validity"],
            "not_evaluated",
        )
        self.assertEqual(report["input_spec"], "oversized-spec.json")
        self.assertEqual(report["input_spec_path_scope"], "basename_only")
        self.assertEqual(len(report["input_spec_sha256"]), 64)
        self.assertNotIn(str(root), json.dumps(report))

    def test_reports_br_project_target_and_installed_version_conflict(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            version_source = br_root / "src" / "BriefingRoom" / "BriefingRoom.cs"
            version_source.parent.mkdir(parents=True)
            version_source.write_text(
                'const string TARGETED_DCS_WORLD_VERSION = "2.9.28.26283";',
                encoding="utf-8",
            )
            spec = fixture_spec()
            units = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]["units"]
            units[0].update({"parking": 46, "parking_id": "01"})
            units[1].update({"parking": 47, "parking_id": "02"})
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with patch(
                "dcsmizzer.spec_audit._installed_product_version",
                return_value="2.9.28.26385",
            ):
                report, valid = audit_build_spec(
                    spec_path,
                    dcs_root=dcs_root,
                    installed_terrain=None,
                    pydcs_root=pydcs_root,
                    pydcs_terrain="fixture",
                    br_root=br_root,
                )

        self.assertTrue(valid)
        versions = report["sources"]["terrain_version_compatibility"]
        self.assertEqual(versions["status"], "different_versions")
        self.assertFalse(versions["version_matched_claim_allowed"])
        self.assertTrue(
            any(
                warning["code"] == "briefingroom_target_differs_from_installed_dcs"
                for warning in report["warnings"]
            )
        )

    def test_inconsistent_source_bounds_suppress_all_inventory_hard_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            terrain_source = pydcs_root / "dcs" / "terrain" / "fixture" / "fixture.py"
            terrain_source.write_text(
                TERRAIN.replace(
                    "mapping.Rectangle(5000, 0, 0, 5000, self)",
                    "mapping.Rectangle(100, 0, 0, 100, self)",
                ),
                encoding="utf-8",
            )
            spec = _parking_spec()
            mission = spec["mission"]
            mission["coalition"]["blue"]["bullseye"] = {
                "x": 9000,
                "y": 9000,
            }
            mission["triggers"]["zones"] = [
                {
                    "zoneId": 1,
                    "name": "Fixture zone",
                    "x": 9100,
                    "y": 9100,
                    "radius": 1000,
                    "type": 0,
                }
            ]
            point = mission["coalition"]["blue"]["country"][0]["plane"]["group"][0][
                "route"
            ]["points"][0]
            point["task"]["params"]["tasks"].append(
                {
                    "id": "EngageTargetsInZone",
                    "number": 1,
                    "auto": False,
                    "enabled": True,
                    "params": {
                        "targetTypes": ["Planes"],
                        "priority": 0,
                        "x": 9200,
                        "y": 9200,
                        "zoneRadius": 1000,
                    },
                }
            )
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertTrue(valid)
        warning = next(
            item
            for item in report["warnings"]
            if item["code"] == "rectangular_bounds_hard_check_suppressed"
        )
        self.assertEqual(
            warning["source_internal_consistency"]["status"],
            "inconsistent",
        )
        kinds = {item["kind"] for item in warning["coordinate_diagnostics"]}
        self.assertTrue(
            {
                "group_route_point",
                "unit_position",
                "coalition_bullseye",
                "trigger_zone_center",
                "task_EngageTargetsInZone",
            }.issubset(kinds)
        )
        self.assertFalse(
            any(
                item["id"].endswith(".declared_bounds") and not item["passed"]
                for item in report["checks"]
            )
        )

    def test_coordinate_inventory_includes_gci_but_not_runway_or_metadata(
        self,
    ) -> None:
        mission = json_to_lua(
            {
                "coalition": {},
                "triggers": {"zones": []},
                "fixture_tasks": {
                    "gci": {
                        "id": "ActivateGCI",
                        "params": {
                            "unitId": 3,
                            "channel": 5,
                            "radius": 9_000_000,
                            "x": 7001,
                            "y": 2000,
                        },
                    },
                    "gci_without_coordinates": {
                        "id": "ActivateGCI",
                        "params": {
                            "unitId": 4,
                            "channel": 6,
                            "radius": 8_000_000,
                        },
                    },
                    "runway_with_incidental_coordinates": {
                        "id": "BombingRunway",
                        "params": {
                            "runwayId": 7,
                            "weaponType": 0,
                            "x": 99_000,
                            "y": 98_000,
                        },
                    },
                },
            }
        )

        coordinates = spec_audit_module._mission_coordinate_inventory(
            mission,
            [],
        )

        self.assertEqual(
            coordinates,
            [
                {
                    "path": "$.fixture_tasks.gci.params",
                    "kind": "task_ActivateGCI",
                    "x": 7001,
                    "y": 2000,
                }
            ],
        )
        checks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        spec_audit_module._audit_declared_bounds(
            coordinates,
            bounds={"top": 5000, "bottom": 0, "left": 0, "right": 5000},
            consistency={
                "status": "consistent",
                "hard_coordinate_rejection_allowed": True,
                "tolerance_m": 1000,
            },
            selected_authority="fixture",
            checks=checks,
            warnings=warnings,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(checks), 1)
        self.assertEqual(
            checks[0]["id"],
            "$.fixture_tasks.gci.params.declared_bounds",
        )
        self.assertFalse(checks[0]["passed"])
        self.assertEqual(
            checks[0]["actual"],
            {
                "x": 7001,
                "y": 2000,
                "strictly_within_declared_rectangle": False,
                "surface_validity": "not_evaluated",
            },
        )

    def test_pydcs_parking_resolver_v1_uses_classification_not_dimensions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            airports = pydcs_root / "dcs" / "terrain" / "fixture" / "airports.py"
            airports.write_text(
                AIRPORTS.replace("    slot_version = 2\n", "")
                .replace("length=40", "length=1")
                .replace("width=20", "width=1")
                .replace("height=8", "height=1"),
                encoding="utf-8",
            )
            spec = _parking_spec()
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertTrue(valid)
        resolver_checks = [
            item
            for item in report["checks"]
            if item["id"].endswith(".parking.resolver_v1")
        ]
        self.assertEqual(len(resolver_checks), 2)
        self.assertTrue(all(item["passed"] for item in resolver_checks))
        self.assertTrue(
            all(
                item["actual"]["dimensions_consulted"] is False
                for item in resolver_checks
            )
        )

    def test_pydcs_parking_resolver_v2_is_strict_and_ignores_large_flag(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            planes = pydcs_root / "dcs" / "planes.py"
            planes.write_text(
                PLANES.replace(
                    "large_parking_slot = False",
                    "large_parking_slot = True",
                ),
                encoding="utf-8",
            )
            spec = _parking_spec()
            fits_path = root / "fits.json"
            fits_path.write_text(json.dumps(spec), encoding="utf-8")
            fits_report, fits = audit_build_spec(
                fits_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

            planes.write_text(
                PLANES.replace("width = 15", "width = 20"),
                encoding="utf-8",
            )
            equal_path = root / "equal.json"
            equal_path.write_text(json.dumps(spec), encoding="utf-8")
            equal_report, equal = audit_build_spec(
                equal_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertTrue(fits)
        self.assertTrue(
            all(
                item["actual"]["large_classification_consulted"] is False
                for item in fits_report["checks"]
                if item["id"].endswith(".parking.resolver_v2")
            )
        )
        self.assertFalse(equal)
        failed = [
            item
            for item in equal_report["checks"]
            if item["id"].endswith(".parking.resolver_v2") and not item["passed"]
        ]
        self.assertEqual(len(failed), 2)
        self.assertEqual(
            failed[0]["actual"]["axis_aligned_declared_dimensions"]["width"],
            {"aircraft_m": 20.0, "parking_m": 20.0},
        )

    def test_per_airdrome_resolution_falls_back_to_br_only_airport(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            source = br_root / "DatabaseJSON" / "TheatersAirbases.json"
            airbases = json.loads(source.read_text(encoding="utf-8"))
            fallback = json.loads(json.dumps(airbases[1]))
            fallback.update(
                {
                    "ID": 37,
                    "displayName": "BR-only Airbase",
                    "typeName": "BR-only Airbase",
                }
            )
            airbases.append(fallback)
            source.write_text(json.dumps(airbases), encoding="utf-8")
            spec = _parking_spec()
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["route"]["points"][0]["airdromeId"] = 37
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
            )

        self.assertTrue(valid)
        resolutions = report["sources"]["parking_source_resolutions"]
        self.assertEqual(len(resolutions), 2)
        self.assertTrue(
            all(
                item["selected_parking_provider"] == "briefingroom"
                and item["secondary_fallback_used"]
                for item in resolutions
            )
        )
        self.assertTrue(
            any(
                warning["code"] == "parking_airdrome_secondary_source_fallback"
                for warning in report["warnings"]
            )
        )

    def test_cross_source_smaller_br_dimensions_do_not_override_pydcs_v2(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            planes = pydcs_root / "dcs" / "planes.py"
            planes.write_text(
                PLANES.replace("width = 15", "width = 40.4")
                .replace("length = 20", "length = 30")
                .replace("height = 5", "height = 10"),
                encoding="utf-8",
            )
            airports = pydcs_root / "dcs" / "terrain" / "fixture" / "airports.py"
            airports.write_text(
                AIRPORTS.replace("length=40", "length=41")
                .replace("width=20", "width=41")
                .replace("height=8", "height=18"),
                encoding="utf-8",
            )
            br_source = br_root / "DatabaseJSON" / "TheatersAirbases.json"
            airbases = json.loads(br_source.read_text(encoding="utf-8"))
            for stand in airbases[1]["stands"]:
                stand["params"].update({"LENGTH": "36", "WIDTH": "36", "HEIGHT": "15"})
            br_source.write_text(json.dumps(airbases), encoding="utf-8")
            spec = _parking_spec()
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
            )

        self.assertTrue(valid)
        self.assertTrue(
            all(
                item["passed"]
                for item in report["checks"]
                if item["id"].endswith(".parking.resolver_v2")
            )
        )
        conflicts = [
            warning
            for warning in report["warnings"]
            if warning["code"] == "parking_cross_source_semantic_conflict"
        ]
        self.assertEqual(len(conflicts), 2)
        self.assertIn("dimensions", conflicts[0]["differences"])
        self.assertFalse(conflicts[0]["fallback_allowed"])

    def test_full_identity_graph_rejects_hidden_duplicate_and_missing_override(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            duplicate = pydcs_root / "dcs" / "terrain" / "duplicate"
            duplicate.mkdir(parents=True)
            (duplicate / "airports.py").write_text(
                AIRPORTS,
                encoding="utf-8",
            )
            (duplicate / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (duplicate / "duplicate.py").write_text(
                TERRAIN.replace("FixtureTerrain", "DuplicateTerrain"),
                encoding="utf-8",
            )
            spec = _parking_spec()
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            duplicate_report, duplicate_valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
            )
            missing_report, missing_valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="definitely-missing",
                br_root=br_root,
            )

        self.assertFalse(duplicate_valid)
        self.assertFalse(missing_valid)
        self.assertTrue(
            any(
                item["id"] == "terrain.evidence" and not item["passed"]
                for item in duplicate_report["checks"]
            )
        )
        self.assertTrue(
            any(
                item["id"] == "terrain.pydcs_override" and not item["passed"]
                for item in missing_report["checks"]
            )
        )

    def test_full_identity_graph_fails_closed_on_unresolved_package(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            broken = pydcs_root / "dcs" / "terrain" / "broken"
            broken.mkdir()
            (broken / "airports.py").write_text(
                "this is not valid Python !!!",
                encoding="utf-8",
            )
            (broken / "projection.py").write_text(
                PROJECTION,
                encoding="utf-8",
            )
            (broken / "broken.py").write_text(
                TERRAIN,
                encoding="utf-8",
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(_parking_spec()),
                encoding="utf-8",
            )

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertFalse(valid)
        self.assertEqual(
            report["sources"]["terrain_source_coverage"]["pydcs"][
                "terrain_packages_unresolved"
            ],
            ["broken"],
        )
        terrain_check = next(
            item for item in report["checks"] if item["id"] == "terrain.evidence"
        )
        self.assertFalse(terrain_check["passed"])
        self.assertFalse(terrain_check["actual"]["identity_graph_parse_complete"])

    def test_bombing_runway_requires_real_airport_with_runway(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            self._write_sources(dcs_root, pydcs_root)
            valid_spec = _parking_spec()
            _add_bombing_runway_task(valid_spec, 7)
            valid_path = root / "valid.json"
            valid_path.write_text(json.dumps(valid_spec), encoding="utf-8")
            valid_report, valid = audit_build_spec(
                valid_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

            invalid_spec = _parking_spec()
            _add_bombing_runway_task(invalid_spec, 999999)
            invalid_path = root / "invalid.json"
            invalid_path.write_text(
                json.dumps(invalid_spec),
                encoding="utf-8",
            )
            invalid_report, invalid = audit_build_spec(
                invalid_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
            )

        self.assertTrue(valid)
        self.assertEqual(
            valid_report["sources"]["bombing_runway_source_resolutions"][0]["runwayId"],
            7,
        )
        self.assertFalse(invalid)
        self.assertTrue(
            any(
                item["id"].endswith(".params.runwayId") and not item["passed"]
                for item in invalid_report["checks"]
            )
        )

    def test_bombing_runway_can_resolve_br_only_airport(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            source = br_root / "DatabaseJSON" / "TheatersAirbases.json"
            airbases = json.loads(source.read_text(encoding="utf-8"))
            airbases[0]["runways"] = [
                {
                    "Name": 9,
                    "course": 1.57,
                    "id": 1,
                    "length": 2500,
                    "position": {"x": 500, "y": 25, "z": 600},
                    "width": 45,
                }
            ]
            source.write_text(json.dumps(airbases), encoding="utf-8")
            spec = _parking_spec()
            spec["mission"]["theatre"] = "RemoteMap"
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["units"][0].update(
                {"parking": 81, "parking_id": "A01", "x": 500, "y": 600}
            )
            group["units"][1].update(
                {"parking": 82, "parking_id": "A02", "x": 510, "y": 610}
            )
            _add_bombing_runway_task(spec, 7)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain=None,
                br_root=br_root,
            )

        self.assertTrue(valid)
        resolution = report["sources"]["bombing_runway_source_resolutions"][0]
        self.assertEqual(resolution["selected_provider"], "briefingroom")
        self.assertEqual(resolution["runwayId"], 7)

    def test_bombing_runway_rejects_malformed_br_runway_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            self._write_sources(dcs_root, pydcs_root)
            self._write_br_sources(br_root)
            source = br_root / "DatabaseJSON" / "TheatersAirbases.json"
            airbases = json.loads(source.read_text(encoding="utf-8"))
            airbases[0]["runways"] = [{}]
            source.write_text(json.dumps(airbases), encoding="utf-8")
            spec = _parking_spec()
            spec["mission"]["theatre"] = "RemoteMap"
            group = spec["mission"]["coalition"]["blue"]["country"][0]["plane"][
                "group"
            ][0]
            group["units"][0].update(
                {"parking": 81, "parking_id": "A01", "x": 500, "y": 600}
            )
            group["units"][1].update(
                {"parking": 82, "parking_id": "A02", "x": 510, "y": 610}
            )
            _add_bombing_runway_task(spec, 7)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            report, valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain=None,
                pydcs_root=pydcs_root,
                pydcs_terrain=None,
                br_root=br_root,
            )

        self.assertFalse(valid)
        runway_check = next(
            item for item in report["checks"] if item["id"].endswith(".params.runwayId")
        )
        self.assertFalse(runway_check["passed"])
        self.assertEqual(
            report["sources"]["bombing_runway_source_resolutions"],
            [],
        )

    @staticmethod
    def _write_sources(dcs_root: Path, pydcs_root: Path) -> None:
        database = dcs_root / "Scripts" / "Database"
        database.mkdir(parents=True)
        (database / "db_countries.lua").write_text(
            """
            country = { next_index = 0 }
            country:add('FIRST', _('First'), 'First', 'FST')
            country:next()
            country:add(
              'Fixture Country',
              _('Fixture Country'),
              'Fixture Country',
              'FIX'
            )
            """,
            encoding="utf-8",
        )
        effects = dcs_root / "Config" / "Effects"
        effects.mkdir(parents=True)
        (effects / "clouds.lua").write_text(CLOUDS, encoding="utf-8")
        terrain = dcs_root / "Mods" / "terrains" / "FixtureTerrain"
        terrain.mkdir(parents=True)
        (terrain / "beacons.lua").write_text(BEACONS, encoding="utf-8")
        module = dcs_root / "Mods" / "aircraft" / "Fixture"
        payloads = module / "UnitPayloads"
        payloads.mkdir(parents=True)
        (module / "entry.lua").write_text(
            """
            local self_ID = "Fixture Plugin"
            declare_plugin(self_ID, {})
            make_flyable("Fixture Plane", "Cockpit")
            """,
            encoding="utf-8",
        )
        (module / "Fixture.lua").write_text(
            'declare_service_life("Fixture Plane", "Fixture Country", 1980, 2000)\n',
            encoding="utf-8",
        )
        (payloads / "Fixture.lua").write_text(PAYLOAD, encoding="utf-8")

        pydcs_terrain = pydcs_root / "dcs" / "terrain" / "fixture"
        pydcs_terrain.mkdir(parents=True)
        (pydcs_terrain / "airports.py").write_text(
            AIRPORTS,
            encoding="utf-8",
        )
        (pydcs_terrain / "projection.py").write_text(
            PROJECTION,
            encoding="utf-8",
        )
        (pydcs_terrain / "fixture.py").write_text(
            TERRAIN,
            encoding="utf-8",
        )
        (pydcs_root / "dcs" / "planes.py").write_text(
            PLANES,
            encoding="utf-8",
        )
        (pydcs_root / "dcs" / "weapons_data.py").write_text(
            WEAPONS,
            encoding="utf-8",
        )
        (pydcs_root / "dcs" / "task.py").write_text(
            TASKS,
            encoding="utf-8",
        )
        (pydcs_root / "dcs" / "vehicles.py").write_text(
            VEHICLES,
            encoding="utf-8",
        )

    @staticmethod
    def _write_br_sources(root: Path) -> None:
        theatres = root / "Database" / "Theaters"
        bounds = root / "DatabaseJSON" / "TheaterTerrainBounds"
        theatres.mkdir(parents=True)
        bounds.mkdir(parents=True)
        (theatres / "Remote.ini").write_text(
            "[GUI]\n"
            "DisplayName=Remote map\n\n"
            "[Theater]\n"
            "DCSID=RemoteMap\n"
            "DefaultMapCenter=0,0\n",
            encoding="utf-8",
        )
        (theatres / "Fixture.ini").write_text(
            "[GUI]\n"
            "DisplayName=Fixture map\n\n"
            "[Theater]\n"
            "DCSID=FixtureMap\n"
            "DefaultMapCenter=0,0\n",
            encoding="utf-8",
        )
        (bounds / "RemoteMap.json").write_text(
            json.dumps(
                {
                    "landMasses": [[[0, 0], [1000, 0], [1000, 1000]]],
                    "waters": [],
                }
            ),
            encoding="utf-8",
        )
        (bounds / "FixtureMap.json").write_text(
            json.dumps(
                {
                    "landMasses": [[[0, 0], [5000, 0], [5000, 5000]]],
                    "waters": [],
                }
            ),
            encoding="utf-8",
        )
        airbase = {
            "theatre": "RemoteMap",
            "ID": 7,
            "displayName": "Fixture Airbase",
            "typeName": "Fixture Airbase",
            "code": "RMT",
            "pos": {
                "DCS": {"x": 500, "z": 600},
                "World": {"alt": 25, "lat": 10, "lon": 20},
            },
            "runways": [],
            "stands": [
                {
                    "crossroad_index": index,
                    "name": name,
                    "params": {
                        "FOR_AIRPLANES": "1",
                        "FOR_HELICOPTERS": "1",
                        "HEIGHT": "",
                        "LENGTH": "40",
                        "SHELTER": "0",
                        "WIDTH": "20",
                    },
                    "x": x,
                    "y": y,
                }
                for index, name, x, y in (
                    (81, "A01", 500, 600),
                    (82, "A02", 510, 610),
                )
            ],
            "parking": [],
            "airdromeData": {"ATC": [], "TACAN": [], "ILS": []},
        }
        fixture_airbase = json.loads(json.dumps(airbase))
        fixture_airbase.update(
            {
                "theatre": "FixtureMap",
                "displayName": "Fixture Airbase",
                "typeName": "Fixture Airbase",
                "code": "FIX",
                "pos": {
                    "DCS": {"x": 1000, "z": 2000},
                    "World": {"alt": 50, "lat": 52.5, "lon": 13.4},
                },
            }
        )
        fixture_airbase["stands"] = [
            {
                "crossroad_index": index,
                "name": name,
                "params": {
                    "FOR_AIRPLANES": "1",
                    "FOR_HELICOPTERS": "1",
                    "HEIGHT": "8",
                    "LENGTH": "40",
                    "SHELTER": "0",
                    "WIDTH": "20",
                },
                "x": x,
                "y": y,
            }
            for index, name, x, y in (
                (46, "01", 1000, 2000),
                (47, "02", 1010, 2010),
            )
        ]
        (root / "DatabaseJSON" / "TheatersAirbases.json").write_text(
            json.dumps([airbase, fixture_airbase]),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
