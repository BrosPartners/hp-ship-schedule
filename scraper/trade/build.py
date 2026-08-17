"""Gộp số liệu XNK đã bóc từ PDF theo nhóm hàng/nhóm nước, sinh JSON cho web.

Tên mặt hàng và tên nước trong file hải quan là gốc, chưa gộp; các nhóm owner
vẽ tay (Hàng điện tử, Chế biến chế tạo, Trung Quốc, Mỹ, Asean, EU...) là owner
tự đặt. Ánh xạ này nằm trong `data/trade/commodity_map.csv` và
`country_map.csv`, sửa được mà không cần đụng code - cùng triết lý với
`berth_map.csv` của scraper lịch tàu.

Tên không có trong file ánh xạ **phải raise**, không im lặng dồn vào "khác" -
một mặt hàng/nước mới nổi lên mà lặng lẽ rơi vào "khác" là loại lỗi không ai
phát hiện, giống hệt lý do `scraper.parse` raise khi gặp section lạ.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from scraper.trade.fetch import list_reports, sync
from scraper.trade.parse import parse_pdf

ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "data" / "trade" / "pdf"
COMMODITY_MAP = ROOT / "data" / "trade" / "commodity_map.csv"
COUNTRY_MAP = ROOT / "data" / "trade" / "country_map.csv"
OUT_DIR = ROOT / "data" / "trade" / "agg"

# Không neo đầu chuỗi: một số file nguồn có số thừa gắn phía trước do lỗi gõ
# của hải quan (ví dụ "3362023-T11-5X(VN-SB)-1.pdf" thay vì "2023-T11-5X...").
MONTH_RE = re.compile(r"(\d{4})-t(\d{1,2})-5([xn])", re.IGNORECASE)


class UnmappedNameError(Exception):
    """Mặt hàng hoặc nước không có trong file ánh xạ."""


def load_map(path, group_col):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {row["ten_hai_quan"]: row[group_col] for row in csv.DictReader(fh)}


def _pdf_month_flow(path):
    """Suy tháng + chiều từ tên file (đã kiểm định dạng ổn định trên 86 file).

    Tên file luôn có đuôi "(vn-sb)" hoặc tương tự sau mã biểu, nên chiều lấy từ
    nhóm regex ("5x"/"5n") chứ không phải ký tự cuối cùng của tên file.
    """
    hit = MONTH_RE.search(path.stem)
    if not hit:
        raise ValueError(f"tên file không đúng định dạng đã biết: {path.name}")
    year, month = hit.group(1), int(hit.group(2))
    flow = "export" if hit.group(3).lower() == "x" else "import"
    return f"{year}-{month:02d}", flow


def parse_all(pdf_dir=None):
    pdf_dir = Path(pdf_dir or PDF_DIR)
    records = []
    for path in sorted(pdf_dir.glob("*.pdf")):
        month, flow = _pdf_month_flow(path)
        records.extend(parse_pdf(path, month=month, flow=flow))
    return records


def _check_mapped(records, commodity_map, country_map):
    unknown_commodities = sorted({r["commodity"] for r in records
                                  if r["commodity"] not in commodity_map})
    unknown_countries = sorted({r["country"] for r in records
                                if r["country"] not in country_map})
    if unknown_commodities or unknown_countries:
        parts = []
        if unknown_commodities:
            parts.append(f"{len(unknown_commodities)} mặt hàng chưa map: "
                        + ", ".join(unknown_commodities[:10]))
        if unknown_countries:
            parts.append(f"{len(unknown_countries)} nước chưa map: "
                        + ", ".join(unknown_countries[:10]))
        raise UnmappedNameError(
            "; ".join(parts) + " - thêm vào commodity_map.csv/country_map.csv"
            " rồi chạy lại.")


def _write(name, payload):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return str(path)


def build_all(pdf_dir=None, commodity_map_path=None, country_map_path=None):
    records = parse_all(pdf_dir)
    if not records:
        raise SystemExit(f"không có PDF nào trong {pdf_dir or PDF_DIR}")

    commodity_map = load_map(commodity_map_path or COMMODITY_MAP, "nhom_xk")
    commodity_map_nk = load_map(commodity_map_path or COMMODITY_MAP, "nhom_nk")
    country_map = load_map(country_map_path or COUNTRY_MAP, "nhom_xk")
    country_map_nk = load_map(country_map_path or COUNTRY_MAP, "nhom_nk")
    _check_mapped(records, commodity_map, country_map)

    # Chart 1 - tổng XK/NK theo tháng.
    monthly = defaultdict(lambda: {"export": 0, "import": 0})
    for r in records:
        monthly[r["month"]][r["flow"]] += r["usd_month"] or 0
    written = {"monthly": _write("monthly", {
        "rows": [{"month": m, "export": v["export"], "import": v["import"]}
                 for m, v in sorted(monthly.items())]
    })}

    # Chart 2/3 - XK/NK theo nhóm hàng.
    for flow, cmap in (("export", commodity_map), ("import", commodity_map_nk)):
        agg = defaultdict(int)
        for r in records:
            if r["flow"] != flow:
                continue
            agg[(r["month"], cmap[r["commodity"]])] += r["usd_month"] or 0
        written[f"commodity_{flow}"] = _write(f"commodity_{flow}", {
            "rows": [{"month": m, "group": g, "usd": v}
                     for (m, g), v in sorted(agg.items())]
        })

    # Chart 4/5 - XK/NK theo nhóm nước.
    for flow, gmap in (("export", country_map), ("import", country_map_nk)):
        agg = defaultdict(int)
        for r in records:
            if r["flow"] != flow:
                continue
            agg[(r["month"], gmap[r["country"]])] += r["usd_month"] or 0
        written[f"country_{flow}"] = _write(f"country_{flow}", {
            "rows": [{"month": m, "group": g, "usd": v}
                     for (m, g), v in sorted(agg.items())]
        })

    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sync", action="store_true",
                    help="dò và tải PDF mới trước khi tổng hợp")
    ap.add_argument("--start-month", default="2023-01")
    args = ap.parse_args(argv)

    if args.sync:
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        reports, downloaded = sync(PDF_DIR, start_month=args.start_month)
        print(f"dò được {len(reports)} bản ghi, tải mới {len(downloaded)} file")

    for name, path in build_all().items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
