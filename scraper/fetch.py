"""HTTP access to the Hải Phòng port authority ship-plan page."""

import gzip
import re
import time
from datetime import date
from pathlib import Path

import requests

from scraper.parse import parse_header_date

BASE_URL = "https://csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx"
USER_AGENT = "hp-ship-schedule/1.0 (research; contact tri.le@brospartners.com)"
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "cache"

# Every valid ship-plan page carries its own date header, e.g.
# "KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 12/08/2026" (tolerating the missing-diacritic
# "NGAY" variant). Its presence is the marker used to reject WAF
# interstitials, truncated responses, or other non-ship-plan HTML that still
# comes back with HTTP 200 - even a legitimately empty day still renders the
# full page shell with this header, so this check does not exclude it.
_DATE_HEADER_RE = re.compile(r"NG[AÀ]Y\s+\d{1,2}/\d{1,2}/\d{4}", re.IGNORECASE)


def _looks_like_valid_page(html):
    return bool(_DATE_HEADER_RE.search(html))


def offset_for(target, today=None):
    """Day offset the site expects for `target`. Always computed, never stored."""
    if today is None:
        today = date.today()
    return (target - today).days


def _cache_path(cache_dir, target):
    return Path(cache_dir) / f"{target.isoformat()}.html.gz"


# The site interprets `d=<offset>` relative to *its own* idea of today, which
# can lag a few minutes behind the local machine's midnight rollover. Trusting
# `date.today()` around that window sends every request off by one day (see
# the 154-day backfill incident this module was patched for). Calibrating
# against the server's own `d=0` response avoids that - but only once per
# process: memoized here so a 1300-day backfill does one calibration request,
# not one per day.
_server_today_cache = None


def reset_server_today_cache(value=None):
    """Clear (or force-set) the memoized server day. Exists for tests."""
    global _server_today_cache
    _server_today_cache = value


def _server_today():
    """The server's current day, per its own `d=0` response. Memoized."""
    global _server_today_cache
    if _server_today_cache is None:
        url = f"{BASE_URL}?d=0"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        _server_today_cache = parse_header_date(resp.text)
    return _server_today_cache


def fetch_day(target, cache_dir=DEFAULT_CACHE, delay=1.5, force=False):
    """Return the HTML for `target`, using a gzip cache when available.

    The cache means a parser change can be re-applied offline instead of
    re-crawling 1300 pages.

    Before being trusted or cached, a response (whether freshly fetched or
    read from the cache) must carry the page's own date header. A cached
    file that fails this check is treated as a cache miss and refetched.

    `delay` only throttles after a live fetch; a cache hit returns
    immediately without sleeping.
    """
    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        if path.exists() and not force:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                cached_html = fh.read()
            if _looks_like_valid_page(cached_html):
                try:
                    cached_date = parse_header_date(cached_html)
                except ValueError:
                    cached_date = None
                if cached_date == target:
                    return cached_html
            # Poisoned cache file (missing header, or header date doesn't
            # match the requested day - e.g. the midnight-lag bug that
            # poisoned 79 cache files) - fall through and refetch live.

    # Calibrate against the server's clock only now that a live fetch is
    # actually about to happen - a cache hit above returns before this runs.
    offset = offset_for(target, _server_today())
    url = f"{BASE_URL}?d={offset}"

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
            if attempt < 3:
                time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"failed to fetch {url}: {last_error}")

    if not _looks_like_valid_page(html):
        raise RuntimeError(
            f"unexpected response from {url}: page is missing its date header; "
            f"first 200 chars: {html[:200]!r}"
        )

    live_date = parse_header_date(html)
    if live_date != target:
        raise RuntimeError(
            f"day-offset mismatch from {url}: requested {target} (offset {offset}) "
            f"but the page carries the header date {live_date}"
        )

    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)

    time.sleep(delay)
    return html
