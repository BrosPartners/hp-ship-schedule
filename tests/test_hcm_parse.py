import gzip
from datetime import date
from pathlib import Path

import pytest

from scraper.hcm.parse import (
    DateMismatchError,
    UnknownSectionError,
    parse_header_date,
    parse_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "hcm"


def _load(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as fh:
        return fh.read()


# Hand-verified against the live site (also recorded in the addendum spec):
# date -> (tau_vao, tau_roi, tau_di_chuyen) row counts.
EXPECTED_COUNTS = {
    "2026-08-14.html.gz": (date(2026, 8, 14), 74, 68, 62),
    "2025-07-01.html.gz": (date(2025, 7, 1), 47, 60, 32),
    "2024-01-01.html.gz": (date(2024, 1, 1), 67, 53, 6),
    "2023-01-01.html.gz": (date(2023, 1, 1), 47, 57, 7),
}


def test_parse_header_date_reads_date_input_value():
    html = _load("2026-08-14.html.gz")
    assert parse_header_date(html) == date(2026, 8, 14)


@pytest.mark.parametrize("fixture", EXPECTED_COUNTS.keys())
def test_section_split_and_row_counts(fixture):
    html = _load(fixture)
    expected_date, n_vao, n_roi, n_dichuyen = EXPECTED_COUNTS[fixture]

    rows = parse_page(html, expected_date=expected_date)

    by_section = {}
    for row in rows:
        by_section.setdefault(row["section"], []).append(row)

    assert len(by_section.get("tau_vao", [])) == n_vao
    assert len(by_section.get("tau_roi", [])) == n_roi
    assert len(by_section.get("tau_di_chuyen", [])) == n_dichuyen


def test_movements_section_has_different_columns_than_arrivals():
    html = _load("2026-08-14.html.gz")
    rows = parse_page(html, expected_date=date(2026, 8, 14))

    arrival = next(r for r in rows if r["section"] == "tau_vao")
    movement = next(r for r in rows if r["section"] == "tau_di_chuyen")

    assert arrival["vi_tri_neo_dau"] is not None
    assert arrival["vi_tri_neo_dau_tu"] is None
    assert arrival["vi_tri_neo_dau_den"] is None
    assert arrival["gio_doi"] is None

    assert movement["vi_tri_neo_dau_tu"] is not None
    assert movement["vi_tri_neo_dau_den"] is not None
    assert movement["gio_doi"] is not None
    assert movement["vi_tri_neo_dau"] is None


def test_all_values_are_string_or_none():
    html = _load("2026-08-14.html.gz")
    rows = parse_page(html, expected_date=date(2026, 8, 14))

    assert rows  # sanity: something was parsed
    for row in rows:
        for key, value in row.items():
            if key in ("section", "plan_date"):
                continue
            assert value is None or isinstance(value, str), (key, value)


def test_plan_date_matches_requested_date_on_every_row():
    html = _load("2024-01-01.html.gz")
    rows = parse_page(html, expected_date=date(2024, 1, 1))
    assert rows
    for row in rows:
        assert row["plan_date"] == date(2024, 1, 1)


def test_date_mismatch_raises():
    html = _load("2026-08-14.html.gz")
    with pytest.raises(DateMismatchError):
        parse_page(html, expected_date=date(2025, 7, 1))


def test_unknown_section_raises(monkeypatch):
    import scraper.hcm.parse as parse_mod

    html = _load("2026-08-14.html.gz")
    # Sabotage the id->section map so a real grid table cannot be attributed.
    monkeypatch.setattr(parse_mod, "_TABLE_ID_TO_SECTION", {})
    with pytest.raises(UnknownSectionError):
        parse_page(html, expected_date=date(2026, 8, 14))
