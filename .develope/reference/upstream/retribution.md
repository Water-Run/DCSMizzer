# DCS Retribution — extracted patterns

Source clone: `.develope/upstream/dcs-retribution`  
Upstream: https://github.com/dcs-retribution/dcs-retribution

Retribution (Liberation fork) is a **dynamic campaign / mission generator** built on
**pydcs**. High-value pieces for DCSMizzer are its theatre metadata, faction loadouts,
flight-plan typology, and mission generator decomposition.

## Layout

| Path | Role |
|------|------|
| `resources/theaters/*/info.yaml` | Daytime bands, climate, season weather weights |
| `resources/factions/*.json` | **131** faction TO&E (aircraft, AD, naval, doctrine) |
| `resources/units/aircraft/*.yaml` | **258** aircraft metadata sheets |
| `resources/units/ground_units/` | Ground unit sheets |
| `resources/payloads/` | Named payload presets |
| `game/ato/flightplans/` | Flight-plan builders by mission type |
| `game/missiongenerator/` | pydcs-based `.miz` assembly pipeline |
| `game/missiongenerator/aircraft/` | Flight group spawn / loadout / painting |

## Supported theatres (resource packs)

`afghanistan`, `caucasus`, `falklands`, `germanycw`, `iraq`, `kola`, `marianaislands`, `nevada`, `normandy`, `persian gulf`, `sinai`, `syria`, `the channel`

Note: includes **iraq** (not always present in older pydcs trees) and **germanycw**.

### `info.yaml` climate pattern (GermanyCW)

```yaml
name: GermanyCW
timezone: +1
daytime:
  dawn: [6, 9]
  day: [9, 18]
  dusk: [18, 20]
  night: [0, 5]
climate:
  seasons:
    summer:
      average_temperature: 22.5
      weather: {thunderstorm: 1, raining: 10, cloudy: 35, clear: 55}
```

Full raw map: [`../data/retribution-theater-info.yaml.json`](../data/retribution-theater-info.yaml.json)

## Flight-plan mission types

Retribution models packages as typed flight plans (builders under
`game/ato/flightplans/`):

`aewc`, `airassault`, `airlift`, `antiship`, `armedrecon`, `bai`, `barcap`, `cas`, `dead`, `escort`, `ferry`, `ocaaircraft`, `ocarunway`, `packagerefueling`, `pretensecargo`, `sead`, `seadsweep`, `shiprecoverytanker`, `strike`, `sweep`, `tarcap`, `theaterrefueling`

Useful mapping for scenario prompts → structure:

| Intent | Builder ideas |
|--------|----------------|
| CAP / BARCAP / TARCAP | `barcap`, `tarcap`, `sweep` |
| Strike / BAI / CAS | `strike`, `bai`, `cas`, `armedrecon` |
| SEAD / DEAD | `sead`, `seadsweep`, `dead` |
| OCA | `ocaaircraft`, `ocarunway` |
| Escort | `escort` |
| AEW&C / tanker | `aewc`, `packagerefueling`, `theaterrefueling` |
| Anti-ship | `antiship` |
| Transport / assault | `airlift`, `airassault`, `ferry` |

## Faction JSON shape

```json
{
  "country": "Combined Joint Task Forces Blue",
  "name": "Bluefor Coldwar",
  "aircrafts": ["F-4E Phantom II", "MiG-..."],
  "awacs": ["E-3A"],
  "tankers": ["KC-135 Stratotanker"],
  "frontline_units": ["M60A3 \"Patton\""],
  "air_defense_units": ["..."],
  "naval_units": ["..."],
  "doctrine": "...",
  "has_jtac": true
}
```

Index: [`../data/retribution-factions-index.json`](../data/retribution-factions-index.json)

Cold-war oriented faction files (sample names):  
`USA 1970 Vietnam War.json`, `USA 1971 Vietnam War.json`, `USSR 1971 Vietnam War.json`, `argentina_1982.json`, `bluefor_coldwar.json`, `bluefor_modern.json`, `blufor_late_coldwar.json`, `egypt_1973.json`, `france_1985.json`, `gdr_1985.json`, `iran_1988.json`, `israel_1973.json`, `israel_1982.json`, `nva_1970.json`, `russia_1970_limited_air.json`, `russia_1975 (Mi-24P).json`, `russia_1975.json`, `russia_1980.json`, `sweden_1970.json`, `sweden_1980.json`, `syria_1973.json`, `syria_1982.json`, `usa_1970.json`, `usa_1975.json`, `usn_1985.json`, `vietcong_1970.json`, `vietnam_1970.json`

## Mission generator pipeline (conceptual)

1. Build theatre / control points / front lines  
2. Plan ATO packages with typed flight plans + waypoints  
3. `aircraftgenerator` spawns pydcs flight groups (start type, loadout, livery)  
4. Ground / flot / carrier / trigger / briefing generators fill the rest  
5. Serialize via pydcs `Mission.save`

## Agent takeaways

1. Use Retribution **flight-plan vocabulary** when structuring multi-package missions.
2. Use **faction TO&E** as era-appropriate unit menus (still verify type ids in pydcs).
3. Theatre `info.yaml` weather weights help pick realistic cloud/rain odds by season.
4. Aircraft YAML descriptions are narrative; **DCS type strings still come from pydcs**.
