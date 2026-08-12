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
    # New test cases for dot-as-decimal (rule 3) and validation
    ("10.5", 10.5),         # 1 digit dot 1 digit - treat as decimal
    ("12.75", 12.75),       # 2 digits dot 2 digits - treat as decimal
    ("1.234", 1234.0),      # proper thousands grouping (1-3 + .3) - treat dot as thousands
    ("1.234.567", 1234567.0),  # multiple thousands groups
])
def test_parse_vn_number(raw, expected):
    assert parse_vn_number(raw) == expected


def test_thousands_separator_is_not_treated_as_decimal():
    """Regression guard: float('4.450') == 4.45 would understate DWT 1000x."""
    assert parse_vn_number("4.450") == 4450.0
    assert parse_vn_number("4.450") != 4.45
