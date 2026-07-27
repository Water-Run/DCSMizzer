# DCSMizzer development reference (`.develope/reference`)

**This directory is development-only.** Final Agent product docs belong in `Docs/`
(not here).

The files in `data/` are **legacy frozen survey snapshots, not current DCS
truth**. Their original one-off extractors are unavailable. Every file is now
bound to a source project, source path, frozen commit, byte count, and SHA-256
in [`provenance.json`](provenance.json); those source paths have been checked
against the recorded commits. Use the current installation and upstream survey
baselines under `../survey/baselines/` when deciding whether a fact is current.

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
| `data/` | Frozen legacy machine-readable indexes; never implicit current truth |
| `provenance.json` | File-by-file frozen-commit provenance and validation |

## Upstream clones (gitignored)

`.develope/upstream/*` except `README.txt`. All six ACK projects cloned:

pydcs · dcs-mission-maker · dcs-global-terrain-database · briefing-room-for-dcs · dcs-retribution · MOOSE

## Frozen snapshot counts

These counts describe only the legacy files recorded in `provenance.json`.
They are retained to explain the old survey, not to claim current coverage.

| Legacy dataset | Frozen count |
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

See [`terrain/theatre-coverage.md`](terrain/theatre-coverage.md) for the frozen
comparison. Do not infer current installed-map or upstream coverage from it.

## Agent rules

1. Verify exact current identifiers against the recorded DCS installation
   source or a version-matched runtime export; do not invent them.
2. Treat pydcs, BriefingRoom, Retribution, MOOSE, GTD, and mission-maker as
   commit-bound reference evidence, never as the current local authority.
3. Treat `data/` as frozen legacy evidence only.
4. Do not copy upstream code into product paths; extract facts only.
5. Product-facing docs go to `Docs/` only after all survey gates admit them.
