"""Parse the HCM port-authority ship-schedule HTML into raw string rows.

The page is ASP.NET WebForms markup (see `scraper/hcm/fetch.py` and the
addendum spec at `docs/superpowers/specs/2026-08-14-hcm-port-addendum.md`
for the POST recipe used to fetch a given date). Three data tables carry a
stable `id`, which is a far more reliable section marker than heading text:

    ctl22_GridView_TauDen       -> tàu vào    ("tau_vao")
    ctl22_GridView_TauRoi       -> tàu rời    ("tau_roi")
    ctl22_GridView_TauDiChuyen  -> tàu di chuyển ("tau_di_chuyen")

Verified against the live page on 2026-08-15 across four dates
(2026-08-14, 2025-07-01, 2024-01-01, 2023-01-01): all three tables are
always present with these ids, in this column shape. Arrivals and
movements have 14 columns; departures have only 13 - the source's own
header row lists a single "Dự kiến rời SG" time column for departures,
not the two separate arrival/departure time columns the addendum spec's
summary implied. Trust the header row observed on the page, not that
summary.

`BeautifulSoup(html, "lxml")` is required, matching the Hải Phòng lesson
that `html.parser` can silently mangle malformed table markup.
"""

import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup

_DATE_INPUT_ID = "ctl22_txtDate_dateInput"

_TABLE_ID_TO_SECTION = {
    "ctl22_GridView_TauDen": "tau_vao",
    "ctl22_GridView_TauRoi": "tau_roi",
    "ctl22_GridView_TauDiChuyen": "tau_di_chuyen",
}

SECTIONS = ("tau_vao", "tau_roi", "tau_di_chuyen")

# Column keys, in on-page order, per section. Derived from the header row
# text observed live (see module docstring), folded to ascii snake_case.
_SHARED_PREFIX = [
    "stt", "ten_tau", "quoc_tich", "ho_hieu", "dwt",
    "chieu_dai", "mon_nuoc", "loai_hang_hoa",
]
_SHARED_SUFFIX = ["tau_lai", "dai_ly", "tuyen_luong"]

_ARRIVAL_COLUMNS = _SHARED_PREFIX + [
    "vi_tri_neo_dau", "du_kien_den_vt", "thoi_gian_roi_vt",
] + _SHARED_SUFFIX

_DEPARTURE_COLUMNS = _SHARED_PREFIX + [
    "vi_tri_neo_dau", "du_kien_roi_sg",
] + _SHARED_SUFFIX

_MOVEMENT_COLUMNS = _SHARED_PREFIX + [
    "vi_tri_neo_dau_tu", "vi_tri_neo_dau_den", "gio_doi",
] + _SHARED_SUFFIX

COLUMNS = {
    "tau_vao": _ARRIVAL_COLUMNS,
    "tau_roi": _DEPARTURE_COLUMNS,
    "tau_di_chuyen": _MOVEMENT_COLUMNS,
}

# Superset of every column key across all sections, so every returned row
# dict has the same keys (missing ones set to None).
_ALL_KEYS = sorted(set(_ARRIVAL_COLUMNS) | set(_DEPARTURE_COLUMNS) | set(_MOVEMENT_COLUMNS))


class DateMismatchError(Exception):
    """The page returned a different date than the one requested."""


class UnknownSectionError(Exception):
    """A grid table's `id` did not match any known section.

    Silently skipping such a table would drop every row in it without a
    trace. If the source renames/re-ids a grid, this must fail loudly
    instead, mirroring the Hải Phòng parser's `UnknownSectionError`.
    """


def parse_header_date(html):
    """Read the selected date from the Telerik date-input's `value` attribute.

    This is the same field the fetch-layer POST verifies against (see
    `scraper/hcm/fetch.py`), so a mismatch here is exactly the failure mode
    that guard exists to catch.
    """
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("input", id=_DATE_INPUT_ID)
    value = tag.get("value") if tag is not None else None
    if not value:
        raise ValueError(
            f"no #{_DATE_INPUT_ID} input with a value found in page"
        )
    day, month, year = (int(part) for part in value.strip().split("/"))
    return datetime(year, month, day).date()


def _fold(text):
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.strip().lower()


def parse_page(html, expected_date=None):
    """Return a list of raw row dicts, one per vessel movement.

    Every value is a string, or None for a column absent from that row's
    section - no type conversion happens here, that is a later stage.

    Raises DateMismatchError when `expected_date` is given and the page's
    date-input disagrees, and UnknownSectionError when a grid table's `id`
    does not match a known section (rather than silently dropping its rows).
    """
    page_date = parse_header_date(html)
    if expected_date is not None and page_date != expected_date:
        raise DateMismatchError(
            f"requested {expected_date} but page says {page_date}"
        )

    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", class_="Grid")

    resolved = []
    for index, table in enumerate(tables):
        table_id = table.get("id")
        section = _TABLE_ID_TO_SECTION.get(table_id)
        if section is None:
            raise UnknownSectionError(
                f"Grid table #{index} on {page_date} has id {table_id!r}, "
                f"which does not match any known section "
                f"{sorted(_TABLE_ID_TO_SECTION.values())}. The source may "
                "have renamed/re-ided a grid; silently skipping this table "
                "would drop its rows without a trace."
            )
        resolved.append(section)

    seen = {}
    duplicates = {}
    for index, section in enumerate(resolved):
        if section in seen:
            duplicates.setdefault(section, [seen[section]]).append(index)
        else:
            seen[section] = index
    if duplicates:
        detail = ", ".join(
            f"{section!r} (tables {idxs})" for section, idxs in duplicates.items()
        )
        raise UnknownSectionError(
            f"on {page_date}: {len(tables)} Grid tables resolved to the "
            f"same section more than once: {detail}."
        )

    rows = []
    for index, table in enumerate(tables):
        section = resolved[index]
        columns = COLUMNS[section]
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) != len(columns):
                continue  # header row (th cells), or an unrecognised shape
            values = [td.get_text(strip=True) for td in cells]
            row = {key: None for key in _ALL_KEYS}
            row.update(dict(zip(columns, values)))
            row["section"] = section
            row["plan_date"] = page_date
            rows.append(row)
    return rows
