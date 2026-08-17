from datetime import date, datetime

import pandas as pd
import pytest

from scraper.store import SCHEMA_COLUMNS
from tools.remap_berths import run

MAP_HEADER = "raw_name,berth,ticker,is_hai_phong,type,zone\n"


def _write_map(path, rows):
    path.write_text(MAP_HEADER + "".join(rows), encoding="utf-8")
    return str(path)


def _frame(rows):
    df = pd.DataFrame(rows)
    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[SCHEMA_COLUMNS]


def _record(from_raw, to_raw, **overrides):
    rec = {
        "plan_date": date(2026, 8, 1), "section": "vao_cang",
        "vessel_name": "TAU A", "from_raw": from_raw, "to_raw": to_raw,
        "from_berth": None, "to_berth": None,
        "from_ticker": None, "to_ticker": None,
        "from_type": None, "to_type": None,
        "from_zone": None, "to_zone": None, "is_domestic": False,
        "crawled_at": datetime(2026, 8, 1, 7, 0), "row_key": "k1",
    }
    rec.update(overrides)
    return rec


@pytest.fixture()
def dataset(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    _frame([_record("HON DAU", "NAM HAI", to_ticker="GMD", to_berth="Nam Hải",
                    to_type="berth", to_zone="ha_nguon", row_key="k1"),
            _record("HON DAU", "HTIT", to_berth="HTIT", to_type="berth",
                    to_zone="lach_huyen", row_key="k2")]) \
        .to_parquet(parts / "ship_plan_2026-08.parquet", index=False)
    map_path = _write_map(tmp_path / "berth_map.csv", [
        "HON DAU,Hòn Dấu,,True,anchorage,ha_nguon\n",
        "NAM HAI,Nam Hải,,True,berth,ha_nguon\n",
        "HTIT,HTIT,PHP,True,berth,lach_huyen\n",
    ])
    return parts, map_path


def _tickers(parts):
    df = pd.read_parquet(parts / "ship_plan_2026-08.parquet")
    col = df.sort_values("row_key")["to_ticker"]
    return [None if pd.isna(v) else v for v in col]


def test_dry_run_reports_without_writing(dataset):
    parts, map_path = dataset
    counts = run(str(parts), map_path, apply_changes=False)

    assert counts["to_ticker"] == 2
    assert _tickers(parts) == ["GMD", None]


def test_apply_rewrites_tickers_from_the_map(dataset):
    parts, map_path = dataset
    run(str(parts), map_path, apply_changes=True)

    # GMD cleared where the map no longer carries it, PHP added where it now does.
    assert _tickers(parts) == [None, "PHP"]


def test_apply_is_idempotent(dataset):
    parts, map_path = dataset
    run(str(parts), map_path, apply_changes=True)

    assert run(str(parts), map_path, apply_changes=False) == {}


def test_raw_columns_are_never_touched(dataset):
    parts, map_path = dataset
    before = pd.read_parquet(parts / "ship_plan_2026-08.parquet")
    run(str(parts), map_path, apply_changes=True)
    after = pd.read_parquet(parts / "ship_plan_2026-08.parquet")

    for col in ("from_raw", "to_raw", "vessel_name", "row_key", "plan_date"):
        assert list(after[col]) == list(before[col])


def test_no_partitions_is_an_error(tmp_path):
    empty = tmp_path / "parts"
    empty.mkdir()
    map_path = _write_map(tmp_path / "berth_map.csv", ["HTIT,HTIT,PHP,True,berth,lach_huyen\n"])

    with pytest.raises(SystemExit):
        run(str(empty), map_path, apply_changes=False)


HCM_MAP = ("raw_name,berth,cluster,ticker,type\n"
           "CANG A,Ben A,CMIT,,berth\n"
           "CANG B,Ben B,Gemalink,GMD,berth\n")


def test_hcm_dataset_remaps_the_cluster_column(tmp_path):
    import pandas as pd

    from scraper.hcm.store import SCHEMA_COLUMNS as HCM_COLUMNS

    parts = tmp_path / "parts"
    parts.mkdir()
    df = pd.DataFrame([
        {"plan_date": date(2026, 8, 1), "section": "tau_vao",
         "from_position": "CANG A", "to_position": "CANG B",
         "from_cluster": "Cai Mep", "to_cluster": "Cai Mep",
         "row_key": "k1", "crawled_at": datetime(2026, 8, 1, 7, 0)},
    ])
    for col in HCM_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df[HCM_COLUMNS].to_parquet(parts / "ship_plan_2026-08.parquet", index=False)

    map_path = tmp_path / "hcm_map.csv"
    map_path.write_text(HCM_MAP, encoding="utf-8")

    counts = run(str(parts), str(map_path), apply_changes=True, dataset="hcm")

    out = pd.read_parquet(parts / "ship_plan_2026-08.parquet")
    assert counts["to_cluster"] == 1
    assert out["from_cluster"][0] == "CMIT" and out["to_cluster"][0] == "Gemalink"
    # Cột riêng của Hải Phòng không được đụng tới ở dataset này.
    assert "to_zone" not in out.columns
