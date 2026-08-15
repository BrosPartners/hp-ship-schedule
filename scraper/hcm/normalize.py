"""Turn raw HCM scraped rows (from `scraper.hcm.parse.parse_page`) into typed
records.

Reuses `scraper.normalize.parse_vn_number` for Vietnamese-formatted numbers
(dot = thousands separator, comma = decimal) rather than writing a second
parser — see that module's docstring for the exact rules.

HCM has no GT column (unlike Hai Phong) but does have `Loai hang hoa`
(cargo type) and `Ho hieu` (call sign), which identifies a vessel more
reliably than its name. `Quoc tich` (nationality) is also new.

Arrivals/departures carry a single berth position ("Vi tri neo dau");
movements carry a "Tu"/"Den" pair. Both are normalized here into a single
`from_position`/`to_position` pair per record so downstream code (storage,
aggregation, dashboard) never has to special-case which section a row came
from. Likewise, arrivals have two time columns (expected arrival at berth,
time leaving berth), departures have one (expected departure from Saigon),
movements have one (time of the move) - normalized into `eta`/`etd`.
"""

import hashlib
import re
from datetime import datetime

from scraper.normalize import parse_vn_number

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

SECTIONS = ("tau_vao", "tau_roi", "tau_di_chuyen")


def _to_int(raw):
    value = parse_vn_number(raw)
    return None if value is None else int(round(value))


def _clean(raw):
    value = (raw or "").strip()
    return value or None


def _plan_time(plan_date, raw):
    match = _TIME_RE.match((raw or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return datetime(plan_date.year, plan_date.month, plan_date.day, hour, minute)


def _from_to(row):
    """Normalize each section's berth-position column(s) into (from, to)."""
    section = row["section"]
    if section == "tau_vao":
        # Arriving at a single position; nothing to record as "from".
        return None, _clean(row.get("vi_tri_neo_dau"))
    if section == "tau_roi":
        # Departing from a single position; nothing to record as "to".
        return _clean(row.get("vi_tri_neo_dau")), None
    if section == "tau_di_chuyen":
        return (
            _clean(row.get("vi_tri_neo_dau_tu")),
            _clean(row.get("vi_tri_neo_dau_den")),
        )
    raise ValueError(f"unknown section {section!r}; refusing to guess from/to")


def _eta_etd(row, plan_date):
    """Normalize each section's time column(s) into (eta, etd).

    eta = expected arrival at a berth position (only arrivals have this).
    etd = expected departure/movement time (all three sections have one,
    under different column names: thoi_gian_roi_vt / du_kien_roi_sg / gio_doi).
    """
    section = row["section"]
    if section == "tau_vao":
        eta = _plan_time(plan_date, row.get("du_kien_den_vt"))
        etd = _plan_time(plan_date, row.get("thoi_gian_roi_vt"))
    elif section == "tau_roi":
        eta = None
        etd = _plan_time(plan_date, row.get("du_kien_roi_sg"))
    elif section == "tau_di_chuyen":
        eta = None
        etd = _plan_time(plan_date, row.get("gio_doi"))
    else:
        raise ValueError(f"unknown section {section!r}; refusing to guess eta/etd")
    return eta, etd


def _row_key(rec):
    """Identity of a movement, independent of when it was crawled.

    Uses call_sign in preference to vessel_name where available - the source
    itself notes call sign (Ho hieu / IMO-style identifier) is a far more
    reliable vessel identifier than the free-text name field, which can be
    mistyped or vary crawl to crawl. crawled_at is deliberately excluded so
    the same movement crawled on two different days yields the same key,
    which is what makes snapshot versioning (scraper.store upsert semantics)
    work.
    """
    parts = [
        rec["plan_date"].isoformat(),
        rec["section"],
        rec["call_sign"] or rec["vessel_name"] or "",
        rec["eta"].isoformat() if rec["eta"] else "",
        rec["etd"].isoformat() if rec["etd"] else "",
        rec["from_position"] or "",
        rec["to_position"] or "",
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def build_records(raw_rows, crawled_at):
    """Convert raw string rows from `parse_page` into typed records.

    `crawled_at` must be a single value stamped once per run (not per row):
    `scraper.store.latest_snapshot` compares crawled_at for exact equality
    to pick the newest snapshot per plan_date, so per-row timestamps would
    make every row look like its own snapshot and silently drop siblings.
    """
    records = []
    for row in raw_rows:
        plan_date = row["plan_date"]
        from_position, to_position = _from_to(row)
        eta, etd = _eta_etd(row, plan_date)
        rec = {
            "plan_date": plan_date,
            "section": row["section"],
            "vessel_name": _clean(row.get("ten_tau")),
            "nationality": _clean(row.get("quoc_tich")),
            "call_sign": _clean(row.get("ho_hieu")),
            "dwt": _to_int(row.get("dwt")),
            "loa_m": parse_vn_number(row.get("chieu_dai")),
            "draft_m": parse_vn_number(row.get("mon_nuoc")),
            "cargo_type": _clean(row.get("loai_hang_hoa")),
            "from_position": from_position,
            "to_position": to_position,
            "eta": eta,
            "etd": etd,
            "tugs": _clean(row.get("tau_lai")),
            "agent": _clean(row.get("dai_ly")),
            "channel": _clean(row.get("tuyen_luong")),
            "crawled_at": crawled_at,
        }
        rec["row_key"] = _row_key(rec)
        records.append(rec)
    return records
