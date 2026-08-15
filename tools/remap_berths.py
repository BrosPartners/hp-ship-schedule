"""Re-apply berth_map.csv to already-stored partitions.

The derived columns (`*_berth`, `*_ticker`, `*_type`, `*_zone`, `is_domestic`)
are baked into the Parquet at crawl time, so editing `berth_map.csv` alone does
nothing to history - only newly crawled days would pick the change up. This
tool rewrites those columns in place from the raw values, which are never
altered by the mapping and so remain the source of truth.

It rewrites partition files, so it takes the same precautions the crawlers do:
every file is written to a temp path and atomically swapped, and `--dry-run`
(the default) reports the diff without touching anything.

    python -m tools.remap_berths --dry-run
    python -m tools.remap_berths --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from scraper.normalize import apply_berth_map, load_berth_map
from scraper.store import _atomic_replace, _normalize_dtypes

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ["from_berth", "to_berth", "from_ticker", "to_ticker",
           "from_type", "to_type", "from_zone", "to_zone", "is_domestic"]


def remap_frame(df, berth_map):
    """Return `df` with the derived columns recomputed from from_raw/to_raw."""
    records = apply_berth_map(df.to_dict("records"), berth_map)
    return _normalize_dtypes(pd.DataFrame(records)[list(df.columns)])


def _diff(before, after):
    """Count changed cells per derived column, treating NaN == NaN as equal."""
    # Compared as plain objects with a null sentinel: the stored frame holds
    # `object`/None while the rebuilt one holds pandas' `string`/<NA>, and an
    # elementwise `==` between those propagates NA instead of returning False,
    # which silently reports "no change" for exactly the rows that changed.
    counts = Counter()
    for col in DERIVED:
        a = before[col].astype(object).where(before[col].notna(), "\0")
        b = after[col].astype(object).where(after[col].notna(), "\0")
        changed = int((a != b).sum())
        if changed:
            counts[col] = changed
    return counts


def run(parts_dir, map_path, apply_changes):
    berth_map = load_berth_map(map_path)
    files = sorted(Path(parts_dir).glob("*.parquet"))
    if not files:
        raise SystemExit(f"không thấy partition nào trong {parts_dir}")

    totals, touched = Counter(), 0
    for path in files:
        before = pd.read_parquet(path)
        after = remap_frame(before, berth_map)
        counts = _diff(before, after)
        if not counts:
            continue
        touched += 1
        totals.update(counts)
        if apply_changes:
            tmp = path.with_suffix(".parquet.tmp")
            after.to_parquet(tmp, index=False, compression="zstd")
            _atomic_replace(tmp, path)

    verb = "đã sửa" if apply_changes else "sẽ sửa"
    print(f"{len(files)} partition, {touched} partition {verb}")
    for col, n in sorted(totals.items()):
        print(f"  {col}: {n} ô")
    if not apply_changes:
        print("(dry-run - chưa ghi gì; chạy lại với --apply để ghi)")
    return totals


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts", default=str(ROOT / "data" / "parts"))
    ap.add_argument("--map", default=str(ROOT / "data" / "berth_map.csv"))
    ap.add_argument("--apply", action="store_true",
                    help="ghi thật; mặc định chỉ dry-run")
    ap.add_argument("--dry-run", action="store_true",
                    help="chỉ báo cáo (mặc định); có mặt để lệnh đọc rõ ý")
    args = ap.parse_args(argv)
    run(args.parts, args.map, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
