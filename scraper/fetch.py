"""HTTP access to the Hải Phòng port authority ship-plan page."""

import gzip
import time
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx"
USER_AGENT = "hp-ship-schedule/1.0 (research; contact tri.le@brospartners.com)"
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "cache"


def offset_for(target, today=None):
    """Day offset the site expects for `target`. Always computed, never stored."""
    if today is None:
        today = date.today()
    return (target - today).days


def _cache_path(cache_dir, target):
    return Path(cache_dir) / f"{target.isoformat()}.html.gz"


def fetch_day(target, cache_dir=DEFAULT_CACHE, delay=1.5, force=False):
    """Return the HTML for `target`, using a gzip cache when available.

    The cache means a parser change can be re-applied offline instead of
    re-crawling 1300 pages.
    """
    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        if path.exists() and not force:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                return fh.read()

    url = f"{BASE_URL}?d={offset_for(target)}"
    last_error = None
    for attempt in range(4):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
            break
        except Exception as exc:            # noqa: BLE001 - retry on any transport error
            last_error = exc
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"failed to fetch {url}: {last_error}")

    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)

    time.sleep(delay)
    return html
