# Upstream reference extract log (2026-07-24)

> Historical survey: figures, upstream commits, and capability status are superseded by the reproducible 2026-07-27 baselines; this file remains as a method and decision record.

## Goal

Complete surveying of six acknowledged upstream projects; write **git-tracked**
distilled references only under `.develope/reference/` and `.develope/survey/`.
**Do not write product Docs/** (reserved for final Agent-facing deliverables).

## Clones

All under `.develope/upstream/` (ignored):

| Project | Status |
|---------|--------|
| pydcs | OK |
| dcs-mission-maker | OK |
| dcs-global-terrain-database | OK (Caucasus data in-tree) |
| briefing-room-for-dcs | OK |
| dcs-retribution | OK (payloads in `customized_payloads/`) |
| MOOSE | OK |

## Major extract batches

1. **pydcs core** — planes, helis, vehicles, ships, statics, countries, weapons, airports, projections, mission/waypoint notes
2. **BriefingRoom** — theatres, 802 airbases, weather INI, default unit lists by decade, situations, unit DB, weapons-by-date, terrain bounds, Iraq/Afghanistan airports
3. **Retribution** — factions, flightplan types, climate yaml, 224 customized payload files (priority loadouts expanded)
4. **MOOSE** — COORDINATE API, module map, Vec3 vs miz y
5. **GTD** — Caucasus airbases/beacons GeoJSON model
6. **mission-maker** — stubs, ME_DB plane keys, callnames

## Verification notes

- MiG-29A CAP preset includes R-27R `{9B25D316-…}` and R-73 `{FBC29BFE-…}`
- Tempelhof id=29 matches pydcs and BriefingRoom
- AAM doc excludes cluster bombs
- Theatre matrix: BR-only Afghanistan, Iraq, MarianaIslandsWWII vs pydcs packages

## Not committed

- Upstream full trees (gitignored)
- Official campaigns under `.develope/official-campaigns/*`
- Empty `Docs/` product tree (intentionally untouched)

## Reproducible verification

```bash
python3 .develope/survey/verify_reference_extracts.py
```

Compares extracts under `.develope/reference/data` to local `.develope/upstream/pydcs` source.
