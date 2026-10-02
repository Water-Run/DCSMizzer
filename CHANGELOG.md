# Changelog

## 0.12.0 — 2026-10-02

- Package the existing Python toolkit as an installable library for Python
  3.14+, with wheel/source builds and a single version source.
- Expose public inspection, Lua limits, explicit-spec construction, and
  verification APIs through `dcsmizzer`; load them on demand without starting
  the CLI or changing interpreter configuration.
- Add `dcsmizzer` and `python -m dcsmizzer` entrypoints. Provenance-sensitive
  commands delegate to the isolated source bootstrap; a wheel without a
  verified Git producer identity refuses them.
- Include the product Lua runtime template and GPL license in distributions.
  Development surveys, upstream clones, local evidence, and generated missions
  remain outside the package.
- Publish the V0-V5 validation contract and separate V2/V3 runtime reporting.
- Validate bounded initialized-registry records and optional exact-runtime
  record slices. The current DCS Hook still emits aggregate counts; a full
  record exporter and complete compatibility registry remain unavailable.
- Run ordinary repository validation with source bytecode writes disabled and
  compilation caches outside the protected source tree.
- Organize installation/API, command routing, mission workflow, capability,
  and validation documentation into their respective guides.

The release provides a low-level mission toolkit. Natural-language planning,
campaign generation, general behavioral validation, and human playtest
validation remain unimplemented. Package or ordinary CI success does not prove
DCS playability.

See [Python library usage](Docs/python-library.md),
[capability boundaries](Docs/capabilities.md), and
[validation meanings](Docs/validation.md).
