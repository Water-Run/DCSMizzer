> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# BriefingRoom for DCS — extracted patterns

Source clone: `.develope/upstream/briefing-room-for-dcs`  
Upstream: https://github.com/DCS-BR-Tools/briefing-room-for-dcs

BriefingRoom is a **mission generator** with a large INI/JSON database of theaters,
coalitions, unit families, objective tasks, weather, and situation templates.

## Database layout (high value)

| Path | Role |
|------|------|
| `Database/Theaters/*.ini` | Theatre DCSID, daytime, temperature, magnetic declination |
| `DatabaseJSON/TheaterTerrainBounds/*.json` | Land/water polygons in map meters |
| `DatabaseJSON/TheatersAirbases.json` | **802** airbases across 14 theatres with DCS+World coords, parking, runways |
| `DatabaseJSON/UnitPlanes.json` | 144 plane type records (tasks, fuel, payload presets) |
| `DatabaseJSON/UnitHelicopters.json` | 26 helicopters |
| `DatabaseJSON/UnitCars.json` | 350 ground vehicles |
| `DatabaseJSON/UnitShips.json` | 57 ships |
| `DatabaseJSON/UnitFortifications.json` | 230 fortifications |
| `Database/Coalitions/*.ini` | 107 coalition templates (countries + unit lists) |
| `Database/ObjectiveTasks/*.ini` | Objective completion semantics |
| `DatabaseJSON/Situations/*.json` | 110 situation templates (front lines / control) |
| `Database/WeatherPresets/` | Weather preset definitions |
| `Database/CAP.ini` | CAP placement distances, group sizes, skill bands |

## Theatre DCSID map (BriefingRoom)

| Display name | DCSID (`theatre` string) | Mag decl | DefaultMapCenter |
|--------------|--------------------------|----------|------------------|
| Afghanistan | `Afghanistan` | -3.46 | `0,0` |
| Caucasus | `Caucasus` | -6 | `-186462,680207` |
| South Atlantic | `Falklands` | 2.5 | `0,0` |
| Cold War Germany | `GermanyCW` | 4 | `-179123.50597609,-700000` |
| Iraq | `Iraq` | -3.46 | `0,0` |
| Kola | `Kola` | -6 | `-65093.762739046,-342633.64480611` |
| Mariana Islands | `MarianaIslands` | -18.21 | `28000,-29670` |
| WWII Mariana Islands | `MarianaIslandsWWII` | -18.21 | `28000,-29670` |
| Nevada Test and Training Range | `Nevada` | 12 | `-294388.0881016,-59252.988047809` |
| Normandy | `Normandy` | 8 | `-1639,-45000` |
| Persian Gulf | `PersianGulf` | -2 | `-188,6279` |
| Sinai | `SinaiMap` | 5.08 | `-291014,617414` |
| Syria | `Syria` | 5.08 | `-29917.390625,82742.13671875` |
| The Channel | `TheChannel` | 8 | `-38133,7500` |

## Airbase counts (TheatersAirbases.json)

| theatre | count |
|---------|-------|
| `GermanyCW` | 227 |
| `Syria` | 225 |
| `Normandy` | 82 |
| `SinaiMap` | 56 |
| `Kola` | 37 |
| `PersianGulf` | 30 |
| `Afghanistan` | 29 |
| `Falklands` | 27 |
| `Caucasus` | 21 |
| `Iraq` | 20 |
| `Nevada` | 17 |
| `TheChannel` | 12 |
| `MarianaIslandsWWII` | 11 |
| `MarianaIslands` | 8 |

Compact extract: [`../data/briefing-room-airbases.json`](../data/briefing-room-airbases.json)

### Coordinate note (BriefingRoom)

Airbase `pos.DCS` uses **Vec3**: `x` north, `y` altitude, `z` east.  
Mission unit fields still use 2D `x`/`y` where `y` = east (= BR `z`).  
`pos.World` provides WGS84 `lat`/`lon`/`alt`.

### Cross-check vs pydcs (GermanyCW Tempelhof)

| source | id | x (north) | east | name |
|--------|----|-----------|------|------|
| BriefingRoom | 29 | -220930.65625 | z=-481126.40625 | Tempelhof |
| pydcs | 29 | -221028.265625 | y=-480137.515625 | Tempelhof |

## Objective tasks

`CaptureLocation`, `DefendAttack`, `DestroyAll`, `DestroyAllExceptAirDefense`, `DestroyTrackingRadars`, `Disable`, `Escort`, `ExtractTroops`, `FlyNearAlly`, `FlyNearEnemy`, `Hold`, `HoldSuperiority`, `LandNearAlly`, `LandNearEnemy`, `SupportAttack`, `TransportCargo`, `TransportDynamicCargo`, `TransportTroops`

## CAP generation knobs (`Database/CAP.ini`)

- `DistanceFromCenter=40,80` (nm-style bands used by generator)
- `GroupSize` distribution and `FlightPathLength`
- Skill bands: VeryLow → VeryHigh with unit count ranges
- Unit families: `PlaneFighter`, `PlaneInterceptor`

## Unit plane record shape

```json
{
  "type": "MiG-29A",
  "displayName": "...",
  "module": "...",
  "tasks": [{"Name": "CAP", "WorldID": ...}],
  "fuel": 3376,
  "flares": ...,
  "chaff": ...,
  "payloadPresets": [ ... ]
}
```

Compact extract: [`../data/briefing-room-unit-planes.json`](../data/briefing-room-unit-planes.json) (144 types).

## Agent takeaways

1. Prefer BR airbases JSON when you need **lat/lon + parking + runway** together.
2. Prefer pydcs for **authoritative type/CLSID/pylon** compatibility.
3. Situation JSON files are good references for multi-base control setups on a map.
4. Do not copy BR Lua generators wholesale; extract data facts only.
