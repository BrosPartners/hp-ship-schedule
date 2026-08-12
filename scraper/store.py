"""Append-only Parquet storage with snapshot versioning and a coverage manifest."""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_REPLACE_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8)


def _atomic_replace(tmp_path, dest_path):
    """Replace `dest_path` with `tmp_path`, retrying on transient locks.

    On Windows, os.replace can fail with PermissionError/OSError when
    something else (e.g. an antivirus scanner or the search indexer)
    transiently holds the destination file open. Retry a few times with a
    short escalating backoff before giving up.
    """
    last_exc = None
    for attempt, delay in enumerate((0.0,) + _REPLACE_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            os.replace(tmp_path, dest_path)
            return
        except (PermissionError, OSError) as exc:
            last_exc = exc
    raise OSError(
        f"Could not replace {dest_path}: it appears to be locked by another "
        f"process (e.g. an antivirus scanner or search indexer). "
        f"Last error: {last_exc}"
    ) from last_exc


def _cleanup_tmp(tmp_path):
    """Best-effort removal of a leftover temp file. Never raises."""
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except OSError:
        pass


SCHEMA_COLUMNS = [
    "plan_date", "section", "plan_time", "vessel_name", "is_sb",
    "draft_m", "loa_m", "dwt", "gt", "tugs", "channel_code",
    "from_raw", "to_raw", "agent", "pilot", "crawled_at", "row_key",
]


def load(parquet_path):
    path = Path(parquet_path)
    if not path.exists():
        return pd.DataFrame({c: pd.Series(dtype="object") for c in SCHEMA_COLUMNS})
    return pd.read_parquet(path)


def upsert(parquet_path, records):
    """Merge `records` in, replacing rows with the same (row_key, crawl day).

    Re-crawling a date on the same day overwrites; crawling it on a later day
    adds a new snapshot, which is what makes plan-slippage measurable.
    """
    path = Path(parquet_path)
    if not records:
        return 0
    incoming = pd.DataFrame(records)[SCHEMA_COLUMNS]
    existing = load(path)

    if not existing.empty:
        incoming_ids = {
            (r.row_key, pd.Timestamp(r.crawled_at).date())
            for r in incoming.itertuples()
        }
        keep = [
            (r.row_key, pd.Timestamp(r.crawled_at).date()) not in incoming_ids
            for r in existing.itertuples()
        ]
        existing = existing[keep]

    if existing.empty:
        merged = incoming
    else:
        merged = pd.concat([existing, incoming], ignore_index=True)
    merged = merged.sort_values(["plan_date", "section", "plan_time", "row_key"])
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first, then atomically replace
    tmp_path = Path(str(path) + ".tmp")
    try:
        merged.to_parquet(tmp_path, index=False, compression="zstd")
        _atomic_replace(tmp_path, path)
    except Exception:
        # Clean up temp file defensively and re-raise the original exception.
        _cleanup_tmp(tmp_path)
        raise

    return len(incoming)


def latest_snapshot(df):
    """Keep, for each plan_date, only the rows from its most recent crawl."""
    if df.empty:
        return df
    newest = df.groupby("plan_date")["crawled_at"].transform("max")
    return df[df["crawled_at"] == newest]


def _read_manifest(manifest_path):
    path = Path(manifest_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"empty_days": []}


def mark_crawled_empty(manifest_path, plan_date):
    """Record a day that was fetched successfully but had no rows.

    Without this, 'no data' and 'never fetched' are indistinguishable and the
    dashboard would under-report coverage forever.
    """
    manifest = _read_manifest(manifest_path)
    empty = set(manifest.get("empty_days", []))
    empty.add(plan_date.isoformat())
    manifest["empty_days"] = sorted(empty)
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first, then atomically replace
    manifest_path_obj = Path(manifest_path)
    tmp_path = Path(str(manifest_path_obj) + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _atomic_replace(tmp_path, manifest_path_obj)
    except Exception:
        # Clean up temp file defensively and re-raise the original exception.
        _cleanup_tmp(tmp_path)
        raise


def write_manifest(parquet_path, manifest_path, start_date, today):
    df = load(parquet_path)
    manifest = _read_manifest(manifest_path)
    empty_days = set(manifest.get("empty_days", []))

    present = set()
    if not df.empty:
        present = {pd.Timestamp(d).date().isoformat() for d in df["plan_date"]}

    expected, cursor = [], start_date
    while cursor <= today:
        expected.append(cursor.isoformat())
        cursor += timedelta(days=1)

    missing = [d for d in expected if d not in present and d not in empty_days]

    manifest.update({
        "start_date": start_date.isoformat(),
        "last_plan_date": max(present) if present else None,
        "last_crawled_at": (
            str(pd.Timestamp(df["crawled_at"].max())) if not df.empty else None
        ),
        "row_count": int(len(df)),
        "days_covered": len(present),
        "days_expected": len(expected),
        "empty_days": sorted(empty_days),
        "missing_days": missing,
    })
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first, then atomically replace
    manifest_path_obj = Path(manifest_path)
    tmp_path = Path(str(manifest_path_obj) + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _atomic_replace(tmp_path, manifest_path_obj)
    except Exception:
        # Clean up temp file defensively and re-raise the original exception.
        _cleanup_tmp(tmp_path)
        raise

    return manifest
