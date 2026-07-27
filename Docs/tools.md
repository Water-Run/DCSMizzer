# Tool reference

Unified Python entry point:

```powershell
python Tools\dcsmizzer.py <command>
```

All output is UTF-8 JSON. All commands are read-only and never start DCS.

Purpose-specific validation entry point:

```powershell
python Tools\validate.py path\mission.miz
python Tools\validate.py path\campaign.cmp
```

This is the direct-script form of `dcsmizzer.py inspect`. No construction
script is published yet because mission and campaign construction are not
implemented.

Repository Prompt-catalog validation:

```powershell
python Tools\validate_prompt_samples.py
```

This checks the bilingual user-facing Prompt examples for matching structure,
well-formed source blocks, control characters, and leaked internal engineering
language. It validates repository documentation only; it does not validate a
mission or campaign.

## `capabilities`

```powershell
python Tools\dcsmizzer.py capabilities
```

Run first. The JSON is the authoritative implemented/refusal matrix.

## `inspect` / `validate.py`

```powershell
python Tools\dcsmizzer.py inspect path\mission.miz
python Tools\dcsmizzer.py inspect path\campaign.cmp
```

For MIZ, returns archive inspection, parsed core-member status, anonymous
semantic statistics, and separate validation levels.

For CMP, returns stage/reference/interval statistics and separate validation
levels.

`--skip-crc` is available only when the caller explicitly accepts that CRC was
not verified.

## `dcs-static`

```powershell
python Tools\dcsmizzer.py dcs-static --dcs-root "D:\path\to\DCSWorld"
```

Returns executable version when readable, Steam build when the manifest is
discoverable, module directories, country/default-payload coverage, and the
facts that still require runtime export.

Directory presence and `entry.lua` state do not prove entitlement or runtime
activation.

## `dcs-countries`

```powershell
python Tools\dcsmizzer.py dcs-countries --dcs-root "D:\path\to\DCSWorld"
```

Returns exact identifiers from the installed `db_countries.lua`, its SHA-256,
and duplicate diagnostics.

## `dcs-payloads`

```powershell
python Tools\dcsmizzer.py dcs-payloads `
  --dcs-root "D:\path\to\DCSWorld" `
  --unit-type "F-16C bl.50"
```

Returns exact default preset names, station numbers, CLSIDs, and task IDs for
the requested unit table. `compatibility_complete` is always false: a preset
does not enumerate every legal store/station pairing.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Query succeeded or inspected file passed available static checks |
| 1 | Input was read, but validation failed or lookup returned no match |
| 2 | Usage, path, unsupported extension, or source error |

Do not ignore a nonzero exit code. Parse the JSON for code 1 and stderr for
code 2.
