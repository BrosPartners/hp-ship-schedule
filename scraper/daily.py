"""Daily refresh: yesterday, today, tomorrow.

Fetching three days in one run is what produces multiple snapshots per
plan_date without needing a second cron entry.
"""

import json
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path

from scraper.aggregate import build_all
from scraper.fetch import fetch_day
from scraper.normalize import apply_berth_map, build_records, load_berth_map
from scraper.parse import parse_page
from scraper.store import mark_crawled_empty, upsert, write_manifest

ROOT = Path(__file__).resolve().parent.parent
START = date(2023, 1, 1)
DEFAULT_PATHS = {
    "parquet": ROOT / "data" / "parts",
    "manifest": ROOT / "data" / "manifest.json",
    "agg": ROOT / "data" / "agg",
    "unmapped_report": ROOT / "data" / "unmapped_report.csv",
}

# Capped small so a multi-day outage's backfill stays fast and polite to the
# source: this runs every day alongside the 3 rolling targets, not as a
# one-off. Oldest first, so the longest-standing hole is healed first.
MAX_MISSING_RETRIES = 5

# The README tells the owner to run this locally, where `cache/` is warm from
# earlier runs/backfills. A plain cache hit would re-read yesterday's cached
# page and never observe a revision, so the default fetcher always forces a
# live fetch. CI's cache is cold anyway, so this changes nothing there.
_DEFAULT_FETCHER = partial(fetch_day, force=True)


def _load_missing_days(manifest_path):
    """Oldest-first list of dates previously recorded as missing, or []."""
    path = Path(manifest_path)
    if not path.exists():
        return []
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return sorted(datetime.strptime(d, "%Y-%m-%d").date()
                  for d in manifest.get("missing_days", []))


def run(paths=None, fetcher=_DEFAULT_FETCHER, today=None, now=None):
    paths = paths or DEFAULT_PATHS
    today = today or date.today()
    crawled_at = now or datetime.now()
    targets = [today - timedelta(days=1), today, today + timedelta(days=1)]

    # Read *before* any writing below - `write_manifest` recomputes
    # missing_days from what is actually stored, so this is the last chance
    # to see what a previous run considered missing.
    previously_missing = _load_missing_days(paths["manifest"])
    retry_targets = previously_missing[:MAX_MISSING_RETRIES]

    map_path = ROOT / "data" / "berth_map.csv"
    if not map_path.exists():
        raise FileNotFoundError(
            f"Berth map not found at {map_path}. Ingesting without it would "
            "silently zero out berth attribution (from_berth/to_berth/"
            "from_ticker/to_ticker/from_type/to_type/is_domestic) for every "
            "record in this run."
        )
    berth_map = load_berth_map(map_path)

    def _process(target):
        """Fetch/parse/store one target day. Returns ("done", rows_written),
        ("empty", 0), or (exc, 0) on failure - never raises, so one bad day
        never stops the remaining ones (see backfill.py, which had exactly
        this defect fixed)."""
        try:
            raw = parse_page(fetcher(target), expected_date=target)

            if not raw:
                # A future target (typically tomorrow) coming back empty
                # usually means its plan is not published yet, not that it
                # was crawled and genuinely had no rows. Only record it as
                # empty once it is not in the future relative to this run's
                # `today`.
                if target <= today:
                    mark_crawled_empty(paths["manifest"], target)
                print(f"{target}: empty")
                return "empty", 0

            records = apply_berth_map(build_records(raw, crawled_at), berth_map)
            written = upsert(paths["parquet"], records)
            print(f"{target}: {written} rows")
            return "done", written
        except Exception as exc:                      # noqa: BLE001
            print(f"{target}: FAILED {exc}")
            return exc, 0

    done, empty, failed, rows = 0, 0, [], 0
    for target in targets:
        status, written = _process(target)
        if status == "done":
            done += 1
            rows += written
        elif status == "empty":
            empty += 1
        else:
            failed.append(target)

    # Retry a bounded number of previously-missing days, oldest first. This
    # is what lets a multi-day outage self-heal instead of leaving a
    # permanent hole that only manual backfill would fix. Reported
    # separately from the 3 rolling targets above, since it describes a
    # different thing ("old holes healed today") from "today's rolling
    # crawl worked". A healed day is simply removed from `missing_days` by
    # `write_manifest` below, once it has rows (or is marked empty) on disk.
    retried_healed, retried_failed, retried_rows = [], [], 0
    for target in retry_targets:
        status, written = _process(target)
        if status == "done":
            retried_healed.append(target)
            retried_rows += written
        elif status == "empty":
            retried_healed.append(target)
        else:
            retried_failed.append(target)

    if Path(paths["parquet"]).exists():
        build_all(paths["parquet"], paths["agg"], today=today)
    # Pass `today` explicitly (not max(end, date.today())) so missing_days is
    # always computed through the actual current day, and stays hermetic
    # under tests that pin `today`.
    write_manifest(paths["parquet"], paths["manifest"], START, today)

    # Regenerate the unmapped-berth report against whatever just got
    # written, so newly-appearing raw berth names surface in the quality
    # tab without waiting for a manual re-run of the tool. Gated on the key
    # being present (it is, in DEFAULT_PATHS) so tests that pass a bare
    # {"parquet", "manifest", "agg"} dict - most of them, pointed at a
    # tmp_path - do not also overwrite the repo's real unmapped_report.csv.
    unmapped_report_path = paths.get("unmapped_report")
    if unmapped_report_path is not None:
        from tools.unmapped_report import main as regenerate_unmapped_report
        regenerate_unmapped_report(
            parts_dir=paths["parquet"],
            berth_map_path=map_path,
            out_path=unmapped_report_path,
        )

    result = {
        "targets": targets, "days_done": done, "days_empty": empty,
        "days_failed": failed, "rows": rows,
        "missing_days_retried": retry_targets,
        "missing_days_healed": retried_healed,
        "missing_days_still_failing": retried_failed,
        "missing_days_rows": retried_rows,
    }
    printable = {
        **result,
        "targets": [d.isoformat() for d in targets],
        "days_failed": [d.isoformat() for d in failed],
        "missing_days_retried": [d.isoformat() for d in retry_targets],
        "missing_days_healed": [d.isoformat() for d in retried_healed],
        "missing_days_still_failing": [d.isoformat() for d in retried_failed],
    }
    print(json.dumps(printable, indent=2))
    return result


def main():
    result = run()
    # A single failed day among the 3 rolling targets (yesterday/today/
    # tomorrow) means the day is genuinely lost until it eventually surfaces
    # in `missing_days` and gets picked up by the bounded retry above, which
    # can take days once more than MAX_MISSING_RETRIES holes exist. That is
    # worth a CI issue every time now, not just when 2+ of the 3 fail: the
    # old ">= 2" threshold let a single real failure (a genuine fetch/parse/
    # storage error - as opposed to tomorrow's plan simply not being
    # published yet, which lands in `days_empty`, never in `days_failed`)
    # exit 0 silently.
    #
    # Failures among the *retried* missing-days are deliberately excluded:
    # those are best-effort, capped, oldest-first attempts at old holes, and
    # a source still down for an old day is not a new incident worth paging
    # on top of whatever already caused it to go missing in the first place.
    if result["days_failed"]:
        raise SystemExit(
            f"crawl failed for: {[d.isoformat() for d in result['days_failed']]}"
        )


if __name__ == "__main__":
    main()
