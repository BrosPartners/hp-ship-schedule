import gzip
from datetime import date
from pathlib import Path

import pytest

from scraper import fetch
from scraper.fetch import offset_for, fetch_day


def test_offset_for_is_relative_to_today():
    today = date(2026, 8, 12)
    assert offset_for(date(2026, 8, 12), today) == 0
    assert offset_for(date(2026, 8, 13), today) == 1
    assert offset_for(date(2026, 8, 11), today) == -1
    # Verified against the live site on 2026-08-12: d=-1320 -> 31/12/2022
    assert offset_for(date(2022, 12, 31), today) == -1320
    # Verified: d=-2000 -> 19/02/2021
    assert offset_for(date(2021, 2, 19), today) == -2000


VALID_HTML = "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 12/08/2026</body></html>"
INVALID_HTML = "<html><body>Access Denied - please enable JavaScript</body></html>"


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.apparent_encoding = "utf-8"
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr("scraper.fetch.time.sleep", lambda *_a, **_k: None)


@pytest.fixture(autouse=True)
def _primed_calibration(monkeypatch):
    # Pre-seed the memoized server-day so ordinary tests (which don't care
    # about calibration) see the same call counts they did before
    # calibration existed. Tests that specifically exercise calibration call
    # fetch.reset_server_today_cache() to clear this and take over.
    monkeypatch.setattr(fetch, "_server_today_cache", date(2026, 8, 12))


def test_fetch_day_writes_cache_and_returns_html(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
    assert len(calls) == 1
    cache_file = tmp_path / "2026-08-12.html.gz"
    assert cache_file.exists()
    with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
        assert fh.read() == VALID_HTML


def test_fetch_day_second_call_uses_cache_not_network(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    fetch_day(date(2026, 8, 12), cache_dir=tmp_path)
    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
    assert len(calls) == 1


def test_fetch_day_force_bypasses_cache(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    fetch_day(date(2026, 8, 12), cache_dir=tmp_path)
    fetch_day(date(2026, 8, 12), cache_dir=tmp_path, force=True)

    assert len(calls) == 2


def test_fetch_day_missing_date_header_raises_and_leaves_no_cache(monkeypatch, tmp_path):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(INVALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    with pytest.raises(Exception) as excinfo:
        fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    message = str(excinfo.value)
    assert "http" in message.lower() or "csdltau" in message.lower()
    assert INVALID_HTML[:50] in message

    cache_file = tmp_path / "2026-08-12.html.gz"
    assert not cache_file.exists()


def test_fetch_day_refetches_when_cache_content_is_invalid(monkeypatch, tmp_path):
    cache_file = tmp_path / "2026-08-12.html.gz"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_file, "wt", encoding="utf-8") as fh:
        fh.write(INVALID_HTML)

    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
    assert len(calls) == 1
    with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
        assert fh.read() == VALID_HTML


def test_fetch_day_retries_transient_failure_then_succeeds(monkeypatch, tmp_path):
    attempts = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise Exception("connection reset")
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
    assert attempts["n"] == 3


def test_fetch_day_persistent_failure_raises_after_exhausting_attempts(monkeypatch, tmp_path):
    attempts = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        attempts["n"] += 1
        raise Exception("connection reset")

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    with pytest.raises(RuntimeError):
        fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert attempts["n"] == 4
    cache_file = tmp_path / "2026-08-12.html.gz"
    assert not cache_file.exists()


SERVER_TODAY_HTML = (
    "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 20/08/2026</body></html>"
)


def test_fetch_day_computes_offset_from_server_day_not_local_clock(monkeypatch, tmp_path):
    fetch.reset_server_today_cache()

    calls = []

    TARGET_HTML = (
        "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 21/08/2026</body></html>"
    )

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("d=0"):
            return _FakeResponse(SERVER_TODAY_HTML)
        return _FakeResponse(TARGET_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    # Server day is stubbed as 2026-08-20 (deliberately not "today" on the
    # local machine). If offset_for were still computed against
    # date.today(), the request would carry a different, wrong offset.
    fetch_day(date(2026, 8, 21), cache_dir=tmp_path)

    calibration_calls = [c for c in calls if c.endswith("d=0")]
    target_calls = [c for c in calls if c.endswith("d=1")]
    assert len(calibration_calls) == 1
    assert len(target_calls) == 1


def test_calibration_happens_once_across_multiple_fetch_day_calls(monkeypatch, tmp_path):
    fetch.reset_server_today_cache()

    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("d=0"):
            return _FakeResponse(SERVER_TODAY_HTML)
        if url.endswith("d=-10"):
            return _FakeResponse(
                "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 10/08/2026</body></html>"
            )
        return _FakeResponse(
            "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 11/08/2026</body></html>"
        )

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    fetch_day(date(2026, 8, 10), cache_dir=tmp_path)
    fetch_day(date(2026, 8, 11), cache_dir=tmp_path)

    calibration_calls = [c for c in calls if c.endswith("d=0")]
    assert len(calibration_calls) == 1
    assert len(calls) == 3  # 1 calibration + 2 live fetches


WRONG_DAY_HTML = "<html><body>KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY 11/08/2026</body></html>"


def test_fetch_day_self_heals_poisoned_cache_with_wrong_day_header(monkeypatch, tmp_path):
    """Regression test for the 79-day cache-poisoning defect: a cache file
    whose header date doesn't match the requested day (e.g. saved under
    2026-08-12.html.gz but its header says 11/08/2026, from the midnight-
    lag bug) must be treated as a cache miss, refetched live, and the cache
    file corrected in place - not permanently rejected by parse_page's
    DateMismatchError on every subsequent run."""
    cache_file = tmp_path / "2026-08-12.html.gz"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_file, "wt", encoding="utf-8") as fh:
        fh.write(WRONG_DAY_HTML)

    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse(VALID_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
    assert len(calls) == 1
    with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
        assert fh.read() == VALID_HTML


def test_fetch_day_live_response_with_wrong_day_header_raises_and_not_cached(monkeypatch, tmp_path):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(WRONG_DAY_HTML)

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    with pytest.raises(Exception) as excinfo:
        fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    message = str(excinfo.value)
    assert "2026-08-12" in message
    assert "2026-08-11" in message

    cache_file = tmp_path / "2026-08-12.html.gz"
    assert not cache_file.exists()


def test_fetch_day_cache_hit_makes_no_http_request_calibration_included(monkeypatch, tmp_path):
    fetch.reset_server_today_cache()

    cache_file = tmp_path / "2026-08-12.html.gz"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_file, "wt", encoding="utf-8") as fh:
        fh.write(VALID_HTML)

    def fake_get(url, headers=None, timeout=None):
        raise AssertionError("cache hit must not make any HTTP request")

    monkeypatch.setattr("scraper.fetch.requests.get", fake_get)

    html = fetch_day(date(2026, 8, 12), cache_dir=tmp_path)

    assert html == VALID_HTML
