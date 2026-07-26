# DCSMizzer 上游能力地图（2026-07-26）

## 1. 用途

本页记录六个已确认第三方项目在当前提交中**实际存在**的能力、入口、数据模型和
限制。目标是帮助未来 DCSMizzer 选择证据与设计参考，不是选择一个项目直接复制为
产品实现。

全部克隆位于 `.develope/upstream/`，由父仓库忽略，保持原 Git 历史与许可。本轮
没有把第三方源码复制到 DCSMizzer 跟踪路径。

精确远端、分支、提交和许可见
[证据与版本账本](2026-07-26-evidence-ledger.md)。

## 2. 能力总览

| 项目 | 读取 MIZ | 写出 MIZ | 任务生成 | 战役模型 | 地形/单位数据 | DCS 内运行时 |
|---|---|---|---|---|---|---|
| pydcs | 是 | 是 | 底层对象/API | 否 | 强，按其导出版本 | 否 |
| dcs-mission-maker | 未见读取器 | 是，范围有限 | 最小 TypeScript 构造 | 否 | 很少 | 否 |
| DCS Global Terrain Database | 否 | 否 | 否 | 否 | Caucasus GeoJSON | 否 |
| BriefingRoom | 以生成模型为主 | 是 | 完整场景管线 | 是 | 自有数据库，多地图 | 可嵌入脚本，但不是运行库 |
| DCS Retribution | 通过 pydcs | 是 | 动态战役任务生成 | 是 | 自有战区/阵营/载荷 | 生成任务，非通用运行框架 |
| MOOSE | 不负责存档读取 | 不负责存档打包 | 运行时编排 | 运行时任务体系 | DCS 对象封装 | 是 |

这六个项目处在不同层次：

- pydcs 与 dcs-mission-maker 主要说明数据和序列化；
- GTD 说明地理数据格式；
- BriefingRoom 与 Retribution 说明生成管线；
- MOOSE 说明任务启动后的运行时行为。

把它们视为可互换的“任务生成器”会导致错误架构。

## 3. pydcs

### 3.1 冻结版本

- 远端：[pydcs/dcs](https://github.com/pydcs/dcs)
- 分支：`master`
- 提交：`412952c5ad5688783d8d53830280f316dbe311ff`
- 许可：LGPL-3.0

### 3.2 实际入口与模型

| 路径 | 作用 |
|---|---|
| `dcs/mission.py` | `Mission` 根对象，读取/保存 `.miz` 与主要 Lua 表 |
| `dcs/lua/parse.py` | Lua 数据表解析器 |
| `dcs/lua/serialize.py` | Lua 表序列化 |
| `dcs/coalition.py`、`country.py`、`unitgroup.py` | 联盟、国家、组模型 |
| `dcs/flyingunit.py`、`unit.py` | 单位模型 |
| `dcs/point.py`、`terrain/` | 坐标、地图投影、机场/跑道/停机位 |
| `dcs/planes.py`、`helicopters.py` 等 | 从 DCS 数据导出的类型定义 |
| `dcs/weapons_data.py` | 武器与 CLSID 数据 |

`Mission.load_file`/`load` 读取 ZIP 中的主表，`Mission.save` 重新生成任务存档。当前
提交还包含把载荷 Lua 中的武器设置写入挂点数据的更新。

### 3.3 可借鉴内容

- Python 中较完整的任务对象关系；
- 地图投影与机场对象；
- 单位、国家、武器和任务类型；
- `.miz` 基础读写流程；
- 大量已有任务样例和解析测试。

### 3.4 已验证限制

1. `dcs/lua/parse.py` 不支持真实 Saved Games 样本中的表内裸标识符键；
2. 它把 Lua 解析为 Python 字典，不能天然保留源码顺序、注释或重复键；
3. 完整包导入依赖 `pyproj` 等环境，本机仅独立使用解析模块完成调查；
4. 生成的类型数据是某次 DCS 导出，不自动等同于当前本机安装；
5. 对未知/新字段的对象级往返保真不能从“能解析主表”直接推出。

结论：pydcs 是优先的模型和数据参考，也是可用于交叉验证的实现，但不能未经兼容层
直接定义 DCSMizzer 的全部输入语法或无损模型。

## 4. dcs-mission-maker

### 4.1 冻结版本

- 远端：[JonathanTurnock/dcs-mission-maker](https://github.com/JonathanTurnock/dcs-mission-maker)
- 分支：`master`
- 提交：`48b2841b4f72ba32be217f3e618cfa3cec6c8f28`
- 包版本：`0.0.0-development`
- 许可声明：`package.json` 为 MIT；根目录未见许可正文

### 4.2 实际入口与输出

| 路径 | 作用 |
|---|---|
| `src/index.ts` | 对外导出 |
| `src/dcs-mission.ts` | `DcsMission`、成员构造和 JSZip 打包 |
| `src/files/mission.ts` | Zod 任务模式 |
| `src/files/options.ts` | options 模式 |
| `src/files/warehouses.ts` | warehouses 模式 |
| `src/files/dictionary.ts` | 字典模式 |
| `src/files/mapResource.ts` | 资源映射模式 |
| `src/js-2-lua/` | JavaScript 到 Lua 数据文本 |

`DcsMission.getFiles()` 当前明确写出六项：

1. `options`；
2. `l10n/DEFAULT/mapResource`；
3. `warehouses`；
4. `theatre`；
5. `mission`；
6. `l10n/DEFAULT/dictionary`。

随后 `build()` 用 JSZip 生成 DEFLATE `.miz`。

### 4.3 可借鉴内容

- 用 Zod 在构造期验证坐标、日期、天气、组、单位和航路点；
- 通过字典对象生成简报键；
- JavaScript/TypeScript 中最小存档生成的清晰边界；
- 对固定翼与地面车辆组的可测试模式。

### 4.4 已验证限制

- 当前任务模式显式建模固定翼和车辆组，未形成等量的直升机、舰船、静态物能力；
- `mapResource` 模式为空对象，options/warehouses 中大量结构以空表默认；
- 没有看到现有 `.miz` 的读取或无损往返层；
- 当前提交距本轮 DCS 版本较远，包仍标记 development；
- 仅有包清单许可声明，未来分发前要补核许可正文。

结论：适合参考“最小 TypeScript 构造器 + 模式验证”，不应被视作当前 DCS 全格式
实现。

## 5. DCS Global Terrain Database

### 5.1 冻结版本

- 远端：[flying-dice/dcs-global-terrain-database](https://github.com/flying-dice/dcs-global-terrain-database)
- 分支：`main`
- 提交：`d58c7a38d3f0a681bde67bed21868b6d3ecd9bb8`
- 包版本：`1.0.0`
- 许可声明：`package.json` 为 ISC；根目录未见许可正文

### 5.2 实际数据流

| 路径 | 作用 |
|---|---|
| `src/caucasus/terrain.json` | 地形边界来源 |
| `src/caucasus/aerodromes.json` | 机场来源 |
| `src/caucasus/beacons.json` | 信标来源 |
| `scripts/build.js` | 合并、校验并写 GeoJSON FeatureCollection |
| `scripts/schemas.js` | 属性 Zod 模式 |
| `scripts/geojson.schema.json` | GeoJSON AJV 模式 |
| `terrains/caucasus.json` | 构建结果 |

当前仓库实际只覆盖 Caucasus。构建脚本使用 Turf 合并 features，再以 AJV 验证
GeoJSON、以 Zod 验证部分属性。

### 5.3 源码中观察到的校验缺口

`scripts/build.js` 的类型枚举接受 `AIRBASE`，但 `switch` 中调用机场模式的分支写成
`AERODROME`。因此 `AIRBASE` feature 可以通过枚举，却不会进入
`aerodromeSchema.parse` 分支。这是当前提交的实际源代码不一致，意味着不能仅凭
“构建成功”认定所有机场属性经过预期 Zod 校验。

此外：

- 只覆盖一个地图；
- 数据提交停留在 2023 年；
- GeoJSON 适合地理交换，但不提供当前 DCS 停机位、单位/任务或 `.miz` 模型。

结论：可作为 Caucasus 地理模式和 GeoJSON 组织参考；位置、机场 ID 和当前版本兼容
仍需本机 DCS 或更新数据交叉验证。

## 6. BriefingRoom for DCS

### 6.1 冻结版本

- 远端：[DCS-BR-Tools/briefing-room-for-dcs](https://github.com/DCS-BR-Tools/briefing-room-for-dcs)
- 分支：`main`
- 提交：`a5893db7daece0e2c25403c34a104057b7365a59`
- 许可：GPL-3.0

### 6.2 已核对入口

| 路径 | 作用 |
|---|---|
| `src/BriefingRoom/IBriefingRoom.cs` | 公共引擎接口 |
| `src/BriefingRoom/BriefingRoom.cs` | 引擎实现与任务/战役生成入口 |
| `src/BriefingRoom/Template/` | `.brt`/`.cbrt` 模板模型 |
| `src/BriefingRoom/Generator/MissionGenerator/Generator.cs` | 主生成管线 |
| `src/BriefingRoom/Generator/CampaignGenerator.cs` | 战役生成 |
| `src/BriefingRoom/Mission/DCSMission.cs` | 内存任务根 |
| `src/BriefingRoom/Library/MizMaker.cs` | `.miz` 序列化与打包 |
| `Database/`、`DatabaseJSON/` | 单位、地图、天气、目标、时代等数据 |
| `Include/Lua/` | 注入任务的运行脚本与功能 |

源码中的主生成管线按阶段构建场景、机场、前线、目标、航母、玩家组、CAP、空防和
任务功能。输出模型分别组织组、单位、航路点、触发器、简报、资源和仓库，再由
`MizMaker` 打包。

### 6.3 可借鉴内容

- 自然语言上游所需的结构化任务模板思想；
- 生成阶段之间的顺序与共享状态；
- 多地图机场、地形边界与生成点；
- 目标、特性、天气、时代武器和联盟数据库；
- 确定性/状态回滚方向；
- 简报、图片、kneeboard、资源和 Lua 功能的一体化处理。

### 6.4 限制与使用边界

- 是 GPL-3.0 完整应用，不是无条件可复制的代码库；
- 自有数据库和 DCSMizzer 本机证据可能版本不同；
- 大量运行功能依赖注入 Lua，增加安全与运行时验证范围；
- 生成能力丰富不代表其每个字段都适合 DCSMizzer 的目标或当前安装；
- 本轮检查源码与样例，没有构建、运行其前端或生成器测试。

结论：是生成架构、目标拆解、资源组织和数据覆盖的重要设计参考；应提取事实与模式，
不复制实现。

## 7. DCS Retribution

### 7.1 冻结版本

- 远端：[dcs-retribution/dcs-retribution](https://github.com/dcs-retribution/dcs-retribution)
- 分支：`dev`
- 提交：`fd932440b55e9e20f487697b3aee73c783f2bb5a`
- 许可：LGPL-3.0

### 7.2 已核对入口

| 路径 | 作用 |
|---|---|
| `game/missiongenerator/missiongenerator.py` | `MissionGenerator` 与 `generate_miz` |
| `game/missiongenerator/` | 空中、地面、仓库、触发器等任务生成阶段 |
| `game/theater/` | 战区、控制点与地理模型 |
| `game/ato/`、`game/flightplan/` | 航空任务与飞行计划 |
| `resources/customized_payloads/` | 机型载荷预设 |
| `resources/factions/` | 阵营与编制数据 |

`generate_miz` 构建 pydcs `Mission`，依次生成地面冲突、空中单位、摧毁状态、仓库等
内容，最后调用 `Mission.save`。这说明 Retribution 的任务模型部分建立在 pydcs
序列化之上，另有自己的动态战役状态、阵营、载荷和战区层。

### 7.3 可借鉴内容

- 任务生成与长期战役状态分离；
- ATO、任务类型与飞行计划；
- 阵营/时代编制；
- 经过项目维护的载荷预设；
- 地面战线、目标与资源状态如何映射到单次任务。

### 7.4 限制与使用边界

- `dev` 分支持续变化，本轮刚从旧提交快进；
- 自定义载荷是项目选择，不等同于 DCS 当前完整挂点数据库；
- 通过 pydcs 写任务，也继承其数据版本和序列化边界；
- 动态战役假设不一定符合用户要求的单次叙事任务；
- 本轮没有运行应用、生成战役或测试。

结论：适合研究“战役状态 → 一次 sortie”的映射、载荷候选与阵营编制。最终类型和
挂载仍需本机 DCS 数据验证。

## 8. MOOSE

### 8.1 冻结版本

- 远端：[FlightControl-Master/MOOSE](https://github.com/FlightControl-Master/MOOSE)
- 分支：`master-ng`
- 提交：`27fa920a8fd49c589565f819ede31914254b9e9e`
- 许可：GPL-3.0

### 8.2 实际角色

相关源码集中在：

- `Moose Development/Moose/Wrapper/Group.lua`：DCS 组包装；
- `Moose Development/Moose/Ops/Auftrag.lua`：任务/行动对象；
- `Moose Development/Moose/Ops/FlightGroup.lua`、`ArmyGroup.lua`、
  `NavyGroup.lua`：运行组；
- 其他 `Core/`、`Functional/`、`AI/`、`Ops/` 模块：调度、区域、事件和功能。

MOOSE 在 DCS Mission Scripting Environment 中运行，处理出生、任务下发、区域、
事件、调度和动态行为。它不是 `.miz` ZIP 读取器或通用序列化器。

### 8.3 可借鉴内容

- DCS 运行对象和事件生命周期；
- 组/单位控制与任务下发；
- 区域、调度、AI 行为和运行时状态机；
- Vec2/Vec3 坐标约定；
- 复杂任务如何从静态编辑器数据扩展到运行时。

### 8.4 限制与使用边界

- GPL-3.0，不能无视许可复制到产品；
- 功能需要任务中注入脚本并在 DCS 运行；
- 静态存档检查无法证明其运行行为；
- MOOSE API 名称不能替代 `.miz` 内部字段或当前本机类型验证；
- 本轮没有把 MOOSE 注入任务或运行 DCS。

结论：只有当未来场景确实需要动态运行时行为时才引入对应设计；简单任务不应为了
“能力丰富”无条件增加大型运行脚本依赖。

## 9. 跨项目数据选择

| 问题 | 首选证据 | 辅助证据 | 不应单独依赖 |
|---|---|---|---|
| `.miz` 实际成员与字段 | 当前真实任务 | pydcs、mission-maker | README 或文件名 |
| 当前类型/CLSID/停机位 | 本机 DCS/验证导出 | pydcs、Retribution | 旧快照 |
| 任务生成阶段 | 真实任务约束 | BriefingRoom、Retribution | 单个最小样例 |
| 地图投影/地理 | 本机地图数据 | pydcs、BR、GTD | 跨地图类推 |
| 运行时 AI/事件 | DCS 实测 | MOOSE、官方脚本文档 | 静态 Lua 表 |
| 战役推进 | 当前 `.cmp` + DCS 实测 | BriefingRoom、Retribution | 文件名或叙事记忆 |

## 10. 对 `.develope/reference/` 的影响

现有参考快照仍有价值，但需要严格理解：

- 它是 2026-07-24 的提取批次，不是自动同步数据库；
- Retribution 上游已经在本轮更新，旧提取不能默认等于当前 `dev`；
- pydcs 本轮提交未变化，现有校验脚本仍可检查其部分数据；
- 每个未来提取文件都应记录远端、分支、提交、DCS 版本、生成命令和覆盖范围；
- 提取事实可以进入项目，第三方源码和受版权内容不能随意复制。

## 11. 当前上游空白

六个项目合起来仍没有直接提供：

- 对本轮全部合法 Lua 数据写法安全且无损的解析器；
- 当前本机 DCS 的完整、已验证挂点兼容矩阵；
- 覆盖所有地图版本的统一机场/停机位来源；
- 对重复 ZIP 成员、旧编码、未知字段的统一策略；
- 一条已在本机 DCS 运行验证的 DCSMizzer 生成路径；
- DCSMizzer 自己的证据版本与 provenance 模型。

这些空白决定了未来 `Tools/` 应先做读取、规范化和验证基座，再做广泛生成。详细
排序见 [Docs/Tools 开发源图](2026-07-26-docs-tools-source-map.md)。
