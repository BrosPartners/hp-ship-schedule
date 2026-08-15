"""HCM-specific Parquet storage, reusing everything from `scraper.store`
that is genuinely schema-agnostic.

`scraper.store.upsert`/`_normalize_dtypes`/`_empty_frame` are hardcoded to
Hai Phong's module-level `SCHEMA_COLUMNS`/`TEXT_COLUMNS` constants: `upsert`
does `incoming = incoming[SCHEMA_COLUMNS]`, which for HCM records would
silently drop every HCM-only column (nationality, call_sign, cargo_type,
from_position/to_position, eta/etd, ...) and fill in Hai Phong columns
(gt, pilot, is_domestic, ...) that don't apply here. That is exactly the
kind of hardcoding the task calls out as blocking reuse, so this module
defines the HCM equivalents of just those pieces instead of editing the
shared module.

Everything else genuinely doesn't care about the schema:
- `partition_files` only globs `ship_plan_*.parquet`, which HCM also uses
  (monthly partitioning, same naming convention as Hai Phong).
- `latest_snapshot`, `mark_crawled_empty`, `write_manifest` only touch
  `plan_date`/`crawled_at`, which both schemas have.
- `_atomic_replace`/`_cleanup_tmp` are pure path/file mechanics.
`scraper.store.load` is also reused as-is in `scraper/hcm/backfill.py`
directly (not re-exported here) for the same reason.
"""

from pathlib import Path

import pandas as pd

from scraper.store import (
    _atomic_replace,
    _cleanup_tmp,
    latest_snapshot,  # noqa: F401  (re-exported for callers)
    mark_crawled_empty,  # noqa: F401  (re-exported for callers)
    partition_files,
    write_manifest,  # noqa: F401  (re-exported for callers)
)

SCHEMA_COLUMNS = [
    "plan_date", "section", "vessel_name", "nationality", "call_sign",
    "dwt", "loa_m", "draft_m", "cargo_type",
    "from_position", "to_position", "eta", "etd",
    "tugs", "agent", "channel", "crawled_at", "row_key",
    "from_berth", "to_berth", "from_cluster", "to_cluster",
    "from_ticker", "to_ticker", "from_type", "to_type",
]

# Columns that can legitimately be all-null within a single monthly
# partition. Cast to pandas' nullable "string" dtype before writing so
# pyarrow infers a consistent Arrow "string" type rather than "null" for an
# all-null partition, which would otherwise clash when a multi-partition
# read (e.g. DuckDB) meets a partition that does have real string values.
# Same reasoning as scraper.store.TEXT_COLUMNS.
TEXT_COLUMNS = [
    "section", "vessel_name", "nationality", "call_sign", "cargo_type",
    "from_position", "to_position", "tugs", "agent", "channel", "row_key",
    "from_berth", "to_berth", "from_cluster", "to_cluster",
    "from_ticker", "to_ticker", "from_type", "to_type",
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
    return Path(dir_path) / f"ship_plan_{month_key}.parquet"


def _load_partition(path):
    path = Path(path)
    if not path.exists():
        return _empty_frame()
    return pd.read_parquet(path)


def _write_partition(path):
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

    Mirrors `scraper.store.upsert` exactly, just against the HCM schema.
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
        merged = merged.sort_values(["plan_date", "section", "row_key"])
        merged = _normalize_dtypes(merged)

        _write_partition(path)(merged)

    return total


__all__ = [
    "SCHEMA_COLUMNS", "TEXT_COLUMNS", "upsert",
    "latest_snapshot", "mark_crawled_empty", "write_manifest",
    "partition_files",
]
