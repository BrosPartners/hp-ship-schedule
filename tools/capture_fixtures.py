"""Download the HTML fixtures the offline test suite runs against.

Run once, with network. Fixture dates are chosen to cover the known shape
variations, not because they are interesting days.
"""

import gzip
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.fetch import fetch_day  # noqa: E402

FIXTURES = {
    # name                 date              why this date
    "2026-08-11_full":     date(2026, 8, 11),   # 4 tables, 86 rows, malformed </td></td>
    "2023-03-15_normal":   date(2023, 3, 15),   # mid-backfill sanity check
    "2021-02-19_3tables":  date(2021, 2, 19),   # only 3 tables - missing qua_luong
    "2023-01-22_tet":      date(2023, 1, 22),   # Tết day - candidate empty day
}

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, target in FIXTURES.items():
        html = fetch_day(target, cache_dir=None, delay=1.5)
        path = OUT / f"{name}.html.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)
        print(f"{path.name}: {len(html):,} chars")


if __name__ == "__main__":
    main()
