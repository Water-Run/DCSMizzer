# Capabilities

This is the detailed **implementation/readiness and
implemented/partial/unavailable capability boundary**.
Start with [quickstart.md](quickstart.md); open this file when a requested
facility may not exist. Confirm the machine-readable state before every task:

```powershell
python Tools\dcsmizzer.py capabilities
```

## Implemented product facilities

| Facility | What it establishes |
|---|---|
| Locked upstream cache management | Read-only `upstream-status`, the sole network/cache writer `upstream-prepare`, and read-only `upstream-promotion-audit` verify fixed pydcs/BriefingRoom identities and fail-closed candidate ancestry, standalone Git state, ignored/untracked/hidden-index worktree inputs, exact consumer blobs, full path diff, license, stable inputs, and parsed consumer-model compatibility without executing either project or automatically changing a pin |
| Evidence lifecycle | Two-pass stable collection into local content-addressed bundles; canonical manifest and exact artifact membership/hash verification; legacy/current DCS domain diff; privacy-safe revalidated runtime and hash-bound physical-terrain attestations; current/stale/incomparable/partial/blocked readiness gates with dirty-producer rejection; and uniform `unbound`/`self`/`bundle-current` CLI references with immutable command-domain mappings, exact source identities, canonical intrinsic-report hashes, current producer equality, and matching pre/post-query readiness fences for 27 supported read-only commands (service-life module filters fail closed outside current artifact coverage) |
| MIZ inspection | ZIP/path policy, optional CRC, safe parsing of five core Lua data members, and anonymous mission statistics |
| CMP inspection | Safe campaign-table parsing, stage and interval checks, and relative MIZ-reference presence |
| Current-install inventory | Executable/Steam version when discoverable, installed module directories, country source, and declared static-source coverage |
| Static module index | Literal plugin IDs, `make_flyable` types, and filterable service country/year records from module sources, linked to same-directory default-payload unit types |
| Country lookup | Current installed country identifiers and sequential numeric IDs derived from `db_countries.lua` |
| Default-payload index | Unit types present in known central/module `UnitPayloads` sources, aggregate/per-type preset, pylon, CLSID and task coverage, source hashes, and explicit parse failures |
| Default-payload lookup | Exact preset names, station evidence, CLSIDs, task IDs, per-store settings, whole-preset fingerprints, source hashes, and integrity diagnostics for one exact unit type |
| Whole-payload matching | Deterministic complete station/CLSID and configured-preset fingerprints; strict exact, ambiguous, custom, unknown-pair, configuration-unspecified/mismatched, metadata-mismatched, duplicate-station, source-incomplete/invalid, and missing-unit classifications; source-bound evidence against current installed defaults |
| Static cloud-preset lookup | Exact literal GUI preset IDs, precipitation power, and base ranges from the current install |
| Mission Editor weather-preset lookup | A bounded parsed view of supported static/dynamic preset fields, precipitation/temperature/fog/dust constraints, source hashes, field-completeness state, and parse/consistency diagnostics from the current install |
| Static airbase lookup | Union of airdrome IDs/names in one installed terrain's radio/beacon sources, plus beacon positions |
| Native MiG-29A GCI lookup | Current station declaration/countries, official `ActivateGCI` training structure, installed-manual radar/link limits, and AI limitation |
| Current options template | Sanitized current Mission Editor data-only default, with local audio-device fields blanked and optional reported full-simulation overrides |
| Current warehouse template | Complete bounded unlimited-mode airport records from verified current Mission Editor literals and caller-verified numeric airdrome IDs |
| Dated official terrain product/theatre catalog | The surveyed 18 official product cards map to 14 current `mission.theatre` IDs with regional, entitlement, and legacy relationships kept explicit |
| Commit-bound upstream terrain identity graph | The two recorded clean-commit snapshots yield 14 parseable DCS theatre IDs; the full unfiltered identity graph preserves conflicts and rejects duplicate or ambiguous mappings |
| Provenance-qualified pydcs terrain lookup | The recorded pydcs snapshot yields 11 generated terrain packages, projection metadata, source-self-consistency diagnostics for declared rectangles, and aggregate airport/parking coverage |
| Provenance-qualified pydcs unit lookup | Safely parsed generated declarations across plane, helicopter, vehicle, ship, and static categories |
| Provenance-qualified pydcs airport lookup | Safely parsed generated airport, runway, parking and `Airport.slot_version` declarations with Git/source provenance |
| Provenance-qualified pydcs aircraft lookup | Safely parsed generated plane pylon/store declarations with Git/source provenance |
| Provenance-qualified BriefingRoom terrain/airbase lookup | The recorded BriefingRoom snapshot yields 14 theatre IDs, 802 airbases, and 25,730 parking records, including three IDs absent from the recorded pydcs snapshot |
| Provenance-qualified BriefingRoom spawn lookup | Bounded streaming queries over 5,635,118 candidate planning points in the recorded snapshot |
| Terrain coordinate conversion | WGS-84 to/from mission-local `x/y` using a projection independently fitted against current installed beacon pairs, with inverse and whole-airfield holdout residuals, sample-domain/extrapolation diagnostics, and bounded WGS-84 geodesic offsets |
| BriefingRoom-derived coordinate conversion | Lower-authority WGS-84 to/from local `x/y` fitted from commit-bound airbase exports for 13 of 14 theatre IDs; Afghanistan fails closed on duplicate placeholder candidates |
| BriefingRoom coastline planning | Bounded commit-qualified sea-mask parsing, nearest `landMasses` boundary measurement, and unique perpendicular land/water offsets remeasured against every planning boundary; explicitly not a current initialized-DCS coastline or physical-surface result |
| Physical-terrain evidence chain | Bounded probe-script generation, verified disposable-MIZ instrumentation, hash-bound log extraction, and explicitly theatre/version-bound point, sampled-placement, sampled-corridor, and landmark consumers with an explicit runtime-attestation field; mission-probe object searches are discovery-only and cannot clear placement collisions |
| Isolated DCS runtime bridge | Separate prepare/run/collect lifecycle; dry-run default and explicit launch authorization; disposable `DCSMizzer-*` profile; version, executable, process, Hook, mission, and result hash binding; aggregate registry initialization; exact-MIZ load/start/smoke and DCS coordinate checks; bounded exact-process cleanup |
| Airfield-footprint checks | An operational envelope only from a supplied complete initialized airfield inventory and per-record complete runway/parking/taxi geometry, with a separately labelled commit-bound BriefingRoom planning fallback |
| Context-bounded report interface | Catalogs default to `dcsmizzer.cli-summary/v1` under a 12 KiB UTF-8 budget including reserved evidence-reference transport space; nested summary collections keep at most 12 items; explicit details/full restores complete output; `report-summary` bounds saved-report review and preserves only a compact, explicitly unverified reported evidence reference after recognizing the source schema identifier, without proving shape/authenticity or rerunning validation |
| Ordinary continuous validation | Read-only GitHub-hosted Windows gate with commit-pinned official actions, exact Python/Ruff inputs, product/survey tests, document and Prompt validators, Ruff `E/F/B`, compilation, explicit timeout/concurrency controls, and a tested prohibition on DCS launch or upstream mutation |
| Observed MIZ registry | Privacy-preserving anonymous structure, frequency, numeric, relationship, start, airdrome, parking, weather, options, `requiredModules`, and warehouse observations from parsed real missions; exact theatre/unit filters are caller-supplied and only those filter strings are echoed; archive policy is checked before bounded snapshot copying and a stable snapshot passes CRC before parsing |
| Low-level MIZ assembly | Deterministic data-only Lua serialization and deterministic ZIP packaging from `dcsmizzer.miz-build-spec/v1`, including a finite common trigger/goal/timed-text compiler; safe regular-file identity/content fences for the spec; and handle/identity/SHA-256 binding plus a path-free member/size/hash ledger for resource inputs |
| Content-addressed construction trace | New `construction-snapshot` output uses `dcsmizzer.construction-bundle/v2`: it requires two identical live audit reports and two identical ordered transcripts, seals the exact calls and content-addressed responses for the complete 16-kind audit query vocabulary, strictly consumes that transcript in an authority-root-independent offline audit replay, then binds the exact spec/resources, audit/build/verify reports, MIZ, evidence/readiness preimages, full producer identity, and recomputed audit-to-build-to-verify DAG. `construction-verify` always checks strict static membership, hashes, bindings, and continuity, but runs audit/build/verification replay only when the complete current producer identity equals the recorded one. Historical producer mismatch is static integrity only. `construction-bundle/v1` remains readable legacy evidence without audit-decision replay. Native GCI specs remain refused, DCS runtime remains `null`, and `static_release_ready` still requires a complete current evidence gate |
| Complete-scenario quality gate | Actual group/unit content and a flying `Player`/`Client`, valid date/time/weather, the observed current runtime shell and coalition-side shapes, required briefing/core tables, exact seven-pair starts, official-pattern route locks (double-locked first point and no later double-lock), airborne lead heading aligned to a first route leg longer than one metre, nonnegative air speeds with positive airborne-start and non-landing enroute speeds, separated time-of-day/mission-elapsed values with zero-offset and non-late-activated human starts plus role-bound group offsets, same-coalition linked facilities, non-self escort, distinct compiled success/failure logic with global goal keys, flag-writer coverage, and a conservative reciprocal terminal guard/order contract that forbids startup/reset writes (not runtime mutual-exclusion or reachability proof), group-bound role contracts, enabled and semantically valid AI waypoint tasks, profile-required finite flying payload fields, airport warehouses, fatal warnings, final-output symlink rejection, handle-bound candidate validation, and an atomic final path update in a required trusted directory |
| MIZ build verification | CRC/archive checks, five-table round trip, handle-bound resource equality checks, finite structural/GCI/task checks, exact sparse global goal-key linkage, and caller-declared global and group-bound scenario-contract checks |
| Build-spec evidence audit | Full-graph terrain identity and provenance gates; exact five-category type plus current country/cloud/task/pylon/service/payload/property/parking/GCI checks; complete authored-coordinate inventory; source-self-consistent bounds checks; per-airport/per-slot primary-to-secondary fallback; version-aware pydcs parking resolution; cross-source conflict propagation; sanitized provenance; and an exact loaded-spec hash with a final identity/content drift fence |

Most evidence queries are read-only. Commands that write or launch declare the
boundary explicitly: `evidence-snapshot` writes a new content-addressed local
bundle below its caller-selected root; `upstream-prepare` writes the caller-
selected locked source cache; `build-miz` writes a mission archive;
`construction-snapshot` writes one local-only, 256 MiB-bounded content-
addressed construction bundle; `construction-verify` is read-only;
`terrain-probe-script`,
`terrain-probe-instrument`, and `terrain-probe-extract` write only their named
outputs. Named-artifact writers refuse an existing target unless `--force` is
supplied. Evidence snapshots instead reuse only an already verified identical
content address; upstream preparation mutates only a recognized clean cache.
`runtime-prepare` creates only a new isolated Saved Games profile.
`runtime-run` previews by default and launches DCS only with its authorization
flag. No command launches Mission Editor, and the probe commands do not execute
generated Lua by themselves.

Implementation is not readiness. `capabilities` can report an implemented
facility while an external DCS install, physical-evidence file, real-mission
root, or locked upstream cache is absent. For upstream-backed facilities, only
`upstream-status --cache-root output\upstream` exiting zero establishes cache
readiness; directory presence alone does not.

A v2 construction content address detects byte changes relative to a trusted,
externally retained bundle ID; it is not a signature and does not authenticate
the producer. A valid historical bundle under a different producer therefore
does not become fully reproducible or reopen its recorded release gate. In the
current evidence baseline, partial module, payload, and airfield authority still
keeps `static_release_ready=false`, even when the v2 offline audit, build, and
verification replays are exact.

The supported script entrypoint re-enters Python in isolated, no-site mode and
does not load repository bytecode. Before any evidence
snapshot/verify/diff/readiness command, `report-summary`, runtime command,
terrain-probe producer command, or explicit current-bundle query imports
product modules, it requires an ordinary clean index, rejects every ignored or
untracked entry under `Tools`, and requires all tracked regular worktree files'
Git-canonical content
IDs to match `HEAD`. Declared text line-ending normalization is accepted while
`-text`/binary content remains byte-exact. This pre-import guarantee applies to
`Tools\dcsmizzer.py`, not to arbitrary direct package imports, and treats the
local interpreter, Git executable, operating system, and bootstrap as trusted
components.

“Commit-bound” is a query-time provenance result, not a permanent label for an
arbitrary directory. The supplied upstream root must be exactly the Git
top-level checkout, have a readable `HEAD`, and be clean, with no ignored
entries or nonordinary tracked index flags. A dirty exact
checkout is reported as `dirty_worktree_snapshot`; a nested, parent-inherited,
or non-Git root is `unversioned_snapshot`. When an acknowledged locked source
participates in a required determination, `audit-spec` treats an absent,
dirty, mismatched, or otherwise unready locked cache as a hard failure rather
than downgrading it to a warning.

The 14-theatre/11-package figures describe unique `mission.theatre` IDs and
generated pydcs packages in the two commits inspected by the 2026-07-30
survey. They are not counts of official product cards, SKUs, regional
entitlements, or future terrains; they are not a current complete DCS
database, and another checkout need not have the same coverage. The separate
dated official survey records 18 product cards mapping to 14 current IDs.

The exact start-pair check was also replayed read-only over all 648 official
installed mission tables: 648 parsed, zero failed, and no mission contained an
invalid cross-pair among the seven known `type`/`action` combinations. This is
parse/start-pair regression evidence, not a claim that all 648 pass
`complete_scenario` and not a warning audit.

The same 648-table replay found all 8,188 plane-route first points
double-locked and zero double-locks among 23,065 later plane points. Helicopter
routes showed the same first-versus-later pattern. This supports the finite
route-lock gate; it is not a general route-timing or runtime proof.

Across 9,243 plane/helicopter groups in that replay, every group start time
equalled its first ETA. All 660 human groups started at elapsed zero, and no
nonzero `mission.start_time` was copied into a group start or first ETA.
This supports separating time of day from the mission-elapsed route timeline.
AI groups may intentionally use large positive delays, so their offsets are
bound per role rather than capped globally.

## Partial evidence, not complete registries

| Evidence | Safe conclusion | Unsafe conclusion |
|---|---|---|
| Installed module directory | Files for that module directory are present | The account owns it or runtime activation succeeds |
| Static plugin/flyable mapping | Those literal identifiers are declared together in that installed entry source | Entitlement, activation, or runtime success |
| Static country source | Identifier and derived numeric ID for that installed version | Compatibility with a different DCS version |
| Default payload | The exact assignment appears in an installed preset | Every CLSID/station combination is legal |
| Exact whole-payload fingerprint | The full source-bound preset, including supplied per-store settings, exactly matches one observed installed default | A complete compatibility matrix, runtime acceptance, or legality of a custom recombination |
| Terrain radio/beacon source | That airfield ID/name has those static records | Complete airbase, runway, center-point, or parking data |
| Literal service-life record | That module source declares the exact type/country/year interval | Historical fidelity beyond that declaration or runtime availability |
| Installed cloud preset | That exact literal preset ID exists in this install | The rest of the weather table or identical rendering on every terrain |
| Installed Mission Editor weather preset | Its supported fields pass the reported completeness gate and the evaluated constraint relationships are consistent in the source-bound install | Unknown future fields, terrain/date acceptance, rendered result, mission loading, or runtime behavior |
| Native GCI report | The current station/action/radar structure is supported by installed static, official-MIZ, and manual evidence | Terrain reception, target assignment, AI guidance, or runtime success |
| Generated pydcs terrain/unit/airport/pylon data | That declaration or relationship exists in the reported provenance-qualified snapshot | Equality with the installed initialized DCS registry, or that a dirty/unversioned snapshot is commit-bound |
| BriefingRoom terrain/airbase/parking data | That exported relationship exists in the reported provenance-qualified snapshot | Current runtime identity, parking heading/elevation, resolver compatibility, or that another checkout has the recorded counts |
| BriefingRoom bounds/spawn data | A planning polygon/type/point exists in the reported snapshot | Rectangular bounds, terrain height, land class, collision, road, or safe placement |
| BriefingRoom coastline offset | The destination is on the requested planning-mask side and its global minimum distance to every exported `landMasses` segment matches the requested offset | Equality with the current initialized-DCS coastline, physical surface type, navigable water, or placement safety |
| Beacon-fitted conversion | A WGS-84 point converts consistently with installed beacon pairs | Terrain height, land cover, feature identity, or placement validity |
| BriefingRoom-derived conversion | The exact commit-bound airbase-export fit passed for that theatre | Current-install equality, terrain/feature identity, or a usable Afghanistan transform |
| Initialized physical-terrain sample | The exact queried point/sample/object passed against explicitly matching theatre and declared-version evidence, with its version-identity basis reported | Runtime-version identity when not attested, unsampled-area safety, continuous terrain, tactical suitability, or aircraft performance |
| Derived initialized airfield footprint | A complete declared airfield inventory and complete selected runway/parking/taxi record produced that operational envelope | An official airport boundary or proof that every placement inside it is safe |
| Extracted terrain-probe log | Complete markers and hashes bind the extracted content to declared producer metadata | Cryptographic attestation of who or what produced the log |
| Parsed real MIZ registry | The anonymous structure/count occurred in the parsed evidence set; an exact caller-supplied filter matched the reported count | The hidden source identity, an unfiltered technical string, universal support, or exhaustive coverage |
| Successful low-level build | Input tables serialized, packaged, parsed back, and passed available checks | DCS will load it or gameplay logic works |
| Successful evidence audit | Selected authored technical relationships match the finite current/upstream evidence scope | Historical scenario correctness, AI behavior, or runtime success |

For pydcs parking, missing `Airport.slot_version` normalizes to upstream
version 1. Version 1 uses large-slot/helicopter classification and does not use
the declared dimensions for normal planes. Version 2 requires the aircraft's
length, width, and height to be strictly less than the slot dimensions, treats
a missing slot height as 1000 m, uses the category-capable flag, and ignores
the large-slot class. BriefingRoom exports do not establish pydcs resolver
semantics. Dual-source position, dimension, or capability differences remain
warnings rather than being blended.

Every partial report includes its authority, source scope, and limitation
fields. Preserve those fields when reasoning.

## Not implemented

| Capability | Status |
|---|---|
| Natural-language scenario planner | Not implemented; the Agent must design the scenario |
| Automatic identifier or compatibility inference | Not implemented; resolve evidence explicitly |
| Campaign generation | Not implemented |
| Complete initialized unit registry | Requires a version-matched runtime export |
| Complete per-aircraft Mission Editor unit shell/default fields | Not implemented; parsed observations can expose field presence, but current per-module defaults such as `AddPropAircraft`, radios, liveries, DTC, and module-specific options are not generated as a complete registry |
| Complete per-unit task-capability matrix | Requires a version-matched runtime export |
| Complete store-to-station compatibility | Requires a version-matched runtime export; pydcs and presets are partial evidence |
| Complete per-terrain airport/runway/parking registry | Requires version-matched terrain/runtime evidence; pydcs and BriefingRoom are provenance-qualified snapshot fallbacks and are commit-bound only when the strict Git gate passes |
| Automatic initialized export for every installed terrain | Not implemented; probe generation/instrumentation still require a separately authorized exact-MIZ DCS run, and mission scripting cannot export runway/parking/taxi geometry |
| Continuous full-map physical terrain, scenery, road, and collision registry | Not implemented; current consumers prove only supplied queried samples and positive object instances, while collision clearance requires separately declared complete coverage |
| Mission Editor resave | Not implemented |
| DCS launch or mission-load test | Implemented as an explicit-opt-in isolated prepare/run/collect bridge with Steam app/build/install/state revalidation that tolerates only unselected volatile appmanifest metadata; readiness still depends on the local install, Steam state, entitlement, and a passing exact run |
| Runtime-valid claim | Available only from a passing `runtime-collect` result for the exact version/hash-bound MIZ and declared V2/V3 checks; static reports remain `runtime_valid: null` |

The absence of those facilities is a completion constraint, not permission to
guess. If a user-required fact cannot be resolved from current installed data
or parsed observations, leave it unresolved and explain what evidence is
missing. Ask before making a material substitution.
