# HCM berth map — provisional / uncertain assignments

`data/hcm/berth_map.csv` covers the 113 raw `from_position`/`to_position`
values needed to reach 60.1% of slots (223,613 total) — short of Hai
Phong's near-total coverage because HCM has ~530 distinct values against
Hai Phong's ~30, and a large share of the tail is cryptic numbered buoy
codes (`BP1`..`BP14`, `NB-01`..`NB-18`, `K1`..`K18`, `V1`/`V2`/`V4`,
`PL03`..`PL05`, `SR-xx`, `TL10`/`TL11`, `VK102`, `B.TT*`, `B.PM*`, `G16`,
`M4`, `A12`, `X51`, `S.MARIN`, `B MAR3`, `BTB4`, `PVC-MS`, `CT-SR7`,
`BTL6/8`, `GG-01`, `HL1`/`HL2`/`HL3`, `VC-SSV1`/`VC-SSV2`,
`SOWATCO-ĐT1/2/3`, `TAN.T.2`, `TTD`, `U MAR1`/`U MAR2`, `APETRO`,
`BPETRO`, `CAU CANG SO x SG-HP`, `CAU CANG 2.200 DWT`, `TRUONG AN 01`,
`CAU CANG SO 1- PETEC CM`, `K2 - XD K2`). None of these were mapped:
I could not identify their operator or exact function with confidence,
and per the owner's brief ("an honest gap beats a guess") they were left
unmapped rather than assigned a guessed cluster/type. Because unmapped
rows never get `to_type == "berth"`, leaving them unmapped is the *safe*
direction for the throughput exclusion this map exists for — the risk it
carries is understating throughput/anchorage/construction shares among the
uncovered 39.9%, not overstating them.

This file follows `data/berth_map_notes.md`'s pattern (a sibling markdown
file rather than in-CSV comments, so `load_berth_map`'s plain
`csv.DictReader` parsing stays untouched) and exists for the same reason:
on the Hai Phong side, flagging uncertain rows here is what caught two
wrong assignments (one of which inverted a chart's reading). Flag
generously; the owner reviews it.

## Flagged as uncertain — please confirm

- **BO BANG** (8,554 movements, 3.83% of slots — the single largest
  mapping decision in this file). Typed `anchorage`, cluster "Vũng Tàu
  roads", alongside `NEO VT`. I could not verify what "Bò Băng" refers to
  beyond inference from context (it behaves like a waiting/roads area
  parallel to `NEO VT` in the raw data, and does not resemble any named
  cargo terminal). If it is in fact a real quay or a different kind of
  location, its `anchorage` typing is wrong and materially changes the
  anchorage share (currently 15.79% of all slots — Bò Băng alone is 3.83
  of the 223,613, roughly a quarter of that total).

- **HL PTSC-1** through **HL PTSC-7** (regarded as PTSC-operated buoys,
  ticker `PVS`) and **VSPT-0** through **VSPT-9** (regarded as
  Vietsovpetro-operated buoys, no ticker — Vietsovpetro is an unlisted
  VN-Russia JV). Both clusters are typed `berth` on the reasoning that
  they are real, named, commercially-identifiable operators unloading
  cargo/servicing offshore fields, just via single-point mooring rather
  than a fixed quay. If the owner's throughput definition is meant to
  count only fixed-quay cargo berths, these ~9,700 combined movements
  should probably be re-typed to something excluded instead — I flagged
  `berth` here but this is a judgment call, not a confirmed fact.

- **PVGAS-1** / **PVGAS-2** → ticker `GAS` (PV GAS, HOSE-listed). Assigned
  with moderate confidence — the buoy naming makes PV GAS ownership highly
  likely, but I have not verified against a primary source that these
  specific Vũng Tàu buoys belong to PV GAS's own fleet operations
  (as opposed to a subsidiary or a shared facility).

- **PVOIL 1** / **PVOIL 2** → ticker `OIL` (PV Oil, UPCoM-listed). Same
  caveat as PV GAS above: plausible from the name, not independently
  verified.

- **CẦU CẢNG SỐ 1 - PTSC PHÚ MỸ** / **SỐ 2 - PTSC PHÚ MỸ** and **CẦU CẢNG
  CHUYÊN DUNG KHO XD PTSC (CÙ LAO TÀO)** → ticker `PVS`. Same reasoning as
  the `HL PTSC-*` buoys above — PTSC is explicit in the name, so PVS is a
  reasonable ticker, but I have not confirmed PTSC (rather than a JV
  subsidiary) is the entity actually recorded in the listed group's
  revenue.

- **MỎ BẠCH HỔ**, **MỎ ĐẠI HÙNG**, **MỎ RẠNG ĐÔNG**, **TE GIAC TRANG**,
  **RỒNG ĐÔI** — offshore oilfields, typed `anchorage` purely so they are
  excluded from throughput (there is no better-fitting `type` value for
  "a vessel visiting an offshore platform, not a port"). If the dashboard
  later wants a dedicated non-throughput category for offshore-field
  traffic distinct from anchorages/roads, these five should move there
  instead.

- **CHINFON** and **XMTL 1** — both cement-terminal names, clustered under
  "Vung Tau"/"Cai Mep" with no ticker. Chinfon Cement's better-known plant
  is in Hải Phòng; if this is the same corporate group operating a second
  facility near Cái Mép, that's plausibly right, but I have not confirmed
  it is not a name collision with an unrelated local operator.

- **BEN DAM - CD** and **CÔN ĐẢO - VŨNG TÀU** → typed `external` (Bến Đầm,
  Côn Đảo — administered separately from the HCM port authority, similar
  in spirit to Hai Phong's `external` Vietnamese-port rows). Low
  materiality (1,743 + 183 movements) but flagged since "external" here is
  a judgment about port-authority boundaries rather than a hard fact I
  looked up.

- **MO RONG** ("mở rộng" = "expansion") — typed `construction` on the
  assumption this denotes a construction/expansion works area rather than
  a specific named place. Low confidence in the exact meaning; low
  materiality (337 movements).

## Confident, not flagged

- **Cát Lái** (`C.LAI 1/2/3/4/5/7`, `CATLAI 4-5`) and **SP-ITC**
  (`SP-ITC01/02`) — Tân Cảng Sài Gòn / Hutchison-SNP JV operations,
  unlisted, no ticker guessed.
- **Cái Mép** cluster (CMIT, TCIT, SP-PSA, SSIT, Baria Serece, SITV, QT
  Thị Vải) and **Long An** (QT Long An berths 1–7) — all unlisted
  operator JVs, no ticker guessed except Gemalink (`CAI MEP
  GEMADEPT-TERMINAL LINK` → `GMD`, Gemadept, HOSE-listed — the one
  ticker in this file I'd call fully confident).
- **NEO VT** — the clear top anchorage/roads value (23,526 movements,
  10.5% of slots); not flagged, its meaning (Vũng Tàu roads) is explicit
  in the name.
- All `KV THI CONG...`, `KV TRUNG CHUYEN...`, `NV LUONG...`, `BAI DO...`,
  `BAI DO CAN GIO` rows — explicit dredging/reclamation/construction
  project names, typed `construction`.

## Type split achieved (of all 223,613 slots)

| type | slots | share |
|---|---|---|
| berth | 78,572 | 35.14% |
| anchorage | 35,313 | 15.79% |
| construction | 18,525 | 8.28% |
| external | 1,926 | 0.86% |
| foreign | 0 | 0.00% |
| unmapped | 89,277 | 39.92% |

`anchorage + construction` = **24.07%** of all slots — this is the share
that must never reach throughput. No `foreign` rows were identified in
the top values examined (HCM's raw values, unlike Hai Phong's, did not
surface any obviously-foreign-country strings in this pass); a future
mapping pass over the long tail may find some.
