# Repository Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate the project README, establish repository ignore rules, and create an ignored local library of the six acknowledged upstream projects.

**Architecture:** The bilingual README files remain parallel user-facing entry points. `.develope/README.txt` documents the local reference area, while `.gitignore` excludes every other path below `.develope/` so intact upstream clones do not enter the parent repository.

**Tech Stack:** Markdown, Git ignore patterns, Git

## Global Constraints

- Do not initialize a Git repository.
- Do not ignore `.develope/README.txt`.
- Ignore all other content below `.develope/`.
- Keep each upstream clone's `.git` directory intact.
- Do not introduce DCSMizzer architecture that is absent from `README-zh.md`.

---

### Task 1: Align the bilingual README files

**Files:**
- Modify: `README-zh.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: The Chinese README and the user's prompt corrections.
- Produces: Parallel Chinese and English project introductions.

- [ ] **Step 1: Update the Chinese example prompt**

Change the mission time from evening to afternoon, change the MiG-29A flight
from runway-ready to cold start, and reduce the equipment constraint to the
late-1980s Cold War setting without naming R-77 or MICA.

- [ ] **Step 2: Translate the complete Chinese README**

Write a faithful English version in `README.md`, preserving links, hierarchy,
example-prompt details, and the final quotation.

- [ ] **Step 3: Compare document structure**

Run:

```powershell
rg '^(#|\* |\s+\* |\[.*\]\(|```|>)' README-zh.md README.md
```

Expected: both documents contain corresponding headings, lists, links, code
fences, and the closing quotation.

### Task 2: Initialize ignore rules and the local reference area

**Files:**
- Modify: `.gitignore`
- Create: `.develope/README.txt`

**Interfaces:**
- Consumes: Common Python/Lua development artifacts and the approved local
  reference layout.
- Produces: Parent-repository ignore behavior that keeps only the explanatory
  text file visible.

- [ ] **Step 1: Add project ignore rules**

Add common Python, Lua, IDE, OS, temporary, secret, build, coverage, log, and
generated-output patterns. Add:

```gitignore
.develope/*
!.develope/README.txt
```

- [ ] **Step 2: Explain the local reference directory**

Create `.develope/README.txt` stating that each child directory contains a
complete clone of an acknowledged upstream project for local development
reference, and that those clones are intentionally ignored by the parent
repository.

- [ ] **Step 3: Verify ignore behavior in a temporary Git index**

Use a temporary Git repository outside the workspace to copy and test the two
paths with `git check-ignore`, without initializing `DcsMizzer` itself.

Expected: `.develope/README.txt` is not ignored; a test file below a child
directory is ignored.

### Task 3: Populate the reference-source directory

**Files:**
- Create ignored directories below: `.develope/`

**Interfaces:**
- Consumes: The six acknowledgement URLs in `README-zh.md`.
- Produces: Six intact local Git clones for agent inspection.

- [ ] **Step 1: Clone each acknowledged repository**

Run non-interactive full clones for:

```text
https://github.com/pydcs/dcs
https://github.com/DCS-BR-Tools/briefing-room-for-dcs
https://github.com/JonathanTurnock/dcs-mission-maker
https://github.com/flying-dice/dcs-global-terrain-database
https://github.com/dcs-retribution/dcs-retribution
https://github.com/FlightControl-Master/MOOSE
```

- [ ] **Step 2: Validate every clone**

For each child directory, run:

```powershell
git -C <directory> rev-parse --verify HEAD
git -C <directory> remote get-url origin
```

Expected: every repository has a valid commit and its origin matches the
corresponding acknowledgement URL.

- [ ] **Step 3: Verify parent ignore coverage**

Use the same temporary Git-index method from Task 2.

Expected: every cloned child directory is ignored, while
`.develope/README.txt` remains visible.

