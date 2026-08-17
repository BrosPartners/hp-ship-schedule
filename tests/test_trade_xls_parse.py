import openpyxl
import pytest

from scraper.trade.xls_parse import (ChecksumError, LayoutError,
                                     parse_commodity_xls, parse_country_xls)


def _wb(rows):
    """rows: list các (giá trị theo cột A,B,C,...) - None cho ô trống."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row, start=1):
            if val is not None:
                ws.cell(row=r, column=c, value=val)
    return wb


# >=2 mốc năm trên cùng dòng là dấu hiệu bắt buộc để _find_year_row nhận ra
# đúng dòng - file thật luôn có ít nhất 2 khối năm nối tiếp, và ngưỡng này cố
# ý chặn một dòng số liệu trùng đơn lẻ có thật ở ngay phía trên dòng năm thật
# trong file gốc. Fixture vì vậy phải có đủ 2 khối năm, không chỉ 1.
# Cột: 0=tên, (1,2)=Lượng/Trị giá Tháng01/2024, (3,4)=Lượng/Trị giá Tháng02/2024,
# (5,6)=Lượng/Trị giá Tháng01/2025. Nhãn năm nằm ở đúng cột "Lượng" đầu mỗi
# khối (cột 1 và cột 5) - giống hệt vị trí trong file thật.
COMMODITY_ROWS = [
    ["Tiêu đề báo cáo"],
    [None, 2024, None, None, None, 2025],
    [None, "Tháng 01", None, "Tháng 02", None, "Tháng 01"],
    [None, "Lượng\n(Tấn)", "Trị giá \n(1000 USD)", "Lượng\n(Tấn)", "Trị giá \n(1000 USD)",
     "Lượng\n(Tấn)", "Trị giá \n(1000 USD)"],
    ["Tổng số", None, 1000, None, 900, None, 1100],
    ["T/đó: Khu vực có vốn ĐTTTNN"],
    ["Nhóm/Mặt hàng chủ yếu"],
    ["Hàng thủy sản", None, 400, None, 350, None, 450],
    ["Hàng hóa khác", None, 600, None, 550, None, 650],
]


def _commodity_path(tmp_path, rows=None):
    wb = _wb(rows or COMMODITY_ROWS)
    path = tmp_path / "commodity.xlsx"
    wb.save(path)
    return path


def test_parses_month_value_columns(tmp_path):
    rows = parse_commodity_xls(_commodity_path(tmp_path), "Sheet", "export")

    by_month = {(r["month"], r["commodity"]): r["usd_month"] for r in rows}
    assert by_month[("2024-01", "Hàng thủy sản")] == 400_000
    assert by_month[("2024-02", "Hàng hóa khác")] == 550_000


def test_amounts_are_scaled_from_thousand_usd_to_usd(tmp_path):
    rows = parse_commodity_xls(_commodity_path(tmp_path), "Sheet", "export")

    assert all(r["usd_month"] % 1000 == 0 for r in rows)


def test_skips_pre_group_subtotal_rows(tmp_path):
    rows = parse_commodity_xls(_commodity_path(tmp_path), "Sheet", "export")

    assert "T/đó: Khu vực có vốn ĐTTTNN" not in {r["commodity"] for r in rows}


def test_checksum_mismatch_raises(tmp_path):
    bad = [row[:] for row in COMMODITY_ROWS]
    bad[4] = ["Tổng số", None, 999999, None, 900]  # Tổng số T01 sai lệch xa

    with pytest.raises(ChecksumError):
        parse_commodity_xls(_commodity_path(tmp_path, bad), "Sheet", "export")


def test_known_sub_items_are_excluded_to_avoid_double_counting(tmp_path):
    rows = [row[:] for row in COMMODITY_ROWS]
    # "Xăng dầu các loại" (mục cha) + "Xăng" (mục con) - cộng cả hai sẽ lệch
    # tổng, đúng lỗi thật đã gặp trên file nhập khẩu từ 01/2025.
    rows[4] = ["Tổng số", None, 1200, None, 900]
    rows.append(["Xăng dầu các loại", None, 200, None, 0])
    rows.append(["Xăng", None, 200, None, 0])

    parsed = parse_commodity_xls(_commodity_path(tmp_path, rows), "Sheet", "export")

    assert "Xăng" not in {r["commodity"] for r in parsed}


def test_layout_error_when_no_year_row(tmp_path):
    wb = _wb([["không có gì liên quan ở đây"]])
    path = tmp_path / "empty.xlsx"
    wb.save(path)

    with pytest.raises(LayoutError):
        parse_commodity_xls(path, "Sheet", "export")


# Cột: 0=khối, 1=tên nước, (2,3)=XK/NK Tháng01/2024, (4,5)=XK/NK Tháng02/2024,
# (6,7)=XK/NK Tháng01/2025. Nhãn năm nằm ở đúng cột XK đầu mỗi khối (cột 2 và
# cột 6), cần đủ 2 khối năm để qua ngưỡng dò dòng năm như file thật.
COUNTRY_ROWS = [
    ["Tiêu đề V03"],
    [None, None],
    [None, None, 2024, None, None, None, 2025],
    ["Khối nước, nước", None, "Tháng 01", None, "Tháng 02", None, "Tháng 01"],
    [None, None, "Xuất khẩu", "Nhập khẩu", "Xuất khẩu", "Nhập khẩu", "Xuất khẩu", "Nhập khẩu"],
    [None, "Tổng", 1000, 900, 1100, 950, 1200, 1000],
    ["EU", None, 300, 200, 320, 210, 330, 220],
    [None, "Trong đó:"],
    [None, "Đức", 150, 100, 160, 105, 165, 110],
    ["Một số nước khác"],
    [None, "Mỹ", 400, 300, 420, 310, 450, 320],
    [None, "CHND Trung Hoa", 300, 400, 360, 430, 420, 460],
]


def _country_path(tmp_path, rows=None):
    wb = _wb(rows or COUNTRY_ROWS)
    path = tmp_path / "country.xlsx"
    wb.save(path)
    return path


def test_bloc_row_used_directly_not_its_detail(tmp_path):
    rows = parse_country_xls(_country_path(tmp_path), "Sheet")

    eu_jan_export = next(r["usd_month"] for r in rows
                         if r["month"] == "2024-01" and r["flow"] == "export"
                         and r["country"] == "EU")
    assert eu_jan_export == 300_000
    assert "Đức" not in {r["country"] for r in rows}


def test_individual_countries_after_bloc_section_are_kept(tmp_path):
    rows = parse_country_xls(_country_path(tmp_path), "Sheet")

    names = {r["country"] for r in rows}
    assert {"Mỹ", "CHND Trung Hoa"} <= names


def test_export_and_import_columns_are_adjacent(tmp_path):
    rows = parse_country_xls(_country_path(tmp_path), "Sheet")

    my_jan = {r["flow"]: r["usd_month"] for r in rows
             if r["month"] == "2024-01" and r["country"] == "Mỹ"}
    assert my_jan == {"export": 400_000, "import": 300_000}


def test_country_checksum_mismatch_raises(tmp_path):
    bad = [row[:] for row in COUNTRY_ROWS]
    bad[5] = [None, "Tổng", 999999, 900, 1100, 950]

    with pytest.raises(ChecksumError):
        parse_country_xls(_country_path(tmp_path, bad), "Sheet")
