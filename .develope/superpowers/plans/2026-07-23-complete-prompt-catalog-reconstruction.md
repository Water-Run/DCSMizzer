# Complete Prompt Catalog Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct both bilingual Prompt catalogs from simple living-world training missions through complex standalone operations, then add 30 detailed named campaign requests.

**Architecture:** Keep the existing three-part AsciiDoc taxonomy and rewrite its 114 aligned source blocks in place. Add a nested named-campaign collection with 30 further aligned blocks, while keeping development plans and local official references under `.develope`.

**Tech Stack:** AsciiDoc, Markdown, PowerShell, Git, local DCS World reference files

## Global Constraints

- Modify the user-facing catalogs only in `PROMPT-SAMPLE-zh.adoc` and `PROMPT-SAMPLE.adoc`.
- Keep internal specifications, plans, and proprietary local references below `.develope`.
- Use AsciiDoc-native navigation: macro TOC, localized TOC title, five heading levels, section anchors and links, and admonition blocks.
- Preserve all 114 baseline Prompt categories and add exactly 30 named campaigns, producing exactly 144 source blocks per language.
- Expand the aggregate body text of the original 114 Chinese blocks from 13,188 characters to 16,485–17,804 characters.
- Expand the aggregate body text of the original 114 English blocks from 40,972 characters to 51,215–55,312 characters.
- Do not count the 30 named campaigns toward the baseline expansion targets.
- Keep Chinese and English heading paths, block order, scenario meaning, aircraft, terrain, era, roles, and campaign lengths aligned.
- Write idiomatic prose in both languages rather than literal sentence-by-sentence translation.
- Give simple missions a living environment without adding compulsory combat or punitive objectives.
- Ensure all owned aircraft and six owned terrains appear in the baseline 114 blocks; emphasize full-fidelity MiG-29A, M-2000C, and JF-17.
- Allow other aircraft and terrains where they produce a stronger classic scenario.
- Do not invent DCS internal type names, CLSIDs, coordinates, airbase identifiers, parking positions, payload compatibility, tasks, or capabilities.
- Use `.develope/official-campaigns/DCSWorld` only as a read-only development reference; do not copy its prose, images, or mission data into the catalog.
- Every multi-mission Prompt must recommend a top-tier long-running model such as Fable or GPT-5.6-Ultra, require end-to-end generation and validation, and request Image Gen artwork.
- The final local history after commit `4d8af75` must contain exactly two commits: one development-reference commit and one Prompt-catalog commit.

---

### Task 1: Record the baseline and inspect relevant references

**Files:**
- Read: `README-zh.md`
- Read: `README.md`
- Read: `PROMPT-SAMPLE-zh.adoc`
- Read: `PROMPT-SAMPLE.adoc`
- Read: `.develope/official-campaigns/README.txt`
- Read selectively: `.develope/official-campaigns/DCSWorld/Mods/aircraft/*/Missions/Campaigns`
- Read selectively: `.develope/official-campaigns/DCSWorld/Mods/campaigns/M2000C Red Flag`

**Interfaces:**
- Consumes: Existing bilingual catalogs, README voice, and legitimate local campaign references.
- Produces: Fixed numeric baselines and editorial observations used by Tasks 2–5.

- [ ] **Step 1: Confirm the source-block baseline**

Run a PowerShell regex over both catalogs matching `[source,text]` blocks.
Require 114 blocks, 13,188 Chinese body characters, and 40,972 English body
characters before editing.

- [ ] **Step 2: Inspect representative official campaigns**

Inspect the `.cmp` metadata, mission ordering, briefing assets, and a small
representative set of missions from JF-17, M-2000C, Su-25T, and M2000C Red
Flag. Record only general lessons about pacing, continuity, variety, and
briefing depth. Do not reproduce copyrighted text or assets.

- [ ] **Step 3: Inventory aircraft and terrain terminology**

Search current repository data and available Tools for the display names used
by the requested scenarios. If an exact internal identifier is not needed in a
Prompt, use the player-facing aircraft or terrain name and tell the future
generating Agent to verify the corresponding DCS data.

### Task 2: Reconstruct Quick Missions in both languages

**Files:**
- Modify: `PROMPT-SAMPLE-zh.adoc`, section `== 快速任务`
- Modify: `PROMPT-SAMPLE.adoc`, section `== Quick Missions`

**Interfaces:**
- Consumes: The existing ordered Quick Mission heading tree.
- Produces: Aligned living-world basic flight, tactical training, weapons, sensors, survival, and aerobatic Prompts.

- [ ] **Step 0: Strengthen the AsciiDoc document header**

Keep `:toc: macro` and `toc::[]`; add localized `:toc-title:`, retain
`:toclevels: 5`, and add `:sectanchors:` and `:sectlinks:`. Use an AsciiDoc
admonition near the introduction to explain that the generated TOC is the
primary route from simple exercises to long campaigns. Add stable anchors and
cross-references for `quick-missions`, `combat-scenarios`, `campaigns`, and
`named-campaigns`.

- [ ] **Step 1: Rebuild basic flight and procedure Prompts**

For every free-flight, startup, takeoff, navigation, landing, formation,
refueling, carrier, and helicopter leaf, write a specific player request with
start state, approximate duration, weather, route or practice area, optional
friendly activity, neutral traffic, recovery behavior, and requested output.
Free flight must remain free of compulsory objectives.

- [ ] **Step 2: Rebuild BFM, ACM, and BVR Prompts**

Specify geometry, weapons restrictions, skill level, repeat behavior, support,
boundaries, and a learning or survival criterion. Use the user's preferred
aircraft often and retain the full-fidelity M-2000C versus full-fidelity
MiG-29A guns-only example.

- [ ] **Step 3: Rebuild weapons, sensors, survival, and aerobatic Prompts**

Give each exercise a credible range or airspace, target set, safety or
collateral constraint, relevant supporting units, repeat opportunity, and
validation request without claiming unverified payload compatibility.

- [ ] **Step 4: Align the English section**

For each finalized Chinese Quick Mission, write an idiomatic English
counterpart with the same scenario facts and output expectations.

### Task 3: Reconstruct Combat Scenarios in both languages

**Files:**
- Modify: `PROMPT-SAMPLE-zh.adoc`, section `== 战斗场景`
- Modify: `PROMPT-SAMPLE.adoc`, section `== Combat Scenarios`

**Interfaces:**
- Consumes: The existing ordered Combat Scenario heading tree.
- Produces: Aligned complete standalone air, ground, maritime, helicopter, support, joint, and multiplayer operations.

- [ ] **Step 1: Rebuild air-superiority and strike Prompts**

Give each scenario an era, coalition context, player package, opposing package,
support plan, objective, escalation or complication, recovery, approximate
duration, and validation requirement.

- [ ] **Step 2: Rebuild SEAD, maritime, helicopter, and special-operation Prompts**

Use classic mission patterns suited to the featured aircraft. Include coherent
orders of battle, timing, rules of engagement, survivable support, and mission
progression without allowing AI support to solve the player's task.

- [ ] **Step 3: Rebuild reconnaissance, support, ground, joint, and multiplayer Prompts**

Define player responsibilities, information flow, coordination, persistence
within the standalone mission, victory logic, and safeguards against civilian
or friendly losses where relevant.

- [ ] **Step 4: Align the English section**

Write natural English counterparts preserving every operational fact and
constraint from the finalized Chinese Combat Scenarios.

### Task 4: Reconstruct the 15 generic Campaign Prompts

**Files:**
- Modify: `PROMPT-SAMPLE-zh.adoc`, existing generic leaves below `== 战役`
- Modify: `PROMPT-SAMPLE.adoc`, existing generic leaves below `== Campaigns`

**Interfaces:**
- Consumes: The existing training, short, narrative, branching, persistent, and dynamic campaign categories.
- Produces: Fifteen detailed multi-mission requests that remain reusable campaign-pattern examples.

- [ ] **Step 1: Add scale and continuity to every generic campaign**

State a mission count or range, typical mission duration, estimated total
playtime, player aircraft and terrain, structure, recurring units or
characters, progression rules, and required deliverables.

- [ ] **Step 2: Add the long-running execution contract**

State the shared contract in a Campaigns-section AsciiDoc `IMPORTANT` block,
then reiterate it compactly inside every copyable Prompt. Require Fable,
GPT-5.6-Ultra, or another top-tier long-running model to inspect `Docs` and
`Tools`, create a campaign bible, generate and validate every mission, check
cross-mission continuity, and finish with a manifest and honest limitations
report rather than stopping at an outline. Avoid repeating a long boilerplate
paragraph in all 15 existing pattern examples.

- [ ] **Step 3: Add the Image Gen contract**

Require campaign cover art, an insignia or patch, selected chapter or mission
art, and appropriate ending art. State that generated art is atmospheric and
cannot replace verified coordinates, navigation charts, or tactical data.

- [ ] **Step 4: Align the English section**

Write equivalent natural English requests with matching lengths, structure,
aircraft, terrains, artifacts, and model requirements.

### Task 5: Add the 30 named Campaign Prompts

**Files:**
- Modify: `PROMPT-SAMPLE-zh.adoc`, append below the generic campaign patterns
- Modify: `PROMPT-SAMPLE.adoc`, append in the corresponding location

**Interfaces:**
- Consumes: The 30-campaign roster in the design specification.
- Produces: Exactly 25 fixed-wing or joint campaigns and five independent helicopter campaigns.

- [ ] **Step 1: Add the three-level named-campaign hierarchy**

Add one collection heading, then three groups: reconceived user concepts,
additional fixed-wing and joint campaigns, and independent helicopter
campaigns. Add 11, 14, and 5 leaf Prompts respectively.

- [ ] **Step 2: Write each campaign as a complete long-running request**

Each Prompt must state required player modules and terrain, era and conflict,
mission count, typical mission duration, total playtime, campaign structure,
mission progression, friendly and hostile forces, continuity, output
directory, validation, long-running model recommendation, and Image Gen
artifacts.

- [ ] **Step 3: Reconsider scenario names and plausibility**

Retain distinctive names such as `德国人的米格` and the paired
`薛定谔的冷热战` campaigns. Improve generic names, terrain choices, and force
relationships where needed. Mark alternate-history or representative-terrain
premises honestly rather than presenting them as historical fact.

- [ ] **Step 4: Align all 30 English campaigns**

Use evocative natural English titles and preserve the exact scenario,
structure, length, and deliverable requirements of each Chinese counterpart.

### Task 6: Validate the complete catalogs

**Files:**
- Verify: `PROMPT-SAMPLE-zh.adoc`
- Verify: `PROMPT-SAMPLE.adoc`

**Interfaces:**
- Consumes: All reconstructed Prompt content.
- Produces: Structural, quantitative, coverage, rendering, and editorial evidence.

- [ ] **Step 1: Validate AsciiDoc structure**

Require exactly 144 `[source,text]` blocks per file, identical ordered heading
levels, balanced block delimiters, no empty blocks, and 30 additional named
campaign leaf headings. Require `:toc: macro`, localized `:toc-title:`,
`:toclevels: 5`, `:sectanchors:`, `:sectlinks:`, `toc::[]`, and at least one
admonition block in each language.

- [ ] **Step 2: Validate baseline expansion**

Measure only the first 114 source-block bodies. Require 16,485–17,804 Chinese
characters and 51,215–55,312 English characters.

- [ ] **Step 3: Validate content coverage**

Search the first 114 blocks for every owned aircraft and owned terrain. Count
full-fidelity MiG-29A, M-2000C, and JF-17 mentions and confirm each is used in
multiple meaningful roles.

- [ ] **Step 4: Validate campaign contracts**

Check all 45 multi-mission blocks for a mission count or range, duration,
long-running model recommendation, end-to-end generation language,
validation, and Image Gen. Check the 30 named campaigns against the roster.

- [ ] **Step 5: Render both documents**

Use an available local AsciiDoc renderer without adding repository
dependencies. Require exit code 0 and generated HTML for both documents in a
temporary directory outside the workspace. If no renderer is available,
report that exact limitation and retain the structural checks.

- [ ] **Step 6: Perform bilingual editorial review**

Spot-check every top-level section and all campaign titles for semantic
alignment, natural language, inconsistent aircraft or terrain, accidental
historical claims, repetitive filler, and invented DCS identifiers.

### Task 7: Produce exactly two final commits

**Files:**
- Commit 1: `.develope/**`, `.gitignore`, and removal of `Docs/superpowers/**`
- Commit 2: `PROMPT-SAMPLE-zh.adoc`, `PROMPT-SAMPLE.adoc`

**Interfaces:**
- Consumes: The verified development references, implementation plan, and reconstructed catalogs.
- Produces: A clean two-commit history after `4d8af75`.

- [ ] **Step 1: Preserve all work while removing transition commits**

After verification, use a non-destructive soft reset to `4d8af75`, leaving all
changes in the working tree. Confirm the copied official campaign payload
remains ignored.

- [ ] **Step 2: Create the development-reference commit**

Stage only `.develope`, `.gitignore`, and the tracked removals below
`Docs/superpowers`. Commit with:

```text
chore: organize development references
```

- [ ] **Step 3: Create the Prompt-catalog commit**

Stage only `PROMPT-SAMPLE-zh.adoc` and `PROMPT-SAMPLE.adoc`. Commit with:

```text
docs: reconstruct bilingual prompt catalog
```

- [ ] **Step 4: Verify final history and worktree**

Require exactly two commits in `4d8af75..HEAD`, require the first commit not to
touch either Prompt catalog, require the second commit to touch only the two
Prompt catalogs, and require a clean worktree.
