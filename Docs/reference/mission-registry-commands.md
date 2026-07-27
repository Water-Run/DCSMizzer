# Mission inspection and registry command details

Open this reference only when current `<command> --help` does not answer a
semantic question about archive inspection, coordinate fitting, or anonymous
real-MIZ evidence. Command availability and syntax still come from current CLI
help. Return to the [command router](../tools.md) after resolving that
question.
Bounded catalogs use `dcsmizzer.cli-summary/v1` and a 12 KiB UTF-8 budget;
request a full report only with the explicit flag shown by current help.

## `inspect`

```powershell
python Tools\dcsmizzer.py inspect path\mission.miz > output\inspect-miz.json
python Tools\dcsmizzer.py inspect path\campaign.cmp > output\inspect-cmp.json
python Tools\dcsmizzer.py report-summary output\inspect-miz.json
python Tools\dcsmizzer.py report-summary output\inspect-cmp.json
```

For MIZ, returns archive policy and CRC status, five core-member parse status,
theatre/version, and anonymous counts for groups, units, slots, routes,
payloads, tasks, triggers, goals, resources, warehouses, and briefing size.
It does not rerun the builder's limited mission-structure pass; the report
therefore returns `limited_structure_checked: false` and
`limited_structure_valid: null`.

For CMP, returns campaign stage/reference/interval checks. Inspection reports
can be large; keep them on disk, review the bounded summaries first, and open
only fields needed for a comparison or diagnosis.

`--skip-crc` is allowed only when the caller explicitly accepts that CRC was
not verified. It weakens validation and must be reported.

The default archive policy allows at most 4,096 members, 128 MiB expanded per
member, 512 MiB expanded in total, and a 250:1 per-member compression ratio.
If a pre-CRC archive error exists—such as an unsafe/duplicate member,
encryption, or a size/ratio violation—CRC expansion and all member parsing are
not attempted; `crc_status` is `not_checked` and the archive remains rejected.

The purpose-specific compatibility entry point remains:

```powershell
python Tools\validate.py path\mission.miz
python Tools\validate.py path\campaign.cmp
```

## `dcs-coordinates`

Derive and validate one installed terrain's projection:

```powershell
python Tools\dcsmizzer.py dcs-coordinates `
  --dcs-root "D:\path\to\DCSWorld" `
  --terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY"
```

Convert an authoritative WGS-84 point to mission-local coordinates:

```powershell
python Tools\dcsmizzer.py dcs-coordinates `
  --dcs-root "D:\path\to\DCSWorld" `
  --terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --latitude 52.0 `
  --longitude 13.0
```

Convert mission-local coordinates back to WGS-84:

```powershell
python Tools\dcsmizzer.py dcs-coordinates `
  --dcs-root "D:\path\to\DCSWorld" `
  --terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --x -200000 `
  --y -480000
```

The tool independently fits a WGS-84 Transverse Mercator model to every usable
map/geodetic coordinate pair in the current installed terrain beacon source.
It searches the UTM-family central meridians, fits scale and offsets, and
refuses conversion unless at least three pairs exist, the fitted scale is
credible, and maximum residual is at most 25 metres. The report includes source
hash, sample/airfield counts, fitted parameters, RMS/maximum residual, and the
inverse round-trip residual, plus the next-best candidate residual.

`x/y` are the horizontal fields used in a mission table. The result does not
identify terrain height, land cover, airport center, runway, parking, or safe
unit placement. Cite the external WGS-84 source separately.

## `br-coordinates`

Fit and report one exact BriefingRoom theatre projection:

First require
`upstream-status --cache-root output\upstream` to exit zero. If it does not,
follow the
[locked upstream source instructions](upstream-source-commands.md) and rerun
status.

```powershell
python Tools\dcsmizzer.py br-coordinates `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID"
```

Forward WGS-84 conversion adds `--latitude` and `--longitude`; inverse
conversion adds `--x` and `--y`:

```powershell
python Tools\dcsmizzer.py br-coordinates `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain Iraq `
  --latitude 33.3 `
  --longitude 44.4
```

With no conversion pair, the command reports only the fit. A usable report has
authority `derived_commit_bound_br_airbase_export_projection`,
`validation.validated=true`, and
`decision_source_binding.all_required_sources_bound_to_head=true`. The airbase
export and every theatre identity declaration are parsed and hashed from the
reported HEAD blobs; required worktree paths must still be contained regular
non-reparse files. This is lower-authority commit-bound evidence derived from
exported airbase pairs, not an installed-terrain fit and not terrain-height or
feature proof.

The parser fails closed above the limits reported in `source_limits`: 128 JSON
levels, 10,000 total exported airbase records, 512 records for the selected
theatre, and 256 distinct finite coordinate samples. The normal JSON report is
also capped at 12 KiB and reports any diagnostic truncation. These are
resource-safety limits, not claims that future upstream maps cannot be larger;
an upstream expansion beyond them requires an intentional tool review.

At the recorded commit, all unique finite samples validate for 13 of 14 theatre IDs,
including `Iraq` and `MarianaIslandsWWII`. `Afghanistan` fails closed with
`validation.validated=false`, exit code 1, `conversion: null`, and duplicate
placeholder candidates for airdrome IDs 26, 27, and 28. Never select one of
those candidates or borrow another terrain's transform.

## `miz-registry`

```powershell
python Tools\dcsmizzer.py miz-registry `
  --root "installed=D:\path\to\official-missions" `
  --root "saved=D:\path\to\Saved Games\DCS\Missions" `
  --theatre "EXACT MISSION THEATRE" `
  --unit-type "EXACT INTERNAL TYPE" `
  --category plane
```

`--root LABEL=PATH` is repeatable and accepts a MIZ file or a recursively
scanned directory. `LABEL` must be an anonymous ASCII token beginning with a
letter and containing only letters, digits, `_`, `.`, or `-`; never put a path
or mission title in the label. Filters are optional and exact. Category
choices are `plane`, `helicopter`, `vehicle`, `ship`, and `static`.

The default is always the bounded anonymous summary, with or without exact
filters. `--summary-only` is only a compatibility alias for that same default:

```powershell
python Tools\dcsmizzer.py miz-registry `
  --root "installed=D:\path\to\DCSWorld"
```

The compact report deliberately uses generated `observed-theatre-N`
references; it cannot be used to discover private mission strings. Resolve an
exact theatre/type from installed data, a provenance-gated upstream query, or
another explicitly public authority, then rerun with that exact
theatre/type/category filter. The filtered result remains a summary. If
relational details are necessary, add the explicit `--details` or `--full`
shown by current help and redirect stdout to a JSON file. Only caller-supplied
exact filter strings are echoed. Do not read a terrain `entry.lua` and assume
its plugin ID is equal to the MIZ theatre namespace.

The command rejects a symbolic link, junction, or other reparse point in any
component of a supplied root path, prunes directory links, skips file links,
and requires every discovered regular file to resolve inside its supplied
root. It binds the root chain, candidate directory chain, and file identity at
discovery and rechecks them around the descriptor-backed read, so a
post-discovery link swap is rejected. The default 512 MiB total archive ceiling
also caps the raw MIZ container before it is opened. The command checks ZIP
policy before copying or hashing, copies an accepted bound input in bounded
chunks to a stable anonymous snapshot, then reruns policy and CRC on that
snapshot before parsing. It deduplicates identical MIZ files internally and
can return privacy-preserving relational observations only under the explicit
detailed view. It does not expose
filenames, paths, mission/group/unit names, briefing text, media, hashes, or
any unfiltered string read from a MIZ.

In detailed output for missions matching the filters, `environment` reports
mission top-level field-count distributions, version/date/start-time scalar
observations, and nested weather table field-count distributions, scalar
types, string cardinality, booleans, and numeric ranges. Paths receive
generated anonymous references and string values are never returned. These are
observed examples, not the complete DCS weather domain; preserve a verified
shape and do not interpret an observed minimum or maximum as a legal limit.

In that detailed output, `environment.logic` reports trigger-zone,
trigger-rule, condition, action, goal, and nested goal-condition field-count
distributions plus anonymous predicate-function occurrence counts.
It never returns predicate bodies, arguments, zone names, trigger comments, or
scripts or function identifiers. Function occurrence proves observed
structure only; it is not a complete signature or behavior specification.

The detailed `core_tables` anonymously summarizes `requiredModules`, `options`,
and `warehouses` presence/shape plus route-airdrome reference resolution. It never
returns player names or audio-device values. Observed presence and
field-count/variant shapes are examples from the supplied corpus, not universal
DCS schema rules.

Always use `--category plane` for aircraft. Record the root labels, filters,
`missions_matching_filters`, coverage, and anonymous errors. Do not publish
private root paths, filenames, mission text, hashes, player names, device
values, or a private value supplied as a filter. The result is observational
and not a complete runtime registry.
