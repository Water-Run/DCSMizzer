from __future__ import annotations

from contextlib import ExitStack
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer import spec_audit as spec_audit_module  # noqa: E402
from dcsmizzer.builder import BuildSpecError  # noqa: E402
from dcsmizzer.gci import GCI_STATION_TYPE  # noqa: E402
from dcsmizzer.spec_audit import audit_build_spec  # noqa: E402
from tests import test_spec_audit as audit_fixtures  # noqa: E402
from tests import test_weather as weather_fixtures  # noqa: E402


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _gci_report() -> dict[str, object]:
    return {
        "coverage": {
            "matching_station_declarations": 1,
            "gci_training_missions_observed": 1,
        },
        "station_declarations": [
            {
                "countries": ["Fixture Country"],
                "source": "Mods/tech/Fixture/GCI.lua",
                "source_sha256": "a" * 64,
            }
        ],
    }


def _full_branch_spec() -> dict[str, object]:
    spec = audit_fixtures._parking_spec()
    country = spec["mission"]["coalition"]["blue"]["country"][0]
    country["vehicle"] = {
        "group": [
            {
                "groupId": 2,
                "name": "Fixture GCI",
                "route": {
                    "points": [
                        {
                            "x": 3000,
                            "y": 3000,
                            "type": "Turning Point",
                            "action": "Off Road",
                            "task": {
                                "id": "ComboTask",
                                "params": {
                                    "tasks": [
                                        {
                                            "number": 1,
                                            "auto": True,
                                            "id": "WrappedAction",
                                            "enabled": True,
                                            "params": {
                                                "action": {
                                                    "id": "ActivateGCI",
                                                    "params": {
                                                        "unitId": 3,
                                                        "channel": 5,
                                                        "radius": 200000,
                                                        "x": 50000,
                                                        "y": 60000,
                                                    },
                                                }
                                            },
                                        }
                                    ]
                                },
                            },
                        }
                    ]
                },
                "units": [
                    {
                        "unitId": 3,
                        "name": "Fixture GCI station",
                        "type": GCI_STATION_TYPE,
                        "x": 3000,
                        "y": 3000,
                        "heading": 0,
                    }
                ],
            },
            {
                "groupId": 3,
                "name": "Fixture GCI radar",
                "route": {
                    "points": [
                        {
                            "x": 100000,
                            "y": 3000,
                            "type": "Turning Point",
                            "action": "Off Road",
                        }
                    ]
                },
                "units": [
                    {
                        "unitId": 4,
                        "name": "Fixture EWR",
                        "type": "1L13 EWR",
                        "x": 100000,
                        "y": 3000,
                        "heading": 0,
                    }
                ],
            },
        ]
    }
    audit_fixtures._add_bombing_runway_task(spec, 7)
    audit_fixtures._add_bombing_runway_task(spec, 7)
    return spec


def _resource_spec(source: str) -> dict[str, object]:
    spec = audit_fixtures._parking_spec()
    spec["mapResource"] = {"briefing": "briefing.bin"}
    spec["resources"] = [
        {
            "member": "briefing.bin",
            "source": source,
        }
    ]
    spec["expect"]["minimum"]["resource_mappings"] = 1
    return spec


class _CountingAuditQueryProvider(spec_audit_module._AuditQueryProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _query_canonical(
        self,
        kind: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((kind, params))
        return {}


class _FalsyAuditQueryProvider(_CountingAuditQueryProvider):
    def __bool__(self) -> bool:
        return False


class AuditQueryProviderTests(unittest.TestCase):
    def test_default_and_explicit_live_provider_reports_are_byte_identical(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            audit_fixtures.BuildSpecEvidenceAuditTests._write_sources(
                dcs_root,
                pydcs_root,
            )
            audit_fixtures.BuildSpecEvidenceAuditTests._write_br_sources(
                br_root
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(audit_fixtures._parking_spec()),
                encoding="utf-8",
            )

            default_report, default_valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
            )
            explicit_report, explicit_valid = audit_build_spec(
                spec_path,
                dcs_root=dcs_root,
                installed_terrain="FixtureTerrain",
                pydcs_root=pydcs_root,
                pydcs_terrain="fixture",
                br_root=br_root,
                _query_provider=spec_audit_module._LiveAuditQueryProvider(
                    dcs_root=dcs_root,
                    pydcs_root=pydcs_root,
                    br_root=br_root,
                ),
            )

        self.assertEqual(default_valid, explicit_valid)
        self.assertEqual(
            _canonical_bytes(default_report),
            _canonical_bytes(explicit_report),
        )

    def test_full_ordered_transcript_replays_without_live_source_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            br_root = root / "briefing-room"
            audit_fixtures.BuildSpecEvidenceAuditTests._write_sources(
                dcs_root,
                pydcs_root,
            )
            audit_fixtures.BuildSpecEvidenceAuditTests._write_br_sources(
                br_root
            )
            weather_source = (
                dcs_root
                / "MissionEditor"
                / "modules"
                / "me_weather.lua"
            )
            weather_source.parent.mkdir(parents=True)
            weather_source.write_text(
                weather_fixtures.ME_WEATHER,
                encoding="utf-8",
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(_full_branch_spec()),
                encoding="utf-8",
            )
            recorder = spec_audit_module._RecordingAuditQueryProvider(
                spec_audit_module._LiveAuditQueryProvider(
                    dcs_root=dcs_root,
                    pydcs_root=pydcs_root,
                    br_root=br_root,
                )
            )
            with patch.object(
                spec_audit_module,
                "gci_evidence_report",
                return_value=_gci_report(),
            ):
                live_report, live_valid = audit_build_spec(
                    spec_path,
                    dcs_root=dcs_root,
                    installed_terrain="FixtureTerrain",
                    pydcs_root=pydcs_root,
                    pydcs_terrain="fixture",
                    br_root=br_root,
                    _query_provider=recorder,
                )
            transcript = recorder.transcript()

            expected_kinds = [
                "countries",
                "gci_evidence",
                "weather_constraints_available",
                "weather_constraints",
                "cloud_preset",
                "pydcs_unit",
                "dcs_payload",
                "dcs_module_index",
                "pydcs_unit",
                "pydcs_terrains",
                "br_terrains",
                "combined_terrains",
                "installed_product_version",
                "payload_match",
                "pydcs_airport",
                "br_airbase",
                "dcs_airbase",
                "pydcs_airport",
                "br_airbase",
                "dcs_airbase",
                "pydcs_airport",
                "br_airbase",
                "dcs_airbase",
            ]
            self.assertEqual(
                [entry["kind"] for entry in transcript],
                expected_kinds,
            )
            payload_query = transcript[13]["params"]
            self.assertEqual(payload_query["unit_type"], "Fixture Plane")
            self.assertEqual(
                len(payload_query["configured_composition_sha256"]),
                64,
            )
            self.assertEqual(
                payload_query["pylons"],
                [{"num": 1, "CLSID": "{FIXTURE}"}],
            )
            self.assertEqual(
                [
                    entry["params"]
                    for entry in transcript
                    if entry["kind"] == "pydcs_airport"
                ],
                [
                    {"airdrome_id": 7, "terrain": "fixture"},
                    {"airdrome_id": 7, "terrain": "fixture"},
                    {"airdrome_id": 7, "terrain": "fixture"},
                ],
            )

            replay = spec_audit_module._ReplayAuditQueryProvider(transcript)
            forbidden_names = (
                "countries_report",
                "gci_evidence_report",
                "weather_constraints_report",
                "cloud_preset_report",
                "pydcs_unit_report",
                "payload_report",
                "module_index_report",
                "pydcs_terrain_report",
                "br_terrain_report",
                "combined_terrain_report",
                "payload_match_report",
                "pydcs_airport_report",
                "br_airbase_report",
                "airbase_beacon_report",
                "_weather_constraints_available",
                "_installed_product_version",
                "_windows_product_version",
            )
            forbidden: dict[str, Mock] = {}
            with ExitStack() as stack:
                for name in forbidden_names:
                    collector = Mock(
                        side_effect=AssertionError(
                            f"live source collector called during replay: {name}"
                        )
                    )
                    forbidden[name] = stack.enter_context(
                        patch.object(spec_audit_module, name, collector)
                    )
                replay_report, replay_valid = audit_build_spec(
                    spec_path,
                    dcs_root=root / "missing-dcs",
                    installed_terrain="FixtureTerrain",
                    pydcs_root=root / "missing-pydcs",
                    pydcs_terrain="fixture",
                    br_root=root / "missing-briefing-room",
                    _query_provider=replay,
                )

            replay.require_consumed()
            self.assertEqual(replay.remaining, 0)
            self.assertEqual(live_valid, replay_valid)
            self.assertEqual(
                _canonical_bytes(live_report),
                _canonical_bytes(replay_report),
            )
            for collector in forbidden.values():
                collector.assert_not_called()

    def test_replay_uses_sealed_resources_for_relative_and_absolute_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dcs_root = root / "DCS"
            pydcs_root = root / "pydcs"
            audit_fixtures.BuildSpecEvidenceAuditTests._write_sources(
                dcs_root,
                pydcs_root,
            )
            sealed_resource = root / "objects" / "resource.bin"
            sealed_resource.parent.mkdir()
            sealed_resource.write_bytes(b"sealed resource content")

            source_variants = {
                "relative": "missing/original.bin",
                "absolute": str(root / "missing-absolute" / "original.bin"),
            }
            for label, source in source_variants.items():
                with self.subTest(source_kind=label):
                    spec_path = root / f"spec-{label}.json"
                    spec_path.write_text(
                        json.dumps(_resource_spec(source)),
                        encoding="utf-8",
                    )
                    overrides = {"briefing.bin": sealed_resource}

                    with self.assertRaisesRegex(
                        BuildSpecError,
                        "source does not exist or is not a safe regular file",
                    ):
                        audit_build_spec(
                            spec_path,
                            dcs_root=dcs_root,
                            installed_terrain=None,
                            pydcs_root=pydcs_root,
                            pydcs_terrain="fixture",
                        )

                    recorder = spec_audit_module._RecordingAuditQueryProvider(
                        spec_audit_module._LiveAuditQueryProvider(
                            dcs_root=dcs_root,
                            pydcs_root=pydcs_root,
                        )
                    )
                    live_report, live_valid = audit_build_spec(
                        spec_path,
                        dcs_root=dcs_root,
                        installed_terrain=None,
                        pydcs_root=pydcs_root,
                        pydcs_terrain="fixture",
                        _query_provider=recorder,
                        _resource_overrides=overrides,
                    )

                    replay = spec_audit_module._ReplayAuditQueryProvider(
                        recorder.transcript()
                    )
                    replay_report, replay_valid = audit_build_spec(
                        spec_path,
                        dcs_root=root / "missing-dcs",
                        installed_terrain=None,
                        pydcs_root=root / "missing-pydcs",
                        pydcs_terrain="fixture",
                        _query_provider=replay,
                        _resource_overrides=overrides,
                    )
                    replay.require_consumed()

                    self.assertEqual(live_valid, replay_valid)
                    self.assertEqual(
                        _canonical_bytes(live_report),
                        _canonical_bytes(replay_report),
                    )

    def test_resource_overrides_require_exact_member_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(_resource_spec("missing/original.bin")),
                encoding="utf-8",
            )
            sealed_resource = root / "resource.bin"
            sealed_resource.write_bytes(b"sealed")
            provider = _CountingAuditQueryProvider()

            invalid_overrides = (
                {},
                {
                    "briefing.bin": sealed_resource,
                    "extra.bin": sealed_resource,
                },
            )
            for overrides in invalid_overrides:
                with (
                    self.subTest(members=sorted(overrides)),
                    self.assertRaisesRegex(
                        BuildSpecError,
                        "exact specification member set",
                    ),
                ):
                    audit_build_spec(
                        spec_path,
                        dcs_root=root / "missing-dcs",
                        installed_terrain=None,
                        pydcs_root=root / "missing-pydcs",
                        pydcs_terrain="fixture",
                        _query_provider=provider,
                        _resource_overrides=overrides,
                    )
            self.assertEqual(provider.calls, [])

    def test_resource_override_rejects_unsafe_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(_resource_spec("missing/original.bin")),
                encoding="utf-8",
            )
            unsafe_resource = root / "not-a-file"
            unsafe_resource.mkdir()
            provider = _CountingAuditQueryProvider()

            with self.assertRaisesRegex(
                BuildSpecError,
                "not a safe regular file",
            ):
                audit_build_spec(
                    spec_path,
                    dcs_root=root / "missing-dcs",
                    installed_terrain=None,
                    pydcs_root=root / "missing-pydcs",
                    pydcs_terrain="fixture",
                    _query_provider=provider,
                    _resource_overrides={"briefing.bin": unsafe_resource},
                )
            self.assertEqual(provider.calls, [])

    def test_query_kind_and_canonical_parameter_vocabulary_is_closed(
        self,
    ) -> None:
        provider = _CountingAuditQueryProvider()
        invalid_calls = (
            lambda: provider.query("unknown"),
            lambda: provider.query("countries", extra=True),
            lambda: provider.query("cloud_preset"),
            lambda: provider.query("cloud_preset", preset=""),
            lambda: provider.query(
                "pydcs_unit",
                category="unknown",
                unit_type="Fixture Plane",
            ),
            lambda: provider.query(
                "pydcs_airport",
                terrain="fixture",
                airdrome_id=True,
            ),
            lambda: provider.query(
                "payload_match",
                unit_type="Fixture Plane",
                configured_composition_sha256="0" * 64,
                pylons=[{"num": 1, "CLSID": "{FIXTURE}"}],
            ),
        )
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call), self.assertRaises(ValueError):
                invalid_call()
        self.assertEqual(provider.calls, [])

        fingerprint = spec_audit_module.payload_fingerprint(
            "Fixture Plane",
            [{"num": 1, "CLSID": "{FIXTURE}"}],
        )
        provider.query(
            "payload_match",
            unit_type="Fixture Plane",
            configured_composition_sha256=fingerprint[
                "configured_composition_sha256"
            ],
            pylons=fingerprint["normalized"]["pylons"],
        )
        self.assertEqual(len(provider.calls), 1)

    def test_falsy_provider_never_falls_back_to_live_sources(self) -> None:
        provider = _FalsyAuditQueryProvider()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(
                spec_audit_module,
                "_LiveAuditQueryProvider",
                side_effect=AssertionError("falsy provider was replaced"),
            ) as live_provider,
            self.assertRaisesRegex(ValueError, "does not exist"),
        ):
            root = Path(temp_dir)
            audit_build_spec(
                root / "missing-spec.json",
                dcs_root=root / "missing-dcs",
                installed_terrain=None,
                pydcs_root=root / "missing-pydcs",
                pydcs_terrain="fixture",
                _query_provider=provider,
            )
        live_provider.assert_not_called()
        self.assertEqual(provider.calls, [])

    def test_replay_rejects_wrong_order_params_and_unused_entries(self) -> None:
        entries = [
            {"kind": "countries", "params": {}, "result": {"value": 1}},
            {
                "kind": "cloud_preset",
                "params": {"preset": "FixtureRain"},
                "result": {"value": 2},
            },
        ]
        wrong_order = spec_audit_module._ReplayAuditQueryProvider(entries)
        with self.assertRaisesRegex(ValueError, "order or canonical parameters"):
            wrong_order.query("cloud_preset", preset="FixtureRain")

        wrong_params = spec_audit_module._ReplayAuditQueryProvider(entries)
        wrong_params.query("countries")
        with self.assertRaisesRegex(ValueError, "order or canonical parameters"):
            wrong_params.query("cloud_preset", preset="Different")

        unused = spec_audit_module._ReplayAuditQueryProvider(entries)
        unused.query("countries")
        with self.assertRaisesRegex(ValueError, "unused entries"):
            unused.require_consumed()

        with self.assertRaisesRegex(ValueError, "require kind, params, and result"):
            spec_audit_module._ReplayAuditQueryProvider(
                [{"kind": "countries", "params": {}, "result": {}, "extra": 1}]
            )

    def test_record_and_replay_results_do_not_share_mutable_references(
        self,
    ) -> None:
        delegate = _CountingAuditQueryProvider()
        recorder = spec_audit_module._RecordingAuditQueryProvider(delegate)
        first = recorder.query("countries")
        first["changed"] = True
        transcript = recorder.transcript()
        transcript[0]["result"]["changed"] = "outside"

        fresh = recorder.transcript()
        self.assertNotIn("changed", fresh[0]["result"])
        replay = spec_audit_module._ReplayAuditQueryProvider(fresh)
        result = replay.query("countries")
        result["changed"] = True
        self.assertNotIn("changed", fresh[0]["result"])


if __name__ == "__main__":
    unittest.main()
