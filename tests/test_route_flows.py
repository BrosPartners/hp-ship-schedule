import json

import pandas as pd
import pytest

from scraper.route_flows import (MissingCountryPointError, NoRouteDataError,
                                 build, flow_rows, load_country_points)


def _leg(**kw):
    base = {
        "plan_date": "2026-01-05", "section": "vao_cang", "vessel_name": "X",
        "dwt": 10000.0, "from_raw": "CHINA", "to_raw": "TAN VU",
        "from_berth": "Trung Quốc", "to_berth": "Tân Vũ",
        "from_type": "foreign", "to_type": "berth",
        "crawled_at": pd.Timestamp("2026-01-06"), "row_key": "k1",
    }
    base.update(kw)
    return base


def _frame(rows):
    df = pd.DataFrame(rows)
    df["plan_date"] = pd.to_datetime(df["plan_date"])
    df["month"] = df["plan_date"].dt.strftime("%Y-%m")
    return df


def test_arrival_and_departure_become_separate_directions():
    df = _frame([
        _leg(row_key="a"),
        _leg(row_key="b", section="roi_cang", from_raw="TAN VU", to_raw="CHINA",
             from_berth="Tân Vũ", to_berth="Trung Quốc",
             from_type="berth", to_type="foreign"),
    ])
    rows = flow_rows(df)
    dirs = {r["direction"]: r for r in rows}
    assert set(dirs) == {"in", "out"}
    assert dirs["in"]["loc"] == "Tân Vũ" and dirs["in"]["country"] == "Trung Quốc"
    assert dirs["out"]["loc"] == "Tân Vũ" and dirs["out"]["country"] == "Trung Quốc"


def test_anchorage_legs_are_kept():
    """Tàu quốc tế vào thẳng khu neo vẫn là lượt quốc tế thật.

    Khác `aggregate.throughput_rows` (loại khu neo để tránh đếm trùng với
    chặng `di_chuyen` vào bến) - chặng nội bộ đó không mang tên nước nên ở
    đây không có gì để trùng.
    """
    df = _frame([_leg(to_raw="HON DAU", to_berth="Hòn Dấu", to_type="anchorage")])
    rows = flow_rows(df)
    assert len(rows) == 1
    assert rows[0]["loc"] == "Hòn Dấu" and rows[0]["loc_type"] == "anchorage"


def test_internal_and_transit_legs_are_ignored():
    df = _frame([
        # bến -> bến, không có đầu nước ngoài
        _leg(row_key="m", section="di_chuyen", from_raw="HHIT", to_raw="TAN VU",
             from_berth="HHIT", to_berth="Tân Vũ",
             from_type="berth", to_type="berth"),
        # đích chưa map được -> không quy được về bến nào
        _leg(row_key="u", to_raw="BEN GOT", to_berth=None, to_type=None),
    ])
    with pytest.raises(NoRouteDataError):
        flow_rows(df)


def test_calls_and_dwt_are_summed_per_month_loc_country():
    df = _frame([
        _leg(row_key="a", dwt=1000.0),
        _leg(row_key="b", dwt=2500.0),
        _leg(row_key="c", plan_date="2026-02-09", dwt=400.0),
    ])
    rows = {r["month"]: r for r in flow_rows(df)}
    assert rows["2026-01"]["calls"] == 2 and rows["2026-01"]["dwt"] == 3500.0
    assert rows["2026-02"]["calls"] == 1 and rows["2026-02"]["dwt"] == 400.0


def test_every_country_in_the_real_data_has_a_point(tmp_path):
    """country_points.csv phải phủ hết các nước xuất hiện trong berth_map."""
    import csv

    points = load_country_points("data/country_points.csv")
    with open("data/berth_map.csv", newline="", encoding="utf-8-sig") as fh:
        countries = {r["berth"].strip() for r in csv.DictReader(fh)
                     if (r["type"] or "").strip() == "foreign" and r["berth"].strip()}
    assert not (countries - set(points)), \
        f"thiếu toạ độ cho: {sorted(countries - set(points))}"


def test_build_raises_when_a_country_has_no_point(tmp_path, monkeypatch):
    from scraper import route_flows as mod

    pts = tmp_path / "points.csv"
    pts.write_text("country,lat,lon,anchor\nSingapore,1.29,103.85,x\n",
                   encoding="utf-8")
    monkeypatch.setattr(mod, "_prepare", lambda df: df)
    monkeypatch.setattr(mod, "flow_rows", lambda df: [
        {"month": "2026-01", "loc": "Tân Vũ", "loc_type": "berth",
         "country": "Trung Quốc", "direction": "in", "calls": 1, "dwt": 1.0}])
    monkeypatch.setattr("scraper.store.load", lambda p: pd.DataFrame())

    with pytest.raises(MissingCountryPointError, match="Trung Quốc"):
        build(tmp_path, tmp_path, points_path=pts)


def test_build_writes_rows_and_points(tmp_path, monkeypatch):
    from scraper import route_flows as mod

    pts = tmp_path / "points.csv"
    pts.write_text("country,lat,lon,anchor\nTrung Quốc,24.5,118.1,Hạ Môn\n",
                   encoding="utf-8")
    monkeypatch.setattr(mod, "_prepare", lambda df: df)
    monkeypatch.setattr(mod, "flow_rows", lambda df: [
        {"month": "2026-01", "loc": "Tân Vũ", "loc_type": "berth",
         "country": "Trung Quốc", "direction": "in", "calls": 3, "dwt": 9.0}])
    monkeypatch.setattr("scraper.store.load", lambda p: pd.DataFrame())

    out = build(tmp_path, tmp_path, points_path=pts)
    payload = json.loads(open(out, encoding="utf-8").read())
    assert payload["rows"][0]["calls"] == 3
    assert payload["points"]["Trung Quốc"]["lat"] == 24.5
