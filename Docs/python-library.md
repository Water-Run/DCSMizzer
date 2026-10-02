# Python library

DCSMizzer 0.12.0 exposes the existing toolkit as an installable library.

## Install and choose an entrypoint

Install the existing `Tools/dcsmizzer` package from the repository root with
`python -m pip install .`, or use `python -m pip install -e .` for development.
The supported Python baseline is 3.14; product imports need only the standard
library. The installed command is `dcsmizzer`, also available through
`python -m dcsmizzer`. The repository script and `Tools/validate.py` remain
available.

## Public Python API

The public root API loads functions on demand. `import dcsmizzer` does not
run a command, launch DCS, query data, change Python's import path, or
reconfigure output streams. Use `pathlib.Path` for filesystem arguments:

```python
from pathlib import Path
from dcsmizzer import ArchivePolicy, LuaLimits, inspect_miz, analyse_miz

archive = inspect_miz(Path("output/mission.miz"), policy=ArchivePolicy())
if archive.safe:
    mission = analyse_miz(Path("output/mission.miz"), limits=LuaLimits())
    print(mission.theatre, mission.parse_valid)
```

| Function | Result and scope |
|---|---|
| `capabilities_report()` | Independent dictionary of current implemented/partial/unavailable capabilities |
| `inspect_miz(path, *, policy=None, verify_crc=True)` | `ArchiveInspection`; ZIP safety, member limits, and optional CRC checks; accepts a `Path` or seekable binary stream |
| `analyse_miz(path, *, limits=None)` | `MizObservation`; bounded Lua core parsing and mission statistics; accepts a `Path` or seekable binary stream; run archive safety checks first |
| `analyse_cmp(path, *, limits=None)` | `CampaignObservation`; CMP structure and local mission-reference checks |
| `load_build_spec(path)` | Parsed `BuildSpec`; use the existing normative spec contract |
| `build_miz(spec_path, output_path, *, force=False)` | `(report, passed)`; writes a deterministic MIZ and performs available static read-back checks; refuses overwrite by default |
| `verify_miz(miz_path, spec_path)` | `(report, passed)`; checks an existing artifact against the supplied spec |

`BuildSpecError` and `LuaDataError` are also exported for exception handling.
Observation objects retain the existing fields defined in their modules;
the API does not convert them into CLI JSON. Advanced evidence, terrain,
installed-data, and runtime APIs remain available in their existing submodules.

## Construct and verify an explicit spec

For an already authored, evidence-audited spec, construction can be called
directly:

```python
from pathlib import Path
from dcsmizzer import build_miz, verify_miz

spec = Path("output/spec.json")
miz = Path("output/mission.miz")
build_report, built = build_miz(spec, miz)
if not built:
    raise RuntimeError("MIZ failed its static construction checks")
verify_report, verified = verify_miz(miz, spec)
if not verified:
    raise RuntimeError("MIZ failed its static spec verification")
```

Read [build-spec.md](build-spec.md) for the actual input contract. These calls
do not plan a scenario, automatically audit source evidence, or prove DCS
playability. Preserve reports and check both returned booleans. Static success
does not supply a runtime validation result.

## Provenance and source caches

The installed CLI delegates provenance-sensitive invocations to the original
isolated bootstrap when running from the source layout. With a wheel, those
invocations fail before loading the CLI; ordinary inspection, low-level
construction, unbound queries, and all command help remain available.
External `--evidence-bundle` bindings use the same source-checkout gate.
This preserves the existing Git producer boundary without giving installed
artifacts a false source identity.

For provenance work use `python Tools/dcsmizzer.py ...` from a clean standalone
clone. An editable install also supports `python -B -m dcsmizzer ...` through
that bootstrap. Ordinary Python imports and console-script startup can create
source `__pycache__` files, which the checkout integrity gate refuses; use
`-B` or set `PYTHONDONTWRITEBYTECODE=1` before starting Python when the source
tree must remain cache-free. Editable package metadata stays at the repository
root, outside the protected `Tools` import tree. Direct library imports do not
carry the bootstrap's pre-import integrity guarantee.

## Build and check distributions

Run the repository validation matrix from a full clone before building;
see [continuous-validation.md](continuous-validation.md). Build a wheel
and source distribution locally:

```powershell
python -m pip install build
python -B -m build
```

Packaging uses the existing package version as its single version source and
includes `resources/runtime_hook.lua` and the GPL license. Only product Python
and declared resources enter the wheel. The source distribution also includes
product guides, Prompt samples, and repository entry scripts; it excludes
development surveys, upstream clones, local evidence, tests, and generated
missions. The package build follows the
[PyPA metadata guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
and [setuptools resource configuration](https://setuptools.pypa.io/en/latest/userguide/datafiles.html).

A basic installed-package check can run in a disposable environment:

```powershell
python -B -m venv tmp\package-check
tmp\package-check\Scripts\python -m pip install dist\dcsmizzer-0.12.0-py3-none-any.whl
tmp\package-check\Scripts\python -B -m dcsmizzer capabilities
tmp\package-check\Scripts\python -B -c "from dcsmizzer import inspect_miz, build_miz, verify_miz"
```

For release verification, additionally check that the wheel contains the Lua
template and license, the source archive can rebuild a wheel, all product
modules import, and a synthetic fixture can build, parse, and verify outside
the source tree. Check the console and module entrypoints, overwrite refusal,
and refusal of provenance work without a verified source checkout. Test
editable and ordinary source installation separately. These are package/static
checks and do not start DCS or prove mission playability.
