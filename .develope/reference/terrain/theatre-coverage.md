> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Theatre coverage matrix

Which surveyed upstream sources ship which theatres.

| theatre | pydcs airports | BriefingRoom airbases | Retribution pack |
|---------|----------------|----------------------|------------------|
| `Afghanistan` |  | yes | yes |
| `Caucasus` | yes | yes | yes |
| `Falklands` | yes | yes | yes |
| `GermanyCW` | yes | yes | yes |
| `Iraq` |  | yes | yes |
| `Kola` | yes | yes | yes |
| `MarianaIslands` | yes | yes | yes |
| `MarianaIslandsWWII` |  | yes |  |
| `Nevada` | yes | yes | yes |
| `Normandy` | yes | yes | yes |
| `PersianGulf` | yes | yes | yes |
| `SinaiMap` | yes | yes | yes |
| `Syria` | yes | yes | yes |
| `TheChannel` | yes | yes | yes |

**Only in BriefingRoom (not current pydcs packages):** `Afghanistan`, `Iraq`, `MarianaIslandsWWII`

**Only in Retribution (not pydcs):** `Afghanistan`, `Iraq`

## Terrain bounds (BriefingRoom land polygons bbox)

| theatre | x_min | x_max | y_min | y_max | land masses |
|---------|-------|-------|-------|-------|-------------|
| `Afghanistan` | -515095.81244063796 | 531919.4469470452 | -533191.0601088353 | 752359.0388195949 | 1 |
| `Caucasus` | -449641.50970052 | 68709.18177302 | 186708.64373018 | 974529.38360196 | 1 |
| `Falklands` | -437944.7146029398 | 348340.9590644287 | -1241404.0788546999 | 98983.50998546268 | 10 |
| `GermanyCW` | -603631.3738590116 | 699391.6629615556 | -1105279.9518088866 | -293501.9447610695 | 7 |
| `Iraq` | -949907.5302360216 | 438596.0324569051 | -499379.6510173421 | 852727.0101703247 | 14 |
| `Kola` | -314105.38280428294 | 361094.7420108244 | -562201.7103092201 | 810376.9066837725 | 2 |
| `MarianaIslands` | -28338.120766124 | 782434.75154222 | -20230.930113314 | 116979.06984124 | 14 |
| `MarianaIslandsWWII` | -28338.120766124 | 782434.75154222 | -20230.930113314 | 116979.06984124 | 14 |
| `Nevada` |  |  |  |  | 0 |
| `Normandy` | -39374.953376662 | 140923.4896737 | -172298.1924099 | -58732.9508011 | 7 |
| `PersianGulf` | -405744.85078554 | 796393.67060053 | -874339.62264155 | 374773.81800298 | 7 |
| `SinaiMap` | -449657.44783795 | 498287.23918971 | -277349.43150944 | 558629.79135177 | 2 |
| `Syria` | -494708.84061432024 | 420736.18168161437 | -430980.3856626055 | 489022.42381176783 | 2 |
| `TheChannel` | -128179.05405405 | 73820.855614974 | -114344.9197861 | 128675.67567567 | 2 |

Data: [`../data/theatre-coverage-matrix.json`](../data/theatre-coverage-matrix.json), [`../data/briefing-room-terrain-bounds.json`](../data/briefing-room-terrain-bounds.json)

Iraq/Afghanistan airport tables: `airports-br-iraq.md`, `airports-br-afghanistan.md`.
