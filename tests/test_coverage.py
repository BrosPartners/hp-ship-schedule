import pytest

from scraper.coverage import apply_coverage, load_coverage

CSV = ("cluster,from_month,note\n"
       "CMIT,2025-08,khu Cái Mép\n"
       "Gemalink,2025-08,khu Cái Mép\n")


@pytest.fixture()
def coverage(tmp_path):
    path = tmp_path / "source_coverage.csv"
    path.write_text(CSV, encoding="utf-8")
    return load_coverage(path)


def test_a_missing_file_means_no_restriction(tmp_path):
    assert load_coverage(tmp_path / "khong-co.csv") == {}


def test_months_before_the_start_are_dropped(coverage):
    volume = {("2025-07", "CMIT"): (4, 10.0), ("2025-08", "CMIT"): (86, 20.0)}

    assert apply_coverage(volume, coverage) == {("2025-08", "CMIT"): (86, 20.0)}


def test_the_start_month_itself_is_kept(coverage):
    volume = {("2025-08", "Gemalink"): (57, 1.0)}

    assert apply_coverage(volume, coverage) == volume


def test_clusters_not_listed_keep_their_whole_history(coverage):
    volume = {("2023-01", "Cat Lai"): (300, 1.0)}

    assert apply_coverage(volume, coverage) == volume


def test_empty_coverage_changes_nothing(coverage):
    volume = {("2023-01", "CMIT"): (1, 1.0)}

    assert apply_coverage(volume, {}) == volume


ZONES_CSV = ("cluster,zone\n"
             "CMIT,cai_mep\n"
             "Cat Lai,song_sai_gon\n"
             "Khong co zone,\n")


def test_cluster_zones_skips_rows_without_a_zone(tmp_path):
    from scraper.coverage import load_cluster_zones

    path = tmp_path / "cluster_zones.csv"
    path.write_text(ZONES_CSV, encoding="utf-8")

    zones = load_cluster_zones(path)

    assert zones == {"CMIT": "cai_mep", "Cat Lai": "song_sai_gon"}


def test_cluster_zones_missing_file_is_empty(tmp_path):
    from scraper.coverage import load_cluster_zones

    assert load_cluster_zones(tmp_path / "khong-co.csv") == {}
