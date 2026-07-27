"""Derive and validate terrain coordinate conversion from installed beacons."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dcs_static import _load_airfield_beacons


WGS84_A = 6_378_137.0
WGS84_E2 = 0.0066943799901413165
WGS84_EP2 = WGS84_E2 / (1.0 - WGS84_E2)
UTM_CENTRAL_MERIDIANS = tuple(range(-177, 180, 6))


@dataclass(frozen=True)
class CoordinateSample:
    latitude: float
    longitude: float
    map_x: float
    map_y: float
    airdrome_id: int


@dataclass(frozen=True)
class ProjectionFit:
    central_meridian: int
    scale_factor: float
    false_easting: float
    false_northing: float
    rms_error_m: float
    max_error_m: float


def coordinate_report(
    dcs_root: Path,
    terrain: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    map_x: float | None = None,
    map_y: float | None = None,
) -> dict[str, Any]:
    """Return a fitted projection and optional forward/inverse conversion."""

    forward_requested = latitude is not None or longitude is not None
    inverse_requested = map_x is not None or map_y is not None
    if forward_requested and inverse_requested:
        raise ValueError("choose either latitude/longitude or x/y")
    if forward_requested and (latitude is None or longitude is None):
        raise ValueError("latitude and longitude must be supplied together")
    if inverse_requested and (map_x is None or map_y is None):
        raise ValueError("x and y must be supplied together")
    for name, value in (
        ("latitude", latitude),
        ("longitude", longitude),
        ("x", map_x),
        ("y", map_y),
    ):
        if value is not None and _finite_float(value) is None:
            raise ValueError(f"{name} must be finite")
    if latitude is not None and not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if longitude is not None and not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")

    selected, beacon_path, records, malformed = _load_airfield_beacons(
        dcs_root,
        terrain,
    )
    samples = _coordinate_samples(records)
    if len(samples) < 3:
        raise ValueError("terrain has too few static beacon coordinate pairs")
    fits: list[ProjectionFit] = []
    for meridian in UTM_CENTRAL_MERIDIANS:
        try:
            candidate = _fit_projection(samples, meridian)
        except (ArithmeticError, ValueError):
            continue
        if _projection_fit_is_finite(candidate):
            fits.append(candidate)
    fits.sort(key=lambda fit: (fit.rms_error_m, fit.max_error_m))
    if len(fits) < 2:
        raise ValueError("terrain projection has too few finite candidate fits")
    fit = fits[0]
    try:
        inverse_errors = _inverse_errors(samples, fit)
        inverse_rms_error = math.sqrt(
            sum(error**2 for error in inverse_errors) / len(inverse_errors)
        )
        inverse_max_error = max(inverse_errors)
    except (ArithmeticError, ValueError) as error:
        raise ValueError(
            "terrain projection inverse validation is outside the supported "
            "numeric range"
        ) from error
    if (
        not math.isfinite(inverse_rms_error)
        or not math.isfinite(inverse_max_error)
        or not 0.99 <= fit.scale_factor <= 1.01
        or fit.max_error_m > 25.0
        or inverse_max_error > 25.0
    ):
        raise ValueError("terrain projection could not be validated within 25 metres")

    conversion: dict[str, Any] | None = None
    if latitude is not None and longitude is not None:
        converted_x, converted_y = _checked_latlon_to_map(
            latitude,
            longitude,
            fit,
        )
        conversion = {
            "direction": "WGS84_to_mission_local",
            "input": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "output": {
                "x": converted_x,
                "y": converted_y,
            },
        }
    elif map_x is not None and map_y is not None:
        converted_latitude, converted_longitude = _checked_map_to_latlon(
            map_x,
            map_y,
            fit,
        )
        conversion = {
            "direction": "mission_local_to_WGS84",
            "input": {
                "x": map_x,
                "y": map_y,
            },
            "output": {
                "latitude": converted_latitude,
                "longitude": converted_longitude,
            },
        }

    return {
        "schema": "dcsmizzer.dcs-coordinate-conversion/v1",
        "authority": "derived_current_install_static_beacon_pairs",
        "dcs_started": False,
        "terrain_directory": selected.name,
        "source": beacon_path.relative_to(dcs_root).as_posix(),
        "source_sha256": _sha256(beacon_path),
        "model": {
            "name": "WGS84 Transverse Mercator",
            "central_meridian": fit.central_meridian,
            "scale_factor": fit.scale_factor,
            "false_easting": fit.false_easting,
            "false_northing": fit.false_northing,
            "axis_mapping": {
                "mission_x": "projected_northing",
                "mission_y": "projected_easting",
            },
        },
        "validation": {
            "validated": True,
            "coordinate_pairs": len(samples),
            "airfields": len({sample.airdrome_id for sample in samples}),
            "malformed_airfield_blocks": malformed,
            "rms_error_m": fit.rms_error_m,
            "max_error_m": fit.max_error_m,
            "inverse_rms_error_m": inverse_rms_error,
            "inverse_max_error_m": inverse_max_error,
            "next_candidate_rms_error_m": fits[1].rms_error_m,
        },
        "conversion": conversion,
        "limitations": [
            "The transform is independently fitted to current installed "
            "static beacon coordinate pairs.",
            "A converted point is not proof of terrain height, land cover, "
            "airport center, runway, parking, or unit placement validity.",
            "The caller must cite an authoritative WGS84 source for any "
            "requested real-world location.",
            "No DCS or Mission Editor process was started.",
        ],
    }


def _coordinate_samples(
    records: dict[int, dict[str, Any]],
) -> list[CoordinateSample]:
    samples: set[CoordinateSample] = set()
    for airdrome_id, record in records.items():
        for beacon in record["beacons"]:
            map_position = beacon.get("map_position")
            geo_position = beacon.get("geo_position")
            if not isinstance(map_position, dict) or not isinstance(
                geo_position,
                dict,
            ):
                continue
            values = tuple(
                _finite_float(value)
                for value in (
                    geo_position.get("latitude"),
                    geo_position.get("longitude"),
                    map_position.get("x"),
                    map_position.get("z"),
                )
            )
            if any(value is None for value in values):
                continue
            samples.add(
                CoordinateSample(
                    latitude=float(values[0]),
                    longitude=float(values[1]),
                    map_x=float(values[2]),
                    map_y=float(values[3]),
                    airdrome_id=airdrome_id,
                )
            )
    return sorted(
        samples,
        key=lambda item: (
            item.airdrome_id,
            item.latitude,
            item.longitude,
            item.map_x,
            item.map_y,
        ),
    )


def _fit_projection(
    samples: list[CoordinateSample],
    central_meridian: int,
) -> ProjectionFit:
    projected = [
        _forward_unscaled(
            sample.latitude,
            sample.longitude,
            central_meridian,
        )
        for sample in samples
    ]
    mean_northing = sum(item[0] for item in projected) / len(projected)
    mean_easting = sum(item[1] for item in projected) / len(projected)
    mean_x = sum(sample.map_x for sample in samples) / len(samples)
    mean_y = sum(sample.map_y for sample in samples) / len(samples)
    numerator = 0.0
    denominator = 0.0
    for sample, (northing, easting) in zip(
        samples,
        projected,
        strict=True,
    ):
        centered_northing = northing - mean_northing
        centered_easting = easting - mean_easting
        numerator += centered_northing * (sample.map_x - mean_x)
        numerator += centered_easting * (sample.map_y - mean_y)
        denominator += centered_northing**2 + centered_easting**2
    if denominator == 0.0:
        raise ValueError("beacon coordinate pairs are degenerate")
    scale_factor = numerator / denominator
    false_northing = mean_x - scale_factor * mean_northing
    false_easting = mean_y - scale_factor * mean_easting
    errors = []
    for sample, (northing, easting) in zip(
        samples,
        projected,
        strict=True,
    ):
        predicted_x = scale_factor * northing + false_northing
        predicted_y = scale_factor * easting + false_easting
        errors.append(
            math.hypot(
                predicted_x - sample.map_x,
                predicted_y - sample.map_y,
            )
        )
    return ProjectionFit(
        central_meridian=central_meridian,
        scale_factor=scale_factor,
        false_easting=false_easting,
        false_northing=false_northing,
        rms_error_m=math.sqrt(sum(error**2 for error in errors) / len(errors)),
        max_error_m=max(errors),
    )


def _latlon_to_map(
    latitude: float,
    longitude: float,
    fit: ProjectionFit,
) -> tuple[float, float]:
    northing, easting = _forward_unscaled(
        latitude,
        longitude,
        fit.central_meridian,
    )
    return (
        fit.scale_factor * northing + fit.false_northing,
        fit.scale_factor * easting + fit.false_easting,
    )


def _checked_latlon_to_map(
    latitude: float,
    longitude: float,
    fit: ProjectionFit,
) -> tuple[float, float]:
    try:
        map_x, map_y = _latlon_to_map(latitude, longitude, fit)
    except ArithmeticError as error:
        raise ValueError(
            "coordinate conversion is outside the supported numeric range"
        ) from error
    if not math.isfinite(map_x) or not math.isfinite(map_y):
        raise ValueError("coordinate conversion is outside the supported numeric range")
    return map_x, map_y


def _inverse_errors(
    samples: list[CoordinateSample],
    fit: ProjectionFit,
) -> list[float]:
    return [
        _surface_distance_m(
            sample.latitude,
            sample.longitude,
            *_map_to_latlon(sample.map_x, sample.map_y, fit),
        )
        for sample in samples
    ]


def _projection_fit_is_finite(fit: ProjectionFit) -> bool:
    return all(
        math.isfinite(value)
        for value in (
            fit.scale_factor,
            fit.false_easting,
            fit.false_northing,
            fit.rms_error_m,
            fit.max_error_m,
        )
    )


def _map_to_latlon(
    map_x: float,
    map_y: float,
    fit: ProjectionFit,
) -> tuple[float, float]:
    northing = (map_x - fit.false_northing) / fit.scale_factor
    easting = (map_y - fit.false_easting) / fit.scale_factor
    return _inverse_unscaled(
        northing,
        easting,
        fit.central_meridian,
    )


def _checked_map_to_latlon(
    map_x: float,
    map_y: float,
    fit: ProjectionFit,
) -> tuple[float, float]:
    try:
        latitude, longitude = _map_to_latlon(map_x, map_y, fit)
    except ArithmeticError as error:
        raise ValueError(
            "coordinate conversion is outside the supported numeric range"
        ) from error
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("coordinate conversion is outside the supported numeric range")
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        raise ValueError(
            "coordinate conversion is outside the supported geographic range"
        )
    return latitude, longitude


def _surface_distance_m(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    first_phi = math.radians(first_latitude)
    second_phi = math.radians(second_latitude)
    delta_phi = second_phi - first_phi
    delta_lambda = math.radians(second_longitude - first_longitude)
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(first_phi) * math.cos(second_phi) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * WGS84_A * math.asin(min(1.0, math.sqrt(haversine)))


def _forward_unscaled(
    latitude: float,
    longitude: float,
    central_meridian: float,
) -> tuple[float, float]:
    phi = math.radians(latitude)
    delta_lambda = math.radians(
        ((longitude - central_meridian + 180.0) % 360.0) - 180.0
    )
    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_phi**2)
    t = tan_phi**2
    c = WGS84_EP2 * cos_phi**2
    a_term = cos_phi * delta_lambda
    meridional_arc = _meridional_arc(phi)
    easting = n * (
        a_term
        + (1.0 - t + c) * a_term**3 / 6.0
        + (5.0 - 18.0 * t + t**2 + 72.0 * c - 58.0 * WGS84_EP2) * a_term**5 / 120.0
    )
    northing = meridional_arc + n * tan_phi * (
        a_term**2 / 2.0
        + (5.0 - t + 9.0 * c + 4.0 * c**2) * a_term**4 / 24.0
        + (61.0 - 58.0 * t + t**2 + 600.0 * c - 330.0 * WGS84_EP2) * a_term**6 / 720.0
    )
    return northing, easting


def _inverse_unscaled(
    northing: float,
    easting: float,
    central_meridian: float,
) -> tuple[float, float]:
    e4 = WGS84_E2**2
    e6 = WGS84_E2**3
    mu = northing / (
        WGS84_A * (1.0 - WGS84_E2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0)
    )
    root = math.sqrt(1.0 - WGS84_E2)
    e1 = (1.0 - root) / (1.0 + root)
    footprint = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu)
        + 151.0 * e1**3 / 96.0 * math.sin(6.0 * mu)
        + 1097.0 * e1**4 / 512.0 * math.sin(8.0 * mu)
    )
    sin_footprint = math.sin(footprint)
    cos_footprint = math.cos(footprint)
    tan_footprint = math.tan(footprint)
    c1 = WGS84_EP2 * cos_footprint**2
    t1 = tan_footprint**2
    n1 = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_footprint**2)
    r1 = WGS84_A * (1.0 - WGS84_E2) / (1.0 - WGS84_E2 * sin_footprint**2) ** 1.5
    d = easting / n1
    latitude = footprint - (n1 * tan_footprint / r1) * (
        d**2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * WGS84_EP2) * d**4 / 24.0
        + (
            61.0
            + 90.0 * t1
            + 298.0 * c1
            + 45.0 * t1**2
            - 252.0 * WGS84_EP2
            - 3.0 * c1**2
        )
        * d**6
        / 720.0
    )
    longitude_delta = (
        d
        - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1**2 + 8.0 * WGS84_EP2 + 24.0 * t1**2)
        * d**5
        / 120.0
    ) / cos_footprint
    latitude_degrees = math.degrees(latitude)
    longitude_degrees = central_meridian + math.degrees(longitude_delta)
    step = 1e-6
    for _iteration in range(5):
        current_northing, current_easting = _forward_unscaled(
            latitude_degrees,
            longitude_degrees,
            central_meridian,
        )
        northing_error = current_northing - northing
        easting_error = current_easting - easting
        if math.hypot(northing_error, easting_error) < 1e-6:
            break
        north_plus, east_plus = _forward_unscaled(
            latitude_degrees + step,
            longitude_degrees,
            central_meridian,
        )
        north_minus, east_minus = _forward_unscaled(
            latitude_degrees - step,
            longitude_degrees,
            central_meridian,
        )
        north_lon_plus, east_lon_plus = _forward_unscaled(
            latitude_degrees,
            longitude_degrees + step,
            central_meridian,
        )
        north_lon_minus, east_lon_minus = _forward_unscaled(
            latitude_degrees,
            longitude_degrees - step,
            central_meridian,
        )
        north_by_lat = (north_plus - north_minus) / (2.0 * step)
        east_by_lat = (east_plus - east_minus) / (2.0 * step)
        north_by_lon = (north_lon_plus - north_lon_minus) / (2.0 * step)
        east_by_lon = (east_lon_plus - east_lon_minus) / (2.0 * step)
        determinant = north_by_lat * east_by_lon - north_by_lon * east_by_lat
        if abs(determinant) < 1e-12:
            raise ValueError("terrain projection inverse is degenerate")
        latitude_degrees -= (
            northing_error * east_by_lon - easting_error * north_by_lon
        ) / determinant
        longitude_degrees -= (
            north_by_lat * easting_error - east_by_lat * northing_error
        ) / determinant
    return latitude_degrees, longitude_degrees


def _meridional_arc(phi: float) -> float:
    e4 = WGS84_E2**2
    e6 = WGS84_E2**3
    return WGS84_A * (
        (1.0 - WGS84_E2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0) * phi
        - (3.0 * WGS84_E2 / 8.0 + 3.0 * e4 / 32.0 + 45.0 * e6 / 1024.0)
        * math.sin(2.0 * phi)
        + (15.0 * e4 / 256.0 + 45.0 * e6 / 1024.0) * math.sin(4.0 * phi)
        - 35.0 * e6 / 3072.0 * math.sin(6.0 * phi)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _finite_float(value: Any) -> float | None:
    if not _is_number(value):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if math.isfinite(converted) else None
