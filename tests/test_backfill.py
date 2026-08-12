import gzip
from datetime import date, datetime
from pathlib import Path

import pytest

from scraper.backfill import days_to_do, run
from scraper.store import load

FIXTURES = Path(__file__).parent / "fixtures"
BERTH_MAP = Path(__file__).parent.parent / "data" / "berth_map.csv"


def _html(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def _rec_for(plan_date, crawled_at):
    return {
        "plan_date": plan_date, "section": "vao_cang",
        "plan_time": datetime.combine(plan_date, datetime.min.time()),
        "vessel_name": "TEST SHIP", "is_sb": False, "draft_m": 7.0,
        "loa_m": 100.0, "dwt": 1000, "gt": 500, "tugs": None,
        "channel_code": "HN", "from_raw": "X", "to_raw": "Y",
        "agent": "AG", "pilot": "P", "crawled_at": crawled_at,
        "row_key": f"{plan_date.isoformat()}-test",
    }


def test_run_ingests_one_day(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}
    result = run(
        date(2026, 8, 11), date(2026, 8, 11), paths,
        fetcher=lambda target: _html("2026-08-11_full"),
        now=datetime(2026, 8, 12, 7, 30),
    )
    assert result["days_done"] == 1
    assert result["rows"] == 86
    assert len(load(paths["parquet"])) == 86


def test_resume_skips_days_already_stored(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}
    run(date(2026, 8, 11), date(2026, 8, 11), paths,
        fetcher=lambda target: _html("2026-08-11_full"),
        now=datetime(2026, 8, 12, 7, 30))

    todo = days_to_do(date(2026, 8, 10), date(2026, 8, 11),
                      paths["manifest"], paths["parquet"])
    assert todo == [date(2026, 8, 10)]


def test_a_failing_day_does_not_abort_the_run(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}

    def flaky(target):
        if target == date(2026, 8, 10):
            raise RuntimeError("boom")
        return _html("2026-08-11_full")

    result = run(date(2026, 8, 10), date(2026, 8, 11), paths,
                 fetcher=flaky, now=datetime(2026, 8, 12, 7, 30))
    assert result["days_failed"] == [date(2026, 8, 10)]
    assert result["days_done"] == 1


def test_a_storage_failure_is_recorded_and_does_not_abort_the_run(
    tmp_path, monkeypatch
):
    """upsert raising (e.g. a locked destination file) for one day should
    land that day in days_failed while the run continues to ingest the
    following good day."""
    import scraper.backfill as backfill_module

    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}

    real_upsert = backfill_module.upsert
    calls = {"n": 0}

    def flaky_upsert(parquet_path, records):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated locked destination file")
        return real_upsert(parquet_path, records)

    monkeypatch.setattr(backfill_module, "upsert", flaky_upsert)
    monkeypatch.setattr(
        backfill_module, "parse_page",
        lambda html, expected_date: [{"date": expected_date}],
    )
    monkeypatch.setattr(
        backfill_module, "build_records",
        lambda raw, crawled_at: [
            _rec_for(raw[0]["date"], crawled_at)
        ],
    )

    result = run(
        date(2026, 8, 10), date(2026, 8, 11), paths,
        fetcher=lambda target: "<html/>",
        now=datetime(2026, 8, 12, 7, 30),
    )

    assert result["days_failed"] == [date(2026, 8, 10)]
    assert result["days_done"] == 1
    assert len(load(paths["parquet"])) == 1


def test_run_applies_berth_map_to_stored_rows(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}
    run(
        date(2026, 8, 11), date(2026, 8, 11), paths,
        fetcher=lambda target: _html("2026-08-11_full"),
        now=datetime(2026, 8, 12, 7, 30),
        berth_map_path=BERTH_MAP,
    )
    df = load(paths["parquet"])
    assert df["to_berth"].notna().any()

    tan_vu = df[df["to_raw"].str.upper() == "TAN VU"]
    assert not tan_vu.empty
    assert (tan_vu["to_berth"] == "Tân Vũ").all()
    assert (tan_vu["to_type"] == "berth").all()


def test_run_raises_before_fetching_when_berth_map_missing(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json"}
    calls = {"n": 0}

    def fetcher(target):
        calls["n"] += 1
        return _html("2026-08-11_full")

    with pytest.raises(Exception):
        run(
            date(2026, 8, 11), date(2026, 8, 11), paths,
            fetcher=fetcher,
            now=datetime(2026, 8, 12, 7, 30),
            berth_map_path=tmp_path / "missing_berth_map.csv",
        )

    assert calls["n"] == 0
