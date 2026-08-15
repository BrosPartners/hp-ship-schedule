"""One-shot historical backfill for the HCM City port authority, resumable
by design. Modelled on `scraper/backfill.py` (Hai Phong); see that module's
docstring for why resumability matters at this request volume.

Four hardening lessons paid for in production on the Hai Phong side, built
in here from the start (see the addendum spec, section 5):

1. Resumable: `days_to_do` skips days already stored (present in the
   parquet) or recorded as legitimately empty (in the manifest); a day
   that only failed is retried on the next run.
2. A failing day must not abort the run: fetch, parse, AND storage
   (`upsert`) are all inside the per-day try/except.
3. "Crawled and empty" stays distinguishable from "never crawled" via
   `mark_crawled_empty`.
4. `parse_page(html, expected_date=...)` (stage 1) verifies the returned
   page's date-input value matches the requested date before this module
   ever sees the rows, guarding against the wrong-day-HTTP-200 failure
   mode described in the addendum spec.
"""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from scraper.hcm.fetch import fetch_day
from scraper.hcm.normalize import build_records
from scraper.hcm.parse import parse_page
from scraper.hcm.store import mark_crawled_empty, upsert, write_manifest
from scraper.store import load

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATHS = {
    "parquet": ROOT / "data" / "hcm" / "parts",
    "manifest": ROOT / "data" / "hcm" / "manifest.json",
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


def run(start, end, paths=None, fetcher=fetch_day, now=None, today=None):
    paths = paths or DEFAULT_PATHS
    crawled_at = now or datetime.now()
    today = today or date.today()
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

            records = build_records(raw, crawled_at)
            written = upsert(paths["parquet"], records)
            rows += written
            done += 1
            print(f"{target}: {written} rows")
        except Exception as exc:                     # noqa: BLE001
            # Storage (upsert) errors land here too, not just fetch/parse -
            # Hai Phong lost a 40-minute run to a storage error that sat
            # outside this try.
            print(f"{target}: FAILED {exc}")
            failed.append(target)
            continue

    # Pass `today`, not `end`: running a past `--end` must not rewrite
    # days_expected/missing_days as if the dataset stopped there.
    write_manifest(paths["parquet"], paths["manifest"], start, today)

    return {"days_done": done, "days_empty": empty,
            "days_failed": failed, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description="Backfill HCM ship plans")
    ap.add_argument("--start", default=START.isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--delay", type=float, default=1.5,
                     help="seconds to wait between requests (politeness)")
    args = ap.parse_args()

    def fetcher(target):
        return fetch_day(target, delay=args.delay)

    result = run(date.fromisoformat(args.start), date.fromisoformat(args.end),
                 fetcher=fetcher)
    print(json.dumps({**result, "days_failed": [d.isoformat()
                                                for d in result["days_failed"]]},
                     indent=2))


if __name__ == "__main__":
    main()
