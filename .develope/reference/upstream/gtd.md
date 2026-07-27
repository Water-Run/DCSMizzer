> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# DCS Global Terrain Database — extract

Source: `dcs-global-terrain-database` (in-repo data is **Caucasus-focused**).

## Feature model

GeoJSON FeatureCollection properties:

| type | meaning |
|------|---------|
| TERRAIN | map bounds feature |
| AIRBASE | airbase point |
| PARKING | parking slot |
| BEACON | navaid |

Coordinates in `geometry.coordinates` are typically **lon, lat, elev**.  
`properties.point` uses DCS-style `{x, y:elev, z:east}`.

## Caucasus counts

- Airbases: **21**
- Beacons: **164**
- Parking features: 942 (in combined terrain file)

Data:

- [`../data/gtd-caucasus-airbases.json`](../data/gtd-caucasus-airbases.json)
- [`../data/gtd-caucasus-beacons.json`](../data/gtd-caucasus-beacons.json)

## Export tooling (upstream)

- `exporters/get-airbases.lua` / `get-terrain.lua` — run inside DCS to dump more maps
- `scripts/schemas.js` / `geojson.schema.json` — validation

## Agent takeaway

GTD is best for **geo analysis / lat-lon** on Caucasus. Prefer pydcs/BriefingRoom for multi-theatre airport ids used in miz generation.
