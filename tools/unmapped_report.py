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
from scraper.store import latest_snapshot, load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(parts_dir=None, berth_map_path=None, out_path=None):
    """Regenerate `unmapped_report.csv` from the current partitioned dataset.

    Defaults read from `ROOT` (module-level, so tests can monkeypatch it) -
    the same layout the standalone CLI has always used. `parts_dir` /
    `berth_map_path` / `out_path` let a caller (the daily job, see
    `scraper/daily.py`) point this at a different data root without
    disturbing that default, e.g. so a test run does not overwrite the
    repo's real `data/unmapped_report.csv`.

    Reads `data/parts/ship_plan_*.parquet` (the partitioned layout), so this
    already works against the post-partitioning dataset unchanged.
    """
    parts_dir = Path(parts_dir) if parts_dir is not None else ROOT / "data" / "parts"
    berth_map_path = (
        Path(berth_map_path) if berth_map_path is not None
        else ROOT / "data" / "berth_map.csv"
    )
    out = Path(out_path) if out_path is not None else ROOT / "data" / "unmapped_report.csv"

    # coverage.json (built by scraper.aggregate) is computed on the latest
    # snapshot per day; reading every snapshot here would make the two
    # unmapped-share numbers drift apart once a day has more than one
    # snapshot, which the daily job now produces routinely.
    df = latest_snapshot(load(parts_dir))
    known = set(load_berth_map(berth_map_path)) if berth_map_path.exists() else set()

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
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    unmapped_share = (
        100 * sum(r["n"] for r in rows if not r["mapped"]) / total if total else 0.0
    )
    print(f"{len(rows)} distinct values, {total:,} slots, "
          f"{unmapped_share:.1f}% of slots unmapped -> {out}")
    return out


if __name__ == "__main__":
    main()
