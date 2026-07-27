# Construction and validation command details

Open this reference only when current `<command> --help` does not answer a
semantic question about evidence audit, MIZ construction, read-back
verification, or saved-report summarization. Command availability and syntax
still come from current CLI help. Return to the
[command router](../tools.md) after resolving that question.
Full audit/build/verify JSON stays on disk. `report-summary` provides the
bounded review; it does not repeat any validation.

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

The report exposes the spec basename and SHA-256, never its absolute path. Git
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
Hash-field discovery is diagnostic and traverses at most the
`view.hash_scan_depth_limit` reported by the summary; absence beyond that
depth is not proof that the saved report contains no additional hashes.
