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

- **Đoạn Xá** — `ha_nguon`. Confirmed by the owner on 2026-08-14, immediately after
  Chùa Vẽ, as also sitting downstream of the bridge. 1,321 movements. Together with
  the Chùa Vẽ correction this took `thuong_nguon`'s 2026 share from 15.1% to 7.7%.

## Still provisional
- **Hòn Dấu** — an outer approach anchorage, placed in `ha_nguon`. It carries
  3,810 movements but is an anchorage, so it never enters throughput
  (`throughput_rows` only counts `to_type == "berth"`); the zone assignment
  only affects the lookup-tab filter, not any chart total.
- **HHIT** and **HTIT** — assumed to be Lạch Huyện terminals based on naming
  convention; they are not labelled on the owner's map.
