# Agent Guidance and Prompt Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize `AGENTS.md`, reorganize ignored upstream source checkouts, and build aligned Chinese and English AsciiDoc catalogs of realistic DCS Prompt examples.

**Architecture:** `AGENTS.md` is the concise model-facing entry point. `.develope` remains a trackable development area while `.develope/upstream` isolates complete ignored third-party clones. The two Prompt documents share an identical heading tree and contain natural-language Prompt blocks at every leaf.

**Tech Stack:** Markdown, AsciiDoc, Git ignore patterns, PowerShell, Git

## Global Constraints

- Do not adopt architecture or requirements from the rejected generated README.
- Preserve all six upstream clones, including their internal `.git` directories and histories.
- Track `.develope/upstream/README.txt`; ignore every other item below `.develope/upstream`.
- Do not ignore other content below `.develope`.
- Use English for `AGENTS.md` and `.develope/upstream/README.txt`.
- Keep the Chinese and English Prompt heading paths aligned.
- Use natural plain-text requests, not forms, JSON, YAML, or parameter tables.
- Put one complete Prompt in every leaf category.
- Include a link back to the matching README in each Prompt document.
- Do not push changes unless the user separately requests a push.

---

### Task 1: Reorganize upstream development references

**Files:**
- Modify: `.gitignore`
- Delete: `.develope/README.txt`
- Create: `.develope/upstream/README.txt`
- Move ignored directories: `.develope/{pydcs,briefing-room-for-dcs,dcs-mission-maker,dcs-global-terrain-database,dcs-retribution,MOOSE}` to `.develope/upstream/`

**Interfaces:**
- Consumes: Six intact local Git clones and the existing broad `.develope/*` ignore rule.
- Produces: A trackable general development area with one isolated upstream-source directory.

- [ ] **Step 1: Record repository identity before moving**

Run `git -C <clone> rev-parse HEAD` and `git -C <clone> remote get-url origin`
for all six existing clone directories. Keep the command output for comparison.

- [ ] **Step 2: Replace the upstream explanation**

Delete `.develope/README.txt` and create `.develope/upstream/README.txt` in
English with this meaning:

```text
This directory contains complete local Git clones of the upstream projects
acknowledged by DCSMizzer. They are development references, retain their own
Git history, and are intentionally ignored by the parent repository. Other
development documents may live elsewhere under .develope and remain
trackable.
```

- [ ] **Step 3: Narrow the ignore rule**

Replace:

```gitignore
.develope/*
!.develope/README.txt
```

with:

```gitignore
.develope/upstream/*
!.develope/upstream/README.txt
```

- [ ] **Step 4: Move the six clones**

Create `.develope/upstream` through the tracked README and move each explicitly
named clone directory with PowerShell `Move-Item -LiteralPath`.

- [ ] **Step 5: Verify identities and ignore behavior**

Re-run the `HEAD` and `origin` checks at the new paths. Use `git check-ignore`
to prove a cloned source file is ignored and the upstream README is not.
Create a temporary untracked test path elsewhere below `.develope` and prove it
is not ignored, then remove only that exact test path.

- [ ] **Step 6: Commit the directory change**

```powershell
git add -- .gitignore .develope/README.txt .develope/upstream/README.txt
git commit -m "chore: organize upstream development references"
```

### Task 2: Initialize model-facing repository instructions

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: The approved project description and repository layout.
- Produces: The first file a Coding Agent can use to understand its role and workflow.

- [ ] **Step 1: Write `AGENTS.md`**

Cover these exact instruction groups:

1. Purpose: DCSMizzer is an Agent-oriented DCS simulation and combat generator.
2. User interaction: understand the natural-language request before consulting examples.
3. Repository workflow: read the matching README and Prompt catalog, then use available `Docs` and `Tools`.
4. Data discipline: query or verify internal names, coordinates, loadouts, capabilities, and mission fields.
5. Scope discipline: examples are inspiration, missing capabilities must not be invented, and user requirements win.
6. Development references: `.develope/upstream` is read-only reference material, not project source.
7. Completion: use every relevant validation facility actually present in the repository.

- [ ] **Step 2: Check instruction content**

Run `rg` for `natural language`, `Docs`, `Tools`, `.develope/upstream`,
`verify`, `invent`, and `Prompt examples`. Every concept must occur.

- [ ] **Step 3: Commit `AGENTS.md`**

```powershell
git add -- AGENTS.md
git commit -m "docs: add agent workflow guidance"
```

### Task 3: Build the Chinese Prompt catalog

**Files:**
- Modify: `PROMPT-SAMPLE-zh.adoc`

**Interfaces:**
- Consumes: The approved classification in the design specification.
- Produces: A Chinese AsciiDoc catalog with one natural Prompt per leaf.

- [ ] **Step 1: Add document navigation and TOC**

Use a level-zero AsciiDoc title, `:toc:`, `:toclevels: 5`, and a link back to
`README-zh.md`.

- [ ] **Step 2: Add Quick Mission Prompt leaves**

Create plain-text Prompt blocks for:

- day, night, sightseeing, and adverse-weather free flight;
- cold start, hot start, runway departure, visual landing, instrument landing,
  night/crosswind landing, formation, air refueling, carrier operations,
  hovering, nap-of-earth flight, and confined-area helicopter landing;
- guns 1v1, 2v2, and 1v2; infrared-missile 1v1, 2v2, and 1v2; a fully armed
  surprise encounter;
- BVR 1v1, 2v2, 1v2, 4v4 with AWACS/datalink, and defensive disengagement;
- cannon, rockets, CCIP bombs, CCRP bombs, cluster munitions, laser-guided
  weapons, electro-optical weapons, GPS/INS weapons, standoff weapons,
  anti-radiation missiles, and anti-ship missiles;
- radar/datalink, targeting/JTAC, RWR/ECM/countermeasures, low-level
  penetration, emergency recovery, solo aerobatics, and formation aerobatics.

The guns-only 1v1 Prompt uses full-fidelity M-2000C against full-fidelity
MiG-29A.

- [ ] **Step 3: Add Combat Scenario Prompt leaves**

Create plain-text Prompt blocks for:

- scramble interception, package interception, BARCAP, TARCAP, fighter sweep,
  escort, airbase defense, fleet defense, and OCA against aircraft;
- planned CAS, on-call CAS, BAI, armed reconnaissance, pinpoint strike, deep
  strike, runway attack, armor attack, and infrastructure attack;
- SEAD, DEAD, SEAD escort, and SEAD sweep;
- anti-ship strike, coastal strike, maritime convoy escort, fleet defense, and
  amphibious support;
- air assault, troop insertion, troop extraction, cargo transport, resupply,
  CSAR, helicopter escort, and helicopter hunt;
- tactical reconnaissance, AFAC/JTAC, AEW&C support, tanker support, recovery
  tanker, battlefield surveillance, and show of force;
- positional defense, capture, ground offensive, convoy escort, convoy
  interdiction, joint fire support, and a large multi-package operation;
- cooperative, adversarial PvP, human-JTAC, and Combined Arms multiplayer.

- [ ] **Step 4: Add Campaign Prompt leaves**

Create plain-text Prompt blocks for:

- basic flight and combat qualification;
- linear mini-campaign and historical short campaign;
- fictional linear, historical linear, and character-driven narrative;
- success/failure branching and multiple endings;
- persistent losses/resources, front-line progression, and a long progressive
  campaign;
- dynamic mission generation, dynamic theater, and cooperative dynamic
  campaign.

- [ ] **Step 5: Verify Chinese structure**

Count heading paths and `[source,text]` blocks. Confirm the three top-level
catalog sections, the README link, the M-2000C versus MiG-29A Prompt, and the
absence of `TODO`, `TBD`, JSON, YAML, or form-like placeholder text.

- [ ] **Step 6: Commit the Chinese catalog**

```powershell
git add -- PROMPT-SAMPLE-zh.adoc
git commit -m "docs: add Chinese DCS prompt catalog"
```

### Task 4: Build the English Prompt catalog

**Files:**
- Modify: `PROMPT-SAMPLE.adoc`

**Interfaces:**
- Consumes: The finalized Chinese heading paths and approved content rules.
- Produces: A natural English Prompt catalog with exactly the same classification tree.

- [ ] **Step 1: Mirror the complete heading tree**

Translate every Chinese heading naturally while preserving its path and order.
Add the link back to `README.md`, `:toc:`, and `:toclevels: 5`.

- [ ] **Step 2: Write natural English Prompts**

Write one complete Prompt for every leaf listed in Tasks 3.2 through 3.4. Keep
the same scenario intent as the Chinese counterpart, but use idiomatic English
requests instead of literal line-by-line translation.

- [ ] **Step 3: Verify bilingual alignment**

Extract ordered heading levels and plain-text block counts from both documents.
Require equal heading counts, equal leaf counts, equal source-block counts, and
matching hierarchy depth.

- [ ] **Step 4: Parse both AsciiDoc files**

Use `npx --yes @asciidoctor/cli` to render both documents into a temporary
directory outside the workspace. Require exit code 0 and generated HTML for
both. Do not add Node packages to the repository.

- [ ] **Step 5: Commit the English catalog**

```powershell
git add -- PROMPT-SAMPLE.adoc
git commit -m "docs: add English DCS prompt catalog"
```

### Task 5: Final repository verification

**Files:**
- Verify: `AGENTS.md`
- Verify: `.gitignore`
- Verify: `.develope/upstream/README.txt`
- Verify: `PROMPT-SAMPLE-zh.adoc`
- Verify: `PROMPT-SAMPLE.adoc`

**Interfaces:**
- Consumes: All implemented tasks.
- Produces: Evidence that the approved design is complete and no upstream clone entered Git.

- [ ] **Step 1: Verify Git scope**

Run `git status -sb`, `git ls-files .develope`, and `git check-ignore` for all
six clone directories. Require only `.develope/upstream/README.txt` beneath
`upstream` to be tracked.

- [ ] **Step 2: Verify upstream repositories**

For each clone, require a valid `HEAD`, the original `origin`, and a clean
working tree.

- [ ] **Step 3: Verify documentation requirements**

Check every exact requirement in the design specification against the three
documents. Render both AsciiDoc files again and count Prompt blocks and leaf
headings.

- [ ] **Step 4: Verify repository state**

Require `git status -sb` to show a clean local branch. Do not push.
