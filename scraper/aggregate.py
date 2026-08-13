"""Precompute the JSON the analysis tab reads, so the page paints immediately."""

import json
from datetime import date
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
    """Movements that represent a vessel calling at a Hải Phòng berth.

    This is "lượt cập cầu bến" (berth calls), not port-wide arrivals: a row
    counts only when its destination (`to_type`) is a berth. That applies to
    both clauses:
      - `vao_cang` (arrival) rows whose `to_type == "berth"`.
      - `di_chuyen` (internal move) rows whose `to_type == "berth"`.

    Three categories of `vao_cang` row are deliberately excluded, because each
    would otherwise inflate the count:
      - Landing at an anchorage (`to_type == "anchorage"`): a large share of
        these vessels have a matching `di_chuyen` to a berth for the same
        voyage within a few days, so counting the anchorage arrival too would
        double-count a single vessel call.
      - Landing outside Hải Phòng (`to_type == "external"`, e.g. Bến Lâm,
        Cảng cá Hạ Long, Nam Ninh, Hạ Long): not Hải Phòng throughput at all.
      - Landing at an unmapped destination (`to_type` is null): cannot be
        attributed to any berth, so it cannot be counted as a berth call.

    Departures (`roi_cang`) and channel transits (`qua_luong`) never count.
    """
    arrivals = (df["section"] == "vao_cang") & (df["to_type"] == "berth")
    moves = (df["section"] == "di_chuyen") & (df["to_type"] == "berth")
    return df[arrivals | moves]


def _write(out_dir, name, payload):
    path = Path(out_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    return str(path)


def build_all(parquet_path, out_dir, today=None):
    """Build every chart JSON the analysis tab reads.

    `today` is the cutoff for the aggregates: rows with `plan_date` later than
    `today` are dropped from `df` before any chart is computed, so they are
    absent from every chart json and from `filters.date_max`. This keeps a
    partially-published future day (the daily job stores "tomorrow", whose
    plan is only partly published) from dragging down monthly/daily
    aggregates. The raw stored parquet and the lookup tab are untouched -
    this only trims what feeds the aggregates. Defaults to `date.today()`;
    tests pass an explicit value to stay hermetic.
    """
    cutoff = today or date.today()
    raw = pd.read_parquet(parquet_path)
    df = _prepare(raw)
    df = df[df["plan_date"] <= pd.Timestamp(cutoff)]
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

    # Berth-mapping coverage, surfaced in the UI rather than buried in a log
    from collections import Counter
    slots, unmapped = 0, Counter()
    recent = df[df["plan_date"] >= df["plan_date"].max() - pd.Timedelta(days=30)] \
        if not df.empty else df
    recent_slots, recent_unmapped = 0, 0
    for frame, is_recent in ((df, False), (recent, True)):
        for side in ("from", "to"):
            raw_col, berth_col = f"{side}_raw", f"{side}_berth"
            mask = frame[raw_col].notna()
            miss = mask & frame[berth_col].isna()
            if is_recent:
                recent_slots += int(mask.sum())
                recent_unmapped += int(miss.sum())
            else:
                slots += int(mask.sum())
                for value in frame.loc[miss, raw_col]:
                    unmapped[str(value).strip().upper()] += 1
    written["coverage"] = _write(out_dir, "coverage", {
        "unmapped_pct_all": round(100 * sum(unmapped.values()) / slots, 2) if slots else 0.0,
        "unmapped_pct_30d": round(100 * recent_unmapped / recent_slots, 2) if recent_slots else 0.0,
        "top_unmapped": [{"raw_name": k, "n": int(v)}
                         for k, v in unmapped.most_common(30)],
    })
    return written


_BASELINE_NOTE = (
    "Baseline for each plan_date is the earliest snapshot, captured the day "
    "before while the plan was only partly published. 'added' is therefore "
    "dominated by publication, not schedule changes, and pct_changed is "
    "computed only over the movements that already existed in that "
    "pre-publication snapshot."
)


def _time_changed(a, b):
    """Null-safe inequality: two nulls are not a change (pd.NaT != pd.NaT is True)."""
    if pd.isna(a) and pd.isna(b):
        return False
    return a != b


def _slippage(raw):
    """Share of movements whose time or destination changed between snapshots.

    Empty for the whole backfill period, which only ever had one snapshot per
    plan_date. It fills in from the day the daily job starts running.
    """
    if raw.empty:
        return {"rows": [], "note": "chưa có dữ liệu nhiều snapshot",
                "baseline_note": _BASELINE_NOTE}
    df = raw.copy()
    df["crawl_day"] = pd.to_datetime(df["crawled_at"]).dt.date
    counts = df.groupby("plan_date")["crawl_day"].nunique()
    multi = counts[counts > 1].index
    if len(multi) == 0:
        return {"rows": [], "note": "chưa có dữ liệu nhiều snapshot",
                "baseline_note": _BASELINE_NOTE}

    def _grouped(snapshot):
        groups = {}
        for r in snapshot.itertuples():
            groups.setdefault((r.vessel_name, r.section), []).append(r)
        for key, items in groups.items():
            items.sort(key=lambda r: (r.plan_time is None, r.plan_time))
        return groups

    rows = []
    for plan_date in sorted(multi):
        subset = df[df["plan_date"] == plan_date]
        first = subset[subset["crawl_day"] == subset["crawl_day"].min()]
        last = subset[subset["crawl_day"] == subset["crawl_day"].max()]
        first_groups = _grouped(first)
        last_groups = _grouped(last)

        matched = 0
        changed = 0
        dropped = 0
        added = 0
        for key in set(first_groups) | set(last_groups):
            first_list = first_groups.get(key, [])
            last_list = last_groups.get(key, [])
            n = min(len(first_list), len(last_list))
            matched += n
            for i in range(n):
                a, b = first_list[i], last_list[i]
                if _time_changed(a.plan_time, b.plan_time) or a.to_raw != b.to_raw:
                    changed += 1
            dropped += len(first_list) - n
            added += len(last_list) - n

        rows.append({
            "plan_date": str(plan_date),
            "matched": matched,
            "changed": changed,
            "dropped": dropped,
            "added": added,
            "pct_changed": round(100 * changed / matched, 2) if matched else None,
        })
    return {"rows": rows, "note": None, "baseline_note": _BASELINE_NOTE}


def main():
    written = build_all(ROOT / "data" / "ship_plan.parquet", ROOT / "data" / "agg")
    for name, path in written.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
