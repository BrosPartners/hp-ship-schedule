"""Daily refresh: yesterday, today, tomorrow.

Fetching three days in one run is what produces multiple snapshots per
plan_date without needing a second cron entry.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from scraper.aggregate import build_all
from scraper.fetch import fetch_day
from scraper.normalize import apply_berth_map, build_records, load_berth_map
from scraper.parse import parse_page
from scraper.store import mark_crawled_empty, upsert, write_manifest

ROOT = Path(__file__).resolve().parent.parent
START = date(2023, 1, 1)
DEFAULT_PATHS = {
    "parquet": ROOT / "data" / "ship_plan.parquet",
    "manifest": ROOT / "data" / "manifest.json",
    "agg": ROOT / "data" / "agg",
}


def run(paths=None, fetcher=fetch_day, today=None, now=None):
    paths = paths or DEFAULT_PATHS
    today = today or date.today()
    crawled_at = now or datetime.now()
    targets = [today - timedelta(days=1), today, today + timedelta(days=1)]

    map_path = ROOT / "data" / "berth_map.csv"
    if not map_path.exists():
        raise FileNotFoundError(
            f"Berth map not found at {map_path}. Ingesting without it would "
            "silently zero out berth attribution (from_berth/to_berth/"
            "from_ticker/to_ticker/from_type/to_type/is_domestic) for every "
            "record in this run."
        )
    berth_map = load_berth_map(map_path)

    done, empty, failed, rows = 0, 0, [], 0
    for target in targets:
        try:
            raw = parse_page(fetcher(target), expected_date=target)
        except Exception as exc:                      # noqa: BLE001
            print(f"{target}: FAILED {exc}")
            failed.append(target)
            continue

        if not raw:
            # A future target (typically tomorrow) coming back empty usually
            # means its plan is not published yet, not that it was crawled
            # and genuinely had no rows. Only record it as empty once it is
            # not in the future relative to this run's `today`.
            if target <= today:
                mark_crawled_empty(paths["manifest"], target)
            empty += 1
            print(f"{target}: empty")
            continue

        records = apply_berth_map(build_records(raw, crawled_at), berth_map)
        written = upsert(paths["parquet"], records)
        rows += written
        done += 1
        print(f"{target}: {written} rows")

    if Path(paths["parquet"]).exists():
        build_all(paths["parquet"], paths["agg"])
    # Pass `today` explicitly (not max(end, date.today())) so missing_days is
    # always computed through the actual current day, and stays hermetic
    # under tests that pin `today`.
    write_manifest(paths["parquet"], paths["manifest"], START, today)

    result = {"targets": targets, "days_done": done, "days_empty": empty,
              "days_failed": failed, "rows": rows}
    print(json.dumps({**result,
                      "targets": [d.isoformat() for d in targets],
                      "days_failed": [d.isoformat() for d in failed]}, indent=2))
    return result


def main():
    result = run()
    # Tomorrow's plan is often not published yet; today and yesterday must work.
    if len(result["days_failed"]) >= 2:
        raise SystemExit(
            f"too many failures: {[d.isoformat() for d in result['days_failed']]}"
        )


if __name__ == "__main__":
    main()
