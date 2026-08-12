"""One-shot historical backfill, resumable by design.

~1300 requests at 1.5s each is roughly 40 minutes, so this must survive a
dropped connection without redoing completed work.
"""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from scraper.fetch import fetch_day
from scraper.normalize import build_records
from scraper.parse import parse_page
from scraper.store import load, mark_crawled_empty, upsert, write_manifest

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATHS = {
    "parquet": ROOT / "data" / "ship_plan.parquet",
    "manifest": ROOT / "data" / "manifest.json",
}
START = date(2023, 1, 1)


def days_to_do(start, end, manifest_path, parquet_path):
    """Days in [start, end] that are neither stored nor known-empty."""
    df = load(parquet_path)
    present = set()
    if not df.empty:
        present = {pd.Timestamp(d).date() for d in df["plan_date"]}

    empty = set()
    mpath = Path(manifest_path)
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        empty = {date.fromisoformat(d) for d in manifest.get("empty_days", [])}

    todo, cursor = [], start
    while cursor <= end:
        if cursor not in present and cursor not in empty:
            todo.append(cursor)
        cursor += timedelta(days=1)
    return todo


def run(start, end, paths=None, fetcher=fetch_day, now=None):
    paths = paths or DEFAULT_PATHS
    crawled_at = now or datetime.now()
    todo = days_to_do(start, end, paths["manifest"], paths["parquet"])

    done, empty, failed, rows = 0, 0, [], 0
    for target in todo:
        try:
            html = fetcher(target)
            raw = parse_page(html, expected_date=target)

            if not raw:
                mark_crawled_empty(paths["manifest"], target)
                empty += 1
                print(f"{target}: empty")
                continue

            written = upsert(paths["parquet"], build_records(raw, crawled_at))
            rows += written
            done += 1
            print(f"{target}: {written} rows")
        except Exception as exc:                     # noqa: BLE001
            print(f"{target}: FAILED {exc}")
            failed.append(target)
            continue

    write_manifest(paths["parquet"], paths["manifest"], start, end)
    return {"days_done": done, "days_empty": empty,
            "days_failed": failed, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description="Backfill Hai Phong ship plans")
    ap.add_argument("--start", default=START.isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    args = ap.parse_args()
    result = run(date.fromisoformat(args.start), date.fromisoformat(args.end))
    print(json.dumps({**result, "days_failed": [d.isoformat()
                                                for d in result["days_failed"]]},
                     indent=2))


if __name__ == "__main__":
    main()
