import pytest
from scraper.normalize import parse_vn_number


@pytest.mark.parametrize("raw,expected", [
    ("4.450", 4450.0),      # dot = thousands separator
    ("151.966", 151966.0),
    ("2,7", 2.7),           # comma = decimal separator
    ("79,9", 79.9),
    ("3", 3.0),
    ("1.234,5", 1234.5),    # both separators at once
    ("", None),
    ("   ", None),
    (None, None),
    ("n/a", None),
])
def test_parse_vn_number(raw, expected):
    assert parse_vn_number(raw) == expected


def test_thousands_separator_is_not_treated_as_decimal():
    """Regression guard: float('4.450') == 4.45 would understate DWT 1000x."""
    assert parse_vn_number("4.450") == 4450.0
    assert parse_vn_number("4.450") != 4.45
