# Capabilities

This document is the product truth for routing. Confirm it against:

```powershell
python Tools\dcsmizzer.py capabilities
```

## Implemented

| Capability | Scope |
|---|---|
| MIZ inspection | ZIP safety, CRC, core Lua data parsing, anonymous semantic statistics |
| CMP inspection | Safe data parsing, stage/reference/interval checks |
| Current DCS static scan | Executable version, Steam build when discoverable, installed module directories, country/default-payload source coverage |
| Country lookup | Exact identifiers from current installed `db_countries.lua` |
| Default payload lookup | Exact current preset assignments and task IDs for one unit type |

All implemented commands are read-only. They do not execute Lua, extract MIZ
members, launch DCS, or modify local evidence.

## Not implemented

| Capability | Status |
|---|---|
| Mission generation or serialization | Not implemented |
| Campaign generation or serialization | Not implemented |
| Complete initialized unit registry | Needs version-matched runtime export |
| Complete unit task-capability matrix | Needs version-matched runtime export |
| Complete store-to-station compatibility | Needs version-matched runtime export |
| Airport/runway/parking registry | Needs per-terrain runtime export |
| Mission Editor resave | Not implemented |
| DCS launch | Not implemented; product tools never start DCS or Mission Editor |
| DCS mission load validation | Not implemented |

If a user requests a generated `.miz`, do not synthesize one from memory or
present an inspected/source mission as generated. Explain that the generator is
not implemented, preserve the scenario specification, and identify the exact
missing product capability.

## Meaning of static lookup

Static installed sources can prove:

- the DCS executable version;
- which module directories and entry declarations are present;
- country identifiers in the installed country source;
- default payload presets stored in data-only UnitPayload files.

They cannot by themselves prove:

- account entitlement or successful module activation;
- the initialized Mission Editor registry;
- every legal pylon/store pairing;
- runtime map airbase IDs, parking, or runway behavior;
- that a mission loads or plays.
