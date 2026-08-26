"""Bounded, content-addressed transcripts for build-spec audit queries."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .dcs_static import payload_fingerprint
from .spec_audit import (
    _AUDIT_QUERY_PARAMETER_NAMES,
    _AuditQueryProvider,
    _LiveAuditQueryProvider,
    _canonical_audit_query_params,
    audit_build_spec,
)


AUDIT_TRANSCRIPT_SCHEMA = "dcsmizzer.audit-evidence-transcript/v1"
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 1_000_000
MAX_CALLS = 4096
MAX_RESPONSES = 4096
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_QUERY_PARAMS_BYTES = 64 * 1024
MAX_TRANSCRIPT_BYTES = 128 * 1024 * 1024

AUDIT_QUERY_KINDS = (
    "countries",
    "gci_evidence",
    "weather_constraints_available",
    "weather_constraints",
    "cloud_preset",
    "pydcs_unit",
    "dcs_payload",
    "dcs_module_index",
    "pydcs_terrains",
    "br_terrains",
    "combined_terrains",
    "installed_product_version",
    "payload_match",
    "pydcs_airport",
    "br_airbase",
    "dcs_airbase",
)

_REPORT_RESULT_SCHEMAS = {
    "countries": "dcsmizzer.dcs-countries/v1",
    "gci_evidence": "dcsmizzer.dcs-mig29-gci/v1",
    "weather_constraints": "dcsmizzer.dcs-weather-constraints/v1",
    "cloud_preset": "dcsmizzer.dcs-cloud-presets/v1",
    "pydcs_unit": "dcsmizzer.pydcs-units/v1",
    "dcs_payload": "dcsmizzer.dcs-default-payloads/v1",
    "dcs_module_index": "dcsmizzer.dcs-module-index/v1",
    "pydcs_terrains": "dcsmizzer.pydcs-terrains/v1",
    "br_terrains": "dcsmizzer.br-terrains/v1",
    "combined_terrains": "dcsmizzer.terrain-coverage/v2",
    "payload_match": "dcsmizzer.dcs-payload-match/v1",
    "pydcs_airport": "dcsmizzer.pydcs-airports/v1",
    "br_airbase": "dcsmizzer.br-airbases/v1",
    "dcs_airbase": "dcsmizzer.dcs-airbase-beacons/v1",
}

if set(AUDIT_QUERY_KINDS) != set(_AUDIT_QUERY_PARAMETER_NAMES):
    raise RuntimeError("audit transcript v1 query vocabulary is out of sync")


class CaptureProvider(_AuditQueryProvider):
    """Capture one exact ordered query stream from a delegate provider."""

    def __init__(self, delegate: _AuditQueryProvider) -> None:
        if not isinstance(delegate, _AuditQueryProvider):
            raise TypeError("audit transcript delegate must be a provider")
        self._delegate = delegate
        self._requests: list[dict[str, Any]] = []
        self._request_sizes: list[int] = []
        self._responses: dict[str, dict[str, Any]] = {}
        self._response_sizes: dict[str, int] = {}
        self._query_responses: dict[bytes, str] = {}

    def query(self, kind: str, /, **params: Any) -> dict[str, Any]:
        _preflight_query_params(kind, params)
        return super().query(kind, **params)

    def _query_canonical(
        self,
        kind: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if len(self._requests) >= MAX_CALLS:
            raise ValueError("audit transcript query limit exceeded")
        params_envelope, params_bytes = _params_envelope(kind, params)
        # Capture already receives canonical params from the outer provider
        # boundary.  Dispatch internally so an unbounded delegate result is
        # measured before the base provider can deepcopy it.  The bounded
        # normalized response below restores the usual detached-result
        # guarantee, while this small clone prevents a delegate from mutating
        # the request record through nested parameter aliases.
        delegate_params = _clone_json(
            params_envelope["value"],
            label="audit delegate query params",
        )
        result = self._delegate._query_canonical(kind, delegate_params)
        result_value, response_envelope, response_bytes = _response_envelope(
            kind,
            result,
        )
        _validate_request_response_binding(kind, params, result_value)
        response_sha256 = hashlib.sha256(response_bytes).hexdigest()
        query_key = params_bytes
        previous_response = self._query_responses.get(query_key)
        if (
            previous_response is not None
            and previous_response != response_sha256
        ):
            raise ValueError(
                "repeated audit query returned a different response"
            )

        new_response = response_sha256 not in self._responses
        if (
            not new_response
            and self._responses[response_sha256]["envelope"]
            != response_envelope
        ):
            raise ValueError("audit response content-address collision")
        if new_response and len(self._responses) >= MAX_RESPONSES:
            raise ValueError("audit transcript response limit exceeded")
        response_record = {
            "sha256": response_sha256,
            "size_bytes": len(response_bytes),
            "envelope": response_envelope,
        }
        request_record = {
            "kind": kind,
            "params": params_envelope,
            "response_sha256": response_sha256,
        }
        request_record_bytes = _canonical_json_bytes(
            request_record,
            label="audit transcript request",
            initial_depth=3,
        )
        response_record_bytes = (
            _canonical_json_bytes(
                response_record,
                label="audit transcript response record",
                initial_depth=3,
            )
            if new_response
            else None
        )
        projected_response_sizes = list(self._response_sizes.values())
        if response_record_bytes is not None:
            projected_response_sizes.append(len(response_record_bytes))
        projected_size = _transcript_size(
            [*self._request_sizes, len(request_record_bytes)],
            projected_response_sizes,
        )
        if projected_size > MAX_TRANSCRIPT_BYTES:
            raise ValueError("audit transcript byte limit exceeded")

        self._requests.append(request_record)
        self._request_sizes.append(len(request_record_bytes))
        if new_response:
            self._responses[response_sha256] = response_record
            assert response_record_bytes is not None
            self._response_sizes[response_sha256] = len(response_record_bytes)
        self._query_responses[query_key] = response_sha256
        return _clone_json(result_value, label="audit query result")

    def transcript(self) -> dict[str, Any]:
        value = {
            "schema": AUDIT_TRANSCRIPT_SCHEMA,
            "requests": self._requests,
            "responses": [
                self._responses[digest]
                for digest in sorted(self._responses)
            ],
        }
        return validate_audit_transcript(value)

    @property
    def request_count(self) -> int:
        return len(self._requests)

    @property
    def response_count(self) -> int:
        return len(self._responses)


class ReplayProvider(_AuditQueryProvider):
    """Low-level exact replay; callers must enforce complete consumption."""

    def __init__(self, transcript: Any) -> None:
        self._transcript = validate_audit_transcript(transcript)
        self._requests = self._transcript["requests"]
        self._responses = {
            record["sha256"]: record
            for record in self._transcript["responses"]
        }
        self._position = 0

    def query(self, kind: str, /, **params: Any) -> dict[str, Any]:
        _preflight_query_params(kind, params)
        return super().query(kind, **params)

    def _query_canonical(
        self,
        kind: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._position >= len(self._requests):
            raise ValueError("audit transcript replay is exhausted")
        expected = self._requests[self._position]
        params_envelope, _payload = _params_envelope(kind, params)
        if expected["kind"] != kind or expected["params"] != params_envelope:
            raise ValueError(
                "audit transcript replay order or parameters differ"
            )
        response = self._responses[expected["response_sha256"]]
        if response["envelope"]["kind"] != kind:
            raise ValueError("audit transcript response kind differs")
        _validate_request_response_binding(
            kind,
            params,
            response["envelope"]["value"],
        )
        self._position += 1
        return _clone_json(
            response["envelope"]["value"],
            label="audit replay result",
        )

    def require_consumed(self) -> None:
        if self._position != len(self._requests):
            raise ValueError("audit transcript replay has unused requests")

    @property
    def remaining(self) -> int:
        return len(self._requests) - self._position

    def __enter__(self) -> ReplayProvider:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: Any,
    ) -> bool:
        if exception_type is None:
            self.require_consumed()
        return False


def build_audit_transcript(entries: Any) -> dict[str, Any]:
    """Build a bounded transcript from ordered kind/params/result entries."""

    if type(entries) is not list:
        raise ValueError("audit transcript entries must be an array")
    if len(entries) > MAX_CALLS:
        raise ValueError("audit transcript query limit exceeded")
    provider = _EntryProvider(entries)
    capture = CaptureProvider(provider)
    for entry in entries:
        if type(entry) is not dict or set(entry) != {
            "kind",
            "params",
            "result",
        }:
            raise ValueError("audit transcript entry fields are not exact")
        kind = entry["kind"]
        params = entry["params"]
        if not isinstance(kind, str) or type(params) is not dict:
            raise ValueError("audit transcript entry query is invalid")
        capture.query(kind, **params)
    provider.require_consumed()
    return capture.transcript()


def capture_live_audit(
    spec_path: Path,
    *,
    dcs_root: Path,
    installed_terrain: str | None,
    pydcs_root: Path,
    pydcs_terrain: str | None,
    br_root: Path | None = None,
    require_acknowledged_upstreams: bool = False,
    _resource_overrides: Mapping[str, Path] | None = None,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """Run one audit through the live provider and return its transcript."""

    capture = CaptureProvider(
        _LiveAuditQueryProvider(
            dcs_root=dcs_root,
            pydcs_root=pydcs_root,
            br_root=br_root,
        )
    )
    report, valid = audit_build_spec(
        spec_path,
        dcs_root=dcs_root,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=require_acknowledged_upstreams,
        _query_provider=capture,
        _resource_overrides=_resource_overrides,
    )
    return report, valid, capture.transcript()


def replay_audit(
    transcript: Any,
    spec_path: Path,
    *,
    dcs_root: Path,
    installed_terrain: str | None,
    pydcs_root: Path,
    pydcs_terrain: str | None,
    br_root: Path | None = None,
    require_acknowledged_upstreams: bool = False,
    _resource_overrides: Mapping[str, Path] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Replay one complete audit query stream and require full consumption."""

    if _resource_overrides is None:
        raise ValueError(
            "audit replay requires the exact sealed resource override set"
        )
    replay = ReplayProvider(transcript)
    report, valid = audit_build_spec(
        spec_path,
        dcs_root=dcs_root,
        installed_terrain=installed_terrain,
        pydcs_root=pydcs_root,
        pydcs_terrain=pydcs_terrain,
        br_root=br_root,
        require_acknowledged_upstreams=require_acknowledged_upstreams,
        _query_provider=replay,
        _resource_overrides=_resource_overrides,
    )
    replay.require_consumed()
    return report, valid


def validate_audit_transcript(value: Any) -> dict[str, Any]:
    """Validate and return a detached canonical JSON transcript tree."""

    _preflight_in_memory_json(
        value,
        maximum_bytes=MAX_TRANSCRIPT_BYTES,
        label="audit transcript",
    )
    _validate_transcript_container(value)
    normalized, payload = _normalized_json_bytes(
        value,
        label="audit transcript",
    )
    if len(payload) > MAX_TRANSCRIPT_BYTES:
        raise ValueError("audit transcript byte limit exceeded")
    assert isinstance(normalized, dict)
    if set(normalized) != {"schema", "requests", "responses"}:
        raise ValueError("audit transcript fields are not exact")
    if normalized["schema"] != AUDIT_TRANSCRIPT_SCHEMA:
        raise ValueError("unsupported audit transcript schema")
    requests = normalized["requests"]
    responses = normalized["responses"]
    if not isinstance(requests, list) or not isinstance(responses, list):
        raise ValueError("audit transcript requests/responses must be arrays")

    response_map: dict[str, dict[str, Any]] = {}
    response_hashes: list[str] = []
    for record in responses:
        validated = _validate_response_record(record)
        digest = validated["sha256"]
        if digest in response_map:
            raise ValueError("audit transcript responses are not deduplicated")
        response_map[digest] = validated
        response_hashes.append(digest)
    if response_hashes != sorted(response_hashes):
        raise ValueError("audit transcript responses are not hash-sorted")

    referenced: set[str] = set()
    query_responses: dict[bytes, str] = {}
    for request in requests:
        if not isinstance(request, dict) or set(request) != {
            "kind",
            "params",
            "response_sha256",
        }:
            raise ValueError("audit transcript request fields are not exact")
        kind = request["kind"]
        if not isinstance(kind, str) or kind not in AUDIT_QUERY_KINDS:
            raise ValueError("unsupported audit transcript query kind")
        params = _validate_params_envelope(kind, request["params"])
        digest = _digest(request["response_sha256"], "response reference")
        response = response_map.get(digest)
        if response is None:
            raise ValueError("audit transcript response reference is missing")
        if response["envelope"]["kind"] != kind:
            raise ValueError("audit transcript request/response kinds differ")
        _validate_request_response_binding(
            kind,
            params["value"],
            response["envelope"]["value"],
        )
        query_key = _canonical_json_bytes(
            params,
            label="audit query params",
        )
        previous = query_responses.get(query_key)
        if previous is not None and previous != digest:
            raise ValueError(
                "repeated audit query has different transcript responses"
            )
        query_responses[query_key] = digest
        referenced.add(digest)
    if referenced != set(response_map):
        raise ValueError("audit transcript contains an unreferenced response")
    return normalized


def canonical_audit_transcript_bytes(value: Any) -> bytes:
    """Return the one canonical UTF-8 JSON encoding of a valid transcript."""

    normalized = validate_audit_transcript(value)
    return _canonical_json_bytes(normalized, label="audit transcript")


def audit_transcript_sha256(value: Any) -> str:
    """Hash the canonical bytes of one valid transcript."""

    return hashlib.sha256(canonical_audit_transcript_bytes(value)).hexdigest()


def parse_canonical_audit_transcript(payload: bytes) -> dict[str, Any]:
    """Parse strict canonical JSON bytes and validate the transcript."""

    if not isinstance(payload, bytes):
        raise ValueError("audit transcript payload must be bytes")
    if len(payload) > MAX_TRANSCRIPT_BYTES:
        raise ValueError("audit transcript byte limit exceeded")
    _preflight_json_depth(payload)
    try:
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise ValueError("audit transcript JSON is invalid") from error
    normalized = validate_audit_transcript(value)
    canonical = _canonical_json_bytes(normalized, label="audit transcript")
    if payload != canonical:
        raise ValueError("audit transcript JSON is not canonical")
    return normalized


def parse_audit_transcript(payload: bytes) -> dict[str, Any]:
    """Parse bounded canonical transcript bytes."""

    return parse_canonical_audit_transcript(payload)


def _params_envelope(
    kind: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    params_schema = _params_schema(kind)
    _preflight_query_params(kind, params, params_schema=params_schema)
    canonical = _canonical_audit_query_params(kind, params)
    if kind == "payload_match":
        fingerprint = payload_fingerprint(
            canonical["unit_type"],
            canonical["pylons"],
        )
        if not _json_exact_equal(
            fingerprint["normalized"]["pylons"],
            canonical["pylons"],
        ):
            raise ValueError("audit payload query pylons are not canonical")
    envelope = {
        "schema": params_schema,
        "kind": kind,
        "value": canonical,
    }
    normalized, payload = _normalized_json_bytes(
        envelope,
        label="audit query params",
    )
    if len(payload) > MAX_QUERY_PARAMS_BYTES:
        raise ValueError("audit query params byte limit exceeded")
    assert isinstance(normalized, dict)
    return normalized, payload


def _preflight_query_params(
    kind: str,
    params: dict[str, Any],
    *,
    params_schema: str | None = None,
) -> None:
    if params_schema is None:
        params_schema = _params_schema(kind)
    _preflight_in_memory_json(
        {
            "schema": params_schema,
            "kind": kind,
            "value": params,
        },
        maximum_bytes=MAX_QUERY_PARAMS_BYTES,
        label="audit query params",
    )


def _validate_params_envelope(
    kind: str,
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "kind",
        "value",
    }:
        raise ValueError("audit query params envelope fields are not exact")
    if value["schema"] != _params_schema(kind) or value["kind"] != kind:
        raise ValueError("audit query params envelope schema differs")
    params = value["value"]
    if not isinstance(params, dict):
        raise ValueError("audit query params value must be an object")
    canonical = _canonical_audit_query_params(kind, params)
    if canonical != params:
        raise ValueError("audit query params are not canonical")
    envelope, _payload = _params_envelope(kind, canonical)
    return envelope


def _response_envelope(
    kind: str,
    result: Any,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    result_schema = _result_schema(kind)
    _preflight_in_memory_json(
        {
            "schema": result_schema,
            "kind": kind,
            "value": result,
        },
        maximum_bytes=MAX_RESPONSE_BYTES,
        label="audit query response",
    )
    result_value = _validate_query_result(kind, result)
    envelope = {
        "schema": result_schema,
        "kind": kind,
        "value": result_value,
    }
    normalized, payload = _normalized_json_bytes(
        envelope,
        label="audit query response",
    )
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("audit query response byte limit exceeded")
    assert isinstance(normalized, dict)
    normalized_value = normalized["value"]
    assert isinstance(normalized_value, dict)
    return normalized_value, normalized, payload


def _validate_response_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "sha256",
        "size_bytes",
        "envelope",
    }:
        raise ValueError("audit response record fields are not exact")
    digest = _digest(value["sha256"], "audit response hash")
    size = value["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("audit response size must be a nonnegative integer")
    envelope = value["envelope"]
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema",
        "kind",
        "value",
    }:
        raise ValueError("audit response envelope fields are not exact")
    kind = envelope["kind"]
    if not isinstance(kind, str) or kind not in AUDIT_QUERY_KINDS:
        raise ValueError("unsupported audit response kind")
    if envelope["schema"] != _result_schema(kind):
        raise ValueError("audit response envelope schema differs")
    result_value, canonical_envelope, payload = _response_envelope(
        kind,
        envelope["value"],
    )
    if canonical_envelope != envelope or result_value != envelope["value"]:
        raise ValueError("audit response envelope is not canonical")
    if size != len(payload):
        raise ValueError("audit response size differs from canonical bytes")
    if digest != hashlib.sha256(payload).hexdigest():
        raise ValueError("audit response content address differs")
    return value


def _validate_query_result(kind: str, value: Any) -> dict[str, Any]:
    normalized = _clone_json(value, label="audit query result")
    if not isinstance(normalized, dict):
        raise ValueError("audit query result must be an object")
    if kind == "weather_constraints_available":
        if set(normalized) != {"available"} or not isinstance(
            normalized["available"], bool
        ):
            raise ValueError("weather availability result envelope is invalid")
        return normalized
    if kind == "installed_product_version":
        product_version = normalized.get("product_version")
        if set(normalized) != {"product_version"} or (
            product_version is not None
            and not isinstance(product_version, str)
        ):
            raise ValueError("installed product version envelope is invalid")
        return normalized
    expected_schema = _REPORT_RESULT_SCHEMAS.get(kind)
    if expected_schema is None or normalized.get("schema") != expected_schema:
        raise ValueError("audit query result schema differs")
    return normalized


def _validate_request_response_binding(
    kind: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> None:
    if kind == "cloud_preset":
        _require_exact_fields(
            result.get("filter"),
            {"preset": params["preset"]},
            "cloud preset filter",
        )
    elif kind == "pydcs_unit":
        _require_exact_fields(
            result.get("filters"),
            {
                "unit_type": params["unit_type"],
                "category": params["category"],
                "search": None,
                "limit": 20,
            },
            "pydcs unit filters",
        )
    elif kind == "dcs_payload":
        if result.get("unit_type") != params["unit_type"]:
            raise ValueError("DCS payload result is not query-bound")
    elif kind == "dcs_module_index":
        _require_exact_fields(
            result.get("filters"),
            {
                "module": None,
                "unit_type": params["unit_type"],
                "service_country": None,
                "service_year": None,
            },
            "DCS module filters",
        )
    elif kind == "pydcs_terrains":
        _require_exact_fields(
            result.get("filters"),
            {
                "terrain": None,
                "latitude": None,
                "longitude": None,
                "x": None,
                "y": None,
            },
            "pydcs terrain filters",
        )
    elif kind == "br_terrains":
        _require_exact_fields(
            result.get("filters"),
            {"terrain": None},
            "BriefingRoom terrain filters",
        )
    elif kind == "combined_terrains":
        _require_exact_fields(
            result.get("filters"),
            {"terrain": None},
            "combined terrain filters",
        )
    elif kind == "payload_match":
        _validate_payload_match_binding(params, result)
    elif kind == "pydcs_airport":
        filters = result.get("filters")
        if not isinstance(filters, dict) or set(filters) != {
            "terrain_query",
            "terrain_package",
            "terrain_class",
            "miz_theatre_name",
            "airport",
            "airdrome_id",
            "parking",
            "airplane_only",
            "limit",
        }:
            raise ValueError("pydcs airport filters are not exact")
        if (
            filters["terrain_query"] != params["terrain"]
            or not _json_exact_equal(
                filters["airdrome_id"],
                params["airdrome_id"],
            )
            or filters["airport"] is not None
            or filters["parking"] is not None
            or filters["airplane_only"] is not False
            or filters["limit"] is not None
        ):
            raise ValueError("pydcs airport result is not query-bound")
    elif kind == "br_airbase":
        filters = result.get("filters")
        if not isinstance(filters, dict) or set(filters) != {
            "terrain",
            "airport",
            "airdrome_id",
            "parking",
            "airplane_only",
            "helicopter_only",
            "limit",
        }:
            raise ValueError("BriefingRoom airbase filters are not exact")
        selected_terrain = filters["terrain"]
        if (
            not isinstance(selected_terrain, str)
            or selected_terrain.casefold() != params["terrain"].casefold()
            or not _json_exact_equal(
                filters["airdrome_id"],
                params["airdrome_id"],
            )
            or filters["airport"] is not None
            or filters["parking"] is not None
            or filters["airplane_only"] is not False
            or filters["helicopter_only"] is not False
            or filters["limit"] is not None
        ):
            raise ValueError("BriefingRoom airbase result is not query-bound")
    elif kind == "dcs_airbase":
        _require_exact_fields(
            result.get("filter"),
            {"airdrome_id": params["airdrome_id"]},
            "DCS airbase filter",
        )
        terrain_directory = result.get("terrain_directory")
        if (
            not isinstance(terrain_directory, str)
            or terrain_directory.casefold() != params["terrain"].casefold()
        ):
            raise ValueError("DCS airbase result is not terrain-bound")


def _validate_payload_match_binding(
    params: dict[str, Any],
    result: dict[str, Any],
) -> None:
    query = result.get("query")
    if not isinstance(query, dict):
        raise ValueError("payload match query envelope is missing")
    normalized = query.get("normalized")
    fingerprints = query.get("fingerprints")
    if not isinstance(normalized, dict) or set(normalized) != {
        "unit_type",
        "pylons",
        "tasks",
        "preset_name",
        "display_name",
        "category",
    }:
        raise ValueError("payload match normalized query is not exact")
    if not isinstance(fingerprints, dict):
        raise ValueError("payload match fingerprints are missing")
    if (
        result.get("unit_type") != params["unit_type"]
        or query.get("valid") is not True
        or normalized["unit_type"] != params["unit_type"]
        or not _json_exact_equal(normalized["pylons"], params["pylons"])
        or any(
            normalized[field] is not None
            for field in ("tasks", "preset_name", "display_name", "category")
        )
        or fingerprints.get("configured_composition_sha256")
        != params["configured_composition_sha256"]
    ):
        raise ValueError("payload match result is not query-bound")


def _require_exact_fields(
    actual: Any,
    expected: dict[str, Any],
    label: str,
) -> None:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise ValueError(f"{label} are not exact")
    if not _json_exact_equal(actual, expected):
        raise ValueError(f"{label} are not query-bound")


def _json_exact_equal(left: Any, right: Any) -> bool:
    return _canonical_json_bytes(
        left,
        label="audit binding value",
    ) == _canonical_json_bytes(
        right,
        label="audit binding value",
    )


def _validate_transcript_container(value: Any) -> None:
    if not isinstance(value, dict) or type(value) is not dict:
        raise ValueError("audit transcript must be an object")
    if set(value) != {"schema", "requests", "responses"}:
        raise ValueError("audit transcript fields are not exact")
    requests = value.get("requests")
    responses = value.get("responses")
    if type(requests) is not list or type(responses) is not list:
        raise ValueError("audit transcript requests/responses must be arrays")
    if len(requests) > MAX_CALLS:
        raise ValueError("audit transcript query limit exceeded")
    if len(responses) > MAX_RESPONSES:
        raise ValueError("audit transcript response limit exceeded")


class _EntryProvider(_AuditQueryProvider):
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries
        self._position = 0

    def _query_canonical(
        self,
        kind: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._position >= len(self._entries):
            raise ValueError("audit transcript entries are exhausted")
        entry = self._entries[self._position]
        if type(entry) is not dict or set(entry) != {
            "kind",
            "params",
            "result",
        }:
            raise ValueError("audit transcript entry fields are not exact")
        expected_params = entry["params"]
        if type(expected_params) is not dict:
            raise ValueError("audit transcript entry params must be an object")
        canonical = _canonical_audit_query_params(kind, expected_params)
        if entry["kind"] != kind or canonical != params:
            raise ValueError("audit transcript entry order or params differ")
        self._position += 1
        result = entry["result"]
        if not isinstance(result, dict):
            raise ValueError("audit transcript entry result must be an object")
        _preflight_in_memory_json(
            {
                "schema": _result_schema(kind),
                "kind": kind,
                "value": result,
            },
            maximum_bytes=MAX_RESPONSE_BYTES,
            label="audit query response",
        )
        return _clone_json(result, label="audit transcript entry result")

    def require_consumed(self) -> None:
        if self._position != len(self._entries):
            raise ValueError("audit transcript has unused entries")


def _params_schema(kind: str) -> str:
    if kind not in AUDIT_QUERY_KINDS:
        raise ValueError("unsupported audit transcript query kind")
    return f"dcsmizzer.audit-query-params/{kind}/v1"


def _result_schema(kind: str) -> str:
    if kind not in AUDIT_QUERY_KINDS:
        raise ValueError("unsupported audit transcript query kind")
    return f"dcsmizzer.audit-query-result/{kind}/v1"


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _clone_json(value: Any, *, label: str) -> Any:
    normalized, _payload = _normalized_json_bytes(value, label=label)
    return normalized


def _normalized_json_bytes(
    value: Any,
    *,
    label: str,
    initial_depth: int = 1,
) -> tuple[Any, bytes]:
    try:
        node_budget = [0]
        normalized = _normalize_json_tree(
            value,
            depth=initial_depth,
            active=set(),
            node_budget=node_budget,
        )
        payload = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeEncodeError,
        ValueError,
    ) as error:
        if isinstance(error, ValueError) and str(error).startswith("audit "):
            raise
        raise ValueError(f"{label} is not bounded canonical JSON") from error
    return normalized, payload


def _preflight_in_memory_json(
    value: Any,
    *,
    maximum_bytes: int,
    label: str,
    initial_depth: int = 1,
) -> int:
    """Measure canonical JSON without cloning or materializing encoded bytes."""

    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 0
    ):
        raise ValueError(f"{label} byte limit is invalid")
    try:
        node_budget = [0]
        byte_budget = [0]
        _measure_json_tree(
            value,
            depth=initial_depth,
            active=set(),
            node_budget=node_budget,
            byte_budget=byte_budget,
            maximum_bytes=maximum_bytes,
            label=label,
        )
    except (
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeEncodeError,
        ValueError,
    ) as error:
        if isinstance(error, ValueError) and str(error).startswith("audit "):
            raise
        raise ValueError(f"{label} is not bounded canonical JSON") from error
    return byte_budget[0]


def _measure_json_tree(
    value: Any,
    *,
    depth: int,
    active: set[int],
    node_budget: list[int],
    byte_budget: list[int],
    maximum_bytes: int,
    label: str,
) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError("audit JSON depth limit exceeded")
    node_budget[0] += 1
    if node_budget[0] > MAX_JSON_NODES:
        raise ValueError("audit JSON node limit exceeded")
    if value is None:
        _consume_json_bytes(byte_budget, 4, maximum_bytes, label)
        return
    if type(value) is bool:
        _consume_json_bytes(
            byte_budget,
            4 if value else 5,
            maximum_bytes,
            label,
        )
        return
    if type(value) is str:
        _measure_json_string(value, byte_budget, maximum_bytes, label)
        return
    if type(value) is int:
        sign_bytes = 1 if value < 0 else 0
        magnitude = -value if value < 0 else value
        lower_digits = (
            1
            if magnitude == 0
            else ((magnitude.bit_length() - 1) * 3) // 10 + 1
        )
        if byte_budget[0] + sign_bytes + lower_digits > maximum_bytes:
            raise ValueError(f"{label} byte limit exceeded")
        _consume_json_bytes(
            byte_budget,
            len(str(value)),
            maximum_bytes,
            label,
        )
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("audit JSON contains a non-finite number")
        _consume_json_bytes(
            byte_budget,
            len(repr(value)),
            maximum_bytes,
            label,
        )
        return
    if type(value) not in {dict, list}:
        raise ValueError("audit JSON contains a non-canonical value type")

    identity = id(value)
    if identity in active:
        raise ValueError("audit JSON contains a recursive value")
    active.add(identity)
    try:
        if isinstance(value, list):
            if node_budget[0] + len(value) > MAX_JSON_NODES:
                raise ValueError("audit JSON node limit exceeded")
            _consume_json_bytes(
                byte_budget,
                2 + max(0, len(value) - 1),
                maximum_bytes,
                label,
            )
            for item in value:
                _measure_json_tree(
                    item,
                    depth=depth + 1,
                    active=active,
                    node_budget=node_budget,
                    byte_budget=byte_budget,
                    maximum_bytes=maximum_bytes,
                    label=label,
                )
            return

        node_budget[0] += len(value)
        if (
            node_budget[0] > MAX_JSON_NODES
            or node_budget[0] + len(value) > MAX_JSON_NODES
        ):
            raise ValueError("audit JSON node limit exceeded")
        _consume_json_bytes(
            byte_budget,
            2 + max(0, len(value) - 1) + len(value),
            maximum_bytes,
            label,
        )
        if any(not isinstance(key, str) for key in value):
            raise ValueError("audit JSON object keys must be strings")
        for key, item in value.items():
            _measure_json_string(key, byte_budget, maximum_bytes, label)
            _measure_json_tree(
                item,
                depth=depth + 1,
                active=active,
                node_budget=node_budget,
                byte_budget=byte_budget,
                maximum_bytes=maximum_bytes,
                label=label,
            )
    finally:
        active.remove(identity)


def _measure_json_string(
    value: str,
    byte_budget: list[int],
    maximum_bytes: int,
    label: str,
) -> None:
    # Every Unicode code point occupies at least one output byte.  This cheap
    # lower bound rejects oversized single strings without allocating UTF-8.
    if byte_budget[0] + 2 + len(value) > maximum_bytes:
        raise ValueError(f"{label} byte limit exceeded")
    _consume_json_bytes(byte_budget, 2, maximum_bytes, label)
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\"} or codepoint in {8, 9, 10, 12, 13}:
            encoded_bytes = 2
        elif codepoint < 0x20:
            encoded_bytes = 6
        elif codepoint < 0x80:
            encoded_bytes = 1
        elif codepoint < 0x800:
            encoded_bytes = 2
        elif 0xD800 <= codepoint <= 0xDFFF:
            raise ValueError("audit JSON contains a Unicode surrogate")
        elif codepoint < 0x10000:
            encoded_bytes = 3
        else:
            encoded_bytes = 4
        _consume_json_bytes(
            byte_budget,
            encoded_bytes,
            maximum_bytes,
            label,
        )


def _consume_json_bytes(
    byte_budget: list[int],
    amount: int,
    maximum_bytes: int,
    label: str,
) -> None:
    byte_budget[0] += amount
    if byte_budget[0] > maximum_bytes:
        raise ValueError(f"{label} byte limit exceeded")


def _canonical_json_bytes(
    value: Any,
    *,
    label: str,
    initial_depth: int = 1,
) -> bytes:
    _normalized, payload = _normalized_json_bytes(
        value,
        label=label,
        initial_depth=initial_depth,
    )
    return payload


def _normalize_json_tree(
    value: Any,
    *,
    depth: int,
    active: set[int],
    node_budget: list[int],
) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise ValueError("audit JSON depth limit exceeded")
    node_budget[0] += 1
    if node_budget[0] > MAX_JSON_NODES:
        raise ValueError("audit JSON node limit exceeded")
    if value is None or type(value) in {bool, str, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("audit JSON contains a non-finite number")
        return value
    if type(value) not in {dict, list}:
        raise ValueError("audit JSON contains a non-canonical value type")
    identity = id(value)
    if identity in active:
        raise ValueError("audit JSON contains a recursive value")
    active.add(identity)
    try:
        if isinstance(value, list):
            return [
                _normalize_json_tree(
                    item,
                    depth=depth + 1,
                    active=active,
                    node_budget=node_budget,
                )
                for item in value
            ]
        if any(not isinstance(key, str) for key in value):
            raise ValueError("audit JSON object keys must be strings")
        node_budget[0] += len(value)
        if node_budget[0] > MAX_JSON_NODES:
            raise ValueError("audit JSON node limit exceeded")
        return {
            key: _normalize_json_tree(
                value[key],
                depth=depth + 1,
                active=active,
                node_budget=node_budget,
            )
            for key in sorted(value)
        }
    finally:
        active.remove(identity)


def _transcript_size(
    request_sizes: list[int],
    response_sizes: list[int],
) -> int:
    empty_size = len(
        _canonical_json_bytes(
            {
                "schema": AUDIT_TRANSCRIPT_SCHEMA,
                "requests": [],
                "responses": [],
            },
            label="empty audit transcript",
        )
    )
    return (
        empty_size
        + sum(request_sizes)
        + max(0, len(request_sizes) - 1)
        + sum(response_sizes)
        + max(0, len(response_sizes) - 1)
    )


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _preflight_json_depth(payload: bytes) -> None:
    depth = 0
    node_estimate = 1
    in_string = False
    escaped = False
    for value in payload:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:  # Backslash.
                escaped = True
            elif value == 0x22:  # Double quote.
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in (0x7B, 0x5B):  # Opening brace or bracket.
            depth += 1
            node_estimate += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("audit JSON depth limit exceeded")
        elif value in (0x2C, 0x3A):  # Comma or colon.
            node_estimate += 1
        elif value in (0x7D, 0x5D):  # Closing brace or bracket.
            depth -= 1
            if depth < 0:
                raise ValueError("audit transcript JSON structure is invalid")
        if node_estimate > MAX_JSON_NODES:
            raise ValueError("audit JSON node limit exceeded")
    if in_string or depth != 0:
        raise ValueError("audit transcript JSON structure is invalid")


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
