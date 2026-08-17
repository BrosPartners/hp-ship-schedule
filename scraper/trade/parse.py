"""Bóc bảng "Nước/vùng lãnh thổ x Mặt hàng chủ yếu" từ PDF hải quan.

`page.get_text()` trả về thứ tự chữ bị đảo trong bảng này (giá trị số đứng
trước tên mặt hàng), nên phải đọc bằng `get_text("words")` rồi tự gộp theo
toạ độ (y để nhóm dòng, x để nhận diện cột).

Mỗi trang PDF in một mặt; mặt sau (mọi trang lẻ theo index 0-based: 1, 3, 5…)
luôn rỗng. Chỉ đọc trang có nội dung.

Bốn cột số dùng chung một header trên mọi trang: Lượng/Trị giá(USD) của
"Số liệu tháng báo cáo" rồi tới "Cộng dồn đến hết tháng báo cáo". Cột là
right-aligned nên toạ độ mép phải (x1) ổn định bất kể số có bao nhiêu chữ số,
còn mép trái (x0) trôi theo độ dài số - vì vậy phải gộp cột bằng x1, không phải
x0. Ngưỡng chia cột được tính động từ chính dòng header của từng trang (không
hard-code), vì đây là điểm neo duy nhất không phụ thuộc nội dung dữ liệu.
"""
from __future__ import annotations

import re

import fitz

_NUMERIC_RE = re.compile(r"^[\d.]+$")
_UNIT_TOKENS = {"USD", "Tấn"}
# Nhãn cột ĐVT nằm cố định quanh đây trên mọi file đã kiểm; dùng làm mỏ neo
# phụ để tách nhãn (bên trái) khỏi vùng số liệu (bên phải).
_UNIT_X_MIN, _UNIT_X_MAX = 270, 315


class HeaderNotFoundError(Exception):
    """Không tìm thấy dòng header cột trên một trang có nội dung."""


class ChecksumError(Exception):
    """Tổng trị giá các mặt hàng lệch quá xa so với dòng tổng của nước đó."""


def _rows_by_y(words, tol=2):
    """Gom các từ thành dòng theo toạ độ y, gộp các y lệch nhau trong `tol`."""
    ys = sorted({round(w[1]) for w in words})
    groups = []
    for y in ys:
        if groups and y - groups[-1][-1] <= tol:
            groups[-1].append(y)
        else:
            groups.append([y])
    row_of = {}
    for g in groups:
        rep = g[0]
        for y in g:
            row_of[y] = rep
    rows = {}
    for w in words:
        y = row_of[round(w[1])]
        rows.setdefault(y, []).append(w)
    return {y: sorted(ws, key=lambda w: w[0]) for y, ws in sorted(rows.items())}


def _find_column_edges(rows):
    """Đọc dòng header ("Lượng"/"(USD)" lặp lại hai lần) để lấy 4 mốc x1.

    Trả về ((biên1, biên2, biên3), y) - ba mốc giữa để phân 4 cột (lượng
    tháng, trị giá tháng, lượng cộng dồn, trị giá cộng dồn), kèm toạ độ y của
    chính dòng header đó. `y` dùng để cắt bỏ toàn bộ phần trên header (tiêu đề
    trang, tên bộ/cục, dòng "Nước/Mặt hàng chủ yếu ĐVT") - phần này lặp lại y
    hệt trên mọi trang và toàn chữ hoa, nên nếu không cắt sẽ bị hiểu nhầm
    thành dòng tổng của một "nước" mới.
    """
    for y, ws in rows.items():
        texts = [w[4] for w in ws]
        if texts.count("Lượng") == 2 and texts.count("(USD)") == 2:
            luong = sorted(w[2] for w in ws if w[4] == "Lượng")
            usd = sorted(w[2] for w in ws if w[4] == "(USD)")
            col1, col3 = luong
            col2, col4 = usd
            mid = lambda a, b: (a + b) / 2
            return (mid(col1, col2), mid(col2, col3), mid(col3, col4)), y
    raise HeaderNotFoundError("không tìm thấy dòng header cột trên trang này")


def _bucket(x1, edges):
    b1, b2, b3 = edges
    if x1 < b1:
        return "qty_month"
    if x1 < b2:
        return "usd_month"
    if x1 < b3:
        return "qty_cum"
    return "usd_cum"


def _to_number(text):
    return int(text.replace(".", ""))


def _is_country_label(label):
    """Dòng tổng theo nước viết hoa toàn bộ; dòng mặt hàng thì không.

    `str.isupper()` của Python nhận diện đúng chữ hoa có dấu tiếng Việt
    ("ẤN ĐỘ"), nên không cần bỏ dấu trước khi so.
    """
    letters = "".join(ch for ch in label if ch.isalpha())
    return bool(letters) and letters.isupper()


def parse_page(rows, current_country=None):
    """Trả về (mặt hàng, tổng theo nước, nước đang dở) cho một trang đã gom dòng.

    `current_country` được truyền vào/ra để nối tiếp qua trang: một nước có
    nhiều mặt hàng sẽ bị cắt giữa chừng ở cuối trang, và trang sau **không lặp
    lại tên nước** - chỉ có các dòng số tiếp theo. Reset theo từng trang sẽ âm
    thầm làm rơi mất đúng những mặt hàng bị cắt đó.
    """
    edges, header_y = _find_column_edges(rows)
    commodities = []
    countries = {}

    for y, ws in rows.items():
        if y <= header_y:
            continue  # tiêu đề trang / dòng header cột, không phải dữ liệu
        # Nhãn là các token chữ nằm bên trái vùng số, trừ chính token ĐVT.
        label_words = [w for w in ws
                       if w[4] not in _UNIT_TOKENS and not _NUMERIC_RE.match(w[4])
                       and w[0] < _UNIT_X_MIN]
        if not label_words:
            continue  # dòng header/tiêu đề, không có nhãn mặt hàng/nước
        label = " ".join(w[4] for w in label_words)

        unit = next((w[4] for w in ws if w[4] in _UNIT_TOKENS), None)
        values = {}
        for w in ws:
            if _NUMERIC_RE.match(w[4]) and w[4] not in _UNIT_TOKENS:
                values[_bucket(w[2], edges)] = _to_number(w[4])

        if _is_country_label(label):
            if not values and current_country is not None:
                # Tên nước dài tràn sang dòng thứ hai (ví dụ "TIỂU VƯƠNG QUỐC"
                # rồi "ARẬP THỐNG NHẤT" ở dòng kế). Dòng nối tiếp viết hoa y
                # hệt dòng tổng nhưng không mang số nào - đây là dấu hiệu phân
                # biệt duy nhất, vì cả hai đều toàn chữ hoa. Ghép lại thành một
                # tên và đổi tên ngược cho những gì đã gán trước đó.
                combined = f"{current_country} {label}"
                countries[combined] = countries.pop(current_country)
                for c in commodities:
                    if c["country"] == current_country:
                        c["country"] = combined
                current_country = combined
                continue
            current_country = label
            countries[label] = {
                "usd_month": values.get("usd_month"),
                "usd_cum": values.get("usd_cum"),
            }
            continue

        if current_country is None:
            continue  # dòng trước khi gặp nước đầu tiên (phần header còn sót)

        commodities.append({
            "country": current_country, "commodity": label, "unit": unit,
            "usd_month": values.get("usd_month"), "usd_cum": values.get("usd_cum"),
            "qty_month": values.get("qty_month"), "qty_cum": values.get("qty_cum"),
        })

    return commodities, countries, current_country


def parse_pdf(path, month, flow, check_tolerance=0.02):
    """Bóc toàn bộ PDF, trả về list bản ghi phẳng.

    `check_tolerance` là sai số tương đối tối đa cho phép giữa tổng các mặt
    hàng và dòng tổng của nước - vượt ngưỡng thì raise thay vì lặng lẽ dùng số
    sai. 2% để chừa chỗ cho làm tròn/mặt hàng lặt vặt hải quan gộp khác cách.
    """
    doc = fitz.open(path)
    all_commodities, all_countries = [], {}
    current_country = None
    for page in doc:
        words = page.get_text("words")
        if not words:
            continue  # mặt sau tờ in, luôn rỗng
        rows = _rows_by_y(words)
        commodities, countries, current_country = parse_page(rows, current_country)
        all_commodities.extend(commodities)
        all_countries.update(countries)
    doc.close()

    by_country = {}
    for c in all_commodities:
        by_country.setdefault(c["country"], []).append(c["usd_month"] or 0)
    for country, total in all_countries.items():
        expected = total.get("usd_month")
        if expected is None:
            continue
        actual = sum(by_country.get(country, []))
        if expected and abs(actual - expected) / expected > check_tolerance:
            raise ChecksumError(
                f"{path}: {country} - tổng mặt hàng {actual:,} lệch quá xa so "
                f"với dòng tổng {expected:,} (tháng {month}, {flow})")

    return [{"month": month, "flow": flow, **c} for c in all_commodities]
