"""Tổng hợp tuyến quốc tế theo cặp (bến Hải Phòng, nước) cho tab Route.

Lịch tàu Hải Phòng ghi thẳng tên nước ở đầu đi hoặc đầu đến của mỗi lượt:
một dòng `vao_cang` có `from_raw = "CHINA"`, `to_raw = "NAM DINH VU"` nghĩa là
tàu từ Trung Quốc cập Nam Đình Vũ. `berth_map.csv` đã phân loại các tên nước
đó thành `type = "foreign"`, nên chỉ cần bắt cặp foreign ↔ bến là ra tuyến.

**Chỉ có Hải Phòng.** Nguồn TP.HCM (cangvuhanghaitphcm.gov.vn) không công bố
cảng đi/cảng đến - bảng của họ chỉ có vị trí neo đậu trong cảng, nên không thể
dựng tuyến. Cột "quốc tịch" bên đó là *cờ tàu* (Panama, Liberia, Marshall
Islands...), không phải điểm đến; dùng nó vẽ tuyến sẽ ra kết quả sai hẳn.

Phạm vi tính:
- Chiều đến: `vao_cang` có `from_type == "foreign"`.
- Chiều đi: `roi_cang` có `to_type == "foreign"`.
Hai chiều này không chồng lấn (đã kiểm: foreign→bến luôn là `vao_cang`,
bến→foreign luôn là `roi_cang`), nên không có nguy cơ đếm trùng.

Đầu Hải Phòng nhận cả `berth` lẫn `anchorage`: tàu quốc tế vào thẳng khu neo
(Hòn Dấu, Vật Cách, Thượng Lý...) là lượt quốc tế thật, bỏ đi sẽ hụt ~1.200
lượt và làm lệch hồ sơ tuyến của hàng rời/hàng lỏng. Khác với
`aggregate.throughput_rows` - ở đó khu neo bị loại vì sẽ đếm trùng với chặng
`di_chuyen` vào bến sau đó, còn ở đây chặng nội bộ ấy không mang tên nước nên
không có gì để trùng.
"""

import json
from pathlib import Path

import pandas as pd

from scraper.store import latest_snapshot

ROOT = Path(__file__).resolve().parent.parent
# Đầu Hải Phòng của một tuyến: bến hoặc khu neo (xem docstring).
_LOCAL_TYPES = ("berth", "anchorage")


class NoRouteDataError(Exception):
    """Không tìm được lượt quốc tế nào - nhiều khả năng berth_map mất mục foreign."""


class MissingCountryPointError(Exception):
    """Có nước trong dữ liệu nhưng chưa có toạ độ trong country_points.csv.

    Phải nổ chứ không lặng lẽ bỏ qua: thiếu toạ độ thì nước đó biến mất khỏi
    bản đồ mà không để lại dấu vết nào, giống hệt loại lỗi "số đẹp hơn thực
    tế" mà repo này đã trả giá một lần với berth_map.
    """


def load_country_points(path):
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {r["country"].strip(): {"lat": float(r["lat"]),
                                       "lon": float(r["lon"]),
                                       "anchor": (r.get("anchor") or "").strip()}
                for r in csv.DictReader(fh) if r.get("country", "").strip()}


def _prepare(df):
    df = latest_snapshot(df).copy()
    df["plan_date"] = pd.to_datetime(df["plan_date"])
    df["month"] = df["plan_date"].dt.strftime("%Y-%m")
    df["dwt"] = pd.to_numeric(df["dwt"], errors="coerce")
    return df


def flow_rows(df):
    """[{month, loc, loc_type, country, direction, calls, dwt}] - chưa ghi ra file."""
    arrivals = df[(df["section"] == "vao_cang")
                  & (df["from_type"] == "foreign")
                  & (df["to_type"].isin(_LOCAL_TYPES))].copy()
    arrivals["loc"] = arrivals["to_berth"]
    arrivals["loc_type"] = arrivals["to_type"]
    arrivals["country"] = arrivals["from_berth"]
    arrivals["direction"] = "in"

    departures = df[(df["section"] == "roi_cang")
                    & (df["to_type"] == "foreign")
                    & (df["from_type"].isin(_LOCAL_TYPES))].copy()
    departures["loc"] = departures["from_berth"]
    departures["loc_type"] = departures["from_type"]
    departures["country"] = departures["to_berth"]
    departures["direction"] = "out"

    legs = pd.concat([arrivals, departures], ignore_index=True)
    if legs.empty:
        raise NoRouteDataError(
            "không có lượt quốc tế nào; kiểm tra các mục type=foreign trong "
            "data/berth_map.csv")
    grouped = (legs.groupby(["month", "loc", "loc_type", "country", "direction"],
                            dropna=True)
               .agg(calls=("row_key", "size"), dwt=("dwt", "sum"))
               .reset_index())
    return [{"month": r.month, "loc": r.loc, "loc_type": r.loc_type,
             "country": r.country, "direction": r.direction,
             "calls": int(r.calls), "dwt": float(r.dwt or 0)}
            for r in grouped.itertuples()]


def build(parquet_path, out_dir, points_path=None):
    from scraper.store import load as load_partitions

    df = _prepare(load_partitions(parquet_path))
    rows = flow_rows(df)
    points = load_country_points(points_path or ROOT / "data" / "country_points.csv")
    missing = sorted({r["country"] for r in rows} - set(points))
    if missing:
        raise MissingCountryPointError(
            f"{len(missing)} nước chưa có toạ độ trong country_points.csv: "
            + ", ".join(missing) + " - thêm vào rồi chạy lại.")

    path = Path(out_dir) / "route_flows.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows, "points": points},
                               ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return str(path)


def main(argv=None):
    print(build(ROOT / "data" / "parts", ROOT / "data" / "agg"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
