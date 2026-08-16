"""Sinh map_ports.json cho tab Bản đồ.

Gộp ba nguồn về một điểm trên bản đồ:

- `data/port_facts.csv` - toạ độ, công suất thiết kế, giá THC (người nhập tay).
- `data/agg/teu.json`   - sản lượng container VPA 12 tháng gần nhất.
- `data/agg/berth_share.json` - lượt tàu 12 tháng gần nhất.

Công suất và THC là số người nhập, không phải số cào được; ô để trống sẽ ra
`null` và giao diện phải hiện "chưa có" thay vì đoán.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scraper.aggregate import _write

ROOT = Path(__file__).resolve().parent.parent
WINDOW = 12  # số tháng gộp cho "12 tháng gần nhất"


def _num(value):
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def load_facts(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{"unit": row["unit"].strip(),
                 "lat": _num(row["lat"]), "lon": _num(row["lon"]),
                 "capacity_teu": _num(row["capacity_teu"]),
                 "thc_usd": _num(row["thc_usd"]),
                 "zone": (row["zone"] or "").strip() or None,
                 "note": (row["note"] or "").strip()}
                for row in csv.DictReader(fh) if row["unit"].strip()]


def _window(months):
    """WINDOW tháng gần nhất trong tập tháng đã cho."""
    return set(sorted(months)[-WINDOW:])


def teu_by_unit(teu):
    months = _window({r["month"] for r in teu["rows"]})
    out = {}
    for r in teu["rows"]:
        if r["month"] in months:
            cur = out.setdefault(r["unit"], {"teu": 0.0, "months": 0})
            cur["teu"] += r["teu"]
            cur["months"] += 1
    return out, sorted(months)


def calls_by_berth(share):
    months = _window({r["month"] for r in share["rows"]})
    out = {}
    for r in share["rows"]:
        if r["month"] in months:
            cur = out.setdefault(r["berth"], {"calls": 0, "dwt": 0})
            cur["calls"] += r["calls"]
            cur["dwt"] += r["dwt"]
    return out


def build(facts, teu, share):
    """Một điểm cho mỗi dòng port_facts có toạ độ.

    Ghép TEU theo tên đơn vị VPA, còn lượt tàu theo tên bến. Hai bên trùng tên
    ở hầu hết các cảng; riêng Chùa Vẽ và Tân Vũ thì VPA gộp làm một nên chỉ
    dòng `Chùa Vẽ` mang TEU của cả cụm - đánh dấu bằng `teu_shared` để giao
    diện nói rõ, thay vì để người đọc tưởng Tân Vũ không có sản lượng.
    """
    teu_map, months = teu_by_unit(teu)
    call_map = calls_by_berth(share)

    points = []
    for f in facts:
        if f["lat"] is None or f["lon"] is None:
            continue
        hit = teu_map.get(f["unit"])
        vol = call_map.get(f["unit"])
        teu_12m = round(hit["teu"]) if hit else None
        capacity = f["capacity_teu"]
        points.append({
            **f,
            "teu_12m": teu_12m,
            "teu_months": hit["months"] if hit else 0,
            "calls_12m": vol["calls"] if vol else None,
            "dwt_12m": vol["dwt"] if vol else None,
            "utilisation": (round(100 * teu_12m / capacity, 1)
                            if teu_12m and capacity else None),
            "teu_per_call": (round(teu_12m / vol["calls"], 1)
                             if teu_12m and vol and vol["calls"] else None),
        })

    # VPA gộp Chùa Vẽ + Tân Vũ: TEU nằm ở "Chùa Vẽ + Tân Vũ", không khớp tên
    # bến nào, nên gán vào Chùa Vẽ và ghi rõ là số của cả cụm.
    combined = teu_map.get("Chùa Vẽ + Tân Vũ")
    if combined:
        pair = [p for p in points if p["unit"] in ("Chùa Vẽ", "Tân Vũ")]
        calls = sum(p["calls_12m"] or 0 for p in pair)
        for p in pair:
            p["teu_12m"] = round(combined["teu"])
            p["teu_shared"] = "Chùa Vẽ + Tân Vũ"
            p["teu_per_call"] = (round(combined["teu"] / calls, 1)
                                 if calls else None)
            p["utilisation"] = (round(100 * combined["teu"] / p["capacity_teu"], 1)
                                if p["capacity_teu"] else None)

    return {"months": months, "window": WINDOW, "points": points}


def build_all(out_dir=None, facts_path=None, agg_dir=None):
    agg_dir = Path(agg_dir or ROOT / "data" / "agg")
    facts = load_facts(facts_path or ROOT / "data" / "port_facts.csv")
    teu = json.loads((agg_dir / "teu.json").read_text(encoding="utf-8"))
    share = json.loads((agg_dir / "berth_share.json").read_text(encoding="utf-8"))
    return _write(out_dir or agg_dir, "map_ports", build(facts, teu, share))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--facts")
    ap.add_argument("--agg")
    args = ap.parse_args(argv)
    print(build_all(facts_path=args.facts, agg_dir=args.agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
