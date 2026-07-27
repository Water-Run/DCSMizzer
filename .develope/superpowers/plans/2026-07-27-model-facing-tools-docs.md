# Model-facing Tools and Docs implementation plan

**Date:** 2026-07-27
**Prerequisite:** `.develope/survey/REPORT-2026-07-27.md`

## Objective

Create a truthful first product surface that a coding model can route without
reading the development survey tree. The surface must provide runnable,
read-only evidence and inspection commands while refusing generation and
runtime claims that are not implemented.

## Public tool contract

Single standard-library entry point:

```text
python Tools/dcsmizzer.py <command>
```

Commands:

- `capabilities`: machine-readable implemented/unimplemented matrix;
- `inspect PATH`: safe MIZ or CMP archive/data inspection;
- `dcs-static --dcs-root PATH`: current installed module, country, and default
  payload evidence without starting DCS;
- `dcs-countries --dcs-root PATH`: exact identifiers from the installed
  `db_countries.lua`;
- `dcs-payloads --dcs-root PATH --unit-type ID`: exact default presets only,
  explicitly not a compatibility matrix.

The tool must never:

- launch DCS or Mission Editor;
- execute Lua;
- extract MIZ members to disk;
- mutate installed DCS, Saved Games, official missions, or upstream clones;
- claim mission generation, complete pylon compatibility, current runtime
  registry, airport parking, editor-resave, or runtime validation.

## Package layout

```text
Tools/
├─ dcsmizzer.py
├─ validate.py
├─ dcsmizzer/
│  ├─ __init__.py
│  ├─ archive.py
│  ├─ capabilities.py
│  ├─ cli.py
│  ├─ dcs_static.py
│  ├─ lua.py
│  ├─ mission.py
│  └─ campaign.py
└─ tests/
   └─ test_*.py
```

`Tools/` contains Python only. Machine-readable capability data is implemented
in `dcsmizzer/capabilities.py`; all model-readable routing and command
documentation lives under `Docs/`.

The parser implementation is promoted from project-owned, tested survey code;
no third-party source is copied.

## Model documentation

`Docs/index.txt` is the only required first read. It routes to:

- `capabilities.md`
- `workflow.md`
- `evidence.md`
- `mission-format.md`
- `validation.md`
- `tools.md`

Documents are compact contracts, not a second legacy database. Exact values
must be obtained through current tools/evidence and carry authority/version.

## Tests

Write failing product tests first for:

1. capability output refuses generation/runtime claims;
2. safe self-created MIZ inspection and unsafe ZIP rejection;
3. CMP relative reference and interval inspection;
4. exact static country lookup;
5. exact default payload lookup labeled non-compatibility;
6. output contains no implicit runtime-valid state.

Then implement and run both product and development survey test suites.
