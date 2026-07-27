# Validation and completion

## Validation levels

| Level | Proves | Does not prove |
|---|---|---|
| Archive-valid | ZIP opens, paths/policy are safe, CRC passes | Lua or scenario semantics |
| Parse-valid | Required data tables parse without executing Lua | IDs, compatibility, scenario fidelity |
| Static-valid | Selected structural/reference/resource checks pass | DCS load or gameplay |
| Runtime-valid | Recorded DCS version actually loaded/ran the artifact | Broader versions or unsupported modules |

Never collapse these levels into one `valid` flag.

The current product can establish archive, parse, and limited static states.
It cannot establish runtime validity.

## MIZ static checks

At minimum:

- valid/path-safe/unencrypted archive;
- CRC checked;
- `mission` and `warehouses` data tables parsed;
- core member status reported;
- theatre/version observed;
- groups, units, slots, routes, tasks, pylons, triggers, goals, resources, and
  warehouse coverage reported;
- referenced missing resources reported;
- scripts never executed.

## CMP static checks

At minimum:

- campaign table parsed;
- start stage exists;
- relative paths are safe;
- MIZ references exist;
- intervals are well formed;
- overlaps and gaps are reported rather than normalized away.

## Completion report contract

Every future generated artifact must report:

```text
artifact path
scenario constraints requested
constraints preserved
data sources and versions
generation method and seed
archive checks
parse checks
static checks
runtime checks
checks not run and reason
remaining uncertainty affecting playability/fidelity
```

Do not call a MIZ/campaign complete unless generation and the claimed
validation steps actually ran.

## Current product runtime boundary

The current Python tools have no DCS launch or runtime-validation facility.
Therefore:

- no mission load;
- no Mission Editor resave;
- no initialized registry export;
- no per-terrain airbase export;
- no runtime-valid claim.

The 2026-07-27 development survey separately records that DCS launch was
prohibited for that evidence run. That session-specific restriction is not a
product capability flag.
