"""Tests for the HCM berth map (`data/hcm/berth_map.csv`) and its
application in `scraper.hcm.normalize`. Modelled on the Hai Phong berth-map
coverage established in `scraper/normalize.py` / `tools/unmapped_report.py`.
"""

from pathlib import Path

from scraper.hcm.normalize import apply_berth_map, load_berth_map

MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "hcm" / "berth_map.csv"


def test_map_loads_and_is_keyed_uppercase():
    berth_map = load_berth_map(MAP_PATH)
    assert berth_map
    for key in berth_map:
        assert key == key.upper()
    # A known entry, lowercased in the source data, must still resolve.
    assert "NEO VT" in berth_map


def test_cluster_and_type_propagate_onto_records():
    berth_map = load_berth_map(MAP_PATH)
    records = [{
        "from_position": "c.lai 5",
        "to_position": "SP-ITC01",
    }]
    out = apply_berth_map(records, berth_map)[0]
    assert out["from_cluster"] == "Cat Lai"
    assert out["from_type"] == "berth"
    assert out["to_cluster"] == "SP-ITC"
    assert out["to_type"] == "berth"


def test_unmapped_position_stays_null_and_raw_preserved():
    berth_map = load_berth_map(MAP_PATH)
    records = [{
        "from_position": "SOME TOTALLY UNKNOWN BUOY XYZ",
        "to_position": None,
    }]
    out = apply_berth_map(records, berth_map)[0]
    assert out["from_berth"] is None
    assert out["from_cluster"] is None
    assert out["from_ticker"] is None
    assert out["from_type"] is None
    # Raw string is untouched, not blanked out just because it's unmapped.
    assert out["from_position"] == "SOME TOTALLY UNKNOWN BUOY XYZ"
    assert out["to_berth"] is None


def test_anchorage_and_construction_types_are_distinguishable():
    berth_map = load_berth_map(MAP_PATH)
    records = [{
        "from_position": "NEO VT",
        "to_position": "BAI DO TIEN GIANG",
    }]
    out = apply_berth_map(records, berth_map)[0]
    assert out["from_type"] == "anchorage"
    assert out["to_type"] == "construction"
    # Both are excluded-from-throughput types, i.e. never "berth".
    assert out["from_type"] != "berth"
    assert out["to_type"] != "berth"


def test_case_insensitive_lookup():
    berth_map = load_berth_map(MAP_PATH)
    records = [{"from_position": "neo vt", "to_position": "Neo Vt"}]
    out = apply_berth_map(records, berth_map)[0]
    assert out["from_type"] == "anchorage"
    assert out["to_type"] == "anchorage"
