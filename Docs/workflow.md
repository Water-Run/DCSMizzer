# Model workflow

## 1. Capture the request

Preserve every supplied constraint. Use this internal record; omit fields the
user did not specify rather than inventing defaults.

```text
scenario_kind
era/date
map
coalitions/countries
player aircraft and exact variant
player count and slot mode
AI package composition
weapons/loadouts
start state
origin/recovery/divert
weather/time/visibility
duration and pacing
objectives
success/failure conditions
realism and scripting constraints
output path and companion artifacts
```

Mark each value as `user-specified`, `verified`, `inferred`, or `unresolved`.

## 2. Check capability before designing

Run:

```powershell
python Tools\dcsmizzer.py capabilities
```

If the required operation is not implemented, stop before fabricating an
artifact. You may still return a preserved scenario specification and an
evidence-gap report.

## 3. Resolve evidence

Follow [evidence.md](evidence.md). Exact IDs and compatibility need evidence
closest to the current local DCS version. Record the source and version beside
each resolved value.

Never silently substitute. If a verified limitation would change aircraft,
map, weapon, mission type, start state, or player experience, ask the user.

## 4. Plan the scenario

Only after facts resolve, design:

1. spatial layout and verified operating locations;
2. coalition order of battle;
3. player and AI routes/tasks;
4. spawn/activation timeline;
5. triggers, scripts, goals, and failure/success paths;
6. briefing and recovery/divert logic;
7. performance budget;
8. validation plan.

Keep a deterministic seed if a future generator supports one.

## 5. Build

Current state: no product builder exists. Do not create a `.miz` by hand and
call it generated. Do not copy or edit official, user, or upstream missions as
a substitute.

## 6. Validate

Use [validation.md](validation.md). A file may be archive-valid and
parse-valid while runtime validity remains unknown.
