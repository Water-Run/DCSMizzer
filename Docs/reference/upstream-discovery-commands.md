# Upstream discovery command details

Open this reference only when current `<command> --help` does not answer a
semantic question about commit-bound pydcs/BriefingRoom discovery. Command
availability and syntax still come from current CLI help. Return to the
[command router](../tools.md) after resolving that question.
Bounded catalogs and exact terrain views use `dcsmizzer.cli-summary/v1` and a
12 KiB UTF-8 budget. Exact pydcs/BR airports default to eight parking records;
an exact parking record can be complete. Request all stands or another full
report only with the explicit `--details` or `--full` shown by help.

Before any command in this reference, require:

```powershell
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
```

If status is nonzero, follow the separate
[locked upstream source instructions](upstream-source-commands.md), then rerun
status. Directory presence is not readiness.

## `terrain-catalog`

```powershell
python Tools\dcsmizzer.py terrain-catalog --search "MAP OR REGION"
```

This dated public-product routing snapshot separates official product cards,
regional/legacy relationships, and exact `mission.theatre` identities. Its
2026-07-30 survey records 18 product cards but 14 unique current theatre IDs;
those counts describe different namespaces. It does not prove ownership,
installation, coordinates, physical terrain, or live store availability.

## `pydcs-terrains`

```powershell
python Tools\dcsmizzer.py pydcs-terrains `
  --pydcs-root output\upstream\pydcs

python Tools\dcsmizzer.py pydcs-terrains `
  --pydcs-root output\upstream\pydcs `
  --terrain "EXACT_PACKAGE_CLASS_OR_THEATRE" `
  --latitude 51.0 `
  --longitude -1.0
```

The no-filter route is a compact discovery catalog. The exact `--terrain`
route remains bounded while preserving identity, projection, rectangular
bounds, airport/parking counts, consistency totals, source hashes, and any
requested conversion. Add `--details` only for the full counterexample lists
and source record. Each terrain includes `declared_bounds_consistency`:
explicit tolerance, airport-center statistics/counterexample counts, and
whether a hard coarse-coordinate rejection is allowed. A filtered query may
also convert WGS-84 to mission-local coordinates, or perform the inverse with
`--x` and `--y`.

The upstream projection is not independently fitted to a noninstalled current
terrain. `declared_center_wgs84` is explicitly untrusted class metadata; its
diagnostic can expose placeholders and sign errors. A converted point does not
prove terrain height, land class, collision, or placement validity.
An unfiltered catalog returns exit code 1 if any discovered terrain package or
airport declaration could not be parsed; use the coverage fields before
trusting its counts.

## `pydcs-units`

```powershell
python Tools\dcsmizzer.py pydcs-units `
  --pydcs-root output\upstream\pydcs `
  --category plane `
  --unit-type "EXACT INTERNAL TYPE"
```

Discovers generated declarations across `plane`, `helicopter`, `vehicle`,
`ship`, and `static`. Exact lookup is preferred for authoring; `--search` and
`--limit` are bounded discovery aids. Use its compact exact-type result before
requesting details. An explicit full-report form returns complete matching
records within the command's current `--limit` (default 20, maximum 100); it is
not an unbounded dump of every generated unit. Records may include generated
task, fuel, countermeasure, property, pylon, and store declarations used by the
evidence audit. Prefer `pydcs-aircraft` with one station for plane pylon
evidence rather than duplicating a whole flying-unit record in context.

The report is commit-bound source evidence, not the initialized registry of the
installed DCS version. Do not infer entitlement, historical service, runtime
availability, or universal task/store compatibility from it.

## `pydcs-airports`

Query a generated airport declaration from an acknowledged pydcs checkout:

```powershell
python Tools\dcsmizzer.py pydcs-airports `
  --pydcs-root output\upstream\pydcs `
  --terrain "EXACT_PACKAGE_CLASS_OR_MIZ_THEATRE" `
  --airdrome-id 123 `
  --parking "EXACT_SLOT_NAME_OR_CROSSROAD_INDEX"
```

`--airport` is an alternative exact name filter. `--parking` requires one of
the exact airport filters and matches either the source `slot_name` or decimal
`crossroad_idx`. The report includes airport center, runways, parking
positions/dimensions/aircraft flags, source hash, upstream Git state, and
normalized `slot_version` (upstream default 1). Exact queries require one
usable parsed airport or exact parking pair; duplicate, ambiguous, or
parse-incomplete results return exit code 1.
The unfiltered airport list uses the same fail-closed rule: any rejected
generated `Airport` class makes the command return exit code 1.

For a model-friendly discovery query, request only airplane-capable slots and
return a small deterministic prefix:

```powershell
python Tools\dcsmizzer.py pydcs-airports `
  --pydcs-root output\upstream\pydcs `
  --terrain "EXACT_PYDCS_TERRAIN_PACKAGE" `
  --airdrome-id 123 `
  --airplane-only `
  --limit 4
```

`--limit` accepts 1-100 and requires an exact airport filter. Without
`--details`, an exact airport defaults to eight parking records; use an exact
`--parking` query for one selected slot or `--details` for all stands.
`matching_parking_slots` remains the full number selected before truncation;
`returned_parking_slots` and `parking_output_truncated` describe the emitted
records. Each returned record is complete, so use its exact pair and position
directly or rerun with `--parking` for one selected slot.

The command parses Python with `ast`; it never imports or executes pydcs. This
is lower-authority, provenance-gated generated evidence, not an installed DCS
runtime export. Prefer a same-version real-MIZ parking observation. When none
exists, cross-check the airport ID/name with `dcs-airbases`, record the pydcs
commit, and retain runtime uncertainty. In the generated pydcs model,
`crossroad_idx` is the mission `parking` value and `slot_name` is
`parking_id`; never infer either from its list position.

## `pydcs-aircraft`

```powershell
python Tools\dcsmizzer.py pydcs-aircraft `
  --pydcs-root output\upstream\pydcs `
  --unit-type "EXACT INTERNAL TYPE" `
  --station 4 `
  --clsid "{EXACT-CLSID}"
```

Safely resolves one generated plane class against generated weapon records and
returns metadata, declared pylons/tasks, station/store assignments, unresolved
counts, source hashes, and upstream Git state. Task records deliberately keep
three namespaces separate:

```text
class                 generated Python class, for example GroundAttack
mission_group_task    exact mission group.task value, for example Ground Attack
payload_internal_name payload/task-constant namespace, for example GroundAttack
```

Use only `mission_group_task` when authoring `group.task`. A missing type or
requested station/CLSID relationship returns exit code 1.

A full aircraft report can contain hundreds of assignments. Start with an
exact `--station`; add exact `--clsid` for the final compatibility check.
Use the explicit full-report flag shown by current help only when needed, and
redirect that response to a work file.
Assignment records use `station` and `CLSID` here, which intentionally differs
from the installed preset report's `num` and `CLSID` fields.

This is a commit-bound compatibility cross-check, not the initialized registry
of the installed DCS version. Cross-check with current installed
`dcs-payloads` or a version-matched real mission whenever possible.

## `br-terrains`

```powershell
python Tools\dcsmizzer.py br-terrains `
  --br-root output\upstream\briefing-room-for-dcs

python Tools\dcsmizzer.py br-terrains `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID"
```

Discovers BriefingRoom's exported DCS theatre IDs and coarse planning
geometry, with Git and source provenance. The current recorded catalog covers
14 unique DCS theatre IDs. The exported `landMasses`/`waters` polygons are
exposed as
sea-mask planning geometry: they are not rectangular map bounds and do not
prove current terrain height, collision, land class, or safe placement.

Project-level target-version metadata does not prove that every individual
bounds or spawn file was regenerated for that version. Product/SKU names in
the official terrain catalog can also share one DCS theatre ID; do not treat
the two namespaces as interchangeable.
The command returns exit code 1 for an incomplete bounds catalog. Resolved
bounds and spawn paths must remain inside the supplied checkout even when an
ancestor is a symlink or Windows reparse point.

## `br-airbases`

```powershell
python Tools\dcsmizzer.py br-airbases `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID" `
  --airdrome-id 101 `
  --airplane-only `
  --limit 4
```

Queries exported airbase centers, runway designator indexes, course/radio
records, and parking. `--airport` is an alternative exact airbase filter;
`--parking` matches the exact exported slot name or decimal parking ID and
requires one airbase. The current recorded catalog contains 802 airbases and
25,730 parking records across all 14 unique theatre IDs in that snapshot.

Without `--details`, an exact airbase defaults to eight parking records.
Select one with `--parking`, pass a smaller explicit `--limit`, or redirect an
explicit detailed report when all stands are genuinely needed.

For stand records, `crossroad_idx`/`slot_name` and `x/y` match the upstream
generator's mission fields, but heading and per-stand elevation are absent.
The separately reported airbase elevation must not be substituted. Terminal
fallback records retain `Term_Index` and exported elevation but have no slot
name, heading, or dimensions. Empty stand dimensions remain unknown rather
than being synthesized.
Malformed airbase or runway records are rejected, and either an exact or
unfiltered query returns exit code 1 when selected source records could not be
parsed.

`br-airfield-footprint` can derive runway polygons and conservative
half-diagonal parking circles from one exact record:

```powershell
python Tools\dcsmizzer.py br-airfield-footprint `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID" `
  --airfield "EXACT_EXPORTED_NAME"
```

That envelope is a commit-bound planning aid, not an official airport boundary
or physical validation. Parking headings are absent from this source, so the
circles are deliberately conservative.

## `br-spawnpoints`

```powershell
python Tools\dcsmizzer.py br-spawnpoints `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID" `
  --type LandSmall `
  --x 100000 `
  --y 200000 `
  --radius 25000 `
  --limit 20
```

Streams a bounded deterministic set of candidate planning points rather than
loading millions of records into model context. The recorded catalog contains
5,635,118 points. `BRtype` is an upstream planning classification, not a DCS
surface/collision query. Two-coordinate manual points return
`altitude_msl: null`; no terrain altitude is inferred. Even a three-coordinate
point does not prove that a unit, formation, or route is safe there.

## `terrain-coverage`

```powershell
python Tools\dcsmizzer.py terrain-coverage `
  --pydcs-root output\upstream\pydcs `
  --br-root output\upstream\briefing-room-for-dcs `
  --terrain "EXACT_DCS_THEATRE_ID"
```

Run this before assuming that a requested terrain must be locally installed.
When the user names a map, `--terrain` is mandatory and avoids loading the full
identity graph. If no map is specified, omit `--terrain` only for the compact
default catalog, then rerun with one exact DCS ID, display name, or pydcs
package. At the currently recorded commits the catalog has 14 unique DCS
theatre IDs:
11 in both sources, three BriefingRoom-only, and none pydcs-only. See the
bounded [terrain matrix](../terrain-coverage.md).

For a dual-source noninstalled terrain, the report selects pydcs for
airport/parking construction and retains BriefingRoom as an independent
conflict check. It never merges records silently. The known identity conflict
is pydcs `Sinai` versus BriefingRoom/current real-MIZ `SinaiMap`; the exact
BriefingRoom DCS ID remains selected and the conflict stays visible.

The v2 report models each source declaration independently. Duplicate DCS IDs,
duplicate pydcs mappings, or any other multi-candidate identity are reported as
`rejected_without_merge` with `selected_parking_authority: null`. Check
`coverage.identity_mappings_rejected`,
`coverage.source_parse_incomplete`, and the exact record before using a
terrain. If either summary field reports a rejection/incomplete source,
redirect an explicit `--details` report and inspect only the relevant
`source_coverage` diagnostics. Rejected records are excluded from usable
theatre and dual-source counts; `matching_records_including_rejected` retains
their diagnostic count. A filtered query succeeds only when
`exact_query_usable` is true. An unfiltered catalog also returns exit code 1
when either source is parse-incomplete.
