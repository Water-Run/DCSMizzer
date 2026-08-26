<h1 align="center">DCSMizzer</h1>

<p align="center">
  <strong><a href="./README.md">English README</a></strong>
</p>

`DCSMizzer`是一个**面向LLM的DCS战斗生成器**. 提供`Docs`供Agent阅读, 以及`Tools`供Agent调用. 在此目录运行你的Coding Agent, 用*自然语言*表述并生成你想要的战斗.

> [!NOTE]
>
> 目录边界：`Tools/`只保存可调用的Python程序及其Python测试；`Docs/`保存
> 面向模型直接阅读的文档。开发工作树也可在`.develope/`中保留测绘、基线和
> 证据记录；该维护目录可被移除，并非产品依赖。

> [!IMPORTANT]
>
> **当前状态（2026-08-26）：基础建设阶段，已具备隔离运行时桥。** `Tools`提供MIZ/CMP
> 检查；当前安装静态和真实任务观测证据查询；锁定上游缓存的准备和就绪检查；
> 认可且绑定提交、覆盖多地图的地形、机场、停机位、生成点、单位及挂点查询；
> 当前选项和仓库模板；常用触发器、
> 目标和定时文本的有限编译；原生MiG-29A GCI证据；构建规格证据审计；
> 确定性低层MIZ组装；完整场景严格结构与契约检查；回读验证；带整机场留出
> 检验、外推诊断和WGS-84测地线偏移的坐标转换；绑定提交的规划海岸线
> 距离与侧向检查；一次性物理探针MIZ注入；
> 以及显式授权、隔离配置的DCS运行时桥。聚合注册表路径已在DCS
> 2.9.28.26385上实测；只有某个MIZ自身哈希绑定的运行结果采集通过，才能称其
> 运行验证通过。
> 自然语言场景规划、战役生成、完整运行时注册表逐项导出、任务编辑器重存、
> 通用行为验证和人工游玩验证仍未实现。使用前先读[`Docs/index.txt`](./Docs/index.txt)，并运行
> `python Tools/dcsmizzer.py capabilities`。
> 以证据为导向的开发顺序与验收门槛记录在
> [`Docs/development-roadmap.md`](./Docs/development-roadmap.md)。

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

## 使用

*在开始之前, 你的设备最好有这些环境(相信对于有Coding Agent的你来说不是难事):*

- **[Python](https://www.python.org/)**. 推荐3.14及以上;
- **[Lua](https://www.lua.org/)**. 推荐5.5.0及以上; `DCS`的`.miz`实际就是`.lua`脚本包
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
