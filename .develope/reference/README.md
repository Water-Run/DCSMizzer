# DCSMizzer Upstream Reference Extracts

This directory holds **extracted, git-tracked reference material** distilled from
the third-party clones under `.develope/upstream/`.

## What lives where

| Path | Content |
|------|---------|
| `aircraft/` | Plane/helicopter type IDs, fuel/speed, pylon counts, unit config writing |
| `units/` | Ground vehicles, ships, statics, countries |
| `terrain/` | Theatre strings, projections, airport tables (map meters) |
| `mission/` | `.miz` structure, waypoints/start types, tasks |
| `weapons/` | CLSID indexes (AAM curated + full dump) |
| `upstream/` | Patterns from BriefingRoom, Retribution, MOOSE |
| `data/` | Machine-readable JSON dumps |

## Source clones (not tracked)

`.develope/upstream/*` is **gitignored** (except `README.txt`). Clones keep their
own licenses and history. Do not redistribute upstream trees as DCSMizzer source.

| Project | Path | Survey status |
|---------|------|---------------|
| [pydcs](https://github.com/pydcs/dcs) | `upstream/pydcs` | Primary unit/terrain/weapon DB |
| [dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker) | `upstream/dcs-mission-maker` | Miz stubs + Zod schemas |
| [DCS Global Terrain Database](https://github.com/flying-dice/dcs-global-terrain-database) | `upstream/dcs-global-terrain-database` | GeoJSON (Caucasus in-tree) |
| [BriefingRoom for DCS](https://github.com/DCS-BR-Tools/briefing-room-for-dcs) | `upstream/briefing-room-for-dcs` | Theatres, 802 airbases, situations |
| [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution) | `upstream/dcs-retribution` | Factions, flight plans, climate |
| [MOOSE](https://github.com/FlightControl-Master/MOOSE) | `upstream/MOOSE` | Runtime coords + module map |

## Counts (pydcs export snapshot)

| Dataset | Count |
|---------|-------|
| Planes | 143 |
| Helicopters | 26 |
| Vehicles | 350 |
| Ships | 57 |
| Statics | 263 |
| Countries | 92 |
| Weapons (all) | 2024 |
| Airports (11 theatres in pydcs) | 744 |
| BR airbases (14 theatres) | 802 |

## Coordinate cheat-sheet

| Context | North | East | Alt |
|---------|-------|------|-----|
| `.miz` unit / waypoint | `x` | `y` | `alt` |
| pydcs `Point` | `x` | `y` | — |
| DCS/MOOSE/BR Vec3 | `x` | `z` | `y` |

Never paste WGS84 lat/lon into mission `x`/`y`.

## Agent usage

1. Prefer `data/*.json` for exact lookups.
2. Prefer markdown guides for config shape and theatre strings.
3. Never invent type IDs, CLSIDs, or airport IDs — verify here or in upstream clones.
4. Upstream narrative docs in `upstream/` are patterns, not license to copy code wholesale.

## License note

Extracted facts (IDs, coordinates, CLSID strings) are DCS/export data mediated by
upstream open-source projects. Narrative docs here are project notes for Agents.
Respect each upstream project's license when reading full source trees.
