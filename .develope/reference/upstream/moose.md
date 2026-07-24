# MOOSE — extracted patterns

Source clone: `.develope/upstream/MOOSE`  
Upstream: https://github.com/FlightControl-Master/MOOSE  
Docs: https://flightcontrol-master.github.io/MOOSE_DOCS/

MOOSE is a **runtime Lua framework** for DCS mission scripting (spawn, tasking,
zones, airboss, etc.). DCSMizzer cares about its **coordinate model** and
**object wrappers** when generating scripts or validating runtime ideas — not
about vendoring the whole framework.

## Module map (130 Lua files surveyed)

| Package | Files | Examples |
|---------|-------|----------|
| `Core` | 29 | `Astar`, `Base`, `Beacon`, `ClientMenu`, `Condition`, `Database`, `Event`, `Fsm`… |
| `Wrapper` | 15 | `Airbase`, `Client`, `Controllable`, `DynamicCargo`, `Group`, `Identifiable`, `Marker`, `Net`… |
| `Functional` | 28 | `AICSAR`, `ATC_Ground`, `AmmoTruck`, `Artillery`, `Autolase`, `CleanUp`, `ClientWatch`, `Designate`… |
| `Ops` | 36 | `ATIS`, `AirWing`, `Airboss`, `ArmyGroup`, `Auftrag`, `Awacs`, `Brigade`, `CSAR`… |
| `Navigation` | 4 | `Beacons`, `Point`, `Radios`, `Towns` |
| `Shapes` | 7 | `Circle`, `Cube`, `Line`, `Oval`, `Polygon`, `ShapeBase`, `Triangle` |
| `Utilities` | 5 | `Enums`, `FiFo`, `Profiler`, `Socket`, `Utils` |
| `Sound` | 6 | `Radio`, `RadioQueue`, `RadioSpeech`, `SRS`, `SoundOutput`, `UserSound` |

## Coordinate system (`Core/Point.lua` → `COORDINATE`)

MOOSE `COORDINATE` wraps DCS map coordinates and conversions.

### Constructors (selected)

| Method | Role |
|--------|------|
| `COORDINATE:New(x, y, z)` | From DCS meters (x north, y alt, z east) |
| `COORDINATE:NewFromVec2(vec2)` | From {x,y} mission 2D |
| `COORDINATE:NewFromVec3(vec3)` | From {x,y,z} |
| `COORDINATE:NewFromLLDD(lat, lon)` | From lat/lon degrees |
| `COORDINATE:NewFromWaypoint(wp)` | From mission waypoint |
| `COORDINATE:NewFromCoordinate(c)` | Copy |

### Operations (selected of 184 methods)

| Method | Role |
|--------|------|
| `GetVec2` / `GetVec3` | Export DCS vectors |
| `Translate(distance, angle)` | Move by meters + heading |
| `Rotate2D` | Rotate about origin |
| `GetMagneticDeclination` | Mag var at point |
| `DistanceFromPointVec2` | Distance meters |
| `ScanUnits` / `FindClosestUnit` | Runtime world queries |
| `ScanStatics` / `FindClosestStatic` | Runtime statics |

### Alignment with mission file fields

| Context | North | East | Alt |
|---------|-------|------|-----|
| `.miz` unit / WP | `x` | `y` | `alt` |
| DCS Vec3 / MOOSE | `x` | `z` | `y` |
| BriefingRoom `pos.DCS` | `x` | `z` | `y` |
| pydcs `Point` | `x` | `y` | (separate) |

**Rule:** when reading MOOSE/BR Vec3 into mission JSON, map `z → y`.

## Core runtime building blocks

From archive core guide + tree:

- **BASE** — inheritance, events, tracing  
- **DATABASE** — scans mission for groups, units, statics, airbases, zones, clients  
- **SPAWN** / **SPAWNSTATIC** — late activation templates  
- **WRAPPER.GROUP / UNIT** — alive object control  
- **ZONE** family — trigger/polygon/round zones  
- **Ops.FlightGroup / ArmyGroup / NavyGroup** — higher-level maneuver units  

## Agent takeaways

1. Use MOOSE as reference for **runtime** behaviours (CAP orbits, CTLD, airboss),
   not for static `.miz` generation (prefer pydcs / mission-maker schemas).
2. Coordinate conversions must respect **Vec2 y = east** vs **Vec3 z = east**.
3. Demo missions live in separate `MOOSE_MISSIONS` repo — clone on demand.
4. Keep MOOSE license (open source) in mind if embedding scripts in generated miz.
