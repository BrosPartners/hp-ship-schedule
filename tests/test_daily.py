import gzip
from datetime import date, datetime
from pathlib import Path

import pytest

from scraper.daily import run

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def test_daily_fetches_yesterday_today_and_tomorrow(tmp_path):
    seen = []

    def fetcher(target):
        seen.append(target)
        raise RuntimeError("stop after recording targets")

    result = run(
        paths={"parquet": tmp_path / "d.parquet",
               "manifest": tmp_path / "m.json",
               "agg": tmp_path / "agg"},
        fetcher=fetcher, today=date(2026, 8, 12),
        now=datetime(2026, 8, 12, 7, 30),
    )
    assert seen == [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)]
    assert result["days_failed"] == seen


def test_daily_stores_rows_and_builds_aggregates(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json",
             "agg": tmp_path / "agg"}

    def fetcher(target):
        if target == date(2026, 8, 11):
            return _html("2026-08-11_full")
        raise RuntimeError("only the 11th is fixtured")

    result = run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
                 now=datetime(2026, 8, 12, 7, 30))
    assert result["rows"] == 86
    assert (tmp_path / "agg" / "monthly_volume.json").exists()
    assert (tmp_path / "m.json").exists()


def test_a_second_run_on_a_later_day_creates_a_second_snapshot(tmp_path):
    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json",
             "agg": tmp_path / "agg"}
    fetcher = lambda target: _html("2026-08-11_full")  # noqa: E731

    run(paths=paths, fetcher=fetcher, today=date(2026, 8, 11),
        now=datetime(2026, 8, 11, 7, 30))
    run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
        now=datetime(2026, 8, 12, 7, 30))

    import pandas as pd
    df = pd.read_parquet(paths["parquet"])
    assert df["crawled_at"].nunique() == 2


def test_daily_raises_loudly_when_berth_map_is_missing(tmp_path, monkeypatch):
    """A missing berth_map.csv must fail before any fetching, not silently
    zero out berth attribution for every record in the run."""
    import scraper.daily as daily_module

    monkeypatch.setattr(daily_module, "ROOT", tmp_path)

    fetched = []

    def fetcher(target):
        fetched.append(target)
        raise AssertionError("should never be called: map check must run first")

    paths = {"parquet": tmp_path / "d.parquet", "manifest": tmp_path / "m.json",
             "agg": tmp_path / "agg"}

    with pytest.raises(FileNotFoundError):
        run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
            now=datetime(2026, 8, 12, 7, 30))

    assert fetched == []
