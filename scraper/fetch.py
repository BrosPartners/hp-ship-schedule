"""HTTP access to the Hải Phòng port authority ship-plan page."""

import gzip
import re
import time
from datetime import date
from pathlib import Path

import requests

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
    url = f"{BASE_URL}?d={offset_for(target)}"

    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        if path.exists() and not force:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                cached_html = fh.read()
            if _looks_like_valid_page(cached_html):
                return cached_html
            # Poisoned cache file - fall through and refetch.

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

    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)

    time.sleep(delay)
    return html
