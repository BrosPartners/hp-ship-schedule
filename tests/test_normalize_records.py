import gzip
from datetime import date, datetime
from pathlib import Path

from scraper.normalize import build_records, split_sb
from scraper.parse import parse_page

FIXTURES = Path(__file__).parent / "fixtures"
CRAWLED = datetime(2026, 8, 12, 7, 30)


def load(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def test_split_sb():
    assert split_sb("HOANG PHUC 69 (SB)") == ("HOANG PHUC 69", True)
    assert split_sb("HT SHATIAN") == ("HT SHATIAN", False)
    assert split_sb("  MACSTAR NGHI SON (SB) ") == ("MACSTAR NGHI SON", True)


def test_records_are_typed():
    rows = parse_page(load("2026-08-11_full"))
    recs = build_records(rows, CRAWLED)
    rec = next(r for r in recs
               if r["section"] == "roi_cang" and r["vessel_name"] == "HOANG PHUC 69")
    assert rec["plan_date"] == date(2026, 8, 11)
    assert rec["plan_time"] == datetime(2026, 8, 11, 0, 30)
    assert rec["is_sb"] is True
    assert rec["draft_m"] == 2.7
    assert rec["loa_m"] == 79.9
    assert rec["dwt"] == 4450
    assert rec["gt"] == 1989
    assert rec["channel_code"] == "HN"
    assert rec["from_raw"] == "CANG 128"
    assert rec["to_raw"] == "NINH BINH"
    assert rec["crawled_at"] == CRAWLED


def test_qua_luong_missing_columns_stay_none():
    recs = build_records(parse_page(load("2026-08-11_full")), CRAWLED)
    rec = next(r for r in recs
               if r["section"] == "qua_luong" and r["vessel_name"] == "SONG TIEN")
    assert rec["gt"] is None
    assert rec["tugs"] is None
    assert rec["agent"] is None
    assert rec["dwt"] == 3564


def test_row_key_is_stable_and_discriminating():
    recs = build_records(parse_page(load("2026-08-11_full")), CRAWLED)
    again = build_records(parse_page(load("2026-08-11_full")),
                          datetime(2026, 8, 13, 7, 30))
    # same movement, different crawl -> same key (crawled_at is NOT in the key)
    assert recs[0]["row_key"] == again[0]["row_key"]
    # keys discriminate between distinct movements
    assert len({r["row_key"] for r in recs}) == len(recs)


def test_blank_time_does_not_crash():
    recs = build_records(
        [{"section": "roi_cang", "plan_date": date(2026, 8, 11), "stt": "9",
          "time": "", "vessel": "NO TIME", "draft": "5", "loa": "100",
          "dwt": "1.000", "gt": "500", "tugs": None, "channel": "HN",
          "from": "A", "to": "B", "agent": None, "pilot": None}],
        CRAWLED,
    )
    assert recs[0]["plan_time"] is None
    assert recs[0]["vessel_name"] == "NO TIME"
