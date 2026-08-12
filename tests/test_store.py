import json
from datetime import date, datetime

import pandas as pd

from scraper.store import (SCHEMA_COLUMNS, latest_snapshot, load,
                            mark_crawled_empty, upsert, write_manifest)


def _rec(day, key, crawled, to_raw="TAN VU"):
    return {
        "plan_date": date(2026, 8, day), "section": "vao_cang",
        "plan_time": datetime(2026, 8, day, 6, 0), "vessel_name": f"SHIP {key}",
        "is_sb": False, "draft_m": 7.7, "loa_m": 143.9, "dwt": 13021, "gt": 9757,
        "tugs": None, "channel_code": "HN", "from_raw": "CHINA", "to_raw": to_raw,
        "agent": "AG", "pilot": "P", "crawled_at": crawled, "row_key": key,
    }


def test_load_missing_file_returns_empty_typed_frame(tmp_path):
    df = load(tmp_path / "nope.parquet")
    assert df.empty
    assert list(df.columns) == SCHEMA_COLUMNS


def test_upsert_appends_then_roundtrips(tmp_path):
    path = tmp_path / "d.parquet"
    assert upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))]) == 1
    assert upsert(path, [_rec(12, "b", datetime(2026, 8, 12, 7, 30))]) == 1
    df = load(path)
    assert len(df) == 2
    assert set(df["row_key"]) == {"a", "b"}


def test_recrawl_same_day_replaces_instead_of_duplicating(tmp_path):
    path = tmp_path / "d.parquet"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 7, 30), to_raw="TAN VU")])
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 19, 0), to_raw="DINH VU")])
    df = load(path)
    assert len(df) == 1
    assert df.iloc[0]["to_raw"] == "DINH VU"


def test_snapshots_from_different_days_are_both_kept(tmp_path):
    path = tmp_path / "d.parquet"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 10, 7, 30))])
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 7, 30))])
    df = load(path)
    assert len(df) == 2
    assert len(latest_snapshot(df)) == 1
    assert latest_snapshot(df).iloc[0]["crawled_at"] == datetime(2026, 8, 12, 7, 30)


def test_manifest_reports_missing_days(tmp_path):
    path = tmp_path / "d.parquet"
    mpath = tmp_path / "manifest.json"
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    upsert(path, [_rec(3, "b", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert man["missing_days"] == ["2026-08-02"]
    assert man["days_covered"] == 2
    assert man["last_plan_date"] == "2026-08-03"
    assert json.loads(mpath.read_text(encoding="utf-8"))["row_count"] == 2


def test_empty_day_is_crawled_not_missing(tmp_path):
    path = tmp_path / "d.parquet"
    mpath = tmp_path / "manifest.json"
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    mark_crawled_empty(mpath, date(2026, 8, 2))
    upsert(path, [_rec(3, "b", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert man["missing_days"] == []
    assert man["empty_days"] == ["2026-08-02"]
