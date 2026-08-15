import gzip
from datetime import date, datetime
from pathlib import Path

from scraper.hcm.normalize import build_records
from scraper.hcm.parse import parse_page

FIXTURES = Path(__file__).parent / "fixtures" / "hcm"


def _load(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as fh:
        return fh.read()


def _records_for(fixture, expected_date):
    html = _load(fixture)
    raw = parse_page(html, expected_date=expected_date)
    return build_records(raw, datetime(2026, 8, 15, 7, 0))


def test_typed_conversion_of_real_columns():
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))
    assert records

    arrival = next(r for r in records if r["section"] == "tau_vao")
    assert isinstance(arrival["plan_date"], date)
    assert arrival["vessel_name"] is None or isinstance(arrival["vessel_name"], str)
    assert arrival["dwt"] is None or isinstance(arrival["dwt"], int)
    assert arrival["loa_m"] is None or isinstance(arrival["loa_m"], float)
    assert arrival["draft_m"] is None or isinstance(arrival["draft_m"], float)
    # At least some rows in a real day should have these populated.
    assert any(r["nationality"] for r in records)
    assert any(r["call_sign"] for r in records)
    assert any(r["cargo_type"] for r in records)
    assert any(r["dwt"] is not None for r in records)


def test_no_gt_field_present():
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))
    assert all("gt" not in r for r in records)


def test_from_to_normalization_across_all_sections():
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))

    arrivals = [r for r in records if r["section"] == "tau_vao"]
    departures = [r for r in records if r["section"] == "tau_roi"]
    movements = [r for r in records if r["section"] == "tau_di_chuyen"]
    assert arrivals and departures and movements

    for r in arrivals:
        assert r["from_position"] is None
        # to_position may occasionally be blank on the source page, but
        # most arrivals should carry a berth position.
    assert any(r["to_position"] for r in arrivals)

    for r in departures:
        assert r["to_position"] is None
    assert any(r["from_position"] for r in departures)

    assert any(r["from_position"] for r in movements)
    assert any(r["to_position"] for r in movements)


def test_eta_etd_normalization():
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))

    arrivals = [r for r in records if r["section"] == "tau_vao"]
    departures = [r for r in records if r["section"] == "tau_roi"]
    movements = [r for r in records if r["section"] == "tau_di_chuyen"]

    # Arrivals can have both an eta and an etd.
    assert any(r["eta"] is not None for r in arrivals)
    for r in departures + movements:
        assert r["eta"] is None
    # Every section carries some form of etd/movement time.
    assert any(r["etd"] is not None for r in arrivals)
    assert any(r["etd"] is not None for r in departures)
    assert any(r["etd"] is not None for r in movements)


def test_row_key_stable_across_crawls():
    html = _load("2026-08-14.html.gz")
    raw = parse_page(html, expected_date=date(2026, 8, 14))

    records_day1 = build_records(raw, datetime(2026, 8, 14, 7, 0))
    records_day2 = build_records(raw, datetime(2026, 8, 15, 7, 0))

    keys_day1 = [r["row_key"] for r in records_day1]
    keys_day2 = [r["row_key"] for r in records_day2]
    assert keys_day1 == keys_day2


def test_row_key_unique_within_a_day():
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))
    keys = [r["row_key"] for r in records]
    assert len(keys) == len(set(keys))


def test_crawled_at_is_uniform_across_all_records():
    stamp = datetime(2026, 8, 15, 9, 30)
    records = _records_for("2026-08-14.html.gz", date(2026, 8, 14))
    html = _load("2026-08-14.html.gz")
    raw = parse_page(html, expected_date=date(2026, 8, 14))
    records = build_records(raw, stamp)
    assert all(r["crawled_at"] == stamp for r in records)
