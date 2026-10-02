<h1 align="center">DCSMizzer</h1>

<p align="center">
  <strong><a href="./README.md">English README</a></strong>
</p>

`DCSMizzer`是一个**面向 Agent 的 DCS World 任务工具库**，提供 Python API、CLI 和模型阅读文档。用户用自然语言描述场景，由 Agent 阅读文档、查询证据，再调用工具构建和验证任务。

> [!NOTE]
>
> 目录边界：`Tools/`只保存可调用的Python程序及其Python测试；`Docs/`保存
> 面向模型直接阅读的文档。开发工作树也可在`.develope/`中保留测绘、基线和
> 证据记录；该维护目录可被移除，并非产品依赖。

> [!IMPORTANT]
>
> **当前状态（2026-10-02）：可安装的 Python 库与 CLI，仍处于基础建设阶段。**
> 已实现 MIZ/CMP 检查、证据查询与审计、基于明确规格的低层 MIZ 构建和回读验证，
> 以及需要显式授权的隔离 DCS 运行时桥。注册表文件的离线结构验证已实现，
> 当前 Hook 仍只导出聚合计数。
> 自然语言规划、战役生成、完整运行时注册表导出、任务编辑器重存、通用行为验证
> 和人工游玩验证仍未实现。静态检查或打包成功不代表某个任务已经通过 DCS 运行验证。
> 能力边界以 [`Docs/capabilities.md`](./Docs/capabilities.md) 和当前
> `python Tools/dcsmizzer.py capabilities` 输出为准。

**良好的Prompt是生成高质量战斗的基础:** 你可以参考[**Prompt示例**](./PROMPT-SAMPLE-zh.adoc)学习如何写一个有效的Prompt.

另一个基础是一个基础性能足够强大的模型, 最好有*多模态*(比如生成战役图片)和*联网搜索*等能力. 就个人而言, Codex订阅GPT-5.6 Sol是一个好的选择.

项目**使用`GPL`协议开源**与[**GitHub**](https://github.com/Water-Run/DCSMizzer). 感谢这些项目, 提供了测绘的基础:

- [pydcs](https://github.com/pydcs/dcs)
- [BriefingRoom for DCS](https://github.com/DCS-BR-Tools/briefing-room-for-dcs)
- [dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker)
- [DCS Global Terrain Database](https://github.com/flying-dice/dcs-global-terrain-database)
- [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution)
- [MOOSE](https://github.com/FlightControl-Master/MOOSE)

---

## Python 库

核心代码是 Python 包，现在可以从此仓库安装为库（需要 Python 3.14 或更高版本）：

```powershell
python -m pip install .
# 开发时使用可编辑安装：
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

安装后可运行 `dcsmizzer capabilities` 或 `python -m dcsmizzer capabilities`。
库提供任务检查、基于明确规格的低层构建和验证；自然语言规划和战役生成仍未实现。
证据、构建溯源和运行时命令仍需要干净的独立 Git 克隆及原有
`python Tools/dcsmizzer.py` 校验入口，wheel 安装不具备 Git 来源证明。
API、构建方法和可编辑安装的缓存约束见[Python 库说明](Docs/python-library.md)。

## 文档导航

| 需要 | 文档 |
|---|---|
| 安装、Python API、分发包构建 | [Python 库](Docs/python-library.md) |
| 为 Agent 选择命令与参考 | [文档入口](Docs/index.txt)、[命令路由](Docs/tools.md) |
| 按用户场景生成任务 | [任务工作流](Docs/quickstart.md)、[构建规格](Docs/build-spec.md) |
| 判断能力和验证结果 | [能力边界](Docs/capabilities.md)、[验证语义](Docs/validation.md) |
| 开发方向和版本变更 | [开发路线](Docs/development-roadmap.md)、[更新记录](CHANGELOG.md) |

## 使用

*在开始之前, 你的设备最好有这些环境(相信对于有Coding Agent的你来说不是难事):*

- **[Python](https://www.python.org/)** 3.14 或更高版本。库的运行依赖只有标准库。
- **[Lua](https://www.lua.org/)** 解释器是可选的开发环境，用于 Hook 的 Lua 测试；库自行解析 MIZ 中的 Lua 数据，不需要外部 Lua。
- **[Git for Windows](https://gitforwindows.org/)**
- **一个Coding Agent.** 作者推荐这些Agent:

  - [Codex](https://github.com/openai/codex)
  - [OpenCode](https://github.com/anomalyco/opencode)
  - [CodeWhale](https://github.com/Hmbown/CodeWhale)
  - [OpenClaude](https://github.com/Gitlawb/openclaude)
  - [Grok Build](https://docs.x.ai/build/overview)
  - [Kimi Code](https://www.kimi.com/code/docs/)
  - [yaca](https://github.com/Water-Run/yaca) *&lt;等作者写完...&gt;*
- **高质量多模态的大模型.** 推荐GPT-5.6 Sol, Kimi K3等

*一切准备就绪就可以开始了.*

**首先, 克隆此项目:**

```cmd
git clone https://github.com/Water-Run/DCSMizzer.git
cd DCSMizzer
```

**然后, 在目录下, 运行Coding Agent(例如`codex`):**

```cmd
codex
```

**让大模型阅读项目, 生成你想要的战斗. 例如:**

```txt
阅读项目中的Docs和Tools，生成一个冷战德国地图的双机MiG-29A拦截任务。

任务发生在1988年夏季下午，天气为大范围暴雨、低云和强风。玩家驾驶苏联空军全模拟MiG-29A支点，与一架AI僚机组成双机编队，携带R-27和R-73空空导弹及副油箱的标准对空构型，从东柏林附近的苏联机场冷启动起飞。

一支法国空军集群从西南方向经西德进入东德领空，目标是攻击东柏林附近的苏联军事设施。法国编队包括负责制空和护航的M-2000C双机编队，以及执行对地攻击的Mirage F1三机编队。玩家需要在地面引导下起飞拦截，突破M-2000C护航，并在Mirage F1进入武器释放区之前阻止攻击。

任务保持1980年代中后期装备和冷战氛围。任务时长约70分钟，包含冷启动、滑行、起飞、雷达引导、拦截、空战和返航过程。

查询数据库中的真实机场、机体、武器、挂点和单位类型，不要编造DCS内部名称或CLSID。生成并验证output/east-berlin-mig29-intercept.miz，任务包括完整的简报等场景叙事，以及成功和失败的检查点。
```

*等待氛围抽奖结果.*

---

<p align="center"><em>Thanks for making our dreams come true.</em></p>
