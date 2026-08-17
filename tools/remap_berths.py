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
    python -m tools.remap_berths --dataset hcm --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from scraper import normalize as hp_normalize
from scraper.hcm import normalize as hcm_normalize
from scraper.hcm import store as hcm_store
from scraper.store import _atomic_replace, _normalize_dtypes

ROOT = Path(__file__).resolve().parents[1]

# Hai bộ dữ liệu có bộ cột dẫn xuất khác nhau: Hải Phòng có zone/is_domestic,
# TP.HCM có cluster. Gom vào một bảng để công cụ chỉ có một đường chạy.
DATASETS = {
    "hp": {
        "parts": ROOT / "data" / "parts",
        "map": ROOT / "data" / "berth_map.csv",
        "load_map": hp_normalize.load_berth_map,
        "apply_map": hp_normalize.apply_berth_map,
        "normalize_dtypes": _normalize_dtypes,
        "derived": ["from_berth", "to_berth", "from_ticker", "to_ticker",
                    "from_type", "to_type", "from_zone", "to_zone",
                    "is_domestic"],
    },
    "hcm": {
        "parts": ROOT / "data" / "hcm" / "parts",
        "map": ROOT / "data" / "hcm" / "berth_map.csv",
        "load_map": hcm_normalize.load_berth_map,
        "apply_map": hcm_normalize.apply_berth_map,
        "normalize_dtypes": hcm_store._normalize_dtypes,
        "derived": ["from_berth", "to_berth", "from_cluster", "to_cluster",
                    "from_ticker", "to_ticker", "from_type", "to_type"],
    },
}
DERIVED = DATASETS["hp"]["derived"]


def remap_frame(df, berth_map, spec=None):
    """Return `df` with the derived columns recomputed from the raw values."""
    spec = spec or DATASETS["hp"]
    records = spec["apply_map"](df.to_dict("records"), berth_map)
    return spec["normalize_dtypes"](pd.DataFrame(records)[list(df.columns)])


def _diff(before, after, derived=None):
    """Count changed cells per derived column, treating NaN == NaN as equal."""
    # Compared as plain objects with a null sentinel: the stored frame holds
    # `object`/None while the rebuilt one holds pandas' `string`/<NA>, and an
    # elementwise `==` between those propagates NA instead of returning False,
    # which silently reports "no change" for exactly the rows that changed.
    counts = Counter()
    for col in (derived or DERIVED):
        a = before[col].astype(object).where(before[col].notna(), "\0")
        b = after[col].astype(object).where(after[col].notna(), "\0")
        changed = int((a != b).sum())
        if changed:
            counts[col] = changed
    return counts


def run(parts_dir, map_path, apply_changes, dataset="hp"):
    spec = DATASETS[dataset]
    berth_map = spec["load_map"](map_path)
    files = sorted(Path(parts_dir).glob("*.parquet"))
    if not files:
        raise SystemExit(f"không thấy partition nào trong {parts_dir}")

    totals, touched = Counter(), 0
    for path in files:
        before = pd.read_parquet(path)
        after = remap_frame(before, berth_map, spec)
        counts = _diff(before, after, spec["derived"])
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
    ap.add_argument("--dataset", choices=sorted(DATASETS), default="hp")
    ap.add_argument("--parts")
    ap.add_argument("--map")
    ap.add_argument("--apply", action="store_true",
                    help="ghi thật; mặc định chỉ dry-run")
    ap.add_argument("--dry-run", action="store_true",
                    help="chỉ báo cáo (mặc định); có mặt để lệnh đọc rõ ý")
    args = ap.parse_args(argv)
    spec = DATASETS[args.dataset]
    run(args.parts or str(spec["parts"]), args.map or str(spec["map"]),
        args.apply, args.dataset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
