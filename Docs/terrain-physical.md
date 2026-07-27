# Physical terrain routing

Read this page only when exact ground height, surface, scenery clearance,
mountain clearance, or airport-area geometry affects the mission.

## Keep the evidence layers separate

| Layer | Route | What it proves |
|---|---|---|
| Public terrain identity | `terrain-catalog` | The recorded official survey has 18 product cards but 14 unique `mission.theatre` IDs. Regional entitlements and legacy cards do not create new theatre IDs. This is not physical terrain evidence. |
| Upstream planning snapshot | `terrain-coverage`, `pydcs-*`, `br-*`, `br-airfield-footprint` | Commit-bound identities, projections, airports, parking, and candidate points. BR/pydcs coordinates do not prove height, surface, slope, collision, or mountain clearance. |
| Initialized DCS physical export | Commands using `--evidence` | Only queried samples/objects/airfields from an initialized DCS terrain, Mission Editor, or mission-scripting export. Theatre and declared version metadata remain explicit; runtime-version attestation is a separate field. Unsampled space remains unknown. |

The repository currently contains bounded physical-evidence consumers and a
manual probe-script/log-extraction path. It does **not** contain a committed
runtime physical export, and no product command starts DCS or Mission Editor.
A planning snapshot or uninitialized export therefore fails physical
validation.

The local probe can produce physical evidence only for a theatre that the
user's DCS installation can load and initialize in a matching mission. If a
theatre is uninstalled, unavailable, or not entitled and therefore cannot be
initialized locally, generating a probe script does not prove it. Only a
separately supplied initialized export can pass the physical gate; otherwise
keep that theatre's physical decisions unresolved and use upstream data for
planning only.

## Decision routes

| Need | Command | Gate |
|---|---|---|
| Product card versus theatre ID | `terrain-catalog` | Select the exact `mission.theatre`; do not infer terrain physics. |
| One height/surface point | `terrain-point --evidence ... --terrain ... --dcs-version ... --x ... --y ...` | Requires a matching sample within at most the evidence-declared tolerance. One point proves no surrounding slope or clearance. |
| Arbitrary landmark instance | `landmark-search --evidence ... --terrain ... --dcs-version ... --query ...` | A returned object proves that exported instance exists. Trust a negative result only when the consumer reports `validation.absence_proven=true`; the bundled mission probe cannot produce that proof. |
| Ground-unit footprint, slope, or scenery collision | `placement-check --evidence ... --terrain ... --dcs-version ...` | Returns `sampled_placement_valid` for distinct center/corner samples and conservative exported object/airfield geometry. Positive obstacle clearance requires a producer-declared ground-placement-complete search; airport checks also require a complete inventory and `geometry_complete=true` per airfield. |
| Route versus mountains | `terrain-corridor --evidence ... --terrain ... --dcs-version ... --point X,Y,ALT_MSL ...` | Returns `sampled_corridor_clear` for the centerline and two lateral edges. Three discrete traces do not prove continuous terrain coverage or aircraft performance. |
| Physical airport geometry | `airfield-footprint --evidence ... --terrain ... --dcs-version ... --airfield ...` | Requires a complete airfield inventory and one record declaring complete runway/parking/taxi geometry. Its envelope is derived geometry, never an official airport boundary. |
| Airport planning fallback | `br-airfield-footprint --br-root ... --terrain ... --airfield ...` | Commit-bound planning geometry only; `validation.physical_validation` remains false. |

For a request such as “place a SAM at the pyramids,” first export/search a
pyramid **instance**, then run `placement-check` at the returned local
coordinate using separate ground-placement-complete evidence. Do not place
from the word “pyramid,” a static model name, or an unverified WGS-84 guess.

Every physical CLI query requires both `--terrain` and `--dcs-version`. Treat
a nonzero exit, `evidence.physical_authority=false`, missing sample, ambiguous
landmark, or truncated/insufficient coverage as unresolved.

## Manual probe path

`terrain-probe-script` validates a bounded
`dcsmizzer.terrain-probe-request/v1` JSON file and writes a Lua probe. Requests
may contain explicit `samples`, oriented `placements`, altitude-MSL
`corridors`, and bounded `object_searches`; placement and corridor entries
generate their required sample points automatically.

```json
{
  "schema": "dcsmizzer.terrain-probe-request/v1",
  "terrain": "EXACT_MISSION_THEATRE",
  "sample_match_tolerance_m": 0.25,
  "samples": [{"x": 1000, "y": 2000}],
  "placements": [
    {"x": 1000, "y": 2000, "heading_deg": 90, "length_m": 12, "width_m": 4}
  ],
  "corridors": [{
    "route": [
      {"x": 1000, "y": 2000, "altitude_msl": 500},
      {"x": 5000, "y": 6000, "altitude_msl": 800}
    ],
    "half_width_m": 500,
    "step_m": 250
  }],
  "object_searches": [{"x": 1000, "y": 2000, "radius_m": 100}],
  "max_objects": 1000
}
```

An `object_searches` entry bounds scenery discovery. The generated mission
probe deliberately marks every search
`complete_for_ground_placement=false`: Eagle Dynamics documents the 3D BOX
volume but not whether `world.searchObjects` selects scenery by pivot or
collision box. A probe search can therefore prove a returned object exists,
but its negative result cannot clear a placement or prove a landmark absent.
The extractor may report that all requested object searches were returned, but
each bundled-probe search remains
`complete_for_ground_placement=false`; only the later consumer field
`validation.absence_proven` is the absence decision.

```powershell
python Tools\dcsmizzer.py terrain-probe-script --request request.json --dcs-root D:\DCSWorld --output probe.lua
```

This command only generates the script. It does not execute Lua, start DCS, or
perform runtime validation. Only after a user explicitly runs that script
through a matching mission's **DO SCRIPT FILE** action can its framed
`dcs.log` output be extracted:

```powershell
python Tools\dcsmizzer.py terrain-probe-extract --log dcs.log --request request.json --output terrain-evidence.json
```

The extractor validates framing, request hash, theatre, schema, and requested
sample completeness; it does not authenticate the log producer or prove
unsampled terrain. Its product version identifies the installation used to
generate the script, not a runtime-attested DCS executable; the extracted
evidence therefore retains
`product_version_source="probe_generation_install"` and
`runtime_identity_attested=false`. The mission-scripting probe exports height,
coarse surface type, and bounded scenery discovery, but not ground-placement-
complete object coverage or Mission Editor runway, parking, and taxi geometry.
It can support point, sampled-corridor, and positive-landmark decisions; it
cannot by itself make `sampled_placement_valid=true`. `--allow-airfield`
explicitly waives rather than passes the airport-overlap gate. Run each
command's current `--help` before authoring a request.
