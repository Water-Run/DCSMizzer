# Construction and validation command details

Open this reference only when current `<command> --help` does not answer a
semantic question about evidence audit, MIZ construction, read-back
verification, or saved-report summarization. Command availability and syntax
still come from current CLI help. Return to the
[command router](../tools.md) after resolving that question.
Full audit/build/verify JSON stays on disk. `report-summary` provides the
bounded review; it does not repeat any validation.

## Content-addressed construction trace

For a new construction, prefer the all-in-one trace command when the current
evidence bundle and its acknowledged upstream cache are available:

```powershell
python Tools\dcsmizzer.py construction-snapshot `
  path\mission-spec.json `
  --construction-root "D:\local-only\dcsmizzer-constructions" `
  --evidence-bundle "D:\local-only\evidence\BUNDLE_ID" `
  --dcs-root "D:\path\to\DCSWorld" `
  --cache-root "D:\local-only\upstream" `
  --installed-terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --pydcs-terrain "EXACT_PYDCS_TERRAIN_PACKAGE" `
  > output\construction-snapshot.json

python Tools\dcsmizzer.py construction-verify `
  "D:\local-only\dcsmizzer-constructions\CONSTRUCTION_ID" `
  > output\construction-verification.json
```

`construction-snapshot` requires one clean exact DCSMizzer producer commit and
now emits `dcsmizzer.construction-bundle/v2`. It collects the live audit twice.
Both the intrinsic audit reports and their canonical ordered transcripts must
be byte-identical. The v2 transcript vocabulary covers all 16 external query
kinds that `audit-spec` can issue:

- `countries`, `gci_evidence`, `weather_constraints_available`, and
  `weather_constraints`;
- `cloud_preset`, `pydcs_unit`, `dcs_payload`, and `dcs_module_index`;
- `pydcs_terrains`, `br_terrains`, `combined_terrains`, and
  `installed_product_version`;
- `payload_match`, `pydcs_airport`, `br_airbase`, and `dcs_airbase`.

An individual transcript contains the exact ordered calls actually made for
that spec, not invented calls for branches the audit did not enter. Each call
binds strict canonical parameters to a content-addressed response. Duplicate
keys, non-finite numbers, schema drift, unsupported or out-of-order calls,
parameter/response mismatches, unreferenced responses, excessive depth/nodes,
and configured call/response/byte limits fail closed. Repeated identical
queries may share one response object but may not produce different responses.

Before building, the writer runs the captured decision again from only the
sealed spec, sealed resource override set, and transcript. It does not consult
the original DCS installation or upstream authority roots during that replay;
the request stream must be consumed completely, and the resulting intrinsic
audit report and verdict must exactly match the capture. It then builds and
reads back a temporary MIZ, verifies the exact spec/resource ledger, repeats
the build and static-verification replay, and applies matching evidence,
spec/resource, and producer fences before publication.

The v2 bundle embeds the exact evidence bundle and stores canonical objects for
the original spec, every resource, audit transcript, bound audit/build/verify
reports, readiness and evidence-verification preimages, and exact MIZ. Its
manifest recomputes an audit-to-build-to-verify hash DAG. Construction objects
are bounded to 256 MiB in total. They are local-only, may contain private or
licensed data, and are not authorized for redistribution. The caller-selected
construction root must be a trusted directory not writable by an untrusted
concurrent actor. It must not equal, contain, or be contained by the selected
DCS install, upstream cache, evidence bundle, build spec, or resource inputs.
It also must not equal, contain, or be contained by the DCSMizzer producer
repository; otherwise publication itself could invalidate the clean producer
identity.

Exit code 0 from `construction-snapshot` means the v2 bundle, audit, strict
offline audit replay, build, byte-exact rebuild, static-verification replay,
and mandatory current evidence gate all passed. An audit/build/verification
failure before publication produces no bundle. A valid bundle may still be
published while the CLI returns 1 when current required evidence is partial;
in that case `fully_reproducible` can be true while
`static_release_ready=false`. The present broad baseline remains in exactly
that non-release-ready state because module declarations, payload observations,
and installed-terrain airfield views have partial authority.

For `construction-bundle/v2`, `construction-verify` always checks the content
address, exact object membership and hashes, transcript/report/evidence
bindings, and pipeline continuity. Audit, build, and static-verification replay
run only when the current producer record exactly equals the complete recorded
producer identity, including name, version, commit, dirty state, and toolchain.
If that identity differs, the replay-performed fields are false, replay-result
fields are `null`, `fully_reproducible=false`, and a zero exit code means only
that historical static integrity passed. With the exact producer, all three
replays must pass for exit code 0. Verification itself never reopens the
historical release gate: its `static_release_ready` remains false and the
manifest's original decision is exposed separately as the recorded gate.

`construction-bundle/v1` remains accepted as a legacy format. It can replay
exact build bytes and static verification under its narrower recorded
producer/toolchain conditions, but it has no audit-decision transcript and
therefore remains `fully_reproducible=false` and
`static_release_ready=false`. Legacy standalone `audit-spec`, `build-miz`, and
`verify-miz` reports remain readable but are not retroactively sealed.

Both construction versions deliberately keep `runtime_valid: null`; neither
launches DCS. The writer refuses a spec containing native
`GCI_station_MiG29`, because that audit branch consults installed declarations,
official training missions, and a local manual whose conditional inputs do not
yet have a sealed evidence domain. Finally, a content address detects changes
relative to a trusted externally retained ID; it is not a signature, proof of
the original author, or authentication of the producer.

## `audit-spec`

After authoring and before building, cross-check the complete spec against
current installed static evidence and the locked upstream cache. First require
`upstream-status --cache-root output\upstream` to exit zero; prepare the cache
through the separate
[locked upstream source commands](upstream-source-commands.md) when needed:

```powershell
python Tools\dcsmizzer.py audit-spec path\mission-spec.json `
  --dcs-root "D:\path\to\DCSWorld" `
  --installed-terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --pydcs-root output\upstream\pydcs `
  --pydcs-terrain "EXACT_PYDCS_TERRAIN_PACKAGE" `
  --br-root output\upstream\briefing-room-for-dcs `
  > output\audit.json
```

The complete report must remain on disk. Review it through
`report-summary output\audit.json`, and open only selected detailed fields
needed to resolve a failure.

For a terrain that is not locally installed, omit `--installed-terrain`. The
audit then reports that current installed terrain cross-check as a warning and
uses exact provenance-gated terrain/parking evidence. `--br-root` enables the
BriefingRoom fallback for theatre IDs absent from pydcs and an independent
cross-source check when both have data.

The audit first runs the build spec's structural gate, then checks:

- every authored unit category/type across plane, helicopter, vehicle, ship,
  and static against exact current or commit-bound declarations;
- every country numeric ID against the current installed country source;
- an authored cloud preset and base against the exact installed preset and its
  declared base range;
- supplied precipitation, temperature, fog, and dust relationships against
  statically extracted Mission Editor constraints when that installed source
  is available;
- every exact flying type and `group.task` against generated task records,
  using `mission_group_task` rather than class/internal names;
- for a flying type represented by current default-payload sources, the whole
  authored station/CLSID/settings composition against one observed preset,
  preventing a synthetic combination of pairs taken from unrelated presets;
- every station/CLSID pair against a current installed default-payload
  observation or, as lower authority, the commit-bound generated pydcs
  declaration;
- authored fuel, chaff, flare, and `AddPropAircraft` fields against the
  generated declarations when those bounds/defaults are available;
- route/unit positions, coalition bullseyes, trigger-zone centers, and
  coordinates from `Bombing`, `AttackMapObject`, `EngageTargetsInZone`, and
  structured `ActivateGCI` actions against a pydcs rectangle only after its
  own airport centers are internally consistent under the same explicit
  tolerance; `BombingRunway` is resolved by `runwayId`, not incidental `x/y`;
  otherwise every discovered coordinate remains diagnostic;
- exact per-airdrome/slot source resolution, with selected-primary then
  explicit-secondary fallback and position/capability/dimension conflicts
  retained in `parking_source_resolutions`;
- pydcs parking resolver-v1 classification semantics or resolver-v2 strict
  three-axis `<` semantics according to normalized `slot_version`; BR-only
  dimensions remain diagnostics because BR exports no pydcs slot version;
- literal service-life records when the current matching module declares them;
- a native MiG-29 GCI station's current declaration/training evidence and
  declared country availability;
- terrain identity and each parking airdrome ID/name against the selected
  pydcs or BriefingRoom authority;
- each parking `crossroad_idx`/`slot_name`, category-capable flag, and exact
  unit position, with installed and secondary-upstream conflicts reported.
- each `BombingRunway.runwayId` against an exact airport with runway evidence,
  including explicit BriefingRoom-only or secondary resolution.

Exit code 1 means at least one technical relationship is contradicted or
unresolved within this command's required scope. Missing literal service-life
declarations and authored country display-name differences are warnings and
leave `review_warnings_clear` false without inventing data. The report does
not judge whether the scenario chose the historically correct coalition,
contains a tactically effective GCI layout or meaningful target, assigns
effective AI behavior, or will load in DCS.
It also does not consume a terrain physical-evidence file: point, landmark,
surface, footprint, obstacle, and route-clearance decisions must be run
separately through the terrain physical commands.
Terrain selection is made from the complete unfiltered identity graph; any
unparsed terrain or airport package makes that graph unusable instead of
allowing an override to hide the gap.

The spec must be a safe regular file reached without a symbolic link, junction,
reparse point, or Windows alternate data stream. It is read through one bound
file identity; audit, build, and verify recheck that identity and the original
loaded-content SHA-256 before accepting their result. The report exposes the
spec basename and SHA-256, never its absolute path. Git
remotes in upstream provenance have user information, query strings, and
fragments removed; local, loopback, private/link-local IP, file, UNC,
drive-path, and malformed remotes are redacted. `commit_bound` additionally
requires Git's exact top-level to equal the supplied root and a clean
worktree. When an acknowledged locked source participates in any required
determination, a missing, dirty, wrong-remote/commit/tree, or otherwise
unready cache is a hard `audit-spec` failure. It is not downgraded to a
warning.

## `build-miz`

```powershell
python Tools\dcsmizzer.py build-miz `
  path\mission-spec.json `
  output\mission.miz `
  > output\build.json
```

Reads `dcsmizzer.miz-build-spec/v1`, rejects unsafe/inconsistent input, writes a
deterministic MIZ, reads it back, and returns:

- archive/CRC status;
- exact archive-member set with no undeclared additions;
- core-table parse and exact equality;
- plaintext theatre match;
- resource completeness;
- packaged-resource byte equality against every spec source file, with each
  regular resource bound to one open identity and initial SHA-256 for the
  complete operation;
- a path-free `member`/`size_bytes`/`sha256` ledger for every bound resource
  input;
- limited structural diagnostics;
- finite trigger/goal compilation metadata when top-level `logic` is used;
- every caller-declared scenario-contract check;
- conservative contract-coverage warnings for common facts left undeclared;
- artifact SHA-256 and deterministic generation metadata;
- `runtime_valid: null`.

For complete-scenario terminal logic, inspect
`generation.logic_compilation.terminal_outcome_dataflow`.
`guard_order_contract_passed=true` proves only reciprocal false guards and
failure-before-success source order. The report deliberately retains
`runtime_mutual_exclusion_proved=false` and
`temporal_reachability_proved=false`.

Use `"quality": {"profile": "complete_scenario"}` for a user mission. This
profile requires complete briefing/core-table shapes, deterministic
provenance, finite compiled logic, positive success and negative failure goals,
role-bound scenario contracts for every group, actionable AI waypoint tasks,
complete flying-unit/loadout fields, and represented airport warehouses.
Warnings are fatal under this profile. The default `technical_fixture` profile
exists for low-level tests and is not an acceptable shortcut for a requested
complete scenario.

The candidate is built and fully checked through its open file handle in the
same directory. The final filesystem path update is atomic and occurs only
when `validation.available_checks_passed=true`, but the report deliberately
sets `publication.atomic=false`: Python's cross-platform standard library
cannot make an end-to-end atomicity claim against an attacker who can modify
the output directory. Require
`filesystem_path_update_atomic=true`,
`candidate_identity_bound_to_open_handle=true`, and
`trusted_directory_required=true`, and select a trusted output directory.
Existing output is refused; `--force` replaces only that exact output after a
successful candidate check. A failed candidate leaves a prior artifact
byte-for-byte intact or leaves a new output absent. Reports expose only
spec/artifact basenames, never their absolute paths. Read
[build-spec.md](../build-spec.md) before authoring a spec.
For supported trigger/goal families, use the documented finite `logic`
compiler instead of hand-authoring compiled Lua-function strings.
Run `audit-spec` before `build-miz`; successful serialization cannot validate
identifiers that the spec itself merely asserted.

## `verify-miz`

```powershell
python Tools\dcsmizzer.py verify-miz `
  output\mission.miz `
  --spec path\mission-spec.json `
  > output\verify.json
```

Re-runs the complete archive/readback/resource/structure/contract verification
against the source spec. Every resource source file must still exist for byte
comparison. Each is opened once, bound by file identity and initial SHA-256,
and rechecked through the original handle before return. Reports expose
`resource_inputs_identity_bound_to_open_handles` and
`resource_inputs_content_bound_to_sha256`. This detects tampering, accidental
edits, missing resources, and scenario drift. It does not load DCS.

## `report-summary`

```powershell
python Tools\dcsmizzer.py report-summary output\audit.json
python Tools\dcsmizzer.py report-summary output\build.json
python Tools\dcsmizzer.py report-summary output\verify.json
```

This reads an already saved JSON report with a recognized dcsmizzer schema
identifier, at most 16 MiB, and emits `dcsmizzer.report-summary/v1` at no more
than 12 KiB. Identifier recognition is not full schema-shape or authenticity
validation. It does not rerun `audit-spec`, `build-miz`, or `verify-miz`, and a
summary cannot turn a failed or unavailable validation level into success.
Keep the complete report on disk and open selected full fields only to resolve
a reported problem.
The summary sets `claims_unverified=true` and prefixes extracted source claims
with `reported_`. Interpret `reported_status.passed` together with
`reported_status.basis`; this means only that the saved file reports that
verdict. Nonfatal audit warnings remain in `reported_warnings` and leave
`reported_validation.review_warnings_clear=false`.
If validation metadata alone would exceed the output budget, the summary
samples its fields, preserves `reported_validation_field_count`, and sets
`view.validation_fields_truncated=true`. It still accepts a valid input within
the 16 MiB input ceiling. `view.runtime_validation_performed=false` states
that this command did not run DCS; any non-null runtime verdict found in the
saved source is exposed separately as the unverified
`reported_runtime_validation_performed` claim.
If the saved source contains CLI `evidence_ref` transport metadata, the summary
copies only its bounded status, bundle/content hash identity, and reported
production-usable Boolean into `reported_evidence_ref`. It explicitly marks
those claims unverified and never forwards arbitrary authority, domain, path,
or limitation fields from the input file. Transport-only hashes are excluded
from `reported_hashes` and `reported_hash_count`.
For an ordinary explicit binding, it also recomputes the canonical report
payload hash after removing top-level `evidence_ref` and exposes
`intrinsic_report_binding_matches`. A false value proves the saved payload no
longer matches its reference; a true value detects consistency only and does
not authenticate a caller-supplied reference.
Hash-field discovery is diagnostic and traverses at most the
`view.hash_scan_depth_limit` reported by the summary; absence beyond that
depth is not proof that the saved report contains no additional hashes.
