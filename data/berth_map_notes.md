# Zone mapping — provisional assignments

`berth_map.csv` gained a `zone` column (`lach_huyen` / `ha_nguon` /
`thuong_nguon`, blank for `external`/`foreign` rows) based on the owner's
port map. This file is a sibling markdown note rather than an in-CSV comment
block because `load_berth_map` (scraper/normalize.py) reads the file with a
plain `csv.DictReader`, which treats the first line as the header — a leading
comment block would become a bogus header or a bogus data row. Keeping notes
here leaves `load_berth_map`'s parsing contract untouched.

Four assignments are provisional. If the owner's map is refined, correct
these first:

- **Chùa Vẽ** and **Đoạn Xá** — placed in `thuong_nguon` (upstream of the
  Bạch Đằng bridge), but their true side of the bridge is unconfirmed from
  the source map. Chùa Vẽ matters most: it is a PHP container terminal with
  4,024 movements, so a wrong side distorts PHP's zone read materially.
- **Hòn Dấu** — an outer approach anchorage, placed in `ha_nguon`. It carries
  3,810 movements but is an anchorage, so it never enters throughput
  (`throughput_rows` only counts `to_type == "berth"`); the zone assignment
  only affects the lookup-tab filter, not any chart total.
- **HHIT** and **HTIT** — assumed to be Lạch Huyện terminals based on naming
  convention; they are not labelled on the owner's map.
