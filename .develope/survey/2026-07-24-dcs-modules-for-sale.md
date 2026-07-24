# DCS 在售机型/地形联网测绘 (2026-07-24)

数据来源: digitalcombatsimulator.com 官方商店分页抓取 (planes/helicopters/terrains/modules)。

## 可飞固定翼 (含 FC / 免费)

| 模块 | 类型 | 备注 |
|------|------|------|
| MiG-29A Fulcrum | 全模拟 | 用户主力 |
| M-2000C | 全模拟 | 用户主力 |
| JF-17 Thunder | 全模拟 | 用户主力 |
| F-16C Viper | 全模拟 | 用户拥有 |
| F-15C | FC | 用户拥有 |
| F-15E | 全模拟 | |
| F/A-18C | 全模拟 | |
| F-14A/B Tomcat | 全模拟 | + F-14B(U) |
| F-4E Phantom II | 全模拟 | |
| F-5E / F-5E Remastered / F-5E FC | 全模拟/FC | 用户 F-5E FC |
| F-100D Super Sabre | 全模拟 | Early Access 2026 |
| A-10C II / A-10C / A-10A | 全模拟/FC | |
| AV-8B Night Attack | 全模拟 | |
| AJS-37 Viggen | 全模拟 | 科拉天然匹配 |
| Mirage F1 | 全模拟 | |
| MiG-21bis | 全模拟 | 用户拥有 |
| MiG-19P Farmer | 全模拟 | |
| MiG-15bis / FC | 全模拟/FC | |
| MiG-29A/S (FC) / MiG-29G | FC | 用户拥有 |
| Su-27 / Su-33 / Su-25 (FC) | FC | Su-27 用户拥有 |
| Su-25T | 免费全模拟 | 用户拥有 |
| F-86F / FC | 全模拟/FC | |
| C-130J | 全模拟 | 运输 |
| MB-339 | 全模拟 | 教练/轻攻 |
| L-39 Albatros | 全模拟 | |
| C-101EB/CC | 全模拟 | |
| Yak-52 | 全模拟 | 螺旋桨教练 |
| Christen Eagle II | 全模拟 | 特技 |
| P-51D Mustang | 全模拟 | |
| TF-51D | 免费 | 用户拥有 |
| P-47D Thunderbolt | 全模拟 | |
| Spitfire LF Mk. IX | 全模拟 | |
| Bf 109 K-4 | 全模拟 | |
| Fw 190 A-8 / D-9 | 全模拟 | |
| Mosquito FB VI | 全模拟 | |
| I-16 | 全模拟 | |
| La-7 | 全模拟 | Early Access |
| F4U-1D Corsair | 全模拟 | 太平洋 |

## 直升机

Ka-50 (BS2/BS3), AH-64D, Mi-24P, Mi-8MTV2, UH-1H, SA342, OH-58D, CH-47F

## 地形

| 地图 | 状态 |
|------|------|
| Caucasus | 免费 |
| Marianas / Marianas WWII | 免费 |
| Nevada NTTR | 付费 |
| Persian Gulf | 付费 |
| Syria | 付费 |
| The Channel | 付费 二战 |
| Normandy / Normandy 2.0 | 付费 二战 |
| South Atlantic | 付费 |
| Cold War Germany | 付费 用户优先1 |
| Sinai | 付费 用户优先2 |
| Kola | 付费 用户优先3 |
| Afghanistan (+SW/East) | 付费 |
| Iraq (+North) | 付费 |

## 其它

Supercarrier, Combined Arms, WWII Assets Pack, NS430 套件, Flaming Cliffs 2024/3

## 用户资产偏重策略

- 主力 (约一半场景主驾驶): 全模拟 MiG-29A, M-2000C, JF-17
- 次主力: MiG-21Bis, F-5E FC, Su-27, MiG-29A/G/S(FC), F-15C, Su-25T, TF-51D, F-16C
- 地图优先: 冷战德国 > 西奈 > 科拉 > 内华达 > 高加索; 其它地图仅在历史/机型天然匹配时使用
- 覆盖约束: 任一在售可飞机型/地形至少出现在一个场景


## Prompt 目录落地结果 (同日)

- `PROMPT-SAMPLE-zh.adoc` / `PROMPT-SAMPLE.adoc` 各 **144** 个 `[source,text]` 块 (114 基线 + 30 具名战役)
- 主力三机 (全模拟 MiG-29A / M-2000C / JF-17) 出现在基线 114 中 **56** 个 (49%)，全目录 144 中 **63** 个 (44%)
- 此前缺失现已补齐: TF-51D, C-130J, F-100D, Yak-52, Christen Eagle II, Spitfire, Fw 190 A-8/D-9, La-7, F4U-1D, The Channel, Marianas WWII, Iraq, WWII Assets Pack
- 二战强化: 海峡 Spitfire 格斗与轰炸机拦截; 高加索 La-7 vs Fw 190 A-8; 二战马里亚纳 F4U 1v2; Normandy/库班战役含轰炸机拦截; WWII Assets 氛围单位
- 地图优先使用: 冷战德国 / 西奈 / 科拉 明显高于其它付费图; 非拥有图仅在机型/史实匹配时出现


## Coverage pass (catalog)

Constraint: every currently sold flyable aircraft module and terrain product appears in at least one Prompt.

**Fixed in pass:**
- 《铁幕》 → full-fidelity MiG-29A + Cold War Germany (not F-5E)
- Fw 190 D-9 explicit in 《库班余火》
- Afghanistan regional (SW/East), Iraq North, Normandy 2.0 named in relevant prompts

**Naming reference (paid DCS campaigns, style only):** short shelf titles (Rising Squall, Raven One, Fangs Out, Fight or Die, Museum Relic, Outpost, Sentry Pacific, Border-type drama)—not templates to clone.
