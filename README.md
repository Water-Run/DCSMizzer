<h1 align="center">DCSMizzer</h1>

<p align="center">
  <strong><a href="./README-zh.md">中文 README</a></strong>
</p>

`DCSMizzer` is an **Agent-oriented DCS World mission toolkit** with a Python
API, CLI, and model-facing documentation. Describe a scenario in natural
language; an Agent reads the guides, queries evidence, and calls the tools to
construct and validate a mission.

> [!NOTE]
>
> Repository boundary: `Tools/` contains callable Python programs and their
> Python tests; `Docs/` contains model-facing documentation. Development
> worktrees may also contain surveys, baselines, and evidence records under
> `.develope/`; that maintenance area is removable and is not a product
> dependency.

> [!IMPORTANT]
>
> **Current status (2026-10-02): installable Python library and CLI; groundwork phase.**
> Implemented facilities include MIZ/CMP inspection, evidence queries and audits,
> explicit-spec low-level construction and read-back verification, and an
> explicitly authorized isolated DCS runtime bridge. Offline registry-file
> validation exists; the current Hook still exports aggregate counts only.
> Natural-language planning, campaign generation, complete initialized-registry
> export, Mission Editor resave, general behavior validation, and human playtest
> validation remain unimplemented. Static or package success does not prove
> that a mission passed DCS runtime validation. Use
> [`Docs/capabilities.md`](./Docs/capabilities.md) and the current
> `python Tools/dcsmizzer.py capabilities` output for the capability boundary.

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

## Python library

The core Python package can now be installed from this repository with
Python 3.14 or later:

```powershell
python -m pip install .
# Use an editable install for development:
python -m pip install -e .
```

```python
from pathlib import Path
from dcsmizzer import inspect_miz, analyse_miz

mission = Path("output/mission.miz")
archive = inspect_miz(mission)
if archive.safe:
    observation = analyse_miz(mission)
    print(observation.theatre)
```

After installation, run `dcsmizzer capabilities` or
`python -m dcsmizzer capabilities`. The library provides inspection,
explicit-spec low-level construction, and validation. Natural-language
planning and campaign generation remain unimplemented. Evidence,
construction-provenance, and runtime commands still require a clean standalone
Git clone and the original `python Tools/dcsmizzer.py` integrity gate; a wheel
installation has no verified Git producer identity. See the
[Python library guide](Docs/python-library.md) for API usage, packaging,
and editable-install cache constraints.

## Documentation

| Need | Guide |
|---|---|
| Installation, Python API, distribution builds | [Python library](Docs/python-library.md) |
| Agent command and reference selection | [Document entry](Docs/index.txt), [command router](Docs/tools.md) |
| Build a user scenario | [Mission workflow](Docs/quickstart.md), [build spec](Docs/build-spec.md) |
| Interpret capability and validation claims | [Capabilities](Docs/capabilities.md), [validation](Docs/validation.md) |
| Development direction and release changes | [Roadmap](Docs/development-roadmap.md), [changelog](CHANGELOG.md) |

## Usage

*Before you begin, it is best to have the following available on your machine
(which should not be difficult if you already use a Coding Agent):*

- **[Python](https://www.python.org/)** 3.14 or later. Product runtime imports
  use only the standard library.
- An optional **[Lua](https://www.lua.org/)** interpreter for developer Hook
  tests. The library parses Lua data in MIZ archives itself and does not need
  an external Lua interpreter.
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
