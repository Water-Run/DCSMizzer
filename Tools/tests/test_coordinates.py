from __future__ import annotations

import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcsmizzer.coordinates import (  # noqa: E402
    ProjectionFit,
    _fit_projection,
    _forward_unscaled,
    _checked_latlon_to_map,
    _latlon_to_map,
    _map_to_latlon,
    CoordinateSample,
    coordinate_report,
    geodesic_destination,
)
from dcsmizzer.cli import main  # noqa: E402


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
)


def synthetic_samples() -> list[CoordinateSample]:
    samples = []
    for index, (latitude, longitude) in enumerate(LOCATIONS, start=1):
        map_x, map_y = _latlon_to_map(latitude, longitude, KNOWN_FIT)
        samples.append(
            CoordinateSample(
                latitude=latitude,
                longitude=longitude,
                map_x=map_x,
                map_y=map_y,
                airdrome_id=index,
            )
        )
    return samples


class CoordinateConversionTests(unittest.TestCase):
    def test_projection_fit_recovers_synthetic_parameters(self) -> None:
        samples = synthetic_samples()
        fits = [_fit_projection(samples, meridian) for meridian in range(-177, 180, 6)]
        best = min(fits, key=lambda fit: fit.rms_error_m)

        self.assertEqual(best.central_meridian, 21)
        self.assertAlmostEqual(best.scale_factor, KNOWN_FIT.scale_factor, places=10)
        self.assertAlmostEqual(best.false_easting, KNOWN_FIT.false_easting, places=4)
        self.assertAlmostEqual(
            best.false_northing,
            KNOWN_FIT.false_northing,
            places=4,
        )
        self.assertLess(best.max_error_m, 0.001)

    def test_forward_and_inverse_round_trip(self) -> None:
        map_x, map_y = _latlon_to_map(52.52, 13.405, KNOWN_FIT)
        latitude, longitude = _map_to_latlon(map_x, map_y, KNOWN_FIT)

        self.assertAlmostEqual(latitude, 52.52, places=5)
        self.assertAlmostEqual(longitude, 13.405, places=5)

    def test_report_derives_projection_from_static_beacon_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            terrain = dcs_root / "Mods" / "terrains" / "SyntheticTerrain"
            terrain.mkdir(parents=True)
            blocks = []
            for index, sample in enumerate(synthetic_samples(), start=1):
                blocks.append(
                    """
                    {
                      display_name = _('Synthetic');
                      beaconId = 'airfield%s_0';
                      type = BEACON_TYPE_TACAN;
                      position = { %.9f, 50, %.9f };
                      positionGeo = { latitude = %.9f, longitude = %.9f };
                    };
                    """
                    % (
                        index,
                        sample.map_x,
                        sample.map_y,
                        sample.latitude,
                        sample.longitude,
                    )
                )
            (terrain / "beacons.lua").write_text(
                "beacons = {\n" + "\n".join(blocks) + "\n}\n",
                encoding="utf-8",
            )

            report = coordinate_report(
                dcs_root,
                "syntheticterrain",
                latitude=52.52,
                longitude=13.405,
            )
            stdout = io.StringIO()
            exit_code = main(
                [
                    "dcs-coordinates",
                    "--dcs-root",
                    str(dcs_root),
                    "--terrain",
                    "SyntheticTerrain",
                    "--latitude",
                    "52.52",
                    "--longitude",
                    "13.405",
                ],
                stdout=stdout,
            )
            cli_report = json.loads(stdout.getvalue())

        self.assertTrue(report["validation"]["validated"])
        self.assertEqual(report["model"]["central_meridian"], 21)
        self.assertLess(report["validation"]["max_error_m"], 0.01)
        self.assertLess(report["validation"]["inverse_max_error_m"], 0.01)
        self.assertLess(
            report["validation"]["leave_one_airfield_out_max_error_m"],
            0.01,
        )
        self.assertEqual(
            report["validation"]["leave_one_airfield_out_samples"],
            len(LOCATIONS),
        )
        self.assertIn("sample_domain", report)
        self.assertEqual(
            report["conversion"]["direction"],
            "WGS84_to_mission_local",
        )
        self.assertIn("support", report["conversion"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(cli_report["validation"]["validated"])

    def test_unscaled_projection_is_finite(self) -> None:
        northing, easting = _forward_unscaled(52.52, 13.405, 21)

        self.assertGreater(northing, 0)
        self.assertLess(easting, 0)

    def test_wgs84_geodesic_offset_and_antimeridian(self) -> None:
        one_degree_at_equator = 111_319.49079327357
        latitude, longitude, final_bearing = geodesic_destination(
            0.0,
            179.5,
            90.0,
            one_degree_at_equator,
        )

        self.assertAlmostEqual(latitude, 0.0, places=10)
        self.assertAlmostEqual(longitude, -179.5, places=9)
        self.assertAlmostEqual(final_bearing, 90.0, places=9)

    def test_projection_round_trip_normalizes_antimeridian(self) -> None:
        fit = ProjectionFit(
            central_meridian=177,
            scale_factor=0.9996,
            false_easting=500_000,
            false_northing=0,
            rms_error_m=0,
            max_error_m=0,
        )
        map_x, map_y = _latlon_to_map(10.0, -179.5, fit)
        latitude, longitude = _map_to_latlon(map_x, map_y, fit)

        self.assertAlmostEqual(latitude, 10.0, places=6)
        self.assertAlmostEqual(longitude, -179.5, places=6)

    def test_checked_projection_rejects_pole_and_far_meridian(self) -> None:
        with self.assertRaisesRegex(ValueError, "Transverse Mercator domain"):
            _checked_latlon_to_map(90.0, 21.0, KNOWN_FIT)
        with self.assertRaisesRegex(ValueError, "Transverse Mercator domain"):
            _checked_latlon_to_map(52.0, 100.0, KNOWN_FIT)

    def test_report_applies_bounded_geodesic_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            terrain = dcs_root / "Mods" / "terrains" / "SyntheticTerrain"
            terrain.mkdir(parents=True)
            blocks = []
            for index, sample in enumerate(synthetic_samples(), start=1):
                blocks.append(
                    """
                    {
                      beaconId = 'airfield%s_0';
                      position = { %.9f, 50, %.9f };
                      positionGeo = { latitude = %.9f, longitude = %.9f };
                    };
                    """
                    % (
                        index,
                        sample.map_x,
                        sample.map_y,
                        sample.latitude,
                        sample.longitude,
                    )
                )
            (terrain / "beacons.lua").write_text(
                "beacons = {\n" + "\n".join(blocks) + "\n}\n",
                encoding="utf-8",
            )
            report = coordinate_report(
                dcs_root,
                "SyntheticTerrain",
                latitude=52.52,
                longitude=13.405,
                offset_bearing_deg=270,
                offset_distance_m=100_000,
            )

        self.assertEqual(
            report["conversion"]["direction"],
            "WGS84_geodesic_offset_to_mission_local",
        )
        offset = report["conversion"]["geodesic_offset"]
        self.assertEqual(offset["distance_m"], 100_000)
        self.assertEqual(offset["initial_bearing_deg"], 270)
        self.assertTrue(math.isfinite(report["conversion"]["output"]["x"]))

    def test_report_rejects_partial_or_excessive_offset(self) -> None:
        with self.assertRaisesRegex(ValueError, "supplied together"):
            coordinate_report(
                Path("missing"),
                "missing",
                latitude=1,
                longitude=1,
                offset_bearing_deg=90,
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 20000000"):
            coordinate_report(
                Path("missing"),
                "missing",
                latitude=1,
                longitude=1,
                offset_bearing_deg=90,
                offset_distance_m=20_000_001,
            )

    def test_extreme_finite_beacon_positions_fail_cleanly_at_cli_boundary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dcs_root = Path(temp_dir)
            terrain = dcs_root / "Mods" / "terrains" / "ExtremeTerrain"
            terrain.mkdir(parents=True)
            blocks = []
            for index, (latitude, longitude) in enumerate(
                LOCATIONS[:3],
                start=1,
            ):
                sign = -1 if index % 2 else 1
                blocks.append(
                    """
                    {
                      display_name = _('Extreme');
                      beaconId = 'airfield%s_0';
                      type = BEACON_TYPE_TACAN;
                      position = { %se155, 50, %se155 };
                      positionGeo = { latitude = %.9f, longitude = %.9f };
                    };
                    """
                    % (
                        index,
                        sign,
                        -sign,
                        latitude,
                        longitude,
                    )
                )
            (terrain / "beacons.lua").write_text(
                "beacons = {\n" + "\n".join(blocks) + "\n}\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                [
                    "dcs-coordinates",
                    "--dcs-root",
                    str(dcs_root),
                    "--terrain",
                    "ExtremeTerrain",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("finite candidate fits", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
