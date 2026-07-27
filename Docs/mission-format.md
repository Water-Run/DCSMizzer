# Observed MIZ and CMP format

This is an observed structure contract, not a generation API.

## MIZ

A `.miz` is a ZIP archive. Common core members:

```text
mission
options
warehouses
l10n/DEFAULT/dictionary
l10n/DEFAULT/mapResource
```

Historical valid missions may omit some nonessential members. The 2026-07-27
survey found nine missing historical core members without ZIP/CRC corruption.
Do not assume every old mission matches a modern template.

The `mission` Lua table commonly contains:

- `version`, `theatre`, `date`, `start_time`, `weather`;
- coalition sides, countries, categories, groups, units;
- unit payload pylons with `CLSID` and station `num`;
- group routes, waypoint actions, and nested task IDs;
- triggers/trigrules, goals, forced options, ground control;
- briefing dictionary keys and resource mappings;
- warehouses;
- newer fields such as `dynSpawnTemplate`, `DTC`, `dataCartridge`,
  `datalinks`, and `coldAtStart`.

Coordinates are map-local. Do not paste latitude/longitude into mission
`x`/`y`. Exact projection, airport ID, runway, and parking data require
version-matched map evidence.

## Safe reading

The product parser accepts a constrained data-only Lua subset:

- assignments, return values, tables, strings, numbers, booleans, `nil`;
- string/numeric/bare keys and implicit arrays;
- comments, common escapes, Unicode, UTF-8 BOM, UTF-8, CP1251;
- the observed `_("<text>")` data wrapper.

It rejects arbitrary function calls, `require`, function definitions, member
execution, I/O, and system access. It applies input, depth, node, string, ZIP
member, expanded-size, and compression-ratio limits.

Mission scripts, trigger scripts, and initialization scripts are counted but
never executed.

## CMP

A `.cmp` is a Lua data file whose `campaign` table commonly includes:

```text
version
name/description and localized variants
directory/fullPath
startStage
stages
```

Stages contain relative MIZ references and score intervals. A static check can
prove that references resolve and intervals are well formed. It cannot prove
campaign progression in DCS.

## Inspection

```powershell
python Tools\dcsmizzer.py inspect path\mission.miz
python Tools\dcsmizzer.py inspect path\campaign.cmp
```

The output intentionally separates archive, parse, static, and runtime states.
