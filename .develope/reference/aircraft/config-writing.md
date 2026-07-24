# Aircraft unit config writing (mission JSON/Lua shape)

Derived from pydcs unit models and `dcs-mission-maker` plane-group stubs.

## Minimal flying unit fields

```json
{
  "type": "MiG-29A",
  "unitId": 1,
  "name": "Aerial-1-1",
  "x": -205735.96,
  "y": -453635.45,
  "alt": 0,
  "alt_type": "BARO",
  "heading": 0,
  "speed": 138.88888888889,
  "skill": "Client",
  "payload": {
    "pylons": [],
    "fuel": "3376",
    "flare": 60,
    "chaff": 60,
    "gun": 100
  },
  "callsign": { "name": "Enfield11", "_1": 1, "_2": 1, "_3": 1 },
  "onboard_num": "010",
  "livery_id": "..."
}
```

## Critical rules

1. **`type` must match a DCS internal type id** (see `planes.md` / `helicopters.md`).
2. **`payload.fuel`** is typically a string of kilograms remaining; max comes from
   plane definition (`fuel_max`).
3. **`payload.pylons`** is a list of `{ "CLSID": "...", "num": <pylon number> }`.
   CLSID must be valid for that aircraft pylon (see `weapons/`).
4. **`skill`**: `Client` / `Player` for human, or AI skills (`Excellent`, `High`,
   `Good`, `Average`, `Low`, `Random`).
5. **Coordinates** (`x`, `y`) are **DCS map meters** for the active theatre
   (see `terrain/coordinates.md`). They are **not** lat/lon.
6. Group-level fields also need matching `x`/`y`, `route.points`, and `task`
   (e.g. `CAP`, `CAS`, `Intercept`, `AFAC`, `Reconnaissance`, `Ground Attack`,
   `Pinpoint Strike`, `SEAD`, `Antiship Strike`, `AWACS`, `Refueling`,
   `Transport`, `Escort`, `Fighter Sweep`).

## Group shell (from mission-maker stubs)

```json
{
  "name": "Aerial-1",
  "groupId": 1,
  "task": "CAP",
  "uncontrolled": false,
  "hidden": false,
  "communication": true,
  "frequency": 124,
  "modulation": 0,
  "start_time": 0,
  "route": { "points": [ /* see mission/waypoints.md */ ] },
  "units": [ /* one or more flying units */ ],
  "x": 0,
  "y": 0
}
```

## Payload pylon example (conceptual)

```json
"payload": {
  "pylons": [
    { "CLSID": "{9B25D316-0434-4954-868F-D51DB1A38DF0}", "num": 2 },
    { "CLSID": "{FBC29BFE-3D24-4C64-B81D-941239D12249}", "num": 1 }
  ],
  "fuel": "3376",
  "flare": 60,
  "chaff": 60,
  "gun": 100
}
```

CLSID values above are R-27R and R-73 samples from pydcs `weapons_data.py` —
always re-check compatibility for the specific aircraft/pylon.
