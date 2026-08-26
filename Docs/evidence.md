# Evidence and exact-data policy

This document is the **authority, provenance, fallback, and conflict policy**.
It is not the startup checklist or command reference. Start with
[quickstart.md](quickstart.md), select commands through [tools.md](tools.md)
and current CLI help, and return here only when choosing between sources or
recording uncertainty.

## Authority order

Use the source closest to the fact:

1. initialized, version-matched DCS or Mission Editor export;
2. current installed DCS data-only source;
3. parsed real missions from the same installed version;
4. current, commit-bound upstream source;
5. frozen survey/reference snapshots.

Primary Eagle Dynamics pages and changelogs are appropriate for current public
release, product, and patch facts. They do not replace installed internal IDs.

## Exact-data routing

| Needed fact | Product route | Coverage boundary |
|---|---|---|
| Locked pydcs/BriefingRoom readiness and candidate review | `upstream-status`; `upstream-prepare` only when not ready; `upstream-promotion-audit` before any pin decision | Exact fixed cache identity plus read-only clean fast-forward/diff/consumer-model review; an audit never authorizes a pin edit |
| Reproducible evidence snapshot, drift, and readiness | `evidence-snapshot`, `evidence-verify`, `evidence-diff`, `evidence-readiness` | Exact local bundle bytes and finite source scopes; verification does not authenticate the original producer or upgrade static evidence to runtime authority |
| Installed version and module directories | `dcs-static` | File presence, not entitlement or activation |
| Plugin ID, literal flyable type, and literal service country/year | `dcs-modules` | Static matching module sources only; absence can remain unresolved |
| Country identifier and numeric ID | `dcs-countries` | Current installed `db_countries.lua`, including reserved ID gaps |
| Unit types with static default presets | `dcs-payload-index` | Known data-only `UnitPayloads` sources only |
| One type's default station/CLSID/task presets | `dcs-payloads` | Observed presets, not complete compatibility |
| One complete authored payload versus installed defaults | `dcs-payload-match` | Strict whole-preset fingerprint; only an exact observed preset passes, never a compatibility matrix |
| Exact installed cloud-preset ID | `dcs-cloud-presets` | Literal current-install GUI presets; other weather fields are separate |
| Supported-field-complete installed Mission Editor weather preset | `dcs-weather` | Statically parsed preset and evaluated constraints; no unknown-field, rendering, mission-load, or runtime proof |
| Terrain airfield IDs/names with radio or beacons | `dcs-airbases` | Static radio/beacon union only; beacon positions are not airport centers |
| Native MiG-29A GCI station/task/radar construction | `dcs-gci` | Current static declaration + official training MIZ + installed manual; no gameplay proof |
| Current sanitized core-table starting shapes | `dcs-options-template`, `dcs-warehouse-template` | Current Mission Editor defaults/literals; authored policy and verified airdrome IDs remain required |
| Dated official products and their `mission.theatre` mappings | `terrain-catalog` | 18 surveyed product cards map to 14 current IDs; not live ownership, future-product, or physical-terrain evidence |
| Commit-bound upstream theatre identity graph | `terrain-coverage` | Explicit combination of two upstream catalogs; 14 IDs at those commits, not 14 DCS products |
| Generated terrain identity/projection | `pydcs-terrains` | 11 commit-bound packages; class-declared centers are untrusted metadata |
| BR-only theatre WGS-84 ↔ local coordinates | `br-coordinates` | Lower-authority projection derived from commit-bound airbase exports; 13/14 validated, Afghanistan fails closed |
| Generated unit declarations in all five categories | `pydcs-units` | Commit-bound source declarations, not a current initialized registry |
| Airport/runway/parking declarations when installed/observed evidence is missing | `pydcs-airports` | Lower-authority generated upstream data at the reported commit |
| Additional theatre/airbase/parking coverage | `br-terrains`, `br-airbases` | Lower-authority exported upstream data, including three DCS IDs absent from pydcs |
| Candidate ground-placement planning points | `br-spawnpoints` | Planning export only; no terrain, collision, road, or tactical validity |
| Minimum distance to a planning land-mass boundary | `br-coastline` | Commit-bound BriefingRoom sea-mask geometry only; an exact offset is globally remeasured but is not a current initialized-DCS coastline or surface result |
| Plane station/store cross-check | `pydcs-aircraft` | Lower-authority generated upstream data, not installed runtime compatibility |
| Complete authored-spec technical cross-check | `audit-spec` | Finite country/weather/task/pylon/parking evidence audit; no scenario or runtime judgment |
| Installed WGS-84 ↔ mission-local coordinates | `dcs-coordinates` | Beacon fit with inverse and whole-airfield holdouts plus explicit sample-domain/extrapolation diagnostics; no height, land-cover, authoritative coastline geometry, or placement proof |
| Exported point, footprint, corridor, or landmark checks | `terrain-point`, `placement-check`, `terrain-corridor`, `landmark-search` | Exact initialized-theatre evidence and queried samples only; declared-version provenance does not imply runtime attestation |
| Derived airfield operating footprint | `airfield-footprint` | Supplied initialized runway/parking/taxi evidence only; derived envelope, not an official boundary |
| Physical-evidence capture chain | `terrain-probe-script`, `terrain-probe-instrument`, authorized exact-MIZ run, `terrain-probe-extract` | Probe commands write only named artifacts; mission scripting cannot export airport geometry |
| Initialized aggregate registry evidence | `runtime-prepare`, authorized `runtime-run`, `runtime-collect` | Version/process/hash-bound aggregate counts; not complete registry records or a mission-runtime claim |
| Exact-MIZ V2/V3 evidence | `runtime-prepare`, authorized `runtime-run`, `runtime-collect` | Exact mission hash/name/theatre load, start, interval and declared DCS coordinate checks only; no general behavior or human-playtest proof |
| Exact-filtered anonymous type/category/task/field-shape relationships | `miz-registry` | Anonymous counts/shapes only from parsed evidence files matching caller-supplied filters |
| Payload/start/parking/coordinate relationships | `miz-registry` | Observed combinations only, not exhaustive |
| MIZ/CMP structure and counts | `inspect` | Static evidence, not runtime behavior |
| Complete unit/task/pylon registry | Version-matched runtime export | Not available in the current product |
| Complete runway/parking registry | Supplied initialized Mission Editor terrain evidence | Consumers exist, but no complete export is bundled or performed automatically; upstream queries remain fallbacks |

Command routing and links to bounded on-demand references are in
[tools.md](tools.md); current CLI help remains the syntax authority.

## Content-addressed evidence lifecycle

`evidence-snapshot` collects the current static installation, countries,
module declarations, default-payload observations, weather presets, every
installed terrain's static airfield radio/beacon view, current capability
matrix, and an optional locked-upstream status. It can additionally revalidate
exact prepared runtime manifests and validate physical-terrain evidence files.
Two complete passes must match before it creates a canonical local bundle. The
manifest binds a clean or dirty producer commit, DCS
product/distribution/build, executable/API hashes, artifact schemas, exact
bytes, authority labels, coverage, failures, and a collection run ID. The
directory name is its manifest content address.

`evidence-verify` recomputes the address and every artifact record, rejects
extra files, and rederives coverage labels from the bound reports. It proves
byte integrity and membership, not external authorship. `evidence-diff`
normalizes comparable domains; a changed source scope is explicitly
`incomparable_basis`. `evidence-readiness` then compares a verified bundle
with two matching new read-only collections and conservatively combines the
bundle and current coverage states. Fresh static bytes remain `partial` when
the underlying source cannot prove entitlement, full payload compatibility,
or a complete initialized airfield registry. A dirty producer or partial
collection cannot pass even an otherwise-current required domain.

Runtime bindings omit local absolute paths and raw logs while retaining the
exact manifest/execution/result/log hashes and a bounded result summary.
For Steam, they also retain the preparation-time raw appmanifest hash and its
path-free semantic identity; launch-time volatile metadata is not mistaken for
an app/build/install/state change.
Physical-terrain bindings validate the raw document and retain its complete
hash plus coverage hashes/counts without embedding potentially proprietary
samples, objects, or airfield geometry. Therefore the external raw terrain
file must still be retained locally to reproduce later physical queries.

Bundle contents remain under ignored local output and are not redistribution-
approved. Every JSON CLI response now declares an `unbound`, `self`, or
`bundle-current` evidence-reference state. External current binding is limited
to source-matched read-only commands with immutable mandatory domains, exact
current producer equality, and matching readiness fences around the query.
It binds the path-free query, domain artifact sets, and canonical intrinsic
report payload SHA-256. A later `report-summary` recomputes the last value and
must report `intrinsic_report_binding_matches=true` before the saved binding
claim is reused; this detects content drift but does not authenticate a file
received from an untrusted party.

The supported `python Tools\dcsmizzer.py ...` entrypoint re-enters Python in
isolated, no-site mode before importing product modules. Provenance-sensitive
commands are the evidence snapshot/verify/diff/readiness lifecycle, both
construction provenance commands, `report-summary`, all three runtime
commands, all three terrain-probe producer commands, and every invocation
carrying `--evidence-bundle`. They require a
clean ordinary index, reject every ignored or untracked entry under `Tools`,
and require every tracked
regular worktree file's Git-canonical content ID to equal its `HEAD` blob
before the product import. This deliberately accepts only Git's declared text
line-ending normalization, while `-text`/binary content remains byte-exact.
The check is fenced and uses isolated Git configuration. The trusted Python
interpreter, Git executable, operating system, and this small bootstrap remain
the local trust base; this is content binding for a controlled host, not
authentication of an entrypoint or machine supplied by an adversary. Direct
package imports do not provide this pre-import bootstrap property.

This binding context is orthogonal to the report's intrinsic authority and
cannot upgrade static/planning evidence to runtime proof. M0 remains partial.
New construction snapshots emit `construction-bundle/v2`. They require two
identical live audit reports and two identical transcripts before publication.
The transcript schema covers the complete 16-kind external query vocabulary of
`audit-spec` and stores every actual ordered request with strict canonical
parameters and a content-addressed response. Offline replay uses only the
sealed spec, sealed resources, and transcript; it must issue the same calls in
the same order, match the parameters and response bindings, and consume the
entire request stream without returning to the original DCS or upstream roots.
The exact replayed audit report must equal the captured intrinsic report before
build and verification proceed.

`construction-verify` validates v2 membership, hashes, evidence/report
bindings, and pipeline continuity under any producer. Audit, build, and static
verification replay occur only when the complete current producer identity
matches the manifest; otherwise their results remain unperformed/unknown and
the result is historical static integrity only. The v1 construction format is
still readable legacy evidence but has no audit-decision transcript, while
standalone legacy reports remain unsealed. Neither version runs DCS, so runtime
validity remains `null`. Native GCI specs are refused until their conditional
install/manual/training inputs have a sealed evidence domain. A content address
is not a signature or producer authentication. Current partial module, payload,
and airfield evidence also continues to block `static_release_ready`, even for
an otherwise exact v2 replay. See
[construction-validation-commands.md](reference/construction-validation-commands.md)
and [evidence-lifecycle-commands.md](reference/evidence-lifecycle-commands.md).

The evidence reference is CLI transport metadata, not a field inserted into
the underlying Python report or bundle artifact. When a saved standalone
report is compared, normalization ignores only this top-level transport field
so adding it does not create false semantic drift; the standalone file's raw
SHA-256 still changes and remains visible as exact physical-file identity.

## Installed static-source scope

The default-payload scan covers:

```text
MissionEditor/data/scripts/UnitPayloads/*.lua
CoreMods/aircraft/*/UnitPayloads/**/*.lua
Mods/aircraft/*/UnitPayloads/**/*.lua
CoreMods/tech/*/UnitPayloads/**/*.lua
Mods/tech/*/UnitPayloads/**/*.lua
```

The parser accepts only data-only Lua. It can resolve the installed task
constants used by these files and numeric-only local multi-assignments. A file
containing functions, loops, executable member calls, or unresolved identifiers
is rejected and listed under `parse_failure_sources`; never hide that gap or
execute the file to make the report look complete.

`dcs-payload-index` identifies exact unit-type strings and source coverage.
Call `dcs-payloads` for the exact type to obtain its station and CLSID details.
Neither command proves every legal pylon/store combination.

`dcs-payload-match` compares the complete authored station/CLSID table with
whole installed default presets using deterministic composition and configured
composition fingerprints. Only `exact_observed_preset` passes. Ambiguous,
custom pairwise-valid, duplicate-station, unknown-pair, metadata-mismatched,
and settings-unspecified results remain non-exact. The result is bound to the
installed version and source hashes. Lua last-write behavior is preserved, and
any parse failure matching the queried unit type or lacking a safe literal
unit-type hint keeps the evidence incomplete. A malformed payload table or
preset within the queried unit also blocks exactness because it could hide
another composition or store configuration. If a preset includes
per-store `settings`, supply them through the Python API; the CLI's
station/CLSID-only query cannot claim configuration equality.

`dcs-modules` links literal `declare_plugin` IDs and `make_flyable` types from
each static `entry.lua` to default-payload types under the same module
directory. Use it to resolve plugin and full-fidelity/player-type namespaces
without guessing, but do **not** infer `mission.requiredModules` from the
player aircraft or a plugin display name. Current real-MIZ observations show
that this table is normally present and empty; the rare nonempty observations
use exact string ID-to-identical-string entries. An unresolved/dynamic module
call remains listed, and directory presence still does not prove entitlement
or activation. Exact `--unit-type` reports also include literal
`declare_service_life` country/year records when present; an empty list leaves
the era fact unresolved.

External current-bundle binding is deliberately unavailable when
`--unit-type`, `--service-country`, or `--service-year` is present. Those
forms recursively read service-life files not represented by the current
modules snapshot artifact, so the CLI rejects their binding flags before any
query is dispatched. Their unbound intrinsic report remains usable within its
declared static scope.

Use `--service-country` and `--service-year` for era-sensitive aircraft
selection. A filter mismatch returns nonzero and must not be converted into a
silent country or variant substitution. When the exact module has no literal
service records at all, the static service fact remains unresolved rather than
contradicted; distinguish that case from an explicit record whose country/year
does not match.

`dcs-gci` is a narrow current-version query for the native full-fidelity
MiG-29A GCI feature. It cross-links the station's static declaration, the
official training mission's real `ActivateGCI` task shape, and the installed
manual's construction constraints. It is stronger than guessing from a task
name, but it still cannot prove terrain line of sight, reception, target
assignment, or runtime behavior. The current manual explicitly limits
instrument guidance to players rather than AI aircraft.

`dcs-cloud-presets` reads only literal preset records from the current install.
Use its exact ID for `mission.weather.clouds.preset`; a friendly display name
or an invented shorthand is not an internal preset ID. Resolve and contract
the remaining weather fields separately.

`dcs-weather` statically parses a bounded, supported-field view of Mission
Editor static and dynamic presets plus selected precipitation, temperature,
fog, and dust constraints. Use the bounded catalog to discover
`presets[].id`, then query that exact ID. An exact preset is usable only when
`validation.fields_complete` and `validation.consistent` are both true.
Retain `missing_fields`, `invalid_fields`, `unsupported_fields`,
`truncated_fields`, and `evaluated_fields` as diagnostics; consistency applies
only to the reported evaluated relationships. Source hashes and parse
diagnostics are also part of the evidence. The command does not execute Lua or
prove unknown future fields, terrain/date acceptance, rendered weather,
mission loading, or runtime behavior; Saved Games presets are outside its
scan.

`dcs-options-template` is the safe starting point for the authored `options`
table. It parses the current installed data-only default, replaces
`playerName`, and blanks local audio-device fields without returning their
values. `--full-sim` applies only its reported difficulty overrides.

`dcs-warehouse-template` emits the currently verified unlimited-mode airport
record shape. Its numeric airdrome keys are caller-supplied, so resolve them
first from exact terrain evidence. Neither template is a runtime-initialized
registry.

## Physical terrain evidence

Physical consumers accept only `dcsmizzer.terrain-physical-evidence/v1`.
Evidence can authorize a result only when its producer kind is an initialized
DCS/runtime, Mission Editor, or mission-scripting export and its theatre and
declared DCS version match the query. The evidence separately reports whether
that version identity was runtime-attested; a mission-scripting probe records
the script-generation installation and does not attest the runtime executable.
Planning coordinates, projection fits, GIS data, map rectangles, and nearby
mission observations cannot satisfy the physical gate. The current capability
report records zero committed runtime exports, so callers must supply the
exact export they use.

Every physical CLI query requires explicit theatre and declared-version
binding. `terrain-point` proves only one exported sample. `placement-check`
returns `sampled_placement_valid` from a center and corners, distinct sample
bindings, maximum pairwise sampled slope, conservative object bounds, and
exported airfield geometry. Positive obstacle clearance requires a search
explicitly declared complete for ground placement; its default airfield gate
requires a complete inventory and `geometry_complete=true` on every record.
`--allow-airfield` is an explicit waiver, not a pass. `terrain-corridor`
returns `sampled_corridor_clear` for a center trace and two lateral traces,
not every point or aircraft performance. `landmark-search` can prove a
returned object exists; a negative result requires complete query-volume
coverage to prove absence. None of these commands turns an unqueried area into
safe placement or makes a tactical judgment.

`airfield-footprint` derives an operational envelope only from a complete
initialized airfield inventory whose selected record declares complete
runway, parking, and taxi geometry; it is not an official airport boundary.
`br-airfield-footprint` remains commit-bound planning geometry and supplies no
physical validation; malformed or skipped source geometry makes it unusable.

`terrain-probe-script` writes a bounded Lua probe for later manual use, and
`terrain-probe-extract` writes hash-bound evidence from complete log markers.
Neither starts DCS, Mission Editor, or Lua. The mission probe uses bounded
3D-BOX scenery discovery, but ED does not specify whether `searchObjects`
selects by pivot or collision box; it therefore always reports ground-
placement completeness false. Mission scripting also cannot export runway,
parking, or taxi geometry, so placement and airport fields require separately
supplied stronger initialized evidence. The extracted log binds content and
declared producer metadata but does not cryptographically attest the producer.

## Commit-bound upstream theatre coverage

For the bounded 14-ID upstream source/projection matrix and query gate, see
[terrain-coverage.md](terrain-coverage.md). The detailed provenance and
limitations below remain controlling. This is not an official DCS product or
map count.

The release workflow uses the disposable `output\upstream` cache described in
[upstream-source-commands.md](reference/upstream-source-commands.md). Run
`upstream-status` before any upstream-backed decision and use
`upstream-prepare` only when that cache is not ready. The latter is the only
product command that may contact the network or write the cache; neither
command executes upstream code or starts DCS.

`upstream-promotion-audit` supplies the read-only candidate gate. It binds a
clean candidate to the current lock, proves fast-forward ancestry, hashes the
complete bounded path diff, rejects replaceable/non-standalone Git state,
matches the safe consumer checkout to exact index blobs, parses changed
consumer models twice, and rechecks both repository inputs after the run. It
never edits a pin. A candidate that changes consumed data must still pass the
separately recorded repository regression and post-lock evidence lifecycle
before promotion.

The recorded clean upstream states are:

- pydcs `master` at
  `e20f328390aecaac2a7f82444b4f5a96ac6bb2c3`;
- BriefingRoom `main` at
  `4d8773e9eec0215edb5cd9f576c085ee9f1bf7a7`.

The pydcs pin was promoted on 2026-08-26 after inspecting its two-commit
generated-data diff, validating the unchanged license and required source
model, rebuilding the locked cache, and passing the pydcs/cache compatibility
tests. Relative to the prior pin it adds one plane, one vehicle, and one Kola
airport with 11 parking records. The newer inspected BriefingRoom tip
`be5e3663ec6ed2b22db69c22f91c51f150566a91` did not change the terrain bounds,
spawn points, or airbase export consumed here, so its product pin was retained
instead of moving merely because the branch advanced.

The implemented promotion audit reproduces those decisions. The current pydcs
candidate is the exact locked commit with a zero-path diff. The BriefingRoom
candidate is a clean 16-commit fast-forward with 36 changed paths. Only
`src/BriefingRoom/BriefingRoom.cs` touches the bounded consumer surface; parsed
theatre, 802-airbase, 25,730-parking, and 14-bounds component fingerprints are
unchanged, while only the project-version metadata component differs. The
audit therefore reports `retain_pin_consumed_model_unchanged`, performs no
write, and does not authorize a lock update.

The read-only development survey clones were safely fast-forwarded and clean
at these inspected tips on 2026-08-26:

| Project | Remote branch | Inspected commit | Product disposition |
|---|---|---|---|
| pydcs | [`master`](https://github.com/pydcs/dcs) | `e20f328390aecaac2a7f82444b4f5a96ac6bb2c3` | Promoted to the immutable product cache profile |
| BriefingRoom | [`main`](https://github.com/DCS-BR-Tools/briefing-room-for-dcs) | `be5e3663ec6ed2b22db69c22f91c51f150566a91` | Inspected; consumed product pin retained at `4d8773e...` after relevant-data comparison |
| DCS Retribution | [`dev`](https://github.com/dcs-retribution/dcs-retribution) | `59719b24662d0b96492e3426c6fb78a58d8d31bc` | Read-only survey reference |
| MOOSE | [`master-ng`](https://github.com/FlightControl-Master/MOOSE) | `4849acbb327471bf4277ae5524c2d96ea89d4b93` | Read-only survey reference |
| dcs-mission-maker | [`master`](https://github.com/JonathanTurnock/dcs-mission-maker) | `48b2841b4f72ba32be217f3e618cfa3cec6c8f28` | Read-only survey reference |
| DCS Global Terrain Database | [`main`](https://github.com/flying-dice/dcs-global-terrain-database) | `d58c7a38d3f0a681bde67bed21868b6d3ecd9bb8` | Read-only survey reference |

Only pydcs and BriefingRoom participate in product commands. No third-party
source was copied into DCSMizzer.

The current-install observation refreshed on 2026-08-26 is DCS
`2.9.28.26385`, Steam build `24431605`, matching Eagle Dynamics'
[2026-07-28 changelog](https://www.digitalcombatsimulator.com/en/news/changelog/).
The recorded BriefingRoom project targets `2.9.28.26283`; it is one patch
behind that install. Treat all of its exports as commit-bound cross-check or
fallback evidence, never as version-matched current-install truth.

`terrain-coverage` combines identities without blending incompatible records.
At those commits the upstream union contains 14 exact DCS theatre IDs:

```text
Afghanistan
Caucasus
Falklands
GermanyCW
Iraq
Kola
MarianaIslands
MarianaIslandsWWII
Nevada
Normandy
PersianGulf
SinaiMap
Syria
TheChannel
```

Eleven have both pydcs and BriefingRoom evidence. Afghanistan, Iraq, and
MarianaIslandsWWII are BriefingRoom-only at the recorded pydcs commit. There
are no pydcs-only theatre IDs. The one identity conflict is pydcs `Sinai`
versus BriefingRoom and current real-MIZ `SinaiMap`; keep the pydcs declaration
unchanged, select the exact BriefingRoom DCS ID for the mission namespace, and
report the conflict.

`br-coordinates` derives a lower-authority projection from commit-bound
BriefingRoom airbase exports. At the recorded commit all unique finite samples
validate for 13 of 14 theatre IDs, including pydcs-absent `Iraq` and
`MarianaIslandsWWII`. Require authority
`derived_commit_bound_br_airbase_export_projection` and
`validation.validated=true`, plus
`decision_source_binding.all_required_sources_bound_to_head=true`. The fit
parses the exact reported HEAD blobs for the airbase export and all theatre
identity declarations; a merely clean status is insufficient. Afghanistan
fails closed with a null conversion because airdrome IDs 26, 27, and 28 expose
duplicate placeholder candidates; never select one or borrow another map
transform.

The aggregate clean-checkout mapping contains:

- 802 BriefingRoom airbases and 25,730 parking records across 14 theatre IDs;
- 5,635,118 BriefingRoom spawn points;
- 745 pydcs airports and 22,661 parking records across 11 terrain packages.

For a dual-source terrain not installed locally, start with pydcs and retain
BriefingRoom as an independent conflict check. Resolve each requested
airdrome/slot independently: exact installed identity evidence first, then the
selected primary source, then an explicitly reported secondary fallback when
the exact primary record is absent. Never silently combine fields from two
records. Report name, pair, position, capability, and dimension conflicts.

If either catalog contains duplicate identities or more than one source
candidate maps to a DCS theatre, `terrain-coverage` rejects that mapping
without selecting a parking authority. Source parse gaps are propagated in
`source_coverage`; a numerically complete-looking union is not enough.
Duplicate display aliases and generated Terrain-class identities are rejected
as well. `audit-spec` fails closed if any terrain/airport package in the
unfiltered identity graph is unresolved, even when an explicit override
otherwise has one parsed match.

`commit_bound` authority is provenance-gated. Git's reported top-level must
equal the supplied checkout root exactly, `HEAD` must exist, and the worktree
must be clean. Acknowledged upstream status also rejects ignored worktree
entries and tracked files carrying `assume-unchanged`, `skip-worktree`, or any
other nonordinary index tag, so those mechanisms cannot hide query inputs. A
dirty checkout becomes `dirty_worktree_snapshot`; a copied
directory, nested subdirectory inheriting a parent repository, or non-Git
source becomes `unversioned_snapshot`. `audit-spec` reports either downgrade
as a warning.

These exports have hard limits:

- BriefingRoom `landMasses`/`waters` are sea-mask planning polygons, not
  rectangular map bounds or terrain-height/land-class/collision evidence;
- BriefingRoom bounds and spawn sources must resolve inside the supplied
  checkout through every ancestor symlink/reparse point; malformed runway
  records do not establish runway evidence;
- BriefingRoom stand parking exports `crossroad_idx`, `slot_name`, and `x/y`,
  but no heading or per-stand elevation; the airbase reference elevation is a
  separate field;
- BriefingRoom terminal fallback records have `Term_Index` and an exported
  elevation, but no slot name, heading, or dimensions;
- `BRtype` and spawn points are placement-planning data only; two-coordinate
  manual points intentionally have `altitude_msl: null`;
- BriefingRoom climate/INI fields are not used as weather authority because
  their provenance and semantics are insufficiently reliable;
- pydcs `declared_center_wgs84` is untrusted class metadata and is accompanied
  by an unverified bounds diagnostic; it is not a verified map center;
- pydcs rectangular bounds first undergo a source-internal airport-center
  consistency check using the same reported tolerance (1,000 metres or 0.1%
  of the maximum axis span, whichever is larger). Only a consistent source
  may hard-fail authored coordinates. Otherwise all discovered route/unit,
  bullseye, trigger-zone, `Bombing`, `AttackMapObject`,
  `EngageTargetsInZone`, and structured `ActivateGCI` coordinates remain
  diagnostics. `BombingRunway` resolves by `runwayId`; incidental `x/y`
  fields on that action are not coordinate evidence;
- parking compatibility mirrors the airport's normalized `slot_version`.
  Version 1 uses pydcs `large`/helicopter classification and ignores
  dimensions. Version 2 requires aircraft length, width, and height to be
  *strictly less than* the slot dimensions, treats missing slot height as
  upstream's 1,000-metre default, and does not use `large`;
- BriefingRoom has no pydcs `slot_version`, so its dimensions and flags remain
  diagnostics and cannot claim a pydcs-resolver pass;
- a project-level target DCS version does not prove that each exported
  bounds/spawn file was regenerated for that version.

### 2026-08-26 coordinate and coastline exercise

The locked BriefingRoom HEAD blobs were exercised across all 14 theatre IDs.
For each theatre, the first exported airbase was used only as a deterministic
boundary-selection anchor; both `water` and `land` offsets were attempted at
100 m, 1 km, and 100 km. Of 84 combinations, 40 satisfied the unique-side and
global-minimum-distance invariant and 44 failed closed. Nevada accounts for
six expected rejections because its recorded bounds contain no `landMasses`
boundary. These counts test algorithmic coverage; they do not turn the source
mask into current DCS physical evidence.

One explicit Caucasus case used the reported commit
`4d8773e9eec0215edb5cd9f576c085ee9f1bf7a7`, terrain-bounds blob
`41ad5fc6bb549c0be2b743887f3c61c8c8b7c822`, and an anchor at mission-local
`x=-148274.511456, y=444041.026167`. The nearest planning `landMasses`
boundary was 453.746559 m away. The unique water-side point whose global
minimum planning-boundary distance is 100,000 m is
`x=-222687.862251, y=376560.596254`; residual was below
`1.5e-11` m. The current-install beacon fit inversely maps it to approximately
`42.9823964215 N, 38.8384627474 E`, but classifies it as an extrapolation about
100.93 km from the nearest beacon sample. The generated physical-probe MIZ
passed archive, CRC, parse, resource-hash, trigger-binding, entity-count, and
human-slot preservation checks. It did not obtain a DCS surface result.

For the Sinai landmark exercise, the selected Great Pyramid reference point
was Wikidata Q37200's `29°58′44.94″N, 31°8′03.19″E`
(`29.97915, 31.1342194444`); UNESCO independently identifies the broader Giza
to Dahshur pyramid-fields component, not that individual structure's point.
The current-install Sinai beacon fit maps the point to
`x=-7373.176364, y=-10781.869447`, inside its sample convex hull and about
25.96 km from the nearest sample. The disposable probe MIZ passed the same
static instrumentation gates and requests a 1.5 km scenery search, but no
runtime object or surface result was produced. Preserve the distinction
between a real-world reference point and the actual initialized-DCS scenery
instance. Sources: [Wikidata Great Pyramid](https://www.wikidata.org/wiki/Q37200),
[UNESCO component map](https://whc.unesco.org/en/list/086/maps/).

Two final isolated aggregate retries started exact, attested DCS
2.9.28.26385 processes but failed before Hook initialization: DCS logged Steam
authorization failures `-35` (SSL connect) and `-28` (timeout), with no cached
authorization in the disposable profiles. The bounded runner stopped the
first at timeout; the second exact PID was identity-checked and stopped early
to avoid excess game time. This does not invalidate the earlier successful
aggregate runtime run, but it prevents claiming current-session V2/V3 or
physical evidence for either disposable mission.

The dated product-card survey exposed by `terrain-catalog` records 18 official
cards mapping to 14 current `mission.theatre` IDs, including explicit regional,
entitlement, and legacy relationships. The
[Eagle Dynamics terrain catalog](https://www.digitalcombatsimulator.com/en/products/terrains/?SHOWALL_1=1)
is the public product/SKU authority when refreshed. Neither the 18-card
snapshot nor the 14-ID upstream union claims every future product. A product
name or installed directory still does not establish the internal ID, and
multiple products can share one.

## Real-mission observation scope

`miz-registry` accepts one or more explicit `LABEL=PATH` roots, recursively
finds regular MIZ files, validates ZIP safety and CRC, SHA-deduplicates
identical archives internally, and safely parses the mission table. It rejects
a symbolic link, junction, or other reparse point in every component of a
supplied root path, and it never follows a discovered directory or file link.
The root chain, candidate directory chain, and file identity are bound at
discovery and rechecked before and after the descriptor-backed read, so a
post-discovery link swap cannot redirect the read outside the supplied root.
Link, containment, and change rejections are returned only as anonymous reason
counts. Before any full copy or hash, the raw container must fit the default
512 MiB total archive ceiling and pass the nonexpanding ZIP policy check. An
accepted input is copied in bounded chunks to an anonymous stable snapshot;
that snapshot passes full policy and CRC checks before mission members are
parsed.

The report deliberately excludes:

- absolute paths and mission filenames;
- titles, briefing text, group names, and unit names;
- per-file and evidence-set hashes, copyrighted media, and every unfiltered
  string read from a mission.

It retains privacy-safe relationships required for research:

- anonymous theatre/unit/store references and exact category;
- structural field-count and variant-count distributions;
- anonymous group-task, waypoint-action, nested-task, side, and skill counts;
- payload station plus anonymous store signatures;
- start mode, numeric airdrome/parking/coordinate observations, and omitted
  string-value types;
- matching mission top-level field-count distributions plus date/time and nested weather
  schema counts, scalar types, string cardinality, booleans, and numeric ranges;
- trigger-zone/rule/condition/action/goal field counts and anonymous
  predicate-function counts, without identifiers, predicates, or comments;
- anonymous `requiredModules`, options, and warehouse shapes, including
  route-airdrome reference resolution, without player or device values;
- filter and coverage counts.

Unfiltered results never enumerate observed technical identity strings.
Resolve an exact theatre or unit type first from installed, generated-upstream,
or another explicitly public authority, then pass it as `--theatre` or
`--unit-type`. Only those caller-supplied exact filter strings are echoed in the
result. Treat every result as “observed in this evidence set,” and record
`missions_matching_filters`. An observation does not establish complete
support, and a missing observation does not prove impossibility.

For an aircraft, always pass `--category plane`. Static display objects can use
the same type string and otherwise contaminate unit, field, and coordinate
counts.

When the user requests a flyable or full-fidelity aircraft, do not select an
AI-only family/legacy type merely because its spelling matches the prose.
Resolve the exact type through current installed `dcs-modules`
`make_flyable` evidence and version-matched public evidence; the privacy-safe
registry intentionally does not reveal observed skill strings and therefore
cannot by itself prove `Player` or `Client` support. Query payloads for that
same exact resolved type. Record any marketing/module name to internal-type
mapping as a separate resolved fact.

The full currently surveyed four-root corpus contained 1,050 file instances
and 897 unique missions accepted by the strict registry policy. Anonymous
core-table observations across those 897 missions were:

| Observation | Count |
|---|---:|
| `requiredModules` present / missing | 854 / 43 |
| `requiredModules` empty / nonempty | 843 / 11 |
| Nonempty tables violating exact string-to-identical-string shape | 0 |
| `options` present / missing | 890 / 7 |
| `playerName` present / nonempty | 888 / 887 |
| Nonempty `hp_output` / `main_layout` / `main_output` | 153 / 238 / 233 |
| Nonempty voice input / output device fields | 284 / 243 |
| `warehouses` present / missing | 897 / 0 |
| Numeric / nonnumeric airport warehouse keys | 38,453 / 0 |
| Route airdrome references resolved / missing | 2,572 / 2 |

Nonempty local audio-device fields were observed often, but only anonymous
field counts were retained and `private_values_returned` was false. This is why
the options template always blanks those fields. These statistics describe the
surveyed corpus; they are not universal format requirements or permission to
copy a private mission's options.

## Identifier namespaces

Keep these namespaces separate:

- official terrain product, region, entitlement, or legacy SKU;
- installed terrain directory passed to `dcs-airbases`;
- internal `mission.theatre` value observed in a MIZ;
- aircraft family/display name in user prose;
- exact unit `type` string in the mission table;
- country identifier in the installed source;
- numeric country `id` in the mission table;
- payload table key, pylon station `num`, and store `CLSID`.

For a real-world target or city, cite an authoritative WGS-84 latitude and
longitude and convert it with `dcs-coordinates`. Then require matching
initialized physical evidence for every needed height, surface, slope, and
obstacle claim; an unqueried or unavailable map remains unresolved. Tactical
suitability is still a separate judgment. Never infer a city's mission-local
point from an airport beacon or paste latitude/longitude directly into mission
`x`/`y`.

Similar spelling is not proof of equality. A user-supplied family name may map
to multiple installed internal variants. Do not choose one silently.

## Parking and pylon fallback evidence

For parking, use this order:

1. a version-matched initialized terrain/runtime export;
2. a version-matched parsed real MIZ containing the exact type, airfield, and
   start mode;
3. for a noninstalled dual-source terrain, the exact per-airdrome/slot
   pydcs record at the recorded clean commit, with an explicit `br-airbases`
   fallback only when primary exact evidence is absent;
4. for a BriefingRoom-only terrain, exact `br-airbases` records;
5. unresolved, never a guessed parking number or beacon coordinate.

The pydcs fallback reports `crossroad_idx`, `slot_name`, and exact point
separately. In that generated model, mission `parking` uses `crossroad_idx`
and `parking_id` uses `slot_name`. A list index such as “first slot” is neither
value. This relationship still needs DCS runtime confirmation for the installed
version.

BriefingRoom stand records use the equivalent exported
`crossroad_index`/`name` relationship normalized to those two mission fields.
Terminal fallback records have no slot name, so do not manufacture
`parking_id`. For either source, query one exact airport and a bounded candidate
set, then re-query the chosen exact pair.

For a station/CLSID relationship, prefer a current installed default preset or
version-matched real mission. `pydcs-aircraft` is a useful independent,
commit-bound cross-check and may expose assignments absent from default
presets, but it does not upgrade the repository to a complete installed
compatibility registry. Before claiming reuse of a default loadout, run
`dcs-payload-match` over the complete station table and require
`exact_observed_preset`; a collection of individually observed pairs is only a
custom composition.

After authoring, run `audit-spec` with both locked cache roots. A scenario contract
can faithfully prove that an invented value survived serialization; the
evidence audit instead cross-checks selected exact technical relationships
against the current install and recorded upstream commits. Both are required,
and neither proves the scenario made the historically or tactically correct
choice. If the terrain is not locally installed, the audit must retain its
explicit installed-terrain warning.
When either acknowledged locked source participates in a required
determination, a missing, dirty, wrong-remote/commit/tree, or otherwise
unready cache is a hard audit failure. Do not reinterpret it as a lower
authority warning.

## Version and conflict handling

Record each exact value with:

```text
value
authority
relative source or evidence-root label
installed DCS version, source hash, or upstream commit
observation date
filters and coverage
known conflict or limitation
```

When sources disagree:

1. do not merge them silently;
2. identify the versions and scopes;
3. prefer the higher-authority version-matched source;
4. retain lower-authority evidence only as historical context;
5. leave the value unresolved if the conflict affects the requested result.

## Survey and upstream boundaries

The repository survey and these documents are reproducible coverage and
routing records, not a live or machine-consumable DCS database. Machine
decisions come from current tool reports and their source bindings.

`.develope` contains optional maintainer survey material only. It may be
deleted from a release checkout: product commands and the documented user
workflow never read it implicitly. A maintainer may explicitly supply one exact
`.develope/upstream` checkout to `upstream-promotion-audit`; that candidate is
review input, not product evidence or an accepted pin. Legacy
`.develope/reference` data is frozen and partial. Candidate-clone provenance
does not make it current.

The release source route is the explicit disposable cache prepared and checked
through `upstream-prepare`/`upstream-status`. Record remote, branch, commit,
tree, and license before relying on behavior. Do not copy, commit, or
redistribute upstream code as DCSMizzer product code.

The `pydcs-*`, `br-*`, and `terrain-coverage` commands expose only narrowly
parsed declarations/exports and Git/source provenance. They do not import
upstream Python, execute upstream code, mutate either checkout, or make that
data equal to the installed DCS version. Reported remotes are sanitized to
remove credentials, query strings, fragments, and local filesystem paths.

## Copyright and privacy

- Search installed DCS, applicable `Saved Games\DCS*` roots, approved local
  mirrors, and identified mission collections read-only.
- Open and parse archives; do not claim real missions were studied from names.
- Do not redistribute mission, campaign, audio, image, script, or briefing
  content.
- Do not commit private mission names, local absolute paths, Steam identifiers,
  briefing text, or per-file hashes.
- Keep generated output separate from installed DCS, Saved Games, official
  mirrors, upstream clones, and frozen references.
