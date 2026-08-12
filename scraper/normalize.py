"""Turn raw scraped strings into typed values."""


def parse_vn_number(raw):
    """Parse a Vietnamese-formatted number.

    '.' is the thousands separator and ',' is the decimal separator, which is
    the opposite of Python's default. Returns None for blank/unparseable input.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
