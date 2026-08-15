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

- **HHIT** and **HTIT** — `lach_huyen`. Confirmed by the owner on 2026-08-14 as
  Lạch Huyện berths, which is where they had been provisionally placed, so no
  figure changed. They are absent from the owner's port map; the original
  assignment was an inference from the naming convention and is now verified.
  ~2,100 movements combined.

- **Hòn Dấu** — `ha_nguon`. Confirmed by the owner on 2026-08-14 as a downstream
  anchorage, which is where it had been provisionally placed, so no figure changed.
  It carries 3,810 movements but is an `anchorage`, and `throughput_rows` counts
  only `to_type == "berth"`, so its zone never affects any chart total — it shapes
  the lookup-tab filter alone.

## Nothing is provisional

All four originally-uncertain assignments have been confirmed by the owner, and every
one of the 37 Hải Phòng locations in `berth_map.csv` now carries a zone — 17
`ha_nguon`, 14 `thuong_nguon`, 6 `lach_huyen`, no blanks.

Two of the four were wrong and were corrected (Chùa Vẽ, Đoạn Xá); two were right and
were merely unverified (HHIT/HTIT, Hòn Dấu). That ratio is the argument for keeping
this file: the Chùa Vẽ error alone inverted the investment reading of the zone trend,
and it was only caught because the assignment had been flagged as a guess rather than
presented as fact.

If a new raw berth name appears in `data/unmapped_report.csv` and gets mapped, give it
a zone at the same time — a Hải Phòng berth with a null zone would silently drop out of
the zone chart while still counting in every other total.

## Ticker corrections (2026-08-15)

The owner corrected two ticker assignments:

- **GMD** operates **Nam Đình Vũ only**. `Nam Hải` and `Nam Hải Đình Vũ` had been
  attributed to GMD and are now blank. This is not cosmetic: GMD's call count
  over the full period drops from 6,652 to 3,825, so any earlier reading of
  GMD's volume from this dashboard was overstated by ~74%.
- **HTIT** belongs to **PHP** and had no ticker. PHP rises from 6,738 to 7,494.

The derived columns are baked into the Parquet at crawl time, so a `berth_map.csv`
edit alone changes nothing in history. `python -m tools.remap_berths --apply`
rewrites them across every partition; run it after any ticker/zone/type edit, then
re-run `python -m scraper.aggregate`.
