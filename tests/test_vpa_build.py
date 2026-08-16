import pytest

from scraper.vpa.build import UnknownPortError, _payload, load_port_map, match
from scraper.vpa.parse import TeuRow

MAP_ROWS = (
    "vpa_name,unit,dataset,members\n"
    "HAI PHONG (CHUA VE+TAN VU),Chùa Vẽ + Tân Vũ,hp,Chùa Vẽ;Tân Vũ\n"
    "Đình Vũ,Đình Vũ,hp,Đình Vũ\n"
    "MIPEC,Mipec,hp,\n"
    "TAN CANG - CAT LAI,Cát Lái,hcm,Cat Lai\n"
    "MIEN BAC,,ignore,\n"
)


@pytest.fixture()
def port_map(tmp_path):
    path = tmp_path / "port_map.csv"
    path.write_text(MAP_ROWS, encoding="utf-8")
    return load_port_map(path)


def _row(name, month="2025-01", teu=100.0, derived=False):
    return TeuRow(month, name, name, teu, derived)


def test_map_keys_are_normalized_so_accents_do_not_matter(port_map):
    assert "DINH VU" in port_map
    assert port_map["DINH VU"]["members"] == ["Đình Vũ"]


def test_match_drops_ignored_and_region_rows(port_map):
    out = match([_row("MIEN BAC", teu=9999), _row("DINH VU")], port_map)

    assert [r["unit"] for r in out] == ["Đình Vũ"]


def test_match_raises_on_a_port_missing_from_the_map(port_map):
    with pytest.raises(UnknownPortError) as err:
        match([_row("CANG MOI TINH")], port_map)

    assert "CANG MOI TINH" in str(err.value)


def test_payload_sums_members_for_a_combined_unit(port_map):
    matched = match([_row("HAI PHONG (CHUA VE+TAN VU)", teu=500)], port_map)
    volume = {("2025-01", "Chùa Vẽ"): (10, 1000.0),
              ("2025-01", "Tân Vũ"): (20, 3000.0)}

    row = _payload(matched, volume)["rows"][0]

    assert (row["teu"], row["calls"], row["dwt"]) == (500, 30, 4000)


def test_payload_leaves_volume_null_when_the_unit_has_no_members(port_map):
    matched = match([_row("MIPEC", teu=42)], port_map)

    row = _payload(matched, {})["rows"][0]

    assert row["calls"] is None and row["dwt"] is None


def test_payload_leaves_volume_null_when_the_month_has_no_ship_data(port_map):
    matched = match([_row("DINH VU", month="2019-05")], port_map)

    row = _payload(matched, {("2025-01", "Đình Vũ"): (5, 10.0)})["rows"][0]

    assert row["calls"] is None


def test_payload_marks_derived_only_when_every_source_is_derived(port_map):
    published = match([_row("DINH VU", teu=10)], port_map)
    derived = match([_row("DINH VU", teu=5, derived=True)], port_map)

    rows = _payload(published + derived, {})["rows"]

    assert len(rows) == 1
    assert rows[0]["derived"] is False and rows[0]["teu"] == 15


def test_payload_lists_units_sorted(port_map):
    matched = match([_row("MIPEC"), _row("DINH VU")], port_map)

    assert _payload(matched, {})["units"] == ["Mipec", "Đình Vũ"]
