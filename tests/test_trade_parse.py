import fitz
import pytest

from scraper.trade.parse import (ChecksumError, HeaderNotFoundError,
                                 _is_country_label, parse_pdf)

# Bố cục toạ độ mô phỏng đúng file thật: cột right-aligned, header lặp mỗi
# trang, tên nước có thể tràn sang dòng thứ hai hoặc sang trang sau.
PAGE_TITLE_Y = 44
HEADER_UNIT_Y = 176
COLUMN_HEADER_Y = 191
FIRST_DATA_Y = 219


# Base14 "helv" chỉ có bảng mã Latin-1, không có dấu tiếng Việt tổ hợp sẵn
# (ộ, ậ, ẤN...) - cần font hệ thống có phủ Unicode để dựng PDF giả lập đúng.
_VN_FONT = r"C:\Windows\Fonts\arial.ttf"


def _draw_row(page, y, cells):
    """cells: list (x, text). Toạ độ khớp đúng các cột đã đo trên file thật."""
    for x, text in cells:
        page.insert_text((x, y), text, fontsize=9, fontfile=_VN_FONT,
                         fontname="F0")


def _new_page(doc):
    page = doc.new_page(width=612, height=850)
    _draw_row(page, PAGE_TITLE_Y, [(86, "BỘ"), (105, "TÀI"), (128, "CHÍNH")])
    _draw_row(page, HEADER_UNIT_Y, [(110, "Nước/Mặt"), (161, "hàng"),
                                    (187, "chủ"), (207, "yếu"), (282, "ĐVT")])
    _draw_row(page, COLUMN_HEADER_Y, [
        (324, "Lượng"), (371, "Trị"), (387, "giá"), (403, "(USD)"),
        (451, "Lượng"), (502, "Trị"), (518, "giá"), (534, "(USD)"),
    ])
    return page


def _country_row(page, y, name, usd_month, usd_cum):
    cells = [(61, name), (390, f"{usd_month:,}".replace(",", ".")),
             (523, f"{usd_cum:,}".replace(",", "."))]
    _draw_row(page, y, cells)


def _commodity_row(page, y, name, usd_month=None, usd_cum=None, unit="USD"):
    cells = [(65, name), (282, unit)]
    if usd_month is not None:
        cells.append((390, f"{usd_month:,}".replace(",", ".")))
    if usd_cum is not None:
        cells.append((523, f"{usd_cum:,}".replace(",", ".")))
    _draw_row(page, y, cells)


@pytest.fixture()
def simple_pdf(tmp_path):
    doc = fitz.open()
    page = _new_page(doc)
    _country_row(page, FIRST_DATA_Y, "AI CẬP", 1000, 5000)
    _commodity_row(page, FIRST_DATA_Y + 20, "Hàng thủy sản", 400, 2000)
    _commodity_row(page, FIRST_DATA_Y + 40, "Hàng hóa khác", 600, 3000)
    path = tmp_path / "simple.pdf"
    doc.save(path)
    doc.close()
    return path


def test_parses_country_and_commodity_rows(simple_pdf):
    rows = parse_pdf(simple_pdf, month="2026-07", flow="export")

    assert {r["commodity"]: r["usd_month"] for r in rows} == {
        "Hàng thủy sản": 400, "Hàng hóa khác": 600,
    }
    assert all(r["country"] == "AI CẬP" for r in rows)


def test_page_title_is_not_mistaken_for_a_country(simple_pdf):
    rows = parse_pdf(simple_pdf, month="2026-07", flow="export")

    assert all("BỘ" not in r["country"] for r in rows)
    assert all("Nước/Mặt" not in r["commodity"] for r in rows)


def test_checksum_mismatch_raises(tmp_path):
    doc = fitz.open()
    page = _new_page(doc)
    _country_row(page, FIRST_DATA_Y, "AI CẬP", 1000, 5000)
    _commodity_row(page, FIRST_DATA_Y + 20, "Hàng thủy sản", 10, 2000)
    path = tmp_path / "bad.pdf"
    doc.save(path); doc.close()

    with pytest.raises(ChecksumError):
        parse_pdf(path, month="2026-07", flow="export")


def test_country_name_wraps_to_a_second_line(tmp_path):
    doc = fitz.open()
    page = _new_page(doc)
    _country_row(page, FIRST_DATA_Y, "TIỂU VƯƠNG QUỐC", 1000, 5000)
    _draw_row(page, FIRST_DATA_Y + 14, [(61, "ARẬP"), (110, "THỐNG"), (160, "NHẤT")])
    _commodity_row(page, FIRST_DATA_Y + 34, "Hàng hóa khác", 1000, 5000)
    path = tmp_path / "wrap.pdf"
    doc.save(path); doc.close()

    rows = parse_pdf(path, month="2026-07", flow="export")

    assert rows[0]["country"] == "TIỂU VƯƠNG QUỐC ARẬP THỐNG NHẤT"


def test_country_continues_across_a_page_break(tmp_path):
    # Trang 1: nước + một mặt hàng nằm sát cuối trang, không có dòng tổng nào
    # khác theo sau. Trang 2: tiếp tục các mặt hàng của CÙNG nước đó, không
    # lặp lại tên - đúng như file thật khi một nước có nhiều mặt hàng.
    doc = fitz.open()
    p1 = _new_page(doc)
    _country_row(p1, FIRST_DATA_Y, "ĂNGGÔLA", 1000, 5000)
    _commodity_row(p1, FIRST_DATA_Y + 20, "Hàng hóa khác", 400, 2000)
    p2 = _new_page(doc)
    _commodity_row(p2, FIRST_DATA_Y, "Dầu thô", 600, 3000)
    path = tmp_path / "crosspage.pdf"
    doc.save(path); doc.close()

    rows = parse_pdf(path, month="2026-07", flow="export")

    assert {r["commodity"]: r["country"] for r in rows} == {
        "Hàng hóa khác": "ĂNGGÔLA", "Dầu thô": "ĂNGGÔLA",
    }


def test_no_header_raises(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=850)
    _draw_row(page, 100, [(61, "AI CẬP"), (390, "1.000")])
    path = tmp_path / "noheader.pdf"
    doc.save(path); doc.close()

    with pytest.raises(HeaderNotFoundError):
        parse_pdf(path, month="2026-07", flow="export")


@pytest.mark.parametrize("label,expected", [
    ("AI CẬP", True), ("ẤN ĐỘ", True), ("Hàng thủy sản", False),
    ("Hàng hóa khác", False), ("", False), ("123", False),
])
def test_is_country_label(label, expected):
    assert _is_country_label(label) is expected
