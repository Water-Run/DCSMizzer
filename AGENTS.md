# DCSMizzer Agent Guide

## What this repository is

DCSMizzer is an Agent-oriented generator for DCS World simulations and combat
scenarios. A user runs a Coding Agent in this repository and describes the
simulation they want in natural language. The Agent uses the repository's
documentation, tools, and verified DCS data to create the requested result.

DCSMizzer is under active development. Treat the files that actually exist in
the repository as the source of truth. Do not pretend that a documented,
planned, or missing capability is already implemented.

## How to handle a request

1. Understand the user's intent before choosing a scenario pattern or reading
   an example as a template.
2. Read the matching project introduction:
   - `README.md` and `PROMPT-SAMPLE.adoc` for English;
   - `README-zh.md` and `PROMPT-SAMPLE-zh.adoc` for Chinese.
3. Inspect the relevant material in `Docs` and use the available programs in
   `Tools`. Read only what the request needs.
4. Query or verify exact DCS data instead of relying on model memory.
5. Generate the requested simulation and any requested supporting material.
6. Run every relevant validation facility that is actually available in the
   repository, report its results honestly, and identify any checks that could
   not be performed.

## Working rules

- The user's request defines the scenario. Prompt examples demonstrate useful
  requests; they are inspiration, not fixed templates or hidden requirements.
- Do not invent DCS internal type names, mission fields, coordinates, airbase
  identifiers, parking positions, weapon CLSIDs, payload compatibility, unit
  capabilities, or supported tasks.
- Keep era, coalition, module, realism, player-count, weather, start-state,
  duration, and output constraints when the user specifies them.
- Prefer deterministic project data and Tools for facts that can be checked.
- Do not silently substitute a different aircraft, map, weapon, target, or
  mission type when a request cannot be satisfied. Explain the limitation.
- Do not claim that a `.miz` file or validation report is complete unless the
  corresponding generation or validation step was actually run.
- Preserve unrelated user files and changes while working in the repository.

## Development references

`.develope/upstream` contains complete local Git clones of acknowledged
third-party projects. Use them only as read-only development references for
understanding formats, data models, and established approaches. They are not
DCSMizzer source, must keep their own license terms, and must not be copied or
redistributed as if they belonged to this project.
