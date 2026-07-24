# DCSMizzer Upstream Reference Extracts

This directory holds **extracted, git-tracked reference material** distilled from
the third-party clones under `.develope/upstream/`.

## What lives where

| Path | Content |
|------|---------|
| `aircraft/` | Plane/helicopter type IDs, class names, fuel/speed, pylon counts |
| `terrain/` | Theatre strings, map projections, airport indexes and coordinates |
| `mission/` | `.miz` structure, waypoint/start types, config writing patterns |
| `weapons/` | CLSID patterns and common AAM/AGM lookup samples |
| `data/` | Machine-readable JSON dumps (full indexes) |

## Source clones (not tracked)

`.develope/upstream/*` is **gitignored** (except `README.txt`). Clones keep their
own licenses and history. Do not redistributed upstream trees as DCSMizzer source.

Surveyed clones (2026-07-24):

| Project | Path | Status |
|---------|------|--------|
| [pydcs](https://github.com/pydcs/dcs) | `upstream/pydcs` | Cloned; primary source for units/terrain/weapons |
| [dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker) | `upstream/dcs-mission-maker` | Cloned; mission stubs + schema notes |
| [DCS Global Terrain Database](https://github.com/flying-dice/dcs-global-terrain-database) | `upstream/dcs-global-terrain-database` | Cloned; GeoJSON aerodrome model (Caucasus sample) |
| BriefingRoom for DCS | `upstream/briefing-room-for-dcs` | Clone timed out (network); re-clone later |
| DCS Retribution | `upstream/dcs-retribution` | Clone timed out; re-clone later |
| MOOSE | `upstream/MOOSE` | Clone timed out; re-clone later |

## License note

Extracted facts (IDs, coordinates, CLSID strings) are DCS/export data mediated by
upstream open-source projects. Narrative docs here are project notes for Agents.
Respect each upstream project's license when reading full source trees.

## Agent usage

Prefer `data/*.json` for exact lookups. Prefer the markdown guides for how to
write mission config and interpret coordinates. Never invent type IDs, CLSIDs,
or airport IDs — verify against these extracts or the live upstream clones.
