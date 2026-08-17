"""Ghép sản lượng container VPA với dữ liệu lượt tàu, sinh teu.json.

Đầu ra cho mỗi dataset (Hải Phòng / TP.HCM) là một file `teu.json` gồm chuỗi
TEU theo tháng của từng đơn vị VPA, kèm số lượt tàu và tổng DWT của đúng các
bến/cụm tạo nên đơn vị đó. Nhờ vậy tỷ lệ TEU/lượt tàu trên giao diện luôn
khớp với số lượt tàu ở các chart cũ - cả hai cùng đi ra từ `throughput_rows`.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

from scraper.aggregate import _prepare, _write, throughput_rows
from scraper.hcm.aggregate import _prepare as hcm_prepare
from scraper.hcm.aggregate import throughput_rows as hcm_throughput_rows
from scraper.store import load as load_partitions
from scraper.vpa.parse import normalize_name, read_workbooks

ROOT = Path(__file__).resolve().parents[2]
# 2023 không có sheet tháng; suy ra từ cột luỹ kế trong workbook 2024.
DERIVE_YEARS = (2023,)


class UnknownPortError(Exception):
    """Tên cảng trong workbook không có trong port_map.csv."""


def load_port_map(path):
    """{tên đã chuẩn hoá: {unit, dataset, members}}."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = normalize_name(row["vpa_name"])
            if not key:
                continue
            out[key] = {
                "unit": (row["unit"] or "").strip(),
                "dataset": (row["dataset"] or "").strip(),
                "members": [m.strip() for m in (row["members"] or "").split(";")
                            if m.strip()],
            }
    return out


def match(rows, port_map):
    """Gắn mỗi dòng TEU vào đơn vị. Tên lạ thì raise, không im lặng bỏ.

    Bỏ im lặng là cách một cảng mới của VPA biến mất khỏi dashboard mà không
    ai biết - cùng lý do scraper raise khi gặp section lạ.
    """
    unknown = sorted({r.raw_name for r in rows if r.name not in port_map})
    if unknown:
        raise UnknownPortError(
            "port_map.csv thiếu " + str(len(unknown)) + " tên: "
            + ", ".join(unknown[:10])
            + ("..." if len(unknown) > 10 else "")
            + " - thêm vào file rồi chạy lại (dataset=ignore nếu không dùng)")

    out = []
    for r in rows:
        hit = port_map[r.name]
        if hit["dataset"] in ("", "ignore"):
            continue
        out.append({"month": r.month, "unit": hit["unit"],
                    "dataset": hit["dataset"], "members": hit["members"],
                    "teu": r.teu, "derived": r.derived})
    return out


class MemberNameClashError(Exception):
    """Một tên vừa là cụm vừa là bến - không biết `members` đang trỏ vào đâu."""


def _volume_by_member(parts_dir, columns, prepare_fn, rows_fn, cutoff):
    """{(month, member): (calls, dwt)} từ đúng nguồn nuôi các chart cũ.

    `columns` là các cấp có thể dùng làm `members` trong port_map.csv. TP.HCM
    cần cả hai cấp: phần lớn đơn vị VPA khớp với một cụm (`to_cluster`), riêng
    các terminal trong Cái Mép thì VPA công bố lẻ từng cái nên phải cộng theo
    từng bến (`to_berth`).

    Mỗi dataset có `_prepare` riêng vì schema khác nhau (bảng TP.HCM không có
    cột `gt`), nên hàm chuẩn bị được truyền vào thay vì gọi cứng.
    """
    df = prepare_fn(load_partitions(parts_dir))
    if cutoff is not None:
        df = df[df["plan_date"] <= pd.Timestamp(cutoff)]
    thr = rows_fn(df)

    out, seen = {}, {}
    for column in columns:
        grouped = (thr.dropna(subset=[column])
                      .groupby(["month", column])
                      .agg(calls=("row_key", "count"), dwt=("dwt", "sum")))
        for (month, key), v in grouped.iterrows():
            # Gộp hai cấp vào một từ điển chỉ an toàn khi tên không đụng nhau;
            # nếu đụng thì `members` trở nên nhập nhằng và số sẽ sai âm thầm.
            if seen.setdefault(key, column) != column:
                raise MemberNameClashError(
                    f"{key!r} vừa là {seen[key]} vừa là {column} - "
                    "đổi tên một bên trước khi dùng làm members")
            out[(month, key)] = (int(v.calls), float(v.dwt or 0))
    return out


def _payload(matched, volume):
    """Gộp các dòng cùng (đơn vị, tháng) rồi cộng mẫu số theo members."""
    agg = {}
    for row in matched:
        key = (row["month"], row["unit"])
        cur = agg.setdefault(key, {"teu": 0.0, "derived": row["derived"],
                                   "members": row["members"]})
        cur["teu"] += row["teu"]
        # Số công bố thắng số suy ra nếu một đơn vị có cả hai nguồn.
        cur["derived"] = cur["derived"] and row["derived"]

    rows = []
    for (month, unit), cur in sorted(agg.items()):
        calls = dwt = None
        if cur["members"]:
            hits = [volume.get((month, m)) for m in cur["members"]]
            hits = [h for h in hits if h is not None]
            # Thiếu hẳn dữ liệu tàu tháng đó thì để null, không quy về 0 -
            # 0 sẽ biến thành phép chia cho 0 rồi thành một tháng "vô hạn".
            if hits:
                calls = sum(h[0] for h in hits)
                dwt = sum(h[1] for h in hits)
        rows.append({"month": month, "unit": unit,
                     "teu": round(cur["teu"], 1), "derived": cur["derived"],
                     "calls": calls, "dwt": None if dwt is None else round(dwt)})

    units = sorted({r["unit"] for r in rows})
    return {"units": units, "rows": rows,
            "derived_note": "Số 2023 suy ra từ cột luỹ kế của VPA, "
                            "không phải số công bố theo tháng."}


def build_all(map_path=None, workbook_dir=None, today=None):
    map_path = map_path or ROOT / "data" / "vpa" / "port_map.csv"
    workbook_dir = Path(workbook_dir or ROOT / "data" / "vpa")
    books = sorted(p for p in workbook_dir.glob("*.xlsx")
                   if not p.name.startswith("~$"))
    if not books:
        raise SystemExit(f"không thấy workbook .xlsx nào trong {workbook_dir}")

    port_map = load_port_map(map_path)
    matched = match(read_workbooks(books, derive_years=DERIVE_YEARS), port_map)

    written = {}
    for dataset, parts, columns, prepare_fn, rows_fn, out_dir in (
        ("hp", ROOT / "data" / "parts", ("to_berth",), _prepare,
         throughput_rows, ROOT / "data" / "agg"),
        ("hcm", ROOT / "data" / "hcm" / "parts", ("to_cluster", "to_berth"),
         hcm_prepare, hcm_throughput_rows, ROOT / "data" / "hcm" / "agg"),
    ):
        subset = [r for r in matched if r["dataset"] == dataset]
        volume = _volume_by_member(parts, columns, prepare_fn, rows_fn, today)
        written[dataset] = _write(out_dir, "teu", _payload(subset, volume))
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map")
    ap.add_argument("--workbooks")
    args = ap.parse_args(argv)
    for dataset, path in build_all(args.map, args.workbooks).items():
        print(f"{dataset}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
