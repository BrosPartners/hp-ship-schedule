import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from scraper.hcm.aggregate import build_all, throughput_rows
from scraper.hcm.store import SCHEMA_COLUMNS


def _df(rows):
    frame = pd.DataFrame(rows)
    for column in SCHEMA_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[SCHEMA_COLUMNS]


def _write_parts(dir_path, df):
    """Write `df` into the monthly partition layout `build_all` reads."""
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    months = pd.to_datetime(df["plan_date"]).dt.strftime("%Y-%m")
    for month, group in df.groupby(months):
        group.to_parquet(dir_path / f"ship_plan_{month}.parquet", index=False)


def _row(**kw):
    base = dict(
        plan_date=date(2026, 8, 11), section="tau_vao", vessel_name="SHIP",
        nationality="VN", call_sign="ABC1", dwt=10000, loa_m=150.0, draft_m=7.0,
        cargo_type="container", from_position="LUONG", to_position="C.LAI 1",
        eta=datetime(2026, 8, 11, 6, 0), etd=None, tugs="1", agent="AGENT",
        channel="Soai Rap", crawled_at=datetime(2026, 8, 12), row_key="k",
        from_berth=None, to_berth="Cat Lai 1", from_cluster=None, to_cluster="Cat Lai",
        from_ticker=None, to_ticker=None, from_type=None, to_type="berth",
    )
    base.update(kw)
    return base


def test_throughput_excludes_anchorage_construction_external_unmapped():
    df = _df([
        _row(row_key="a", section="tau_vao", to_type="berth"),
        _row(row_key="b", section="tau_vao", to_type="anchorage",
             to_berth=None, to_cluster=None),
        _row(row_key="c", section="tau_vao", to_type="construction",
             to_berth=None, to_cluster=None),
        _row(row_key="d", section="tau_vao", to_type="external",
             to_berth=None, to_cluster=None),
        _row(row_key="e", section="tau_vao", to_type=None,
             to_berth=None, to_cluster=None),
        _row(row_key="f", section="tau_di_chuyen", to_type="berth"),
        _row(row_key="g", section="tau_di_chuyen", to_type="anchorage",
             to_berth=None, to_cluster=None),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a", "f"}


def test_throughput_excludes_departures():
    df = _df([
        _row(row_key="a", section="tau_vao", to_type="berth"),
        _row(row_key="b", section="tau_roi", to_type="berth"),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a"}


def test_only_latest_snapshot_feeds_the_aggregates(tmp_path):
    parquet = tmp_path / "parts"
    _write_parts(parquet, _df([
        _row(row_key="a", crawled_at=datetime(2026, 8, 11)),
        _row(row_key="a", crawled_at=datetime(2026, 8, 12)),
    ]))
    build_all(parquet, tmp_path / "agg")
    data = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    assert next(r for r in data["rows"] if r["month"] == "2026-08")["calls"] == 1


def test_build_all_excludes_future_dated_rows_from_charts(tmp_path):
    parquet = tmp_path / "parts"
    _write_parts(parquet, _df([
        _row(row_key="a", plan_date=date(2026, 8, 11)),
        _row(row_key="b", plan_date=date(2026, 8, 12)),
    ]))
    build_all(parquet, tmp_path / "agg", today=date(2026, 8, 11))

    monthly = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    entry = next(r for r in monthly["rows"] if r["month"] == "2026-08")
    assert entry["calls"] == 1

    heatmap = json.loads((tmp_path / "agg" / "daily_heatmap.json").read_text(encoding="utf-8"))
    assert {r["date"] for r in heatmap["rows"]} == {"2026-08-11"}

    filters = json.loads((tmp_path / "agg" / "filters.json").read_text(encoding="utf-8"))
    assert filters["date_max"] == "2026-08-11"


def test_cluster_share_reconciles_with_monthly_volume(tmp_path):
    parquet = tmp_path / "parts"
    _write_parts(parquet, _df([
        _row(row_key="a", to_cluster="Cat Lai", dwt=10000),
        _row(row_key="b", to_cluster="Cai Mep", dwt=5000),
        _row(row_key="c", to_cluster=None, dwt=1000),
    ]))
    build_all(parquet, tmp_path / "agg")
    monthly = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    cluster = json.loads((tmp_path / "agg" / "cluster_share.json").read_text(encoding="utf-8"))

    month_calls = next(r for r in monthly["rows"] if r["month"] == "2026-08")["calls"]
    month_dwt = next(r for r in monthly["rows"] if r["month"] == "2026-08")["dwt"]
    cluster_rows = [r for r in cluster["rows"] if r["month"] == "2026-08"]
    assert sum(r["calls"] for r in cluster_rows) == month_calls == 3
    assert sum(r["dwt"] for r in cluster_rows) == month_dwt == 16000
    assert {r["cluster"] for r in cluster_rows} == {"Cat Lai", "Cai Mep", "(chưa map)"}


def test_build_all_writes_every_chart_file(tmp_path):
    parquet = tmp_path / "parts"
    _write_parts(parquet, _df([_row(row_key="a"),
                                _row(row_key="b", plan_date=date(2026, 7, 3),
                                     eta=datetime(2026, 7, 3, 8, 0))]))
    out = build_all(parquet, tmp_path / "agg")
    for name in ("monthly_volume", "cluster_share", "vessel_size",
                 "daily_heatmap", "filters", "coverage"):
        path = tmp_path / "agg" / f"{name}.json"
        assert path.exists(), f"{name}.json missing"
        json.loads(path.read_text(encoding="utf-8"))
    assert set(out) >= {"monthly_volume", "filters"}
