# Upstream reference extract log (2026-07-24)

## Goal

Pull acknowledged upstream projects into `.develope/upstream` (gitignored),
read their data models, and write **git-tracked** distilled references under
`.develope/reference/` for Agents (types, coordinates, config writing, weapons).

## Clone status

| Project | Result |
|---------|--------|
| pydcs | OK (primary) |
| dcs-mission-maker | OK |
| dcs-global-terrain-database | OK (Caucasus-focused data in-tree) |
| briefing-room-for-dcs | Network timeout — retry later |
| dcs-retribution | Network timeout — retry later |
| MOOSE | Network timeout — retry later |

## Outputs

- `.develope/reference/**` — human docs + `data/*.json` indexes
- Airport coverage: 11 theatres, 744 airports total in pydcs export
- Planes: 143 types; Helicopters: 26; Weapons entries: 2024

## Intentionally not committed

- Entire upstream git clones (`.gitignore`: `.develope/upstream/*` except README)
- Official campaign binaries under `.develope/official-campaigns/*`
