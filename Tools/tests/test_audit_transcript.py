from __future__ import annotations

from copy import deepcopy
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

from dcsmizzer import audit_transcript as transcript_module  # noqa: E402
from dcsmizzer import spec_audit as spec_audit_module  # noqa: E402
from tests import test_spec_audit as audit_fixtures  # noqa: E402


class _ScriptedProvider(spec_audit_module._AuditQueryProvider):
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _query_canonical(
        self,
        kind: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((kind, params))
        if len(self.calls) > len(self.results):
            raise AssertionError("unexpected scripted query")
        return self.results[len(self.calls) - 1]


def _params(kind: str, *, alternate: bool = False) -> dict[str, object]:
    suffix = " Two" if alternate else ""
    if kind == "cloud_preset":
        return {"preset": f"FixtureRain{suffix}"}
    if kind == "pydcs_unit":
        return {"category": "plane", "unit_type": f"Fixture Plane{suffix}"}
    if kind in {"dcs_payload", "dcs_module_index"}:
        return {"unit_type": f"Fixture Plane{suffix}"}
    if kind == "payload_match":
        unit_type = f"Fixture Plane{suffix}"
        pylons = [{"num": 1, "CLSID": f"{{FIXTURE{suffix}}}"}]
        fingerprint = spec_audit_module.payload_fingerprint(unit_type, pylons)
        return {
            "configured_composition_sha256": fingerprint[
                "configured_composition_sha256"
            ],
            "pylons": fingerprint["normalized"]["pylons"],
            "unit_type": unit_type,
        }
    if kind in {"pydcs_airport", "br_airbase", "dcs_airbase"}:
        return {
            "airdrome_id": 8 if alternate else 7,
            "terrain": "FixtureMapTwo" if alternate else "FixtureMap",
        }
    return {}


def _result(
    kind: str,
    params: dict[str, object],
    *,
    marker: object | None = None,
) -> dict[str, object]:
    if kind == "weather_constraints_available":
        return {"available": True}
    if kind == "installed_product_version":
        return {"product_version": "2.9.0"}
    value: dict[str, object] = {
        "schema": transcript_module._REPORT_RESULT_SCHEMAS[kind]
    }
    if marker is not None:
        value["marker"] = marker
    if kind == "cloud_preset":
        value["filter"] = {"preset": params["preset"]}
    elif kind == "pydcs_unit":
        value["filters"] = {
            "unit_type": params["unit_type"],
            "category": params["category"],
            "search": None,
            "limit": 20,
        }
    elif kind == "dcs_payload":
        value["unit_type"] = params["unit_type"]
    elif kind == "dcs_module_index":
        value["filters"] = {
            "module": None,
            "unit_type": params["unit_type"],
            "service_country": None,
            "service_year": None,
        }
    elif kind == "pydcs_terrains":
        value["filters"] = {
            "terrain": None,
            "latitude": None,
            "longitude": None,
            "x": None,
            "y": None,
        }
    elif kind in {"br_terrains", "combined_terrains"}:
        value["filters"] = {"terrain": None}
    elif kind == "payload_match":
        value.update(
            {
                "unit_type": params["unit_type"],
                "query": {
                    "valid": True,
                    "normalized": {
                        "unit_type": params["unit_type"],
                        "pylons": params["pylons"],
                        "tasks": None,
                        "preset_name": None,
                        "display_name": None,
                        "category": None,
                    },
                    "fingerprints": {
                        "configured_composition_sha256": params[
                            "configured_composition_sha256"
                        ]
                    },
                },
            }
        )
    elif kind == "pydcs_airport":
        value["filters"] = {
            "terrain_query": params["terrain"],
            "terrain_package": "fixture",
            "terrain_class": "FixtureTerrain",
            "miz_theatre_name": "FixtureMap",
            "airport": None,
            "airdrome_id": params["airdrome_id"],
            "parking": None,
            "airplane_only": False,
            "limit": None,
        }
    elif kind == "br_airbase":
        value["filters"] = {
            "terrain": params["terrain"],
            "airport": None,
            "airdrome_id": params["airdrome_id"],
            "parking": None,
            "airplane_only": False,
            "helicopter_only": False,
            "limit": None,
        }
    elif kind == "dcs_airbase":
        value["terrain_directory"] = params["terrain"]
        value["filter"] = {"airdrome_id": params["airdrome_id"]}
    return value


def _entries() -> list[dict[str, object]]:
    return [
        {
            "kind": kind,
            "params": (params := _params(kind)),
            "result": _result(kind, params),
        }
        for kind in transcript_module.AUDIT_QUERY_KINDS
    ]


class AuditTranscriptTests(unittest.TestCase):
    def test_all_sixteen_kinds_round_trip_as_canonical_json(self) -> None:
        entries = _entries()
        transcript = transcript_module.build_audit_transcript(entries)
        payload = transcript_module.canonical_audit_transcript_bytes(
            transcript
        )

        self.assertEqual(
            transcript["schema"],
            "dcsmizzer.audit-evidence-transcript/v1",
        )
        self.assertEqual(len(transcript["requests"]), 16)
        self.assertEqual(len(transcript["responses"]), 16)
        self.assertEqual(
            [record["sha256"] for record in transcript["responses"]],
            sorted(record["sha256"] for record in transcript["responses"]),
        )
        self.assertFalse(payload.endswith(b"\n"))
        self.assertEqual(
            transcript_module.parse_audit_transcript(payload),
            transcript,
        )
        self.assertEqual(
            transcript_module.audit_transcript_sha256(transcript),
            hashlib.sha256(payload).hexdigest(),
        )
        self.assertEqual(
            transcript_module.build_audit_transcript(entries),
            transcript,
        )

        replay = transcript_module.ReplayProvider(transcript)
        for entry in entries:
            self.assertEqual(
                replay.query(entry["kind"], **entry["params"]),
                entry["result"],
            )
        replay.require_consumed()

    def test_capture_deduplicates_and_detaches_mutable_values(self) -> None:
        shared = {"nested": [1, 2]}
        first_result = _result("countries", {}, marker={"a": shared, "b": shared})
        provider = _ScriptedProvider([first_result, first_result])
        capture = transcript_module.CaptureProvider(provider)

        returned = capture.query("countries")
        returned["marker"]["a"]["nested"].append(3)
        capture.query("countries")
        first = capture.transcript()
        first["responses"][0]["envelope"]["value"]["marker"] = "changed"
        second = capture.transcript()

        self.assertEqual(capture.request_count, 2)
        self.assertEqual(capture.response_count, 1)
        self.assertEqual(len(second["requests"]), 2)
        marker = second["responses"][0]["envelope"]["value"]["marker"]
        self.assertEqual(marker["a"]["nested"], [1, 2])
        self.assertIsNot(marker["a"], marker["b"])
        self.assertEqual(first_result["marker"]["a"]["nested"], [1, 2])
        self.assertIs(first_result["marker"]["a"], first_result["marker"]["b"])

    def test_repeated_query_with_different_response_fails_without_recording(
        self,
    ) -> None:
        provider = _ScriptedProvider(
            [
                _result("countries", {}, marker=1),
                _result("countries", {}, marker=2),
            ]
        )
        capture = transcript_module.CaptureProvider(provider)
        capture.query("countries")

        with self.assertRaisesRegex(ValueError, "different response"):
            capture.query("countries")

        self.assertEqual(capture.request_count, 1)
        self.assertEqual(capture.response_count, 1)

    def test_replay_enforces_order_parameters_exhaustion_and_consumption(
        self,
    ) -> None:
        entries = [
            _entries()[0],
            _entries()[4],
        ]
        transcript = transcript_module.build_audit_transcript(entries)
        replay = transcript_module.ReplayProvider(transcript)

        with self.assertRaisesRegex(ValueError, "order or parameters"):
            replay.query("cloud_preset", **entries[1]["params"])
        self.assertEqual(replay.remaining, 2)
        replay.query("countries")
        with self.assertRaisesRegex(ValueError, "unused requests"):
            replay.require_consumed()
        cloud_result = replay.query("cloud_preset", **entries[1]["params"])
        cloud_result["filter"]["preset"] = "mutated"
        replay.require_consumed()
        with self.assertRaisesRegex(ValueError, "exhausted"):
            replay.query("countries")

        with self.assertRaisesRegex(ValueError, "unused requests"):
            with transcript_module.ReplayProvider(transcript) as unused:
                unused.query("countries")

    def test_hostile_shapes_addresses_and_schema_confusion_fail_closed(
        self,
    ) -> None:
        entries = _entries()[:2]
        transcript = transcript_module.build_audit_transcript(entries)
        mutations: list[dict[str, object]] = []

        extra_top = deepcopy(transcript)
        extra_top["extra"] = True
        mutations.append(extra_top)
        unknown_kind = deepcopy(transcript)
        unknown_kind["requests"][0]["kind"] = "unknown"
        mutations.append(unknown_kind)
        wrong_params_schema = deepcopy(transcript)
        wrong_params_schema["requests"][0]["params"]["schema"] = "wrong"
        mutations.append(wrong_params_schema)
        missing_response = deepcopy(transcript)
        missing_response["requests"][0]["response_sha256"] = "0" * 64
        mutations.append(missing_response)
        unreferenced = deepcopy(transcript)
        unreferenced["requests"] = []
        mutations.append(unreferenced)
        duplicate = deepcopy(transcript)
        duplicate["responses"].append(deepcopy(duplicate["responses"][0]))
        duplicate["responses"].sort(key=lambda item: item["sha256"])
        mutations.append(duplicate)
        wrong_size = deepcopy(transcript)
        wrong_size["responses"][0]["size_bytes"] += 1
        mutations.append(wrong_size)
        wrong_hash = deepcopy(transcript)
        wrong_hash["responses"][0]["sha256"] = "f" * 64
        wrong_hash["responses"].sort(key=lambda item: item["sha256"])
        mutations.append(wrong_hash)
        wrong_result_schema = deepcopy(transcript)
        wrong_result_schema["responses"][0]["envelope"]["schema"] = "wrong"
        mutations.append(wrong_result_schema)

        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                transcript_module.validate_audit_transcript(mutation)

        unsorted = transcript_module.build_audit_transcript(_entries()[:3])
        unsorted["responses"].reverse()
        with self.assertRaisesRegex(ValueError, "hash-sorted"):
            transcript_module.validate_audit_transcript(unsorted)

    def test_every_query_result_binding_is_rechecked(self) -> None:
        bound_kinds = (
            "cloud_preset",
            "pydcs_unit",
            "dcs_payload",
            "dcs_module_index",
            "pydcs_terrains",
            "br_terrains",
            "combined_terrains",
            "payload_match",
            "pydcs_airport",
            "br_airbase",
            "dcs_airbase",
        )
        for kind in bound_kinds:
            params = _params(kind)
            wrong_params = _params(kind, alternate=True)
            if not wrong_params:
                wrong_result = _result(kind, params)
                wrong_result["filters"]["terrain"] = "filtered"
            else:
                wrong_result = _result(kind, wrong_params)
            entry = {"kind": kind, "params": params, "result": wrong_result}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                transcript_module.build_audit_transcript([entry])

        payload_params = _params("payload_match")
        noncanonical_payload_params = deepcopy(payload_params)
        noncanonical_payload_params["pylons"][0]["num"] = 1.0
        with self.assertRaisesRegex(ValueError, "pylons are not canonical"):
            transcript_module.build_audit_transcript(
                [
                    {
                        "kind": "payload_match",
                        "params": noncanonical_payload_params,
                        "result": _result("payload_match", payload_params),
                    }
                ]
            )

        airport_params = _params("pydcs_airport")
        numeric_alias = _result("pydcs_airport", airport_params)
        numeric_alias["filters"]["airdrome_id"] = 7.0
        with self.assertRaisesRegex(ValueError, "not query-bound"):
            transcript_module.build_audit_transcript(
                [
                    {
                        "kind": "pydcs_airport",
                        "params": airport_params,
                        "result": numeric_alias,
                    }
                ]
            )

    def test_nonfinite_recursive_deep_and_noncanonical_json_is_rejected(
        self,
    ) -> None:
        for number in (float("nan"), float("inf"), float("-inf")):
            entry = {
                "kind": "countries",
                "params": {},
                "result": _result("countries", {}, marker=number),
            }
            with self.subTest(number=number), self.assertRaises(ValueError):
                transcript_module.build_audit_transcript([entry])

        recursive: dict[str, object] = {}
        recursive["self"] = recursive
        with self.assertRaisesRegex(ValueError, "recursive"):
            transcript_module.build_audit_transcript(
                [
                    {
                        "kind": "countries",
                        "params": {},
                        "result": _result("countries", {}, marker=recursive),
                    }
                ]
            )

        too_deep: object = "leaf"
        for _index in range(transcript_module.MAX_JSON_DEPTH + 1):
            too_deep = [too_deep]
        with self.assertRaisesRegex(ValueError, "depth limit"):
            transcript_module.build_audit_transcript(
                [
                    {
                        "kind": "countries",
                        "params": {},
                        "result": _result("countries", {}, marker=too_deep),
                    }
                ]
            )

        valid = transcript_module.build_audit_transcript([])
        canonical = transcript_module.canonical_audit_transcript_bytes(valid)
        with self.assertRaisesRegex(ValueError, "not canonical"):
            transcript_module.parse_audit_transcript(b" " + canonical)
        duplicate_key = canonical.replace(
            b'{"requests":',
            b'{"requests":[],"requests":',
            1,
        )
        with self.assertRaisesRegex(ValueError, "JSON is invalid"):
            transcript_module.parse_audit_transcript(duplicate_key)

        deep_payload = b"[" * 129 + b"0" + b"]" * 129
        with (
            patch.object(
                transcript_module.json,
                "loads",
                side_effect=AssertionError("parser must not run"),
            ) as loads,
            self.assertRaisesRegex(ValueError, "depth limit"),
        ):
            transcript_module.parse_audit_transcript(deep_payload)
        loads.assert_not_called()

    def test_limits_are_exact_and_enforced_without_large_allocations(self) -> None:
        self.assertEqual(transcript_module.MAX_JSON_DEPTH, 128)
        self.assertEqual(transcript_module.MAX_JSON_NODES, 1_000_000)
        self.assertEqual(transcript_module.MAX_CALLS, 4096)
        self.assertEqual(transcript_module.MAX_RESPONSES, 4096)
        self.assertEqual(transcript_module.MAX_RESPONSE_BYTES, 16 * 1024 * 1024)
        self.assertEqual(transcript_module.MAX_QUERY_PARAMS_BYTES, 64 * 1024)
        self.assertEqual(transcript_module.MAX_TRANSCRIPT_BYTES, 128 * 1024 * 1024)

        params_provider = _ScriptedProvider([])
        capture = transcript_module.CaptureProvider(params_provider)
        with (
            patch.object(transcript_module, "MAX_QUERY_PARAMS_BYTES", 32),
            self.assertRaisesRegex(ValueError, "params byte limit"),
        ):
            capture.query("cloud_preset", preset="x" * 100)
        self.assertEqual(params_provider.calls, [])

        result = _result("countries", {}, marker="x" * 100)
        response_capture = transcript_module.CaptureProvider(
            _ScriptedProvider([result])
        )
        with (
            patch.object(transcript_module, "MAX_RESPONSE_BYTES", 64),
            self.assertRaisesRegex(ValueError, "response byte limit"),
        ):
            response_capture.query("countries")

        oversized_delegate = _ScriptedProvider([result])
        guarded_capture = transcript_module.CaptureProvider(oversized_delegate)
        with (
            patch.object(transcript_module, "MAX_RESPONSE_BYTES", 64),
            patch.object(
                spec_audit_module,
                "deepcopy",
                side_effect=AssertionError("unbounded result copy must not run"),
            ) as defensive_copy,
            self.assertRaisesRegex(ValueError, "response byte limit"),
        ):
            guarded_capture.query("countries")
        defensive_copy.assert_not_called()
        self.assertEqual(len(oversized_delegate.calls), 1)
        self.assertEqual(guarded_capture.request_count, 0)

        oversized_params = {"preset": "x" * 100}
        with (
            patch.object(transcript_module, "MAX_QUERY_PARAMS_BYTES", 32),
            patch.object(
                transcript_module,
                "_canonical_audit_query_params",
                side_effect=AssertionError("params clone must not run"),
            ) as canonicalize_params,
            patch.object(
                transcript_module.json,
                "dumps",
                side_effect=AssertionError("canonical serializer must not run"),
            ) as params_dumps,
            self.assertRaisesRegex(ValueError, "params byte limit"),
        ):
            transcript_module._params_envelope("cloud_preset", oversized_params)
        canonicalize_params.assert_not_called()
        params_dumps.assert_not_called()

        guarded_params_delegate = _ScriptedProvider(
            [_result("cloud_preset", oversized_params)]
        )
        guarded_params_capture = transcript_module.CaptureProvider(
            guarded_params_delegate
        )
        with (
            patch.object(transcript_module, "MAX_QUERY_PARAMS_BYTES", 32),
            patch.object(
                spec_audit_module,
                "deepcopy",
                side_effect=AssertionError("unbounded params copy must not run"),
            ) as params_copy,
            patch.object(
                transcript_module.json,
                "dumps",
                side_effect=AssertionError("canonical serializer must not run"),
            ) as public_params_dumps,
            self.assertRaisesRegex(ValueError, "params byte limit"),
        ):
            guarded_params_capture.query(
                "cloud_preset",
                **oversized_params,
            )
        params_copy.assert_not_called()
        public_params_dumps.assert_not_called()
        self.assertEqual(guarded_params_delegate.calls, [])
        self.assertEqual(guarded_params_capture.request_count, 0)

        oversized_result = _result("countries", {}, marker="x" * 100)
        with (
            patch.object(transcript_module, "MAX_RESPONSE_BYTES", 64),
            patch.object(
                transcript_module,
                "_validate_query_result",
                side_effect=AssertionError("result clone must not run"),
            ) as validate_result,
            patch.object(
                transcript_module.json,
                "dumps",
                side_effect=AssertionError("canonical serializer must not run"),
            ) as result_dumps,
            self.assertRaisesRegex(ValueError, "response byte limit"),
        ):
            transcript_module._response_envelope("countries", oversized_result)
        validate_result.assert_not_called()
        result_dumps.assert_not_called()

        oversized_entry = {
            "kind": "countries",
            "params": {},
            "result": oversized_result,
        }
        clone_labels: list[str] = []
        original_clone = transcript_module._clone_json

        def guarded_clone(value: object, *, label: str) -> object:
            clone_labels.append(label)
            if label == "audit transcript entry result":
                raise AssertionError("entry result clone must not run")
            return original_clone(value, label=label)

        with (
            patch.object(transcript_module, "MAX_RESPONSE_BYTES", 64),
            patch.object(
                transcript_module,
                "_clone_json",
                side_effect=guarded_clone,
            ) as clone_result,
            self.assertRaisesRegex(ValueError, "response byte limit"),
        ):
            transcript_module.build_audit_transcript([oversized_entry])
        self.assertNotIn("audit transcript entry result", clone_labels)
        self.assertEqual(clone_result.call_count, 1)

        call_delegate = _ScriptedProvider(
            [_result("countries", {}), _result("countries", {})]
        )
        call_capture = transcript_module.CaptureProvider(call_delegate)
        with patch.object(transcript_module, "MAX_CALLS", 1):
            call_capture.query("countries")
            with self.assertRaisesRegex(ValueError, "query limit"):
                call_capture.query("countries")
        self.assertEqual(len(call_delegate.calls), 1)

        response_delegate = _ScriptedProvider(
            [
                _result("countries", {}),
                _result("gci_evidence", {}),
            ]
        )
        response_count_capture = transcript_module.CaptureProvider(
            response_delegate
        )
        with patch.object(transcript_module, "MAX_RESPONSES", 1):
            response_count_capture.query("countries")
            with self.assertRaisesRegex(ValueError, "response limit"):
                response_count_capture.query("gci_evidence")
        self.assertEqual(response_count_capture.response_count, 1)

        value = transcript_module.build_audit_transcript([])
        payload = transcript_module.canonical_audit_transcript_bytes(value)
        with patch.object(
            transcript_module,
            "MAX_TRANSCRIPT_BYTES",
            len(payload),
        ):
            self.assertEqual(
                transcript_module.parse_audit_transcript(payload),
                value,
            )
        with (
            patch.object(
                transcript_module,
                "MAX_TRANSCRIPT_BYTES",
                len(payload) - 1,
            ),
            self.assertRaisesRegex(ValueError, "byte limit"),
        ):
            transcript_module.validate_audit_transcript(value)

        oversized_transcript = {
            "schema": "x" * 100,
            "requests": [],
            "responses": [],
        }
        with (
            patch.object(transcript_module, "MAX_TRANSCRIPT_BYTES", 32),
            patch.object(
                transcript_module,
                "_validate_transcript_container",
                side_effect=AssertionError(
                    "transcript validation must not precede preflight"
                ),
            ) as validate_container,
            patch.object(
                transcript_module,
                "_normalized_json_bytes",
                side_effect=AssertionError("transcript clone must not run"),
            ) as normalize_transcript,
            patch.object(
                transcript_module.json,
                "dumps",
                side_effect=AssertionError("canonical serializer must not run"),
            ) as transcript_dumps,
            self.assertRaisesRegex(ValueError, "transcript byte limit"),
        ):
            transcript_module.validate_audit_transcript(oversized_transcript)
        validate_container.assert_not_called()
        normalize_transcript.assert_not_called()
        transcript_dumps.assert_not_called()

        one_entry = _entries()[:1]
        one_transcript = transcript_module.build_audit_transcript(one_entry)
        one_size = len(
            transcript_module.canonical_audit_transcript_bytes(one_transcript)
        )
        immediate = transcript_module.CaptureProvider(
            _ScriptedProvider([one_entry[0]["result"]])
        )
        with (
            patch.object(
                transcript_module,
                "MAX_TRANSCRIPT_BYTES",
                one_size - 1,
            ),
            self.assertRaisesRegex(ValueError, "byte limit"),
        ):
            immediate.query("countries")
        self.assertEqual(immediate.request_count, 0)

        with (
            patch.object(transcript_module, "MAX_CALLS", 1),
            self.assertRaisesRegex(ValueError, "query limit"),
        ):
            transcript_module.validate_audit_transcript(
                {
                    "schema": transcript_module.AUDIT_TRANSCRIPT_SCHEMA,
                    "requests": [{}, {}],
                    "responses": [],
                }
            )

        dense_result = _result("countries", {}, marker=[0] * 32)
        with (
            patch.object(transcript_module, "MAX_JSON_NODES", 16),
            self.assertRaisesRegex(ValueError, "node limit"),
        ):
            transcript_module.build_audit_transcript(
                [{"kind": "countries", "params": {}, "result": dense_result}]
            )

        dense_payload = b'{"dense":[' + b",".join([b"0"] * 32) + b"]}"
        with (
            patch.object(transcript_module, "MAX_JSON_NODES", 16),
            patch.object(
                transcript_module.json,
                "loads",
                side_effect=AssertionError("parser must not run"),
            ) as loads,
            self.assertRaisesRegex(ValueError, "node limit"),
        ):
            transcript_module.parse_audit_transcript(dense_payload)
        loads.assert_not_called()

    def test_in_memory_preflight_matches_canonical_utf8_size(self) -> None:
        values = (
            None,
            True,
            False,
            0,
            -123456789,
            1.25,
            -0.0,
            1e20,
            1e-20,
            sys.float_info.max,
            sys.float_info.min,
            5e-324,
            'quote"slash\\control\b\f\n\r\t\x00',
            "é中文😀\u2028",
            [],
            [1, "two", None],
            {},
            {"é": "😀", "nested": [False, {"control": "\x1f"}]},
        )
        for value in values:
            with self.subTest(value=repr(value)):
                canonical = json.dumps(
                    value,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                measured = transcript_module._preflight_in_memory_json(
                    value,
                    maximum_bytes=len(canonical),
                    label="audit fixture",
                )
                self.assertEqual(measured, len(canonical))
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    transcript_module._preflight_in_memory_json(
                        value,
                        maximum_bytes=len(canonical) - 1,
                        label="audit fixture",
                    )

    def test_capture_live_helper_passes_resource_overrides(self) -> None:
        collected = _result("countries", {})

        def fake_audit(
            *args: object,
            **kwargs: object,
        ) -> tuple[dict[str, object], bool]:
            del args
            provider = kwargs["_query_provider"]
            provider.query("countries")
            self.assertEqual(
                kwargs["_resource_overrides"],
                {"l10n/DEFAULT/briefing.png": Path("sealed.bin")},
            )
            return {"schema": "fixture.audit/v1"}, True

        with (
            patch.object(
                spec_audit_module,
                "countries_report",
                return_value=collected,
            ),
            patch.object(
                transcript_module,
                "audit_build_spec",
                side_effect=fake_audit,
            ),
        ):
            report, valid, transcript = transcript_module.capture_live_audit(
                Path("spec.json"),
                dcs_root=Path("DCS"),
                installed_terrain=None,
                pydcs_root=Path("pydcs"),
                pydcs_terrain=None,
                _resource_overrides={
                    "l10n/DEFAULT/briefing.png": Path("sealed.bin")
                },
            )

        self.assertTrue(valid)
        self.assertEqual(report, {"schema": "fixture.audit/v1"})
        self.assertEqual(len(transcript["requests"]), 1)

    def test_real_fixture_capture_and_missing_root_replay_are_exact(self) -> None:
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

            report, valid, transcript = (
                transcript_module.capture_live_audit(
                    spec_path,
                    dcs_root=dcs_root,
                    installed_terrain="FixtureTerrain",
                    pydcs_root=pydcs_root,
                    pydcs_terrain="fixture",
                    br_root=br_root,
                )
            )
            replayed, replay_valid = transcript_module.replay_audit(
                transcript,
                spec_path,
                dcs_root=root / "missing-dcs",
                installed_terrain="FixtureTerrain",
                pydcs_root=root / "missing-pydcs",
                pydcs_terrain="fixture",
                br_root=root / "missing-briefing-room",
                _resource_overrides={},
            )

        self.assertTrue(valid)
        self.assertEqual(replay_valid, valid)
        self.assertEqual(replayed, report)
        self.assertEqual(len(transcript["requests"]), 14)
        self.assertEqual(len(transcript["responses"]), 14)

    def test_replay_helper_requires_explicit_sealed_resource_set(self) -> None:
        with (
            patch.object(
                transcript_module,
                "audit_build_spec",
                side_effect=AssertionError("audit must not start"),
            ) as audit,
            self.assertRaisesRegex(ValueError, "sealed resource override set"),
        ):
            transcript_module.replay_audit(
                {
                    "schema": transcript_module.AUDIT_TRANSCRIPT_SCHEMA,
                    "requests": [],
                    "responses": [],
                },
                Path("spec.json"),
                dcs_root=Path("missing-dcs"),
                installed_terrain=None,
                pydcs_root=Path("missing-pydcs"),
                pydcs_terrain=None,
            )
        audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
