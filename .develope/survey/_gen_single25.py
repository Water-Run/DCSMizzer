#!/usr/bin/env python3
"""Generate 25 single-map single-aircraft campaign prompts (EN+ZH)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

campaigns: list[dict] = []


def add(
    slug: str,
    en_t: str,
    zh_t: str,
    lock_en: str,
    lock_zh: str,
    story_en: str,
    story_zh: str,
    struct_en: str = "8–12 missions, 50–80 min, ~9–14 h.",
    struct_zh: str = "8–12 关，50–80 分钟，总约 9–14 小时。",
) -> None:
    campaigns.append(
        dict(
            slug=slug,
            en_t=en_t,
            zh_t=zh_t,
            lock_en=lock_en,
            lock_zh=lock_zh,
            story_en=story_en,
            story_zh=story_zh,
            struct_en=struct_en,
            struct_zh=struct_zh,
        )
    )


# --- User-required owned-type scenes ---
add(
    "fulcrum-front",
    "Fulcrum Front",
    "支点前线",
    "Player **full-fidelity MiG-29A** only. Map **Cold War Germany** only. Window **1986** (late Cold War Pact front). Fixed type, fixed map—no alternatives.",
    "玩家全程 **全模拟 MiG-29A**。地图仅 **Cold War Germany**。窗口 **1986**（冷战后期华约前线）。固定机型、固定地图——无二选一。",
    "Front-line Fulcrum regiment on inter-German corridors in 1986: GCI, VID, shadow-first ROE, then escort, airfield defense, and limited retaliation when the exercise dies. Political officers want resolve; division wants no headlines. NATO uses verified **F-4E**, **F-15C**, **M-2000C**, **F-16C** as data allows. Civil mis-ID or border breach is political failure.",
    "1986 两德走廊前线的支点团：GCI、目视识别、先影子后开火，再护航、机场防御，以及演习死亡后的有限反击。政工要姿态，师部不要头条。北约用经验证 **F-4E**、**F-15C**、**M-2000C**、**F-16C**。误伤/越境为政治失败。",
)

add(
    "viper-high-north",
    "Viper High North",
    "极北蝰蛇",
    "Player **F-16C** only. Map **Kola** only. Modern high-north crisis fiction: US/NATO Viper vs **China + Russia** with a **complete opposing fleet** presence (carriers/surface groups as verified ship types allow). Fixed type, fixed map.",
    "玩家全程 **F-16C**。地图仅 **Kola**。现代高北架空：美/北约蝰蛇对 **中俄**，对方含**完整舰队**存在（航母/水面编队以经验证舰型为准）。固定机型、固定地图。",
    "You fly CAP, SEAD escort, anti-ship support, and fleet-defense edge fights under polar weather. Red/coalition AI fields full Flanker/Fulcrum/naval AD pressure plus a coherent surface threat—not a token destroyer. Nordic/US support is thin atmosphere; the player seat stays F-16C.",
    "极地天气下 CAP、SEAD 护航、反舰支援与舰队防空边缘交战。红方/联军 AI 铺满侧卫/支点/海基防空压力与连贯水面威胁——不是象征性一艘驱逐舰。北欧/美军支援仅薄氛围；玩家座始终 F-16C。",
)

add(
    "thunder-pakistan",
    "Thunder Pakistan",
    "雷电巴基斯坦",
    "Player **JF-17** only. Map **Afghanistan** only, used as a **declared geographic stand-in** for a fictional Pakistan border war (DCS has no Pakistan terrain—state this in the brief/manifest). Fixed type, fixed map; no dual aircraft or alternate map.",
    "玩家全程 **JF-17**。地图仅 **Afghanistan**，并声明为架空巴基斯坦边境战争的**地理替代**（DCS 无巴基斯坦地形——简报/manifest 写明）。固定机型、固定地图；无第二玩家机或备选地图。",
    "Home-defense and limited counter-air/strike along a tense border: datalink, precision, ROE politics, and the pride of a lightweight fighter punched above its weight. Opposition uses verified peer types (Su/MiG/F-16 family as era allows). Fiction only—no real-world victory claims.",
    "边境紧张下的本土防空与有限反击/打击：数据链、精确武器、ROE 政治，以及轻型战斗机以小博大的自豪。对手用经验证同辈机型。纯架空——不宣称真实胜负。",
    "8–11 missions, 50–75 min, ~9–13 h.",
    "8–11 关，50–75 分钟，总约 9–13 小时。",
)

add(
    "mirage-watch",
    "Mirage Watch",
    "幻影值班",
    "Player **M-2000C** only. Map **Cold War Germany** only. **French** forward-deploy fiction **1987–1989**. Fixed type, fixed map.",
    "玩家全程 **M-2000C**。地图仅 **Cold War Germany**。**法国**前出架空 **1987–1989**。固定机型、固定地图。",
    "QRA, VID, tanker tracks, corridor CAP, and the week quiet duty becomes real. Alliance ROE and nuclear-threshold politics. German liaison characters; Pact Fulcrums as weather.",
    "紧急起飞、目视识别、加油航线、走廊 CAP，以及安静勤务变真的一周。联盟 ROE 与核门槛政治。德国联络官人物；华约支点是天气。",
)

add(
    "persian-fulcrum",
    "Persian Fulcrum",
    "波斯支点",
    "Player **full-fidelity MiG-29A** only (Iranian/coalition Fulcrum seat). Map **Persian Gulf** only. Fiction: Iran-side air war alongside **F-14**, **MiG-21**, **Mirage F1** as **friendly AI** (not player seats) against **United States Navy**. Fixed type, fixed map.",
    "玩家全程 **全模拟 MiG-29A**（伊朗/联军支点座位）。地图仅 **Persian Gulf**。架空：伊朗侧空战，友军 AI 含 **F-14**、**MiG-21**、**Mirage F1**（非玩家座）对抗 **美国海军**。固定机型、固定地图。",
    "You are one Fulcrum in a mixed Iranian package: Tomcats and Fishbeds and Mirages share the sky as allies; the enemy is carrier air and fleet AD. Civil oil traffic is sacred ROE. Verify every ally type; never invent Iran-only airframes that do not exist in data.",
    "你是混成伊朗编队里的一架支点：雄猫、鱼床与幻影作友军同空；敌人是舰载航空与舰队防空。石油民航神圣 ROE。逐型核实友军；禁止编造数据中不存在的伊朗专属机。",
)

add(
    "germans-mig",
    "The Germans' MiG",
    "德国人的米格",
    "Player **MiG-29G** only. Map **Nevada** only. Window **1992** post-reunification German Fulcrum on US ranges—**aggressor / evaluation / exchange** story (not 1986 Pact front). Fixed type, fixed map. Signature title once.",
    "玩家全程 **MiG-29G**。地图仅 **Nevada**。窗口 **1992** 统一后德国支点在美军靶场——**入侵者/评估/交流**故事（不是 1986 华约前线）。固定机型、固定地图。招牌标题仅此一处。",
    "German crews in Fulcrums learn American range culture the hard way: dissimilar COMs, safety briefs, and the odd pride of flying a Soviet jet under a German flag on Nellis-area airspace. Blue Eagles and Vipers are hosts and sparring partners. Characters matter—this is the classic Germans' MiG idea restored.",
    "德国机组开着支点在内华达吃美军靶场文化：异机种通联、安全简报，以及在 Nellis 空域挂着德国标志开苏联喷气的古怪自豪。蓝方鹰与蝰蛇是东道主与陪练。人物要立住——经典「德国人的米格」构想回归。",
)

add(
    "late-civil-war",
    "Late Civil War",
    "迟到的内战",
    "Player **MiG-29S** only (**Ukrainian** seat). Map **Caucasus** only. Window **2022** technical fiction: **Ukraine vs Russia** using Caucasus as declared stand-in geography. Wholly fictional OOBs; no real-world victory claims. Fixed type, fixed map.",
    "玩家全程 **MiG-29S**（**乌克兰**座位）。地图仅 **Caucasus**。窗口 **2022** 技术架空：**乌克兰 vs 俄罗斯**，高加索为声明的地理替代。OOB 完全架空；不宣称真实胜负。固定机型、固定地图。",
    "Same-drawing-board Fulcrums on both sides of a line. Dispersal, CAP over radars and corridors, SEAD escort, and the exhaustion of a war that arrived late and stays. Russian opposition is verified AI only—player does not switch sides.",
    "图纸同源的支点分列线两侧。疏散、雷达与走廊 CAP、SEAD 护航，以及迟到又不肯走的战争疲惫。俄方仅为经验证 AI——玩家不换边。",
)

add(
    "strait-crisis-flanker",
    "Strait Crisis",
    "海峡危机",
    "Player **Su-27** only (PLAN naval-aviation / shore heavy-fighter fiction). Map **Marianas** only. Window **1996** strait-crisis fiction. Oppose **US fleet** + **Taiwan F-5E** atmosphere as verified AI. Fixed type, fixed map.",
    "玩家全程 **Su-27**（解放军海航/岸基重歼架空）。地图仅 **Marianas**。窗口 **1996** 海峡危机架空。对手 **美军舰队** + **台湾 F-5E** 氛围（经验证 AI）。固定机型、固定地图。",
    "Long-range CAP, fleet pressure, and the politics of a crisis that must not become a world war. F-5E defenders are dangerous in visual range; US carrier air is the industrial threat. Single Su-27 seat—not J-11A.",
    "远程 CAP、对舰队施压，以及危机不得变成世界大战的政治。F-5E 守方在目视距离危险；美军舰载航空是工业级威胁。单 Su-27 座位——不是 J-11A。",
)

add(
    "iron-bird",
    "Iron Bird",
    "铁鸟",
    "Player **J-11A** only. Map **Marianas** only. Window **2010** PLAN/PLAAF shore fiction. Teammates as AI: **JF-17**, **MiG-21**, **Su-27** (not player seats). Oppose **United States**. Fixed type, fixed map.",
    "玩家全程 **J-11A**。地图仅 **Marianas**。窗口 **2010** 海空军岸基架空。友军 AI：**JF-17**、**MiG-21**、**Su-27**（非玩家座）。对手 **美国**。固定机型、固定地图。",
    "Domestic heavy fighter proving itself in a joint package: light fighters and older Fishbeds and Su-27s share the sky as AI wingmen/packages. US opposition is modern and unforgiving. Distinct from 1996 Su-27 crisis—this is 2010 iron-bird confidence.",
    "国产重歼在联合编成中自证：轻斗、老鱼床与苏-27 作 AI 僚机/编队。美军对手现代且冷酷。与 1996 苏-27 危机区分——这是 2010「铁鸟」自信。",
)

add(
    "desperation",
    "Desperation",
    "绝望",
    "Player **F-5E FC** only (ROCAF-inspired livery if verified). Map **Marianas** only. Window **2026** defender fiction: **Taiwan** against **China** with **huge material disparity**—enemy AI may field **MiG-21**, **JF-17**, **Su-27**, **H-6**/bomber atmosphere, **UAV** pressure as data allows; threats **from the sea**. Thin teammates: a few **F-16C** and **M-2000C** as AI only. Fixed type, fixed map. Independent of attacker campaigns.",
    "玩家全程 **F-5E FC**（有则 ROCAF 风格涂装）。地图仅 **Marianas**。窗口 **2026** 守方架空：**台湾**对 **中国**，**巨大实力差**——敌 AI 可含 **MiG-21**、**JF-17**、**Su-27**、**轰-6**/轰炸机氛围、**无人机**压力（以数据为准）；威胁**从海上来**。稀薄队友：少数 **F-16C** 与 **M-2000C** 仅 AI。固定机型、固定地图。与攻方战役胜负独立。",
    "Scramble, visual merge, runway survival, and the arithmetic of not enough jets. Title energy is honest despair with courage—not a power fantasy. Signature Desperation / 绝望 once.",
    "紧急起飞、目视汇合、跑道存活，以及飞机不够的算术。标题气质是诚实的绝望加勇气——不是爽文。招牌「绝望」仅此一处。",
)

add(
    "pyramid-tour",
    "Pyramid Tour",
    "金字塔之旅",
    "Player **TF-51D** only (modern retired Mustang trainer/display—not WWII P-51D combat). Map **Sinai** only. Observation/route tourism—not air war. Signature Tour title once.",
    "玩家全程 **TF-51D**（现代退役野马教练/展示——非二战作战 P-51D）。地图仅 **Sinai**。观察/航线观光——非空战。招牌「之旅」仅此一处。",
    "Canal, coast, pyramid-direction visuals within map visibility. Enemies: crosswind, haze, wrong fields. Lived-in traffic; typically <=35 active units; staggered spawns after t=0.",
    "运河、海岸、地图可视范围内金字塔方向目视点。敌人：侧风、薄尘、飞错场。空域要活；活跃单位一贯 <=35；t=0 后错峰起飞。",
    "5–7 missions, 40–60 min, ~4–7 h. Score nav/discipline, not kills.",
    "5–7 关，40–60 分钟，总约 4–7 小时。评分导航与纪律，非击落。",
)

add(
    "caucasus-frogfoot",
    "Caucasus Frogfoot",
    "高加索蛙足",
    "Player **Su-25T** only. Map **Caucasus** only. Modern/low-intensity attack fiction on home terrain. Fixed type, fixed map.",
    "玩家全程 **Su-25T**。地图仅 **Caucasus**。本土地形上的现代/低烈度对地架空。固定机型、固定地图。",
    "Valleys, weather, armor columns, and the honesty of a Frogfoot that is not a Fulcrum. SEAD only as the type can perform. Persist airframes and trucks.",
    "山谷、天气、装甲纵队，以及蛙足不是支点的诚实。SEAD 仅在机型能力内。持续机体与保障车。",
)

# --- Best-of classics to reach 25 ---
add(
    "top-gun",
    "Top Gun",
    "壮志凌云",
    "Player **F-14B** only (not A, not B(U), not Hornet). Map **Nevada** only. TOPGUN/NFWS fiction—school, not geopolitics. Fixed type, fixed map.",
    "玩家全程 **F-14B**（非 A、非 B(U)、非大黄蜂）。地图仅 **Nevada**。TOPGUN/NFWS 架空——军校气质，非地缘政治。固定机型、固定地图。",
    "BFM/ACM syllabus, limited IR + guns vs aggressors (**F-5E FC** MiG-28-style liveries if verified). Optional dual-crew narrative. Glorious school, not fleet war—distinct from the multi-map Tomcat Journey ladder.",
    "BFM/ACM 大纲，有限红外+机炮对入侵者（有则 **F-5E FC** MiG-28 涂装）。可选双座叙事。辉煌军校，非舰队战争——与跨地图《雄猫之旅》区分。",
)

add(
    "phantom-over-fulda",
    "Phantom over Fulda",
    "富尔达幽灵",
    "Player **F-4E** only. Map **Cold War Germany** only. Alt **1984–1987** NATO–WP war fiction. No anachronistic loads.",
    "玩家全程 **F-4E**。地图仅 **Cold War Germany**。架空 **1984–1987** 北约—华约开战。禁止超时代挂载。",
    "Fog before radar, terrain-following, bridges, escort, airfield attack—crew-jet weight and semi-active era weapons verified.",
    "雾先于雷达、地形跟随、桥梁、护航、打机场——双座机重量与半主动时代武器须核实。",
)

add(
    "thunder-in-the-fjords",
    "Thunder in the Fjords",
    "峡湾雷霆",
    "Player **AJS-37** only. Map **Kola** only. 1980s road-base / fjord anti-ship classic.",
    "玩家全程 **AJS-37**。地图仅 **Kola**。1980s 道路基地/峡湾反舰经典。",
    "Snow strip, preplanned routes, photo then strike, come home on fumes. Pure Viggen.",
    "雪道、预规划航路、先拍照再打、油尽返场。纯 Viggen。",
)

add(
    "channel-spitfire",
    "Channel Spitfire",
    "海峡喷火",
    "Player **Spitfire LF Mk. IX** only. Map **The Channel** only. WWII.",
    "玩家全程 **Spitfire LF Mk. IX**。地图仅 **The Channel**。二战。",
    "Convoy escort, scrambles, sweeps; Bf 109 / Fw 190 opposition; weather kills pride.",
    "护航船队、紧急起飞、扫荡；Bf 109 / Fw 190 对手；天气杀死傲气。",
)

add(
    "desert-longbow",
    "Desert Longbow",
    "沙漠长弓",
    "Player **AH-64D** only (scout AI optional). Map **Sinai** only. Modern desert scout-shooter.",
    "玩家全程 **AH-64D**（侦察可 AI）。地图仅 **Sinai**。现代沙漠侦打。",
    "See first, shoot second; anti-armor, escort, night, AD edges.",
    "先看见后开枪；反装甲、护航、夜战、防空泡边缘。",
)

add(
    "hind-valley",
    "Hind Valley",
    "雌鹿山谷",
    "Player **Mi-24P** only. Map **Afghanistan** only (SW/East task area OK if stated once and kept).",
    "玩家全程 **Mi-24P**。地图仅 **Afghanistan**（可一次写死 SW/East 任务区并保持）。",
    "Valley clearing, inserts, technicals, MANPADS atmosphere as data allows.",
    "清山谷、投送、皮卡、数据允许的 MANPADS 氛围。",
)

add(
    "island-huey",
    "Island Huey",
    "岛屿轻语",
    "Player **UH-1H** only. Map **Marianas** only. SOF/CSAR/logistics.",
    "玩家全程 **UH-1H**。地图仅 **Marianas**。特种/CSAR/后勤。",
    "Insert, extract, haul, rescue; people and airframe survival is the score.",
    "投送、撤离、吊运、救援；人与机体存活即得分。",
)

add(
    "thunderbolt-normandy",
    "Thunderbolt Normandy",
    "诺曼底雷电",
    "Player **P-47D** only. Map **Normandy** only (prefer **Normandy 2.0**). WWII. Distinct from the USAF multi-map ladder.",
    "玩家全程 **P-47D**。地图仅 **Normandy**（优先 **2.0**）。二战。与空军跨地图长梯区分。",
    "Dive, flak, trains, fighter sweeps; heavy Thunderbolt work over the beachhead belt.",
    "俯冲、高炮、火车、战斗机扫荡；滩头带上的重雷电活计。",
)

add(
    "mustang-channel",
    "Mustang Channel",
    "海峡野马",
    "Player **P-51D** only. Map **The Channel** only. WWII long-range escort fiction. Distinct from Thunderbolt Normandy and from TF-51D Pyramid Tour.",
    "玩家全程 **P-51D**。地图仅 **The Channel**。二战远程护航架空。与诺曼底雷电、金字塔之旅（TF-51D）区分。",
    "Escort bombers, sweep ahead, come home across grey water. Guns and drop tanks as verified.",
    "护航轰炸机、前方扫荡、灰色海面返航。机炮与副油箱以核实为准。",
)

add(
    "eagle-shift",
    "Eagle Shift",
    "鹰的轮班",
    "Player **F-15C** (FC) only. Map **Nevada** only. Air-superiority long story.",
    "玩家全程 **F-15C**（FC）。地图仅 **Nevada**。制空长故事。",
    "High CAP, BVR geometry, protect strikers; aggressors fill the range.",
    "高位 CAP、BVR 几何、掩护打击机；入侵者填满靶场。",
)

add(
    "spear-of-the-islands",
    "Spear of the Islands",
    "群岛之矛",
    "Player **F/A-18C** only. Map **Marianas** only. Expeditionary carrier fiction; verify **Supercarrier** if used. Distinct from Tomcat Journey finale.",
    "玩家全程 **F/A-18C**。地图仅 **Marianas**。远征航母架空；用超级航母须核实。与《雄猫之旅》终幕区分。",
    "CQ, fleet defense, SEAD, anti-ship, amphibious support—Hornet present tense, not Tomcat sunset.",
    "CQ、舰队防空、SEAD、反舰、两栖支援——大黄蜂的现在时，不是雄猫落日。",
)

add(
    "fishbed-summer",
    "Fishbed Summer",
    "鱼床之夏",
    "Player **MiG-21Bis** only. Map **Sinai** only. **1970s** window (F-4 / Mirage F1 peers).",
    "玩家全程 **MiG-21Bis**。地图仅 **Sinai**。**1970s** 窗口（F-4 / Mirage F1 同辈）。",
    "Short legs, GCI ropes, desert heat, intercept and photo escort. No modern AMRAAM wall.",
    "短腿、GCI 绳索、沙漠热、拦截与护航照相。禁止现代主动弹火墙。",
)

add(
    "sabre-morning",
    "Sabre Morning",
    "佩刀清晨",
    "Player **F-86F** only. Map **Nevada** only. 1950s guns-jet war / large exercise fiction. Distinct from the USAF multi-map ladder act.",
    "玩家全程 **F-86F**。地图仅 **Nevada**。1950s 机炮喷气战/大型演习架空。与空军跨地图长梯单幕区分。",
    "Equal-energy merges, MiG-15 opposition as AI, pure guns pride. No missiles-era cheat.",
    "等能汇合、MiG-15 作 AI 对手、纯机炮傲气。禁止导弹时代开挂。",
)

assert len(campaigns) == 25, len(campaigns)


def en_block(c: dict) -> str:
    return f"""==== {c['en_t']}

[source,text]
----
Create the long single-map single-aircraft campaign **{c['en_t']}** (Chinese **{c['zh_t']}**).

**Lock.** {c['lock_en']}

**Story.** {c['story_en']}

**Structure.** {c['struct_en']} Persist characters, airframes, and campaign state. Short hard mission titles.

**Delivery.** Long-running model end to end: Docs/Tools; verify aircraft, map, units, weapons, bases, coords; bible + OOB + state + deps; validate every `.miz`; continuity audit. Output `output/campaigns/{c['slug']}/` (missions, briefings, state, artwork, validation-reports, manifest with **mission · aircraft · map**). Image Gen cover/patch/key/ending—not chart authority. Report unsupported items; **never silent substitute**; **no alternate player aircraft or map**.
----
"""


def zh_block(c: dict) -> str:
    return f"""==== {c['zh_t']}

[source,text]
----
制作长篇单图单机战役**《{c['zh_t']}》**（English: **{c['en_t']}**）。

**锁定。** {c['lock_zh']}

**故事。** {c['story_zh']}

**结构。** {c['struct_zh']} 持续人物、机体与战役状态。短硬关名。

**交付。** 长程模型端到端：Docs/Tools；核实机型、地图、单位、武器、基地、坐标；圣经 + OOB + 状态 + 依赖；逐关验证 `.miz`；连续性审计。输出 `output/campaigns/{c['slug']}/`（missions、briefings、state、artwork、validation-reports、manifest 含 **关卡 · 机型 · 地图**）。Image Gen 封面/徽章/关键/结局——不能当航图依据。不支持则报告；**禁止静默替换**；**禁止备选玩家机型或地图**。
----
"""


EN_SEC = """[[single-map-campaigns]]
=== Single-Map Single-Aircraft Campaigns

**Exactly 25** long campaigns. Each locks **one player aircraft** and **one map** for the whole story (**no dual-choice** seats, no type-evolution, no map-hopping). Still multi-mission complete narratives. AI may use other era-correct types as written. Owned-type signature scenes (Fulcrum Front, Germans' MiG, Desperation, etc.) are mandatory anchors; the rest complete a best-of set.

""" + "\n".join(en_block(c) for c in campaigns)

ZH_SEC = """[[single-map-campaigns]]
=== 单图单机战役

**整好 25 部**长战役。每部全故事锁定 **一种玩家机型** 与 **一张地图**（**无二选一**座位、无机型演化、不跨图）。仍是多关完整叙事。AI 可按正文使用其它时代正确机型。用户机型招牌场景（支点前线、德国人的米格、绝望等）为必含锚点；其余补全最佳场景集。

""" + "\n".join(zh_block(c) for c in campaigns)


def replace_single(path: Path, new_sec: str) -> None:
    t = path.read_text(encoding="utf-8")
    i = t.find("[[single-map-campaigns]]")
    if i < 0:
        raise SystemExit(f"no single-map in {path}")
    out = t[:i] + new_sec
    if not out.endswith("\n"):
        out += "\n"
    path.write_text(out, encoding="utf-8", newline="\n")
    total = len(re.findall(r"\[source,text\]", out))
    single = len(re.findall(r"\[source,text\]", new_sec))
    print(f"{path.name}: total {total}, single {single}")


def patch_important(path: Path, old: str, new: str) -> None:
    t = path.read_text(encoding="utf-8")
    if old not in t:
        print(f"WARN IMPORTANT missing in {path.name}")
        return
    path.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print(f"IMPORTANT ok {path.name}")


def main() -> None:
    replace_single(ROOT / "PROMPT-SAMPLE.adoc", EN_SEC)
    replace_single(ROOT / "PROMPT-SAMPLE-zh.adoc", ZH_SEC)
    patch_important(
        ROOT / "PROMPT-SAMPLE.adoc",
        "2. **Single-map single-aircraft (25 campaigns):** **one map** and **one player aircraft** for the entire campaign—**no dual-choice** seats or maps; still multi-mission narrative depth.",
        "2. **Single-map single-aircraft (exactly 25):** **one map** and **one player aircraft** for the entire campaign—**no dual-choice** seats or maps; still multi-mission narrative depth. Include signature owned-type scenes (e.g. full-fidelity MiG-29A 1986 CWG, MiG-29G 1992 Nevada, F-5E Desperation).",
    )
    patch_important(
        ROOT / "PROMPT-SAMPLE-zh.adoc",
        "2. **单图单机（25 部）：** 全战役**一张地图、一种玩家机型**——**无二选一**座位或地图；仍是多关叙事深度。",
        "2. **单图单机（整好 25 部）：** 全战役**一张地图、一种玩家机型**——**无二选一**座位或地图；仍是多关叙事深度。须含用户机型招牌场景（如全模拟 MiG-29A 1986 冷战德国、MiG-29G 1992 内华达、F-5E《绝望》等）。",
    )
    en = (ROOT / "PROMPT-SAMPLE.adoc").read_text(encoding="utf-8")
    zh = (ROOT / "PROMPT-SAMPLE-zh.adoc").read_text(encoding="utf-8")
    print("blocks", len(re.findall(r"\[source,text\]", en)), len(re.findall(r"\[source,text\]", zh)))
    print("depth match", [len(m.group(1)) for m in re.finditer(r"^(={2,5}) ", en, re.M)] == [len(m.group(1)) for m in re.finditer(r"^(={2,5}) ", zh, re.M)])
    for c in campaigns:
        print(f"  {c['zh_t']} / {c['en_t']}")


if __name__ == "__main__":
    main()
