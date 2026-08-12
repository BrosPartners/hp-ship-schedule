"""Precompute the JSON the analysis tab reads, so the page paints immediately."""

import json
from pathlib import Path

import pandas as pd

from scraper.store import latest_snapshot

ROOT = Path(__file__).resolve().parent.parent
DWT_BANDS = [(0, 5000), (5000, 20000), (20000, 50000), (50000, 100000),
             (100000, 10 ** 9)]
DRAFT_BANDS = [(0, 5), (5, 7), (7, 9), (9, 11), (11, 100)]


def _band(value, bands, suffix=""):
    if value is None or pd.isna(value):
        return None
    for low, high in bands:
        if low <= value < high:
            if high >= 10 ** 8 or high == 100:      # open-ended top band
                return f"{low:,.0f}{suffix}+"
            return f"{low:,.0f}-{high:,.0f}{suffix}"
    return None


def _prepare(df):
    df = latest_snapshot(df).copy()
    df["plan_date"] = pd.to_datetime(df["plan_date"])
    df["month"] = df["plan_date"].dt.strftime("%Y-%m")
    df["dwt"] = pd.to_numeric(df["dwt"], errors="coerce")
    df["gt"] = pd.to_numeric(df["gt"], errors="coerce")
    df["draft_m"] = pd.to_numeric(df["draft_m"], errors="coerce")
    return df


def throughput_rows(df):
    """Movements that represent a vessel arriving at a Hải Phòng berth.

    Arrivals count. Internal moves count only when the destination is a berth,
    otherwise an anchorage-to-anchorage shuffle would count the same vessel
    twice. Departures and channel transits never count.
    """
    arrivals = df["section"] == "vao_cang"
    moves = (df["section"] == "di_chuyen") & (df["to_type"] == "berth")
    return df[arrivals | moves]


def _write(out_dir, name, payload):
    path = Path(out_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return str(path)


def build_all(parquet_path, out_dir):
    raw = pd.read_parquet(parquet_path)
    df = _prepare(raw)
    thr = throughput_rows(df)
    written = {}

    # Chart 1 - monthly calls and tonnage
    monthly = (thr.groupby("month")
                  .agg(calls=("row_key", "count"),
                       dwt=("dwt", "sum"), gt=("gt", "sum"))
                  .reset_index())
    monthly[["dwt", "gt"]] = monthly[["dwt", "gt"]].fillna(0)
    written["monthly_volume"] = _write(out_dir, "monthly_volume", {
        "rows": [{"month": r.month, "calls": int(r.calls),
                  "dwt": int(r.dwt), "gt": int(r.gt)}
                 for r in monthly.itertuples()]
    })

    # Chart 2 - berth / ticker share by month
    share = (thr.assign(berth=thr["to_berth"].fillna("(chưa map)"),
                        ticker=thr["to_ticker"].fillna("(không niêm yết)"))
                .groupby(["month", "berth", "ticker"])
                .agg(calls=("row_key", "count"), dwt=("dwt", "sum"))
                .reset_index())
    written["berth_share"] = _write(out_dir, "berth_share", {
        "rows": [{"month": r.month, "berth": r.berth, "ticker": r.ticker,
                  "calls": int(r.calls), "dwt": int(r.dwt or 0)}
                 for r in share.itertuples()]
    })

    # Chart 3 - average size by month, plus draft distribution by berth
    size = (thr.groupby("month")
               .agg(dwt_avg=("dwt", "mean"), gt_avg=("gt", "mean"),
                    draft_avg=("draft_m", "mean"))
               .reset_index())
    draft_hist = (thr.assign(band=thr["draft_m"].apply(lambda v: _band(v, DRAFT_BANDS, "m")),
                             berth=thr["to_berth"].fillna("(chưa map)"))
                     .dropna(subset=["band"])
                     .groupby(["berth", "band"]).size()
                     .reset_index(name="calls"))
    written["vessel_size"] = _write(out_dir, "vessel_size", {
        "monthly": [{"month": r.month,
                     "dwt_avg": None if pd.isna(r.dwt_avg) else round(r.dwt_avg, 1),
                     "gt_avg": None if pd.isna(r.gt_avg) else round(r.gt_avg, 1),
                     "draft_avg": None if pd.isna(r.draft_avg) else round(r.draft_avg, 2)}
                    for r in size.itertuples()],
        "draft_hist": [{"berth": r.berth, "band": r.band, "calls": int(r.calls)}
                       for r in draft_hist.itertuples()],
        "dwt_bands": [{"berth": b, "band": d, "calls": int(n)} for (b, d), n in
                      thr.assign(band=thr["dwt"].apply(lambda v: _band(v, DWT_BANDS)),
                                 berth=thr["to_berth"].fillna("(chưa map)"))
                         .dropna(subset=["band"])
                         .groupby(["berth", "band"]).size().items()],
    })

    # Chart 4 - domestic vs international mix
    mix = (thr.groupby(["month", "is_domestic"])
              .agg(calls=("row_key", "count"), dwt=("dwt", "sum"))
              .reset_index())
    written["route_mix"] = _write(out_dir, "route_mix", {
        "rows": [{"month": r.month, "domestic": bool(r.is_domestic),
                  "calls": int(r.calls), "dwt": int(r.dwt or 0)}
                 for r in mix.itertuples()]
    })

    # Chart 5 - calls per calendar day
    daily = (thr.groupby(thr["plan_date"].dt.strftime("%Y-%m-%d"))
                .size().reset_index(name="calls"))
    daily.columns = ["date", "calls"]
    written["daily_heatmap"] = _write(out_dir, "daily_heatmap", {
        "rows": [{"date": r.date, "calls": int(r.calls)} for r in daily.itertuples()]
    })

    # Chart 6 - plan slippage: earliest vs latest snapshot of the same plan_date
    written["plan_slippage"] = _write(out_dir, "plan_slippage",
                                      _slippage(raw))

    # Filter options for the UI
    berths = sorted({b for b in pd.concat([df["from_berth"], df["to_berth"]]).dropna()})
    tickers = sorted({t for t in pd.concat([df["from_ticker"], df["to_ticker"]]).dropna()})
    written["filters"] = _write(out_dir, "filters", {
        "berths": berths,
        "tickers": tickers,
        "sections": ["roi_cang", "di_chuyen", "vao_cang", "qua_luong"],
        "date_min": df["plan_date"].min().strftime("%Y-%m-%d") if not df.empty else None,
        "date_max": df["plan_date"].max().strftime("%Y-%m-%d") if not df.empty else None,
        "dwt_max": int(df["dwt"].max()) if df["dwt"].notna().any() else 0,
        "draft_max": float(df["draft_m"].max()) if df["draft_m"].notna().any() else 0.0,
    })
    return written


def _slippage(raw):
    """Share of movements whose time or destination changed between snapshots.

    Empty for the whole backfill period, which only ever had one snapshot per
    plan_date. It fills in from the day the daily job starts running.
    """
    if raw.empty:
        return {"rows": [], "note": "chưa có dữ liệu nhiều snapshot"}
    df = raw.copy()
    df["crawl_day"] = pd.to_datetime(df["crawled_at"]).dt.date
    counts = df.groupby("plan_date")["crawl_day"].nunique()
    multi = counts[counts > 1].index
    if len(multi) == 0:
        return {"rows": [], "note": "chưa có dữ liệu nhiều snapshot"}

    rows = []
    for plan_date in sorted(multi):
        subset = df[df["plan_date"] == plan_date]
        first = subset[subset["crawl_day"] == subset["crawl_day"].min()]
        last = subset[subset["crawl_day"] == subset["crawl_day"].max()]
        first_idx = {(r.vessel_name, r.section): r for r in first.itertuples()}
        last_idx = {(r.vessel_name, r.section): r for r in last.itertuples()}
        common = set(first_idx) & set(last_idx)
        changed = sum(
            1 for k in common
            if first_idx[k].plan_time != last_idx[k].plan_time
            or first_idx[k].to_raw != last_idx[k].to_raw
        )
        rows.append({
            "plan_date": str(plan_date),
            "matched": len(common),
            "changed": changed,
            "dropped": len(set(first_idx) - set(last_idx)),
            "added": len(set(last_idx) - set(first_idx)),
            "pct_changed": round(100 * changed / len(common), 2) if common else None,
        })
    return {"rows": rows, "note": None}


def main():
    written = build_all(ROOT / "data" / "ship_plan.parquet", ROOT / "data" / "agg")
    for name, path in written.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
