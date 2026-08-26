# Validation and completion

This document defines **validation semantics and completion claims only**. It
does not define evidence authority, command discovery, or the construction
sequence. Start with [quickstart.md](quickstart.md); use
[workflow.md](workflow.md) for order and [build-spec.md](build-spec.md) for the
normative input contract.

## Validation levels

| Level | Proves | Does not prove |
|---|---|---|
| Archive-valid | ZIP opens, member paths/policy are safe, entries are unencrypted, and requested CRC check passes | Lua shape or scenario meaning |
| Parse-valid | Required data tables parse without executing Lua | Internal IDs, compatibility, or DCS acceptance |
| Round-trip-valid | The five parsed core tables exactly equal the complete input spec and the theatre member matches | Whether the supplied tables are legitimate DCS data |
| Limited-structure-valid | Implemented identity, route, coordinate, pylon, parking, logic, native-GCI, briefing, and resource consistency checks have no errors | Full DCS schema or gameplay behavior |
| Contract-valid | Every caller-declared count/membership constraint survived the artifact | Constraints the caller forgot to declare |
| Evidence-bundle-valid | Canonical manifest, content address, safe exact artifact membership, hashes, schemas, authority labels, and derived coverage records match | External authorship or truth of the reports' semantic claims |
| Evidence-domain-ready | The verified clean-producer bundle matches a new read-only collection and the named domain declares complete coverage | Runtime behavior, entitlement, or any domain marked partial/blocked/incomparable |
| V2 DCS-load-valid | A version/hash-bound run loaded the exact filename and theatre | Stable simulation, AI behavior, or another artifact/version |
| V3 simulation-smoke-valid | V2 plus simulation start and the declared stable interval; declared DCS coordinate checks also pass | Every trigger path, AI tactics, or a human playthrough |

Never collapse these into one ambiguous `valid` statement. Static build and
inspection establish only the first five static rows. The isolated runtime
bridge can establish V2/V3 only when `runtime-collect` passes for that exact
MIZ, DCS version, manifest, execution, and result. An aggregate registry probe
is runtime evidence about registry initialization, not V2/V3 evidence for a
mission.

## Quality profiles and gates

The build spec defaults to `quality.profile="technical_fixture"`. This is for
bounded technical artifacts: structural errors, failed contract checks, and
archive/read-back failures are hard failures, but structural warnings and
contract-coverage warnings remain explicit review items. Consequently,
`validation.available_checks_passed` can be true while
`validation.review_warnings_clear` is false.

Use `quality.profile="complete_scenario"` for a user-facing mission. Before
packaging, it requires deterministic seed/provenance, a nonempty contract, the
finite logic compiler with at least two checkpoints, positive success and
negative failure goals with distinct conditions, at least one actual
group/unit and Player/Client slot, a valid date/start-time/weather core,
the observed current mission runtime shell and coalition-side shapes,
current-shape options and warehouses, an explicit `mission.requiredModules`
table, and profile-required finite air-group/route/unit/payload/briefing
fields.

After read-back, the complete profile makes both warning classes fatal:

```text
limited_structure.warning_count == 0
contract.coverage_warning_count == 0
validation.review_warnings_clear == true
validation.quality_gate_passed == true
```

Every actual group must also have one exact `expect.roles` binding; otherwise
`groups_not_fully_role_bound` fails the quality gate. Require
`validation.available_checks_passed: true` in addition to each component
result. A complete-profile pass is a stronger static authoring claim, not a
DCS runtime claim.

## `build-miz` and `verify-miz` checks

Both commands check:

- ZIP validity, safe member paths, encryption, duplicate members, size policy,
  compression ratio, and requested CRC status;
- all five core data tables are present and safely parsed;
- the archive contains exactly the core, theatre, and spec-declared members;
- every parsed core table equals the build spec;
- the plaintext theatre member equals `mission.theatre`;
- every declared resource exists and equals its spec source byte-for-byte;
  its regular-file identity and initial SHA-256 stay bound to one open handle
  through packaging/comparison and the final resource recheck;
- every `mapResource` value resolves to an archive member;
- limited mission-structure diagnostics have no errors;
- every requested `expect` check passes.

The default ZIP ceiling is 4,096 members, 128 MiB expanded per member, 512 MiB
expanded in total, and a 250:1 per-member compression ratio. Any pre-CRC archive
error—including unsafe/duplicate members, encryption, or a policy
violation—rejects the archive before CRC expansion or member parsing, so its CRC
status is `not_checked`, not `passed`.

The limited structural pass checks:

- country IDs;
- globally unique group/unit IDs and names;
- group units and non-static route points;
- waypoint and unit coordinates, including distinct positions within one
  airborne-start group;
- standard air-group main-task display strings;
- air-waypoint `ComboTask` roots, direct child wrapper fields, `ControlledTask`
  nesting, and bounded parameter/reference semantics for `AttackGroup`,
  `AttackMapObject`, `Bombing`, `BombingRunway`, `EngageTargets`,
  `EngageTargetsInZone`, and `Escort`;
- unit type and applicable aircraft/helicopter skill/altitude fields;
- duplicate pylon stations and missing CLSIDs;
- exact known first-waypoint `type`/`action` pairs; exclusive positive
  airdrome or same-coalition linked static/ship references for runway and
  parking starts; ground-area starts without a facility requirement; plus
  airdrome parking occupancy and `parking_id` warnings;
- rejection of `trigrules`, `trig`, `goals`, or `result` nested under
  `mission.triggers`;
- top-level trigger/compiled-trigger and goal/compiled-result linkage,
  including dense trigger sequences and exact global goal keys in sparse
  per-side result tables, predicate shape, and common group/unit/zone
  references;
- dictionary-backed timed-text action shape and dictionary resolution;
- native MiG-29 GCI task-chain/parameter/station linkage plus a recognized
  same-side compatible radar within 250 km;
- a warning for a late-activation group with no structured
  `a_activate_group` link;
- briefing dictionary references, with empty keys or resolved text reported as
  warnings.

This is deliberately finite. It is not a complete DCS mission-schema validator.
Warnings do not fail `technical_fixture`, but the caller must review them;
scripts or other runtime mechanisms can make a warning intentionally
unresolved. All warnings fail `complete_scenario`.

The complete-profile structural pass additionally verifies:

- the observed runtime-shell tables, nonnegative `currentKey`/`maxDictId`,
  finite map view, blue/red coalition-side name/bullseye/nav/country shapes,
  dense country membership, fixed ground-control roles, and empty-or-populated
  blue/red picture tables;
- every briefing field is present and resolves without a warning;
- plane/helicopter group communication, frequency, and modulation;
- waypoint altitude, speed, ETA, altitude type, mode/action, and lock fields;
- both locks true on each air route's first point and no later point with both
  locks true;
- airborne lead heading aligned with the first route leg when that leg is
  longer than one metre;
- nonnegative elapsed route times, group start time equal to the first ETA,
  every human flight starting at elapsed zero, and no human group using late
  activation;
- nonnegative air speeds, positive airborne-start speeds, and positive
  non-landing enroute waypoint speeds;
- internally consistent landing mode and exactly one airfield or linked-helipad
  reference form;
- aircraft/helicopter altitude, speed, altitude type, callsign, onboard number,
  pylons, fuel, chaff, flare, and gun fields;
- an enabled, semantically valid actionable route task in dense task/route
  sequences for each all-AI combat air group;
- complete-profile combat-task parameters and exact direct-task numbering.

The complete input gate also verifies that every used route airdrome has a
current-shape airport warehouse record, that current core option categories
are present, and that local audio-device identifiers are absent.
`mission.requiredModules` must be a table, normally empty; it is never inferred
from the player aircraft.

## Scenario contract discipline

The `expect` section is the model's protection against silent loss during
construction. Include every critical user constraint that the vocabulary can
express:

- exact theatre and mission version;
- player/client slot counts and exact unit types;
- coalition package sizes by category/type;
- required CLSIDs and start modes;
- required waypoint actions, nested task IDs, and group tasks;
- for native MiG-29 GCI, required station/radar unit types and
  `ActivateGCI`;
- required trigger-condition, trigger-action, and goal predicate functions;
- airdrome IDs;
- trigger rules/actions, goals, briefing fields, and briefing size;
- a minimum or exact `max_route_span_seconds` when duration is a user
  constraint, plus a separately meaningful assertion for
  `latest_waypoint_eta_seconds` whenever it is nonzero so the complete-profile
  coverage gate is clear;
- zero missing resources;
- exact path/value assertions for critical date, time, weather, unit, parking,
  route, and trigger scalars in `mission`.

For each group, add a complete `expect.roles` record that binds:

```text
role label and group ID
side, category, and group task
exact unit-type and Player/Client counts
start mode and first-waypoint airdrome ID; for linked facilities, optional
helipad ID and link-unit ID
late-activation state
exact group start offset in mission-elapsed seconds
minimum waypoint count and max(ETA)-min(ETA) route span
required waypoint task IDs and waypoint actions
required groupId references inside the route task tree
```

Role names and group IDs are unique. Under `complete_scenario`, the declared
group-ID set must exactly equal the actual group-ID set. Global counters cannot
replace this binding: they can prove that two fighters exist, but not that the
fighters belong to the intended player, escort, strike, or target group.

Inspect the generated mission for constraints outside that vocabulary. A
passing contract proves only the checks actually requested.
Review `contract.coverage_warnings` as a separate under-declaration signal; a
passing sparse contract is not comprehensive merely because its own checks
passed. `validation.review_warnings_clear` is true only when both limited
structure warnings and contract-coverage warnings are empty; it is separate
from `contract_valid`. It is review-only in the technical profile and a hard
quality requirement in the complete profile.

Zero observed trigger rules, trigger conditions, trigger actions, or goals
always generate coverage warnings. A mission with required success/failure
logic must therefore show nonzero values in the independent inspection as well
as the contract, and cannot achieve a clear review gate by deleting those
expectations.

Predicate-function membership proves that a named condition/action family is
present. It does not prove its arguments, flag flow, timing, scoring, or
gameplay semantics. When the finite `logic` compiler is used, review its source
and compilation metadata as well as the read-back predicates; runtime-test
when an authorized facility exists.

For terminal outcomes, review a stronger authoring invariant: failure writers
precede the success writer; every failure writer requires the success flag to
be false; and the success writer requires every failure flag to be false.
Terminal flags must not be written by `start` rules or later reset/assigned a
value other than true/`1`. Flag-writer coverage alone does not establish that
invariant. Require:

```text
generation.logic_compilation.terminal_outcome_dataflow.guard_order_contract_passed = true
generation.logic_compilation.terminal_outcome_dataflow.runtime_mutual_exclusion_proved = false
generation.logic_compilation.terminal_outcome_dataflow.temporal_reachability_proved = false
```

The true field proves only the authored reciprocal guards,
failure-before-success order, same non-start trigger phase, and absence of
finite reset/other-value writes. The two false fields deliberately prevent
that static result from being promoted to DCS runtime mutual exclusion or
temporal reachability.

## Independent inspection

After build and spec verification, run:

```powershell
python Tools\dcsmizzer.py inspect path\mission.miz > output\inspect.json
python Tools\dcsmizzer.py report-summary output\inspect.json
```

Keep the complete inspection report on disk and open only the needed fields.
Review the anonymous statistics rather than relying only on
`available_checks_passed`. The general inspector independently repeats archive,
CRC, and core-table parsing/statistics; it does not repeat the builder's
limited structure pass and reports that level as unchecked.

## CMP static checks

At minimum:

- campaign table parsed;
- start stage exists;
- relative paths are safe;
- referenced MIZ files exist;
- score intervals are well formed;
- overlaps and gaps are reported rather than normalized away.

Campaign generation and runtime progression validation are not implemented.

## Completion report

Report:

```text
artifact path
requested scenario constraints
constraints preserved and the matching checks
installed DCS/static source version and hashes used
real-mission root labels, filters, and coverage used
generation method and seed
build-spec evidence-audit result and reviewed warnings
archive, CRC, parse, round-trip, structure, resource, and contract results
independent inspection result
runtime checks not run and why
remaining uncertainty affecting loadability, playability, or fidelity
```

Use “built and statically verified” only when build, readback, and the relevant
checks actually ran. Do not say “DCS-valid,” “playable,” or “complete” while
`runtime_valid` is `null`.

Static archive, parse, round-trip, structure, contract, and complete-profile
quality checks do not simulate DCS initialization, AI behavior, task
execution, terrain collision, parking clearance, trigger timing, radio/GCI
reception, or mission success/failure in play.

No current product command starts DCS or Mission Editor.
