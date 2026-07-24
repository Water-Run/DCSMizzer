# Upstream reference extract log (2026-07-24)

## Goal

Pull acknowledged upstream projects into `.develope/upstream` (gitignored),
read their data models, and write **git-tracked** distilled references under
`.develope/reference/` for Agents (types, coordinates, config writing, weapons,
factions, runtime patterns).

## Clone status (final)

| Project | Result |
|---------|--------|
| pydcs | OK |
| dcs-mission-maker | OK |
| dcs-global-terrain-database | OK |
| briefing-room-for-dcs | OK (~401M shallow) |
| dcs-retribution | OK (~265M shallow) |
| MOOSE | OK (~71M shallow, partial blob filter) |

## Tracked outputs

### pydcs-derived

- `reference/aircraft/*` — planes, helicopters, config writing
- `reference/units/*` — vehicles (350), ships (57), statics (263), countries (92)
- `reference/terrain/*` — theatres, projections, 11 airport tables
- `reference/mission/*` — miz structure, waypoints, tasks
- `reference/weapons/clsid-common-aam.md` — **AAM-only** curated CLSID list
- `reference/data/*.json` — machine indexes including vehicles/ships/statics/countries/weapons

### third-party patterns

- `reference/upstream/briefing-room.md` + `data/briefing-room-*.json`
- `reference/upstream/retribution.md` + faction/theater indexes
- `reference/upstream/moose.md` — COORDINATE API + module map

## Verification (spot-check vs pydcs source)

Script evidence: `/tmp/grok-goal-47e6a9fc77b8/implementer/verify-reference.txt`

Checks include:

- Plane ids/fuel for MiG-29A, JF-17, M-2000C, F-16C_50, FA-18C_hornet, Su-25T
- Germany Tempelhof / Finow airport ids and coordinates
- Vehicle count 350; ship Speedboat/VINSON field isolation
- Country Russia id 0
- AAM doc excludes AB cluster bombs; includes R-27R / AIM-9M
- R-27R CLSID present in weapons-index and source
- BriefingRoom Tempelhof id 29 (+ lat/lon); note ~100m reference-point delta vs pydcs airport position

## Intentionally not committed

- Entire upstream git clones (`.gitignore`: `.develope/upstream/*` except README)
- Official campaign binaries under `.develope/official-campaigns/*`
