import gzip
from datetime import date, datetime
from pathlib import Path

from scraper.backfill import days_to_do, run
from scraper.store import load

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


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
