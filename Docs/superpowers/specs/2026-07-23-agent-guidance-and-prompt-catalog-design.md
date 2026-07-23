# Agent Guidance and Prompt Catalog Design

## Goal

Initialize the model-facing project instructions, reorganize local upstream
source checkouts, and turn the bilingual AsciiDoc Prompt examples into a broad
catalog of realistic DCS simulation requests.

This work documents and demonstrates the project described by the current
README files. It does not introduce the speculative architecture from earlier
generated documentation.

## `AGENTS.md`

`AGENTS.md` is a concise English instruction file for Coding Agents working in
the repository. It explains:

- DCSMizzer is an Agent-oriented DCS simulation and combat generator.
- Users describe the desired simulation in natural language.
- The Agent must understand the request before consulting examples.
- The Agent reads the matching README and Prompt examples, then uses available
  material in `Docs` and `Tools`.
- Prompt examples are inspiration, not fixed templates or hidden
  requirements.
- DCS internal identifiers, coordinates, payloads, capabilities, and mission
  fields must be queried or verified rather than invented from memory.
- `.develope/upstream` is development reference material, not DCSMizzer source
  and not content to redistribute.
- The Agent must not claim that missing project capabilities exist.
- Generated results should be checked with every relevant validation facility
  currently available in the project.

## `.develope`

The `.develope` directory is a general area for development-only documents and
resources. It is not ignored as a whole.

Complete third-party Git clones live under:

```text
.develope/upstream/
```

The six existing clones are moved there without removing their internal Git
history:

1. pydcs
2. BriefingRoom for DCS
3. dcs-mission-maker
4. DCS Global Terrain Database
5. DCS Retribution
6. MOOSE

`.develope/upstream/README.txt` is an English explanation of the directory.
The parent `.develope` directory has no README.

The parent repository ignores every item below `.develope/upstream/` except
`README.txt`. Other future `.develope` documents remain trackable.

## Prompt Document Format

The project keeps two parallel documents:

- `PROMPT-SAMPLE-zh.adoc`
- `PROMPT-SAMPLE.adoc`

Each document:

- links back to its matching README near the top;
- uses an AsciiDoc-generated table of contents with enough depth for the full
  classification tree;
- has exactly three first-level catalog sections: Quick Missions, Combat
  Scenarios, and Campaigns;
- contains one complete Prompt in every leaf category;
- places Prompts in plain-text source blocks;
- uses natural prose that resembles a real request to a Coding Agent;
- varies aircraft, maps, eras, weather, start state, player count, difficulty,
  and duration where appropriate;
- asks the Agent to use real project data and validation where a scenario
  depends on exact DCS identifiers;
- keeps the Chinese and English classification structures aligned while using
  natural writing in each language rather than mechanical sentence-by-sentence
  translation.

## Classification

### Quick Missions

Quick Missions focus on one flight skill, weapon, system, or tactical problem
with little narrative overhead.

The catalog covers:

- free flight by day, night, sightseeing route, and adverse weather;
- cold start, hot start, runway takeoff, visual landing, instrument landing,
  night or crosswind landing, formation flight, air-to-air refueling, carrier
  operations, and basic helicopter handling;
- close combat with guns, infrared missiles, and a fully armed surprise
  encounter, including 1v1, 2v2, and outnumbered configurations where useful;
- BVR in 1v1, 2v2, outnumbered, and coordinated AWACS/datalink configurations;
- air-to-ground practice with cannon, rockets, unguided bombs, cluster
  munitions, laser-guided weapons, electro-optical weapons, GPS/INS weapons,
  anti-radiation missiles, and anti-ship missiles;
- radar and datalink, targeting sensors, defensive systems, low-level
  penetration, emergency recovery, and aerobatics.

The guns-only 1v1 example uses full-fidelity M-2000C and MiG-29A aircraft.

### Combat Scenarios

Combat Scenarios are complete standalone military operations with objectives,
opposing forces, support elements, and mission progression.

The catalog covers:

- scramble and package interception, BARCAP, TARCAP, fighter sweep, escort,
  airbase defense, fleet defense, and offensive counter-air;
- planned and on-call CAS, BAI, armed reconnaissance, precision and deep
  strike, runway attack, armor attack, and infrastructure attack;
- SEAD, DEAD, SEAD escort, and SEAD sweep;
- anti-ship strike, coastal strike, convoy escort, and fleet defense;
- air assault, troop insertion and extraction, cargo transport, resupply,
  combat search and rescue, and helicopter escort;
- tactical reconnaissance, AFAC/JTAC, airborne early warning, refueling, and
  recovery support;
- defensive, capture, ground offensive, convoy, combined-arms, and large
  multi-package operations;
- cooperative, adversarial, human-JTAC, and Combined Arms multiplayer
  scenarios.

### Campaigns

Campaigns contain linked missions and emphasize progression, narrative,
branching, or persistent state.

The catalog covers:

- training and combat qualification campaigns;
- linear mini-campaigns and historical short campaigns;
- fictional, historical, and character-driven narrative campaigns;
- success/failure branching and multiple endings;
- persistent losses, resources, and front-line progression;
- dynamically generated missions, dynamic theaters, and cooperative dynamic
  campaigns.

## Validation

The completed change is verified by checking:

- `AGENTS.md` contains the approved purpose, workflow, data rules, and
  development-reference boundary;
- all six upstream repositories have the same valid `HEAD` and `origin` after
  moving;
- only `.develope/upstream/README.txt` is tracked beneath `upstream`;
- another development file below `.develope` would not be ignored;
- both Prompt documents parse as AsciiDoc;
- both have matching heading paths and one plain-text block per leaf;
- both link back to the correct README;
- the required top-level sections and representative DCS mission types are
  present;
- no Prompt is an empty placeholder or structured configuration form.

