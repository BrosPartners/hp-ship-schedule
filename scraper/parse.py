"""Parse the ship-plan HTML into raw string rows.

Two hard-won facts, both verified against the live page on 2026-08-12:

1. The markup is malformed (86 stray `</td></td>` and a missing `</td>` in the
   last table). `BeautifulSoup(html, "html.parser")` collapses the first three
   tables to a single 12-cell row and glues STT onto the time in the fourth,
   *without raising*. Only "lxml" recovers correctly.
2. The `qua_luong` table has a different, 10-column schema.
"""

import html as htmllib
import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup

SECTIONS = ("roi_cang", "di_chuyen", "vao_cang", "qua_luong")

_SECTION_LABELS = {
    "ke hoach tau roi cang": "roi_cang",
    "ke hoach tau di chuyen": "di_chuyen",
    "ke hoach tau vao cang": "vao_cang",
    "ke hoach tau qua luong": "qua_luong",
}

_WIDE = ["stt", "time", "vessel", "draft", "loa", "dwt", "gt",
         "tugs", "channel", "from", "to", "agent", "pilot"]
_NARROW = ["stt", "time", "vessel", "draft", "loa", "dwt",
           "channel", "from", "to", "pilot"]

COLUMNS = {
    "roi_cang": _WIDE,
    "di_chuyen": _WIDE,
    "vao_cang": _WIDE,
    "qua_luong": _NARROW,
}

_ALL_KEYS = _WIDE  # superset; narrow rows get None for the missing keys

_DATE_RE = re.compile(r"NG[ÀA]Y\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)


class DateMismatchError(Exception):
    """The page returned a different date than the offset was meant to select."""


class UnknownSectionError(Exception):
    """A `cssTD` table's nearest preceding heading did not match a known section.

    Silently skipping such a table (the old behaviour) drops every row in it
    without a trace: the crawl succeeds, the manifest records the day as
    covered, and no issue is opened. If the source renames a section caption,
    this must fail loudly instead so the day lands in `days_failed` and CI
    opens an issue.
    """


def _fold(text):
    """Lowercase, strip diacritics and collapse whitespace, for label matching."""
    text = htmllib.unescape(text or "")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_header_date(html):
    """Read the date out of 'KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY dd/mm/yyyy'."""
    match = _DATE_RE.search(htmllib.unescape(html))
    if not match:
        raise ValueError("no 'NGÀY dd/mm/yyyy' header found in page")
    day, month, year = (int(g) for g in match.groups())
    return datetime(year, month, day).date()


def _section_of(table):
    """Nearest preceding text node that names a section, or None."""
    for text in table.find_all_previous(string=True):
        label = _SECTION_LABELS.get(_fold(text))
        if label:
            return label
    return None


def _nearest_heading_text(table):
    """Nearest non-blank preceding text node, for the UnknownSectionError message."""
    for text in table.find_all_previous(string=True):
        if _fold(text):
            return str(text).strip()
    return None


def parse_page(html, expected_date=None):
    """Return a list of raw row dicts, one per vessel movement.

    Raises DateMismatchError when `expected_date` is given and the page header
    disagrees — the site is addressed by relative day offset, so a stale or
    shifted response is a real failure mode, not a curiosity.
    """
    page_date = parse_header_date(html)
    if expected_date is not None and page_date != expected_date:
        raise DateMismatchError(
            f"requested {expected_date} but page says {page_date}"
        )

    soup = BeautifulSoup(html, "lxml")
    rows = []
    for index, table in enumerate(soup.find_all("table", class_="cssTD")):
        section = _section_of(table)
        if section is None:
            heading = _nearest_heading_text(table)
            raise UnknownSectionError(
                f"cssTD table #{index} on {page_date}: nearest preceding "
                f"heading {heading!r} does not match any known section "
                f"{sorted(_SECTION_LABELS.values())}. The source may have "
                "renamed a section caption; silently skipping this table "
                "would drop its rows without a trace."
            )
        columns = COLUMNS[section]
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) != len(columns):
                continue          # header row, or a shape we do not recognise
            values = [htmllib.unescape(td.get_text(strip=True)) for td in cells]
            row = {key: None for key in _ALL_KEYS}
            row.update(dict(zip(columns, values)))
            row["section"] = section
            row["plan_date"] = page_date
            rows.append(row)
    return rows
