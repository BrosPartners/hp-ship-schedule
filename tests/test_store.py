import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scraper.store import (SCHEMA_COLUMNS, latest_snapshot, load,
                            mark_crawled_empty, upsert, write_manifest)

# All test records fall in August 2026, so they all land in this one
# partition file - keeps the .tmp-file assertions below simple.
PARTITION_NAME = "ship_plan_2026-08.parquet"


def _part(dir_path):
    return dir_path / PARTITION_NAME


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
    path = tmp_path / "parts"
    assert upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))]) == 1
    assert upsert(path, [_rec(12, "b", datetime(2026, 8, 12, 7, 30))]) == 1
    df = load(path)
    assert len(df) == 2
    assert set(df["row_key"]) == {"a", "b"}


def test_recrawl_same_day_replaces_instead_of_duplicating(tmp_path):
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 7, 30), to_raw="TAN VU")])
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 19, 0), to_raw="DINH VU")])
    df = load(path)
    assert len(df) == 1
    assert df.iloc[0]["to_raw"] == "DINH VU"


def test_snapshots_from_different_days_are_both_kept(tmp_path):
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 10, 7, 30))])
    upsert(path, [_rec(11, "a", datetime(2026, 8, 12, 7, 30))])
    df = load(path)
    assert len(df) == 2
    assert len(latest_snapshot(df)) == 1
    assert latest_snapshot(df).iloc[0]["crawled_at"] == datetime(2026, 8, 12, 7, 30)


def test_manifest_reports_missing_days(tmp_path):
    path = tmp_path / "parts"
    mpath = tmp_path / "manifest.json"
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    upsert(path, [_rec(3, "b", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert man["missing_days"] == ["2026-08-02"]
    assert man["days_covered"] == 2
    assert man["last_plan_date"] == "2026-08-03"
    assert json.loads(mpath.read_text(encoding="utf-8"))["row_count"] == 2


def test_empty_day_is_crawled_not_missing(tmp_path):
    path = tmp_path / "parts"
    mpath = tmp_path / "manifest.json"
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    mark_crawled_empty(mpath, date(2026, 8, 2))
    upsert(path, [_rec(3, "b", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert man["missing_days"] == []
    assert man["empty_days"] == ["2026-08-02"]


def test_write_manifest_heals_empty_day_that_now_has_rows(tmp_path):
    """A date previously recorded as empty that later has rows must be
    dropped from empty_days (and not appear in missing_days either)."""
    path = tmp_path / "parts"
    mpath = tmp_path / "manifest.json"
    mark_crawled_empty(mpath, date(2026, 8, 2))
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    upsert(path, [_rec(2, "b", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert "2026-08-02" not in man["empty_days"]
    assert "2026-08-02" not in man["missing_days"]


def test_write_manifest_keeps_legitimately_empty_days(tmp_path):
    """A date in empty_days that still has no rows must stay in empty_days;
    the healing purge must not wipe legitimately empty days."""
    path = tmp_path / "parts"
    mpath = tmp_path / "manifest.json"
    mark_crawled_empty(mpath, date(2026, 8, 2))
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    man = write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 3))
    assert man["empty_days"] == ["2026-08-02"]


def test_upsert_leaves_no_tmp_file_on_success(tmp_path):
    """A successful upsert should not leave a .tmp file in the data directory."""
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))])

    # Check no .tmp file exists
    tmp_file = tmp_path / "parts" / (PARTITION_NAME + ".tmp")
    assert not tmp_file.exists()


def test_upsert_preserves_data_on_write_failure(tmp_path, monkeypatch):
    """If Parquet write fails, the pre-existing file is untouched and no .tmp file left."""
    path = tmp_path / "parts"

    # Write initial data
    initial_records = [_rec(11, "a", datetime(2026, 8, 11, 7, 30))]
    upsert(path, initial_records)
    original_content = _part(path).read_bytes()

    # Simulate write failure: make to_parquet raise on next call
    original_to_parquet = pd.DataFrame.to_parquet

    def failing_to_parquet(self, *args, **kwargs):
        raise IOError("Simulated write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", failing_to_parquet)

    # Try to upsert new data; this should fail
    new_records = [_rec(12, "b", datetime(2026, 8, 12, 7, 30))]
    with pytest.raises(IOError, match="Simulated write failure"):
        upsert(path, new_records)

    # Verify original file is untouched
    assert _part(path).read_bytes() == original_content

    # Verify no .tmp file left behind
    tmp_file = tmp_path / "parts" / (PARTITION_NAME + ".tmp")
    assert not tmp_file.exists()

    # Verify original data is still loadable
    df = load(path)
    assert len(df) == 1
    assert df.iloc[0]["row_key"] == "a"


def test_write_manifest_preserves_manifest_on_failure(tmp_path, monkeypatch):
    """If manifest write fails, the pre-existing manifest is untouched and no .tmp file left."""
    path = tmp_path / "parts"
    mpath = tmp_path / "manifest.json"

    # Write initial data and manifest
    upsert(path, [_rec(1, "a", datetime(2026, 8, 12, 7, 30))])
    write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 1))
    original_manifest_content = mpath.read_text(encoding="utf-8")

    # Simulate write failure: make write_text fail on manifest.json.tmp writes
    original_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        # Fail on tmp file writes for manifest
        if "manifest.json.tmp" in str(self):
            raise IOError("Simulated manifest write failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    # Try to write manifest again; this should fail
    with pytest.raises(IOError, match="Simulated manifest write failure"):
        write_manifest(path, mpath, date(2026, 8, 1), date(2026, 8, 5))

    # Verify original manifest is untouched
    assert mpath.read_text(encoding="utf-8") == original_manifest_content

    # Verify no .tmp file left behind
    tmp_file = tmp_path / "manifest.json.tmp"
    assert not tmp_file.exists()


def test_upsert_retries_transient_permission_error_then_succeeds(tmp_path, monkeypatch):
    """A transient PermissionError on os.replace (e.g. AV/indexer holding the
    file open) should be retried and the write should still succeed."""
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))])

    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(
                "[WinError 32] The process cannot access the file because it "
                "is being used by another process"
            )
        return real_replace(src, dst)

    monkeypatch.setattr("scraper.store.os.replace", flaky_replace)
    monkeypatch.setattr("scraper.store.time.sleep", lambda *a, **k: None)

    written = upsert(path, [_rec(12, "b", datetime(2026, 8, 12, 7, 30))])
    assert written == 1
    assert calls["n"] == 3

    df = load(path)
    assert len(df) == 2
    assert set(df["row_key"]) == {"a", "b"}

    tmp_file = tmp_path / "parts" / (PARTITION_NAME + ".tmp")
    assert not tmp_file.exists()


def test_upsert_persistent_permission_error_names_file_and_preserves_data(
    tmp_path, monkeypatch
):
    """If os.replace never succeeds, raise an informative error naming the
    target file, leave the existing file untouched, and clean up the tmp
    file."""
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))])
    original_content = _part(path).read_bytes()

    def always_fails(src, dst):
        raise PermissionError(
            "[WinError 32] The process cannot access the file because it "
            "is being used by another process"
        )

    monkeypatch.setattr("scraper.store.os.replace", always_fails)
    monkeypatch.setattr("scraper.store.time.sleep", lambda *a, **k: None)

    with pytest.raises(Exception) as excinfo:
        upsert(path, [_rec(12, "b", datetime(2026, 8, 12, 7, 30))])

    assert str(_part(path)) in str(excinfo.value)

    assert _part(path).read_bytes() == original_content

    tmp_file = tmp_path / "parts" / (PARTITION_NAME + ".tmp")
    assert not tmp_file.exists()


def test_upsert_tolerates_records_missing_berth_columns(tmp_path):
    """Records with only the original 17 keys (no berth_map columns) must
    still upsert successfully, with the seven berth columns present and
    null in the stored result."""
    path = tmp_path / "parts"
    rec = _rec(11, "a", datetime(2026, 8, 11, 7, 30))
    assert set(rec) & {
        "from_berth", "to_berth", "from_ticker", "to_ticker",
        "from_type", "to_type", "is_domestic",
    } == set()

    written = upsert(path, [rec])
    assert written == 1

    df = load(path)
    assert len(df) == 1
    for col in ("from_berth", "to_berth", "from_ticker", "to_ticker",
                "from_type", "to_type", "is_domestic"):
        assert col in df.columns
        assert pd.isna(df.iloc[0][col])


def test_upsert_cleanup_failure_does_not_mask_original_exception(
    tmp_path, monkeypatch
):
    """If the unlink cleanup itself raises, the original exception type must
    still surface, not the cleanup failure."""
    path = tmp_path / "parts"
    upsert(path, [_rec(11, "a", datetime(2026, 8, 11, 7, 30))])

    def failing_to_parquet(self, *args, **kwargs):
        raise IOError("Simulated write failure")

    def failing_unlink(self, *args, **kwargs):
        raise OSError("Simulated cleanup failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", failing_to_parquet)
    monkeypatch.setattr(Path, "unlink", failing_unlink)

    with pytest.raises(IOError, match="Simulated write failure"):
        upsert(path, [_rec(12, "b", datetime(2026, 8, 12, 7, 30))])
