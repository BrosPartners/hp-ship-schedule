import pytest

from scraper.map_data import build, load_facts

FACTS = (
    "unit,lat,lon,capacity_teu,thc_usd,zone,note\n"
    "Nam Đình Vũ,20.82,106.80,2000000,46,ha_nguon,\n"
    "Chùa Vẽ,20.85,106.71,500000,42,ha_nguon,gộp với Tân Vũ\n"
    "Tân Vũ,20.84,106.76,,42,ha_nguon,\n"
    "Không toạ độ,,,,,ha_nguon,\n"
)


@pytest.fixture()
def facts(tmp_path):
    path = tmp_path / "port_facts.csv"
    path.write_text(FACTS, encoding="utf-8")
    return load_facts(path)


def _teu(rows):
    return {"units": sorted({r[1] for r in rows}),
            "rows": [{"month": m, "unit": u, "teu": t, "derived": False,
                      "calls": None, "dwt": None} for m, u, t in rows]}


def _share(rows):
    return {"rows": [{"month": m, "berth": b, "ticker": "X", "zone": "ha_nguon",
                      "calls": c, "dwt": d} for m, b, c, d in rows]}


def test_a_port_without_coordinates_is_left_off_the_map(facts):
    out = build(facts, _teu([("2026-01", "Nam Đình Vũ", 100.0)]), _share([]))

    assert "Không toạ độ" not in [p["unit"] for p in out["points"]]


def test_utilisation_is_teu_over_design_capacity(facts):
    out = build(facts, _teu([("2026-01", "Nam Đình Vũ", 500000.0)]), _share([]))

    point = next(p for p in out["points"] if p["unit"] == "Nam Đình Vũ")
    assert point["utilisation"] == 25.0


def test_missing_capacity_leaves_utilisation_null(facts):
    out = build(facts, _teu([("2026-01", "Tân Vũ", 900.0)]), _share([]))

    point = next(p for p in out["points"] if p["unit"] == "Tân Vũ")
    assert point["capacity_teu"] is None and point["utilisation"] is None


def test_only_the_last_twelve_months_are_summed(facts):
    rows = [(f"2025-{m:02d}", "Nam Đình Vũ", 10.0) for m in range(1, 13)]
    rows.append(("2026-01", "Nam Đình Vũ", 7.0))

    out = build(facts, _teu(rows), _share([]))

    # 12 tháng gần nhất là 2025-02..2026-01: 11 tháng x 10 + 7.
    point = next(p for p in out["points"] if p["unit"] == "Nam Đình Vũ")
    assert point["teu_12m"] == 117 and point["teu_months"] == 12


def test_the_combined_vpa_unit_is_shown_on_both_berths(facts):
    teu = _teu([("2026-01", "Chùa Vẽ + Tân Vũ", 1000.0)])
    share = _share([("2026-01", "Chùa Vẽ", 3, 100), ("2026-01", "Tân Vũ", 2, 90)])

    out = build(facts, teu, share)
    pair = {p["unit"]: p for p in out["points"] if p["unit"] in ("Chùa Vẽ", "Tân Vũ")}

    assert pair["Chùa Vẽ"]["teu_12m"] == pair["Tân Vũ"]["teu_12m"] == 1000
    assert pair["Tân Vũ"]["teu_shared"] == "Chùa Vẽ + Tân Vũ"
    # Mẫu số là lượt tàu của cả hai bến, không phải của riêng từng bến.
    assert pair["Chùa Vẽ"]["teu_per_call"] == 200.0


def test_teu_per_call_uses_the_matching_berth_volume(facts):
    teu = _teu([("2026-01", "Nam Đình Vũ", 1000.0)])
    share = _share([("2026-01", "Nam Đình Vũ", 4, 500)])

    out = build(facts, teu, share)
    point = next(p for p in out["points"] if p["unit"] == "Nam Đình Vũ")

    assert point["teu_per_call"] == 250.0 and point["calls_12m"] == 4


def test_a_port_with_no_ship_data_keeps_null_volume(facts):
    out = build(facts, _teu([("2026-01", "Nam Đình Vũ", 10.0)]), _share([]))

    point = next(p for p in out["points"] if p["unit"] == "Nam Đình Vũ")
    assert point["calls_12m"] is None and point["teu_per_call"] is None


def test_combined_unit_utilisation_uses_the_summed_capacity(facts):
    # Chùa Vẽ 500k + Tân Vũ chưa có số -> mẫu số là 500k, không phải nhân đôi.
    teu = _teu([("2026-01", "Chùa Vẽ + Tân Vũ", 250000.0)])
    out = build(facts, teu, _share([("2026-01", "Chùa Vẽ", 1, 1)]))

    pair = {p["unit"]: p for p in out["points"] if p["unit"] in ("Chùa Vẽ", "Tân Vũ")}
    assert pair["Chùa Vẽ"]["capacity_shared"] == 500000
    assert pair["Chùa Vẽ"]["utilisation"] == pair["Tân Vũ"]["utilisation"] == 50.0


def test_geo_source_is_carried_through(facts):
    out = build(facts, _teu([]), _share([]))

    assert all("geo_source" in p for p in out["points"])
