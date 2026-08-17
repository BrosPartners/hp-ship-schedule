import pytest

from scraper.trade.build import UnmappedNameError, _pdf_month_flow, build_all


def _write_maps(tmp_path):
    commodity = tmp_path / "commodity_map.csv"
    commodity.write_text(
        "ten_hai_quan,nhom_xk,nhom_nk\n"
        "Hàng thủy sản,nong_nghiep,khac\n"
        "Hàng hóa khác,khac,khac\n", encoding="utf-8")
    country = tmp_path / "country_map.csv"
    country.write_text(
        "ten_hai_quan,nhom_xk,nhom_nk\n"
        "TRUNG QUỐC,trung_quoc,trung_quoc\n"
        "AI CẬP,khac,khac\n", encoding="utf-8")
    return commodity, country


@pytest.mark.parametrize("name,expected", [
    ("2026-t7-5x(vn-sb).pdf", ("2026-07", "export")),
    ("2026-t7-5n(vn-sb).pdf", ("2026-07", "import")),
    ("2023-T11-5X(VN-SB).pdf", ("2023-11", "export")),
    # Lỗi gõ có thật trong nguồn: số thừa gắn phía trước do sơ suất khi đặt
    # tên file, vẫn phải đọc đúng phần YYYY-tMM-5x/5n ở giữa.
    ("3362023-T11-5X(VN-SB)-1.pdf", ("2023-11", "export")),
    ("6792023-T6-5X(VN-SB).pdf", ("2023-06", "export")),
])
def test_pdf_month_flow_reads_through_source_typos(tmp_path, name, expected):
    from pathlib import Path
    assert _pdf_month_flow(Path(name)) == expected


def test_pdf_month_flow_rejects_unknown_pattern():
    from pathlib import Path
    with pytest.raises(ValueError):
        _pdf_month_flow(Path("bao-cao-thang-7.pdf"))


def test_build_all_raises_on_unmapped_commodity(tmp_path, monkeypatch):
    from scraper.trade import build as build_mod

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    commodity, country = _write_maps(tmp_path)

    monkeypatch.setattr(build_mod, "parse_all", lambda _: [
        {"month": "2026-07", "flow": "export", "country": "TRUNG QUỐC",
         "commodity": "Mặt hàng chưa từng thấy", "usd_month": 100},
    ])

    with pytest.raises(UnmappedNameError, match="Mặt hàng chưa từng thấy"):
        build_all(pdf_dir, commodity, country)


def test_build_all_raises_on_unmapped_country(tmp_path, monkeypatch):
    from scraper.trade import build as build_mod

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    commodity, country = _write_maps(tmp_path)

    monkeypatch.setattr(build_mod, "parse_all", lambda _: [
        {"month": "2026-07", "flow": "export", "country": "Nước lạ",
         "commodity": "Hàng hóa khác", "usd_month": 100},
    ])

    with pytest.raises(UnmappedNameError, match="Nước lạ"):
        build_all(pdf_dir, commodity, country)


def test_build_all_aggregates_by_group(tmp_path, monkeypatch):
    import json

    from scraper.trade import build as build_mod

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    commodity, country = _write_maps(tmp_path)
    monkeypatch.setattr(build_mod, "OUT_DIR", tmp_path / "agg")

    monkeypatch.setattr(build_mod, "parse_all", lambda _: [
        {"month": "2026-07", "flow": "export", "country": "TRUNG QUỐC",
         "commodity": "Hàng thủy sản", "usd_month": 300},
        {"month": "2026-07", "flow": "export", "country": "AI CẬP",
         "commodity": "Hàng thủy sản", "usd_month": 200},
        {"month": "2026-07", "flow": "import", "country": "TRUNG QUỐC",
         "commodity": "Hàng hóa khác", "usd_month": 500},
    ])

    written = build_all(pdf_dir, commodity, country)

    monthly = json.loads(open(written["monthly"], encoding="utf-8").read())
    assert monthly["rows"] == [{"month": "2026-07", "export": 500, "import": 500}]

    ce = json.loads(open(written["commodity_export"], encoding="utf-8").read())
    assert {(r["group"], r["usd"]) for r in ce["rows"]} == {("nong_nghiep", 500)}

    cx = json.loads(open(written["country_export"], encoding="utf-8").read())
    assert {(r["group"], r["usd"]) for r in cx["rows"]} == \
        {("trung_quoc", 300), ("khac", 200)}
