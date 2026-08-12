"""Rank the raw Từ/Đến values by frequency so mapping effort goes where it pays.

Roughly 30 values cover ~95% of movements; the long tail is deliberately left
unmapped rather than guessed at.
"""

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.normalize import load_berth_map  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    df = pd.read_parquet(ROOT / "data" / "ship_plan.parquet")
    map_path = ROOT / "data" / "berth_map.csv"
    known = set(load_berth_map(map_path)) if map_path.exists() else set()

    counts = Counter()
    for column in ("from_raw", "to_raw"):
        for value in df[column].dropna():
            counts[str(value).strip().upper()] += 1

    total = sum(counts.values())
    rows, running = [], 0
    for name, n in counts.most_common():
        running += n
        rows.append({
            "raw_name": name, "n": n,
            "pct": round(100 * n / total, 3),
            "cum_pct": round(100 * running / total, 2),
            "mapped": name in known,
        })
    out = ROOT / "data" / "unmapped_report.csv"
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    unmapped_share = 100 * sum(r["n"] for r in rows if not r["mapped"]) / total
    print(f"{len(rows)} distinct values, {total:,} slots, "
          f"{unmapped_share:.1f}% of slots unmapped -> {out}")


if __name__ == "__main__":
    main()
