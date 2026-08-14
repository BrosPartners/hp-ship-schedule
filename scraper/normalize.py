"""Turn raw scraped strings into typed values."""

import hashlib
import re
from datetime import datetime


def parse_vn_number(raw):
    """Parse a Vietnamese-formatted number.

    Applies dot-interpretation rules in order:
    1. If comma is present: comma is the decimal separator (e.g., '1.234,5' → 1234.5)
    2. If dots form valid thousands grouping (1–3 digits, then .XXX groups):
       strip dots (e.g., '1.234.567' → 1234567)
    3. If single dot with 1–2 digits after: treat as decimal (e.g., '10.5' → 10.5)
    4. Otherwise: attempt float(), returning None on failure

    Returns None for blank/unparseable input.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Rule 1: If comma present, it's the decimal separator
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    # Rule 2: Check if dots form valid thousands grouping
    # Pattern: 1-3 digits, followed by one or more groups of (.XXX)
    if re.match(r"^\d{1,3}(\.\d{3})+$", s):
        # Valid thousands grouping, strip all dots
        s = s.replace(".", "")
        try:
            return float(s)
        except ValueError:
            return None

    # Rule 3: Single dot with 1-2 digits after (treat as decimal)
    if re.match(r"^\d+\.\d{1,2}$", s):
        try:
            return float(s)
        except ValueError:
            return None

    # Rule 4: Fall through to plain float() attempt
    try:
        return float(s)
    except ValueError:
        return None


_SB_RE = re.compile(r"\s*\(SB\)\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def split_sb(vessel_raw):
    """Split the '(SB)' suffix off a vessel name.

    '(SB)' marks a VR-SB river-sea vessel, which is a useful domestic-traffic
    proxy, so it is kept as a boolean rather than left inside the name.
    """
    name = (vessel_raw or "").strip()
    is_sb = bool(_SB_RE.search(name))
    return _SB_RE.sub("", name).strip(), is_sb


def _to_int(raw):
    value = parse_vn_number(raw)
    return None if value is None else int(round(value))


def _plan_time(plan_date, raw):
    match = _TIME_RE.match((raw or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return datetime(plan_date.year, plan_date.month, plan_date.day, hour, minute)


def _row_key(rec):
    """Identity of a movement, independent of when it was crawled."""
    parts = [
        rec["plan_date"].isoformat(),
        rec["section"],
        rec["vessel_name"],
        rec["plan_time"].isoformat() if rec["plan_time"] else "",
        rec["from_raw"] or "",
        rec["to_raw"] or "",
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def build_records(raw_rows, crawled_at):
    """Convert raw string rows from parse_page into typed records."""
    records = []
    for row in raw_rows:
        vessel_name, is_sb = split_sb(row.get("vessel"))
        rec = {
            "plan_date": row["plan_date"],
            "section": row["section"],
            "plan_time": _plan_time(row["plan_date"], row.get("time")),
            "vessel_name": vessel_name,
            "is_sb": is_sb,
            "draft_m": parse_vn_number(row.get("draft")),
            "loa_m": parse_vn_number(row.get("loa")),
            "dwt": _to_int(row.get("dwt")),
            "gt": _to_int(row.get("gt")),
            "tugs": (row.get("tugs") or None) or None,
            "channel_code": (row.get("channel") or None) or None,
            "from_raw": (row.get("from") or None) or None,
            "to_raw": (row.get("to") or None) or None,
            "agent": (row.get("agent") or None) or None,
            "pilot": (row.get("pilot") or None) or None,
            "crawled_at": crawled_at,
        }
        rec["row_key"] = _row_key(rec)
        records.append(rec)
    return records


import csv

_TRUE = {"true", "1", "yes", "y"}


def load_berth_map(path):
    """Load berth_map.csv keyed by uppercased raw name."""
    mapping = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            raw = (row["raw_name"] or "").strip().upper()
            if not raw:
                continue
            mapping[raw] = {
                "berth": (row["berth"] or "").strip() or None,
                "ticker": (row["ticker"] or "").strip() or None,
                "is_hai_phong": (row["is_hai_phong"] or "").strip().lower() in _TRUE,
                "type": (row["type"] or "").strip() or None,
                "zone": (row.get("zone") or "").strip() or None,
            }
    return mapping


def _lookup(berth_map, raw):
    if not raw:
        return None
    return berth_map.get(str(raw).strip().upper())


def apply_berth_map(records, berth_map):
    """Add normalized berth/ticker/type columns. Raw values are never altered."""
    out = []
    for rec in records:
        rec = dict(rec)
        src = _lookup(berth_map, rec.get("from_raw"))
        dst = _lookup(berth_map, rec.get("to_raw"))
        for side, hit in (("from", src), ("to", dst)):
            rec[f"{side}_berth"] = hit["berth"] if hit else None
            rec[f"{side}_ticker"] = hit["ticker"] if hit else None
            rec[f"{side}_type"] = hit["type"] if hit else None
            rec[f"{side}_zone"] = hit["zone"] if hit else None
        both_known = src is not None and dst is not None
        rec["is_domestic"] = bool(
            (both_known and src["type"] != "foreign" and dst["type"] != "foreign")
            or rec.get("is_sb")
        )
        out.append(rec)
    return out


def coverage(records):
    """Share of non-empty from/to slots that resolved to a mapped entry."""
    total = mapped = 0
    for rec in records:
        for side in ("from", "to"):
            if rec.get(f"{side}_raw"):
                total += 1
                if rec.get(f"{side}_berth"):
                    mapped += 1
    return 1.0 if total == 0 else mapped / total
