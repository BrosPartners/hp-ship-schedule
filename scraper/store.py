"""Append-only Parquet storage with snapshot versioning and a coverage manifest.

The dataset is stored as monthly partitions (`ship_plan_YYYY-MM.parquet`)
inside a directory, instead of one ever-growing file. Parquet is compressed
binary, so git cannot delta it - rewriting the whole file every day made
every daily commit store a fresh ~2.9 MB blob. Partitioning means the daily
crawl (which only ever touches yesterday/today/tomorrow) rewrites just the
one or two partitions those days fall into, each of which stays a flat
tens-of-KB regardless of how much history accumulates.
"""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_REPLACE_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8)

PARTITION_PREFIX = "ship_plan_"
PARTITION_SUFFIX = ".parquet"
PARTITION_GLOB = f"{PARTITION_PREFIX}*{PARTITION_SUFFIX}"


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
    "from_raw", "to_raw", "from_berth", "to_berth",
    "from_ticker", "to_ticker", "from_type", "to_type", "is_domestic",
    "agent", "pilot", "crawled_at", "row_key",
]

# Text columns that can legitimately be all-null within a single monthly
# partition (e.g. a month where `pilot` was never recorded). pandas/pyarrow
# infer an all-null object column as Arrow's "null" type instead of
# "string"; when DuckDB's read_parquet later reads many such partitions
# together, a schema mismatch between an all-null partition and a partition
# with real strings raises a Conversion Error. Casting to pandas' nullable
# "string" dtype before writing forces a consistent Arrow "string" type
# regardless of whether a given partition happens to have any non-null
# values, which is what one single ship_plan.parquet always had by virtue
# of covering the whole dataset.
TEXT_COLUMNS = [
    "section", "vessel_name", "tugs", "channel_code", "from_raw", "to_raw",
    "from_berth", "to_berth", "from_ticker", "to_ticker", "from_type",
    "to_type", "agent", "pilot", "row_key",
]


def _normalize_dtypes(df):
    df = df.copy()
    for col in TEXT_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("string")
    return df


def _empty_frame():
    return pd.DataFrame({c: pd.Series(dtype="object") for c in SCHEMA_COLUMNS})


def _month_key(value):
    return pd.Timestamp(value).strftime("%Y-%m")


def _partition_path(dir_path, month_key):
    return Path(dir_path) / f"{PARTITION_PREFIX}{month_key}{PARTITION_SUFFIX}"


def partition_files(dir_path):
    """Sorted list of partition file paths present in `dir_path`."""
    d = Path(dir_path)
    if not d.exists():
        return []
    return sorted(d.glob(PARTITION_GLOB))


def _load_partition(path):
    path = Path(path)
    if not path.exists():
        return _empty_frame()
    return pd.read_parquet(path)


def load(dir_path):
    """Read every monthly partition under `dir_path` and concatenate them.

    Returns the whole dataset - callers that need to filter to one month
    (currently just `upsert`, internally) use `_load_partition` instead.
    """
    files = partition_files(dir_path)
    if not files:
        return _empty_frame()
    frames = [pd.read_parquet(f) for f in files]
    return pd.concat(frames, ignore_index=True)


def _write_partition(path):
    """Return a context-managed writer helper: write df to `path` atomically."""
    def _write(df):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = Path(str(path) + ".tmp")
        try:
            df.to_parquet(tmp_path, index=False, compression="zstd")
            _atomic_replace(tmp_path, path)
        except Exception:
            _cleanup_tmp(tmp_path)
            raise
    return _write


def upsert(dir_path, records):
    """Merge `records` in, replacing rows with the same (row_key, crawl day).

    Re-crawling a date on the same day overwrites; crawling it on a later day
    adds a new snapshot, which is what makes plan-slippage measurable.

    Incoming records are grouped by the month of their `plan_date`; only the
    touched monthly partitions are loaded, merged and rewritten, so the
    unrelated history stays untouched (both in memory and in the working
    tree, which is the point of partitioning). Each partition is written
    atomically and independently, mirroring the previous whole-file write.
    """
    dir_path = Path(dir_path)
    if not records:
        return 0
    incoming = pd.DataFrame(records)
    for column in SCHEMA_COLUMNS:
        if column not in incoming.columns:
            incoming[column] = None
    incoming = incoming[SCHEMA_COLUMNS]

    incoming["_month"] = incoming["plan_date"].map(_month_key)
    total = len(incoming)

    for month_key, group in incoming.groupby("_month"):
        group = group.drop(columns=["_month"])
        path = _partition_path(dir_path, month_key)
        existing = _load_partition(path)

        if not existing.empty:
            incoming_ids = {
                (r.row_key, pd.Timestamp(r.crawled_at).date())
                for r in group.itertuples()
            }
            keep = [
                (r.row_key, pd.Timestamp(r.crawled_at).date()) not in incoming_ids
                for r in existing.itertuples()
            ]
            existing = existing[keep]

        if existing.empty:
            merged = group
        else:
            merged = pd.concat([existing, group], ignore_index=True)
        merged = merged.sort_values(["plan_date", "section", "plan_time", "row_key"])
        merged = _normalize_dtypes(merged)

        _write_partition(path)(merged)

    return total


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


def write_manifest(dir_path, manifest_path, start_date, today):
    df = load(dir_path)
    manifest = _read_manifest(manifest_path)
    empty_days = set(manifest.get("empty_days", []))

    present = set()
    if not df.empty:
        present = {pd.Timestamp(d).date().isoformat() for d in df["plan_date"]}

    # A date that has rows is, by definition, not an empty day. Without this
    # purge, a date wrongly marked empty (e.g. "tomorrow" before its plan was
    # published) would stay labelled "crawled and empty" forever, even after
    # it genuinely gets rows.
    empty_days -= present

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
        "partitions": [p.name for p in partition_files(dir_path)],
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
