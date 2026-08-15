"""Daily refresh for the HCM City port authority dataset: yesterday, today,
tomorrow.

Modelled closely on `scraper/daily.py` (Hai Phong) - see that module's
docstring for the rationale behind each hardening decision baked in here:

- Fetching three days in one run is what produces multiple snapshots per
  plan_date without needing a second cron entry (tomorrow's plan is
  published early and revised later).
- `crawled_at` is stamped once per run, before the loop:
  `latest_snapshot` compares exact timestamp equality, so per-row stamps
  would silently drop rows.
- Fetch, parse AND storage (`upsert`) all sit inside the per-day try, so a
  storage error can never abort the whole run (this exact bug once cost
  the Hai Phong side a full run).
- A genuinely empty day is recorded as empty via `mark_crawled_empty`, so
  "crawled and empty" stays distinguishable from "never crawled" - but
  never for a day in the future relative to this run's `today`, since an
  unpublished tomorrow-plan must self-heal once it appears.
- A bounded, oldest-first slice of `manifest["missing_days"]` is retried
  each run so an outage does not leave a permanent hole.
- Missing `data/hcm/berth_map.csv` raises before any fetching - ingesting
  without it would silently null out every mapping column.

HCM-specific: `scraper.hcm.fetch.fetch_day` reuses a harvested ASP.NET
form/session across days for efficiency (see `scraper/hcm/fetch.py`). Its
`HcmClient` already re-harvests and retries once on a stale-viewstate
failure, so a 3-day run here is unaffected; nothing extra is needed on
this side for that to self-heal.
"""

import json
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path

from scraper.hcm.aggregate import build_all
from scraper.hcm.fetch import fetch_day
from scraper.hcm.normalize import apply_berth_map, build_records, load_berth_map
from scraper.hcm.parse import parse_page
from scraper.hcm.store import mark_crawled_empty, upsert, write_manifest

ROOT = Path(__file__).resolve().parent.parent.parent
START = date(2023, 1, 1)
DEFAULT_PATHS = {
    "parquet": ROOT / "data" / "hcm" / "parts",
    "manifest": ROOT / "data" / "hcm" / "manifest.json",
    "agg": ROOT / "data" / "hcm" / "agg",
}

# Capped small so a multi-day outage's backfill stays fast and polite to the
# source: this runs every day alongside the 3 rolling targets, not as a
# one-off. Oldest first, so the longest-standing hole is healed first.
MAX_MISSING_RETRIES = 5

# `force=True` bypasses the gzip cache so a revised tomorrow-plan is always
# observed live, matching the Hai Phong default fetcher.
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

    map_path = ROOT / "data" / "hcm" / "berth_map.csv"
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
        never stops the remaining ones."""
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

    # Retry a bounded number of previously-missing days, oldest first.
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
    # Pass `today` explicitly so missing_days is always computed through the
    # actual current day, and stays hermetic under tests that pin `today`.
    write_manifest(paths["parquet"], paths["manifest"], START, today)

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
    # A single failed day among the 3 rolling targets means the day is
    # genuinely lost until it surfaces in `missing_days` and gets picked up
    # by the bounded retry above. Worth a CI issue every time, not just when
    # 2+ of the 3 fail (see scraper/daily.py for the same reasoning).
    #
    # Failures among the *retried* missing-days are deliberately excluded:
    # those are best-effort, capped, oldest-first attempts at old holes.
    if result["days_failed"]:
        raise SystemExit(
            f"HCM crawl failed for: {[d.isoformat() for d in result['days_failed']]}"
        )


if __name__ == "__main__":
    main()
