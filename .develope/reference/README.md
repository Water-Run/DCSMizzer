# DCSMizzer development reference (`.develope/reference`)

**This directory is development-only.** Final Agent product docs belong in `Docs/`
(not here). Everything below is extracted from ignored upstream clones for
mapping DCS types, coordinates, mission config, and era data.

## Layout

| Path | Content |
|------|---------|
| `aircraft/` | Plane/heli type ids, fuel/speed, flying-unit config writing |
| `units/` | Vehicles, ships, statics, countries, ground config, era lists |
| `terrain/` | Theatre matrix, projections, airports (pydcs + BR extras) |
| `mission/` | `.miz` structure, waypoints, tasks |
| `weather/` | Cloud presets + BR weather INI |
| `payloads/` | Retribution customized loadouts |
| `weapons/` | AAM / AGM-bomb CLSIDs, weapons-by-decade |
| `upstream/` | BriefingRoom, Retribution, MOOSE, GTD, mission-maker notes |
| `data/` | Machine-readable JSON indexes |

## Upstream clones (gitignored)

`.develope/upstream/*` except `README.txt`. All six ACK projects cloned:

pydcs · dcs-mission-maker · dcs-global-terrain-database · briefing-room-for-dcs · dcs-retribution · MOOSE

## Snapshot counts

| Dataset | Count |
|---------|------:|
| Planes (pydcs) | 143 |
| Helicopters | 26 |
| Vehicles | 350 |
| Ships | 57 |
| Statics | 263 |
| Countries | 92 |
| Weapons all | 2024 |
| Weapons AAM curated | 215 |
| Weapons AGM/bomb curated | 564 |
| pydcs airports (all maps) | sum of airports-by-theatre |
| BR airbases | 802 |
| BR situations | 110 |
| Retribution customized payloads | 224 |
| Retribution factions | 131 |
| Cloud presets | 30 |

## Coordinate cheat-sheet

| Context | North | East | Alt |
|---------|-------|------|-----|
| `.miz` unit / WP | `x` | `y` | `alt` |
| pydcs `Point` | `x` | `y` | — |
| DCS / MOOSE / BR Vec3 | `x` | `z` | `y` |

Never paste WGS84 into mission `x`/`y`. Join airports by **numeric id** across sources.

## Theatre coverage

See [`terrain/theatre-coverage.md`](terrain/theatre-coverage.md).  
BR/Retribution add **Iraq**, **Afghanistan** (and BR **MarianaIslandsWWII**) beyond current pydcs packages.

## Agent rules

1. Look up types/CLSIDs/airports here or in upstream — do not invent.
2. Prefer pydcs for unit/weapon fidelity; BR for multi-map airbase+latlon; Retribution for loadout presets & faction TO&E.
3. Do not copy upstream code into product paths; extract facts only.
4. Product-facing docs go to `Docs/` when generation tooling is ready — not this tree.
