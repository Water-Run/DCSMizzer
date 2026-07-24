# Weather configuration reference

## pydcs cloud presets (`mission.weather.clouds.preset`)

Use `name` string (e.g. `Preset1`) in miz cloud tables.

| enum | name | ui_name | min_base (m) | max_base (m) |
|------|------|---------|--------------|--------------|
| `LightScattered1` | `Preset1` | Light Scattered 1 | 840 | 4200 |
| `Scattered5` | `Preset10` | Scattered 5 | 1260 | 4200 |
| `Scattered6` | `Preset11` | Scattered 6 | 2520 | 5460 |
| `Scattered7` | `Preset12` | Scattered 7 | 1680 | 3360 |
| `Broken1` | `Preset13` | Broken 1 | 1680 | 3360 |
| `Broken2` | `Preset14` | Broken 2 | 1680 | 3360 |
| `Broken3` | `Preset15` | Broken 3 | 840 | 5040 |
| `Broken4` | `Preset16` | Broken 4 | 1260 | 4200 |
| `Broken5` | `Preset17` | Broken 5 | 0 | 2520 |
| `Broken6` | `Preset18` | Broken 6 | 0 | 3780 |
| `Broken7` | `Preset19` | Broken 7 | 0 | 2940 |
| `LightScattered2` | `Preset2` | Light Scattered 2 | 1260 | 2520 |
| `Broken8` | `Preset20` | Broken 8 | 0 | 3780 |
| `Overcast1` | `Preset21` | Overcast 1 | 1260 | 4200 |
| `Overcast2` | `Preset22` | Overcast 2 | 420 | 4200 |
| `Overcast3` | `Preset23` | Overcast 3 | 840 | 3360 |
| `Overcast4` | `Preset24` | Overcast 4 | 420 | 2520 |
| `Overcast5` | `Preset25` | Overcast 5 | 420 | 3360 |
| `Overcast6` | `Preset26` | Overcast 6 | 420 | 2940 |
| `Overcast7` | `Preset27` | Overcast 7 | 420 | 2520 |
| `HighScattered1` | `Preset3` | High Scattered 1 | 840 | 2520 |
| `HighScattered2` | `Preset4` | High Scattered 2 | 1260 | 2520 |
| `Scattered1` | `Preset5` | Scattered 1 | 1260 | 4620 |
| `Scattered2` | `Preset6` | Scattered 2 | 1260 | 4200 |
| `Scattered3` | `Preset7` | Scattered 3 | 1680 | 5040 |
| `HighScattered3` | `Preset8` | High Scattered 3 | 3780 | 5460 |
| `Scattered4` | `Preset9` | Scattered 4 | 1680 | 3780 |
| `OvercastAndRain1` | `RainyPreset1` | Overcast And Rain 1 | 420 | 2940 |
| `OvercastAndRain2` | `RainyPreset2` | Overcast And Rain 2 | 840 | 2520 |
| `OvercastAndRain3` | `RainyPreset3` | Overcast And Rain 3 | 840 | 2520 |

Full: [`../data/pydcs-cloud-presets.json`](../data/pydcs-cloud-presets.json)

## BriefingRoom weather presets (INI narrative)

| preset | notes |
|--------|-------|
| `BrokenClouds` | see INI extract |
| `Clear` | see INI extract |
| `HighScatteredClouds` | see INI extract |
| `LightRain` | see INI extract |
| `LightScatteredClouds` | see INI extract |
| `Overcast` | see INI extract |
| `OvercastAndRain` | see INI extract |
| `ScatteredClouds` | see INI extract |

Raw INI: [`../data/briefing-room-weather-presets.json`](../data/briefing-room-weather-presets.json)

## Mission weather skeleton (recap)

```json
{
  "atmosphere_type": 0,
  "qnh": 760,
  "enable_fog": false,
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
  }
}
```

`iprecptns`: 0 none, 1 rain, 2 thunderstorm (DCS ME conventions — verify in target build).
Wind `dir` is **from** direction (meteorological). Speed in m/s.
