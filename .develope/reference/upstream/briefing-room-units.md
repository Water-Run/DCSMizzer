# BriefingRoom unit DB extracts

Compact type lists from `DatabaseJSON/Unit*.json`.

| file | count | extract |
|------|-------|---------|
| UnitPlanes | 144 | [`../data/briefing-room-unit-planes.json`](../data/briefing-room-unit-planes.json) |
| UnitHelicopters | 26 | [`../data/briefing-room-unit-helicopters.json`](../data/briefing-room-unit-helicopters.json) |
| UnitCars | 350 | [`../data/briefing-room-unit-cars.json`](../data/briefing-room-unit-cars.json) |
| UnitShips | 57 | [`../data/briefing-room-unit-ships.json`](../data/briefing-room-unit-ships.json) |

Also BRInfo metadata dumps: `data/briefing-room-Unit*BRInfo.json`.

## Plane record fields (useful)

`type`, `displayName`, `module`, `tasks[]` (Name/WorldID), `fuel`, `flares`, `chaff`,
`payloadPresets[]`.

## Weapons by date

[`../data/briefing-room-weapons-by-date.json`](../data/briefing-room-weapons-by-date.json) —
list of `{decade, clsid}` for era filtering of loadouts.
