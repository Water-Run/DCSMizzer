# Model workflow

This document defines **sequence and decision gates only**. Start with the
bounded [quickstart.md](quickstart.md); open this longer workflow when a
generation decision or unresolved evidence branch needs it. Exact authority is
in [evidence.md](evidence.md), command syntax is in current CLI help, the
construction contract is [build-spec.md](build-spec.md), and validation claim
meanings are in [validation.md](validation.md).

Do not start designing from memory and retrofit evidence later.

The required construction sequence is:

```text
capabilities -> evidence-readiness (snapshot first when absent)
  -> upstream-status -> upstream-prepare only if needed -> upstream-status
  -> terrain-catalog -> terrain-coverage
  -> exact terrain/unit/airbase/parking/payload/weather queries
  -> physical placement/corridor evidence where required
  -> options and warehouse templates
  -> audit-spec -> build-miz -> verify-miz -> inspect
```

A requested map does not have to be installed locally to enter the
commit-bound construction workflow. Missing current installed evidence lowers
authority and leaves runtime uncertainty; it is not permission to substitute a
locally installed map.

## 1. Preserve the request

Create a constraint ledger. Record each value as `user-specified`, `verified`,
`inferred`, or `unresolved`.

```text
scenario and objective
era/date and duration
map and mission theatre
coalitions and country IDs
player aircraft and exact internal variant
player count, skill, and slot mode
AI packages, tasks, timing, and skill
weapons, fuel, countermeasures, and station assignments
start state, airdrome, parking, recovery, and divert
coordinates, routes, altitudes, and speeds
weather, time, visibility, and wind
triggers, checkpoints, goals, success, and failure
briefing, narrative, and packaged resources
realism, scripting, and performance constraints
output path
```

Never fill an omitted field with a consequential assumption without labeling
it. Never change a user-specified aircraft variant, map, weapon, start mode, or
player experience silently.

## 2. Gate on real capabilities

Run:

```powershell
python Tools\dcsmizzer.py capabilities
python Tools\dcsmizzer.py evidence-readiness --help
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
```

For a MIZ request, the available product operation is low-level assembly from a
complete build spec. The Agent remains responsible for research, scenario
design, and authoring the complete low-level tables. Natural-language plan
compilation and campaign generation are unavailable. Exact-MIZ runtime
validation exists only through the explicit-opt-in isolated bridge and is
ready only after a passing version/hash-bound collection.

Implementation and readiness are separate. When a current content-addressed
bundle exists, `evidence-readiness` must pass every domain used by the decision;
otherwise create and verify a snapshot first. Pass the exact runtime manifest
and physical-terrain source again whenever those bundled domains are required;
an omitted external source is unavailable, not implicitly current. An
implemented upstream reader is not ready evidence until `upstream-status`
exits zero. If it does not, run
`upstream-prepare --cache-root output\upstream`, then rerun status. Only
`upstream-prepare` may contact the network or write that cache; add `--offline`
to forbid network access. The fixed locks and failure semantics are in the
[upstream source command details](reference/upstream-source-commands.md).
Branch movement never changes a product pin by itself. For dependency
maintenance, run `upstream-promotion-audit` against one exact clean candidate
checkout, preserve its report, review every consumed-model change, and complete
the separately recorded repository regression and post-lock evidence sequence.

## 3. Build an evidence ledger

Follow [evidence.md](evidence.md) and [tools.md](tools.md). Resolve, at minimum:

1. use `terrain-catalog` to separate the named product/region from its exact
   `mission.theatre`, then run `terrain-coverage` with
   `output\upstream\pydcs` and
   `output\upstream\briefing-room-for-dcs` after a successful
   `upstream-status`. If
   the user named a map, this query must include `--terrain`; if no map was
   named, use the compact default catalog, select one candidate, and rerun with
   its exact `--terrain`. Retain every source conflict. For a
   dual-source noninstalled terrain, use pydcs for construction and
   BriefingRoom as an independent check. For a BriefingRoom-only terrain, use
   exact BriefingRoom records. Never merge a pydcs package name with a
   conflicting DCS ID;
2. installed DCS version and terrain/module presence. Installed terrain data is
   higher authority when present, but the installed map list is not the
   allowed map list;
3. plugin IDs and literal flyable mappings with `dcs-modules`, plus literal
   service country/year for an era-sensitive selection when declared. An empty
   literal service list is unresolved static evidence, not a historical
   contradiction; use a version-matched official source and retain the warning
   rather than substituting another aircraft;
4. country identifier and numeric ID;
5. exact unit type in the correct one of the five categories, field shape, and
   supported observed tasks. Use `pydcs-units` for commit-bound discovery and
   exact lookup, then current installed/real-MIZ evidence when available;
   for a flyable/full-fidelity request, the exact type must also have observed
   `Player` or `Client` use;
6. exact loadout station/CLSID/settings assignments. Prefer a complete
   installed preset and require `dcs-payload-match` to classify the entire
   authored composition as `exact_observed_preset`; do not combine pairs from
   unrelated presets. Use `pydcs-aircraft` only as a commit-bound
   cross-check/fallback rather than installed runtime proof;
7. exact airdrome/start/parking/coordinate relationship. Prefer initialized or
   same-version real-MIZ evidence. Otherwise query `pydcs-airports` and
   `br-airbases` under the selection policy from step 1; retain missing
   heading/elevation, terminal-fallback, and cross-source limitations;
8. bounded candidate ground positions with `br-spawnpoints` only when useful;
   treat them as planning points. For a physical placement, scenery landmark,
   or low-level route, require explicitly theatre/declared-version-bound
   initialized evidence and run
   `placement-check`, `landmark-search`, or `terrain-corridor`. A generated
   terrain probe and its log extractor do not start DCS. Even after an
   authorized manual run, that probe can prove sampled points, sampled
   corridors, and positive scenery instances but deliberately cannot prove
   negative ground-collision coverage; placement needs a stronger initialized
   export or remains unresolved;
9. authoritative WGS-84 source and version-appropriate coordinate conversion
   for requested real-world target/city points. Use beacon-fitted
   `dcs-coordinates` on a locally installed terrain; otherwise use the
   commit-bound pydcs projection, or `br-coordinates` for an exact
   BriefingRoom-only theatre, and retain its unvalidated-runtime warning.
   Require the reported BR-derived authority and validated fit; Afghanistan
   fails closed and must remain unresolved;
10. one exact `dcs-weather` current Mission Editor preset. Require both
    `validation.fields_complete` and `validation.consistent`; retain its
    authored wind fields, field-integrity diagnostics, and the
    `evaluated_fields` scope of its precipitation, temperature, fog, and dust
    checks. Do not treat BriefingRoom climate/INI values as weather authority;
11. waypoint action and nested task shapes needed by the scenario, including
    real AI engagement/escort/strike behavior rather than briefing prose;
12. for a MiG-29 native-GCI request, run `dcs-gci` and preserve the exact
    station type, `ActivateGCI` task, declared country, compatible radar,
    channel, responsibility area, and player-only guidance limitation.

Keep discovery output bounded throughout this pass. Use the sequence compact
catalog -> exact type/airport -> one station/parking/preset. Use exact filters
and `--limit`; request the explicit `--details` or `--full` shown by current
command help only when needed. Redirect every detailed report to a working
file, then inspect only the selected records.

Use the current static sources first, then link them to parsed real-mission
observations. For aircraft research, include `--category plane`. Record all
filters and coverage counts. An empty result is unresolved evidence, not a
license to invent.

## 4. Design the scenario

Only after the exact values are resolved, design:

1. order of battle and globally unique group/unit IDs and names;
2. verified starts, routes, tasks, timing, and recovery;
3. player and AI payloads;
4. weather and environmental settings supported by observed structure;
5. native GCI ground assets and responsibility geometry when requested,
   separately from optional command-post text;
6. triggers, success/failure checkpoints, and mission goals expressible by the
   finite compiler, or separately verified complete low-level logic;
7. complete localized briefing text and optional resources;
8. a deterministic seed and provenance record;
9. an `expect` contract covering every critical user constraint, including one
   exact `expect.roles` entry bound to every authored group ID.

If an exact variant or compatibility remains ambiguous, stop for that material
choice. For example, a family name that maps to several installed internal
types is not an exact aircraft selection.

Design terminal outcomes with conservative mutual-exclusion guards. Put
failure-writer rules before the success writer, guard every failure writer
with the success flag being false, and guard the success writer with every
failure flag being false. Do not use `start` rules for terminal writers and do
not reset or assign another value to a terminal flag. A
`terminal_outcome_dataflow.guard_order_contract_passed=true` result proves
only that the authored guards and order exist; it does not prove DCS runtime
mutual exclusion or temporal reachability.

## 5. Author the build spec

Read [build-spec.md](build-spec.md) completely. The build spec must contain the
full `mission`, `options`, `warehouses`, `dictionary`, and `mapResource`
tables. The builder does not add DCS defaults or infer missing fields.
`warehouses` must include both `airports` and `warehouses` tables.

For a user mission, set:

```json
{
  "quality": {
    "profile": "complete_scenario"
  }
}
```

The default `technical_fixture` profile is for low-level fixtures, not a
complete requested mission. Under `complete_scenario`, every warning is fatal.
The strict contract requires complete briefing and core shapes, deterministic
provenance, finite compiled logic, success and failure goals, actionable AI
waypoint tasks, group-bound role contracts, profile-required finite
flying-unit/payload fields, and warehouse coverage for every used airdrome.

The mission core must also carry the observed current runtime shell documented
in [mission-format.md](mission-format.md#complete-profile-runtime-shell):
`coalitions`, `currentKey`, `failures`, `forcedOptions`, `groundControl`,
`map`, `maxDictId`, blue/red picture tables, and complete blue/red
name/bullseye/nav/country side shapes. Include every used country ID in the
matching dense coalition-membership array. Empty tables are still explicit;
do not omit this shell merely because the serializer accepts a smaller
technical fixture.

Generate current sanitized starting tables instead of copying them from a
private mission:

```powershell
python Tools\dcsmizzer.py dcs-options-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --full-sim

python Tools\dcsmizzer.py dcs-warehouse-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --airdrome-id VERIFIED_ID
```

Keep `mission.requiredModules` as an explicit table. Empty is valid and is the
dominant current real-MIZ observation. Do not infer an entry merely because a
Player/Client aircraft belongs to a module. If evidence requires a nonempty
entry, use only an exact string ID mapped to the identical string.

For supported common trigger and goal predicates, author top-level `logic`
with schema `dcsmizzer.miz-logic/v1` and omit `mission.trigrules`,
`mission.trig`, `mission.goals`, and `mission.result`. The builder compiles
those fields and validates common ID references. Never put trigger rules or
goals under `mission.triggers`. The compiler preserves each goal's global
numeric key in the applicable side-specific result tables; do not reindex
those sparse side tables by hand.

Within `logic.trigger_rules`, keep failure writers before the success writer.
Every failure writer must include `c_flag_is_false` for the success flag; the
success writer must include `c_flag_is_false` for every failure flag. Goals
then read those distinct terminal flags. Terminal writers must not use
`kind="start"`, and no finite action may reset a terminal flag or assign a
value other than true/`1`. Do not rely on rule prose or scoring alone. Require
the reported guard/order contract, while retaining
`runtime_mutual_exclusion_proved=false` and
`temporal_reachability_proved=false`.

Use only an exact observed first-waypoint `type`/`action` pair from
[mission-format.md](mission-format.md#starts-coordinates-and-parking). A
ground-area start needs no facility reference. A linked runway/parking start
must resolve to a same-coalition static or ship unit, and an `Escort` task must
target a different friendly plane group.

Use normal JSON arrays for dense one-based Lua arrays. Use `$fields` for sparse
numeric or mixed-key tables. Do not use JSON `null`.

The `provenance` object should identify the installed DCS version and the
static/observed reports used. Do not put private absolute evidence paths,
mission names, briefing text, or per-file evidence hashes into repository
documentation.

## 6. Audit exact evidence relationships

Run the documented `audit-spec` command with both locked cache roots and,
when available, the separately named current installed terrain. It must return
exit code 0 before packaging. Review every warning. For a noninstalled terrain,
omit `--installed-terrain`; preserve the resulting
`installed_terrain_crosscheck_not_run` warning rather than substituting a map.
When an acknowledged locked source participates in a required determination,
an absent, dirty, wrong-remote/commit/tree, or otherwise unready cache is a
hard audit failure rather than a provenance warning.

This catches common namespace and transcription errors that a self-consistent
`expect` contract cannot catch, including an invented cloud preset/base,
`GroundAttack` used where `group.task` requires `Ground Attack`, an unsupported
station/CLSID pair, swapped/guessed parking identifiers, or a native GCI
  station authored for a country absent from its current declaration. It also
  checks exact unit categories, fuel/countermeasure bounds, aircraft property
  keys/types, and the selected upstream terrain/parking authority. The
  structural gate requires the `ActivateGCI` chain and a compatible radar, but
  neither check decides whether GCI geometry, targeting, and AI behavior are
  tactically effective; compare those against the constraint ledger yourself.

## 7. Build and verify

```powershell
python Tools\dcsmizzer.py build-miz spec.json output\mission.miz `
  > output\build.json
python Tools\dcsmizzer.py verify-miz output\mission.miz --spec spec.json `
  > output\verify.json
```

Both commands must return exit code 0. Read the JSON; do not rely on the exit
code alone. Keep the full JSON on disk. Use
`report-summary output\build.json` and
`report-summary output\verify.json` for bounded review; it does not rerun
validation. Inspect only selected full-report fields needed to resolve a
failure. Confirm:

- archive and CRC checks passed;
- all five core tables parsed and equal the spec;
- the plaintext theatre member matches;
- resources are complete;
- limited structural checks are valid;
- every declared scenario-contract check passed;
- `quality.profile` is `complete_scenario` and its quality gate passed;
- `review_warnings_clear` is true; warnings are fatal for this profile;
- `runtime_valid` is `null`.

Use `--force` only when replacement of that exact output is intended. The
builder validates a same-directory candidate through the open file handle and
then performs an atomic filesystem path update. This is not an end-to-end
atomicity guarantee against an attacker who can write in that directory:
require `publication.atomic=false`,
`publication.filesystem_path_update_atomic=true`,
`publication.candidate_identity_bound_to_open_handle=true`, and
`publication.trusted_directory_required=true`, and use a trusted output
directory. On a failed build, require `publication.published=false` and confirm
the report says the old output was preserved or the new output is absent.

## 8. Inspect the finished archive independently

Run:

```powershell
python Tools\dcsmizzer.py inspect output\mission.miz > output\inspect.json
python Tools\dcsmizzer.py report-summary output\inspect.json
```

Keep the complete inspection report on disk. Open only the needed fields and
check the resulting counts, types, CLSIDs, slots, routes, task IDs, triggers,
goals, briefing size, and missing resources against the design ledger.
Require nonzero top-level trigger and goal counts for a mission whose request
includes success/failure checkpoints. Confirm that every authored group is
role-bound and that the generated AI route tasks, timing, landing/recovery, and
warehouse airdrome references survived packaging.

## 9. Report completion honestly

Use [validation.md](validation.md). State exactly what was generated, which
source versions were used, which checks ran, which could not run, and what
uncertainty remains.

Without an actual DCS load, say “built and statically verified,” not “playable,”
“DCS-valid,” or “complete.” Do not start DCS unless the user separately
authorizes a runtime-validation workflow and a product facility exists.
