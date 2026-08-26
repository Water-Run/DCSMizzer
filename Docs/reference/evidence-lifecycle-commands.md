# Evidence lifecycle commands

Use these commands to preserve current local evidence, detect DCS/source drift,
and decide whether a named technical domain is ready. They never start DCS or
Mission Editor. Current CLI `--help` remains authoritative for syntax.

## Create a content-addressed snapshot

```powershell
python Tools\dcsmizzer.py evidence-snapshot `
  --dcs-root "D:\path\to\DCSWorld" `
  --bundle-root output\evidence-bundles `
  --cache-root output\upstream
```

`evidence-snapshot` performs the complete read-only collection twice and
requires byte-identical normalized results before writing anything. It records
the exact DCS product version, distribution/build, executable and supported
control-API hashes, installed terrain identities, DCSMizzer version/clean Git
commit, report schemas, authority labels, coverage, collection outcome, and
optional acknowledged-upstream locks.

Use repeated explicit inputs to bind previously collected higher-authority
evidence without starting DCS:

```powershell
python Tools\dcsmizzer.py evidence-snapshot `
  --dcs-root "D:\path\to\DCSWorld" `
  --bundle-root output\evidence-bundles `
  --cache-root output\upstream `
  --runtime-manifest `
    "$env:USERPROFILE\Saved Games\DCSMizzer-RUN_ID\DCSMizzer\manifest.json" `
  --terrain-evidence output\terrain-evidence.json
```

Each runtime manifest is revalidated through the exact runtime collection
contract. Its attestation retains the manifest/execution/result/log hashes and
bounded result summary but strips absolute paths and raw logs. Each terrain
file passes the physical-evidence schema validator; the attestation retains
the full raw-file hash and coverage hashes/counts but does not embed raw
samples, scenery objects, or airfield geometry. Retain that external raw file
locally for later physical queries.

The output directory is the SHA-256 of the canonical manifest without its
self-identifying `bundle` field. Every artifact is canonical JSON under
`artifacts/` and has an exact size/hash/schema/authority record. A missing
bundle root is created only when its safe parent already exists. Existing
content is never overwritten.

Exit code 1 means that the bundle was preserved but its collection was partial,
its producer worktree was dirty, or a collected domain was blocked. Such a
bundle is useful for diagnosis but cannot pass a production readiness gate.
Static module, payload, and airfield authority may remain partial without
blocking snapshot creation; readiness still fails when those domains are
required. Raw bundles remain local under the ignored `output/` tree and have
not undergone redistribution review.

## Verify exact bytes and membership

```powershell
python Tools\dcsmizzer.py evidence-verify `
  output\evidence-bundles\BUNDLE_SHA256
```

Verification rejects a noncanonical manifest, wrong directory/content ID,
unsafe file kind, missing or extra artifact, duplicate identity, unknown
schema, authority/coverage mismatch, cross-artifact DCS identity conflict,
changed size/hash, and byte-limit breach.
It verifies the bundle's bytes and bindings; it does not cryptographically
authenticate who originally produced a report or rerun the report's semantic
claims.

## Compare old and new evidence

```powershell
python Tools\dcsmizzer.py evidence-diff `
  output\historical-installation-report.json `
  output\evidence-bundles\BUNDLE_SHA256
```

Inputs may be verified bundle directories or recognized standalone evidence
reports. The comparison normalizes installation identity, country identifiers,
installed modules, payload observations, weather, airfields, capabilities, and
upstream pins where present. A different source scope is
`incomparable_basis`, never silently presented as a content change or equality.
Changed, removed, and incomparable domains are listed for invalidation while
the earlier source remains untouched.

## Gate current readiness

```powershell
python Tools\dcsmizzer.py evidence-readiness `
  output\evidence-bundles\BUNDLE_SHA256 `
  --dcs-root "D:\path\to\DCSWorld" `
  --cache-root output\upstream `
  --require installation `
  --require countries `
  --require weather
```

The command first verifies the bundle, requires two matching new read-only
collections, and compares normalized domains. Each record independently
reports freshness (`current`, `stale`, `incomparable_basis`, absent, or
current-check unavailable) plus bundled, current, and conservative effective
coverage (`complete`, `partial`, `blocked`, or absent). Fresh bytes do not
upgrade partial static authority. A clean commit-bound producer, complete
collection, current fingerprint, and complete coverage in both the bundle and
current collection are all required for a named decision domain to pass.

Pass the same `--runtime-manifest` and `--terrain-evidence` inputs when those
domains are required. Omitting a previously bundled external input produces
`current_check_unavailable`; it is never assumed current. A runtime collection
from a dirty producer or a non-valid run is blocked. An initialized terrain
export with only a declared version remains partial; complete finite-scope
terrain authority requires runtime-attested version identity.

Without explicit `--require`, the command gates installation, countries,
modules, payloads, weather, and every installed-terrain airfield record. It is
expected to fail while initialized module, payload-compatibility, and complete
airfield evidence remain unavailable; the detailed states are the actionable
readiness result.
