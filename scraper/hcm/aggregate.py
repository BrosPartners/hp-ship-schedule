"""Precompute the JSON the TP.HCM tab reads, so the page paints immediately.

Deliberately simpler than `scraper.aggregate` (Hai Phong): six chart files
instead of seven, no plan-slippage/zone-share/route-mix equivalents. The
owner has not asked for feature parity between the two ports, and this
dataset's dominant analytical dimension is `cluster` (Cat Lai, Cai Mep,
SP-ITC, ...), not the individual berth.
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from scraper.store import latest_snapshot, load as load_partitions
from scraper.coverage import load_cluster_zones, load_coverage

ROOT = Path(__file__).resolve().parent.parent.parent
DRAFT_BANDS = [(0, 5), (5, 7), (7, 9), (9, 11), (11, 100)]


def _band(value, bands, suffix=""):
    if value is None or pd.isna(value):
        return None
    for low, high in bands:
        if low <= value < high:
            if high >= 100:
                return f"{low:,.0f}{suffix}+"
            return f"{low:,.0f}-{high:,.0f}{suffix}"
    return None


def _prepare(df):
    df = latest_snapshot(df).copy()
    df["plan_date"] = pd.to_datetime(df["plan_date"])
    df["month"] = df["plan_date"].dt.strftime("%Y-%m")
    df["dwt"] = pd.to_numeric(df["dwt"], errors="coerce")
    df["loa_m"] = pd.to_numeric(df["loa_m"], errors="coerce")
    df["draft_m"] = pd.to_numeric(df["draft_m"], errors="coerce")
    return df


def throughput_rows(df):
    """Movements that represent a vessel calling at a TP.HCM berth.

    Mirrors the Hai Phong rule exactly: a row counts only when its
    destination (`to_type`) is a berth, and only for these two sections:
      - `tau_vao` (arrival) rows whose `to_type == "berth"`.
      - `tau_di_chuyen` (internal move) rows whose `to_type == "berth"`.

    Three categories of destination are deliberately excluded from
    throughput, by explicit owner decision, because counting them would
    badly inflate the numbers:
      - `anchorage` (~15.8% of all from/to slots): NEO VT roads and similar
        anchorages, not a berth call.
      - `construction` (~8.3%): dredging, spoil grounds, land reclamation and
        port-construction sites. TP.HCM's plan carries a lot of this traffic
        - dredgers and construction barges - that Hai Phong's plan does not,
        and it is not commercial port throughput.
      - `external` and unmapped destinations (~39.9% combined): not
        attributable to any TP.HCM berth.

    Departures (`tau_roi`) never count, on either port's dashboard - a
    departure is the mirror image of an arrival/move already counted, and
    counting both would double the total.

    On the Hai Phong side, an equivalent over-count (counting anchorage
    arrivals as throughput) went unnoticed until a late review and required
    re-baselining every chart in the analysis tab. Do not repeat that here.
    """
    arrivals = (df["section"] == "tau_vao") & (df["to_type"] == "berth")
    moves = (df["section"] == "tau_di_chuyen") & (df["to_type"] == "berth")
    return df[arrivals | moves]


def _write(out_dir, name, payload):
    path = Path(out_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return str(path)


def build_all(parquet_path, out_dir, today=None):
    """Build every chart JSON the TP.HCM tab reads.

    `today` is the cutoff for the aggregates: rows with `plan_date` later
    than `today` are dropped from `df` before any chart is computed, exactly
    as `scraper.aggregate.build_all` does, so a partially-published future
    day never drags down a monthly/daily aggregate. Defaults to
    `date.today()`; tests pass an explicit value to stay hermetic.
    """
    cutoff = today or date.today()
    raw = load_partitions(parquet_path)
    df = _prepare(raw)
    df = df[df["plan_date"] <= pd.Timestamp(cutoff)]
    thr = throughput_rows(df)
    written = {}

    # Chart 1 - monthly throughput movements and total DWT
    monthly = (thr.groupby("month")
                  .agg(calls=("row_key", "count"), dwt=("dwt", "sum"))
                  .reset_index())
    monthly["dwt"] = monthly["dwt"].fillna(0)
    written["monthly_volume"] = _write(out_dir, "monthly_volume", {
        "rows": [{"month": r.month, "calls": int(r.calls), "dwt": int(r.dwt)}
                 for r in monthly.itertuples()]
    })

    # Chart 2 - cluster share by month (the meaningful commercial dimension
    # for this port, the way berth was for Hai Phong)
    cshare = (thr.assign(cluster=thr["to_cluster"].fillna("(chưa map)"))
                 .groupby(["month", "cluster"])
                 .agg(calls=("row_key", "count"), dwt=("dwt", "sum"))
                 .reset_index())
    # Nguồn TP.HCM chỉ đăng khu Vũng Tàu - Cái Mép từ 01/08/2025. Vài lượt lẻ
    # trước đó không phải "thị phần gần 0" mà là chưa có dữ liệu; để nguyên sẽ
    # vẽ ra một cú tăng trưởng bùng nổ không có thật.
    coverage = load_coverage(ROOT / "data" / "hcm" / "source_coverage.csv")
    if coverage:
        starts = cshare["cluster"].map(coverage)
        cshare = cshare[starts.isna() | (cshare["month"] >= starts)]
    # Zone là hàm thuần của cluster nên tra ở đây thay vì ghi vào Parquet:
    # sửa phân vùng chỉ cần chạy lại aggregate, không phải remap 44 partition.
    zones = load_cluster_zones(ROOT / "data" / "hcm" / "cluster_zones.csv")
    zone_of = cshare["cluster"].map(zones).fillna("chua_xep")
    written["cluster_share"] = _write(out_dir, "cluster_share", {
        "rows": [{"month": r.month, "cluster": r.cluster, "zone": z,
                  "calls": int(r.calls), "dwt": int(r.dwt or 0)}
                 for r, z in zip(cshare.itertuples(), zone_of)],
        "coverage": coverage,
    })

    # Chart zone - dịch chuyển giữa các khu, đối xứng với chart 7 của Hải Phòng
    zshare = (cshare.assign(zone=zone_of.values)
                    .groupby(["month", "zone"])
                    .agg(calls=("calls", "sum"), dwt=("dwt", "sum"))
                    .reset_index())
    written["zone_share"] = _write(out_dir, "zone_share", {
        "rows": [{"month": r.month, "zone": r.zone,
                  "calls": int(r.calls), "dwt": int(r.dwt or 0)}
                 for r in zshare.itertuples()]
    })

    # Chart 3 - average vessel size by month, plus draft distribution
    size = (thr.groupby("month")
               .agg(dwt_avg=("dwt", "mean"), loa_avg=("loa_m", "mean"),
                    draft_avg=("draft_m", "mean"))
               .reset_index())
    draft_hist = (thr.assign(band=thr["draft_m"].apply(lambda v: _band(v, DRAFT_BANDS, "m")))
                     .dropna(subset=["band"])
                     .groupby("band").size()
                     .reset_index(name="calls"))
    written["vessel_size"] = _write(out_dir, "vessel_size", {
        "monthly": [{"month": r.month,
                     "dwt_avg": None if pd.isna(r.dwt_avg) else round(r.dwt_avg, 1),
                     "loa_avg": None if pd.isna(r.loa_avg) else round(r.loa_avg, 1),
                     "draft_avg": None if pd.isna(r.draft_avg) else round(r.draft_avg, 2)}
                    for r in size.itertuples()],
        "draft_hist": [{"band": r.band, "calls": int(r.calls)}
                       for r in draft_hist.itertuples()],
    })

    # Chart 4 - movements per calendar day
    daily = (thr.groupby(thr["plan_date"].dt.strftime("%Y-%m-%d"))
                .size().reset_index(name="calls"))
    daily.columns = ["date", "calls"]
    written["daily_heatmap"] = _write(out_dir, "daily_heatmap", {
        "rows": [{"date": r.date, "calls": int(r.calls)} for r in daily.itertuples()]
    })

    # Chart tuyến (thay thế) - KHÔNG phải cảng đi/đến thật: nguồn TP.HCM không
    # công bố cột này (xem HCM_ROUTE_NOTE ở web/index.html). Đây chỉ là cờ tàu
    # (nationality/flag of convenience) - một tàu treo cờ Panama hay Liberia
    # tuyệt đại đa số không đi Panama/Liberia, cờ thuận tiện chỉ phản ánh nơi
    # đăng ký tàu. Vẫn hữu ích để thấy tỷ trọng tàu Việt Nam so với tàu nước
    # ngoài theo thời gian, nhưng UI phải luôn ghi rõ đây không phải tuyến.
    # Gộp vài biến thể ghi tên khác nhau của cùng một nước (không đổi ý nghĩa,
    # chỉ tránh xé lẻ "MARSHALL ISL" và "MARSHALL ISLANDS" thành hai lát khác
    # nhau của cùng một cờ tàu).
    NATIONALITY_ALIAS = {
        "MARSHALL ISL": "MARSHALL ISLANDS",
        "KOREA (REPUBLIC)": "KOREA",
    }
    nat = thr["nationality"].fillna("(không rõ)").replace(NATIONALITY_ALIAS)
    top_nat = nat.value_counts().head(10).index
    nat_grouped = nat.where(nat.isin(top_nat), "Khác")
    nmix = (thr.assign(nationality=nat_grouped.values)
               .groupby(["month", "nationality"])
               .agg(calls=("row_key", "count"))
               .reset_index())
    written["nationality_mix"] = _write(out_dir, "nationality_mix", {
        "rows": [{"month": r.month, "nationality": r.nationality, "calls": int(r.calls)}
                 for r in nmix.itertuples()]
    })

    # Filter options for the UI
    # Chỉ liệt kê cụm còn là bến thương mại. Cụm đã bị đánh `external` (Ba Son)
    # vẫn còn giá trị `cluster` trong Parquet, nên nếu lấy thẳng cột cluster thì
    # nó vẫn hiện trong ô lọc dù đã biến khỏi mọi chart.
    clusters = sorted({
        *df.loc[df["from_type"] == "berth", "from_cluster"].dropna(),
        *df.loc[df["to_type"] == "berth", "to_cluster"].dropna(),
    })
    sections = ["tau_vao", "tau_roi", "tau_di_chuyen"]
    written["filters"] = _write(out_dir, "filters", {
        "clusters": clusters,
        # Tab tra cứu lọc theo khu, mà zone chỉ có ở tầng tổng hợp (không nằm
        # trong Parquet), nên gửi kèm bảng tra cụm -> khu cho trình duyệt.
        "cluster_zones": {c: zones[c] for c in clusters if c in zones},
        "zones": sorted({zones[c] for c in clusters if c in zones}),
        "sections": sections,
        "date_min": df["plan_date"].min().strftime("%Y-%m-%d") if not df.empty else None,
        "date_max": df["plan_date"].max().strftime("%Y-%m-%d") if not df.empty else None,
        "dwt_max": int(df["dwt"].max()) if df["dwt"].notna().any() else 0,
        "draft_max": float(df["draft_m"].max()) if df["draft_m"].notna().any() else 0.0,
    })

    # Cluster-mapping coverage, mirroring Hai Phong's coverage.json
    slots, unmapped = 0, Counter()
    recent = df[df["plan_date"] >= df["plan_date"].max() - pd.Timedelta(days=30)] \
        if not df.empty else df
    recent_slots, recent_unmapped = 0, 0
    for frame, is_recent in ((df, False), (recent, True)):
        for side in ("from", "to"):
            pos_col, berth_col = f"{side}_position", f"{side}_berth"
            mask = frame[pos_col].notna()
            miss = mask & frame[berth_col].isna()
            if is_recent:
                recent_slots += int(mask.sum())
                recent_unmapped += int(miss.sum())
            else:
                slots += int(mask.sum())
                for value in frame.loc[miss, pos_col]:
                    unmapped[str(value).strip().upper()] += 1
    written["coverage"] = _write(out_dir, "coverage", {
        "unmapped_pct_all": round(100 * sum(unmapped.values()) / slots, 2) if slots else 0.0,
        "unmapped_pct_30d": round(100 * recent_unmapped / recent_slots, 2) if recent_slots else 0.0,
        "top_unmapped": [{"raw_name": k, "n": int(v)}
                         for k, v in unmapped.most_common(30)],
    })
    return written


def main():
    written = build_all(ROOT / "data" / "hcm" / "parts", ROOT / "data" / "hcm" / "agg")
    for name, path in written.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
