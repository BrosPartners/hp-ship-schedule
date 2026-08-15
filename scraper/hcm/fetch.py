"""HTTP access to the HCM City port authority ship-schedule page.

Unlike Hải Phòng's simple `?d=<offset>` GET, this page is ASP.NET
WebForms with a Telerik RadDatePicker and has no GET parameter for the
date - a specific POST postback recipe is required. See the addendum spec
at `docs/superpowers/specs/2026-08-14-hcm-port-addendum.md` for how this
was reverse-engineered; do not simplify it:

1. GET the page once and harvest every `input`/`select`/`textarea` that
   has a `name` (skipping unchecked checkboxes/radios).
2. POST back to the same URL with ALL of those fields, overriding
   `__EVENTTARGET`, `__EVENTARGUMENT`, both date fields, and the
   `ClientState` JSON. Posting only the hidden `__VIEWSTATE`-style
   fields silently returns today's page with HTTP 200.
3. Omitting `minDateStr`/`maxDateStr` from the ClientState JSON makes the
   server return HTTP 500.
4. Verify by reading the returned page's date-input value - a wrong
   payload returns today's page with HTTP 200, so status alone proves
   nothing. `parse_page`'s DateMismatchError is that guard.
"""

import gzip
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scraper.hcm.parse import DateMismatchError, parse_header_date, parse_page

BASE_URL = "https://cangvuhanghaitphcm.gov.vn/index.aspx?cat=2033&page=shipschedule"
USER_AGENT = "hp-ship-schedule/1.0 (research; contact tri.le@brospartners.com)"
DEFAULT_CACHE = Path(__file__).resolve().parent.parent.parent / "cache" / "hcm"

_EVENT_TARGET_FIELD = "ctl22$txtDate"
_DATE_FIELD = "ctl22$txtDate"
_DATE_INPUT_FIELD = "ctl22$txtDate$dateInput"
_CLIENT_STATE_FIELD = "ctl22_txtDate_dateInput_ClientState"


def _cache_path(cache_dir, target):
    return Path(cache_dir) / f"{target.isoformat()}.html.gz"


def _harvest_form_fields(html):
    """Every named input/select/textarea on the page, unchecked boxes skipped."""
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for tag in soup.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name:
            continue
        field_type = (tag.get("type") or "").lower()
        if field_type in ("checkbox", "radio") and not tag.has_attr("checked"):
            continue
        if tag.name == "select":
            selected = tag.find("option", selected=True) or tag.find("option")
            fields[name] = selected.get("value", selected.get_text()) if selected else ""
        elif tag.name == "textarea":
            fields[name] = tag.get_text()
        else:
            fields[name] = tag.get("value", "")
    return fields


def _build_payload(base_fields, target):
    date_str = target.strftime("%d/%m/%Y")
    iso_midnight = f"{target.isoformat()}-00-00-00"
    payload = dict(base_fields)
    payload["__EVENTTARGET"] = _EVENT_TARGET_FIELD
    payload["__EVENTARGUMENT"] = ""
    payload[_DATE_FIELD] = date_str
    payload[_DATE_INPUT_FIELD] = date_str
    payload[_CLIENT_STATE_FIELD] = json.dumps({
        "enabled": True,
        "emptyMessage": "",
        "validationText": iso_midnight,
        "valueAsString": iso_midnight,
        "minDateStr": "1980-01-01-00-00-00",
        "maxDateStr": "2099-12-31-00-00-00",
        "lastSetTextBoxValue": date_str,
    })
    return payload


def _fetch_live(target):
    session = requests.Session()
    get_resp = session.get(BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    get_resp.raise_for_status()
    get_resp.encoding = get_resp.apparent_encoding or "utf-8"

    fields = _harvest_form_fields(get_resp.text)
    payload = _build_payload(fields, target)

    post_resp = session.post(
        BASE_URL, data=payload, headers={"User-Agent": USER_AGENT}, timeout=60
    )
    post_resp.raise_for_status()
    post_resp.encoding = post_resp.apparent_encoding or "utf-8"
    html = post_resp.text

    # Raises DateMismatchError if the payload didn't land - the failure
    # mode is HTTP 200 with today's page, so status alone proves nothing.
    parse_page(html, expected_date=target)
    return html


def fetch_day(target, cache_dir=DEFAULT_CACHE, delay=1.5, force=False):
    """Return the HTML for `target`, using a gzip cache when available.

    Before being trusted or cached, a response (fresh or cached) must
    carry the requested date in its date-input field - a cached file
    whose date does not match `target` is treated as a cache miss and
    refetched, the same guard `scraper/fetch.py` (Hải Phòng) applies
    after 79 days of cache poisoning from a looser check.
    """
    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        if path.exists() and not force:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                cached_html = fh.read()
            try:
                cached_date = parse_header_date(cached_html)
            except ValueError:
                cached_date = None
            if cached_date == target:
                return cached_html
            # Poisoned/mismatched cache file - fall through and refetch live.

    html = _fetch_live(target)

    if cache_dir is not None:
        path = _cache_path(cache_dir, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)

    time.sleep(delay)
    return html
