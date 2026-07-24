# Common air-to-air missiles (CLSID)

Source: `pydcs/dcs/weapons_data.py` (generated from DCS export).

This document lists **air-to-air missiles only**. Cluster bombs, AGMs, rockets,
and fuel tanks are excluded (see full index for those).

Curated entries: **215** unique CLSIDs.

Full weapon dump (all categories): [`../data/weapons-index.json`](../data/weapons-index.json).

## Shape

```python
WeaponAttr = {"clsid": "{GUID-or-name}", "name": "Human name", "weight": kg}
```

In mission payload pylons:

```json
{ "CLSID": "{9B25D316-0434-4954-868F-D51DB1A38DF0}", "num": 3 }
```

## Soviet / Russian AAMs

| attr | clsid | name | weight |
|------|-------|------|--------|
| `APU_13MT_with_R_13M__AA_2_Atoll_D____IR_AAM` | `{R-13M}` | APU-13MT with R-13M (AA-2 Atoll-D) - IR AAM | 143.9 |
| `APU_13MT_with_R_13M1__AA_2_Atoll_D____IR_AAM` | `{R-13M1}` | APU-13MT with R-13M1 (AA-2 Atoll-D) - IR AAM | 146.8 |
| `APU_13MT_with_R_3S__AA_2_Atoll_B____IR_AAM` | `{APU_13MT_R_3S}` | APU-13MT with R-3S (AA-2 Atoll-B) - IR AAM | 122.8 |
| `APU_13U_2_with_R_3R__AA_2_Atoll_C____Semi_Active_AAM` | `{R-3R}` | APU-13U-2 with R-3R (AA-2 Atoll-C) - Semi Active AAM | 114.14 |
| `APU_13U_2_with_R_3S__AA_2_Atoll_B____IR_AAM` | `{R-3S}` | APU-13U-2 with R-3S (AA-2 Atoll-B) - IR AAM | 106.6 |
| `APU_60_1M_with_R_60__AA_8_Aphid____IR_AAM` | `{R-60}` | APU-60-1M with R-60 (AA-8 Aphid) - IR AAM | 75 |
| `APU_60_1M_with_R_60__AA_8_Aphid____IR_AAM_` | `{APU_60_1_R_60}` | APU-60-1M with R-60 (AA-8 Aphid) - IR AAM | 75 |
| `APU_60_1M_with_R_60M__AA_8_Aphid_B____IR_AAM` | `{R-60M}` | APU-60-1M with R-60M (AA-8 Aphid-B) - IR AAM | 75.5 |
| `APU_60_1M_with_R_60M__AA_8_Aphid_B____IR_AAM_` | `{APU-60-1_R_60M}` | APU-60-1M with R-60M (AA-8 Aphid-B) - IR AAM | 75.5 |
| `APU_60_2M_with_2_x_R_60__AA_8_Aphid____IR_AAM` | `{R-60 2L}` | APU-60-2M with 2 x R-60 (AA-8 Aphid) - IR AAM | 157 |
| `APU_60_2M_with_2_x_R_60__AA_8_Aphid____IR_AAM_` | `{R-60 2R}` | APU-60-2M with 2 x R-60 (AA-8 Aphid) - IR AAM | 157 |
| `APU_60_2M_with_2_x_R_60__AA_8_Aphid____IR_AAM__` | `{APU_60_2M_R_60_L}` | APU-60-2M with 2 x R-60 (AA-8 Aphid) - IR AAM | 157 |
| `APU_60_2M_with_2_x_R_60__AA_8_Aphid____IR_AAM___` | `{APU_60_2M_R_60_R}` | APU-60-2M with 2 x R-60 (AA-8 Aphid) - IR AAM | 157 |
| `APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM` | `{R-60M 2L}` | APU-60-2M with 2 x R-60M (AA-8 Aphid-B) - IR AAM | 158 |
| `APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM_` | `{R-60M 2R}` | APU-60-2M with 2 x R-60M (AA-8 Aphid-B) - IR AAM | 158 |
| `APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM__` | `{B0DBC591-0F52-4F7D-AD7B-51E67725FB81}` | APU-60-2M with 2 x R-60M (AA-8 Aphid-B) - IR AAM | 158 |
| `APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM___` | `{275A2855-4A79-4B2D-B082-91EA2ADF4691}` | APU-60-2M with 2 x R-60M (AA-8 Aphid-B) - IR AAM | 158 |
| `R_13M__AA_2_Atoll_D____IR_AAM` | `{R_13M}` | R-13M (AA-2 Atoll-D) - IR AAM | 87.7 |
| `R_13M1__AA_2_Atoll_D____IR_AAM` | `{R_13M1}` | R-13M1 (AA-2 Atoll-D) - IR AAM | 90.6 |
| `R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range` | `{E8069896-8435-4B90-95C0-01A03AE6E400}` | R-27ER (AA-10 Alamo C) - Semi-Act Extended Range | 350 |
| `R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range_` | `{MISSILE_R-27ER_APU-470}` | R-27ER (AA-10 Alamo C) - Semi-Act Extended Range | 421 |
| `R_27ET__AA_10_Alamo_D____IR_Extended_Range` | `{B79C379A-9E87-4E50-A1EE-7F7E29C2E87A}` | R-27ET (AA-10 Alamo D) - IR Extended Range | 343 |
| `R_27ET__AA_10_Alamo_D____IR_Extended_Range_` | `{MISSILE_R-27ET_APU-470}` | R-27ET (AA-10 Alamo D) - IR Extended Range | 413 |
| `R_27R__AA_10_Alamo_A____Semi_Act_Rdr` | `{9B25D316-0434-4954-868F-D51DB1A38DF0}` | R-27R (AA-10 Alamo A) - Semi-Act Rdr | 253 |
| `R_27R__AA_10_Alamo_A____Semi_Act_Rdr_` | `{MISSILE_R-27R_APU-470}` | R-27R (AA-10 Alamo A) - Semi-Act Rdr | 323 |
| `R_27T__AA_10_Alamo_B____Infra_Red` | `{88DAC840-9F75-4531-8689-B46E64E42E53}` | R-27T (AA-10 Alamo B) - Infra Red | 254 |
| `R_27T__AA_10_Alamo_B____Infra_Red_` | `{MISSILE_R-27T_APU-470}` | R-27T (AA-10 Alamo B) - Infra Red | 324 |
| `R_33__AA_9_Amos____Semi_Act_Rdr` | `{F1243568-8EF0-49D4-9CB5-4DA90D92BC1D}` | R-33 (AA-9 Amos) - Semi-Act Rdr | 490 |
| `R_3R__AA_2_Atoll_C____Semi_Active_AAM` | `{R_3R}` | R-3R (AA-2 Atoll-C) - Semi Active AAM | 82.84 |
| `R_3S__AA_2_Atoll_B____IR_AAM` | `{R_3S}` | R-3S (AA-2 Atoll-B) - IR AAM | 75.3 |
| `R_40RD__AA_6_Acrid____Semi_Act_Rdr` | `{4EDBA993-2E34-444C-95FB-549300BF7CAF}` | R-40RD (AA-6 Acrid) - Semi-Act Rdr | 465 |
| `R_40TD__AA_6_Acrid____Infra_Red` | `{5F26DBC2-FB43-4153-92DE-6BBCE26CB0FF}` | R-40TD (AA-6 Acrid) - Infra Red | 463 |
| `R_60__AA_8_Aphid____IR_AAM` | `{R_60}` | R-60 (AA-8 Aphid) - IR AAM | 43 |
| `R_60__AA_8_Aphid____IR_AAM_` | `{MISSILE_R-60_APU-60}` | R-60 (AA-8 Aphid) - IR AAM | 75 |
| `R_60M__AA_8_Aphid_B____IR_AAM` | `{682A481F-0CB5-4693-A382-D00DD4A156D7}` | R-60M (AA-8 Aphid-B) - IR AAM | 43.5 |
| `R_60M__AA_8_Aphid_B____IR_AAM_` | `{MISSILE_R-60M_APU-60}` | R-60M (AA-8 Aphid-B) - IR AAM | 75.5 |
| `R_73__AA_11_Archer____Infra_Red` | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` | R-73 (AA-11 Archer) - Infra Red | 110 |
| `R_73__AA_11_Archer____Infra_Red_` | `{CBC29BFE-3D24-4C64-B81D-941239D12249}` | R-73 (AA-11 Archer) - Infra Red | 110 |
| `R_73__AA_11_Archer____Infra_Red__` | `{MISSILE_R-73_APU-73}` | R-73 (AA-11 Archer) - Infra Red | 161 |
| `R_77__AA_12_Adder____Active_Rdr` | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FE9}` | R-77 (AA-12 Adder) - Active Rdr | 175 |
| `R_77__AA_12_Adder____Active_Rdr_` | `{B4C01D60-A8A3-4237-BD72-CA7655BC0FEC}` | R-77 (AA-12 Adder) - Active Rdr | 250 |

## US / NATO AAMs (AIM family)

| attr | clsid | name | weight |
|------|-------|------|--------|
| `_1x_AIM_9B_Sidewinder_IR_AAM` | `{GD_F100_AIM-9B_x1_Right}` | 1x AIM-9B Sidewinder IR AAM | 156.39 |
| `_1x_AIM_9B_Sidewinder_IR_AAM_` | `{GD_F100_AIM-9B_x1_Left}` | 1x AIM-9B Sidewinder IR AAM | 156.39 |
| `_1x_AIM_9E_Sidewinder_IR_AAM` | `{GD_F100_AIM-9E_x1_Right}` | 1x AIM-9E Sidewinder IR AAM | 158.43 |
| `_1x_AIM_9E_Sidewinder_IR_AAM_` | `{GD_F100_AIM-9E_x1_Left}` | 1x AIM-9E Sidewinder IR AAM | 158.43 |
| `_1x_AIM_9J_Sidewinder_IR_AAM` | `{GD_F100_AIM-9J_x1_Right}` | 1x AIM-9J Sidewinder IR AAM | 158.93 |
| `_1x_AIM_9J_Sidewinder_IR_AAM_` | `{GD_F100_AIM-9J_x1_Left}` | 1x AIM-9J Sidewinder IR AAM | 158.93 |
| `_1x_AIM_9L_Sidewinder_IR_AAM__hypothetical_for_90s_` | `{GD_F100_AIM-9L_x1_Right}` | 1x AIM-9L Sidewinder IR AAM (hypothetical for 90s) | 167.73 |
| `_1x_AIM_9L_Sidewinder_IR_AAM__hypothetical_for_90s__` | `{GD_F100_AIM-9L_x1_Left}` | 1x AIM-9L Sidewinder IR AAM (hypothetical for 90s) | 167.73 |
| `_1x_AIM_9M_Sidewinder_IR_AAM__hypothetical_for_90s_` | `{GD_F100_AIM-9_x1_Right}` | 1x AIM-9M Sidewinder IR AAM (hypothetical for 90s) | 167.73 |
| `_1x_AIM_9M_Sidewinder_IR_AAM__hypothetical_for_90s__` | `{GD_F100_AIM-9_x1_Left}` | 1x AIM-9M Sidewinder IR AAM (hypothetical for 90s) | 167.73 |
| `_1x_AIM_9P_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P_x1_Right}` | 1x AIM-9P Sidewinder IR AAM (backwards compatible) | 156.84 |
| `_1x_AIM_9P_Sidewinder_IR_AAM__backwards_compatible__` | `{GD_F100_AIM-9P_x1_Left}` | 1x AIM-9P Sidewinder IR AAM (backwards compatible) | 156.84 |
| `_1x_AIM_9P3_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P3_x1_Right}` | 1x AIM-9P3 Sidewinder IR AAM (backwards compatible) | 162.7 |
| `_1x_AIM_9P3_Sidewinder_IR_AAM__backwards_compatible__` | `{GD_F100_AIM-9P3_x1_Left}` | 1x AIM-9P3 Sidewinder IR AAM (backwards compatible) | 162.7 |
| `_1x_AIM_9P5_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P5_x1_Right}` | 1x AIM-9P5 Sidewinder IR AAM (backwards compatible) | 162.7 |
| `_1x_AIM_9P5_Sidewinder_IR_AAM__backwards_compatible__` | `{GD_F100_AIM-9P5_x1_Left}` | 1x AIM-9P5 Sidewinder IR AAM (backwards compatible) | 162.7 |
| `_1x_Captive_AIM_9M_for_ACM` | `{GD_F100_CATM-9M_x1_Right}` | 1x Captive AIM-9M for ACM | 167.73 |
| `_1x_Captive_AIM_9M_for_ACM_` | `{GD_F100_CATM-9M_x1_Left}` | 1x Captive AIM-9M for ACM | 167.73 |
| `_2x_AIM_9B_Sidewinder_IR_AAM` | `{GD_F100_AIM-9B_x2}` | 2x AIM-9B Sidewinder IR AAM | 230.78 |
| `_2x_AIM_9E_Sidewinder_IR_AAM` | `{GD_F100_AIM-9E_x2}` | 2x AIM-9E Sidewinder IR AAM | 234.86 |
| `_2x_AIM_9J_Sidewinder_IR_AAM` | `{GD_F100_AIM-9J_x2}` | 2x AIM-9J Sidewinder IR AAM | 235.86 |
| `_2x_AIM_9L` | `{LAU-7_AIM-9L_Left}` | 2x AIM-9L | 100.5 |
| `_2x_AIM_9L_` | `{LAU-7_AIM-9L_Right}` | 2x AIM-9L | 100.5 |
| `_2x_AIM_9L_Sidewinder_IR_AAM__hypothetical_for_90s_` | `{GD_F100_AIM-9L_x2}` | 2x AIM-9L Sidewinder IR AAM (hypothetical for 90s) | 253.46 |
| `_2x_AIM_9M` | `{LAU-7_AIM-9M_Left}` | 2x AIM-9M | 101.64 |
| `_2x_AIM_9M_` | `{LAU-7_AIM-9M_Right}` | 2x AIM-9M | 101.64 |
| `_2x_AIM_9M_Sidewinder_IR_AAM__hypothetical_for_90s_` | `{GD_F100_AIM-9_x2}` | 2x AIM-9M Sidewinder IR AAM (hypothetical for 90s) | 253.46 |
| `_2x_AIM_9P_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P_x2}` | 2x AIM-9P Sidewinder IR AAM (backwards compatible) | 231.68 |
| `_2x_AIM_9P3_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P3_x2}` | 2x AIM-9P3 Sidewinder IR AAM (backwards compatible) | 243.4 |
| `_2x_AIM_9P5_Sidewinder_IR_AAM__backwards_compatible_` | `{GD_F100_AIM-9P5_x2}` | 2x AIM-9P5 Sidewinder IR AAM (backwards compatible) | 243.4 |
| `_2x_Captive_AIM_9M_for_ACM` | `{GD_F100_CATM-9M_x2}` | 2x Captive AIM-9M for ACM | 253.46 |
| `AIM_120B_AMRAAM___Active_Radar_AAM` | `{C8E06185-7CD6-4C90-959F-044679E90751}` | AIM-120B AMRAAM - Active Radar AAM | 157.85 |
| `AIM_120C_AMRAAM___Active_Radar_AAM` | `{40EF17B7-F508-45de-8566-6FFECC0C1AB8}` | AIM-120C AMRAAM - Active Radar AAM | 161.48 |
| `AIM_54A_Mk47` | `{AIM_54A_Mk47}` | AIM-54A-Mk47 | 444 |
| `AIM_54A_Mk47_` | `{SHOULDER AIM_54A_Mk47 L}` | AIM-54A-Mk47 | 489.36 |
| `AIM_54A_Mk47__` | `{SHOULDER AIM_54A_Mk47 R}` | AIM-54A-Mk47 | 489.36 |
| `AIM_54A_Mk60` | `{AIM_54A_Mk60}` | AIM-54A-Mk60 | 444 |
| `AIM_54A_Mk60_` | `{SHOULDER AIM_54A_Mk60 L}` | AIM-54A-Mk60 | 489.36 |
| `AIM_54A_Mk60__` | `{SHOULDER AIM_54A_Mk60 R}` | AIM-54A-Mk60 | 489.36 |
| `AIM_54C_Mk47` | `{AIM_54C_Mk47}` | AIM-54C-Mk47 | 454 |
| `AIM_54C_Mk47_` | `{SHOULDER AIM_54C_Mk47 L}` | AIM-54C-Mk47 | 499.36 |
| `AIM_54C_Mk47__` | `{SHOULDER AIM_54C_Mk47 R}` | AIM-54C-Mk47 | 499.36 |
| `AIM_54C_Mk47_Phoenix_IN__Semi_Active_Radar` | `{7575BA0B-7294-4844-857B-031A144B2595}` | AIM-54C-Mk47 Phoenix IN & Semi-Active Radar | 463 |
| `AIM_54C_Mk60` | `{AIM_54C_Mk60}` | AIM-54C-Mk60 | 454 |
| `AIM_54C_Mk60_` | `{SHOULDER AIM_54C_Mk60 L}` | AIM-54C-Mk60 | 499.36 |
| `AIM_54C_Mk60__` | `{SHOULDER AIM_54C_Mk60 R}` | AIM-54C-Mk60 | 499.36 |
| `AIM_7E` | `{SHOULDER AIM-7E}` | AIM-7E | 284.4 |
| `AIM_7E_` | `{BELLY AIM-7E}` | AIM-7E | 230 |
| `AIM_7E_Sparrow_Semi_Active_Radar` | `{AIM-7E}` | AIM-7E Sparrow Semi-Active Radar | 206.4 |
| `AIM_7E_Sparrow_Semi_Active_Radar_` | `{HB_F4E_AIM-7E}` | AIM-7E Sparrow Semi-Active Radar | 230 |
| `AIM_7E_2_Sparrow_Semi_Active_Radar` | `{AIM-7E-2}` | AIM-7E-2 Sparrow Semi-Active Radar | 194 |
| `AIM_7E_2_Sparrow_Semi_Active_Radar_` | `{HB_F4E_AIM-7E-2}` | AIM-7E-2 Sparrow Semi-Active Radar | 230 |
| `AIM_7F` | `{HB_F4E_AIM-7F}` | AIM-7F | 230 |
| `AIM_7F_` | `{SHOULDER AIM-7F}` | AIM-7F | 284.4 |
| `AIM_7F__` | `{BELLY AIM-7F}` | AIM-7F | 230 |
| `AIM_7F_Sparrow_Semi_Active_Radar` | `{AIM-7F}` | AIM-7F Sparrow Semi-Active Radar | 231 |
| `AIM_7M` | `{HB_F4E_AIM-7M}` | AIM-7M | 230 |
| `AIM_7M_` | `{SHOULDER AIM-7M}` | AIM-7M | 284.4 |
| `AIM_7M__` | `{BELLY AIM-7M}` | AIM-7M | 230 |
| `AIM_7M_Sparrow_Semi_Active_Radar` | `{8D399DDA-FF81-4F14-904D-099B34FE7918}` | AIM-7M Sparrow Semi-Active Radar | 231.1 |
| `AIM_7MH` | `{SHOULDER AIM-7MH}` | AIM-7MH | 284.4 |
| `AIM_7MH_` | `{BELLY AIM-7MH}` | AIM-7MH | 230 |
| `AIM_7MH_Sparrow_Semi_Active_Radar` | `{AIM-7H}` | AIM-7MH Sparrow Semi-Active Radar | 231 |
| `AIM_7P` | `{SHOULDER AIM-7P}` | AIM-7P | 284.4 |
| `AIM_7P_` | `{BELLY AIM-7P}` | AIM-7P | 230 |
| `AIM_7P_Sparrow_Semi_Active_Radar` | `{AIM-7P}` | AIM-7P Sparrow Semi-Active Radar | 231 |
| `AIM_9B_Sidewinder_IR_AAM` | `{AIM-9B}` | AIM-9B Sidewinder IR AAM | 74.39 |
| `AIM_9E_Sidewinder_IR_AAM` | `{AIM-9E}` | AIM-9E Sidewinder IR AAM | 76.43 |
| `AIM_9J_Sidewinder_IR_AAM` | `{AIM-9J}` | AIM-9J Sidewinder IR AAM | 76.93 |
| `AIM_9JULI_Sidewinder_IR_AAM` | `{AIM-9JULI}` | AIM-9JULI Sidewinder IR AAM | 82.3 |
| `AIM_9L_Sidewinder_IR_AAM` | `{AIM-9L}` | AIM-9L Sidewinder IR AAM | 85.73 |
| `AIM_9M` | `{AIM-9M}` | AIM-9M | 86.64 |
| `AIM_9M_Sidewinder_IR_AAM` | `{6CEB49FC-DED8-4DED-B053-E1F033FF72D3}` | AIM-9M Sidewinder IR AAM | 85.73 |
| `AIM_9P_Sidewinder_IR_AAM` | `{9BFD8C90-F7AE-4e90-833B-BFD0CED0E536}` | AIM-9P Sidewinder IR AAM | 74.84 |
| `AIM_9P3_Sidewinder_IR_AAM` | `{AIM-9P3}` | AIM-9P3 Sidewinder IR AAM | 80.7 |
| `AIM_9P5_Sidewinder_IR_AAM` | `{AIM-9P5}` | AIM-9P5 Sidewinder IR AAM | 80.7 |
| `AIM_9X_Sidewinder_IR_AAM` | `{5CE2FF2A-645A-4197-B48D-8720AC69394F}` | AIM-9X Sidewinder IR AAM | 84.46 |
| `CATM_9M` | `CATM-9M` | Captive AIM-9M for ACM | 85.73 |
| `LAU_105_1_AIM_9L_L` | `LAU-105_1*AIM-9L_L` | LAU-105 with 1 x AIM-9L Sidewinder IR AAM | 291.73 |
| `LAU_105_1_AIM_9L_R` | `LAU-105_1*AIM-9L_R` | LAU-105 with 1 x AIM-9L Sidewinder IR AAM | 291.73 |
| `LAU_105_1_AIM_9M_L` | `LAU-105_1*AIM-9M_L` | LAU-105 with 1 x AIM-9M Sidewinder IR AAM | 291.73 |
| `LAU_105_1_AIM_9M_R` | `LAU-105_1*AIM-9M_R` | LAU-105 with 1 x AIM-9M Sidewinder IR AAM | 291.73 |
| `LAU_105_1_CATM_9M_L` | `LAU-105_1*CATM-9M_L` | LAU-105 with 1 x Captive AIM-9M for ACM | 291.73 |
| `LAU_105_1_CATM_9M_R` | `LAU-105_1*CATM-9M_R` | LAU-105 with 1 x Captive AIM-9M for ACM | 291.73 |
| `LAU_105_2_AIM_9L` | `LAU-105_2*AIM-9L` | LAU-105 with 2 x AIM-9L Sidewinder IR AAM | 377.46 |
| `LAU_105_with_2_x_AIM_9M_Sidewinder_IR_AAM` | `{DB434044-F5D0-4F1F-9BA9-B73027E18DD3}` | LAU-105 with 2 x AIM-9M Sidewinder IR AAM | 377.46 |
| `LAU_105_with_2_x_AIM_9P_Sidewinder_IR_AAM` | `{3C0745ED-8B0B-42eb-B907-5BD5C1717447}` | LAU-105 with 2 x AIM-9P Sidewinder IR AAM | 355.68 |
| `LAU_105_2_AIM_9P3` | `LAU-105_2*AIM-9P3` | LAU-105 with 2 x AIM-9P3 Sidewinder IR AAM | 367.4 |
| `LAU_105_2_AIM_9P5` | `LAU-105_2*AIM-9P5` | LAU-105 with 2 x AIM-9P5 Sidewinder IR AAM | 367.4 |
| `LAU_105_2_CATM_9M` | `LAU-105_2*CATM-9M` | LAU-105 with 2 x Captive AIM-9M for ACM | 377.46 |
| `LAU_115_with_1_x_LAU_127_AIM_120B_AMRAAM___Active_Radar_AAM` | `{LAU-115 - AIM-120B}` | LAU-115 with 1 x LAU-127 AIM-120B AMRAAM - Active Radar AAM | 302.85 |
| `LAU_115_with_1_x_LAU_127_AIM_120B_AMRAAM___Active_Radar_AAM_` | `{LAU-115 - AIM-120B_R}` | LAU-115 with 1 x LAU-127 AIM-120B AMRAAM - Active Radar AAM | 302.85 |
| `LAU_115_with_1_x_LAU_127_AIM_120C_AMRAAM___Active_Radar_AAM` | `{LAU-115 - AIM-120C}` | LAU-115 with 1 x LAU-127 AIM-120C AMRAAM - Active Radar AAM | 306.48 |
| `LAU_115_with_1_x_LAU_127_AIM_120C_AMRAAM___Active_Radar_AAM_` | `{LAU-115 - AIM-120C_R}` | LAU-115 with 1 x LAU-127 AIM-120C AMRAAM - Active Radar AAM | 306.48 |
| `LAU_115_LAU_127_AIM_9L` | `LAU-115_LAU-127_AIM-9L` | LAU-115 with 1 x LAU-127 AIM-9L Sidewinder IR AAM | 230.73 |
| `LAU_115_LAU_127_AIM_9L_R` | `LAU-115_LAU-127_AIM-9L_R` | LAU-115 with 1 x LAU-127 AIM-9L Sidewinder IR AAM | 230.73 |
| `LAU_115_LAU_127_AIM_9M` | `LAU-115_LAU-127_AIM-9M` | LAU-115 with 1 x LAU-127 AIM-9M Sidewinder IR AAM | 230.73 |
| `LAU_115_LAU_127_AIM_9M_R` | `LAU-115_LAU-127_AIM-9M_R` | LAU-115 with 1 x LAU-127 AIM-9M Sidewinder IR AAM | 230.73 |
| `LAU_115_LAU_127_AIM_9X` | `LAU-115_LAU-127_AIM-9X` | LAU-115 with 1 x LAU-127 AIM-9X Sidewinder IR AAM | 229.46 |
| `LAU_115_LAU_127_AIM_9X_R` | `LAU-115_LAU-127_AIM-9X_R` | LAU-115 with 1 x LAU-127 AIM-9X Sidewinder IR AAM | 229.46 |
| `LAU_115_LAU_127_CATM_9M` | `LAU-115_LAU-127_CATM-9M` | LAU-115 with 1 x LAU-127 Captive AIM-9M for ACM | 230.73 |
| `LAU_115_LAU_127_CATM_9M_R` | `LAU-115_LAU-127_CATM-9M_R` | LAU-115 with 1 x LAU-127 Captive AIM-9M for ACM | 230.73 |
| `LAU_115_2_LAU_127_AIM_120B` | `LAU-115_2*LAU-127_AIM-120B` | LAU-115 with 2 x LAU-127 AIM-120B AMRAAM - Active Radar AAM | 460.7 |
| `LAU_115_2_LAU_127_AIM_120C` | `LAU-115_2*LAU-127_AIM-120C` | LAU-115 with 2 x LAU-127 AIM-120C AMRAAM - Active Radar AAM | 467.96 |
| `LAU_115_2_LAU_127_AIM_9L` | `LAU-115_2*LAU-127_AIM-9L` | LAU-115 with 2 x LAU-127 AIM-9L Sidewinder IR AAM | 316.46 |
| `LAU_115_2_LAU_127_AIM_9M` | `LAU-115_2*LAU-127_AIM-9M` | LAU-115 with 2 x LAU-127 AIM-9M Sidewinder IR AAM | 316.46 |
| `LAU_115_2_LAU_127_AIM_9X` | `LAU-115_2*LAU-127_AIM-9X` | LAU-115 with 2 x LAU-127 AIM-9X Sidewinder IR AAM | 313.92 |
| `LAU_115_2_LAU_127_CATM_9M` | `LAU-115_2*LAU-127_CATM-9M` | LAU-115 with 2 x LAU-127 Captive AIM-9M for ACM | 316.46 |
| `LAU_115C_with_AIM_7E_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7E}` | LAU-115C with AIM-7E Sparrow Semi-Active Radar | 260.8 |
| `LAU_115C_with_AIM_7E_2_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7E-2}` | LAU-115C with AIM-7E-2 Sparrow Semi-Active Radar | 248.4 |
| `LAU_115C_with_AIM_7F_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7F}` | LAU-115C with AIM-7F Sparrow Semi-Active Radar | 285.4 |
| `LAU_115C_with_AIM_7M_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7M}` | LAU-115C with AIM-7M Sparrow Semi-Active Radar | 285.5 |
| `LAU_115C_with_AIM_7MH_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7H}` | LAU-115C with AIM-7MH Sparrow Semi-Active Radar | 285.4 |
| `LAU_115C_with_AIM_7P_Sparrow_Semi_Active_Radar` | `{LAU-115 - AIM-7P}` | LAU-115C with AIM-7P Sparrow Semi-Active Radar | 285.4 |
| `LAU_127_AIM_9L` | `LAU-127_AIM-9L` | LAU-127 AIM-9L Sidewinder IR AAM | 131.03 |
| `LAU_127_AIM_9M` | `LAU-127_AIM-9M` | LAU-127 AIM-9M Sidewinder IR AAM | 131.03 |
| `LAU_127_AIM_9X` | `LAU-127_AIM-9X` | LAU-127 AIM-9X Sidewinder IR AAM | 129.76 |
| `LAU_127_CATM_9M` | `LAU-127_CATM-9M` | LAU-127 Captive AIM-9M for ACM | 131.03 |
| `LAU_138_AIM_9J` | `{LAU-138 wtip - AIM-9J}` | LAU-138 AIM-9J | 76.93 |
| `LAU_138_AIM_9L` | `{LAU-138 wtip - AIM-9L}` | LAU-138 AIM-9L | 85.73 |
| `LAU_138_AIM_9M` | `{LAU-138 wtip - AIM-9M}` | LAU-138 AIM-9M | 85.73 |
| `LAU_138_AIM_9P` | `{LAU-138 wtip - AIM-9P}` | LAU-138 AIM-9P | 74.84 |
| `LAU_138_AIM_9P3` | `{LAU-138 wtip - AIM-9P3}` | LAU-138 AIM-9P3 | 80.7 |
| `LAU_138_AIM_9P5` | `{LAU-138 wtip - AIM-9P5}` | LAU-138 AIM-9P5 | 80.7 |
| `LAU_7_AIM_9J` | `{LAU-7 - AIM-9J}` | LAU-7 AIM-9J | 91.93 |
| `LAU_7_AIM_9J_` | `{LAU-7 wtip - AIM-9J}` | LAU-7 AIM-9J | 76.93 |
| `LAU_7_AIM_9L` | `{LAU-7 - AIM-9L}` | LAU-7 AIM-9L | 100.73 |
| `LAU_7_AIM_9M` | `{LAU-7 - AIM-9M}` | LAU-7 AIM-9M | 100.73 |
| `LAU_7_AIM_9P` | `{LAU-7 - AIM-9P}` | LAU-7 AIM-9P | 89.84 |
| `LAU_7_AIM_9P_` | `{LAU-7 wtip - AIM-9P}` | LAU-7 AIM-9P | 74.84 |
| `LAU_7_AIM_9P3` | `{LAU-7 - AIM-9P3}` | LAU-7 AIM-9P3 | 95.7 |
| `LAU_7_AIM_9P5` | `{LAU-7 - AIM-9P5}` | LAU-7 AIM-9P5 | 95.7 |
| `LAU_7_with_2_x_AIM_9B_Sidewinder_IR_AAM` | `{F4-2-AIM9B}` | LAU-7 with 2 x AIM-9B Sidewinder IR AAM | 178.78 |
| `LAU_7_with_2_x_AIM_9L_Sidewinder_IR_AAM` | `{F4-2-AIM9L}` | LAU-7 with 2 x AIM-9L Sidewinder IR AAM | 201.46 |
| `LAU_7_with_2_x_AIM_9M_Sidewinder_IR_AAM` | `{9DDF5297-94B9-42FC-A45E-6E316121CD85}` | LAU-7 with 2 x AIM-9M Sidewinder IR AAM | 201.46 |
| `LAU_7_with_2_x_AIM_9P_Sidewinder_IR_AAM` | `{773675AB-7C29-422f-AFD8-32844A7B7F17}` | LAU-7 with 2 x AIM-9P Sidewinder IR AAM | 179.68 |
| `LAU_7_with_2_x_AIM_9P5_Sidewinder_IR_AAM` | `{F4-2-AIM9P5}` | LAU-7 with 2 x AIM-9P5 Sidewinder IR AAM | 191.4 |
| `LAU_7_with_AIM_9B_Sidewinder_IR_AAM` | `{HB_A6E_LAU7_AIM9B}` | LAU-7 with AIM-9B Sidewinder IR AAM | 115.39 |
| `LAU_7_with_AIM_9B_Sidewinder_IR_AAM_` | `{GAR-8}` | LAU-7 with AIM-9B Sidewinder IR AAM | 115.39 |
| `LAU_7_with_AIM_9E_Sidewinder_IR_AAM` | `{AIM-9E-ON-ADAPTER}` | LAU-7 with AIM-9E Sidewinder IR AAM | 117.43 |
| `LAU_7_with_AIM_9J_Sidewinder_IR_AAM` | `{AIM-9J-ON-ADAPTER}` | LAU-7 with AIM-9J Sidewinder IR AAM | 117.93 |
| `LAU_7_with_AIM_9L_Sidewinder_IR_AAM` | `{HB_A6E_LAU7_AIM9L}` | LAU-7 with AIM-9L Sidewinder IR AAM | 126.73 |
| `LAU_7_with_AIM_9L_Sidewinder_IR_AAM_` | `{AIM-9L-ON-ADAPTER}` | LAU-7 with AIM-9L Sidewinder IR AAM | 126.55328 |
| `LAU_7_with_AIM_9M_Sidewinder_IR_AAM` | `{HB_A6E_LAU7_AIM9M}` | LAU-7 with AIM-9M Sidewinder IR AAM | 126.73 |
| `LAU_7_with_AIM_9M_Sidewinder_IR_AAM_` | `{AIM-9M-ON-ADAPTER}` | LAU-7 with AIM-9M Sidewinder IR AAM | 126.73 |
| `LAU_7_with_AIM_9P_Sidewinder_IR_AAM` | `{AIM-9P-ON-ADAPTER}` | LAU-7 with AIM-9P Sidewinder IR AAM | 115.84 |
| `LAU_7_with_AIM_9P3_Sidewinder_IR_AAM` | `{AIM-9P3-ON-ADAPTER}` | LAU-7 with AIM-9P3 Sidewinder IR AAM | 121.7 |
| `LAU_7_with_AIM_9P5_Sidewinder_IR_AAM` | `{AIM-9P5-ON-ADAPTER}` | LAU-7 with AIM-9P5 Sidewinder IR AAM | 121.7 |
| `LAU_7_with_AIM_9X_Sidewinder_IR_AAM` | `{AIM-9X-ON-ADAPTER}` | LAU-7 with AIM-9X Sidewinder IR AAM | 125.46 |
| `LAU_7_with_RB_24__AIM_9B__Sidewinder_IR_AAM` | `{Robot24}` | LAU-7 with RB-24 (AIM-9B) Sidewinder IR AAM | 115.39 |
| `LAU_7_with_RB_24J__AIM_9P3__Sidewinder_IR_AAM` | `{Robot24J}` | LAU-7 with RB-24J (AIM-9P3) Sidewinder IR AAM | 121.7 |
| `LAU_7_with_RB_74__AIM_9L__Sidewinder_IR_AAM` | `{Robot74}` | LAU-7 with RB-74 (AIM-9L) Sidewinder IR AAM | 126.73 |
| `RB_24__AIM_9B__Sidewinder_IR_AAM` | `{Rb_24}` | RB-24 (AIM-9B) Sidewinder IR AAM | 74.39 |
| `RB_24J__AIM_9P3__Sidewinder_IR_AAM` | `{Rb_24J}` | RB-24J (AIM-9P3) Sidewinder IR AAM | 80.7 |
| `RB_74__AIM_9L__Sidewinder_IR_AAM` | `{Rb_74}` | RB-74 (AIM-9L) Sidewinder IR AAM | 85.73 |

## French AAMs

| attr | clsid | name | weight |
|------|-------|------|--------|
| `MICA_IR` | `{0DA03783-61E4-40B2-8FAE-6AEE0A5C5AAE}` | MICA IR | 110 |
| `MICA_RF` | `{6D778860-7BB8-4ACB-9E95-BA772C6BBC2C}` | MICA RF | 110 |
| `Matra_Magic_II` | `{MMagicII}` | Matra Magic II | 85 |
| `Matra_Magic_II___DDM` | `{MMagicII_DDM}` | Matra Magic II / DDM | 95 |
| `Matra_Super_530D` | `{Matra_S530D}` | Matra Super 530D | 350 |
| `R550_Magic_1_IR_AAM` | `{R550_Magic_1}` | R550 Magic 1 IR AAM | 89 |
| `R550_Magic_2_IR_AAM` | `{FC23864E-3B80-48E3-9C03-4DA8B1D7497B}` | R550 Magic 2 IR AAM | 89 |

## Chinese / JF-17 AAMs

| attr | clsid | name | weight |
|------|-------|------|--------|
| `DIS_PL_12` | `DIS_PL-12` | PL-12 AAM | 199 |
| `DIS_PL_12_DUAL_L` | `DIS_PL-12_DUAL_L` | PL-12 AAM x 2 | 528 |
| `DIS_PL_12_DUAL_R` | `DIS_PL-12_DUAL_R` | PL-12 AAM x 2 | 528 |
| `DIS_PL_5EII` | `DIS_PL-5EII` | PL-5EII | 153 |
| `DIS_PL_8A` | `DIS_PL-8A` | PL-8A | 115 |
| `DIS_PL_8B` | `DIS_PL-8B` | PL-8B | 115 |
| `DIS_SD_10` | `DIS_SD-10` | SD-10A AAM | 259 |
| `DIS_SD_10_DUAL_L` | `DIS_SD-10_DUAL_L` | SD-10A AAM x 2 | 528 |
| `DIS_SD_10_DUAL_R` | `DIS_SD-10_DUAL_R` | SD-10A AAM x 2 | 528 |

## Other AAMs

| attr | clsid | name | weight |
|------|-------|------|--------|
| `_2_x_FIM_92C_Stinger` | `{CHAP_AIM92}` | 2 x FIM-92C Stinger | 47 |
| `R_24R__AA_7_Apex_SA____Semi_Act_Rdr` | `{CCF898C9-5BC7-49A4-9D1E-C3ED3D5166A1}` | R-24R (AA-7 Apex SA) - Semi-Act Rdr | 215 |
| `R_24T__AA_7_Apex_IR____Infra_Red` | `{6980735A-44CC-4BB9-A1B5-591532F1DC69}` | R-24T (AA-7 Apex IR) - Infra Red | 215 |

## Rules

1. CLSID must be allowed on the **specific aircraft pylon** (see plane class
   `PylonN` definitions in pydcs `planes.py`).
2. Some weapons have **multiple CLSID variants** (rail/adapter differences),
   e.g. R-27R with and without APU-470 style ids.
3. Era realism: late-1980s Soviet CAP should prefer R-27R/T/ER/ET + R-73, not
   R-77, unless the user/module explicitly allows it.
4. Never invent GUIDs. If missing, re-query `weapons-index.json` or upstream.

## Quick pick: MiG-29 / Su-27 era AA

| Weapon | CLSID |
|--------|-------|
| R-27R | `{9B25D316-0434-4954-868F-D51DB1A38DF0}` |
| R-27T | `{88DAC840-9F75-4531-8689-B46E64E42E53}` |
| R-27ER | `{E8069896-8435-4B90-95C0-01A03AE6E400}` |
| R-27ET | `{B79C379A-9E87-4E50-A1EE-7F7E29C2E87A}` |
| R-73 | `{FBC29BFE-3D24-4C64-B81D-941239D12249}` |

## Quick pick: M-2000C AA

| Weapon | CLSID |
|--------|-------|
| R550 Magic 2 | `{FC23864E-3B80-48E3-9C03-4DA8B1D7497B}` |
| Magic II | `{MMagicII}` |
| MICA IR | `{0DA03783-61E4-40B2-8FAE-6AEE0A5C5AAE}` |
| MICA RF | `{6D778860-7BB8-4ACB-9E95-BA772C6BBC2C}` |

## Quick pick: JF-17 AA

| Weapon | CLSID |
|--------|-------|
| SD-10A | `DIS_SD-10` |
| SD-10A x2 L/R | `DIS_SD-10_DUAL_L` / `DIS_SD-10_DUAL_R` |
| PL-5EII | `DIS_PL-5EII` |
