# Installed-data command details

Open this reference only when current `<command> --help` does not answer a
semantic question about installed DCS evidence or sanitized core-table
templates. Command availability and syntax still come from current CLI help.
Return to the [command router](../tools.md) after resolving that question.
Bounded catalogs use `dcsmizzer.cli-summary/v1` and a 12 KiB UTF-8 budget;
exact record queries may be complete, while full reports require the explicit
`--details` or `--full` shown by help.

## `capabilities`

```powershell
python Tools\dcsmizzer.py capabilities
```

Run first. The report is the authoritative implemented/partial/unavailable
matrix.

## `dcs-static`

```powershell
python Tools\dcsmizzer.py dcs-static `
  --dcs-root "D:\path\to\DCSWorld"
```

Returns installed version/build when discoverable, module directories, country
source summary, default-payload scan coverage, and facts still requiring
runtime export. Directory presence is not entitlement or activation.

## `dcs-modules`

```powershell
python Tools\dcsmizzer.py dcs-modules `
  --dcs-root "D:\path\to\DCSWorld" `
  --unit-type "EXACT INTERNAL TYPE"
```

Optional exact filters are `--unit-type` and `--module` (a directory name or
`CoreMods/aircraft/NAME`-style module key). With `--unit-type`, optional
`--service-country` and `--service-year` filters require at least one literal
service-life record matching both:

```powershell
python Tools\dcsmizzer.py dcs-modules `
  --dcs-root "D:\path\to\DCSWorld" `
  --unit-type "EXACT INTERNAL TYPE" `
  --service-country "EXACT COUNTRY STRING" `
  --service-year 1988
```

The detailed report links:

- literal plugin IDs passed to `declare_plugin`;
- literal flyable types passed to `make_flyable`;
- default-payload unit types found under that same module directory;
- for `--unit-type`, separate flyable/payload module keys and plugin-ID sets
  for flyable versus payload/asset modules;
- literal `declare_service_life` country/year records for that exact type,
  when present under the matching module directories;
- relative entry source, SHA-256, scope, and unresolved dynamic calls.

The command parses literals only and never executes `entry.lua`. It does not
prove ownership, activation, or runtime availability. An exact service query
with no literal match returns exit code 1. That means this particular static
source did not declare the relationship; it is unresolved evidence, not proof
that the aircraft was historically absent. Do not claim a literal match or
silently substitute a different aircraft. Use a version-matched official
manual/product source or parsed mission where appropriate, and retain the
unresolved static-service warning.

## `dcs-cloud-presets`

```powershell
python Tools\dcsmizzer.py dcs-cloud-presets `
  --dcs-root "D:\path\to\DCSWorld" `
  --preset "EXACT_PRESET_ID"
```

Safely scans literal GUI cloud-preset blocks in the current installed
`Config/Effects/clouds.lua`. The report returns exact preset ID, display name,
precipitation power, allowed base-altitude range, source hash, and parse
coverage. An exact preset with no match returns exit code 1.

This resolves only the cloud preset. Wind at each altitude, fog, visibility,
temperature, pressure, and turbulence remain separate mission weather fields.
No Lua is executed.

## `dcs-weather`

```powershell
python Tools\dcsmizzer.py dcs-weather `
  --dcs-root "D:\path\to\DCSWorld"
```

Use the bounded default catalog to discover `presets[].id`. An exact
`--preset ID` returns the bounded supported-field view of that exact static or
dynamic Mission Editor preset; use `--details` only when full report records
for a broader filtered set are needed. Treat the exact result as usable only
when `validation.fields_complete` and `validation.consistent` are both true.
The report exposes `missing_fields`, `invalid_fields`, `unsupported_fields`,
and `truncated_fields`; its constraint result applies only to
`evaluated_fields`. Every parsed record and the statically extracted
precipitation, temperature, fog, and dust constraints are bound to installed
source hashes, with parse and consistency failures reported.

This is stronger than `dcs-cloud-presets`, but it still does not prove unknown
future fields, rendered weather, terrain/date temperature acceptance, mission
loading, or runtime behavior. Saved Games presets are outside this command. No
preset or Mission Editor Lua is executed.

## `dcs-countries`

```powershell
python Tools\dcsmizzer.py dcs-countries `
  --dcs-root "D:\path\to\DCSWorld"
```

The compact default returns bounded records and coverage. The detailed report
returns:

- exact identifier order from installed `db_countries.lua`;
- `{id, identifier}` entries;
- source-relative path and SHA-256;
- duplicate diagnostics and numeric-ID derivation.

The numeric IDs are derived from the installed source's `next_index = 0` and
the ordered `country:add` plus explicit `country:next()` events. Reserved IDs
are returned separately. Re-query after a DCS update; never enumerate only the
visible country names because a reserved gap would shift later IDs.

## `dcs-payload-index`

```powershell
python Tools\dcsmizzer.py dcs-payload-index `
  --dcs-root "D:\path\to\DCSWorld"
```

The compact default returns bounded unit discovery and aggregate coverage. The
detailed report indexes every safe data-only default-payload source in the
declared central and module scopes, including exact unit-type strings,
sources/hashes, preset and pylon-assignment counts, unique-CLSID counts, task
IDs, and parse failures. The top-level `coverage` object gives aggregate
source, unit, preset, assignment, unique-CLSID, and task-ID coverage so an
Agent does not need to load or sum the full per-aircraft list.

Use it to discover the exact `--unit-type` string. It does not return all
CLSIDs; call `dcs-payloads` for one exact type.

Procedural Lua is rejected and listed, not executed. `compatibility_complete`
is false.

## `dcs-payloads`

```powershell
python Tools\dcsmizzer.py dcs-payloads `
  --dcs-root "D:\path\to\DCSWorld" `
  --unit-type "EXACT INTERNAL TYPE"
```

Use the compact preset catalog first. Select one preset, then request its full
pylon records through the exact filter or explicit full-report option shown by
current help. Redirect full stdout before inspecting it. Detailed output returns
exact default preset names, station evidence, CLSIDs, numeric task constants,
source-relative paths/hashes, total source coverage, and all parse-failure
sources.

The copy-ready records are under `presets[]`. Their exact field names are:

```text
presets[].name
presets[].display_name
presets[].tasks[]
presets[].pylons[].num
presets[].pylons[].CLSID
presets[].pylons[].station_evidence
```

`num` is the authored station and `CLSID` is case-sensitive. Do not invent
lowercase `station`/`clsid` aliases. For a type with many presets, redirect the
JSON to a working file and inspect only matching preset names instead of
printing the entire report into model context.

Use assignments only as verified preset observations. Do not rearrange CLSIDs
between stations or claim a complete compatibility matrix.

## `dcs-payload-match`

```powershell
python Tools\dcsmizzer.py dcs-payload-match `
  --dcs-root "D:\path\to\DCSWorld" `
  --unit-type "EXACT INTERNAL TYPE" `
  --pylon '1={EXACT-CLSID}' `
  --pylon '2={EXACT-CLSID}' `
  --task 11
```

Supply the whole authored pylon table, not one pair. The bounded default
returns the classification, normalized query counts, composition/configured
composition fingerprints, exact-match counts, source-set hash, and bounded
match evidence. Add `--details` for pair observations, complete provenance,
integrity diagnostics, and limitations.

Only `exact_observed_preset` returns exit code 0. Ambiguous presets, pairwise
custom compositions, unknown pairs, duplicate stations, metadata mismatch,
missing per-store settings, and missing unit evidence return nonzero rather
than being promoted to compatibility. The CLI accepts station/CLSID pairs;
use `--empty` for a complete payload with no assignments. When an installed
preset contains per-store `settings`, use the Python API to
supply them or retain the non-exact configuration result. Even an exact
fingerprint proves one source-bound installed default preset, not the complete
runtime compatibility matrix. A relevant/unknown parse failure or any
malformed table or preset for the queried unit makes candidate enumeration
incomplete and prevents an exact result.

## `dcs-airbases`

Summary for an installed terrain directory:

```powershell
python Tools\dcsmizzer.py dcs-airbases `
  --dcs-root "D:\path\to\DCSWorld" `
  --terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY"
```

Compact summary for one exact radio/beacon-encoded ID:

```powershell
python Tools\dcsmizzer.py dcs-airbases `
  --dcs-root "D:\path\to\DCSWorld" `
  --terrain "EXACT_INSTALLED_TERRAIN_DIRECTORY" `
  --airdrome-id 123
```

The bounded exact view returns IDs, names, callsigns, beacon types, and
radio/beacon counts. To inspect complete `beacons[]`, `radios[]`, coordinates,
and source details, add `--details` and redirect stdout to a working JSON file.
The underlying report is the union of IDs/names/callsigns found in the
terrain's static `radio.lua` and beacon source, with both source hashes and
separate radio/beacon/union coverage counts. The union is still not declared
complete. The terrain directory is not necessarily the `mission.theatre`
string. Beacon coordinates are not airport centers, runway thresholds, or
parking positions.

## Terrain identity and physical evidence

Use `terrain-catalog` to distinguish the dated official product-card survey
from unique `mission.theatre` identities. For height, surface, scenery,
placement, corridor, airport-envelope, declared-version, runtime-attestation,
and locally unavailable-theatre gates, use the bounded
[physical-terrain router](../terrain-physical.md) and current CLI help. Static
installed-data sources and upstream planning coordinates cannot replace that
physical evidence.

## `dcs-gci`

Query the current installed MiG-29A native GCI evidence:

```powershell
python Tools\dcsmizzer.py dcs-gci `
  --dcs-root "D:\path\to\DCSWorld"
```

The compact report links three current-install evidence layers:

- the exact `GCI_station_MiG29` static declaration and its declared countries;
- the official training mission's observed
  `ComboTask -> WrappedAction -> ActivateGCI` structure and parameter fields;
- the installed English manual hash and relevant printed pages 177-181,
  including the compatible-radar list and 250 km link radius.

Use the report's exact internal names and construction fields. The current
manual states that instrument GCI guides player aircraft, not AI aircraft.
Static checks cannot prove line of sight, terrain masking, radio reception,
target assignment, or gameplay behavior. A missing declaration or official
training observation returns exit code 1. Do not replace native GCI with a
`groundControl` table or briefing prose.

## `dcs-options-template`

```powershell
python Tools\dcsmizzer.py dcs-options-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --player-name DCSMizzer `
  --full-sim
```

Safely parses the current installed data-only
`MissionEditor/data/scripts/options.lua`, emits the `options` table for a build
spec, sets the requested nonempty `playerName`, and forces the five local audio
device fields to empty strings. It never returns the original device values.

`--full-sim` changes only the explicitly reported difficulty fields. Plugin
options, views, map visibility, and other scenario policies are not inferred.
Use the returned source hash and policy record in provenance rather than
copying options from a private mission.

## `dcs-warehouse-template`

```powershell
python Tools\dcsmizzer.py dcs-warehouse-template `
  --dcs-root "D:\path\to\DCSWorld" `
  --airdrome-id 101 `
  --airdrome-id 102 `
  --coalition NEUTRAL
```

After the exact numeric IDs have been resolved for the selected terrain, emits
a complete unlimited-mode `warehouses` table with numeric `$fields` airport
keys. The command verifies the current Mission Editor literals used by the
template but does not execute that source.

The caller-supplied IDs and authored initial coalition are not inferred or
validated by this command. The empty inventory arrays do not reproduce an
initialized DCS resource registry; use `audit-spec` to ensure that every
mission-used departure or recovery airdrome is represented.
