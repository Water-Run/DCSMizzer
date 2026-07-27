> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Payload presets (Retribution customized)

Source: `dcs-retribution/resources/customized_payloads/*.lua` (**224** airframes).

Index: [`../data/retribution-customized-payloads-index.json`](../data/retribution-customized-payloads-index.json)

Priority detail: [`../data/retribution-customized-payloads-priority.json`](../data/retribution-customized-payloads-priority.json)

## Loadout shape

```json
{
  "name": "CAP",
  "tasks": [10],
  "pylons": [
    { "CLSID": "{9B25D316-0434-4954-868F-D51DB1A38DF0}", "num": 3 }
  ]
}
```

Task numbers are DCS ME task WorldIDs (e.g. CAP ≈ 11/10 depending on export — treat as Retribution labels first).

## Priority aircraft loadout names

### `A-10C II`

`AGM-65K*2,GBU-38*4,AIM-9*2,TGP,ECM`, `STRIKE`, `SEAD`, `CAP`, `CAS`, `New Payload`, `ANTISHIP`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{DB434044-F5D0-4F1F-9BA9-B73027E18DD3}` |
| 11 | `{DB434044-F5D0-4F1F-9BA9-B73027E18DD3}` |

(from loadout **CAP**)

### `AJS37`

`CAP`, `ANTISHIP`, `CAS`, `STRIKE`, `SEAD`, `Retribution OCA/Runway`, `Retribution OCA/Aircraft`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{Robot24}` |
| 2 | `{AKAN}` |
| 3 | `{Robot74}` |
| 4 | `{VIGGEN_X-TANK}` |
| 5 | `{Robot74}` |
| 6 | `{AKAN}` |
| 7 | `{Robot24}` |

(from loadout **CAP**)

### `F-14B`

`Retribution DEAD`, `CAS`, `STRIKE`, `Retribution SEAD`, `CAP`, `ANTISHIP`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{LAU-138 wtip - AIM-9M}` |
| 2 | `{SHOULDER AIM-7MH}` |
| 3 | `{F14-300gal}` |
| 4 | `{AIM_54C_Mk60}` |
| 5 | `{AIM_54C_Mk60}` |
| 6 | `{AIM_54C_Mk60}` |
| 7 | `{AIM_54C_Mk60}` |
| 8 | `{F14-300gal}` |
| 9 | `{SHOULDER AIM-7MH}` |
| 10 | `{LAU-138 wtip - AIM-9M}` |

(from loadout **CAP**)

### `F-15C`

`CAS`, `STRIKE`, `CAP`, `ANTISHIP`, `SEAD`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{6CEB49FC-DED8-4DED-B053-E1F033FF72D3}` |
| 2 | `{E1F29B21-F291-4589-9FD8-3272EEC69506}` |
| 3 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 4 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 5 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 6 | `{E1F29B21-F291-4589-9FD8-3272EEC69506}` |
| 7 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 8 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 9 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 10 | `{E1F29B21-F291-4589-9FD8-3272EEC69506}` |
| 11 | `{6CEB49FC-DED8-4DED-B053-E1F033FF72D3}` |

(from loadout **CAP**)

### `F-16C_50`

`Retribution TARCAP`, `Retribution Anti-ship`, `Retribution SEAD Escort`, `Retribution Fighter Sweep`, `Retribution SEAD Sweep`, `Retribution Strike`, `Clean`, `Retribution OCA/Runway`, `Retribution CAS`, `Retribution BARCAP`, `Retribution OCA/Aircraft`, `Retribution Escort`, `Retribution DEAD`, `Retribution BAI`, `Retribution SEAD`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 2 | `{5CE2FF2A-645A-4197-B48D-8720AC69394F}` |
| 3 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 4 | `{F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}` |
| 5 | `<CLEAN>` |
| 6 | `{F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}` |
| 7 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 8 | `{5CE2FF2A-645A-4197-B48D-8720AC69394F}` |
| 9 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 11 | `{AN_AAQ_33}` |

(from loadout **Retribution TARCAP**)

### `F-4E-45MC`

`Retribution CAS`, `Retribution DEAD`, `Retribution Strike`, `Retribution Escort`, `Retribution BARCAP`, `Retribution SEAD`, `Retribution TARCAP`, `Retribution Anti-ship`, `Retribution BAI`, `Retribution SEAD Escort`, `Retribution OCA/Aircraft`, `Retribution OCA/Runway`, `Retribution SEAD Sweep`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{F4_SARGENT_TANK_370_GAL}` |
| 2 | `{AIM-9M}` |
| 4 | `{AIM-9M}` |
| 5 | `{HB_F4E_AIM-7M}` |
| 6 | `{HB_F4E_AIM-7M}` |
| 8 | `{HB_F4E_AIM-7M}` |
| 9 | `{HB_F4E_AIM-7M}` |
| 10 | `{AIM-9M}` |
| 12 | `{AIM-9M}` |
| 13 | `{F4_SARGENT_TANK_370_GAL_R}` |
| 14 | `{HB_ALE_40_30_60}` |

(from loadout **Retribution BARCAP**)

### `F-5E-3`

`CAS`, `SEAD`, `CAP`, `STRIKE`, `ANTISHIP`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{AIM-9P5}` |
| 4 | `{PTB-150GAL}` |
| 7 | `{AIM-9P5}` |

(from loadout **CAP**)

### `FA-18C_hornet`

`Retribution DEAD`, `Retribution BARCAP`, `Retribution SEAD`, `Retribution CAS`, `Retribution Strike`, `Retribution Anti-ship`, `Retribution BAI`, `Retribution OCA/Runway`, `Retribution Ferry`, `Retribution SEAD Sweep`, `Retribution SEAD Escort`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{5CE2FF2A-645A-4197-B48D-8720AC69394F}` |
| 2 | `LAU-115_2*LAU-127_AIM-120C` |
| 3 | `{FPU_8A_FUEL_TANK}` |
| 4 | `{AN_ASQ_228}` |
| 5 | `<CLEAN>` |
| 6 | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` |
| 7 | `{FPU_8A_FUEL_TANK}` |
| 8 | `LAU-115_2*LAU-127_AIM-120C` |
| 9 | `{5CE2FF2A-645A-4197-B48D-8720AC69394F}` |

(from loadout **Retribution BARCAP**)

### `JF-17`

`ANTISHIP`, `STRIKE`, `CAP`, `RUNWAY_ATTACK`, `CAS`, `SEAD`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `DIS_PL-5EII` |
| 2 | `DIS_SD-10_DUAL_L` |
| 3 | `DIS_TANK800` |
| 4 | `DIS_SPJ_POD` |
| 5 | `DIS_TANK800` |
| 6 | `DIS_SD-10_DUAL_R` |
| 7 | `DIS_PL-5EII` |

(from loadout **CAP**)

### `Ka-50`

`Retribution CAS`, `Retribution BAI`, `Retribution DEAD`, `Retribution OCA/Aircraft`, `Retribution Escort`

### `M-2000C`

`RUNWAY_ATTACK`, `CAS`, `STRIKE`, `CAP`, `ANTISHIP`, `SEAD`, `DEAD`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{MMagicII}` |
| 2 | `{Matra_S530D}` |
| 5 | `{M2KC_RPL_522}` |
| 8 | `{Matra_S530D}` |
| 9 | `{MMagicII}` |
| 10 | `{Eclair}` |

(from loadout **CAP**)

### `MiG-21Bis`

`CAS`, `ANTISHIP`, `CAP`, `SEAD`, `STRIKE`, `DEAD`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{R-60M 2L}` |
| 2 | `{R-3R}` |
| 3 | `{PTB_490C_MIG21}` |
| 4 | `{R-3R}` |
| 5 | `{R-60M 2R}` |
| 6 | `{ASO-2}` |

(from loadout **CAP**)

### `MiG-29A`

`CAS`, `STRIKE`, `CAP`, `ANTISHIP`, `SEAD`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 2 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 3 | `{9B25D316-0434-4954-868F-D51DB1A38DF0}` |
| 4 | `{2BEC576B-CDF5-4B7F-961F-B0FA4312B841}` |
| 5 | `{9B25D316-0434-4954-868F-D51DB1A38DF0}` |
| 6 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 7 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |

(from loadout **CAP**)

### `MiG-29S`

`STRIKE`, `CAS`, `CAP`, `ANTISHIP`, `SEAD`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 2 | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FE9}` |
| 3 | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FE9}` |
| 4 | `{2BEC576B-CDF5-4B7F-961F-B0FA4312B841}` |
| 5 | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FE9}` |
| 6 | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FE9}` |
| 7 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |

(from loadout **CAP**)

### `Su-25T`

`CAS`, `STRIKE`, `CAP`, `SEAD`, `ANTISHIP`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{682A481F-0CB5-4693-A382-D00DD4A156D7}` |
| 2 | `{CBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 5 | `{E8D4652F-FD48-45B7-BA5B-2AE05BB5A9CF}` |
| 7 | `{E8D4652F-FD48-45B7-BA5B-2AE05BB5A9CF}` |
| 10 | `{CBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 11 | `{682A481F-0CB5-4693-A382-D00DD4A156D7}` |

(from loadout **CAP**)

### `Su-27`

`ANTISHIP`, `CAP`, `STRIKE`, `SEAD`, `CAS`, `Retribution OCA/Runway`

Example air-to-air-ish loadout pylons:

| num | CLSID |
|-----|-------|
| 1 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 2 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 3 | `{B79C379A-9E87-4E50-A1EE-7F7E29C2E87A}` |
| 4 | `{E8069896-8435-4B90-95C0-01A03AE6E400}` |
| 5 | `{E8069896-8435-4B90-95C0-01A03AE6E400}` |
| 6 | `{E8069896-8435-4B90-95C0-01A03AE6E400}` |
| 7 | `{E8069896-8435-4B90-95C0-01A03AE6E400}` |
| 8 | `{B79C379A-9E87-4E50-A1EE-7F7E29C2E87A}` |
| 9 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |
| 10 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |

(from loadout **CAP**)

## Agent rules

1. Prefer these presets as **starting points**; still verify CLSID vs aircraft pylon tables in pydcs.
2. Era filter: late-1980s MiG-29A CAP should not silently upgrade to R-77.
3. Empty / ferry loadouts exist on some modules — check names.
