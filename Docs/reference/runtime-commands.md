# Isolated DCS runtime commands

Use this reference only for an explicitly authorized installed-DCS run. Current
CLI `--help` remains authoritative for flags and argument order.

## Lifecycle and authority

The three commands deliberately separate mutation and authorization:

1. `runtime-prepare` creates a new disposable
   `Saved Games\DCSMizzer-<run-id>` profile, a supported GameGUI Hook, and an
   exclusive-create preparation manifest. It does not start DCS.
2. `runtime-run` validates every bound input and returns a dry-run preview by
   default. Only `--authorize-dcs-launch` starts one DCS process.
3. `runtime-collect` validates the execution record and runtime result against
   the exact run ID, mode, hashes, DCS version, and mission when supplied.

Never copy an ordinary user's `Saved Games\DCS*` profile into the disposable
profile. The bridge does not desanitize MissionScripting, write the DCS
installation, use obsolete `net.dostring_in`, or terminate a pre-existing DCS
process.

Before preview or launch, the bridge rechecks the DCS executable, Steam
manifest/launcher when applicable, local Sim Control API, mission, and Hook.
It reconstructs the Hook from the current trusted product resource and the
manifest's bounded inputs rather than trusting a self-declared Hook hash.

## Aggregate initialized-registry probe

```powershell
python Tools\dcsmizzer.py runtime-prepare `
  --dcs-root "D:\path\to\DCSWorld" `
  --saved-games-root "$env:USERPROFILE\Saved Games" `
  --run-id registry-20260826 `
  --mode registry-probe

python Tools\dcsmizzer.py runtime-run `
  "$env:USERPROFILE\Saved Games\DCSMizzer-registry-20260826\DCSMizzer\manifest.json"

python Tools\dcsmizzer.py runtime-run `
  "$env:USERPROFILE\Saved Games\DCSMizzer-registry-20260826\DCSMizzer\manifest.json" `
  --authorize-dcs-launch

python Tools\dcsmizzer.py runtime-collect `
  "$env:USERPROFILE\Saved Games\DCSMizzer-registry-20260826\DCSMizzer\manifest.json"
```

The aggregate probe initializes `me_db_api` inside DCS and returns bounded
counts only. It does not export names, records, proprietary data, or complete
compatibility relationships. A passing aggregate result proves initialization
and those counts for the bound installation; it does not make a complete unit
or pylon registry available.

## Exact-MIZ load and smoke

```powershell
python Tools\dcsmizzer.py runtime-prepare `
  --dcs-root "D:\path\to\DCSWorld" `
  --saved-games-root "$env:USERPROFILE\Saved Games" `
  --run-id mission-smoke-20260826 `
  --mode mission-smoke `
  --mission output\exact.miz `
  --smoke-seconds 10 `
  --coordinate-checks output\coordinate-checks.json
```

`mission-smoke` first requires the exact MIZ to pass archive safety, CRC, and
core-table parsing. The manifest binds its path, size, SHA-256, filename, and
theatre. A coordinate-check file uses
`dcsmizzer.runtime-coordinate-checks/v1`; each record binds a WGS-84 point,
expected mission-local `x/y`, and tolerance. During the loaded mission, the
Hook checks those values through DCS `Export.LoGeoCoordinatesToLoCoordinates`.
Collection independently matches the declared records and recomputes each
reported coordinate error; a result cannot pass by setting its own `passed`
field alone.

A passing collection establishes exact filename/theatre load, mission-load and
simulation-start callbacks, the declared stable interval, bounded entity and
slot observations, and all declared coordinate checks. It does not establish
AI tactics, every trigger branch, mission success/failure reachability, a
Mission Editor resave, or a human playtest.

## Steam behavior and cleanup

Steam may show a custom-arguments confirmation. Confirm it before the reported
120-second startup deadline only when the displayed arguments match the
prepared preview. A generic
`steam_confirmation_or_startup_pending` result means no DCS PID was bound; it
is not runtime success. If Steam reports another active session, do not evict
that session without separate authorization.

For Steam launches, the bridge binds the one new DCS PID only after its
executable path, prepared `-w` profile, and mission argument (when present)
match the manifest. Cleanup re-attests the same identity. Normal Hook exit is
preferred; after a result is present, a ten-second grace provides bounded
exact-process cleanup. Timeout cleanup can terminate and then kill only that
re-attested PID. Ambiguous, untrusted, or identity-lost processes fail closed.

## Evidence handling

Do not commit raw runtime profiles, logs, official missions, or instrumented
derivatives. Retain only privacy-reviewed schemas, summaries, and synthetic
fixtures. Report the DCS product version, Steam build when available, exact
manifest/execution/result hashes, validation tier achieved, checks that did not
run, and any external blocker.
