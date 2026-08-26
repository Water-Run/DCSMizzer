# Command router

This file selects a command and, only when needed, one bounded reference
group. Do not load all command references. Run current CLI help first:

```powershell
python Tools\dcsmizzer.py <command> --help
```

CLI help is authoritative for command availability, flags, defaults, and
argument order.

## Context gate

Use this evidence ladder:

```text
compact catalog -> exact type or airport -> one preset, station, or parking
```

- If the user named a map, `terrain-coverage` must include `--terrain`.
- If no map was named, use the compact default catalog, select one exact
  theatre, then rerun with `--terrain`.
- Use `terrain-catalog` to distinguish official product cards from exact
  `mission.theatre` IDs. For height, surface, slope, scenery, mountain, or
  airport-area decisions, route through
  [terrain-physical.md](terrain-physical.md); planning snapshots cannot pass
  that physical gate.
- Bounded catalogs and exact terrain views default to
  `dcsmizzer.cli-summary/v1` and a 12 KiB UTF-8 budget. Exact pydcs/BR airports
  default to eight parking records; use `--details` only when all stands are
  required. Check `view.output_truncated`; when a single returned record has a
  large nested collection or long text, `view.nested_truncations` reports its
  path and item/character counts.
- Keep normal model-visible evidence below a cumulative 128 KiB working-set
  target before spec authoring. Save selected values in the constraint ledger
  and replace broad responses with narrower queries.
- Use exact filters and small limits. For catalog/evidence views, request a
  full report only with the explicit `--details` or `--full` shown by current
  help, then redirect it.
- For plane stores, use compact `pydcs-units` only for identity/tasks, then
  `pydcs-aircraft --unit-type ... --station ... --search/--clsid ...`.
  Do not use `pydcs-units --details` as a pylon query.
- Always redirect full `audit-spec`, `build-miz`, `verify-miz`, and `inspect`
  JSON.
  `report-summary PATH` accepts JSON with a recognized schema identifier up to
  16 MiB and emits at most 12 KiB without checking authenticity/schema shape
  or rerunning validation.

## Command groups

| Need | Commands | Open only if help is insufficient |
|---|---|---|
| Capability boundary | `capabilities` (compact status matrix; `--details` for the full machine report) | [capabilities.md](capabilities.md) |
| Locked upstream cache readiness/preparation | `upstream-status`, `upstream-prepare` | [upstream source command details](reference/upstream-source-commands.md) |
| Official product cards versus unique theatre IDs | `terrain-catalog` | [physical terrain routing](terrain-physical.md) |
| Current installed version, modules, countries, weather, payload presets/fingerprints, airbases, native MiG-29A GCI | `dcs-static`, `dcs-modules`, `dcs-countries`, `dcs-cloud-presets`, `dcs-weather`, `dcs-payload-index`, `dcs-payloads`, `dcs-payload-match`, `dcs-airbases`, `dcs-gci` | [installed-data command details](reference/installed-data-commands.md) |
| Sanitized build inputs | `dcs-options-template`, `dcs-warehouse-template` | [installed-data command details](reference/installed-data-commands.md) |
| Current-theatre identity and commit-bound terrain/unit/airport/pylon evidence | `terrain-coverage`, `pydcs-terrains`, `pydcs-units`, `pydcs-airports`, `pydcs-aircraft` | [upstream discovery command details](reference/upstream-discovery-commands.md) |
| BriefingRoom terrain, airbase, parking, planning points, and planning coastline offsets | `br-terrains`, `br-airbases`, `br-spawnpoints`, `br-coastline` | [upstream discovery command details](reference/upstream-discovery-commands.md) |
| Physical point, landmark, placement, route-clearance, and airport geometry | `terrain-point`, `landmark-search`, `placement-check`, `terrain-corridor`, `airfield-footprint`, `br-airfield-footprint`; producer path `terrain-probe-script`, `terrain-probe-instrument`, `terrain-probe-extract` | [physical terrain routing](terrain-physical.md) |
| MIZ/CMP archive inspection | `inspect`; compatibility entry point `Tools/validate.py` | [mission inspection and registry details](reference/mission-registry-commands.md) |
| WGS-84 conversion | `dcs-coordinates`, `br-coordinates` | [mission inspection and registry details](reference/mission-registry-commands.md) |
| Isolated DCS registry or exact-MIZ smoke | `runtime-prepare`, `runtime-run`, `runtime-collect` | [runtime command details](reference/runtime-commands.md) |
| Anonymous real-MIZ evidence | `miz-registry` | [mission inspection and registry details](reference/mission-registry-commands.md) |
| Spec evidence gate | `audit-spec` | [construction and validation details](reference/construction-validation-commands.md) |
| Deterministic artifact and read-back | `build-miz`, `verify-miz` | [construction and validation details](reference/construction-validation-commands.md) |
| Bounded saved-report review | `report-summary` | [construction and validation details](reference/construction-validation-commands.md) |

For authority or source conflicts, use [evidence.md](evidence.md). For the
recorded 14-identity theatre snapshot, use
[terrain-coverage.md](terrain-coverage.md). For the
normative input contract, use [build-spec.md](build-spec.md). For claim
meanings, use [validation.md](validation.md).

## Construction route

```text
capabilities
  -> upstream-status (upstream-prepare only when not ready)
  -> terrain-catalog + filtered terrain-coverage
  -> exact terrain/unit/airbase/parking/payload/weather evidence
  -> physical placement/corridor evidence where required
  -> dcs-options-template + dcs-warehouse-template
  -> audit-spec -> build-miz -> verify-miz -> inspect
```

Query commands, including `upstream-status`, are read-only.
`upstream-prepare` is the only command that may contact the network or write
the locked source cache. `terrain-probe-script` and
`terrain-probe-extract` write only their requested output; they do not execute
the generated Lua or start DCS/Mission Editor. `terrain-probe-instrument`
writes only a verified disposable derivative and never edits its source MIZ.
`runtime-prepare` creates only a new `Saved Games\DCSMizzer-*` profile;
`runtime-run` is dry-run by default and is the sole command that can start DCS,
after `--authorize-dcs-launch`. `build-miz` writes only its
requested artifact flow and internal same-directory temporary entries.

All reports are UTF-8 JSON on stdout; usage/source errors go to stderr. Tool
errors are normalized to one line and at most 2 KiB, with an explicit
`[truncated]` marker when needed. Do not ignore a nonzero exit:

| Code | Meaning |
|---:|---|
| 0 | Query succeeded, or every available requested validation passed |
| 1 | Input was read but inspection/build verification failed, or an exact filtered lookup had no match |
| 2 | Usage, missing path/source, unsafe/invalid spec, unsupported extension, or other source error |

For repository documentation only:

```powershell
python Tools\validate_prompt_samples.py
python Tools\validate_document_links.py
```

The first validates bilingual user Prompt examples; the second checks local
documentation links. Neither validates a mission.
