# Continuous validation

The repository's ordinary merge gate is
`.github/workflows/product-ci.yml`. It runs on the explicit GitHub-hosted
`windows-2025` label for pushes to `main`, pull requests, and explicit manual
dispatches. This lane validates
repository code and distributable fixtures only. It never starts DCS or Steam,
never prepares or updates upstream caches, and never claims a DCS runtime tier.

## Reproducible tool boundary

The workflow uses Python 3.14.3 on Windows x64. Both GitHub-maintained actions
are pinned to full 40-character commits, not movable major tags. Ruff 0.16.2 is
installed from the exact Windows x64 wheel hash recorded in
`.github/requirements-ci.txt`; pip is required to use hashes, binary packages,
and no dependencies.

These pins were reviewed on 2026-08-26 against the official
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python), and
[Ruff releases](https://github.com/astral-sh/ruff/releases). A future update is
an explicit reviewed dependency change, not an automatic move to “latest.”

The workflow grants only `contents: read`, does not persist checkout
credentials, has a 20-minute job timeout, and cancels superseded runs on the
same ref. Fork pull requests therefore receive no write capability from this
workflow.

## Gates

The ordinary lane runs:

- the complete product unit-test discovery;
- the maintainer survey-test discovery; the two frozen-commit path audits run
  when all six ignored, read-only upstream evidence roots are present and are
  reported as explicit skips in a clean hosted checkout, while the hermetic
  suite proves that absent roots fail closed;
- repository document-link and bilingual Prompt-sample validators;
- Ruff `E`, `F`, and `B` rules over product code and tests;
- Python bytecode compilation over product and survey code.

The corresponding release-checkout commands that do not depend on maintainer
survey material are:

```powershell
python -m pip install --no-deps --only-binary=:all: --require-hashes -r .github\requirements-ci.txt
python -m unittest discover -s Tools\tests
python Tools\validate_document_links.py
python Tools\validate_prompt_samples.py
ruff check --select E,F,B Tools\dcsmizzer Tools\tests
python -m compileall -q Tools
```

For the complete local evidence lane, populate the acknowledged clones under
`.develope/upstream` at the commits recorded by the survey, then run the same
survey discovery command. Missing clones never produce a validated provenance
manifest: the CLI returns failure and lists each unavailable commit source.

The CI contract itself has unit tests. They reject movable action references,
write permissions, credential persistence, unpinned Ruff input, missing release
commands, absent timeout/concurrency controls, and accidental DCS/runtime or
mutating-upstream commands.

## Authority and remaining external lane

A green ordinary run establishes only that the checked-out repository revision
passed its static and synthetic release matrix on the declared hosted runner.
It does not establish that branch protection required the run, that a local
evidence bundle is current, or that any MIZ loaded in DCS.

The authorized Windows/DCS lane remains deliberately separate. It requires a
legal local installation, explicit launch authorization, isolated profiles,
and exact runtime collection. Its blocked or absent result cannot be replaced
by ordinary CI success.
