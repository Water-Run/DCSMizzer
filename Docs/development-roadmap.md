# DCSMizzer development roadmap

- Status: planning baseline; the milestones below are not implemented capability
  claims.
- Baseline date: 2026-08-05 (Asia/Shanghai).
- Scope: development after the survey, low-level generator, and static-validation
  groundwork.
- Current capability boundary: [capabilities.md](./capabilities.md).
- Evidence and conflict policy: [evidence.md](./evidence.md).
- Baseline issue review:
  [ISSUE-REVIEW-2026-08-05.md](../output/survey-verification-2026-08-05/ISSUE-REVIEW-2026-08-05.md).

This document records the intended development order, dependencies, acceptance
gates, and deliberate non-goals. It does not override the current capability
report. A milestone becomes a product capability only after its implementation
and corresponding validation have actually run.

## Executive decision

DCSMizzer already has a substantial low-level MIZ toolchain. Its next critical
path is not more unauthoritative static breadth, a chat interface, or campaign
generation. It is a version-bound evidence and runtime feedback loop:

```text
evidence lifecycle
    -> isolated DCS runtime bridge
    -> initialized registries and terrain evidence
    -> tiered runtime validation
    -> scenario intent and resolved-plan IR
    -> supported mission archetypes
    -> campaign generation
```

Static CI and evidence maintenance span every milestone. Briefing media is an
optional branch after the scenario IR exists; Mission Editor resave is a
separate feasibility branch after the runtime bridge exists.

The design objective is to move from "a tool can construct a self-consistent
MIZ" to "an Agent can produce an explainable, reproducible scenario that the
specified DCS version has accepted at a declared validation tier."

## Baseline reality

### Implemented foundation

The repository currently provides, among other facilities:

- safe MIZ archive inspection and parsing;
- deterministic construction of the five core Lua members plus resources;
- low-level build-spec auditing, construction, read-back verification, and
  structural checks;
- installed-DCS, pydcs, BriefingRoom, observed-mission, weather, payload,
  module, airbase, coordinate, parking, and spawn queries;
- terrain catalog and bounded physical-terrain probe consumers;
- CMP parsing and corpus investigation;
- locked upstream source-cache preparation and status checks.

The current build contract, `dcsmizzer.miz-build-spec/v1`, is a useful compiler
target. It is not a model of user intent or of the technical decisions that
resolve that intent.

Verification rerun on the baseline date produced:

- product tests: 362 passed, 1 skipped;
- survey tests: 37 passed;
- English prompt catalog: 147 source blocks and 186 headings;
- Chinese prompt catalog: 147 source blocks and 186 headings;
- repository-facing document links: 20 files passed before this roadmap was
  added.

The skipped product test requires a Lua 5.5 executable that was not available;
it was not a product-test failure.

### 2026-08-26 release-candidate verification

After the runtime bridge, terrain-probe MIZ instrumenter, coordinate
hardening, pydcs pin promotion, and coastline-planning work were integrated,
the release candidate passed:

- 442 product tests, with one Windows-only open-path replacement race test
  skipped because the platform denies replacing that already-open temporary
  path;
- all 37 survey tests;
- all Ruff `E`, `F`, and `B` checks over product code and tests;
- Python bytecode compilation over product and survey code;
- 147 source blocks and 186 headings in each bilingual Prompt catalog;
- all links in 23 repository-facing documentation files;
- Lua 5.5 syntax checks for the rendered runtime Hook and both generated
  Sinai/Caucasus terrain probes;
- both locked upstream-cache profiles, including pydcs
  `e20f328390aecaac2a7f82444b4f5a96ac6bb2c3`, with zero unusable sources.
- the content-addressed evidence lifecycle's stable-pass, tamper, canonical-
  manifest, unexpected-file, wrong-domain-schema, producer/source-race,
  transactional preflight, current-coverage, content-level payload/upstream-
  lock drift, dirty-producer, partial-collection, historical-drift, stale-
  domain, and CLI exit-code fixtures.

The DCS runtime limits recorded below remain external validation gaps; passing
the static release suite does not upgrade the blocked exact-MIZ probes to V2
or V3.

### Current DCS evidence

The local Steam installation reported:

- DCS product version `2.9.28.26385`;
- Steam build `24431605`;
- installed aircraft products: F-16C, JF-17, M-2000C, MiG-29 Fulcrum,
  Su-25T, and TF-51D;
- installed terrain products: Caucasus, Germany Cold War, Kola, and Sinai;
- 143 default-payload files and 141 observed unit types, with one payload parse
  failure and explicitly incomplete compatibility coverage.

The product version matches Eagle Dynamics' 2026-07-28 entry in the
[official changelog](https://www.digitalcombatsimulator.com/en/news/changelog/).
The repository's recorded installation baseline is still `2.9.28.26283`, so
evidence drift is already present and must be handled by product design rather
than by operator memory.

The current DCS installation also contains
`<DCS installation>/API/Sim_ControlAPI.md`. It documents supported GUI-state
hooks under `$WRITE_DIR/Scripts/Hooks`, `Sim.setUserCallbacks`, mission
load/start/stop callbacks, slot and mission inspection, game events, mission
results, log access, and process exit. It marks `net.dostring_in` obsolete and
unsafe. The runtime design must use the supported callback surface and must not
depend on that obsolete interface or on desanitizing mission scripting.

DCS supports selecting a separate Saved Games profile with `-w`, as documented
in the [official custom settings FAQ](https://www.digitalcombatsimulator.com/en/support/faq/custom_settings/).
This makes a disposable `Saved Games/DCSMizzer-<run-id>` profile the required
boundary for automated runtime work.

### Mission and campaign corpus

The following roots were searched read-only:

| Root class | MIZ instances | CMP instances | Important limit |
| --- | ---: | ---: | --- |
| Installed DCS content | 648 | 5 | Only locally installed products |
| `Saved Games/DCS` | 76 | 0 | User-local coverage, not a public corpus |
| `.develope/official-campaigns` mirror | 144 | 5 | Overlaps installed content |
| Six acknowledged upstream repositories | 182 | not counted as campaign corpus | Commit-bound third-party samples |

The completed survey covers 1,050 MIZ instances representing 904 unique
contents, and 10 CMP instances representing 5 unique CMP contents. All surveyed
MIZ archives passed the survey's archive safety and CRC checks, and their
mission tables parsed. The corpus contains 14 current theatre identities in
union and substantial group, waypoint, payload, trigger, goal, Player, and
Client-slot evidence.

This is sufficient for mission-structure modelling and an initial set of
mission archetypes. Five unique CMP files are enough for a basic CMP model, but
not enough evidence for broad dynamic-campaign claims.

### Upstream status

Six acknowledged upstream clones were clean when inspected. Product code
currently consumes locked pydcs and BriefingRoom source caches. The locked
pydcs master commit matched the inspected remote master; the locked
BriefingRoom commit was behind the inspected remote main branch.

Upstream movement is not itself a reason to update a product pin. A pin is
promoted only after a source diff, data-model comparison, compatibility run,
and regression validation. Dirty clones must continue to fail closed and must
never be reset or cleaned automatically.

### Remaining issue classes

| Issue class | Current state | Primary milestone |
| --- | --- | --- |
| A1/A2: no DCS runtime closure | `runtime_valid` remains unknown | M1 and M3 |
| B1: no natural-language planning layer | only low-level authored specs exist | M4 |
| B2: no campaign generation | CMP is inspectable, not generated | M6 |
| B3: no initialized complete registries | static and upstream views are partial | M1 and M2 |
| C1: no collected physical runtime exports | probe production/consumption exists | M2 |
| C2: zero-preset payload ambiguity | no authoritative general exemption | M2 |
| C3: evidence coverage is uneven | corpus and installed products differ | M2 and M5 |
| C4/C5: module and identifier drift | sources can disagree | M0 and M2 |
| D1-D3: version and revalidation drift | refresh remains manual | M0 and M7 |

## Evidence authority

Use the source closest to the technical decision. The default authority order
for generation is:

```text
initialized export from the target DCS version
    > parsed official mission from a compatible DCS version
    > inspected, locked upstream implementation
    > versioned survey snapshot
    > explicitly labelled static inference
```

This is not an instruction to merge the sources. When they disagree, the
resolved plan records the conflict, versions involved, selected authority, and
reason. A lower-authority source may fill a field only when the higher-authority
source does not make an incompatible claim and the remaining uncertainty is
visible.

## M0: evidence lifecycle and reproducible baselines

**Implementation status (2026-08-26): bundle lifecycle and bound attestations
implemented; exit gate partially satisfied.** Product commands now perform
two-pass stable collection into local content-addressed bundles, verify
canonical manifests and exact artifact membership/hashes, compare recognized
historical/current evidence, and gate
current/stale/incomparable/partial/blocked decision domains. Exact runtime
manifests can be revalidated into path-free attestations; physical-terrain
files can be validated and bound by full source and finite-coverage hashes
without embedding raw records. Dirty producers, blocked domains, partial
collection, changed inputs, and incompatible source scopes fail closed. The
recorded `2.9.28.26283` baseline versus current `2.9.28.26385` comparison is
machine-generated rather than prose-only. Ordinary unbundled reports do not
yet carry a bundle reference, and the upstream pin-promotion protocol remains
incomplete, so M0 is not marked complete.

The clean reference run from producer commit
`5fdbeb4df86d0e07d1457e92779375682dc44d87` collected DCS
`2.9.28.26385` / Steam build `24431605` twice without drift or collection
failure. Its local-only bundle ID is
`db6717b76df16db77988bc1fb64077dca69f34318d6492b1d7d30293a774bfff`
and its canonical manifest SHA-256 is
`41c9c2dfe555cc4d17a7585fe67ed2af66bc6df97f3f5b3d1ae5e594087eb90e`.
All 11 artifacts and 188,184 bytes verified. Current complete-domain readiness
passed for installation, countries, weather, capabilities, and both locked
upstreams. The default broad gate correctly remained non-ready because static
module declarations, payload observations, and all four installed-terrain
airfield views are partial authority. The raw bundle remains ignored and was
not committed.

### Goal

Make every registry, planning, generation, and validation result traceable to
the exact DCS and upstream inputs that produced it. Prevent stale or mixed
evidence from being silently treated as current.

### Deliverables

1. `EvidenceManifest/v1`, recording at minimum:

   - DCS product version, distribution, and distribution build;
   - executable and task-relevant DCS API/Lua source hashes;
   - selected Saved Games profile and terrain identity where applicable;
   - relevant installed module identities;
   - upstream repository, branch, and commit bindings;
   - DCSMizzer commit and schema versions;
   - run ID, timestamp, producer, coverage, and collection outcome.

2. Content-addressed local evidence bundles.

3. Evidence comparison and invalidation:

   - compare old and new DCS installations;
   - identify unit, payload, module, weather, airfield, and API changes;
   - reject a stale bundle when the requested decision requires current data;
   - preserve old bundles for reproducing historical artifacts.

4. A readiness report showing which capabilities have current evidence and
   which are stale, absent, partial, or blocked.

5. An upstream pin-promotion protocol based on diff and validation, not an
   automatic "latest commit" policy.

### Storage and licensing policy

Raw initialized DCS exports may contain data that must not be redistributed.
They remain local and ignored by Git unless a specific redistribution review
permits otherwise. The repository should contain schemas, hashes, aggregate
statistics, synthetic fixtures, and minimal legally distributable examples.

### Exit gate

- The `2.9.28.26283` to `2.9.28.26385` drift is represented by evidence diff,
  not merely changed prose.
- Every report identifies its evidence bundle and authority tier.
- Incompatible evidence versions fail closed.
- Historical reports remain reproducible with their original bundles.
- A BriefingRoom pin update or retention has a recorded compatibility result.

## M1: isolated DCS runtime bridge

**Implementation status (2026-08-26): implemented and exercised.** The product
now has separate prepare/run/collect commands, disposable `-w` profiles,
supported GameGUI Hooks, Steam/standalone launch handling, exact process and
input hash binding, bounded cleanup, and aggregate initialized-registry output.
A Steam DCS 2.9.28.26385 / build 24431605 aggregate run passed with no
collection failure reasons. Raw local profiles/logs are not committed.

### Goal

Safely launch an explicitly authorized, isolated DCS process, collect
run-bound structured evidence, and terminate without modifying the DCS
installation or the user's ordinary Saved Games profiles.

### Command boundary

The product interface should separate preparation, execution, and collection:

1. `runtime-prepare` creates the disposable profile, hook bundle, manifest,
   command preview, and expected outputs. It never launches DCS.
2. `runtime-run` launches DCS only after explicit external-run authorization.
3. `runtime-collect` verifies and parses results for the exact run ID.

Names are provisional, but the permission and lifecycle separation is not.

### Required controls

- Dry-run by default.
- Explicit authorization for every DCS launch until a future, separately
  approved automation policy exists.
- A resolved and checked disposable `-w DCSMizzer-<run-id>` profile.
- No writes under the DCS installation or ordinary `Saved Games/DCS*`
  profiles.
- No copying or modifying existing user hooks.
- Process-start, mission-load, simulation-start, run, and shutdown timeouts.
- Crash, startup error, hook-load error, result corruption, and timeout
  classification.
- Run-ID and artifact-hash binding for every log and result.
- Bounded log capture and privacy redaction.
- Fail-safe process cleanup limited to the exact process started by the run.
- Supported `Sim` callbacks only; no `net.dostring_in` or mission-script
  desanitization.

### First integration experiment

Productize the existing development-only
[runtime registry probe](../.develope/survey/runtime/runtime_registry_probe.lua)
as a bounded aggregate exporter. The first authorized run should prove only
that it can initialize and report stable counts for countries, unit types,
weapon CLSIDs, tasks, categories, flyable aircraft, pylon stations and
launcher edges, unknown launcher CLSIDs, and task-capability edges.

Exact record export follows only after this lifecycle succeeds.

### Exit gate

- Synthetic-process and synthetic-log tests cover all lifecycle outcomes.
- An authorized run against the current DCS installation uses an isolated
  profile and emits a schema-valid result.
- The result binds the current DCS version, relevant source hashes, run ID, and
  producer version.
- Normal user profiles and the DCS installation are unchanged.
- Cleanup is safe after success, failure, and timeout.

## M2: initialized registries and terrain evidence

**Implementation status (2026-08-26): partial.** Aggregate initialized-registry
runtime counts, bounded physical-terrain consumers/probes, and privacy-safe
bundle attestations exist. The staged initialized record export, referential-
integrity graph, full payload/launcher resolution, and per-installed-terrain
initialization records below do not yet exist.

### Goal

Replace static guesses and silent cross-source joins with version-matched data
from an initialized DCS environment.

### Registry scope

Export in bounded stages:

1. countries, coalitions, services, categories, unit types, and attributes;
2. flyable/AI-only state, supported tasks, and default task;
3. pylon stations, launchers, CLSIDs, launcher settings, and weapon links;
4. fuel, chaff, flare, radio, livery, `AddPropAircraft`, DTC/data-cartridge,
   and other unit-shell defaults needed for safe construction;
5. provenance and unknown-field preservation for values not yet modelled.

The serializer must reject or safely represent cycles, functions, userdata,
excessive depth, excessive node counts, and oversized output. Stable ordering
is required so two equivalent exports produce useful diffs.

### Terrain scope

Initialize each installed terrain separately and collect, where the current
terrain API provides them:

- exact theatre identity;
- airdrome identifiers and metadata;
- runway geometry;
- parking/stand identifiers, dimensions, and supported categories;
- version-bound terrain, road-network, height, surface, and scenery capability
  declarations.

Continue using bounded point, placement, corridor, and scenery requests from
[terrain-physical.md](./terrain-physical.md). Do not pursue a purportedly
complete continuous terrain/collision database: a bounded probe cannot prove
negative collision or scenery coverage over an entire map. Every terrain
result states its actual spatial and API coverage.

### Payload and identifier resolution

The initialized export becomes the highest authority for pylon compatibility
and DCS identifiers. Static presets and upstream libraries remain discovery
and comparison sources.

A zero-preset type such as the observed E-2C case is accepted only when the
initialized registry or a compatible Mission Editor-authored artifact proves
the correct empty/default payload shape. There must be no generic "zero
presets means valid" exemption.

### Exit gate

- Exported references pass unit/category, task, pylon, launcher, and CLSID
  referential-integrity checks.
- Unknown and unresolved CLSIDs are counted and listed without silent removal.
- Each installed terrain has a separate initialization and coverage record.
- Query and audit commands prefer compatible initialized evidence and explain
  every fallback.
- DCS, pydcs, BriefingRoom, and observed-mission identifier conflicts are
  reported, not blended.
- `requiredModules` decisions are derived and auditable.

## M3: tiered runtime validation contract

**Implementation status (2026-08-26): partially implemented.** Exact-MIZ
load/start/smoke collection and DCS Export coordinate checks exist with unit
and failure-injection coverage. The current-session Sinai/Caucasus mission lane
remains unpromoted: an initial Steam launch requested authority to evict another
active session, and later isolated retries reached exact DCS processes but the
DCS Steam-authorization request failed with SSL/timeout errors before Hook
initialization. No other session was evicted, and static instrumentation
success is not counted as V2/V3.

### Goal

Replace an ambiguous runtime Boolean with explicit evidence levels.

| Tier | Meaning | Minimum evidence |
| --- | --- | --- |
| V0 | Static validity | Schema and authored-spec audit pass |
| V1 | Archive validity | Safe archive, required members parse, read-back checks pass |
| V2 | DCS load validity | DCS loads the exact artifact without a blocking initialization error |
| V3 | Simulation smoke validity | Simulation starts and remains stable for the declared interval |
| V4 | Behavioural checkpoint validity | Instrumented expected events/checkpoints are observed |
| V5 | Human playtest validity | A recorded human playtest covers the declared scenario path |

No lower tier implies a higher tier. Validation reports retain the separate
results rather than collapsing them to one `true` value.

### Exact-artifact smoke checks

V2/V3 validation must bind to the generated MIZ hash and check at least:

- mission and theatre identity;
- coalition, group, unit, and player-slot initialization;
- missing module, resource, payload, warehouse, and Lua errors;
- mission-load and simulation-start callbacks;
- stability for a declared frame or time interval;
- mission result, normal stop, timeout, crash, or forced-exit reason.

### Behavioural conformance missions

Create small deterministic fixtures rather than one all-purpose scenario.
Initial fixtures should cover:

- delayed activation and static trigger linkage;
- intercept/CAP and escort task activation;
- bombing/strike task activation;
- flag, message, success, failure, and terminal logic;
- GCI/AWACS linkage;
- carrier spawn and recovery;
- Client/Player slot enumeration.

Ordinary user missions receive non-invasive exact-artifact smoke validation.
Deeper behavioural claims require a fixture or an explicit telemetry contract.

### Mission Editor resave branch

Automated Mission Editor resave is a research spike after the runtime bridge,
not a prerequisite for V2/V3. It enters the product roadmap only after a small
prototype proves a stable, supportable save interface. Brittle GUI automation
must not be presented as an established capability.

### Exit gate

- One generated vertical-slice mission on a currently installed terrain
  reaches V3 against the current DCS version.
- Initial trigger and AI-task conformance fixtures reach V4.
- Runtime reports distinguish load, start, stability, behaviour, and human
  evidence.
- Static success is never described as runtime or playability success.

## M4: scenario intent and resolved-plan IR

### Goal

Provide the missing bridge between the user's scenario and the existing
low-level build specification. DCSMizzer is Agent-oriented; this milestone
defines narrow tools and auditable intermediate representations rather than
embedding an autonomous chat product first.

### `ScenarioIntent`

Represent only the user's requirements and permissions:

- era and date constraints;
- terrain and location;
- coalition and country;
- player module and player count;
- mission type and objectives;
- start state, weather, time, and intended duration;
- friendly support and threat constraints;
- realism and difficulty preferences;
- output and briefing requirements;
- forbidden substitutions and permitted substitutions;
- unresolved ambiguities that materially affect the scenario.

### `ResolvedScenarioPlan`

Represent the evidence-backed technical decisions:

- exact DCS types, countries, tasks, and module requirements;
- airdrome, runway, parking, coordinates, and placement evidence;
- pylon stations, launcher CLSIDs, quantities, and payload rationale;
- route, formation, timing, activation, and task details;
- trigger, result, success, failure, and finite-state logic;
- briefing and resource manifest;
- deterministic identifiers and seed;
- an `EvidenceRef` and decision reason for every material technical choice;
- rejected candidates, unresolved risks, and approved substitutions.

The compilation boundary is:

```text
ScenarioIntent
    -> evidence resolution and explicit decisions
    -> ResolvedScenarioPlan
    -> dcsmizzer.miz-build-spec/v1
    -> MIZ artifact
```

### Planner rules

- The same intent, seed, evidence bundle, and compiler version produce the
  same resolved plan and build spec.
- Every explicit user constraint is preserved or marked unresolved.
- A material substitution requires user approval before generation.
- The Agent uses narrow resolver commands instead of inventing low-level DCS
  fields.
- Generated artifacts are inspected back into semantic facts and compared to
  the intent and resolved plan.
- Direct use of the low-level build spec remains available for experts, but it
  does not bypass capability and evidence claims.

### First vertical slice

Use an installed, well-observed terrain such as Caucasus and select a locally
installed full-fidelity player type only after M2 resolves its exact registry.
The provisional scenario shape is:

- one cold-start Client slot;
- one AI wingman;
- one bounded hostile air package;
- takeoff, intercept, recovery, success, and failure flow;
- deterministic placement, route, timing, and seed;
- no carrier, dynamic campaign, or broad multi-role requirements.

This slice exercises player slots, parking, payloads, AI tasks, routes,
triggers, briefing, build, read-back, and runtime smoke without combining all
hard problem classes at once.

### Exit gate

- Intent audit proves every explicit constraint was preserved, rejected, or
  explicitly approved for substitution.
- Every material resolved field has provenance and a decision reason.
- Equal inputs produce an equal plan/spec artifact hash.
- Build, verify, inspect, V2, and V3 pass for the supported slice.
- The current capability matrix names this narrow support rather than claiming
  a general natural-language planner.

## M5: mission-archetype expansion

### Goal

Grow only through evidence-backed vertical slices with declared support
matrices.

Recommended order:

1. intercept and CAP;
2. strike and escort;
3. SEAD and CAS;
4. maritime and carrier operations;
5. helicopter and ground support;
6. multiplayer and Combined Arms-oriented scenarios.

The order increases complexity deliberately: airfield and route fundamentals,
then ground objectives and payloads, coordinated threats, moving platforms,
low-altitude terrain constraints, and finally multi-slot interactions.

Each archetype requires:

- structure observed in legitimately accessed real missions;
- a synthetic static fixture;
- at least one runtime conformance fixture;
- a matrix of terrain, unit family, task, start state, weather, logic, and
  achieved validation tier;
- explicit negative and untested coverage.

### Exit gate

An archetype is advertised only within its passing matrix. "All maps," "all
modules," and "all mission types" are not valid claims without corresponding
current evidence and runtime coverage.

## M6: campaign generation

### Goal

Build campaigns from already validated single-mission plans, while preserving
CMP compatibility and campaign continuity.

### Data model

- campaign bible and narrative constraints;
- mission dependency graph;
- campaign state variables;
- roster, resource, loss, and continuity ledger;
- score intervals, skip scores, branch conditions, and reachability;
- a `ScenarioIntent` and `ResolvedScenarioPlan` for every mission;
- campaign resource, localization, image, and provenance manifests.

### Delivery order

1. Lossless CMP parse/serialize round trip with raw Unicode and unknown-field
   preservation.
2. A three-mission linear campaign.
3. A four-mission score-branched campaign.
4. Roster and resource continuity.
5. More dynamic generation only after additional legitimate CMP evidence and
   progression validation exist.

### Exit gate

- Every relative mission and asset reference resolves within the campaign.
- Score intervals have no accidental overlap, gap, or unreachable branch.
- Every generated MIZ independently passes its required static and runtime
  tiers.
- The CMP parses after generation and preserves required Unicode, resources,
  and unknown fields.
- Progression and continuity rules have automated tests.

## M7: media, release engineering, and recurring verification

### Optional media branch

Briefing and campaign media use a provider-neutral artifact manifest containing
dimensions, format, hash, provenance, licence, and generation parameters.
Remote or billable generation requires explicit confirmation. User-provided
assets and deterministic placeholders remain valid fallbacks, so media never
blocks core mission construction.

### Continuous validation

Split automation into:

- ordinary CI: unit tests, schemas, synthetic fixtures, document checks,
  historical evidence replay, deterministic build checks;
- authorized Windows/DCS lane: installed-version discovery, registry probes,
  exact-artifact runtime smoke, and selected behavioural fixtures.

The second lane requires a legally installed DCS environment and must never be
implied by ordinary hosted CI.

### Capability publication

Generate the machine-readable support matrix and human-facing capability
summary from evidence and validation records. Documentation must not manually
promote a capability ahead of its passing gate.

After a DCS update:

1. mark version-bound runtime evidence stale;
2. run a bounded installation and API diff;
3. refresh initialized registries as required;
4. rerun the supported runtime matrix;
5. publish any reduced or restored support explicitly.

## First implementation iteration

The first implementation iteration combines the smallest useful parts of M0
and M1. It must not start the natural-language planner.

### Work items

1. Record an architecture decision for runtime isolation, authorization,
   evidence storage, privacy, and redistribution boundaries.
2. Define and test `EvidenceManifest/v1` and `RuntimeResult/v1`.
3. Implement runtime preparation and command preview without process launch.
4. Convert the existing aggregate registry probe into a bounded,
   schema-versioned product resource.
5. Implement run-ID creation, artifact/source hash binding, log extraction,
   result validation, timeout handling, and failure classification.
6. Test with fake processes, synthetic logs, truncated output, mismatched run
   IDs, corrupt JSON, timeout, crash, and partial cleanup.
7. Re-run all static validation.
8. Request explicit authorization before the first real DCS aggregate probe.
9. Use that result to estimate and design exact-record export; do not assume
   the aggregate prototype proves the full exporter.

### Definition of done

- No command launches DCS without explicit authorization.
- Preparation never writes outside its disposable run root.
- Execution does not touch the DCS installation or ordinary Saved Games
  profiles.
- Every result is tied to a run ID, DCS identity, producer, and relevant source
  hashes.
- Hook-not-loaded, process-not-started, mission-not-loaded, probe-failed,
  result-corrupt, timeout, crash, and normal completion are distinguishable.
- Automated tests pass before a real launch is requested.
- One authorized current-version run yields a readable aggregate result and
  safe cleanup.

## Deliberate non-goals for the next iteration

- A chat UI or direct prompt-to-Lua translation.
- A large dynamic-campaign engine.
- Treating static validity as playability.
- Generic payload exemptions used to conceal missing registry evidence.
- Silent merging of DCS, pydcs, BriefingRoom, and survey identifiers.
- Automatic adoption of the newest upstream commit.
- Committing full copyrighted DCS exports or mission assets.
- A purportedly complete continuous terrain or collision database.
- Product claims for Mission Editor automatic resave before a feasibility
  proof.
- Claims of compatibility with uninstalled or untested modules and terrains.

## Risk register

| Risk | Consequence | Control |
| --- | --- | --- |
| DCS internal Lua/API drift | Exporter or hook fails after update | Hash sources, probe capabilities, invalidate, fail closed |
| Steam/standalone/profile differences | Incorrect launch or evidence binding | Distribution-aware discovery and explicit profile manifest |
| Map/module entitlement | Runtime load cannot initialize requested content | Report entitlement separately; never substitute silently |
| Existing user hooks or settings | Contaminated result or user disruption | Disposable `-w` profile and no profile copying |
| Runtime nondeterminism | Flaky behavioural tests | Fixed seeds, small fixtures, bounded retries, separate smoke from behaviour |
| DCS launch cost | Slow feedback and oversized test matrix | Content-addressed evidence, targeted invalidation, tiered schedules |
| Upstream identifier drift | Incorrect joins and module declarations | Commit binding, conflict reports, runtime authority |
| Export redistribution limits | Licensing or copyright problem | Local raw bundles; commit schemas, summaries, and synthetic fixtures only |
| Mission/campaign copyright | Accidental redistribution | Read-only parsing and aggregate observations; never commit source assets |
| Sparse CMP corpus | Overgeneralized campaign model | Begin with linear/basic branching and expand evidence before claims |
| ME automation brittleness | False promise of resave validation | Keep as an isolated feasibility branch |
| Logs and paths contain private data | Privacy leak in reports | Bounded capture, redaction, no private filenames in committed evidence |

## Release gates

Progress is measured by evidence gates, not dates alone.

### Groundwork complete

- Current-version evidence lifecycle operates.
- Isolated runtime bridge operates.
- Initialized registry export is version-bound and consumable.

### Technical alpha

- One vertical slice compiles from intent through resolved plan to MIZ.
- The exact artifact passes V3 on the current supported DCS version.
- The result is repeatable with equal seed and evidence.

### Functional alpha

- At least three mission archetypes have static and runtime fixtures.
- Their positive, negative, and untested support matrices are published.

### Beta

- At least two terrains and two aircraft families are represented in the
  declared runtime matrix.
- A DCS update has exercised invalidation, refresh, regression, and capability
  republication.

### Campaign alpha

- A three-mission linear campaign passes CMP reference, per-MIZ validation,
  and available progression checks.

### 1.0

- The supported matrix is explicit and reproducibly validated.
- No critical runtime uncertainty is hidden behind static success.
- DCS and upstream update procedures operate without silent evidence mixing.
- Remaining limitations are published at the same granularity as supported
  capabilities.

## Roadmap maintenance rules

- Update this roadmap when dependencies, milestone scope, or exit gates change.
- Do not mark a milestone complete in prose before its validation artifacts
  exist.
- Record completed implementation in [capabilities.md](./capabilities.md) and
  the machine-readable capability output; keep this file focused on direction
  and gates.
- Preserve dated issue reviews as evidence snapshots instead of rewriting them
  to match later product state.
- Reassess milestone priority after the first authorized DCS probe, after each
  DCS version update that changes relevant APIs/data, and before campaign work.
