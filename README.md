<h1 align="center">DCSMizzer</h1>

<p align="center">
  <strong><a href="./README-zh.md">中文 README</a></strong>
</p>

`DCSMizzer` is an **LLM-oriented DCS combat generator**. It provides `Docs` for
Agents to read and `Tools` for Agents to call. Run your Coding Agent in this
directory, describe the combat scenario you want in *natural language*, and have
it generated for you.

> [!NOTE]
>
> Repository boundary: `Tools/` contains callable Python programs and their
> Python tests; `Docs/` contains model-facing documentation. Development
> worktrees may also contain surveys, baselines, and evidence records under
> `.develope/`; that maintenance area is removable and is not a product
> dependency.

> [!IMPORTANT]
>
> **Current status (2026-08-27): groundwork with an isolated runtime bridge.** `Tools` provide MIZ/CMP
> inspection; current-install static and real-mission observed evidence
> queries; locked upstream-cache preparation, readiness, and read-only pin-
> candidate audits; acknowledged
> commit-bound cross-map terrain, airbase, parking, spawn-point, unit, and
> pylon queries; current options and warehouse templates; finite common
> trigger, goal, and timed-text compilation; native MiG-29A GCI evidence;
> authored-spec evidence auditing; deterministic low-level MIZ assembly;
> strict complete-scenario structural and contract checks; read-back
> verification; beacon-fitted coordinates with whole-airfield holdouts,
> extrapolation diagnostics, WGS-84 geodesic offsets, and commit-bound planning-
> coastline distance/side checks; two-pass stable, content-addressed local
> evidence bundles with drift/readiness gates and privacy-safe runtime/terrain
> attestations; uniform CLI evidence-reference states plus fail-closed,
> pre/post-fenced current-bundle binding, including canonical intrinsic-report
> hashes, for source-matched read-only queries;
> disposable physical-
> probe MIZ instrumentation; a read-only, dependency-pinned Windows CI release
> gate; and an explicit-opt-in isolated DCS runtime bridge.
> The aggregate registry path was exercised on DCS 2.9.28.26385 by an older
> development producer; the current clean candidate was blocked by Steam
> authorization before Hook initialization and has no reusable runtime
> authority. An exact MIZ is runtime-valid only when its own hash-bound
> collection passes.
> Natural-language scenario planning, campaign generation, complete runtime
> registry record export, Mission Editor resave, and general behavioural or
> human-playtest validation are not implemented. Before use, read [`Docs/index.txt`](./Docs/index.txt) and run
> `python Tools/dcsmizzer.py capabilities`.
> The evidence-led development order and acceptance gates are recorded in
> [`Docs/development-roadmap.md`](./Docs/development-roadmap.md).
> The ordinary hosted/static gate and its strict separation from authorized
> local DCS validation are documented in
> [`Docs/continuous-validation.md`](./Docs/continuous-validation.md).

**A good Prompt is the foundation of a high-quality combat scenario.** See the
[**Prompt examples**](./PROMPT-SAMPLE.adoc) to learn how to write an effective
Prompt.

Another foundation is a sufficiently capable model, preferably one with
*multimodal capabilities* (such as generating campaign artwork) and *web search*.
Personally, a Codex subscription with GPT-5.6 Sol is a good choice.

This project is **open-source under the `GPL`** on
[**GitHub**](https://github.com/Water-Run/DCSMizzer). Thanks to the following
projects for providing the foundations for mapping:

- [pydcs](https://github.com/pydcs/dcs)
- [BriefingRoom for DCS](https://github.com/DCS-BR-Tools/briefing-room-for-dcs)
- [dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker)
- [DCS Global Terrain Database](https://github.com/flying-dice/dcs-global-terrain-database)
- [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution)
- [MOOSE](https://github.com/FlightControl-Master/MOOSE)

---

## Usage

*Before you begin, it is best to have the following available on your machine
(which should not be difficult if you already use a Coding Agent):*

- **[Python](https://www.python.org/)**, version 3.14 or later recommended;
- **[Lua](https://www.lua.org/)**, version 5.5.0 or later recommended; a `DCS` `.miz`
  file is essentially a package of `.lua` scripts;
- **[Git for Windows](https://gitforwindows.org/)**;
- **A Coding Agent.** The author recommends:

  - [Codex](https://github.com/openai/codex)
  - [OpenCode](https://github.com/anomalyco/opencode)
  - [CodeWhale](https://github.com/Hmbown/CodeWhale)
  - [OpenClaude](https://github.com/Gitlawb/openclaude)
  - [Grok Build](https://docs.x.ai/build/overview)
  - [Kimi Code](https://www.kimi.com/code/docs/)
  - [yaca](https://github.com/Water-Run/yaca) *&lt;waiting for the author to finish...&gt;*
- **A high-quality multimodal model.** GPT-5.6 Sol and Kimi K3, among others, are
  recommended.

*Once everything is ready, you can begin.*

**First, clone this project:**

```cmd
git clone https://github.com/Water-Run/DCSMizzer.git
cd DCSMizzer
```

**Then run a Coding Agent (for example, `codex`) in the project directory:**

```cmd
codex
```

**Ask the model to read the project and generate the combat scenario you want.
For example:**

```txt
Read the project's Docs and Tools, and generate a two-ship MiG-29A interception
mission on the Cold War Germany map.

The mission takes place on a summer afternoon in 1988, with widespread heavy
rain, low cloud, and strong winds. The player flies a full-fidelity Soviet Air
Force MiG-29A Fulcrum alongside one AI wingman in a two-aircraft formation.
The flight carries a standard air-to-air loadout of R-27 and R-73 missiles
with external fuel tanks, and cold-starts from a Soviet airbase near East
Berlin.

A French Air Force package approaches from the southwest through West Germany
and enters East German airspace, intending to attack Soviet military facilities
near East Berlin. The French formation includes a two-aircraft M-2000C flight
providing air superiority and escort, as well as a three-aircraft Mirage F1
flight conducting the ground attack. Guided by ground control, the player must
take off and intercept the package, break through the M-2000C escort, and stop
the Mirage F1s before they enter their weapons-release zone.

Keep the mission's equipment and atmosphere appropriate to the mid-to-late
1980s Cold War. The mission should last about 70 minutes and include cold
start, taxi, takeoff, radar guidance, interception, air combat, and recovery.

Query the database for real airbases, aircraft, weapons, pylons, and unit
types. Do not invent DCS internal names or CLSIDs. Generate and validate
output/east-berlin-mig29-intercept.miz. The mission should include a complete
briefing and other scenario narrative, plus success and failure checkpoints.
```

*Then wait for the atmosphere lottery result.*

---

<p align="center"><em>Thanks for making our dreams come true.</em></p>
