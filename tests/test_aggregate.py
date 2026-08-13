import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from scraper.aggregate import _slippage, build_all, throughput_rows
from scraper.store import SCHEMA_COLUMNS


def _df(rows):
    frame = pd.DataFrame(rows)
    for column in SCHEMA_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[SCHEMA_COLUMNS]


def _row(**kw):
    base = dict(
        plan_date=date(2026, 8, 11), section="vao_cang",
        plan_time=datetime(2026, 8, 11, 6, 0), vessel_name="SHIP",
        is_sb=False, draft_m=7.0, loa_m=100.0, dwt=10000, gt=8000,
        channel_code="HN", from_raw="CHINA", to_raw="TAN VU",
        from_berth="Trung Quốc", to_berth="Tân Vũ", to_ticker="PHP",
        from_type="foreign", to_type="berth", is_domestic=False,
        crawled_at=datetime(2026, 8, 12), row_key="k",
    )
    base.update(kw)
    return base


def test_throughput_excludes_anchorage_to_anchorage_moves():
    df = _df([
        _row(row_key="a", section="vao_cang"),
        _row(row_key="b", section="di_chuyen", from_type="anchorage",
             to_type="anchorage", from_berth="Neo A", to_berth="Neo B"),
        _row(row_key="c", section="di_chuyen", from_type="anchorage",
             to_type="berth", to_berth="Tân Vũ"),
    ])
    keys = set(throughput_rows(df)["row_key"])
    assert keys == {"a", "c"}, "anchorage-to-anchorage double-counts a vessel"


def test_throughput_excludes_departures_and_channel_transits():
    df = _df([
        _row(row_key="a", section="vao_cang"),
        _row(row_key="b", section="roi_cang"),
        _row(row_key="c", section="qua_luong"),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a"}


def test_throughput_excludes_vao_cang_landing_at_anchorage():
    """An anchorage arrival must not be counted, or the same vessel is
    double-counted once more when it later moves on to a berth."""
    df = _df([
        _row(row_key="a", section="vao_cang", to_type="berth"),
        _row(row_key="b", section="vao_cang", to_type="anchorage",
             to_berth=None, to_ticker=None),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a"}


def test_throughput_excludes_vao_cang_landing_outside_hai_phong():
    """An arrival at an external destination (e.g. Bến Lâm, Nam Ninh) is not
    Hải Phòng throughput and must not be counted."""
    df = _df([
        _row(row_key="a", section="vao_cang", to_type="berth"),
        _row(row_key="b", section="vao_cang", to_type="external",
             to_berth=None, to_ticker=None),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a"}


def test_throughput_excludes_vao_cang_with_unmapped_destination():
    """An arrival whose destination never resolved (to_type is null) cannot
    be attributed to any berth and must not be counted."""
    df = _df([
        _row(row_key="a", section="vao_cang", to_type="berth"),
        _row(row_key="b", section="vao_cang", to_type=None,
             to_berth=None, to_ticker=None),
    ])
    assert set(throughput_rows(df)["row_key"]) == {"a"}


def test_build_all_writes_every_chart_file(tmp_path):
    parquet = tmp_path / "d.parquet"
    _df([_row(row_key="a"), _row(row_key="b", plan_date=date(2026, 7, 3),
                                  plan_time=datetime(2026, 7, 3, 8, 0))]
        ).to_parquet(parquet, index=False)
    out = build_all(parquet, tmp_path / "agg")
    for name in ("monthly_volume", "berth_share", "vessel_size",
                 "route_mix", "daily_heatmap", "plan_slippage", "filters"):
        path = tmp_path / "agg" / f"{name}.json"
        assert path.exists(), f"{name}.json missing"
        json.loads(path.read_text(encoding="utf-8"))
    assert set(out) >= {"monthly_volume", "filters"}


def test_monthly_volume_has_month_calls_and_dwt(tmp_path):
    parquet = tmp_path / "d.parquet"
    _df([_row(row_key="a", dwt=10000), _row(row_key="b", dwt=5000)]
        ).to_parquet(parquet, index=False)
    build_all(parquet, tmp_path / "agg")
    data = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    entry = next(r for r in data["rows"] if r["month"] == "2026-08")
    assert entry["calls"] == 2
    assert entry["dwt"] == 15000


def test_only_latest_snapshot_feeds_the_aggregates(tmp_path):
    """Two snapshots of one day must not double the monthly call count."""
    parquet = tmp_path / "d.parquet"
    _df([
        _row(row_key="a", crawled_at=datetime(2026, 8, 11)),
        _row(row_key="a", crawled_at=datetime(2026, 8, 12)),
    ]).to_parquet(parquet, index=False)
    build_all(parquet, tmp_path / "agg")
    data = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    assert next(r for r in data["rows"] if r["month"] == "2026-08")["calls"] == 1


def test_slippage_same_vessel_section_collision_matches_positionally():
    """Three same-day movements of one vessel in one section must not
    collapse to a single match under a (vessel_name, section) dict key."""
    d = date(2026, 8, 11)
    early = datetime(2026, 8, 11)
    late = datetime(2026, 8, 12)
    rows = []
    for i, t in enumerate([6, 10, 14]):
        rows.append(_row(row_key=f"a{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=early))
    for i, t in enumerate([6, 11, 14]):  # second movement's time changed
        rows.append(_row(row_key=f"b{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=late))
    df = _df(rows)
    result = _slippage(df)
    row = result["rows"][0]
    assert row["matched"] == 3
    assert row["changed"] == 1


def test_slippage_shrinking_key_counts_dropped_without_crashing():
    d = date(2026, 8, 11)
    early = datetime(2026, 8, 11)
    late = datetime(2026, 8, 12)
    rows = []
    for i, t in enumerate([6, 10, 14]):
        rows.append(_row(row_key=f"a{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=early))
    for i, t in enumerate([6, 10]):
        rows.append(_row(row_key=f"b{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=late))
    df = _df(rows)
    result = _slippage(df)
    row = result["rows"][0]
    assert row["matched"] == 2
    assert row["dropped"] == 1


def test_slippage_growing_key_counts_added():
    d = date(2026, 8, 11)
    early = datetime(2026, 8, 11)
    late = datetime(2026, 8, 12)
    rows = []
    for i, t in enumerate([6, 10]):
        rows.append(_row(row_key=f"a{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=early))
    for i, t in enumerate([6, 10, 14]):
        rows.append(_row(row_key=f"b{i}", plan_date=d, section="di_chuyen",
                          plan_time=datetime(2026, 8, 11, t, 0),
                          to_raw=f"BERTH{i}", crawled_at=late))
    df = _df(rows)
    result = _slippage(df)
    row = result["rows"][0]
    assert row["matched"] == 2
    assert row["added"] == 1


def test_slippage_single_snapshot_still_short_circuits():
    df = _df([_row(row_key="a")])
    result = _slippage(df)
    assert result["rows"] == []
    assert result["note"] == "chưa có dữ liệu nhiều snapshot"


def test_slippage_null_plan_time_is_not_treated_as_changed():
    """pd.NaT != pd.NaT is True; a null-safe comparison must not count two
    null plan_times as a change."""
    d = date(2026, 8, 11)
    early = datetime(2026, 8, 11)
    late = datetime(2026, 8, 12)
    rows = [
        _row(row_key="a", plan_date=d, section="di_chuyen",
             plan_time=None, to_raw="BERTH0", crawled_at=early),
        _row(row_key="b", plan_date=d, section="di_chuyen",
             plan_time=None, to_raw="BERTH0", crawled_at=late),
    ]
    df = _df(rows)
    result = _slippage(df)
    row = result["rows"][0]
    assert row["matched"] == 1
    assert row["changed"] == 0


def test_slippage_reports_a_baseline_note_in_every_branch():
    """The chart's label must state that its baseline is a pre-publication
    stub, not the fully-published plan."""
    empty_result = _slippage(_df([]))
    assert "baseline_note" in empty_result
    assert empty_result["baseline_note"]

    single_snapshot_result = _slippage(_df([_row(row_key="a")]))
    assert single_snapshot_result["baseline_note"]

    d = date(2026, 8, 11)
    early = datetime(2026, 8, 11)
    late = datetime(2026, 8, 12)
    rows = [
        _row(row_key="a", plan_date=d, section="di_chuyen",
             to_raw="BERTH0", crawled_at=early),
        _row(row_key="b", plan_date=d, section="di_chuyen",
             to_raw="BERTH0", crawled_at=late),
    ]
    multi_snapshot_result = _slippage(_df(rows))
    assert multi_snapshot_result["baseline_note"]


def test_coverage_json_reports_unmapped_share(tmp_path):
    parquet = tmp_path / "d.parquet"
    _df([
        _row(row_key="a", to_raw="TAN VU", to_berth="Tân Vũ"),
        _row(row_key="b", to_raw="ZZZ", to_berth=None,
             from_raw="CHINA", from_berth="Trung Quốc"),
    ]).to_parquet(parquet, index=False)
    build_all(parquet, tmp_path / "agg")
    cov = json.loads((tmp_path / "agg" / "coverage.json").read_text(encoding="utf-8"))
    # 4 slots total, 1 unmapped ('ZZZ')
    assert cov["unmapped_pct_all"] == 25.0
    assert cov["top_unmapped"][0]["raw_name"] == "ZZZ"


def test_build_all_excludes_future_dated_rows_from_charts(tmp_path):
    """A future-dated row (e.g. the daily job's partly-published 'tomorrow')
    is stored but must not drag down monthly_volume or daily_heatmap."""
    parquet = tmp_path / "d.parquet"
    _df([
        _row(row_key="a", plan_date=date(2026, 8, 11),
             plan_time=datetime(2026, 8, 11, 6, 0)),
        _row(row_key="b", plan_date=date(2026, 8, 12),
             plan_time=datetime(2026, 8, 12, 6, 0)),
    ]).to_parquet(parquet, index=False)
    build_all(parquet, tmp_path / "agg", today=date(2026, 8, 11))

    monthly = json.loads((tmp_path / "agg" / "monthly_volume.json").read_text(encoding="utf-8"))
    entry = next(r for r in monthly["rows"] if r["month"] == "2026-08")
    assert entry["calls"] == 1

    heatmap = json.loads((tmp_path / "agg" / "daily_heatmap.json").read_text(encoding="utf-8"))
    assert {r["date"] for r in heatmap["rows"]} == {"2026-08-11"}

    filters = json.loads((tmp_path / "agg" / "filters.json").read_text(encoding="utf-8"))
    assert filters["date_max"] == "2026-08-11"


def test_filters_json_lists_berths_and_range(tmp_path):
    parquet = tmp_path / "d.parquet"
    _df([_row(row_key="a")]).to_parquet(parquet, index=False)
    build_all(parquet, tmp_path / "agg")
    filters = json.loads((tmp_path / "agg" / "filters.json").read_text(encoding="utf-8"))
    assert "Tân Vũ" in filters["berths"]
    assert filters["date_min"] == "2026-08-11"
    assert "PHP" in filters["tickers"]
