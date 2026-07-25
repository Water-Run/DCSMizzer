# DCSMizzer Agent Guide

## Project reality

DCSMizzer is an Agent-oriented generator for DCS World simulations and combat
scenarios. The user describes the desired simulation in natural language; the
Agent uses this repository, verified DCS data, and available tools to produce
it.

This project is still in its survey and groundwork phase. Sparse or empty
directories are normal. Treat the files and working programs that actually
exist as the source of truth. A directory name, document, plan, or reference
snapshot does not prove that a capability has been implemented or validated.

## Capability gate

Before starting project work, verify that the current session meets all of
these requirements:

- It is not a Mini or other lightweight model and is at least GPT-5.6-class in
  reasoning and coding ability.
- It has working internet search.
- It can handle multimodal input when source material requires it.
- It has enough context, tool use, and long-horizon reliability for sustained
  repository and mission analysis.

If the environment does not expose enough information to verify the model tier,
say so. If any required capability is unavailable, tell the user and ask them
to switch to a suitable session. Never claim capabilities merely from
confidence in the answer.

## Required startup sequence

1. Read one project introduction: use either `README.md` or `README-zh.md`,
   choosing the language most useful for the request. Do not read both unless
   translation differences matter.
2. Index the repository before deciding how to work. Inspect Git status, the
   directory tree, tracked and relevant untracked files, and the real contents
   of the areas involved. Establish what exists, what is empty, what is only a
   reference, and what is executable.
3. Preserve unrelated user changes. Do not assume a dirty worktree is yours.
4. For mission or campaign research and generation, complete the evidence
   workflow below before relying on model memory.
5. Implement only with facilities that actually exist, then run the relevant
   validation that is actually available.

## Evidence workflow

### Upstream source

Use `.develope/upstream` for acknowledged third-party projects:

- Clone missing repositories or update existing clean clones when network
  access permits. Use safe fast-forward updates; never reset, clean, or
  overwrite a dirty clone.
- Record the remote, branch, and commit inspected so conclusions remain
  traceable.
- Make an initial pass over each relevant repository's README, license, tree,
  entry points, and main data model. Then open the task-relevant source files.
  Do not invent upstream behavior from memory or from filenames alone.
- Treat every clone as read-only reference material. Keep its license terms and
  do not copy or redistribute third-party source as DCSMizzer code.

`.develope/reference` may contain extracted survey results. These are partial
snapshots, not a complete or automatically current DCS database. Check their
provenance and version before use, and return to primary data when necessary.

### Real missions and campaigns

Actively locate legitimate `.miz` missions and related campaign files such as
`.cmp` on the user's device. Relevant roots can include:

- Installed DCS World directories and their built-in missions, training,
  campaigns, and module content.
- Every applicable `Saved Games\DCS*` directory, including user missions and
  downloaded campaign content.
- `.develope/official-campaigns` and other local development mirrors.
- Other user-provided or clearly identified local mission collections.

Search read-only unless the user explicitly requests a write. A `.miz` is an
archive: open and parse its real contents rather than judging it by filename.
When present, inspect the mission table, options, warehouses, dictionaries,
resource mappings, scripts, briefing assets, and campaign metadata. Compare
structure, coalition setup, groups, tasks, waypoints, triggers, pacing,
briefings, player slots, loadouts, and failure or success conditions.

Report which roots were searched and any access or coverage limits. Do not
claim that real missions were studied unless files were actually opened and
parsed. Never paste, commit, or redistribute copyrighted mission, campaign,
audio, image, or briefing content.

### Current web information

Search the web whenever a fact can change or local evidence is insufficient.
This includes current DCS versions, modules, maps, weapons, store availability,
patch behavior, known constraints, and upstream status.

Prefer Eagle Dynamics documentation, product pages, changelogs, and other
primary sources. Use community sources for observed behavior only when useful,
and distinguish them from authoritative data. Record dates or versions and
cross-check important claims. Do not present model memory as current fact.

### Choosing evidence

Use the source closest to the question:

- Installed DCS data and verified exports for internal identifiers and local
  compatibility.
- Parsed real missions for archive structure and established mission patterns.
- Current upstream source for library behavior and data models.
- Primary web sources for current product and patch information.
- Project survey snapshots only within their documented scope.

When sources conflict, identify the versions involved and explain which source
was used. Do not silently blend incompatible data.

## Generation rules

- The user's request defines the scenario. Preserve specified era, coalition,
  module, map, realism, player count, weather, start state, duration, and output
  constraints.
- Verify exact DCS type names, mission fields, coordinates, airbase and parking
  identifiers, weapon CLSIDs, pylon compatibility, unit capabilities, and
  supported tasks. Do not invent them.
- Do not silently substitute a different aircraft, map, weapon, target, or
  mission type. Explain any verified limitation and ask when the alternative
  would materially change the request.
- Prefer deterministic inputs and record seeds or source versions when the
  available tooling supports them.
- Keep generated work separate from read-only upstream projects, installed DCS
  files, and reference missions.

## Validation and completion

Run every relevant validation facility that actually exists in the repository.
For generated missions, also inspect the resulting archive and confirm that its
required files parse and that major scenario constraints survived generation.
Use DCS itself when runtime validation is available.

Report:

- What was generated or changed.
- Which data and source versions were used.
- Which checks ran and their results.
- Which checks could not run and why.
- Any remaining uncertainty that affects playability or fidelity.

Do not call a `.miz`, campaign, data extract, or validation report complete
unless the corresponding generation, parsing, or validation step actually ran.
