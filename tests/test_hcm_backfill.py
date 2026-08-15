import gzip
from datetime import date, datetime
from pathlib import Path

from scraper.hcm.backfill import days_to_do, run
from scraper.store import load

FIXTURES = Path(__file__).parent / "fixtures" / "hcm"


def _html(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def test_run_ingests_one_day(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json"}
    result = run(
        date(2026, 8, 14), date(2026, 8, 14), paths,
        fetcher=lambda target: _html("2026-08-14"),
        now=datetime(2026, 8, 15, 7, 30),
    )
    assert result["days_done"] == 1
    assert result["days_failed"] == []
    # 74 + 68 + 62 rows across the three sections, per test_hcm_parse.py.
    assert result["rows"] == 74 + 68 + 62
    assert len(load(paths["parquet"])) == 74 + 68 + 62


def test_resume_skips_days_already_stored(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json"}
    run(date(2026, 8, 14), date(2026, 8, 14), paths,
        fetcher=lambda target: _html("2026-08-14"),
        now=datetime(2026, 8, 15, 7, 30))

    todo = days_to_do(date(2026, 8, 13), date(2026, 8, 14),
                       paths["manifest"], paths["parquet"])
    assert todo == [date(2026, 8, 13)]


def test_a_failing_day_does_not_abort_the_run(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json"}

    def flaky(target):
        if target == date(2026, 8, 13):
            raise RuntimeError("boom")
        return _html("2026-08-14")

    result = run(date(2026, 8, 13), date(2026, 8, 14), paths,
                 fetcher=flaky, now=datetime(2026, 8, 15, 7, 30))
    assert result["days_failed"] == [date(2026, 8, 13)]
    assert result["days_done"] == 1


def test_a_storage_failure_is_recorded_and_does_not_abort_the_run(
    tmp_path, monkeypatch
):
    """upsert raising (e.g. a locked destination file) for one day should
    land that day in days_failed while the run continues to ingest the
    following good day."""
    import scraper.hcm.backfill as backfill_module

    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json"}

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
        lambda html, expected_date: [{
            "plan_date": expected_date, "section": "tau_vao",
            "ten_tau": "TEST SHIP", "quoc_tich": "VN", "ho_hieu": "ABC123",
            "dwt": "1.000", "chieu_dai": "100,5", "mon_nuoc": "7,2",
            "loai_hang_hoa": "Container", "vi_tri_neo_dau": "VICT",
            "du_kien_den_vt": "08:00", "thoi_gian_roi_vt": None,
            "tau_lai": None, "dai_ly": "AG", "tuyen_luong": "Soai Rap",
        }],
    )

    result = run(
        date(2026, 8, 13), date(2026, 8, 14), paths,
        fetcher=lambda target: "<html/>",
        now=datetime(2026, 8, 15, 7, 30),
    )

    assert result["days_failed"] == [date(2026, 8, 13)]
    assert result["days_done"] == 1
    assert len(load(paths["parquet"])) == 1


def test_empty_day_is_recorded_as_empty_not_failed(tmp_path):
    paths = {"parquet": tmp_path / "parts", "manifest": tmp_path / "m.json"}

    def fetcher(target):
        return _html("2026-08-14")

    def empty_parse(html, expected_date):
        return []

    import scraper.hcm.backfill as backfill_module
    orig_parse = backfill_module.parse_page

    def parse_side_effect(html, expected_date):
        if expected_date == date(2026, 8, 13):
            return []
        return orig_parse(html, expected_date=expected_date)

    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(backfill_module, "parse_page", parse_side_effect)
        result = run(
            date(2026, 8, 13), date(2026, 8, 13), paths,
            fetcher=fetcher, now=datetime(2026, 8, 15, 7, 30),
        )

    assert result["days_empty"] == 1
    assert result["days_failed"] == []

    import json
    manifest = json.loads((paths["manifest"]).read_text(encoding="utf-8"))
    assert "2026-08-13" in manifest["empty_days"]

    # And it must not be retried as "still to do" on the next run.
    todo = days_to_do(date(2026, 8, 13), date(2026, 8, 13),
                       paths["manifest"], paths["parquet"])
    assert todo == []
