# MIZ and CMP data format

This is an **on-demand raw-structure and diagnostic reference**. A typical
generation pass should read [quickstart.md](quickstart.md) and the normative
[build-spec.md](build-spec.md), not this file end to end. Open only the
relevant section when diagnosing archive/Lua shape, starts and parking,
payload/task tables, native MiG-29A GCI, resources, or CMP structure.

This document describes the data shape accepted by the safe parser and the
low-level builder. It is not a guarantee that an arbitrary table will load in
DCS.

## MIZ archive

A `.miz` is a ZIP archive. The low-level builder always writes:

```text
mission
options
warehouses
l10n/DEFAULT/dictionary
l10n/DEFAULT/mapResource
theatre
```

It then adds caller-declared resource members. Historical missions can omit
some nonessential members, but a newly built artifact must contain and parse
all five core tables.

The core members are UTF-8 data-only Lua assignments:

```text
mission = { ... }
options = { ... }
warehouses = { ... }
dictionary = { ... }
mapResource = { ... }
```

The separate plaintext `theatre` member must equal `mission.theatre`.

## Common mission table shape

The complete schema is version- and content-dependent. Common top-level fields
include:

- `version`, `theatre`, `date`, `start_time`, and `weather`;
- `coalition` sides containing numeric `country` tables;
- `plane`, `helicopter`, `vehicle`, `ship`, and `static` categories;
- numeric group arrays with `groupId`, `name`, `task`, `units`, and `route`;
- units with `unitId`, `name`, exact `type`, `skill`, coordinates, heading,
  payload, and category-specific fields;
- route points with coordinates, `type`, `action`, speed/altitude fields,
  optional `airdromeId`, and nested tasks;
- `triggers` for zones, top-level `trigrules` plus compiled `trig`, top-level
  `goals` plus compiled `result`, forced options, and ground-control data;
- briefing dictionary keys and resource-key references;
- `requiredModules`, which is a plugin-requirement table and is not derived
  from the player aircraft;
- newer version-specific fields such as `dynSpawnTemplate`, `DTC`,
  `dataCartridge`, `datalinks`, and `coldAtStart`.

Do not reduce a real mission to this list. `miz-registry` can provide anonymous
field-count and variant shapes for an exact caller-supplied category/type
filter; it deliberately does not reveal raw mission field names or offer a
version filter. Resolve exact version-specific field shapes from current
public/static evidence or an independently inspected authorized mission, and
preserve task-relevant fields.

### Complete-profile runtime shell

The current accepted official-mission core-shape sample consistently contains
more than groups and routes. A `complete_scenario` build therefore requires:

```text
mission.coalitions.blue/red       dense country-ID membership arrays
mission.currentKey                nonnegative integer
mission.failures                  table, possibly empty
mission.forcedOptions             table, possibly empty
mission.groundControl             pilot-control boolean plus roles table
mission.map                       finite centerX/centerY and positive zoom
mission.maxDictId                 nonnegative integer
mission.pictureFileNameB/R        tables, possibly empty
```

The exact role nesting is
`groundControl.roles.<role>.<side>`. Provide all four role names
`artillery_commander`, `forward_observer`, `instructor`, and `observer`, and
provide table-valued `blue` and `red` under each role. Empty side tables are
valid.

Each blue/red `mission.coalition` side also carries:

```text
name          exact side string
bullseye      numeric x/y table
nav_points    table
country       numeric country table
```

An authored neutral side is checked the same way. Every used country ID must
also occur in the matching `mission.coalitions` membership array; one ID
cannot belong to multiple sides. Empty failure, forced-option, picture, nav,
membership, and role-side arrays still need an explicit Lua table rather than
an omitted field or JSON `null`.

This is an observed current completeness floor, not a universal DCS schema or
a runtime-load proof. Choose map center, zoom, bullseyes, coalition membership,
and counters deliberately from the scenario and current evidence.

## Options, warehouses, and required modules

`options` and `warehouses` are complete archive core tables, not optional
decorations. For a user-facing build, query current-install-backed templates
instead of reducing them to empty placeholders:

```powershell
python Tools\dcsmizzer.py dcs-options-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --player-name "DCSMizzer" `
  --full-sim

python Tools\dcsmizzer.py dcs-warehouse-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --airdrome-id 23 `
  --coalition NEUTRAL
```

The first report's `options` value is the safely parsed current Mission Editor
default with a deterministic player name, local audio-device fields blanked,
and only the reported full-simulation overrides applied. A complete-profile
options table contains current core fields `VR`, `difficulty`, `format`,
`graphics`, `miscellaneous`, `playerName`, `plugins`, `sound`, and `views`.
Do not copy a user's device names into a generated mission.

The second report's `warehouses` value contains both top-level registries and a
numeric `$fields` airport entry for each requested ID. Resolve each airdrome ID
from terrain-specific evidence first. The command emits a bounded
unlimited-stock shape from verified current Mission Editor literals; it does
not validate the ID, initialize runtime inventory, or decide the warehouse
coalition for the author.

Under `complete_scenario`, every numeric route `airdromeId` must be present in
`warehouses.airports`. Each used entry must retain the current 20 fields and
their expected table, boolean, number, fuel-record, and coalition-string
types. `warehouses.warehouses` must exist even when empty.

`mission.requiredModules` is separate from `options.plugins` and from the
aircraft used by a Player or Client slot. Do not infer it from a module display
name. Current observed missions overwhelmingly use an empty table:

```json
{
  "requiredModules": {}
}
```

Use a nonempty table only with exact version-matched plugin evidence. In the
complete profile every entry must map an exact plugin-ID string to the
identical string.

## Starts, coordinates, and parking

The evidence tools classify a group's first route point only when its `type`
and `action` form one of these exact observed pairs:

| Mode | `type` | `action` |
|---|---|---|
| `cold_parking` | `TakeOffParking` | `From Parking Area` |
| `hot_parking` | `TakeOffParkingHot` | `From Parking Area Hot` |
| `runway` | `TakeOff` | `From Runway` |
| `cold_ground` | `TakeOffGround` | `From Ground Area` |
| `hot_ground` | `TakeOffGroundHot` | `From Ground Area Hot` |
| `air` | `Turning Point` | `Turning Point` |
| `air` | `Turning Point` | `Fly Over Point` |

An unknown pair is `other`. A pair containing any known marker in the wrong
combination is structurally invalid; one matching half does not classify a
start.

For an airdrome parking start, link the first waypoint's exact positive
`airdromeId` to each unit's `parking`, `parking_id`, position, altitude, and
heading from the same observed record. Current real missions contain both
numeric and nonempty string parking tokens, so preserve the observed type as
well as its value. Do not mix fields from unrelated missions or airfields.

A runway or parking first point instead may use the linked-facility form
`helipadId == linkUnit`, with no `airdromeId`. The linked ID must resolve to a
static or ship unit on the same coalition side. Observed FARP/ship starts can
omit unit `parking`; do not invent a parking token just to resemble an
airdrome start. Observed ground-area starts do not require an airdrome, linked
facility, or parking token.

If no version-matched observation exists, `pydcs-airports` can provide
lower-authority, commit-bound declarations after its airport ID/name is
cross-checked against current installed `dcs-airbases`. In that generated
model, mission `parking` is the reported `crossroad_idx`, and `parking_id` is
the reported `slot_name`; neither is the parking array position. Preserve the
reported position and record that installed-runtime compatibility remains
unverified.

Coordinates are terrain-local. Latitude/longitude and beacon coordinates are
not automatically mission `x`/`y`. Use `dcs-coordinates` to derive a
current-install, beacon-validated projection, then convert an authoritative
WGS-84 point. The conversion does not provide terrain height, land cover, or
unit-placement validity, and beacon positions are not parking positions. Exact
runway and parking behavior remains runtime-dependent.

## Payloads and tasks

A unit payload commonly contains a numeric or sparse `pylons` table. Each
assignment contains an exact `CLSID` and may carry explicit station `num`.
Preserve the relationship from one verified preset or mission observation.
`pydcs-aircraft` can independently cross-check a generated station/CLSID
declaration at its reported commit, but does not replace current installed or
version-matched observed evidence.

A group's high-level `task`, waypoint `action`, and nested task `id` are
different fields. Do not substitute the numeric default-payload task constants
for string mission task IDs. Validate both through the build contract.

Generated upstream task records expose another easy-to-confuse split. For
example:

```text
Python class             GroundAttack
mission group.task       Ground Attack
payload internal name    GroundAttack
```

Use `pydcs-aircraft` field `mission_group_task` for the group table. Every air
waypoint must use a root `ComboTask` with a `params.tasks` table; a high-level
group task is not a substitute for that route structure. Each direct task
entry needs a nonempty `id`, a `params` table, a positive `number`, and boolean
`auto`/`enabled`. In `complete_scenario`, its `number` must equal the numeric
sequence key. A `ControlledTask` supplies a nested `params.task` record whose
own `id` and `params` are checked recursively.

The bounded semantic gate recognizes `AttackGroup`, `AttackMapObject`,
`Bombing`, `BombingRunway`, `EngageTargets`, `EngageTargetsInZone`, and
`Escort`. It checks their required coordinates, distances, target-type
sequences, quantities, enable flags, weapon/expend fields, runway/group
references, and task-family-specific values. In particular:

- `AttackGroup` must reference an existing hostile non-static group when a
  target is specified;
- `Escort` must reference a different friendly plane group and use a
  `lastWptIndex` within that target's route; the source group cannot escort
  itself;
- `EngageTargets` distance and enable fields must be paired;
- zone and engagement radii/distances must be positive;
- task parameter sequences must be dense and contain the expected scalar
  types.

The complete profile requires the fuller current generated parameter contract
for those task families and rejects an all-AI combat flight whose route has no
compatible, `enabled=true`, semantically valid task in a dense `ComboTask`
route. Empty, disabled, malformed, or unknown task IDs cannot satisfy this
gate. See
[build-spec.md](build-spec.md#air-waypoint-task-semantics) for the exact
implemented field contract. This is still not a universal DCS task schema.

For complete-profile plane/helicopter groups, also preserve group radio fields,
full waypoint altitude/speed/ETA and lock fields, `start_time` equal to the
first ETA, unit altitude/speed/callsign/onboard number, and payload
pylons/fuel/chaff/flare/gun. A landing point uses both `type="Land"` and
`action="Landing"` and exactly one destination reference form: an
`airdromeId`, or the `helipadId` plus `linkUnit` pair.

Units in the same airborne-start group must also have distinct `x/y/alt`
positions.

For trigger logic, `miz-registry` exposes anonymous zone/rule/condition/action/
goal field-count and variant shapes plus predicate-function occurrence
distributions. It does not expose field or function identifiers, predicate
bodies, arguments, names, comments, or scripts. Treat the reported shapes as
observed structural examples and verify the required predicate family in the
scenario contract or independent inspection.

The four logic products occupy separate top-level namespaces:

```text
mission.triggers   zone definitions
mission.trigrules  editable trigger-rule records
mission.trig       compiled trigger condition/action/function strings
mission.goals      editable scoring-goal records
mission.result     compiled goal condition/action/function strings
```

Nesting `trigrules` or `goals` under `mission.triggers` creates inert data and
is rejected by the builder. For the common supported families, use the finite
`dcsmizzer.miz-logic/v1` compiler in [build-spec.md](build-spec.md); it creates
and links all four top-level products without accepting arbitrary Lua.
Compiled trigger sequences remain dense. Each side-specific
`mission.result.{side}.conditions/actions/func` table instead retains the
corresponding `mission.goals` global numeric keys, so one side's keys can be
sparse.

## Native MiG-29A GCI

Current installed evidence exposes native instrument guidance for the
full-fidelity `MiG-29 Fulcrum`. Query it before authoring:

```powershell
python Tools\dcsmizzer.py dcs-gci --dcs-root "D:\path\to\DCSWorld"
```

The current exact station type is `GCI_station_MiG29`. Place it as a vehicle
unit and add this shape to its first waypoint task, replacing the IDs and
mission-local area geometry with the authored values:

```json
{
  "task": {
    "id": "ComboTask",
    "params": {
      "tasks": [
        {
          "number": 1,
          "auto": true,
          "id": "WrappedAction",
          "enabled": true,
          "params": {
            "action": {
              "id": "ActivateGCI",
              "params": {
                "unitId": 701,
                "channel": 5,
                "radius": 200000,
                "x": 12345.0,
                "y": 67890.0
              }
            }
          }
        }
      ]
    }
  }
}
```

`unitId` must identify that exact station unit. `x`, `y`, and `radius` define
the GCI responsibility area; they are not a substitute for the station unit's
own position. On the same coalition side, place at least one exact compatible
radar reported by `dcs-gci` within 250,000 metres of the station. The installed
official training mission observes both `1L13 EWR` and `55G6 EWR`; do not infer
a display name or use an unreported type.

The limited structural gate rejects an invalid task chain, missing/invalid
parameters, a station without `ActivateGCI`, an action linked to the wrong
unit, or no recognized compatible radar in link range. Require
`GCI_station_MiG29`, the selected radar type, and `ActivateGCI` in the scenario
contract.

The current installed manual states that native instrument GCI guides players,
not AI aircraft. An AI wingman still uses its normal group route and combat
tasks. Dictionary-backed timed text actions can provide additional command-post
instructions, but briefing prose or a `groundControl` table is not a native
GCI implementation. Static validation cannot prove terrain masking, reception,
target assignment, or in-game behavior.

## Briefing and resources

These mission fields normally contain dictionary keys:

```text
sortie
descriptionText
descriptionBlueTask
descriptionRedTask
descriptionNeutralsTask
```

Each nonempty key must resolve to a string in `dictionary`; an empty key or
empty resolved string produces a structural warning. Require every
user-relevant briefing field through the scenario contract to prove it is
nonempty. `mapResource` is a flat string-to-string table whose values name
archive resources. List every packaged binary under top-level build-spec
`resources`; do not embed bytes in JSON.

The complete profile requires all five listed briefing fields to be present.
Because its warnings are fatal, every field must also resolve to nonempty
dictionary text, including a deliberately short neutral-side statement when
that side has no task.

## Safe Lua handling

The parser accepts a constrained data-only subset:

- assignments, return values, tables, strings, finite numbers, booleans, and
  data omissions;
- string/numeric/bare keys and implicit arrays;
- comments, common escapes, Unicode, UTF-8 BOM, UTF-8, and CP1251;
- the observed `_("<text>")` data wrapper when reading.

It rejects arbitrary function calls, `require`, function definitions, loops,
member execution, I/O, and system access. It applies limits to Lua input,
depth, nodes, strings, and ZIP expansion. The default ZIP ceiling is 4,096
members, 128 MiB expanded per member, 512 MiB expanded in total, and a 250:1
per-member compression ratio. Unsafe/duplicate, encrypted, or policy-violating
archives are rejected without CRC expansion or member parsing. Mission and
trigger scripts are never executed.

## CMP

A `.cmp` is a Lua data file whose `campaign` table commonly includes version,
localized name/description fields, directory/fullPath, `startStage`, and
stages. Stages contain relative MIZ references and score intervals.

The product can inspect CMP references and intervals. It cannot generate a
campaign or prove campaign progression in DCS.
