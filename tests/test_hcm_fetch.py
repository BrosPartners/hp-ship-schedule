import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from scraper.hcm import fetch
from scraper.hcm.fetch import fetch_day
from scraper.hcm.parse import DateMismatchError

FIXTURES = Path(__file__).parent / "fixtures" / "hcm"


def _fixture_html(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as fh:
        return fh.read()


TODAY_HTML = _fixture_html("2026-08-14.html.gz")
OTHER_DAY_HTML = _fixture_html("2025-07-01.html.gz")

GET_FORM_HTML = """
<html><body>
<form>
<input type="hidden" name="__VIEWSTATE" value="VS" />
<input type="hidden" name="__EVENTVALIDATION" value="EV" />
<input type="text" name="ctl22$txtDate" value="14/08/2026" />
<input type="text" name="ctl22$txtDate$dateInput" value="14/08/2026" />
<input type="hidden" name="ctl22_txtDate_dateInput_ClientState" value="" />
<input type="checkbox" name="unchecked_box" value="x" />
<input type="checkbox" name="checked_box" value="y" checked="checked" />
</form>
</body></html>
"""


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
    monkeypatch.setattr(fetch.time, "sleep", lambda *_a, **_k: None)


def test_fetch_day_does_get_then_post_and_verifies_date(monkeypatch, tmp_path):
    calls = []

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls.append(("GET", url))
            return _FakeResponse(GET_FORM_HTML)

        def post(self, url, data=None, headers=None, timeout=None):
            calls.append(("POST", url, data))
            return _FakeResponse(TODAY_HTML)

    monkeypatch.setattr(fetch.requests, "Session", lambda: FakeSession())

    html = fetch_day(date(2026, 8, 14), cache_dir=tmp_path)

    assert html == TODAY_HTML
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    posted = calls[1][2]

    # All harvested fields must be present, plus the postback overrides.
    assert posted["__VIEWSTATE"] == "VS"
    assert posted["__EVENTVALIDATION"] == "EV"
    assert posted["checked_box"] == "y"
    assert "unchecked_box" not in posted
    assert posted["__EVENTTARGET"] == "ctl22$txtDate"
    assert posted["__EVENTARGUMENT"] == ""
    assert posted["ctl22$txtDate"] == "14/08/2026"
    assert posted["ctl22$txtDate$dateInput"] == "14/08/2026"

    client_state = json.loads(posted["ctl22_txtDate_dateInput_ClientState"])
    assert client_state["minDateStr"] == "1980-01-01-00-00-00"
    assert client_state["maxDateStr"] == "2099-12-31-00-00-00"
    assert client_state["valueAsString"] == "2026-08-14-00-00-00"


def test_fetch_day_raises_on_date_mismatch(monkeypatch, tmp_path):
    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            return _FakeResponse(GET_FORM_HTML)

        def post(self, url, data=None, headers=None, timeout=None):
            # Server silently returned some other day's page (HTTP 200).
            return _FakeResponse(OTHER_DAY_HTML)

    monkeypatch.setattr(fetch.requests, "Session", lambda: FakeSession())

    with pytest.raises(DateMismatchError):
        fetch_day(date(2026, 8, 14), cache_dir=tmp_path)


def test_fetch_day_writes_and_reuses_cache(monkeypatch, tmp_path):
    calls = []

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls.append("GET")
            return _FakeResponse(GET_FORM_HTML)

        def post(self, url, data=None, headers=None, timeout=None):
            calls.append("POST")
            return _FakeResponse(TODAY_HTML)

    monkeypatch.setattr(fetch.requests, "Session", lambda: FakeSession())

    html1 = fetch_day(date(2026, 8, 14), cache_dir=tmp_path)
    html2 = fetch_day(date(2026, 8, 14), cache_dir=tmp_path)

    assert html1 == html2 == TODAY_HTML
    assert calls == ["GET", "POST"]  # second call served from cache

    cache_file = tmp_path / "2026-08-14.html.gz"
    assert cache_file.exists()
    with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
        assert fh.read() == TODAY_HTML


def test_fetch_day_refetches_when_cache_date_is_wrong(monkeypatch, tmp_path):
    # Poison the cache file directly with a different day's HTML under the
    # wrong filename - the exact 79-day incident this guard exists for.
    cache_file = tmp_path / "2026-08-14.html.gz"
    with gzip.open(cache_file, "wt", encoding="utf-8") as fh:
        fh.write(OTHER_DAY_HTML)

    calls = []

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls.append("GET")
            return _FakeResponse(GET_FORM_HTML)

        def post(self, url, data=None, headers=None, timeout=None):
            calls.append("POST")
            return _FakeResponse(TODAY_HTML)

    monkeypatch.setattr(fetch.requests, "Session", lambda: FakeSession())

    html = fetch_day(date(2026, 8, 14), cache_dir=tmp_path)

    assert html == TODAY_HTML
    assert calls == ["GET", "POST"]  # cache miss -> live refetch happened


def test_fetch_day_force_bypasses_cache(monkeypatch, tmp_path):
    calls = []

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls.append("GET")
            return _FakeResponse(GET_FORM_HTML)

        def post(self, url, data=None, headers=None, timeout=None):
            calls.append("POST")
            return _FakeResponse(TODAY_HTML)

    monkeypatch.setattr(fetch.requests, "Session", lambda: FakeSession())

    fetch_day(date(2026, 8, 14), cache_dir=tmp_path)
    fetch_day(date(2026, 8, 14), cache_dir=tmp_path, force=True)

    assert calls == ["GET", "POST", "GET", "POST"]
