# DCSMizzer 测绘证据与版本账本（2026-07-26）

> 历史测绘：数字、上游提交和能力状态已由 2026-07-27 可重现基线取代；本文只保留作方法与决策记录。

## 1. 目的与结论边界

本账本回答四个问题：

1. 本轮实际搜索和打开了什么；
2. 每项结论对应哪个版本或本机数据源；
3. 哪些目录只是同一内容的镜像；
4. 哪些检查尚未运行，不能据此声称任务可玩或生成能力已完成。

本轮只在 `.develope/` 下提交 Markdown 调查材料。所有安装文件、Saved Games
任务、官方战役镜像和上游克隆都按只读证据处理。

## 2. 会话能力门检查

项目要求至少具备 GPT-5.6 级推理与编码能力、互联网搜索、多模态处理和长时工具
使用能力。当前工作区没有暴露可独立核验的精确模型层级，因此**无法证明具体模型
标签或等级**。当前会话实际提供并使用了：

- 本地文件系统、PowerShell、Python、Lua、Git 与 ZIP 读取能力；
- 可访问互联网的搜索能力；
- 图像查看/生成接口（本轮没有任务素材需要调用）；
- 足以完成多轮仓库、上游和任务语料分析的上下文与工具调用。

精确模型层级不可见是本轮的环境不确定项，不应被后续文档省略或改写为已验证。

## 3. 仓库基线

| 项目 | 值 |
|---|---|
| 工作区 | `D:\Coding\DCSMizzer` |
| 分支 | `main` |
| 调查开始提交 | `bd303a8` |
| 远端 | `https://github.com/Water-Run/DCSMizzer.git` |
| 初始状态 | `main` 与 `origin/main` 同步，父仓库工作树干净 |
| 上游目录 | `.develope/upstream/`，父仓库忽略，仅作本机参考 |
| 官方镜像目录 | `.develope/official-campaigns/DCSWorld/`，父仓库忽略 |
| 参考快照 | `.develope/reference/`，已跟踪但只是局部、带版本的提取结果 |

索引时实际检查了 Git 状态、已跟踪文件、相关未跟踪文件、目录内容以及空目录。
`Docs/index.txt` 与 `Tools/index.txt` 当时为空；目录名本身不构成已实现能力的证据。

## 4. 本机搜索范围

### 4.1 活动证据根

| 逻辑名称 | 实际根 | 用途 |
|---|---|---|
| DCS 安装 | `D:\SteamLibrary\steamapps\common\DCSWorld` | 当前安装任务、战役和版本 |
| Saved Games | `%USERPROFILE%\Saved Games\DCS` | 用户任务与下载/实验任务 |
| 官方战役镜像 | `.develope/official-campaigns/DCSWorld` | 便于只读研究的安装目录副本 |
| 上游样例 | `.develope/upstream` | 六个第三方项目内的测试、模板和样例任务 |

对 `C:\` 与 `D:\` 进行了包含隐藏/忽略项的 `.miz`、`.cmp` 扩展名扫描。扫描得到
1,089 个后缀匹配路径，其中 1,059 个位于上述活动证据根，另外 30 个为：

- 回收站内 27 个 `.miz` 后缀对象：15 个仍是有效 ZIP，12 个是回收站元数据或
  不可作为 ZIP 读取的对象；15 个有效 ZIP 中有 9 个文件实例与活动语料哈希相同；
- Windows 语音组件内 3 个 `.cmp` 文件：不是 DCS 战役，按扩展名误命中。

回收站对象属于已删除状态，未纳入活动语料、语义统计或后续验收基线。系统 `.cmp`
也未按战役解析。

### 4.2 覆盖限制

- 只扫描了本机 `C:`、`D:` 固定卷；未扫描断开的移动盘、网络共享、云端仅在线文件
  或其他用户配置文件。
- 只发现 `%USERPROFILE%\Saved Games\DCS`，未发现可纳入的其他 `DCS*`
  Saved Games 根；未来机器可能同时存在 Open Beta、Dedicated Server 等目录。
- 本机安装内容取决于当前已安装模块，不代表 DCS 全产品线。
- 没有读取回收站任务正文，也没有恢复任何删除文件。
- 没有修改 DCS 安装、Saved Games、镜像或上游克隆中的任务内容。

## 5. DCS 版本证据

| 证据 | 观测值 |
|---|---|
| `bin\DCS.exe` 产品版本 | `2.9.28.26283` |
| `bin\DCS.exe` 文件版本 | `2.9.28.26283` |
| EXE 最后写入时间 | `2026-07-24T21:32:40+08:00` |
| Steam App ID | `223750` |
| Steam Build ID | `24331355` |
| Steam `SizeOnDisk` | `638,583,196,667` bytes |
| 官方发行记录 | [DCS 2.9.28.26283，2026-07-22](https://www.digitalcombatsimulator.com/en/news/changelog/release/2.9.28.26283/) |

本机 EXE 与 Eagle Dynamics 官方发行记录的版本号一致。该对应关系只冻结到
2026-07-26；DCS 更新后必须重取版本并判断语料是否随安装更新而变化。

任务脚本的运行语境参考 Eagle Dynamics 的
[Lua environment](https://www.digitalcombatsimulator.com/en/support/faq/1253/)。
官方说明确认任务脚本运行于 Mission Scripting Environment，但没有提供完整
`.miz` 存档模式，因此本轮格式结论主要来自实际任务和上游源码。

## 6. 上游源码版本

2026-07-26 对六个克隆执行了安全的 `git pull --ff-only`。Retribution 从
`b7493d016f3c` 快进到下表提交；其余仓库已经位于远端当前提交。更新后六个工作树
均为干净状态。

| 项目 | 远端 | 分支 | 检查提交 | 提交时间 | 许可证据 |
|---|---|---|---|---|---|
| BriefingRoom | [DCS-BR-Tools/briefing-room-for-dcs](https://github.com/DCS-BR-Tools/briefing-room-for-dcs) | `main` | `a5893db7daece0e2c25403c34a104057b7365a59` | 2026-07-24 | 根许可文件：GPL-3.0 |
| DCS Global Terrain Database | [flying-dice/dcs-global-terrain-database](https://github.com/flying-dice/dcs-global-terrain-database) | `main` | `d58c7a38d3f0a681bde67bed21868b6d3ecd9bb8` | 2023-02-06 | `package.json`：ISC；根目录未见许可正文 |
| dcs-mission-maker | [JonathanTurnock/dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker) | `master` | `48b2841b4f72ba32be217f3e618cfa3cec6c8f28` | 2023-11-15 | `package.json`：MIT；根目录未见许可正文 |
| DCS Retribution | [dcs-retribution/dcs-retribution](https://github.com/dcs-retribution/dcs-retribution) | `dev` | `fd932440b55e9e20f487697b3aee73c783f2bb5a` | 2026-07-25 | 根许可文件：LGPL-3.0 |
| MOOSE | [FlightControl-Master/MOOSE](https://github.com/FlightControl-Master/MOOSE) | `master-ng` | `27fa920a8fd49c589565f819ede31914254b9e9e` | 2026-07-23 | 根许可文件：GPL-3.0 |
| pydcs | [pydcs/dcs](https://github.com/pydcs/dcs) | `master` | `412952c5ad5688783d8d53830280f316dbe311ff` | 2026-06-29 | 根许可文件：LGPL-3.0 |

“许可证据”只记录仓库内实际看到的声明。尤其是仅在包清单中声明许可、却没有根
许可正文的两个 JavaScript 项目，未来若考虑分发或复制代码，必须回到上游再次核对，
不能只凭本表作法律结论。

## 7. 证据方法

### 7.1 存档与哈希

- 使用 SHA-256 对四个活动根的全部 `.miz`、`.cmp` 做内容级去重；
- 使用 Python `zipfile` 打开 `.miz`，枚举成员、压缩/解压大小、重复成员、
  加密标志和核心文件；
- 对安装、Saved Games、上游的 905 个非镜像 `.miz` 文件实例运行全成员 CRC；
- 官方镜像逐文件哈希等同于安装子集，因此没有把它再次计作独立语料。

### 7.2 Lua 数据

- 用当前 pydcs 的 `dcs/lua/parse.py` 独立模块解析 `mission`、`options`、
  `warehouses`、`dictionary` 与 `mapResource`；
- 不导入完整 pydcs 包来完成语料扫描，因为完整包在本机还需要未安装的
  `pyproj`；这不影响独立 Lua 数据解析模块；
- 对 pydcs 失败的两个 Saved Games 样本，以空全局环境、指令数限制的 Lua 5.5
  沙箱加载，确认任务表语法可被 Lua 接受；
- `.cmp` 同样在空环境和指令限制下加载，只汇总结构和引用，不输出名称、描述或正文。

解析数据表与执行任务脚本是两件事。本轮没有执行 `.miz` 中的 `Scripts/`、触发器
脚本字符串或外部 Lua 资源。

### 7.3 上游源码

每个项目都完成了 README、许可、根目录、入口和任务相关数据模型的初始检查，
随后打开相关源文件。结论以当前提交的实际源码为准，不从仓库名、目录名或模型记忆
推断能力。

## 8. 证据层级与冲突规则

后续开发应按下列顺序选择最接近问题的证据：

1. 当前安装数据和可验证导出：内部类型名、地图/机场/停机位、武器和本机兼容性；
2. 当前安装的真实任务：存档结构、编辑器实际写法和官方设计模式；
3. Saved Games 任务：用户环境兼容性、旧编码和非官方写法；
4. 当前上游源码：库的实际 API、数据模型和已知限制；
5. Eagle Dynamics 当前官方网页：版本、发行状态和脚本环境；
6. `.develope/reference/`：只在其提取版本和覆盖范围内使用。

出现冲突时必须同时记录来源版本。例如：

- pydcs 解析器不接受两个 Saved Games 任务中的表内裸标识符键；
- Lua 5.5 沙箱接受同一任务；
- 因此结论是“pydcs 解析器覆盖不足”，不是“任务损坏”。

不得把不同 DCS 版本、地图版本或上游提交的数据静默合并为一个无版本事实。

## 9. 版权、隐私与仓库边界

- 未提交任何 `.miz`、`.cmp`、音频、图片、kneeboard、简报或任务脚本；
- 未在文档中摘录任务标题、战役叙事、简报正文或私有 Saved Games 文件名；
- 哈希只用于内存中的去重和关系判断，没有形成可追踪私有文件的清单；
- 上游克隆保留其 Git 历史和许可，仍位于父仓库忽略目录；
- 文档只保留结构、数量、版本、能力、限制和未来验收要求。

## 10. 尚未完成的验证

以下事项没有运行，不能在产品文档中写成已完成：

- 在 DCS 中打开、保存或实际飞行任一任务；
- 运行全部上游项目的构建和测试；
- 验证每个武器 CLSID 对每个机型/挂点/年代的兼容性；
- 验证所有机场、停机位、地图坐标和地形碰撞；
- 执行任务脚本、MOOSE、动态生成或多人联机流程；
- 对未安装模块、未连接存储和未来 DCS 版本进行覆盖。

详细语料结果见
[MIZ/CMP 语料地图](2026-07-26-miz-cmp-corpus-map.md)，上游入口与限制见
[上游能力地图](2026-07-26-upstream-capability-map.md)。
