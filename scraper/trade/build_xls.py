"""Gộp số liệu XNK từ Excel gốc theo nhóm hàng/nhóm nước, sinh JSON cho web.

Thay thế nguồn PDF hải quan (`scraper.trade.build`, `parse.py`, `fetch.py`) -
những file đó vẫn còn trong repo và vẫn được test, nhưng không còn được
`daily.yml` gọi tới. Nguồn Excel này chính xác hơn (native, không cần đọc theo
toạ độ) và khớp đúng nhóm nước owner đang dùng vì EU/ASEAN đã được cơ quan
thống kê tổng hợp sẵn thành khối, không phải tự cộng từng nước như trước.

Owner tải file thủ công và thả vào `data/trade/xls/` - giống hệt luồng
`data/vpa/*.xlsx`. Mỗi lần tải mới đã chứa nguyên lịch sử nhiều năm (không
phải một tháng), nên chỉ cần giữ **file mới nhất của mỗi trong ba loại**
(Xuất khẩu/Nhập khẩu/V03) trong thư mục; file cũ hơn cùng loại nên xoá đi để
khỏi nhầm bản nào là bản dùng.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from scraper.trade.xls_parse import parse_commodity_xls, parse_country_xls

ROOT = Path(__file__).resolve().parents[2]
XLS_DIR = ROOT / "data" / "trade" / "xls"
COMMODITY_MAP = ROOT / "data" / "trade" / "commodity_map_xls.csv"
COUNTRY_MAP = ROOT / "data" / "trade" / "country_map_xls.csv"
OUT_DIR = ROOT / "data" / "trade" / "agg"


class NoFileError(Exception):
    """Không tìm thấy file loại nào đó (Xuất khẩu/Nhập khẩu/V03) trong thư mục."""


class UnmappedNameError(Exception):
    """Mặt hàng hoặc nước/khối không có trong file ánh xạ."""


def load_map(path, group_col):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {row["ten_file"]: row[group_col] for row in csv.DictReader(fh)}


def _latest(xls_dir, prefix):
    """File mới nhất bắt đầu bằng `prefix` (theo mtime, không theo tên)."""
    hits = sorted(Path(xls_dir).glob(f"{prefix}*.xls*"), key=lambda p: p.stat().st_mtime)
    if not hits:
        raise NoFileError(f"không thấy file nào bắt đầu bằng {prefix!r} trong {xls_dir}")
    return hits[-1]


def _sheet_name(path, want_data=True):
    """Sheet đầu tiên có dữ liệu bảng (không phải sheet phụ kiểu 'Sheet1')."""
    import pandas as pd
    xl = pd.ExcelFile(path)
    return xl.sheet_names[0] if want_data else xl.sheet_names[-1]


def _check_mapped(names, mapping, kind):
    unknown = sorted(n for n in names if n not in mapping)
    if unknown:
        raise UnmappedNameError(
            f"{len(unknown)} {kind} chưa có trong file ánh xạ: "
            + ", ".join(unknown[:10])
            + ("..." if len(unknown) > 10 else "")
            + " - thêm vào rồi chạy lại.")


def _write(name, payload):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return str(path)


def build_all(xls_dir=None, commodity_map_path=None, country_map_path=None):
    xls_dir = Path(xls_dir or XLS_DIR)
    export_xls = _latest(xls_dir, "Xuất khẩu")
    import_xls = _latest(xls_dir, "Nhập khẩu")
    country_xls = _latest(xls_dir, "V03")

    commodities = (
        parse_commodity_xls(export_xls, _sheet_name(export_xls), "export")
        + parse_commodity_xls(import_xls, _sheet_name(import_xls), "import"))
    countries = parse_country_xls(country_xls, _sheet_name(country_xls))

    cmap = load_map(commodity_map_path or COMMODITY_MAP, "nhom_xk")
    cmap_nk = load_map(commodity_map_path or COMMODITY_MAP, "nhom_nk")
    gmap = load_map(country_map_path or COUNTRY_MAP, "nhom_xk")
    gmap_nk = load_map(country_map_path or COUNTRY_MAP, "nhom_nk")
    _check_mapped({c["commodity"] for c in commodities if c["flow"] == "export"},
                 cmap, "mặt hàng xuất khẩu")
    _check_mapped({c["commodity"] for c in commodities if c["flow"] == "import"},
                 cmap_nk, "mặt hàng nhập khẩu")
    _check_mapped({c["country"] for c in countries}, gmap, "nước/khối")

    # Chart 1 - tổng theo tháng. Cộng từ nhóm nước (EU + ASEAN + "Một số nước
    # khác") thay vì cộng lại toàn bộ mặt hàng, vì đằng nào cũng cần cộng một
    # bên để ra tổng - dùng nhóm nước cho nhất quán với chart 4/5.
    totals = defaultdict(lambda: defaultdict(int))
    for c in countries:
        totals[c["month"]][c["flow"]] += c["usd_month"]
    written = {"monthly": _write("monthly", {
        "rows": [{"month": m, "export": v.get("export", 0),
                  "import": v.get("import", 0)}
                 for m, v in sorted(totals.items())]
    })}

    for flow, cmap_flow in (("export", cmap), ("import", cmap_nk)):
        agg = defaultdict(int)
        for c in commodities:
            if c["flow"] != flow:
                continue
            agg[(c["month"], cmap_flow[c["commodity"]])] += c["usd_month"]
        written[f"commodity_{flow}"] = _write(f"commodity_{flow}", {
            "rows": [{"month": m, "group": g, "usd": v}
                     for (m, g), v in sorted(agg.items())]
        })

    for flow, gmap_flow in (("export", gmap), ("import", gmap_nk)):
        agg = defaultdict(int)
        for c in countries:
            if c["flow"] != flow:
                continue
            agg[(c["month"], gmap_flow[c["country"]])] += c["usd_month"]
        written[f"country_{flow}"] = _write(f"country_{flow}", {
            "rows": [{"month": m, "group": g, "usd": v}
                     for (m, g), v in sorted(agg.items())]
        })

    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args(argv)
    for name, path in build_all().items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
