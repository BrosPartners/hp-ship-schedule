import gzip
from datetime import date
from pathlib import Path

import pytest

from scraper.parse import DateMismatchError, parse_header_date, parse_page

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    with gzip.open(FIXTURES / f"{name}.html.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def test_parse_header_date():
    assert parse_header_date(load("2026-08-11_full")) == date(2026, 8, 11)


def test_row_counts_per_section():
    """Counts verified by hand against the live page on 2026-08-12."""
    rows = parse_page(load("2026-08-11_full"), expected_date=date(2026, 8, 11))
    counts = {}
    for r in rows:
        counts[r["section"]] = counts.get(r["section"], 0) + 1
    assert counts == {
        "roi_cang": 28,
        "di_chuyen": 15,
        "vao_cang": 27,
        "qua_luong": 16,
    }
    assert len(rows) == 86


def test_first_row_of_roi_cang_is_field_aligned():
    """Guards the column mapping: channel/from/to are three distinct fields."""
    rows = parse_page(load("2026-08-11_full"))
    row = next(r for r in rows if r["section"] == "roi_cang" and r["stt"] == "1")
    assert row["time"] == "00:30"
    assert row["vessel"] == "HOANG PHUC 69 (SB)"
    assert row["draft"] == "2,7"
    assert row["loa"] == "79,9"
    assert row["dwt"] == "4.450"
    assert row["gt"] == "1.989"
    assert row["channel"] == "HN"      # channel code, NOT a berth
    assert row["from"] == "CANG 128"
    assert row["to"] == "NINH BINH"
    assert "BẢO KHÁNH" in row["agent"]


def test_qua_luong_has_its_own_10_column_shape():
    """STT and time must not be glued together, and gt/tugs/agent are absent."""
    rows = parse_page(load("2026-08-11_full"))
    row = next(r for r in rows if r["section"] == "qua_luong" and r["stt"] == "1")
    assert row["stt"] == "1"
    assert row["time"] == "06:00"          # regression: html.parser yields '106:00'
    assert row["vessel"] == "SONG TIEN"
    assert row["dwt"] == "3.564"
    assert row["channel"] == "HN"
    assert row["from"] == "HUY VAN"
    assert row["to"] == "CUA LO"
    assert row["gt"] is None
    assert row["tugs"] is None
    assert row["agent"] is None


def test_missing_section_is_tolerated():
    rows = parse_page(load("2021-02-19_3tables"))
    assert rows, "2021 fixture should still yield rows"
    assert "qua_luong" not in {r["section"] for r in rows}


def test_empty_day_yields_no_rows():
    name = "2023-01-22_empty" if (FIXTURES / "2023-01-22_empty.html.gz").exists() \
        else "2026-08-11_empty_synthetic"
    assert parse_page(load(name)) == []


def test_date_mismatch_raises():
    with pytest.raises(DateMismatchError):
        parse_page(load("2026-08-11_full"), expected_date=date(2026, 8, 10))


def test_lxml_is_required_not_optional():
    """If someone swaps the parser to html.parser, this fails loudly.

    html.parser silently collapses the first three tables, so the only symptom
    would be a quiet 80% drop in row counts.
    """
    from bs4 import BeautifulSoup
    html = load("2026-08-11_full")
    lxml_rows = sum(
        len(t.find_all("tr")) - 1
        for t in BeautifulSoup(html, "lxml").find_all("table", class_="cssTD")
    )
    stdlib_rows = sum(
        len(t.find_all("tr")) - 1
        for t in BeautifulSoup(html, "html.parser").find_all("table", class_="cssTD")
    )
    assert lxml_rows == 86
    assert stdlib_rows < lxml_rows, "fixture no longer demonstrates the hazard"
    assert len(parse_page(html)) == lxml_rows
