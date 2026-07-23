# DCSMizzer

[英文README](./README.md)

`DCSMizzer`是一个面向LLM的DCS战斗生成器. 提供`Docs`供Agent阅读, 以及`Tools`供Agent调用. 在此目录运行你的Coding Agent, 用自然语言表述并生成你想要的战斗.  
良好的Prompt是生成高质量战斗的基础: 你可以参考[Prompt示例](./PROMPT-SAMPLE-zh.adoc)学习如何写一个有效的Prompt.
另一个基础是一个基础性能足够强大的模型, 最好有多模态(比如生成战役图片)和联网搜索等能力. 就个人而言, CodeX订阅GPT-5.6 sol是一个好的选择.  
项目使用`GPL`协议开源与[GitHub](https://github.com/Water-Run/DCSMizzer). 感谢这些项目, 提供了测绘的基础:

* [pydcs](https://github.com/pydcs/dcs)
* [BriefingRoom for DCS](https://github.com/DCS-BR-Tools/briefing-room-for-dcs)
* [dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker)
* [DCS Global Terrain Database](https://github.com/flying-dice/dcs-global-terrain-database)
* [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution)
* [MOOSE](https://github.com/FlightControl-Master/MOOSE)

## 使用

在开始之前, 你的设备最好有这些环境(相信对于有Coding Agent的你来说不是难事):

* [Python](https://www.python.org/). 推荐3.14及以上;
* [Lua](https://www.lua.org/). 推荐5.50及以上; `DCS`的`.miz`实际就是`.lua`脚本包
* [Git For Windows](https://gitforwindows.org/)
* 一个Coding Agent. 作者推荐这些Agent:

  * [CodeX](https://github.com/openai/codex)
  * [OpenCode](https://github.com/anomalyco/opencode)
  * [Codewhale](https://github.com/Hmbown/CodeWhale)
  * [OpenClaude](https://github.com/Gitlawb/openclaude)
  * [Grok Build](https://docs.x.ai/build/overview)
  * [Kimi Code](https://www.kimi.com/code/docs/)
  * [yaca](https://github.com/Water-Run/yaca) <等作者写完...>
* 高质量多模态的大模型. 推荐GPT5.6Sol, KimiK3等

一切准备就绪就可以开始了.  
首先, 克隆此项目:  

```cmd
git clone https://github.com/Water-Run/DCSMizzer.git
cd DCSMizzer
```

然后, 在目录下, 运行Coding Agent(例如`codex`):  

```cmd
codex
```

让大模型阅读项目, 生成你想要的战斗. 例如:  

```txt
阅读项目中的Docs和Tools，生成一个冷战德国地图的双人MiG-29A拦截任务。

任务发生在1988年夏季下午，天气为大范围暴雨、低云和强风。玩家驾驶苏联空军全模拟MiG-29A支点，与一架AI僚机组成双机编队，携带R-27和R-73空空导弹，从东柏林附近的苏联机场冷启动起飞。

一支法国空军集群从西南方向经西德进入东德领空，目标是攻击东柏林附近的苏联军事设施。法国编队包括负责制空和护航的M-2000C，以及执行对地攻击的Mirage F1编队。玩家需要在A-50M预警机和地面引导下起飞拦截，突破M-2000C护航，并在Mirage F1进入武器释放区之前阻止攻击。

任务保持1980年代中后期装备和冷战氛围。任务时长约70分钟，包含起飞、雷达引导、拦截、空战和返航过程。

查询数据库中的真实机场、机体、武器、挂点和单位类型，不要编造DCS内部名称或CLSID。生成并验证output/east-berlin-mig29-intercept.miz，同时输出任务简报和验证报告。
```

等待氛围抽奖结果.  

> *Thanks for making our dreams come true.*
