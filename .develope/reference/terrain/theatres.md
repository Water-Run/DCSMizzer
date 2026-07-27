> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Theatre / map names

pydcs terrain class name vs **mission file `theatre` string** (from `mission.py` load switch).

| pydcs package | Terrain display name | miz `theatre` string | notes |
|---------------|----------------------|----------------------|-------|
| `caucasus` | `Caucasus` | `Caucasus` | 免费默认 |
| `nevada` | `Nevada` | `Nevada` | NTTR |
| `persiangulf` | `PersianGulf` | `PersianGulf` | 注意无空格 |
| `normandy` | `Normandy` | `Normandy` | Normandy 2.0 同 theatre 串需以 DCS 为准 |
| `thechannel` | `TheChannel` | `TheChannel` | 二战海峡 |
| `sinai` | `Sinai` | `SinaiMap` | miz theatre 为 SinaiMap |
| `syria` | `Syria` | `Syria` |  |
| `marianaislands` | `MarianaIslands` | `MarianaIslands` | 含 WWII 变体需查 DCS 版本 |
| `falklands` | `Falklands` | `Falklands` | South Atlantic |
| `germany` | `GermanyCW` | `GermanyCW` | 冷战德国 — 用户优先 |
| `kola` | `Kola` | `Kola` | 用户优先 |

## Airport counts in pydcs export

| theatre package | airports |
|-----------------|----------|
| `germany` | 227 |
| `syria` | 224 |
| `normandy` | 89 |
| `sinai` | 55 |
| `kola` | 36 |
| `persiangulf` | 29 |
| `falklands` | 26 |
| `caucasus` | 21 |
| `nevada` | 17 |
| `thechannel` | 12 |
| `marianaislands` | 8 |

Full airport tables: [`airports-*.md`](./) and [`../data/airports-by-theatre.json`](../data/airports-by-theatre.json).
