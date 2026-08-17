import json

import pytest

from scraper.trade.build_xls import NoFileError, UnmappedNameError, build_all


def _write_maps(tmp_path):
    commodity = tmp_path / "commodity_map_xls.csv"
    commodity.write_text(
        "ten_file,nhom_xk,nhom_nk\n"
        "Hàng thủy sản,nong_nghiep,\n"
        "Hàng hóa khác,khac,khac\n"
        "Ngô,,khac\n", encoding="utf-8")
    country = tmp_path / "country_map_xls.csv"
    country.write_text(
        "ten_file,nhom_xk,nhom_nk\n"
        "EU,eu,eu\n"
        "Mỹ,my,my\n", encoding="utf-8")
    return commodity, country


def test_no_files_raises(tmp_path):
    (tmp_path / "xls").mkdir()
    with pytest.raises(NoFileError):
        build_all(tmp_path / "xls")


def test_build_all_aggregates_by_group(tmp_path, monkeypatch):
    from scraper.trade import build_xls as mod

    commodity, country = _write_maps(tmp_path)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "agg")
    monkeypatch.setattr(mod, "_latest",
                        lambda xls_dir, prefix: tmp_path / f"{prefix}.xls")
    monkeypatch.setattr(mod, "_sheet_name", lambda path, want_data=True: "S")

    def fake_commodity(path, sheet, flow):
        if flow == "export":
            return [{"month": "2024-01", "flow": "export",
                     "commodity": "Hàng thủy sản", "usd_month": 300}]
        return [{"month": "2024-01", "flow": "import",
                 "commodity": "Ngô", "usd_month": 500}]

    def fake_country(path, sheet):
        return [
            {"month": "2024-01", "flow": "export", "country": "EU", "usd_month": 700},
            {"month": "2024-01", "flow": "import", "country": "Mỹ", "usd_month": 900},
        ]

    monkeypatch.setattr(mod, "parse_commodity_xls", fake_commodity)
    monkeypatch.setattr(mod, "parse_country_xls", fake_country)

    written = build_all(tmp_path / "xls", commodity, country)

    monthly = json.loads(open(written["monthly"], encoding="utf-8").read())
    assert monthly["rows"] == [{"month": "2024-01", "export": 700, "import": 900}]

    ce = json.loads(open(written["commodity_export"], encoding="utf-8").read())
    assert ce["rows"] == [{"month": "2024-01", "group": "nong_nghiep", "usd": 300}]

    cx = json.loads(open(written["country_export"], encoding="utf-8").read())
    assert cx["rows"] == [{"month": "2024-01", "group": "eu", "usd": 700}]


def test_unmapped_commodity_raises(tmp_path, monkeypatch):
    from scraper.trade import build_xls as mod

    commodity, country = _write_maps(tmp_path)
    monkeypatch.setattr(mod, "_latest",
                        lambda xls_dir, prefix: tmp_path / f"{prefix}.xls")
    monkeypatch.setattr(mod, "_sheet_name", lambda path, want_data=True: "S")
    monkeypatch.setattr(mod, "parse_commodity_xls", lambda path, sheet, flow: [
        {"month": "2024-01", "flow": flow, "commodity": "Chưa từng thấy",
         "usd_month": 1}])
    monkeypatch.setattr(mod, "parse_country_xls", lambda path, sheet: [])

    with pytest.raises(UnmappedNameError, match="Chưa từng thấy"):
        build_all(tmp_path / "xls", commodity, country)


def test_unmapped_country_raises(tmp_path, monkeypatch):
    from scraper.trade import build_xls as mod

    commodity, country = _write_maps(tmp_path)
    monkeypatch.setattr(mod, "_latest",
                        lambda xls_dir, prefix: tmp_path / f"{prefix}.xls")
    monkeypatch.setattr(mod, "_sheet_name", lambda path, want_data=True: "S")
    monkeypatch.setattr(mod, "parse_commodity_xls", lambda path, sheet, flow: [])
    monkeypatch.setattr(mod, "parse_country_xls", lambda path, sheet: [
        {"month": "2024-01", "flow": "export", "country": "Nước lạ", "usd_month": 1}])

    with pytest.raises(UnmappedNameError, match="Nước lạ"):
        build_all(tmp_path / "xls", commodity, country)


def test_latest_picks_newest_by_mtime(tmp_path):
    import os
    import time

    from scraper.trade.build_xls import _latest

    old = tmp_path / "Xuất khẩu-2025-10.xls"
    new = tmp_path / "Xuất khẩu-2025-11.xls"
    old.write_text("x", encoding="utf-8")
    time.sleep(0.01)
    new.write_text("x", encoding="utf-8")
    os.utime(old, (1, 1))

    assert _latest(tmp_path, "Xuất khẩu") == new
