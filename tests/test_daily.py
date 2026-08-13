import gzip
import json
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
        paths={"parquet": tmp_path / "parts",
               "manifest": tmp_path / "m.json",
               "agg": tmp_path / "agg"},
        fetcher=fetcher, today=date(2026, 8, 12),
        now=datetime(2026, 8, 12, 7, 30),
    )
    assert seen == [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)]
    assert result["days_failed"] == seen


def test_daily_stores_rows_and_builds_aggregates(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
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
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
             "agg": tmp_path / "agg"}
    fetcher = lambda target: _html("2026-08-11_full")  # noqa: E731

    run(paths=paths, fetcher=fetcher, today=date(2026, 8, 11),
        now=datetime(2026, 8, 11, 7, 30))
    run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
        now=datetime(2026, 8, 12, 7, 30))

    from scraper.store import load
    df = load(paths["parquet"])
    assert df["crawled_at"].nunique() == 2


def _empty_page_for(target):
    """A minimal page with the correct date header and no data tables, so
    parse_page returns [] without raising DateMismatchError."""
    return f"<html><body>KE HOACH DIEU DONG TAU NGAY {target:%d/%m/%Y}</body></html>"


def test_daily_does_not_mark_unpublished_future_day_as_empty(tmp_path):
    """Tomorrow's plan is usually not published yet; an empty fetch for a
    future target must not be recorded as empty_days, or it can never
    self-heal once the plan is actually published."""
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg"}

    result = run(paths=paths, fetcher=_empty_page_for, today=date(2026, 8, 12),
                 now=datetime(2026, 8, 12, 7, 30))
    assert result["days_failed"] == []

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert date(2026, 8, 13).isoformat() not in manifest["empty_days"]


def test_daily_marks_non_future_empty_day_as_empty(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg"}

    result = run(paths=paths, fetcher=_empty_page_for, today=date(2026, 8, 12),
                 now=datetime(2026, 8, 12, 7, 30))
    assert result["days_failed"] == []

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert date(2026, 8, 12).isoformat() in manifest["empty_days"]
    assert date(2026, 8, 11).isoformat() in manifest["empty_days"]


def test_a_storage_failure_on_one_target_does_not_abort_the_run(tmp_path, monkeypatch):
    """upsert raising for the first target (e.g. a locked destination file)
    must land only that target in days_failed, and the remaining targets
    must still be ingested and the aggregates/manifest still rebuilt -
    mirroring the fix already in scraper.backfill."""
    import scraper.daily as daily_module

    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg"}

    calls = {"n": 0}
    real_upsert = daily_module.upsert

    def flaky_upsert(parquet_path, records):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated locked destination file")
        return real_upsert(parquet_path, records)

    monkeypatch.setattr(daily_module, "upsert", flaky_upsert)
    monkeypatch.setattr(
        daily_module, "parse_page",
        lambda html, expected_date: [{"date": expected_date}],
    )
    monkeypatch.setattr(
        daily_module, "build_records",
        lambda raw, crawled_at: [{
            "plan_date": raw[0]["date"], "section": "vao_cang",
            "plan_time": datetime.combine(raw[0]["date"], datetime.min.time()),
            "vessel_name": "TEST SHIP", "is_sb": False, "draft_m": 7.0,
            "loa_m": 100.0, "dwt": 1000, "gt": 500, "tugs": None,
            "channel_code": "HN", "from_raw": "X", "to_raw": "Y",
            "agent": "AG", "pilot": "P", "crawled_at": crawled_at,
            "row_key": f"{raw[0]['date'].isoformat()}-test",
        }],
    )

    result = daily_module.run(paths=paths, fetcher=lambda target: "<html/>",
                               today=date(2026, 8, 11), now=datetime(2026, 8, 11, 7, 30))

    assert result["days_failed"] == [date(2026, 8, 10)]
    assert result["days_done"] == 2  # today and tomorrow still ingested
    assert (tmp_path / "agg" / "monthly_volume.json").exists()
    assert (tmp_path / "m.json").exists()


def test_a_missing_day_that_is_retried_successfully_is_healed(tmp_path):
    """A day in manifest['missing_days'] must be retried and, on success,
    disappear from missing_days (it now has rows on disk, so the next
    write_manifest computes it as present rather than missing)."""
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg"}

    # Seed a manifest that claims 2026-07-01 is missing.
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    paths["manifest"].write_text(json.dumps({"missing_days": ["2026-07-01"]}),
                                  encoding="utf-8")

    seen = []

    def fetcher(target):
        seen.append(target)
        if target == date(2026, 7, 1):
            return _html("2026-08-11_full").replace("11/08/2026", "01/07/2026")
        # The 3 rolling targets: no fixture for them, so treat as empty.
        return _empty_page_for(target)

    result = run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
                 now=datetime(2026, 8, 12, 7, 30))

    assert date(2026, 7, 1) in seen
    assert result["missing_days_retried"] == [date(2026, 7, 1)]
    assert result["missing_days_healed"] == [date(2026, 7, 1)]

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert "2026-07-01" not in manifest["missing_days"]


def test_the_missing_day_retry_cap_is_respected(tmp_path):
    """More than MAX_MISSING_RETRIES missing days exist: only the oldest
    MAX_MISSING_RETRIES are attempted this run, so the job stays fast and
    polite to the source even after a long outage."""
    import scraper.daily as daily_module

    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg"}
    missing = [f"2026-0{m}-01" for m in range(1, 8)]  # 7 missing days
    assert len(missing) > daily_module.MAX_MISSING_RETRIES
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    paths["manifest"].write_text(json.dumps({"missing_days": missing}),
                                  encoding="utf-8")

    seen_retries = []

    def fetcher(target):
        if target.day == 1 and target < date(2026, 8, 1):
            seen_retries.append(target)
        return _empty_page_for(target)

    result = run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
                 now=datetime(2026, 8, 12, 7, 30))

    assert len(result["missing_days_retried"]) == daily_module.MAX_MISSING_RETRIES
    assert len(seen_retries) == daily_module.MAX_MISSING_RETRIES
    # Oldest first.
    assert result["missing_days_retried"] == sorted(result["missing_days_retried"])[:5]


def test_unmapped_report_is_regenerated_when_wired_up(tmp_path):
    """When the caller opts in with an `unmapped_report` path (as
    DEFAULT_PATHS does for the real daily job), the CSV must be regenerated
    against the partitioned data this run just wrote."""
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
              "agg": tmp_path / "agg",
              "unmapped_report": tmp_path / "unmapped_report.csv"}

    def fetcher(target):
        if target == date(2026, 8, 11):
            return _html("2026-08-11_full")
        return _empty_page_for(target)

    run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
        now=datetime(2026, 8, 12, 7, 30))

    assert paths["unmapped_report"].exists()
    import pandas as pd
    out = pd.read_csv(paths["unmapped_report"])
    assert len(out) > 0
    assert {"raw_name", "n", "mapped"}.issubset(out.columns)


def test_main_raises_when_a_single_rolling_target_fails(monkeypatch):
    """A single real failure among the 3 rolling targets must make main()
    fail/exit non-zero, so CI opens an issue - not just when 2+ of the 3
    fail, which used to let a single real failure exit 0 silently."""
    import scraper.daily as daily_module

    monkeypatch.setattr(daily_module, "run", lambda: {
        "targets": [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)],
        "days_done": 2, "days_empty": 0, "days_failed": [date(2026, 8, 11)],
        "rows": 0, "missing_days_retried": [], "missing_days_healed": [],
        "missing_days_still_failing": [], "missing_days_rows": 0,
    })

    with pytest.raises(SystemExit):
        daily_module.main()


def test_main_does_not_raise_when_only_the_retried_missing_days_fail(monkeypatch):
    """Failures among the retried missing_days entries are best-effort and
    must not, on their own, fail the whole job - only a real failure among
    the 3 rolling targets should."""
    import scraper.daily as daily_module

    monkeypatch.setattr(daily_module, "run", lambda: {
        "targets": [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)],
        "days_done": 3, "days_empty": 0, "days_failed": [],
        "rows": 10, "missing_days_retried": [date(2026, 1, 1)],
        "missing_days_healed": [], "missing_days_still_failing": [date(2026, 1, 1)],
        "missing_days_rows": 0,
    })

    daily_module.main()  # must not raise


def test_daily_raises_loudly_when_berth_map_is_missing(tmp_path, monkeypatch):
    """A missing berth_map.csv must fail before any fetching, not silently
    zero out berth attribution for every record in the run."""
    import scraper.daily as daily_module

    monkeypatch.setattr(daily_module, "ROOT", tmp_path)

    fetched = []

    def fetcher(target):
        fetched.append(target)
        raise AssertionError("should never be called: map check must run first")

    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json",
             "agg": tmp_path / "agg"}

    with pytest.raises(FileNotFoundError):
        run(paths=paths, fetcher=fetcher, today=date(2026, 8, 12),
            now=datetime(2026, 8, 12, 7, 30))

    assert fetched == []
