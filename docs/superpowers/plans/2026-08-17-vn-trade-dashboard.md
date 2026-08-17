# Vietnam Trade Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-updating national Vietnam export/import dashboard from official Customs monthly reports, with industry and partner breakdowns from January 2023.

**Architecture:** A `scraper.trade` package discovers, fetches and parses official Customs PDF reports into revisioned monthly records. A build step validates and aggregates those records into small JSON files under `data/trade/`, which a lazy-loaded ECharts module renders as a top-level dashboard tab.

**Tech Stack:** Python 3.13, requests, pdfplumber, pandas, pytest, ECharts, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-08-17-vn-trade-dashboard-design.md`

## Global Constraints

- Use only Customs official reports at `customs.gov.vn` or `files.customs.gov.vn`; retain source URL, publish/download time and SHA-256.
- Start at `2023-01`; store USD and render billion USD by default.
- Build monthly flows from end-of-month cumulative values; January equals its cumulative value.
- Publish missing/incomplete data as missing, never zero; never infer from press articles or growth rates.
- Industry groups and partner groups are CSV mappings; no silent fuzzy mapping.
- A trade failure must not block port crawls or replace the last known-good trade aggregates.
- Commit only compact metadata and derived data; do not serve source PDFs or Excel files from Pages.

---

### Task 1: Domain models and explicit mappings

**Files:**
- Create: `scraper/trade/__init__.py`, `scraper/trade/models.py`, `scraper/trade/normalize.py`
- Create: `data/trade/commodity_map.csv`, `data/trade/partner_map.csv`
- Test: `tests/test_trade_normalize.py`

**Interfaces:** Produces immutable `TradeRecord(month, direction, dimension, source_label, value_usd, cumulative_value_usd, source_url, published_at, downloaded_at, source_sha256, revision_id)`; `parse_usd(text) -> float`, `month_end_from_label(text) -> str`, `bucket_commodity(label, direction, mapping) -> str`, and `bucket_partner(label, mapping) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_usd_and_period():
    assert parse_usd("24.209.559.419") == 24209559419.0
    assert parse_usd("1,234.50") == 1234.50
    assert month_end_from_label("Kỳ 2 tháng 06 năm 2026") == "2026-06"

def test_mapping_is_explicit_and_falls_to_other(mapping):
    assert bucket_commodity("Máy vi tính, sản phẩm điện tử và linh kiện", "export", mapping) == "Hàng điện tử"
    assert bucket_commodity("Nhãn chưa map", "export", mapping) == "Khác"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_trade_normalize.py -v`

Expected: FAIL because `scraper.trade` does not exist.

- [ ] **Step 3: Implement the model, parsers and mappings**

Use a frozen dataclass and reject invalid month, direction, dimension and non-finite values with `ValueError`. `monthly_from_cumulative(current, previous)` returns `current` for January and `current - previous` otherwise.

Seed exact official labels for electronics, textile/footwear, agriculture, wood, oil, the ten ASEAN countries and all 27 EU countries. CSV headers are `direction,source_label,bucket` and `source_label,bucket`. Normalise case and whitespace only; any unmatched value is `Khác`.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_normalize.py -v`

Expected: PASS.

```bash
git add scraper/trade data/trade/commodity_map.csv data/trade/partner_map.csv tests/test_trade_normalize.py
git commit -m "Add trade domain normalization and mappings"
```

### Task 2: Discover and retrieve official PDF reports safely

**Files:**
- Create: `scraper/trade/discover.py`, `scraper/trade/fetch.py`
- Test: `tests/test_trade_fetch.py`

**Interfaces:** `discover_sources(index_html, base_url) -> list[TradeSource]`; `fetch_pdf(source, cache_dir, session) -> DownloadedReport`. `DownloadedReport` contains path, SHA-256, download time and original `TradeSource`.

- [ ] **Step 1: Write failing tests**

```python
def test_discover_keeps_only_official_pdf_reports():
    found = discover_sources(HTML_WITH_K1_K2_AND_NEWS, "https://www.customs.gov.vn")
    assert [(x.report_kind, x.period_hint) for x in found] == [("export", "2026-06"), ("import", "2026-06")]

def test_fetch_rejects_html_error_page(tmp_path, fake_session):
    fake_session.get.return_value.headers = {"Content-Type": "text/html"}
    with pytest.raises(InvalidReportError):
        fetch_pdf(SOURCE, tmp_path, fake_session)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_trade_fetch.py -v`

Expected: FAIL because discovery and fetch functions are absent.

- [ ] **Step 3: Implement fail-closed discovery and retrieval**

Accept only HTTPS PDF URLs on the two official hosts, whose text identifies export/import and a period; deduplicate canonical URLs and never construct missing K2 filenames. Retry network/5xx failures three times. Require both a PDF content type and `%PDF` bytes, calculate SHA-256 and atomically cache only valid PDFs. Invalid pages must not enter cache.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_fetch.py -v`

Expected: PASS.

```bash
git add scraper/trade/discover.py scraper/trade/fetch.py tests/test_trade_fetch.py
git commit -m "Add official Customs report discovery"
```

### Task 3: Parse official tables

**Files:**
- Modify: `requirements.txt`
- Create: `scraper/trade/parse.py`
- Create: `tests/fixtures/trade/export_report_text.txt`, `tests/fixtures/trade/import_report_text.txt`, `tests/fixtures/trade/partner_report_text.txt`
- Test: `tests/test_trade_parse.py`

**Interfaces:** `parse_report(report: DownloadedReport) -> list[TradeRecord]`; raises `MissingTradeTableError` for missing total/table and `AmbiguousTradeTableError` for incompatible duplicate tables.

- [ ] **Step 1: Write the failing parser tests**

```python
def test_parse_export_total_and_commodity_rows(report_from_fixture):
    rows = parse_report(report_from_fixture("export_report_text.txt"))
    total = next(x for x in rows if x.dimension == "total")
    assert (total.month, total.direction, total.cumulative_value_usd) == ("2026-06", "export", 239926293189.0)
    assert any(x.source_label == "Hàng dệt, may" for x in rows)

def test_parse_rejects_report_without_total(report_from_fixture):
    with pytest.raises(MissingTradeTableError):
        parse_report(report_from_fixture("partner_report_text.txt", remove_total=True))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_parse.py -v`

Expected: FAIL because parser is missing.

- [ ] **Step 3: Implement table extraction**

Add `pdfplumber==0.11.7`. Extract page text, identify report period/direction, and parse rows only when a recognised label and cumulative value are present. Keep labels verbatim. Include a monkeypatched `pdfplumber.open` test proving the PDF page path goes through the same text parser. Ignore subordinate rows prefixed `- ` when their parent is emitted, preventing double counting.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_parse.py -v`

Expected: PASS.

```bash
git add requirements.txt scraper/trade/parse.py tests/fixtures/trade tests/test_trade_parse.py
git commit -m "Parse Customs trade report tables"
```

### Task 4: Revisioned storage, reconciliation and aggregate build

**Files:**
- Create: `scraper/trade/store.py`, `scraper/trade/build.py`
- Test: `tests/test_trade_store.py`, `tests/test_trade_build.py`

**Interfaces:** `upsert_records(records, root) -> Path`, `latest_records(root) -> list[TradeRecord]`, and `build_all(root) -> dict[str, Path]`. Writes `raw/trade_records.jsonl`, `agg/summary.json`, `agg/commodity.json`, `agg/partner.json`, and `manifest.json` below `data/trade/`.

- [ ] **Step 1: Write failing revision and completeness tests**

```python
def test_latest_revision_wins_without_losing_history(tmp_path):
    upsert_records([record(revision_id="a", cumulative_value_usd=100)], tmp_path)
    upsert_records([record(revision_id="b", cumulative_value_usd=105)], tmp_path)
    assert latest_records(tmp_path)[0].cumulative_value_usd == 105

def test_partner_gap_is_incomplete_not_invented(tmp_path):
    write_records(tmp_path, records_with_partner_gap())
    assert build_all(tmp_path)["partner"]["coverage"]["2026-06|export"] == "incomplete"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_store.py tests/test_trade_build.py -v`

Expected: FAIL because store/build modules are missing.

- [ ] **Step 3: Implement records and payloads**

Raw identity is `(month, direction, dimension, source_label, source_sha256)`; retain all source versions and choose newest `downloaded_at` for latest calculations. All rewrites use temp file plus `os.replace`.

Calculate flows before mapping. Commodity sum may not exceed total by more than USD 1. A partner period is `complete` only if its sum differs from total by at most USD 1,000 (official rounding); otherwise preserve values but label it `incomplete`. Emit source links at both row and month level.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_store.py tests/test_trade_build.py -v`

Expected: PASS.

```bash
git add scraper/trade/store.py scraper/trade/build.py tests/test_trade_store.py tests/test_trade_build.py
git commit -m "Build revisioned Vietnam trade aggregates"
```

### Task 5: Backfill and independent daily update

**Files:**
- Create: `scraper/trade/backfill.py`, `scraper/trade/daily.py`
- Create: `data/trade/manifest.json`
- Test: `tests/test_trade_daily.py`

**Interfaces:** `backfill.run(start, end, root) -> dict`, `daily.run(root) -> dict`; runnable as `python -m scraper.trade.backfill --start 2023-01 --end 2026-08` and `python -m scraper.trade.daily`.

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_daily_keeps_last_good_aggregate_when_new_source_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(daily, "discover_sources", lambda: [BROKEN_SOURCE])
    result = daily.run(tmp_path)
    assert result["updated_months"] == []
    assert result["errors"] == [BROKEN_SOURCE.url]
    assert (tmp_path / "agg" / "summary.json").exists()

def test_backfill_reports_every_requested_month(tmp_path):
    result = backfill.run("2023-01", "2023-03", tmp_path)
    assert result["months_requested"] == ["2023-01", "2023-02", "2023-03"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_daily.py -v`

Expected: FAIL because command modules are absent.

- [ ] **Step 3: Implement idempotent orchestration**

Backfill uses only reports whose parsed month exactly matches the requested month and checks both directions. Build once after successful records. Manifest records `available_months`, `incomplete_months`, `failed_sources`, `last_checked_at`, `last_success_at`. Daily checks newest plus prior two months for late posts/revisions. Errors retain existing aggregates and return a structured error report.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_daily.py -v`

Expected: PASS.

```bash
git add scraper/trade/backfill.py scraper/trade/daily.py data/trade/manifest.json tests/test_trade_daily.py
git commit -m "Add Vietnam trade monthly update pipeline"
```

### Task 6: Official backfill and audited reconciliation

**Files:**
- Create: `tools/trade_reconcile.py`
- Test: `tests/test_trade_reconcile.py`
- Modify: `data/trade/raw/trade_records.jsonl`, `data/trade/agg/*.json`, `data/trade/manifest.json`

**Interfaces:** `python -m tools.trade_reconcile --root data/trade` prints JSON plus table and exits non-zero if published total/commodity values violate reconciliation.

- [ ] **Step 1: Write a failing reconcile test**

```python
def test_reconcile_flags_commodity_sum_above_total(tmp_path):
    write_aggregates(tmp_path, total=100, commodity_sum=101)
    assert reconcile(tmp_path)["2026-06|export"]["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_reconcile.py -v`

Expected: FAIL because reconciliation tool is absent.

- [ ] **Step 3: Implement reconciliation and run backfill**

For each month/direction report total, commodity sum, partner sum, coverage, source URL and status. Backfill 2023-01 through newest official month. Spot-check January, June and December of every year against source PDF for total and one mapped label. Add new official labels to an explicit mapping or leave them `Khác`.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest -q`

Expected: PASS with no skipped trade tests.

Run: `python -m tools.trade_reconcile --root data/trade`

Expected: every summary/commodity period is `ok`; partner periods are `ok` or clearly `incomplete`.

```bash
git add data/trade tools/trade_reconcile.py tests/test_trade_reconcile.py
git commit -m "Backfill Vietnam Customs trade data"
```

### Task 7: Top-level dashboard tab and five charts

**Files:**
- Modify: `web/index.html`, `web/app.css`
- Create: `web/js/trade.js`
- Test: `tests/test_trade_frontend.py`

**Interfaces:** `initTrade(root: HTMLElement): Promise<void>` consumes all three aggregate JSON files. `PORTS.trade` uses only `["trade"]`, and its state shows neither port subtab bar.

- [ ] **Step 1: Write failing DOM/data-contract tests**

```python
def test_trade_is_a_lazy_top_level_tab(index_html):
    assert 'data-port="trade"' in index_html
    assert 'initTrade(root)' in index_html

def test_trade_keeps_missing_months_null(trade_js):
    assert "null" in trade_js
    assert "chưa có dữ liệu" in trade_js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_frontend.py -v`

Expected: FAIL because the trade UI is absent.

- [ ] **Step 3: Implement navigation and interaction**

Add a `Xuất nhập khẩu VN` top-level button and `tab-trade`. Extend `PORTS` with title `Xuất nhập khẩu Việt Nam`, tabs `["trade"]`, initial `"trade"`; lazy-load `trade.js`; hide both port subtab bars.

Render: total XK/NK line chart with value/YoY toggle; separate export/import commodity stacked columns; separate export/import partner stacked columns. Use common date range and checkbox selectors. Hide all only unchecks boxes; every individual box remains re-selectable. Tooltip has USD value, share, YoY and source URL. Missing values stay `null`; incomplete partner months display an explicit warning.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_trade_frontend.py -v`

Expected: PASS.

Serve the Pages publish tree, mount all five ECharts instances, change date range, press Hide all then re-enable one bucket, and verify browser console is clean.

```bash
git add web/index.html web/js/trade.js web/app.css tests/test_trade_frontend.py
git commit -m "Add Vietnam trade dashboard tab"
```

### Task 8: Automate, deploy and perform final verification

**Files:**
- Modify: `.github/workflows/daily.yml`, `.github/workflows/pages.yml`, `README.md`
- Modify: `tests/test_trade_daily.py`

**Interfaces:** runs `python -m scraper.trade.daily` as a separate outcome. Pages receives `data/trade/agg/` but not `data/trade/raw/` or the PDF cache.

- [ ] **Step 1: Write the failing workflow-contract test**

```python
def test_daily_workflow_does_not_make_port_crawls_depend_on_trade(workflow_text):
    assert "Run Vietnam trade update" in workflow_text
    assert "continue-on-error: true" in workflow_text
    assert "python -m scraper.trade.daily" in workflow_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_daily.py -v`

Expected: FAIL because the workflow step is absent.

- [ ] **Step 3: Wire and document**

Add the trade command after port crawls with `if: always()` and `continue-on-error: true`; retain the existing HP/HCM failure gate. Commit `data/trade/` but exclude raw/PDF paths from the Pages artifact. Document source, monthly publication lag, `Khác`, revisions and incomplete partner data in README.

- [ ] **Step 4: Final verification, commit and deploy**

Run: `python -m pytest -q`

Expected: PASS with no skipped trade tests.

Run: `python -m scraper.trade.daily`

Expected: idempotent success or a validated update; a source failure leaves the existing aggregate unchanged.

Run `git diff --check`, repeat the five-chart browser smoke test, then:

```bash
git add .github/workflows/daily.yml .github/workflows/pages.yml README.md tests/test_trade_daily.py
git commit -m "Automate Vietnam trade dashboard updates"
git push origin master
```

Verify the Pages action is green and `https://brospartners.github.io/hp-ship-schedule/` serves all five charts.

## Plan self-review

- **Spec coverage:** Tasks 1–2 cover official provenance; 3–6 cover parsing, monthly conversion, mapping, revisions, backfill and quality gates; 7 covers the top-level tab and five charts; 8 covers isolated automation, deployment and documentation.
- **No silent assumptions:** unmatched labels map to `Khác`, incomplete partner data stays incomplete, invalid reports fail closed, and missing months remain missing.
- **Interface consistency:** every later task uses `TradeRecord`, `DownloadedReport`, `build_all` and the `data/trade/agg/` paths introduced in an earlier task.
