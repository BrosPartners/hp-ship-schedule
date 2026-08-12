from datetime import date
from scraper.fetch import offset_for


def test_offset_for_is_relative_to_today():
    today = date(2026, 8, 12)
    assert offset_for(date(2026, 8, 12), today) == 0
    assert offset_for(date(2026, 8, 13), today) == 1
    assert offset_for(date(2026, 8, 11), today) == -1
    # Verified against the live site on 2026-08-12: d=-1320 -> 31/12/2022
    assert offset_for(date(2022, 12, 31), today) == -1320
    # Verified: d=-2000 -> 19/02/2021
    assert offset_for(date(2021, 2, 19), today) == -2000
