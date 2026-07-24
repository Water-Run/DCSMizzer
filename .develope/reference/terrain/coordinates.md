# Coordinates and map projection

## Two coordinate systems you will see

### 1. DCS mission map coordinates (`x`, `y`) — **authoritative in `.miz`**

- Used in unit positions, waypoints, zones, bullseye.
- **`x` points north**, **`y` points east** (mission-maker schema comments;
  pydcs `Point(x, y)` matches this).
- Units are **meters** in the theatre-local projected plane.
- Origin and axis offsets differ per map (Transverse Mercator parameters).

### 2. Geographic lat/lon

- Converted via each theatre's Transverse Mercator projection
  (`pydcs/dcs/terrain/<map>/projection.py`).
- pydcs API: `Point.latlng()` / `Point.from_latlng(LatLng, terrain)`.
- Global Terrain Database GeoJSON for Caucasus stores **lon, lat, elev** in
  `geometry.coordinates`, plus DCS-style `properties.point` as
  `{x, y: elev, z}` where **z is easting** (note axis naming differs from miz `y`).

## Projection parameters (Transverse Mercator)

| theatre package | central_meridian (°) | false_easting | false_northing | scale |
|-----------------|----------------------|---------------|----------------|-------|
| `caucasus` | 33.0 | -99516.9999999732 | -4998114.999999984 | 0.9996 |
| `falklands` | -57.0 | 147639.99999997593 | 5815417.000000032 | 0.9996 |
| `germany` | 21.0 | 35427.619999985734 | -6061633.128000011 | 0.9996 |
| `kola` | 21.0 | -62702.00000000087 | -7543624.999999979 | 0.9996 |
| `marianaislands` | 147.0 | 238417.99999989968 | -1491840.000000048 | 0.9996 |
| `nevada` | -117.0 | -193996.80999964548 | -4410028.063999966 | 0.9996 |
| `normandy` | -3.0 | -195526.00000000204 | -5484812.999999951 | 0.9996 |
| `persiangulf` | 57.0 | 75755.99999999645 | -2894933.0000000377 | 0.9996 |
| `sinai` | 33.0 | 169221.9999999585 | -3325312.9999999693 | 0.9996 |
| `syria` | 39.0 | 282801.00000003993 | -3879865.9999999935 | 0.9996 |
| `thechannel` | 3.0 | 99376.00000000288 | -5636889.00000001 | 0.9996 |

## Practical conversion notes

1. Never paste WGS84 lat/lon into mission `x`/`y` fields.
2. When moving a scenario between maps, re-resolve airports and regenerate points.
3. Airport positions in pydcs are already in map meters — use them as anchors.
4. Distances in pydcs helpers (`point_from_heading`, `_distance`) use meters.
5. Heading: 0° is **north**, increasing clockwise in geographic sense used by
   `point_from_heading` (math: cos/sin on heading degrees).

## Example: East Berlin Soviet CAP (Cold War Germany)

Suggested Soviet-side fields near East Berlin (from pydcs `germany/airports.py`):

| id | name | x | y | parking |
|----|------|---|---|---------|
| 31 | Werneuchen | -205735.96 | -453635.45 | 95 |
| 12 | Finow | -183543.06 | -456471.53 | 135 |
| 49 | Oranienburg | -191502.89 | -489781.80 | 81 |
| 29 | Tempelhof | -221028.27 | -480137.52 | 39 |
| 26 | Schonefeld | -231590.28 | -472324.47 | 66 |
| 101 | Sperenberg | -257400.23 | -490766.81 | 78 |

Use `airdromeId` = airport `id` in takeoff/landing waypoints.
