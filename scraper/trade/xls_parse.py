"""Bóc số liệu XNK từ file Excel gốc của Tổng cục Thống kê/Hải quan.

Đây là nguồn tốt hơn nhiều so với PDF hải quan (`scraper.trade.parse`): Excel
thật, không cần đọc theo toạ độ, và một file duy nhất đã phủ nhiều năm (mỗi
lần owner tải về là có luôn lịch sử, không phải ghép 86 file như PDF).

Ba dạng file, bố cục bảng rộng giống nhau (mỗi tháng chiếm 2 cột con, năm sau
nối tiếp năm trước trên cùng hàng, không lặp lại nhãn năm - nhãn năm chỉ xuất
hiện ở ô đầu mỗi khối 12 tháng):

- "Xuất khẩu-*.xls" / "Nhập khẩu-*.xls": mỗi mặt hàng một dòng, mỗi tháng có
  cặp cột Lượng/Trị giá. Có dòng "Tổng số" dùng để đối chiếu.
- "V03-*.xls": mỗi tháng có cặp cột Xuất khẩu/Nhập khẩu (không phải Lượng/Trị
  giá). Nước được nhóm sẵn thành khối EU, khối ASEAN (mang giá trị tổng ngay
  trên dòng tên khối, các dòng "Trong đó:" bên dưới chỉ là chi tiết - không
  được cộng thêm, kẻo tính đôi) và một khối "Một số nước khác" liệt kê từng
  nước rời rạc không có dòng tổng riêng.

Vị trí dòng năm/tháng dò động thay vì hard-code, vì hai file mẫu đã có số dòng
tiêu đề lệch nhau một dòng (file nhập khẩu thiếu một dòng trống so với file
xuất khẩu) - hard-code sẽ đọc sai ngay khi owner tải một phiên bản khác đợt.
"""
from __future__ import annotations

import re

import pandas as pd

_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_RE = re.compile(r"^Tháng\s*0?(\d{1,2})$")

# File nhập khẩu bắt đầu công bố chi tiết ba nhóm hàng này từ 01/2025 - trước
# đó các dòng con luôn trống nên vô hại, nhưng từ 01/2025 chúng có số thật,
# và số đó đã nằm sẵn trong dòng cha ("Xăng dầu các loại", "Phân bón các
# loại", "Ô tô nguyên chiếc các loại (*)"). Cộng thêm cả dòng con sẽ tính đôi
# - phát hiện được nhờ chính guard đối chiếu tổng bên dưới báo lệch 2-5% đúng
# từ tháng 01/2025 trở đi. Hai dòng có dấu ":" cuối tên ("Thịt và các sản
# phẩm từ thịt:", "Sắn và các sản phẩm từ sắn:") đã kiểm và KHÔNG có dòng con
# - dấu ":" chỉ là lỗi định dạng của file gốc, không phải luôn là mục cha.
_KNOWN_SUB_ITEMS = {
    "Xăng", "Dầu DO", "Dầu FO", "Nhiên liệu bay",
    "Phân U rê", "Phân NPK", "Phân DAP", "Phân SA", "Phân Kali",
    "Ô tô 9 chỗ ngồi trở xuống", "Ô tô trên 9 chỗ ngồi", "Ô tô tải",
}


class LayoutError(Exception):
    """Không dò được vị trí hàng năm/tháng hoặc dòng Tổng số trong file."""


class ChecksumError(Exception):
    """Tổng các dòng chi tiết lệch quá xa so với dòng Tổng số/Tổng."""


def _find_year_row(df, max_scan=8):
    """Hàng đầu tiên có >=2 giá trị số dạng năm (2000-2100)."""
    for r in range(min(max_scan, len(df))):
        years = [v for v in df.iloc[r, :] if isinstance(v, (int, float))
                 and 2000 < v < 2100]
        if len(years) >= 2:
            return r
    raise LayoutError("không tìm thấy hàng nhãn năm trong 8 hàng đầu")


def _month_columns(df, month_row):
    """{cột: (năm, tháng)} - ghép nhãn năm (thưa) với nhãn tháng (dày đặc).

    Nhãn năm chỉ có ở cột đầu mỗi khối 12 tháng; các cột sau trong cùng khối
    dùng lại năm đó tới khi gặp nhãn năm mới.
    """
    year_row = month_row - 1
    years = {c: int(v) for c, v in enumerate(df.iloc[year_row, :])
             if isinstance(v, (int, float)) and 2000 < v < 2100}
    if not years:
        raise LayoutError("không tìm thấy nhãn năm ngay trên hàng tháng")
    year_cols = sorted(years)
    out = {}
    for c, v in enumerate(df.iloc[month_row, :]):
        hit = _MONTH_RE.match(str(v).strip()) if pd.notna(v) else None
        if not hit:
            continue
        year_col = max((yc for yc in year_cols if yc <= c), default=None)
        if year_col is None:
            raise LayoutError(f"cột tháng {c} không có nhãn năm nào phía trước")
        out[c] = (years[year_col], int(hit.group(1)))
    return out


def _find_label_row(df, label, col=0, max_scan=None):
    limit = len(df) if max_scan is None else max_scan
    for r in range(limit):
        if str(df.iloc[r, col]).strip() == label:
            return r
    raise LayoutError(f"không tìm thấy dòng {label!r} ở cột {col}")


def _checked_sum(rows_iter, total, month, tolerance, context):
    total_actual = sum(v for _, v in rows_iter)
    if total and abs(total_actual - total) / abs(total) > tolerance:
        raise ChecksumError(
            f"{context}: tổng chi tiết {total_actual:,.0f} lệch quá xa so với "
            f"dòng tổng {total:,.0f} (tháng {month})")


def parse_commodity_xls(path, sheet_name, flow, tolerance=0.02):
    """Đọc "Xuất khẩu-*.xls"/"Nhập khẩu-*.xls" -> [{month, flow, commodity, usd}].

    Giá trị lấy từ cột "Trị giá (1000 USD)" - cột liền sau mỗi cột "Lượng".
    Đổi ra USD nguyên (nhân 1000) để cùng đơn vị với phần còn lại của repo.
    """
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    year_row = _find_year_row(df)
    month_row = year_row + 1
    months = _month_columns(df, month_row)
    total_row = _find_label_row(df, "Tổng số", col=0, max_scan=month_row + 6)
    group_header_row = _find_label_row(df, "Nhóm/Mặt hàng chủ yếu", col=0,
                                       max_scan=total_row + 6)

    out = []
    by_month = {}
    for col, (year, month) in months.items():
        value_col = col + 1  # "Trị giá" nằm ngay sau "Lượng"
        month_key = f"{year}-{month:02d}"
        total = df.iloc[total_row, value_col]
        total = float(total) * 1000 if pd.notna(total) else None
        rows = []
        for r in range(group_header_row + 1, len(df)):
            name = df.iloc[r, 0]
            val = df.iloc[r, value_col]
            if pd.isna(name) or pd.isna(val):
                continue
            if str(name).strip() in _KNOWN_SUB_ITEMS:
                continue
            usd = float(val) * 1000
            rows.append((str(name).strip(), usd))
            out.append({"month": month_key, "flow": flow,
                       "commodity": str(name).strip(), "usd_month": usd})
        by_month[month_key] = (rows, total)

    for month_key, (rows, total) in by_month.items():
        _checked_sum(rows, total, month_key, tolerance,
                    f"{path} ({flow})")
    return out


def parse_country_xls(path, sheet_name, tolerance=0.02):
    """Đọc "V03-*.xls" -> [{month, flow, label, usd, is_bloc}].

    `label` là tên gốc trong file: "EU", "ASEAN" (đã là khối tổng hợp sẵn) hoặc
    tên một nước dưới mục "Một số nước khác". `is_bloc=True` cho hai khối EU/
    ASEAN, để tầng gộp nhóm biết bỏ qua các dòng "Trong đó:" chi tiết bên dưới
    (đã nằm trong số của khối, cộng thêm sẽ tính đôi).
    """
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    year_row = _find_year_row(df)
    month_row = year_row + 1
    months = _month_columns(df, month_row)
    total_row = _find_label_row(df, "Tổng", col=1, max_scan=month_row + 6)

    bloc_rows = {}
    other_rows = []
    skip_until = -1
    for r in range(total_row + 1, len(df)):
        bloc = df.iloc[r, 0]
        name = df.iloc[r, 1]
        if pd.notna(bloc):
            bloc = str(bloc).strip()
            if bloc == "Một số nước khác":
                skip_until = -1  # phần này liệt kê nước rời rạc, không khối
                continue
            bloc_rows[bloc] = r
            skip_until = r  # dòng khối mang giá trị; các dòng "Trong đó:" sau nó bị bỏ
            continue
        if pd.isna(name) or str(name).strip() == "Trong đó:":
            continue
        # Dòng chi tiết ngay sau một dòng khối (EU/ASEAN) là thành phần đã
        # gộp trong khối đó - chỉ những dòng dưới mục "Một số nước khác" mới
        # là các nước độc lập cần cộng riêng.
        if skip_until == -1:
            other_rows.append((r, str(name).strip()))

    out = []
    by_month_flow = {}
    for col, (year, month) in months.items():
        # Cột mang nhãn tháng chính là cột Xuất khẩu; cột liền sau là Nhập
        # khẩu - khác với file mặt hàng (Lượng rồi mới tới Trị giá), ở đây
        # không có cột Lượng nào chen giữa.
        month_key = f"{year}-{month:02d}"
        for flow, value_col in (("export", col), ("import", col + 1)):
            total = df.iloc[total_row, value_col]
            total = float(total) if pd.notna(total) else None
            rows = []
            for bloc in ("EU", "ASEAN"):
                if bloc in bloc_rows:
                    val = df.iloc[bloc_rows[bloc], value_col]
                    if pd.notna(val):
                        rows.append((bloc, float(val)))
            for r, name in other_rows:
                val = df.iloc[r, value_col]
                if pd.isna(val):
                    continue
                rows.append((name, float(val)))
            # Đổi ra USD nguyên khi ghi ra ngoài, nhưng đối chiếu tổng
            # (`_checked_sum`) vẫn dùng đơn vị gốc (nghìn USD) cho khớp với
            # `total` - nhân trước rồi so sẽ chỉ đổi tỷ lệ, không đổi kết quả,
            # nhưng giữ đơn vị gốc để lỡ có sai số làm tròn thì dễ đọc hơn.
            for label, usd in rows:
                out.append({"month": month_key, "flow": flow, "country": label,
                           "usd_month": usd * 1000})
            by_month_flow[(month_key, flow)] = (rows, total)

    for (month_key, flow), (rows, total) in by_month_flow.items():
        _checked_sum(rows, total, month_key, tolerance, f"{path} ({flow})")
    return out
