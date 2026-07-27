> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# DCS `.miz` structure (config writing)

A `.miz` file is a **ZIP** archive of Lua tables and resources. Core members:

| Entry | Role |
|-------|------|
| `mission` | Main scenario table: theatre, date, start time, weather, coalition units, triggers, goals |
| `options` | Mission options (difficulty, labels, etc.) |
| `warehouses` | Airbase/warehouse stock |
| `l10n/DEFAULT/dictionary` | Localized strings (`DictKey_*`) |
| `l10n/DEFAULT/mapResource` | Map resource dict |
| Optional media | Briefing images, kneeboard, scripts |

## High-level `mission` keys

Observed via pydcs load/save and dcs-mission-maker Zod schemas:

- `theatre` — string, e.g. `GermanyCW`, `SinaiMap`, `Caucasus` (see `terrain/theatres.md`)
- `date` — `{ Year, Month, Day }`
- `start_time` — seconds since midnight (0–86400)
- `weather` — wind layers, clouds, fog, qnh, temperature, precipitation flags
- `coalition` — `blue` / `red` (and neutrals handling) with `bullseye` and nested countries
- `coalitions` — country membership lists per side
- `triggers` / trigger rules
- goals / result conditions
- groundControl, forced options, etc.

## Coalition → country → category → group → unit

```
mission
 └── coalition
      ├── blue
      │    ├── bullseye { x, y }
      │    └── country
      │         └── [N]
      │              ├── id / name
      │              ├── plane  → group → units + route
      │              ├── helicopter
      │              ├── vehicle
      │              ├── ship
      │              └── static
      └── red
           └── ...
```

Country **numeric ids** and names come from DCS country table (pydcs
`countries.py`: Russia=0, Ukraine=1, USA=2, … — 184 named countries in export).

## Weather skeleton (mission-maker defaults)

```json
{
  "atmosphere_type": 0,
  "qnh": 760,
  "name": "Winter, clean sky",
  "enable_fog": false,
  "enable_dust": false,
  "groundTurbulence": 0,
  "season": { "temperature": 20 },
  "visibility": { "distance": 80000 },
  "wind": {
    "atGround": { "speed": 0, "dir": 0 },
    "at2000": { "speed": 0, "dir": 0 },
    "at8000": { "speed": 0, "dir": 0 }
  },
  "clouds": {
    "thickness": 200,
    "density": 0,
    "preset": "Preset2",
    "base": 2500,
    "iprecptns": 0
  },
  "fog": { "thickness": 0, "visibility": 0 }
}
```

`start_time` example: `28800` = 08:00 local mission clock.

## pydcs creation sketch

```python
import dcs
m = dcs.Mission(terrain=dcs.terrain.Germany())
batumi_like = ...  # airport object from m.terrain
usa = m.country("USA")
fg = m.flight_group_from_airport(
    usa, "Viper CAP", dcs.planes.F_16C_50,
    m.terrain.airports["Tempelhof"], group_size=2)
fg.units[0].set_player()
m.save("output/example.miz")
```

## Validation mindset for Agents

1. Theatre string exact match.
2. Every unit `type` exists in DCS DB.
3. Every weapon CLSID allowed on that airframe/pylon.
4. `airdromeId` exists on that map.
5. Coordinates inside theatre bounds (see terrain bounds in pydcs terrain classes).
6. Country belongs to the coalition you assigned.
