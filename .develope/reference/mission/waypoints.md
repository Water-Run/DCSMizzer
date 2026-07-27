> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Waypoints and start states

Source: `dcs-mission-maker/mission-stubs/coalition/country/plane/group/*.json`
and pydcs `point.py` enums.

## Common route point fields

```json
{
  "type": "TakeOff",
  "action": "From Runway",
  "x": -319064.875,
  "y": 903148.53125,
  "alt": 465,
  "alt_type": "BARO",
  "speed": 138.88888888889,
  "speed_locked": true,
  "ETA": 0,
  "ETA_locked": true,
  "airdromeId": 31,
  "formation_template": "",
  "task": { "id": "ComboTask", "params": { "tasks": [] } }
}
```

## Start / waypoint type matrix

| Stub file | `type` | `action` | Needs `airdromeId` | Meaning |
|-----------|--------|----------|--------------------|---------|
| takeoff-from-runway | `TakeOff` | `From Runway` | yes | Runway takeoff |
| takeoff-from-parking-hot | `TakeOffParkingHot` | `From Parking Area Hot` | yes | Hot parking start |
| takeoff-from-ramp | `TakeOffParking` | `From Parking Area` | yes | Cold / ramp start |
| turning-point | `Turning Point` | `Turning Point` | no | Normal WP |
| fly-over-point | `Turning Point` | `Fly Over Point` | no | Fly-over |
| landing-autopark | `Land` | `Landing` | yes | Land + park |
| landing-fixed-park | `Land` | `Landing` | yes | Land fixed slot |

## Agent guidance

- Cold start missions: first point `TakeOffParking` + `From Parking Area`.
- Hot start: `TakeOffParkingHot`.
- Air start: first point is a `Turning Point` at altitude with airspeed; no airdromeId.
- Landing: final `Land` with valid destination `airdromeId`.
- Keep unit and group `x`/`y` consistent with the first route point for ground starts.
- Speed in stubs is often ~138.89 m/s (~500 km/h) as a default; set realistically per airframe.
