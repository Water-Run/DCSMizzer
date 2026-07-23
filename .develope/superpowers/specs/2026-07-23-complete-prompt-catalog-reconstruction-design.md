# Complete Prompt Catalog Reconstruction Design

## Goal

Completely reconstruct the English and Chinese Prompt catalogs so they lead a
user from the simplest DCS familiarization flight to demanding standalone
operations and long, illustrated campaigns.

The reconstruction must preserve the catalogs' role as examples of natural
requests to a Coding Agent. It must not turn them into rigid forms, claim that
unimplemented DCSMizzer capabilities exist, or invent DCS data.

## Scope

The two parallel documents are:

- `PROMPT-SAMPLE-zh.adoc`
- `PROMPT-SAMPLE.adoc`

The existing 114 Prompt examples remain the baseline catalog. Their Prompt
bodies are rewritten and expanded by approximately 30 percent in aggregate,
measured independently of the newly added campaign material. The target range
is 25–35 percent so natural prose takes priority over padding.

Thirty fully conceived named campaign Prompts are added after the current
generic campaign examples. The additional collection contains 25 fixed-wing
or joint campaigns and five helicopter campaigns. It does not replace the
existing training, linear, branching, persistent, or dynamic campaign
examples.

Chinese and English retain matching heading paths and source-block counts.
The English version is idiomatic English, not a literal translation.

## AsciiDoc Navigation and Semantics

Use AsciiDoc as a document format rather than treating it as Markdown with a
different extension. Each catalog must provide:

- a macro-positioned table of contents with `:toc: macro`;
- a localized `:toc-title:` and `:toclevels: 5`, so every leaf category and
  named campaign is directly reachable;
- `:sectanchors:` and `:sectlinks:` for linkable, navigable headings;
- stable explicit anchors and cross-references for Quick Missions, Combat
  Scenarios, Campaigns, and the named campaign collection;
- AsciiDoc admonition blocks for catalog guidance and the special requirements
  of long-running campaign generation;
- proper nested section levels for the three catalog scales and named campaign
  groups;
- `[source,text]` blocks for copyable Prompts.

Do not replace this hierarchy with a manually maintained Markdown-style list.
The rendered table of contents is the authoritative navigation structure.

## Editorial Direction

### Complete reconstruction

Every Prompt is reconsidered as a scenario rather than mechanically extended.
The catalog still progresses from simple to complex:

1. familiarization, procedures, navigation, and handling;
2. air combat and weapon training;
3. sensors, survival, and specialized skills;
4. complete standalone combat operations;
5. multiplayer and joint operations;
6. linked, branching, persistent, and dynamic campaigns.

Individual Prompts gain useful detail such as setting, friendly and neutral
traffic, player role, start state, weather, opposition, support, restrictions,
duration, scoring, failure conditions, or expected deliverables. Not every
Prompt must contain every category of detail.

### Living environments

Even simple flights should feel inhabited. Free-flight examples may contain:

- an AI wingman or friendly formation to join or observe;
- neutral civilian or military traffic;
- airport departures, arrivals, and radio activity;
- training ranges, ships, patrols, or other non-hostile activity;
- optional navigation or formation suggestions.

Free flight remains genuinely free: no compulsory combat, forced objective, or
punitive failure condition is added merely to create activity.

Training scenarios receive proportionate background activity without
obscuring the skill being trained. Complex combat operations receive coherent
friendly, hostile, and neutral orders of battle rather than disconnected unit
lists.

### Voice and detail

The prose follows the README style: direct, specific, enthusiastic, and
slightly personal. Each source block should read like a Prompt a DCS player
would actually submit.

Repeated validation boilerplate is varied or integrated into the scenario.
Extra length must add operational value rather than restating the same warning.

## Aircraft and Terrain Coverage

The user's owned aircraft are:

- full-fidelity MiG-29A Fulcrum;
- MiG-29S;
- MiG-29G;
- F-5E FC;
- Su-27;
- J-11A;
- F-16C;
- F-15C;
- Su-25T;
- MiG-21Bis;
- M-2000C;
- JF-17.

Full-fidelity MiG-29A, M-2000C, and JF-17 receive the greatest emphasis.
Every owned aircraft appears at least once in the reconstructed pre-campaign
examples, with several receiving both training and combat roles.

The user's owned terrains are Caucasus, Nevada, Mariana Islands, Cold War
Germany, Kola, and Sinai. Every one appears in the pre-campaign catalog, but
the catalog is not limited to them. Other terrains may be used whenever they
better fit a historical setting, aircraft, or mission, including Persian Gulf,
Syria, Afghanistan, Normandy, The Channel, and South Atlantic.

Non-owned aircraft remain welcome when they are the natural choice for a
classic scenario. Examples include F-14 and F/A-18 carrier operations, F-4 and
AJS-37 strike missions, C-130 transport, warbirds, and helicopters.

## Local Official Campaign References

When present, the ignored files below `.develope/official-campaigns/DCSWorld`
are read-only development references copied from the user's legitimate DCS
World installation. Inspect relevant JF-17, M-2000C, Su-25T, and M2000C Red
Flag campaigns while reconstructing the catalog.

Use them to understand established mission pacing, briefing depth, campaign
progression, variety, atmosphere, and `.cmp`/`.miz` organization. Do not copy
their prose, artwork, mission content, or other copyrighted assets into
DCSMizzer. Do not modify the local DCS installation or commit the ignored
copies. Exact DCS data must still be checked through current project data and
Tools rather than inferred solely from an official campaign.

## Quick Missions and Standalone Operations

The existing taxonomy remains recognizable, but all Prompt bodies are rebuilt.
The sequence deliberately moves from low workload to high workload.

### Basic flight

Free flight, startup, takeoff, navigation, landing, formation, refueling,
carrier, helicopter, and aerobatic examples specify an atmospheric but
non-intrusive world. They state what is optional, what is being practiced, and
how the player can recover or repeat the exercise.

### Tactical training

BFM, ACM, BVR, weapon, sensor, and survival exercises define:

- starting geometry and tactical problem;
- allowed or prohibited weapons;
- relevant support and neutral traffic;
- repeat or reset behavior where useful;
- clear success, survival, or learning criteria.

### Combat scenarios

Standalone combat operations provide a compact operational story, credible
package composition, objective, restrictions, escalation, and recovery plan.
Classic scenarios are favored: alert intercepts, fighter sweeps, escorts,
low-level strikes, close air support, SEAD/DEAD, anti-ship attacks, fleet
defense, air assault, combat rescue, reconnaissance, logistics, and joint
operations.

## Additional Named Campaign Collection

Each campaign Prompt specifies its required modules and terrains, approximate
mission count, typical mission duration, estimated total playtime, campaign
structure, recurring forces, continuity rules, generated artifacts, and
validation expectations.

### Reconceived user concepts

1. **德国人的米格 / The Germans' MiG** — MiG-29G; Cold War Germany and
   Nevada; post-reunification evaluation and exchange testing; 8 missions,
   8–10 hours.
2. **红星裂痕 / Fractured Red Stars** — Chinese MiG-21Bis in a fictional
   1970s Sino-Soviet conflict with MiG-19 and MiG-15 allies; 7 missions,
   6–8 hours.
3. **同源之敌 / Enemy of the Same Bloodline** — Ukrainian MiG-29S in a
   modern conflict represented on Caucasus; 10 missions, 10–13 hours.
4. **海峡尽头 / At the End of the Strait** — ROCAF-liveried F-5E FC
   defending the Mariana Islands against a much larger Chinese force;
   9 missions, 8–11 hours.
5. **海上来客 / Visitors from the Sea** — Chinese naval Su-27 and J-11A
   operations against a United States carrier force in the Marianas;
   8 missions, 8–10 hours.
6. **薛定谔的冷热战：红色 / Schrödinger's Hot-and-Cold War: Red** —
   full-fidelity Soviet MiG-29A on Cold War Germany, balancing front-line
   clashes against uncontrolled escalation; 10 missions, 10–13 hours.
7. **薛定谔的冷热战：蓝色 / Schrödinger's Hot-and-Cold War: Blue** —
   French M-2000C campaign sharing major events with the Red campaign from
   the opposing perspective; 10 missions, 10–13 hours.
8. **西奈无缓冲区 / No Buffer in Sinai** — Egyptian MiG-29A resisting a
   2010s Israeli invasion force containing F-15C, F-15E, F-16C, F-4E, and
   appropriate support; 10 missions, 10–13 hours.
9. **极北对峙 / Confrontation in the High North** — American F-16C and
   F-15C operations around Kola against a broad, data-verified Russian force;
   12 missions, 14–18 hours.
10. **旧怨长空 / Old Grudges in the Sky** — Pakistani JF-17 campaign
    against India and supporting outside powers; 10 missions, 10–14 hours.
11. **冻土手术刀 / Scalpel over Frozen Ground** — Russian Su-25T precision
    strike campaign on Kola; 8 missions, 8–10 hours.

### Additional fixed-wing and joint campaigns

12. **冰海雄猫 / Tomcats over the Ice Sea** — F-14B fleet defense and
    long-range interception on Kola; 10 missions, 11–14 hours.
13. **群岛之矛 / Spear of the Islands** — F/A-18C carrier campaign in the
    Marianas; 12 missions, 13–17 hours.
14. **富尔达幽灵 / Phantom over Fulda** — F-4E low-level interdiction,
    escort, and air-defense hunting on Cold War Germany; 10 missions,
    10–13 hours.
15. **峡湾雷霆 / Thunder in the Fjords** — AJS-37 low-level anti-ship
    campaign on Kola; 8 missions, 7–10 hours.
16. **山口守望者 / Guardians of the Pass** — A-10C II and A-10A continuous
    close-air-support campaign on Caucasus; 10 missions, 11–15 hours.
17. **尼罗河夜航 / Night Flights over the Nile** — F-15E deep night strike
    campaign on Sinai; 10 missions, 12–15 hours.
18. **滩头上空 / Above the Beachhead** — AV-8B expeditionary and amphibious
    campaign on South Atlantic; 8 missions, 8–11 hours.
19. **最后的幻影 / The Last Mirage** — Mirage F1 campaign on Sinai about an
    older air force facing modern opposition; 9 missions, 9–12 hours.
20. **银色军刀 / Silver Sabres** — F-86F and MiG-15bis in a fictional
    1950s mountain air war on Caucasus; 7 missions, 6–8 hours.
21. **铁路上的月光 / Moonlight on the Railways** — Mosquito, P-47D, and
    P-51D interdiction on Normandy; 8 missions, 8–10 hours.
22. **库班余火 / Embers over the Kuban** — I-16, Bf 109, and Fw 190 in a
    fictionalized eastern-front campaign on Caucasus; 7 missions, 6–9 hours.
23. **最后一堂飞行课 / The Last Flying Lesson** — L-39, C-101, and MB-339
    training units forced into a regional war; 7 missions, 7–9 hours.
24. **航母没有退路 / No Retreat for the Carrier** — Su-33 carrier aviation
    campaign on Kola; 9 missions, 10–13 hours.
25. **空中桥梁 / The Air Bridge** — C-130 transport, evacuation, airdrop,
    and fighter-escort campaign; 8 missions, 9–12 hours.

### Independent helicopter campaigns

26. **黑鲨猎场 / Black Shark Hunting Grounds** — Ka-50 anti-armor and
    air-defense hunting on Caucasus; 8 missions, 8–11 hours.
27. **雌鹿走廊 / The Hind Corridor** — Mi-24P and Mi-8 assault transport
    and escort on Cold War Germany; 9 missions, 9–12 hours.
28. **沙漠长弓 / Desert Longbow** — AH-64D and OH-58D reconnaissance-attack
    coordination on Sinai; 10 missions, 11–15 hours.
29. **岛屿救援线 / Island Rescue Line** — UH-1H and SA342 special
    operations and combat rescue in the Marianas; 8 missions, 8–10 hours.
30. **极地吊运 / Arctic Heavy Lift** — CH-47F and Mi-8 heavy supply and
    evacuation on Kola; 8 missions, 9–12 hours.

Exact aircraft, assets, weapons, coalitions, and terrain support are checked
against the repository before final wording. A Prompt must instruct the
generating Agent to report an unsupported request instead of silently
substituting another unit.

## Long-Running Model and Image Generation Requirements

Campaigns, dynamic theaters, and other multi-mission requests explicitly
recommend a top-tier long-running model such as Fable or GPT-5.6-Ultra.

An AsciiDoc `IMPORTANT` block at the start of the Campaigns section states the
shared end-to-end contract once in full. Each campaign Prompt still names the
long-running-model and Image Gen requirements in a compact, self-contained
form, then spends its remaining detail budget on the scenario-specific
structure, forces, state, and deliverables. This avoids inflating the 15
existing campaign-pattern examples with repeated boilerplate while keeping a
copied Prompt actionable.

They instruct that model to carry the work through:

1. read the relevant `Docs` and inspect available `Tools`;
2. verify modules, terrains, units, weapons, bases, and coordinates;
3. establish the campaign bible and mission dependency graph;
4. generate each mission, briefing, and state transition;
5. run every available validation facility for every `.miz`;
6. check continuity across the whole campaign;
7. produce a final manifest and honest limitations report.

The model must not stop after producing a synopsis or mission list.

Multi-mission Prompts also require the model to call Image Gen for a campaign
cover, insignia or patch, chapter or key-mission artwork, and ending artwork
where appropriate. Generated images are atmosphere and presentation assets.
Navigation charts, target coordinates, and tactical maps must still be derived
from verified project data rather than treated as factual because Image Gen
drew them.

The requested output is organized into a campaign directory containing
missions, briefings, state or progression data, artwork, validation reports,
and a manifest.

## Validation

The finished reconstruction is checked with repository facilities that
actually exist. At minimum:

- both AsciiDoc files have identical heading paths and exactly 144 source
  blocks: 114 reconstructed baseline examples and 30 additional named
  campaigns;
- both files use the localized five-level macro TOC, section anchors and
  links, and AsciiDoc admonition blocks;
- every source block is properly delimited and non-empty;
- the 114 baseline Prompt bodies grow by 25–35 percent in aggregate before
  counting new campaign content;
- all owned aircraft and all six owned terrains appear in the pre-campaign
  catalog;
- full-fidelity MiG-29A, M-2000C, and JF-17 appear more often than before;
- the additional named campaign collection has exactly 30 Prompts, including
  five independent helicopter campaigns;
- every campaign states mission count or range, per-mission duration, total
  playtime, required modules or terrain, and campaign structure;
- every multi-mission Prompt recommends an appropriate long-running model,
  requires end-to-end completion, and requests Image Gen artwork;
- scenario details do not assert unverified DCS internal identifiers,
  payloads, parking positions, coordinates, or capabilities;
- English and Chinese remain semantically aligned and read naturally;
- no Prompt is filler, an empty placeholder, or a rigid configuration form.
