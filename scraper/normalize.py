"""Turn raw scraped strings into typed values."""

import re


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
