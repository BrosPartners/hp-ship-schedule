# Zone mapping — provisional assignments

`berth_map.csv` gained a `zone` column (`lach_huyen` / `ha_nguon` /
`thuong_nguon`, blank for `external`/`foreign` rows) based on the owner's
port map. This file is a sibling markdown note rather than an in-CSV comment
block because `load_berth_map` (scraper/normalize.py) reads the file with a
plain `csv.DictReader`, which treats the first line as the header — a leading
comment block would become a bogus header or a bogus data row. Keeping notes
here leaves `load_berth_map`'s parsing contract untouched.

## Confirmed by the owner

- **Chùa Vẽ** — `ha_nguon`. The owner confirmed on 2026-08-14 that Chùa Vẽ sits
  **downstream** of the Bạch Đằng bridge. It was initially placed in
  `thuong_nguon`; correcting it moved 4,024 movements and materially changed the
  zone trend (2023 `thuong_nguon` share fell from 25.1% to 18.8%, and the 2026
  figure from 15.1% to 9.1%). No longer provisional.

## Still provisional

If the map is refined further, correct these first:

- **Đoạn Xá** — still in `thuong_nguon`, and this is now the **most likely next
  correction**: the Đoạn Xá terminal sits immediately alongside Chùa Vẽ on sông
  Cấm, so if Chùa Vẽ is downstream of the bridge, Đoạn Xá probably is too. It was
  left unchanged because the owner corrected only Chùa Vẽ explicitly, and guessing
  by adjacency is exactly the kind of inference this file exists to flag rather
  than bury. 1,321 movements — about a third of Chùa Vẽ's weight.
- **Hòn Dấu** — an outer approach anchorage, placed in `ha_nguon`. It carries
  3,810 movements but is an anchorage, so it never enters throughput
  (`throughput_rows` only counts `to_type == "berth"`); the zone assignment
  only affects the lookup-tab filter, not any chart total.
- **HHIT** and **HTIT** — assumed to be Lạch Huyện terminals based on naming
  convention; they are not labelled on the owner's map.
