from datetime import date, datetime
from pathlib import Path

import pandas as pd

from scraper.store import SCHEMA_COLUMNS

ROOT = Path(__file__).resolve().parent.parent


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


def test_unmapped_report_counts_only_the_latest_snapshot_per_day(monkeypatch, tmp_path):
    """A day re-crawled with a newly-mapped destination must not have its
    earlier (unmapped) snapshot counted too - otherwise this tool's unmapped
    share and coverage.json's unmapped share (which already uses
    latest_snapshot) drift apart once a day has multiple snapshots."""
    df = _df([
        # First (earlier) snapshot of this plan_date: destination "ZZZ",
        # which is never in berth_map.csv below.
        _row(row_key="a", plan_date=date(2026, 8, 11), to_raw="ZZZ",
             to_berth=None, crawled_at=datetime(2026, 8, 11)),
        # Second (later) snapshot of the SAME plan_date, same vessel: the
        # plan was revised and now points at a mapped destination.
        _row(row_key="a", plan_date=date(2026, 8, 11), to_raw="TAN VU",
             to_berth="Tân Vũ", crawled_at=datetime(2026, 8, 12)),
    ])
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    parts_dir = data_dir / "parts"
    parts_dir.mkdir()
    df.to_parquet(parts_dir / "ship_plan_2026-08.parquet", index=False)
    (data_dir / "berth_map.csv").write_text(
        "raw_name,berth,ticker,is_hai_phong,type\n"
        "TAN VU,Tân Vũ,PHP,true,berth\n",
        encoding="utf-8",
    )

    import tools.unmapped_report as module
    monkeypatch.setattr(module, "ROOT", tmp_path)
    module.main()

    out = pd.read_csv(data_dir / "unmapped_report.csv")
    # The earlier snapshot's "ZZZ" must be gone entirely - only the latest
    # snapshot's "TAN VU" (already mapped) should be counted.
    assert "ZZZ" not in set(out["raw_name"])
    tan_vu = out[out["raw_name"] == "TAN VU"]
    assert len(tan_vu) == 1
    assert bool(tan_vu.iloc[0]["mapped"]) is True
