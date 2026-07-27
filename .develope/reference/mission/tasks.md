> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Flight tasks and engage actions (pydcs)

## Group-level mission tasks (common ME strings)

Typical group `task` values used in DCS missions include:

`CAP`, `CAS`, `Interception` / intercept variants, `Fighter Sweep`, `Escort`,
`SEAD`, `Antiship Strike`, `Ground Attack`, `Pinpoint Strike`, `Runway Attack`,
`AFAC`, `Reconnaissance`, `AWACS`, `Refueling`, `Transport`, `Nothing`.

Always match what the Mission Editor accepts for the unit category.

## pydcs Task action classes (sample)

From `pydcs/dcs/task.py` (59+ classes), including:

- Air-to-air / package: `CAPTaskAction`, `FighterSweepTaskAction`, `EscortTaskAction`, `EngageTargets`, `EngageTargetsInZone`, `EngageGroup`, `EngageUnit`
- Air-to-ground: `CASTaskAction`, `SEADTaskAction`, `Bombing`, `BombingRunway`, `Strafing`, `AttackGroup`, `AttackUnit`, `AttackMapObject`, `FireAtPoint`
- Support: `AWACSTaskAction`, `RefuelingTaskAction`, `Tanker`, `RecoveryTanker`, `OrbitAction`, `EWR`, `FAC`, `FACAttackGroup`
- Utility: `Hold`, `Land`, `Follow`, `GoToWaypoint`, `NoTask`, `ControlledTask`

## Target category filter strings (task id samples)

`Fighters`, `Multirole fighters`, `Bombers`, `Helicopters`, `Planes`, `Air`,
`Ground Units`, `Armor`/`Tanks`, `Infantry`, `Artillery`, `Air Defence`,
`SAM related`, `SR SAM` / `MR SAM` / `LR SAM`, `Ships`, `Aircraft Carriers`, etc.

## Orbit / AWACS pattern (conceptual)

Waypoint task list often embeds nested ComboTask → Orbit / AWACS actions with
pattern (Circle/Race-Track), altitude, speed, and race distance — mirror pydcs
`awacs_flight` / `OrbitAction` when implementing generators.
