# Model quickstart

This is the bounded entry path for building a user-facing mission. DCSMizzer
does not plan a scenario from prose, invent missing DCS data, or prove runtime
playability. Keep generated specs, reports, and MIZ files under a working
directory such as `output/`.

## 1. Capture the request

Make a compact constraint ledger: era/date, duration, exact map, coalitions,
country IDs, player/AI types and counts, skill and start state, airbases and
parking, loadouts, objectives, routes, weather, triggers, success/failure,
briefing, resources, realism, and output path. Mark each value
`user-specified`, `verified`, `inferred`, or `unresolved`. Do not silently
change a specified map, variant, weapon, start, player count, or mission type.

## 2. Check capability and terrain

```powershell
python Tools\dcsmizzer.py capabilities
python Tools\dcsmizzer.py evidence-readiness --help
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
python Tools\dcsmizzer.py terrain-catalog --help
python Tools\dcsmizzer.py terrain-coverage --help
```

`capabilities` defaults to a compact status matrix. Use
`capabilities --details` only when the current decision needs the full
machine-readable boundary; [capabilities.md](capabilities.md) is the
human-readable counterpart.

When a current content-addressed bundle already exists, run
`evidence-readiness` for the exact decision domains before querying individual
records. If no bundle exists, create one from the current installation and
locked upstream cache, then verify it:

```powershell
python Tools\dcsmizzer.py evidence-snapshot `
  --dcs-root "D:\path\to\DCSWorld" `
  --bundle-root output\evidence-bundles `
  --cache-root output\upstream

python Tools\dcsmizzer.py evidence-verify `
  output\evidence-bundles\BUNDLE_SHA256
```

A dirty producer, partial domain, stale fingerprint, or incomparable source
scope remains non-ready even when the bundle's bytes verify. See the
[evidence lifecycle command details](reference/evidence-lifecycle-commands.md)
only when snapshot, drift, or readiness behavior needs review.
The documented entrypoint isolates Python before product imports and refuses
provenance-sensitive work on a dirty or Git-canonical-content-mismatched
checkout; use it rather than importing `dcsmizzer.cli` directly when the
pre-import producer gate is required.
Run provenance-sensitive commands from a standalone clone with an ordinary
root `.git` directory; linked worktrees and submodule source trees are not
accepted by this gate.

To make a supported read-only query carry a usable current-bundle reference,
pass its exact current roots and bundle explicitly:

```powershell
python Tools\dcsmizzer.py dcs-countries `
  --dcs-root "D:\path\to\DCSWorld" `
  --evidence-bundle output\evidence-bundles\BUNDLE_SHA256 `
  --evidence-current-dcs-root "D:\path\to\DCSWorld"
```

Check `evidence_ref.status` and
`evidence_ref.validation.usable_for_current_production_decision`; only
`bundle-current` plus `true` passes this transport gate. `unbound` remains a
valid report with only its intrinsic authority. The command's mandatory
domains are fixed and any `--evidence-required-domain` values only add gates.
Unsupported, writing, launching, or arbitrary-input commands reject external
binding flags before dispatch. See the lifecycle reference for the complete
allowlist and upstream/terrain forms.
The reference includes `report_binding.intrinsic_report_sha256`, calculated
over the canonical payload without `evidence_ref`. After saving or moving a
report, run `report-summary` and also require
`reported_evidence_ref.intrinsic_report_binding_matches=true`; this detects
content edits but does not authenticate an untrusted file.

When an exact isolated runtime run or initialized physical-terrain export is
already available, add its `--runtime-manifest` or `--terrain-evidence` path to
both snapshot and later readiness commands. These options revalidate existing
files and never start DCS.

If `upstream-status` is nonzero, prepare the fixed source lock, then check it
again:

```powershell
python Tools\dcsmizzer.py upstream-prepare --cache-root output\upstream
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
```

Only `upstream-prepare` contacts the network or writes this cache. Use
`upstream-prepare --cache-root output\upstream --offline` when network access
must be forbidden; missing locked Git objects then fail closed. See the
[upstream source command details](reference/upstream-source-commands.md) only
when preparation or provenance needs review.

`terrain-catalog` distinguishes dated official product cards from the unique
`mission.theatre` identities written into a MIZ. Product/SKU count and theatre
count are not interchangeable.

If the user named a map, the first terrain query **must** include its exact
`--terrain` selector. Do not emit the full theatre identity graph:

```powershell
python Tools\dcsmizzer.py terrain-coverage `
  --pydcs-root output\upstream\pydcs `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID" `
  > output\terrain.json
```

If the user did not name a map, use the command's compact default catalog,
choose without restricting candidates to installed maps, then rerun for one
exact terrain. Read [terrain-coverage.md](terrain-coverage.md) only when map
authority, identity, or coordinate support matters. Read
[terrain-physical.md](terrain-physical.md) only when a placement, landmark,
airfield envelope, surface, slope, or route-clearance decision is required.

## 3. Resolve evidence without flooding context

Use three levels:

```text
compact catalog -> exact type/airport -> one station/parking/preset
```

Keep model-visible evidence bounded. Treat 12 KiB as the maximum for one
discovery response and 128 KiB as the normal cumulative evidence working-set
target before authoring the spec. If a response would exceed 12 KiB, redirect
it and extract only the decision field, or issue a narrower query. Record the
selected value and provenance in the constraint ledger; do not keep every raw
response in model context. For an optional long document, list its headings
first and read only the relevant section.

Prefer installed/version-matched data, then parsed same-version missions, then
clean commit-bound upstream data. Query only the fields needed by the ledger.
For aircraft, use category `plane`; static objects can share a type string.
Default payloads are observations, not a complete compatibility registry.
After selecting one exact installed preset, verify the **whole** authored
composition instead of combining separately observed station/store pairs:

```powershell
python Tools\dcsmizzer.py dcs-payload-match --help
```

Its default output is a bounded fingerprint summary. Only
`exact_observed_preset` is a strict preset match; use `--details` only for
needed mismatch evidence. Per-store settings require the Python API and remain
part of strict matching.

For weather, prefer one supported-field-complete current Mission Editor preset
and retain both its field-integrity and constraint results:

```powershell
python Tools\dcsmizzer.py dcs-weather `
  --dcs-root "D:\path\to\DCSWorld" `
  --preset "EXACT PRESET ID"
```

Use the result only when both `validation.fields_complete` and
`validation.consistent` are true. Preserve `missing_fields`,
`invalid_fields`, `unsupported_fields`, `truncated_fields`, and the
`evaluated_fields` scope; this is not proof about unknown fields or rendering.

Run `python Tools\dcsmizzer.py <command> --help` before every unfamiliar
command. CLI help is the source of truth. Bounded catalogs and exact terrain
views default to `dcsmizzer.cli-summary/v1` within a 12 KiB UTF-8 budget. Use
that response first. Inspect `view.output_truncated` and any
`view.nested_truncations` item/character counts before treating a field as
complete. Exact pydcs/BR airports default to eight parking records;
an exact parking or normal-sized payload preset may remain complete within the
budget. Use the explicit `--details` or `--full` shown by help only when all
stands or another complete report are necessary, and redirect it to a file.

For a plane, do not expand `pydcs-units --details` to find stores. Use its
compact exact-type result for identity/tasks, then query only the required
relationship:

```powershell
python Tools\dcsmizzer.py pydcs-aircraft `
  --pydcs-root output\upstream\pydcs `
  --unit-type "EXACT INTERNAL TYPE" `
  --station 3 --search "R-27" --limit 10

python Tools\dcsmizzer.py pydcs-aircraft `
  --pydcs-root output\upstream\pydcs `
  --unit-type "EXACT INTERNAL TYPE" `
  --station 3 --clsid "{EXACT-CLSID}"
```

The compact unit and aircraft responses contain a `routing` hint for this
transition. Resolve one selected parking position with exact `--parking`
instead of loading every stand.

Use [tools.md](tools.md) to choose a command and [evidence.md](evidence.md) only
to decide authority or resolve conflicts. Never blend two airbase/parking
records. Record fallbacks and unresolved conflicts explicitly.

Coordinates and upstream planning points do not establish physical safety.
For a ground footprint or low-level route, use initialized, theatre- and
declared-version-bound evidence and run `placement-check` or
`terrain-corridor`. For a request such as placing a SAM near the pyramids,
`landmark-search` can prove a returned scenery instance exists, but placement
also needs producer-declared ground-placement-complete object coverage and
complete airfield geometry. `terrain-probe-script` can prepare bounded point,
corridor, and scenery-discovery evidence, `terrain-probe-instrument` can bind
it to a verified disposable MIZ, and `terrain-probe-extract` can parse its log.
Only an explicitly authorized `runtime-run` starts DCS.
Because the mission probe deliberately cannot prove negative collision
coverage, keep the footprint unresolved unless a stronger initialized export
is separately supplied.

## 4. Author one complete spec

For generation, read [build-spec.md](build-spec.md). It is the normative
construction contract. Use `quality.profile="complete_scenario"`, sanitized
current options, verified-ID warehouse records, deterministic provenance, a
complete briefing, and an `expect.roles` binding for every group.

Author finite success/failure logic with conservative terminal guards:

- put failure writers before the success writer;
- guard the success writer with every failure flag being false;
- guard each failure writer with the success flag being false;
- never write a terminal flag from a `start` rule, and never reset or assign it
  any value other than true/`1`.

For every plane/helicopter route, set both locks true on the first waypoint.
After the first point, never set both `ETA_locked` and `speed_locked` true:
normally lock speed and leave ETA unlocked; for an exact arrival time, lock
ETA and leave speed unlocked. For an airborne start, align the lead unit's
heading with the first route leg; parking headings require separate
parking/mission evidence.

Keep the two time domains separate: `mission.start_time` is the clock time
since midnight, while every group `start_time`, waypoint `ETA`, and
`c_time_after` value is elapsed seconds since mission start. Every human
flight starts at elapsed `0`. Bind every role's intended offset with
`mission_elapsed_start_seconds` (use JSON `null` when the group has no
`start_time`); never add `mission.start_time` to route ETAs.

A static pass at
`generation.logic_compilation.terminal_outcome_dataflow.guard_order_contract_passed`
proves only that those guards and that order exist. The report keeps
`runtime_mutual_exclusion_proved` and `temporal_reachability_proved` false;
review the logic and do not claim DCS runtime exclusivity or reachability.

Read [mission-format.md](mission-format.md) only when diagnosing raw Lua/archive
shape, starts, native MiG-29A GCI, resources, or CMP structure.

## 5. Audit, build, verify, inspect

Full audit/build/verify reports belong on disk:

```powershell
python Tools\dcsmizzer.py audit-spec spec.json `
  --dcs-root "D:\path\to\DCSWorld" `
  --installed-terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --pydcs-root output\upstream\pydcs `
  --br-root output\upstream\briefing-room-for-dcs `
  > output\audit.json
python Tools\dcsmizzer.py build-miz spec.json output\mission.miz `
  > output\build.json
python Tools\dcsmizzer.py verify-miz output\mission.miz --spec spec.json `
  > output\verify.json
```

Use `--installed-terrain` whenever the selected map is installed; omitting it
deliberately leaves the current-terrain cross-check unperformed and produces
a warning. For an uninstalled map, omit it and preserve that limitation.
When either acknowledged locked upstream source participates in a required
determination, `audit-spec` must hard-fail if its cache is absent, dirty, or
does not match the fixed remote, commit, and tree.

Inspect each full report through the bounded summary:

```powershell
python Tools\dcsmizzer.py report-summary output\audit.json
python Tools\dcsmizzer.py report-summary output\build.json
python Tools\dcsmizzer.py report-summary output\verify.json
```

`report-summary` accepts a JSON file with a recognized schema identifier up to
16 MiB and emits at most 12 KiB. It does not prove schema shape or
authenticity and does not rerun audit, build, or verification. Its extracted
claims use `reported_*` names and `claims_unverified=true`; a reported pass is
not a new validation result. Oversized validation metadata is sampled and
disclosed by `view.validation_fields_truncated`; the original field count is
retained. `view.runtime_validation_performed` is therefore always false, while
`reported_runtime_validation_performed` describes only the unverified saved
claim. Do not put the complete saved JSON into model context.

All three commands must exit zero, and their reports must agree. Then run
`inspect` independently, keep its complete report on disk, and review its
bounded summary:

```powershell
python Tools\dcsmizzer.py inspect output\mission.miz > output\inspect.json
python Tools\dcsmizzer.py report-summary output\inspect.json
```

Compare the resulting scenario counts and identifiers with the constraint
ledger by opening only the needed fields from `inspect.json`. For a complete
scenario, require the build/verify quality gate and fatal warning review to
pass. Resolve audit warnings where evidence exists; otherwise preserve them as
explicit limitations. Verify archive/CRC/parsing, round-trip equality,
resources, structure, contract, trigger/goal presence, role bindings, routes,
tasks, payloads, starts, recovery, and briefing.

## 6. Optionally establish an exact runtime tier

Static success does not authorize an external process. When DCS validation is
requested and available, follow
[runtime-commands.md](reference/runtime-commands.md): prepare a new isolated
profile, review the dry-run preview, authorize one run, then collect the exact
hash-bound result. A passing aggregate registry probe is not mission evidence.
Only a passing mission-smoke collection for `output\mission.miz` establishes
its declared V2/V3 tier. Do not interrupt another Steam session without
separate authorization.

## 7. Report the actual result

Read [validation.md](validation.md) for claim meanings. Report the artifact,
source versions, preserved constraints, checks run, checks not run, and
remaining uncertainty. Without an actual authorized DCS load, say **built and
statically verified**; never say DCS-valid, playable, or runtime-valid.

For a longer sequence or a material decision gate, open [workflow.md](workflow.md).
For capability gaps, open [capabilities.md](capabilities.md).
