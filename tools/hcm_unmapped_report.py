"""Rank the raw HCM from_position/to_position values by frequency so mapping
effort goes where it pays. Modelled directly on `tools/unmapped_report.py`
(Hai Phong) - see that module's docstring for the rationale; this is the
HCM equivalent, reading `scraper.hcm.normalize.load_berth_map` and the
`from_position`/`to_position` columns instead of `from_raw`/`to_raw`.

HCM has ~530 distinct position strings versus Hai Phong's ~30, so mapping
was deliberately stopped at the top ~113 (80% of slots) / ~176 (90%) -
the long tail stays unmapped by design (see `data/hcm/berth_map_notes.md`).
"""

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.hcm.normalize import load_berth_map  # noqa: E402
from scraper.store import latest_snapshot, load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(parts_dir=None, berth_map_path=None, out_path=None):
    """Regenerate `data/hcm/unmapped_report.csv` from the current dataset.

    Uses the latest-snapshot basis (one row per plan_date, its newest
    crawl), matching `tools/unmapped_report.py` so the two datasets' notion
    of "coverage" is computed the same way.
    """
    parts_dir = Path(parts_dir) if parts_dir is not None else ROOT / "data" / "hcm" / "parts"
    berth_map_path = (
        Path(berth_map_path) if berth_map_path is not None
        else ROOT / "data" / "hcm" / "berth_map.csv"
    )
    out = Path(out_path) if out_path is not None else ROOT / "data" / "hcm" / "unmapped_report.csv"

    df = latest_snapshot(load(parts_dir))
    known = set(load_berth_map(berth_map_path)) if berth_map_path.exists() else set()

    counts = Counter()
    for column in ("from_position", "to_position"):
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
