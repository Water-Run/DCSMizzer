#!/usr/bin/env python3
"""Hard-lock campaign aircraft and maps — no player choice."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch_en(t: str) -> str:
    t = t.replace(
        "2. **Single-map single-aircraft:** **one map** and **one player aircraft** for the entire campaign; still multi-mission narrative depth.",
        "2. **Single-map single-aircraft (exactly 25):** **one map** and **one player aircraft** for the entire campaign—both **hard-locked unique** (no player choice of type or map); still multi-mission narrative depth.",
    )
    t = t.replace(
        "**One player aircraft type per act**; **never mix generations in one mission**. **Maps change by act** (cross-theatre).",
        "**One player aircraft type and one map per act** (both hard-locked in the act table—no player choice). **Never mix generations in one mission**. **Maps change by act** (cross-theatre, author-specified only).",
    )

    # G1
    t = t.replace(
        "1. **Yak-52** — act title **First Turns** / **第一课** — map **Caucasus** (or other verified prop-friendly field). Pure prop handling, pattern, spin awareness, dual instruction.\n"
        "2. **L-39** — act title **Jets!** / **喷气!** — map **Nevada** or **Caucasus**. First jet: systems, circuit, basic instruments; the word “jet” should feel like a threshold.\n"
        "3. **C-101** — act title **Something Good from the West** / **来自西方的好东西** — map **Nevada** or **Persian Gulf** training fields. Western cockpit culture, procedures, navigation discipline.\n"
        "4. **Christen Eagle II** — act title **Aerobatics** / **特技飞行** — map **Nevada** or **Caucasus**. Formation and display box, energy management, show discipline—not combat.\n"
        "5. **MB-339** — act title **Niche Toy** / **小众玩具** — map **South Atlantic** or **Marianas** coastal. Light-attack / advanced trainer edge of the syllabus; still “compliance,” not a war campaign. Optional light weapons only if verified and briefed as training loads.",
        "1. **Yak-52** — act title **First Turns** / **第一课** — map **Caucasus** (hard-locked). Pure prop handling, pattern, spin awareness, dual instruction.\n"
        "2. **L-39** — act title **Jets!** / **喷气!** — map **Nevada** (hard-locked). First jet: systems, circuit, basic instruments; the word “jet” should feel like a threshold.\n"
        "3. **C-101** — act title **Something Good from the West** / **来自西方的好东西** — map **Nevada** (hard-locked). Western cockpit culture, procedures, navigation discipline.\n"
        "4. **Christen Eagle II** — act title **Aerobatics** / **特技飞行** — map **Nevada** (hard-locked). Formation and display box, energy management, show discipline—not combat.\n"
        "5. **MB-339** — act title **Niche Toy** / **小众玩具** — map **Marianas** (hard-locked). Light-attack / advanced trainer edge of the syllabus; still “compliance,” not a war campaign. Light weapons only if verified and briefed as training loads.",
    )
    t = t.replace(
        "**Maps.** Must use **at least three** different theatres across the campaign; state the act→map table in the bible and manifest.",
        "**Maps.** Follow the hard-locked act→aircraft→map table above in the bible and manifest; **no** alternate player maps or aircraft.",
    )

    # G2
    t = t.replace(
        "1. **I-16** — **It Started Many Years Ago…** / **从很多年前开始…** — map **Caucasus** (or other verified early-war fit). Biplane/early monoplane era feel, guns, rough fields.\n"
        "2. **La-7** — **Wooden Thunder** / **木质惊雷** — map **Caucasus**. Late prop air superiority / escort; report La-7 access limits if any.\n"
        "3. **MiG-15** — **The Jet Age** / **喷气时代** — map **Caucasus** or **Nevada** stand-in. Early jet boom, guns-primary, new speeds and new mistakes.\n"
        "4. **MiG-19** — **Past the Sound Barrier** / **跨过音速** — map **Cold War Germany** approaches or **Caucasus**. Transonic/supersonic transition, raw power, limited missiles only if era-verified.\n"
        "5. **MiG-21Bis** — **Twice the Speed of Sound** / **两倍音速** — map **Cold War Germany** or **Sinai** (70s-compatible window). Delta wing, GCI tether, short legs, high drama.\n"
        "6. **MiG-29** (prefer **full-fidelity MiG-29A** when the act is “modern Fulcrum”; FC **MiG-29S/G** only if briefed as a distinct late act—do not silent-swap) — **Dnieper Swifts** / **第聂伯河雨燕** — map **Caucasus** or **Cold War Germany**. Look-down/shoot-down era, regiment pride.\n"
        "7. **Finale mission (still MiG-29 act or immediate epilogue)** — **Afterglow of the Soviets** / **苏维埃的余晖** — same theatre as act 6 or a last cross-map hop. Political twilight, last parade weather, bittersweet ending—not a meme ending.",
        "1. **I-16** — **It Started Many Years Ago…** / **从很多年前开始…** — map **Caucasus** (hard-locked). Early monoplane era feel, guns, rough fields.\n"
        "2. **La-7** — **Wooden Thunder** / **木质惊雷** — map **Caucasus** (hard-locked). Late prop air superiority / escort; report La-7 access limits if any.\n"
        "3. **MiG-15** — **The Jet Age** / **喷气时代** — map **Caucasus** (hard-locked). Early jet boom, guns-primary, new speeds and new mistakes.\n"
        "4. **MiG-19** — **Past the Sound Barrier** / **跨过音速** — map **Cold War Germany** (hard-locked). Transonic/supersonic transition, raw power, limited missiles only if era-verified.\n"
        "5. **MiG-21Bis** — **Twice the Speed of Sound** / **两倍音速** — map **Cold War Germany** (hard-locked). Delta wing, GCI tether, short legs, high drama.\n"
        "6. **full-fidelity MiG-29A** (hard-locked; do not use FC S/G) — **Dnieper Swifts** / **第聂伯河雨燕** — map **Caucasus** (hard-locked). Look-down/shoot-down era, regiment pride.\n"
        "7. **Finale (still full-fidelity MiG-29A)** — **Afterglow of the Soviets** / **苏维埃的余晖** — map **Caucasus** (hard-locked, same as act 6). Political twilight, last parade weather, bittersweet ending—not a meme ending.",
    )
    t = t.replace(
        "Cross **at least four** maps/eras as the chain demands. Fiction boundaries explicit; no real-world victory claims.",
        "Follow the hard-locked act table for maps/eras. Fiction boundaries explicit; no real-world victory claims. **No** alternate player aircraft or maps.",
    )

    # G3
    t = t.replace(
        "1. **MiG-15** — **The Jet Age** / **喷气时代** — map **Caucasus** or **Nevada** as stand-in. Guns jet basics, mass training culture.\n"
        "2. **MiG-19** — **Past the Sound Barrier** / **跨过音速** — map **Cold War Germany** fringe or **Caucasus**. Supersonic step, accidents and lessons.\n"
        "3. **MiG-21Bis** — **Twice the Speed of Sound** / **两倍音速** — map **Sinai** (70s-compatible) or **Caucasus**. Export-era point defense and GCI.\n"
        "4. **Su-27** — **The Big Thing** / **大东西** — map **Kola** or **Marianas** shore. Heavy fighter arrival—range, radar, BVR adolescence; “big” is literal and cultural.\n"
        "5. **J-11A** — **Domestic Substitute** / **国产替代** — map **Marianas** or **Caucasus**. Same class, local production/identity; do not invent non-DCS types. **J-11A** is the FC Flanker family seat bundled with **Su-27** sales—verify ID.\n"
        "6. **JF-17** — **The Electronic Age** / **电子时代** — map **Sinai**, **Nevada**, or **Persian Gulf**. Glass cockpit, datalink, precision and restraint; campaign thesis lands here.",
        "1. **MiG-15** — **The Jet Age** / **喷气时代** — map **Caucasus** (hard-locked). Guns jet basics, mass training culture.\n"
        "2. **MiG-19** — **Past the Sound Barrier** / **跨过音速** — map **Cold War Germany** (hard-locked). Supersonic step, accidents and lessons.\n"
        "3. **MiG-21Bis** — **Twice the Speed of Sound** / **两倍音速** — map **Sinai** (hard-locked, 70s-compatible window). Export-era point defense and GCI.\n"
        "4. **Su-27** — **The Big Thing** / **大东西** — map **Kola** (hard-locked). Heavy fighter arrival—range, radar, BVR adolescence; “big” is literal and cultural.\n"
        "5. **J-11A** — **Domestic Substitute** / **国产替代** — map **Marianas** (hard-locked). Same class, local production/identity; do not invent non-DCS types. **J-11A** is the FC Flanker family seat bundled with **Su-27** sales—verify ID.\n"
        "6. **JF-17** — **The Electronic Age** / **电子时代** — map **Sinai** (hard-locked). Glass cockpit, datalink, precision and restraint; campaign thesis lands here.",
    )
    t = t.replace(
        "**At least four** theatres. One type per act; conversion briefs between acts.",
        "Follow the hard-locked theatres above. One type and one map per act; conversion briefs between acts. **No** alternates.",
    )

    # G4
    t = t.replace(
        "1. **P-47D** — **Thunderbolt** / **雷电** — map **Normandy** (prefer **2.0**) or **The Channel**. Escort, dive, flak, long missions.\n"
        "2. **P-51D** — **Mustang** / **野马** — map **The Channel** or **Normandy**. Escort range, cleaner air superiority feel; distinct from P-47 act.\n"
        "3. **F-86F** — **Sabre** / **佩刀** — map **Nevada** or **Caucasus** as 1950s jet war stand-in. Guns jet duels, boom-and-zoom lessons.\n"
        "4. **F-4E** — **Phantom** / **鬼怪** — map **Cold War Germany** or **Nevada**. Crew concept if supported, early BVR/semi-active character, multi-role weight.\n"
        "5. **F-15C** — **Eagle** / **鹰** — map **Nevada** or **Cold War Germany**. Air superiority pure, FC F-15C as player seat—verify module.\n"
        "6. **F-16C** — **Viper / The Sky Is Ours** / **蝰蛇·天空属于我们** — map **Nevada**, **Sinai**, or **Caucasus** modern window. Finale thesis: single-seat multirole heir.",
        "1. **P-47D** — **Thunderbolt** / **雷电** — map **Normandy** (**Normandy 2.0** hard-locked). Escort, dive, flak, long missions.\n"
        "2. **P-51D** — **Mustang** / **野马** — map **The Channel** (hard-locked). Escort range, cleaner air superiority feel; distinct from P-47 act.\n"
        "3. **F-86F** — **Sabre** / **佩刀** — map **Nevada** (hard-locked, 1950s jet-war/range tone). Guns jet duels, boom-and-zoom lessons.\n"
        "4. **F-4E** — **Phantom** / **鬼怪** — map **Cold War Germany** (hard-locked). Crew concept if supported, early BVR/semi-active character, multi-role weight.\n"
        "5. **F-15C** — **Eagle** / **鹰** — map **Nevada** (hard-locked). Air superiority pure, FC F-15C as player seat—verify module.\n"
        "6. **F-16C** — **Viper / The Sky Is Ours** / **蝰蛇·天空属于我们** — map **Nevada** (hard-locked, modern window). Finale thesis: single-seat multirole heir.",
    )
    t = t.replace(
        "**At least five** different maps across the campaign. Explicit fiction boundaries where history is only atmosphere.",
        "Follow the hard-locked multi-map table above. Explicit fiction boundaries where history is only atmosphere. **No** alternate player aircraft or maps. **No F-5** player acts.",
    )
    t = t.replace(
        "**Delivery.** Long-running model end to end; act·type·map table mandatory; validate every `.miz`. Output `output/campaigns/the-sky-belongs-to-us/`. Image Gen cover/patch/key/ending. **Do not** insert F-5E as a player act. Report unsupported; never silent substitute.",
        "**Delivery.** Long-running model end to end; act·type·map table mandatory (hard-locked only); validate every `.miz`. Output `output/campaigns/the-sky-belongs-to-us/`. Image Gen cover/patch/key/ending. **Do not** insert F-5E as a player act. Report unsupported; never silent substitute; **no player choice of aircraft or map**.",
    )

    # G5
    t = t.replace(
        "1. **F-14A** — **Fleet Defense, Day One** / **舰队防空的开端** — map **Marianas** or **Persian Gulf** with **Supercarrier** if required (verify). Early Tomcat fleet air defense, Phoenix/Sparrow-era loads as data allows.\n"
        "2. **F-14B** — **New Heart** / **发动机换心** — map **Kola** or **Marianas**. Improved engines, same soul; longer legs, harder fights.\n"
        "3. **F-14B(U)** — **Digital Tomcat** / **数字雄猫** — map **Persian Gulf** or **Marianas**. Modernized avionics era **only if installed/verified**; if B(U) unsupported, **report and stop**—do not silent-swap to B or Hornet early.\n"
        "4. **F/A-18C** — **Glorious Ending** / **辉煌的尾声** — map **Marianas** or **Persian Gulf**. Carrier transition, multirole navy present, bittersweet handoff. Era sunset—Tomcat memory in the brief, Hornet hands on the stick.",
        "1. **F-14A** — **Fleet Defense, Day One** / **舰队防空的开端** — map **Marianas** (hard-locked); **Supercarrier** required (verify). Early Tomcat fleet air defense, Phoenix/Sparrow-era loads as data allows.\n"
        "2. **F-14B** — **New Heart** / **发动机换心** — map **Kola** (hard-locked). Improved engines, same soul; longer legs, harder fights.\n"
        "3. **F-14B(U)** — **Digital Tomcat** / **数字雄猫** — map **Persian Gulf** (hard-locked). Modernized avionics **must be installed/verified**; if B(U) unsupported, **report and stop**—do not silent-swap to B or Hornet early.\n"
        "4. **F/A-18C** — **Glorious Ending** / **辉煌的尾声** — map **Marianas** (hard-locked); **Supercarrier** required (verify). Carrier transition, multirole navy present, bittersweet handoff. Era sunset—Tomcat memory in the brief, Hornet hands on the stick.",
    )
    t = t.replace(
        "**At least three** maps. Supercarrier verified when used.",
        "Follow the hard-locked three-map chain. Supercarrier verified when used. **No** alternate player aircraft, variants, or maps.",
    )

    # single-map intro
    t = t.replace(
        "**Exactly 25** long campaigns. Each locks **one player aircraft** and **one map** for the whole story (**no dual-choice** seats, no type-evolution, no map-hopping). Still multi-mission complete narratives. AI may use other era-correct types as written. Owned-type signature scenes (Fulcrum Front, Germans' MiG, Desperation, etc.) are mandatory anchors; the rest complete a best-of set.",
        "**Exactly 25** long campaigns. Each hard-locks **one player aircraft** and **one map** for the whole story (**no player choice** of type or map, no type-evolution, no map-hopping). Still multi-mission complete narratives. AI may use other era-correct types as written. Owned-type signature scenes (Fulcrum Front, Germans' MiG, Desperation, etc.) are mandatory anchors; the rest complete a best-of set.",
    )

    # single-map soft phrases
    soft = [
        (
            "Map **Normandy** only (prefer **Normandy 2.0**). WWII. Distinct from the USAF multi-map ladder.",
            "Map **Normandy** only (**Normandy 2.0** hard-locked). WWII. Distinct from the USAF multi-map ladder.",
        ),
        (
            "Map **Afghanistan** only (SW/East task area OK if stated once and kept).",
            "Map **Afghanistan** full map only (hard-locked; plan tasking inside the full map—no regional-module dual choice).",
        ),
        (
            "Player **F-5E FC** only (ROCAF-inspired livery if verified).",
            "Player **F-5E FC** only (use verified ROCAF-inspired livery; if unavailable report livery limit—do not change aircraft).",
        ),
        (
            "BFM/ACM syllabus, limited IR + guns vs aggressors (**F-5E FC** MiG-28-style liveries if verified). Optional dual-crew narrative.",
            "BFM/ACM syllabus, limited IR + guns vs aggressors (**F-5E FC** with verified MiG-28-style liveries; if livery missing report limit—keep F-5E FC). Dual-crew narrative when module supports.",
        ),
        (
            "Player **AH-64D** only (scout AI optional).",
            "Player **AH-64D** only (scout AI **OH-58D** if installed; otherwise verified scout-helo AI—player remains AH-64D).",
        ),
        (
            "Expeditionary carrier fiction; verify **Supercarrier** if used.",
            "Expeditionary carrier fiction; **Supercarrier** hard-required (verify).",
        ),
        (
            "Map **Normandy** only (prefer **Normandy 2.0**)",
            "Map **Normandy** only (**Normandy 2.0** hard-locked)",
        ),
    ]
    for a, b in soft:
        t = t.replace(a, b)

    # universal delivery reinforcement on single-map
    t = t.replace(
        "Report unsupported items; **never silent substitute**; **no alternate player aircraft or map**.",
        "Report unsupported items; **never silent substitute**; **aircraft and map are fixed—no player selection**.",
    )
    return t


def patch_zh(t: str) -> str:
    t = t.replace(
        "2. **单图单机：** 全战役**一张地图、一种玩家机型**；仍是多关叙事深度。",
        "2. **单图单机（整好 25 部）：** 全战役**一张地图、一种玩家机型**——均**写死唯一**，禁止玩家选机/选图；仍是多关叙事深度。",
    )
    t = t.replace(
        "**每幕锁定一种玩家机型**；**禁止同一任务内跨代混机**。**地图随幕更换**（跨战区）。",
        "**每幕锁定一种玩家机型与一张地图（均写死）**；**禁止同一任务内跨代混机**。**地图随幕更换**（跨战区，由作者表指定，不给玩家选图）。",
    )

    t = t.replace(
        "1. **Yak-52** — **第一课** — 地图 **Caucasus**（或其它经验证螺旋桨机场）。纯螺旋桨、起落航线、尾旋意识、双座教学。\n"
        "2. **L-39** — **喷气!** — 地图 **Nevada** 或 **Caucasus**。第一次喷气：系统、起落、基础仪表；「喷气」必须是门槛感。\n"
        "3. **C-101** — **来自西方的好东西** — 地图 **Nevada** 或 **Persian Gulf** 训练场。西方座舱文化、程序、导航纪律。\n"
        "4. **Christen Eagle II** — **特技飞行** — 地图 **Nevada** 或 **Caucasus**。编队与表演空域、能量管理、表演纪律——非作战。\n"
        "5. **MB-339** — **小众玩具** — 地图 **South Atlantic** 或 **Marianas** 近海。高级教练/轻攻边缘课目；仍是「合规」而非全面战争。武器仅在经验证且简报为训练挂载时少量出现。",
        "1. **Yak-52** — **第一课** — 地图 **Caucasus**（写死）。纯螺旋桨、起落航线、尾旋意识、双座教学。\n"
        "2. **L-39** — **喷气!** — 地图 **Nevada**（写死）。第一次喷气：系统、起落、基础仪表；「喷气」必须是门槛感。\n"
        "3. **C-101** — **来自西方的好东西** — 地图 **Nevada**（写死）。西方座舱文化、程序、导航纪律。\n"
        "4. **Christen Eagle II** — **特技飞行** — 地图 **Nevada**（写死）。编队与表演空域、能量管理、表演纪律——非作战。\n"
        "5. **MB-339** — **小众玩具** — 地图 **Marianas**（写死）。高级教练/轻攻边缘课目；仍是「合规」而非全面战争。武器仅在经验证且简报为训练挂载时少量出现。",
    )
    t = t.replace(
        "**地图。** 全战役须使用**至少三个**不同战区；圣经与 manifest 写死 幕→地图 表。",
        "**地图。** 全战役按上表写死 幕→机型→地图；圣经与 manifest 照抄该表，**禁止**备选图或备选玩家机。",
    )

    t = t.replace(
        "1. **I-16** — **从很多年前开始…** — 地图 **Caucasus**（或其它经验证早期场）。早期单翼/机炮、粗糙机场。\n"
        "2. **La-7** — **木质惊雷** — 地图 **Caucasus**。晚期螺旋桨制空/护航；La-7 权限/EA 限制须报告。\n"
        "3. **MiG-15** — **喷气时代** — 地图 **Caucasus** 或 **Nevada** 替代。早期喷气轰鸣、机炮为主、新速度新错误。\n"
        "4. **MiG-19** — **跨过音速** — 地图 **Cold War Germany** 方向或 **Caucasus**。跨音速/超音速门槛、生猛推力；导弹仅当时代数据允许。\n"
        "5. **MiG-21Bis** — **两倍音速** — 地图 **Cold War Germany** 或 **Sinai**（70 年代相容窗口）。三角翼、GCI 绳索、短腿、高戏剧性。\n"
        "6. **MiG-29**（「现代支点」幕优先 **全模拟 MiG-29A**；FC **MiG-29S/G** 仅当简报写成明确的晚期变体幕——禁止静默替换）— **第聂伯河雨燕** — 地图 **Caucasus** 或 **Cold War Germany**。下视下射时代、团队荣耀。\n"
        "7. **终章（仍属 MiG-29 幕或紧接尾声）** — **苏维埃的余晖** — 与第 6 幕同图或最后一次跨图。政治黄昏、最后阅兵天气、苦乐参半——禁止恶搞结局。",
        "1. **I-16** — **从很多年前开始…** — 地图 **Caucasus**（写死）。早期单翼/机炮、粗糙机场。\n"
        "2. **La-7** — **木质惊雷** — 地图 **Caucasus**（写死）。晚期螺旋桨制空/护航；La-7 权限/EA 限制须报告。\n"
        "3. **MiG-15** — **喷气时代** — 地图 **Caucasus**（写死）。早期喷气轰鸣、机炮为主、新速度新错误。\n"
        "4. **MiG-19** — **跨过音速** — 地图 **Cold War Germany**（写死）。跨音速/超音速门槛、生猛推力；导弹仅当时代数据允许。\n"
        "5. **MiG-21Bis** — **两倍音速** — 地图 **Cold War Germany**（写死）。三角翼、GCI 绳索、短腿、高戏剧性。\n"
        "6. **全模拟 MiG-29A**（写死；禁止改用 FC S/G）— **第聂伯河雨燕** — 地图 **Caucasus**（写死）。下视下射时代、团队荣耀。\n"
        "7. **终章（仍全模拟 MiG-29A）** — **苏维埃的余晖** — 地图 **Caucasus**（写死，与第 6 幕同图）。政治黄昏、最后阅兵天气、苦乐参半——禁止恶搞结局。",
    )
    t = t.replace(
        "按链条需要跨**至少四**图/时代。写明架空边界；不宣称真实历史胜负。",
        "严格按上表跨图；写明架空边界；不宣称真实历史胜负。**禁止**备选机型或备选地图。",
    )

    t = t.replace(
        "1. **MiG-15** — **喷气时代** — 地图 **Caucasus** 或 **Nevada** 替代。机炮喷气基础、大规模训练文化。\n"
        "2. **MiG-19** — **跨过音速** — 地图 **Cold War Germany** 边缘或 **Caucasus**。超音速台阶、事故与教训。\n"
        "3. **MiG-21Bis** — **两倍音速** — 地图 **Sinai**（70 年代相容）或 **Caucasus**。出口时代要点防御与 GCI。\n"
        "4. **Su-27** — **大东西** — 地图 **Kola** 或 **Marianas** 岸基。「大」既是机体也是时代心理；航程、雷达、BVR 青春期。\n"
        "5. **J-11A** — **国产替代** — 地图 **Marianas** 或 **Caucasus**。同级、本地身份；禁止发明非 DCS 机型。**J-11A** 为与 **Su-27** 捆绑的 FC 侧卫族座位——须核实 ID。\n"
        "6. **JF-17** — **电子时代** — 地图 **Sinai**、**Nevada** 或 **Persian Gulf**。玻璃座舱、数据链、精确与克制；战役命题在此落地。",
        "1. **MiG-15** — **喷气时代** — 地图 **Caucasus**（写死）。机炮喷气基础、大规模训练文化。\n"
        "2. **MiG-19** — **跨过音速** — 地图 **Cold War Germany**（写死）。超音速台阶、事故与教训。\n"
        "3. **MiG-21Bis** — **两倍音速** — 地图 **Sinai**（写死，70 年代相容窗口）。出口时代要点防御与 GCI。\n"
        "4. **Su-27** — **大东西** — 地图 **Kola**（写死）。「大」既是机体也是时代心理；航程、雷达、BVR 青春期。\n"
        "5. **J-11A** — **国产替代** — 地图 **Marianas**（写死）。同级、本地身份；禁止发明非 DCS 机型。**J-11A** 为与 **Su-27** 捆绑的 FC 侧卫族座位——须核实 ID。\n"
        "6. **JF-17** — **电子时代** — 地图 **Sinai**（写死）。玻璃座舱、数据链、精确与克制；战役命题在此落地。",
    )
    t = t.replace(
        "**至少四**个战区。每幕一型；幕间换装简报。",
        "严格按上表战区。每幕一型一图（写死）；幕间换装简报。**禁止**备选。",
    )

    t = t.replace(
        "1. **P-47D** — **雷电** — 地图 **Normandy**（优先 **2.0**）或 **The Channel**。护航、俯冲、高炮、长任务。\n"
        "2. **P-51D** — **野马** — 地图 **The Channel** 或 **Normandy**。航程与更干净的制空感；与 P-47 幕明显区分。\n"
        "3. **F-86F** — **佩刀** — 地图 **Nevada** 或 **Caucasus** 作 1950s 喷气战替代。机炮格斗、能量战术课。\n"
        "4. **F-4E** — **鬼怪** — 地图 **Cold War Germany** 或 **Nevada**。双座概念（模块支持时）、半主动/早期 BVR 气质、多用途重量。\n"
        "5. **F-15C** — **鹰** — 地图 **Nevada** 或 **Cold War Germany**。纯制空；玩家座 FC F-15C——核实模块。\n"
        "6. **F-16C** — **蝰蛇·天空属于我们** — 地图 **Nevada**、**Sinai** 或 **Caucasus** 现代窗口。终章命题：单座多用途继承人。",
        "1. **P-47D** — **雷电** — 地图 **Normandy**（**Normandy 2.0** 写死）。护航、俯冲、高炮、长任务。\n"
        "2. **P-51D** — **野马** — 地图 **The Channel**（写死）。航程与更干净的制空感；与 P-47 幕明显区分。\n"
        "3. **F-86F** — **佩刀** — 地图 **Nevada**（写死，1950s 喷气战/靶场气质）。机炮格斗、能量战术课。\n"
        "4. **F-4E** — **鬼怪** — 地图 **Cold War Germany**（写死）。双座概念（模块支持时）、半主动/早期 BVR 气质、多用途重量。\n"
        "5. **F-15C** — **鹰** — 地图 **Nevada**（写死）。纯制空；玩家座 FC F-15C——核实模块。\n"
        "6. **F-16C** — **蝰蛇·天空属于我们** — 地图 **Nevada**（写死，现代窗口）。终章命题：单座多用途继承人。",
    )
    t = t.replace(
        "全战役**至少五**张不同地图。历史仅作氛围处写明架空边界。",
        "全战役严格按上表地图（多图串联）。历史仅作氛围处写明架空边界。**禁止**备选机型/地图。**禁止 F-5** 玩家幕。",
    )

    t = t.replace(
        "1. **F-14A** — **舰队防空的开端** — 地图 **Marianas** 或 **Persian Gulf**，需要时 **Supercarrier**（须核实）。早期舰队防空；凤凰/麻雀时代挂载以数据为准。\n"
        "2. **F-14B** — **发动机换心** — 地图 **Kola** 或 **Marianas**。换心之后同一灵魂；更长腿、更硬仗。\n"
        "3. **F-14B(U)** — **数字雄猫** — 地图 **Persian Gulf** 或 **Marianas**。现代化航电**仅当已安装/可核实**；若不支持 B(U)，**报告并停止**——禁止静默提前换成 B 或大黄蜂。\n"
        "4. **F/A-18C** — **辉煌的尾声** — 地图 **Marianas** 或 **Persian Gulf**。舰载换装、多用途海军当下；苦乐参半的交接。时代落幕——简报里是雄猫记忆，杆上是大黄蜂。",
        "1. **F-14A** — **舰队防空的开端** — 地图 **Marianas**（写死）；**Supercarrier** 须核实并使用。早期舰队防空；凤凰/麻雀时代挂载以数据为准。\n"
        "2. **F-14B** — **发动机换心** — 地图 **Kola**（写死）。换心之后同一灵魂；更长腿、更硬仗。\n"
        "3. **F-14B(U)** — **数字雄猫** — 地图 **Persian Gulf**（写死）。现代化航电**必须已安装/可核实**；若不支持 B(U)，**报告并停止**——禁止静默提前换成 B 或大黄蜂。\n"
        "4. **F/A-18C** — **辉煌的尾声** — 地图 **Marianas**（写死）；**Supercarrier** 须核实并使用。舰载换装、多用途海军当下；苦乐参半的交接。时代落幕——简报里是雄猫记忆，杆上是大黄蜂。",
    )
    t = t.replace(
        "**至少三**张地图。使用超级航母时须核实。",
        "严格按上表三图串联。使用超级航母时须核实。**禁止**备选机型/地图/变体。",
    )

    t = t.replace(
        "**整好 25 部**长战役。每部全故事锁定 **一种玩家机型** 与 **一张地图**（**无二选一**座位、无机型演化、不跨图）。仍是多关完整叙事。AI 可按正文使用其它时代正确机型。用户机型招牌场景（支点前线、德国人的米格、绝望等）为必含锚点；其余补全最佳场景集。",
        "**整好 25 部**长战役。每部全故事 **机型唯一、地图唯一**（正文写死；**禁止**玩家选机/选图、无机型演化、不跨图）。仍是多关完整叙事。AI 可按正文使用其它时代正确机型。用户机型招牌场景为必含锚点。",
    )

    soft = [
        ("地图仅 **Normandy**（优先 **2.0**）", "地图仅 **Normandy**（**Normandy 2.0** 写死）"),
        (
            "地图仅 **Afghanistan**（可一次写死 SW/East 任务区并保持）",
            "地图仅 **Afghanistan** 全图（写死；任务区在全图内规划，不另开区域模块二选一）",
        ),
        (
            "（有则 ROCAF 风格涂装）",
            "（使用经验证 ROCAF 风格涂装；无该涂装则报告，禁止改机型）",
        ),
        (
            "（有则 **F-5E FC** MiG-28 涂装）",
            "（入侵者 **F-5E FC** 使用经验证 MiG-28 涂装；无则报告涂装限制，仍用 F-5E FC）",
        ),
        (
            "（侦察可 AI）",
            "（侦察 AI 为 **OH-58D** 若已装；未装则用经验证侦察直升机 AI，玩家仍为 AH-64D）",
        ),
        ("用超级航母须核实", "**Supercarrier** 写死使用并核实"),
        (
            "地图仅 **Normandy**（优先 2.0）",
            "地图仅 **Normandy**（**Normandy 2.0** 写死）",
        ),
    ]
    for a, b in soft:
        t = t.replace(a, b)

    t = t.replace(
        "不支持则报告；**禁止静默替换**；**禁止备选玩家机型或地图**。",
        "不支持则报告；**禁止静默替换**；**机型与地图固定——禁止玩家选择**。",
    )
    return t


def main() -> None:
    en_path = ROOT / "PROMPT-SAMPLE.adoc"
    zh_path = ROOT / "PROMPT-SAMPLE-zh.adoc"
    en_path.write_text(patch_en(en_path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    zh_path.write_text(patch_zh(zh_path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print("patched")

    for p in (en_path, zh_path):
        t = p.read_text(encoding="utf-8")
        camp = t[t.find("[[campaigns]]") :]
        soft_or = re.findall(r"map \*\*[^*]+\*\* or \*\*", camp, re.I)
        soft_zh = re.findall(r"地图 \*\*[^*]+\*\* 或", camp)
        print(p.name, "remaining map-or EN", soft_or)
        print(p.name, "remaining map-or ZH", soft_zh[:10], "count", len(soft_zh))
        # also 或 **Nevada** patterns
        soft2 = re.findall(r"\*\*[^*]+\*\* 或 \*\*[^*]+\*\*", camp)
        print(p.name, "xx 或 yy count", len(soft2), soft2[:15])


if __name__ == "__main__":
    main()
