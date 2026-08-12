from datetime import date, datetime
from pathlib import Path

import pytest

from scraper.normalize import (apply_berth_map, coverage, load_berth_map)

MAP_PATH = Path(__file__).parent.parent / "data" / "berth_map.csv"


def _rec(from_raw, to_raw, is_sb=False):
    return {
        "plan_date": date(2026, 8, 11), "section": "vao_cang",
        "plan_time": datetime(2026, 8, 11, 6, 0), "vessel_name": "X",
        "is_sb": is_sb, "draft_m": 7.0, "loa_m": 100.0, "dwt": 1000, "gt": 800,
        "tugs": None, "channel_code": "HN", "from_raw": from_raw,
        "to_raw": to_raw, "agent": None, "pilot": None,
        "crawled_at": datetime(2026, 8, 12), "row_key": "k",
    }


def test_map_loads_and_is_keyed_uppercase():
    bmap = load_berth_map(MAP_PATH)
    assert "TAN VU" in bmap
    assert bmap["TAN VU"]["type"] == "berth"
    assert bmap["TAN VU"]["is_hai_phong"] is True
    assert bmap["CHINA"]["type"] == "foreign"
    assert bmap["CHINA"]["is_hai_phong"] is False


def test_apply_adds_berth_columns():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("CHINA", "TAN VU")], bmap)[0]
    assert out["from_berth"] == bmap["CHINA"]["berth"]
    assert out["to_berth"] == bmap["TAN VU"]["berth"]
    assert out["to_ticker"] == bmap["TAN VU"]["ticker"]
    assert out["to_type"] == "berth"
    assert out["is_domestic"] is False


def test_lookup_is_case_and_whitespace_insensitive():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("  tan vu ", "dinh vu")], bmap)[0]
    assert out["from_berth"] is not None
    assert out["to_berth"] is not None


def test_unmapped_value_stays_none_and_raw_is_preserved():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("ZZZ NOWHERE", "TAN VU")], bmap)[0]
    assert out["from_berth"] is None
    assert out["from_type"] is None
    assert out["from_raw"] == "ZZZ NOWHERE"


def test_domestic_when_both_ends_are_vietnamese():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("TAN VU", "NINH BINH")], bmap)[0]
    assert out["is_domestic"] is True


def test_sb_vessel_counts_as_domestic_even_if_unmapped():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("ZZZ NOWHERE", "ZZZ ELSEWHERE", is_sb=True)], bmap)[0]
    assert out["is_domestic"] is True


def test_domestic_when_one_end_is_a_vietnamese_port_outside_hai_phong():
    """TAN VU -> NGHI SON is a domestic voyage: Nghi Son is a Vietnamese port
    outside Hai Phong (type=external), not a foreign port. Conflating the two
    was the exact defect being fixed here."""
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("TAN VU", "NGHI SON")], bmap)[0]
    assert out["is_domestic"] is True


def test_not_domestic_when_one_end_is_foreign():
    bmap = load_berth_map(MAP_PATH)
    out = apply_berth_map([_rec("CHINA", "TAN VU")], bmap)[0]
    assert out["is_domestic"] is False


@pytest.mark.parametrize(
    "raw_name", ["NINH BINH", "NGHI SON", "CUA LO", "HON LA"]
)
def test_external_vn_ports_are_not_type_berth(raw_name):
    """These are Vietnamese ports outside Hai Phong. If type were ever
    relabelled 'berth' here, Task 8's throughput rule (to_type == 'berth')
    would silently count vessels leaving for another province as Hai Phong
    port throughput -- inflating Hai Phong's numbers with traffic that never
    called at a Hai Phong quay."""
    bmap = load_berth_map(MAP_PATH)
    assert bmap[raw_name]["type"] == "external", (
        f"{raw_name} must be type=external (Vietnamese port outside Hai Phong), "
        f"not 'berth' -- otherwise Task 8 throughput counts it as Hai Phong port "
        f"throughput, inflating the numbers with vessels that left for another province"
    )


@pytest.mark.skip(
    reason="full backfill not finished yet; coverage gate runs in Task 7 part 2",
)
def test_real_data_coverage_is_at_least_90_percent():
    import pandas as pd
    path = Path(__file__).parent.parent / "data" / "ship_plan.parquet"
    df = pd.read_parquet(path)
    bmap = load_berth_map(MAP_PATH)
    recs = apply_berth_map(df.to_dict("records"), bmap)
    assert coverage(recs) >= 0.90
