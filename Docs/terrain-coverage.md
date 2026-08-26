# Terrain coverage routing

This is a compact mission-theatre selection aid, not a count of every DCS map
product or region. The dated official survey currently records 18 product
cards that resolve to 14 unique `mission.theatre` identities because regional,
entitlement, and legacy products can share an identity. Query
`terrain-catalog` for that product-to-theatre relationship. Exact output, Git
provenance, parse status, and conflicts from `terrain-coverage` remain
authoritative for a build.

## Query gate

- User named a map: call `terrain-coverage` with `--terrain`; never load the
  complete identity graph into model context.
- User did not name a map: use the compact default catalog, select one exact
  DCS theatre ID without limiting choices to installed maps, then rerun with
  `--terrain`.
- Request detailed source records only when current `<command> --help` exposes
  the corresponding option, and redirect them to a work file.

## Recorded clean-snapshot matrix

At the recorded sources, BriefingRoom supplies airbase/local-point records for
all 14 unique current theatre IDs represented by that snapshot. Eleven rows
have a pydcs terrain projection; two more have a lower-authority projection
derived from the commit-bound BriefingRoom airbase export. The counts below
are source records, not current-install, physical-terrain, product-ownership,
or runtime proof.

| DCS theatre ID | BR airbases | pydcs airports | Coordinate status |
|---|---:|---:|---|
| `Afghanistan` | 29 | — | BR local planning points; derived conversion fails closed |
| `Caucasus` | 21 | 21 | pydcs projection |
| `Falklands` | 27 | 26 | pydcs projection |
| `GermanyCW` | 227 | 227 | pydcs projection |
| `Iraq` | 20 | — | derived commit-bound BR airbase-export projection |
| `Kola` | 37 | 37 | pydcs projection |
| `MarianaIslands` | 8 | 8 | pydcs projection |
| `MarianaIslandsWWII` | 11 | — | derived commit-bound BR airbase-export projection |
| `Nevada` | 17 | 17 | pydcs projection |
| `Normandy` | 82 | 89 | pydcs projection |
| `PersianGulf` | 30 | 29 | pydcs projection |
| `SinaiMap` | 56 | 55 | pydcs projection declares `Sinai`; identity conflict |
| `Syria` | 225 | 224 | pydcs projection |
| `TheChannel` | 12 | 12 | pydcs projection |

The recorded pydcs commit has no matching packages for `Afghanistan`, `Iraq`,
or `MarianaIslandsWWII`. `Iraq` and `MarianaIslandsWWII` have passed the
derived BriefingRoom airbase-export projection gate. Require the report
authority
`derived_commit_bound_br_airbase_export_projection`, its commit provenance,
`decision_source_binding.all_required_sources_bound_to_head=true`, and a
successful exact conversion before use; this remains lower authority than a
version-matched installed fit. The product route is `br-coordinates`; run
current `br-coordinates --help` for the exact interface.

`Afghanistan` fails closed: conversion remains `null`, and the report exposes
duplicate placeholder candidates for airdrome IDs 26, 27, and 28. Do not pick a
candidate, borrow another terrain's transform, or suppress that conflict.
Author only already-local BR points or leave geographic conversion unresolved.

BriefingRoom `x/y`, bounds, sea masks, and spawn points are planning evidence.
They do not prove WGS-84 conversion, terrain height, surface, collision, road
access, parking clearance, or tactical safety. A pydcs or derived BR
projection is commit-bound generated evidence, not a fit against an
uninstalled current map.
For `SinaiMap`, preserve the pydcs `Sinai` versus DCS/BriefingRoom `SinaiMap`
disagreement; never normalize it silently.

For exact authority and fallback rules, read [evidence.md](evidence.md). For
bounded command selection, read [tools.md](tools.md) and current CLI help.
For height, surface, scenery-instance, placement, airport-envelope, or
mountain-clearance decisions, read [terrain-physical.md](terrain-physical.md);
this projection matrix cannot answer them.
