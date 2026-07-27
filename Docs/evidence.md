# Evidence and exact-data policy

## Authority order

Use the source closest to the fact:

1. initialized, version-matched DCS or Mission Editor export;
2. current installed DCS data-only source;
3. parsed real missions for observed structures and assignments;
4. current, commit-bound upstream source;
5. frozen legacy survey snapshots.

Web information is appropriate for current public release/module/patch facts.
Prefer Eagle Dynamics primary pages and record the date/version.

## Exact-data routing

| Needed fact | Best available route | Current limitation |
|---|---|---|
| DCS/Steam version | `dcs-static` | Static version only; no runtime confirmation |
| Installed module directories | `dcs-static` | Presence is not entitlement/activation |
| Country identifiers | `dcs-countries` | Current static authority |
| Default preset CLSIDs/tasks | `dcs-payloads` | Presets are not complete compatibility |
| Unit type registry | Runtime export | Not available |
| Per-unit task capabilities | Runtime export | Not available |
| Complete pylon compatibility | Runtime export | Not available |
| Airbase IDs/coordinates/runways/parking | Per-terrain runtime export | Not available |
| MIZ/CMP observed structure | `inspect` plus survey corpus | Does not prove runtime behavior |

## Version and conflict handling

Every exact value should carry:

```text
value
authority
source
source version/commit
observed date
coverage
known conflict or limitation
```

When sources disagree:

1. do not merge them silently;
2. identify both versions;
3. prefer the higher-authority version-matched source;
4. keep the lower source as historical/reference evidence;
5. leave the value unresolved if authority is insufficient.

## Frozen development references

`.develope/reference/data` contains 45 frozen legacy files. Their one-off
extractors are unavailable. Provenance is recorded in
`.develope/reference/provenance.json`, and every reference document is marked
as historical. Do not use those files as implicit current truth.

Six current upstream clones are useful for behavior and data-model research,
but none overrides the local DCS registry. Do not copy upstream code into
product paths.

## Copyright and privacy

- Parse local real missions read-only.
- Do not redistribute mission/campaign/audio/image/briefing content.
- Do not commit private mission names, briefing text, local absolute paths,
  Steam account identifiers, or per-file mission hashes.
- Generated work must be separate from installed DCS, Saved Games evidence,
  official mirrors, upstream clones, and frozen references.
