"""Dò và tải PDF "Xuất/Nhập khẩu theo nước × mặt hàng chủ yếu" từ hải quan.

Cổng customs.gov.vn không phát hành Excel — đã kiểm ba nơi (trang Thống kê hải
quan, trang Số liệu định kỳ, VCCI đăng lại), không nơi nào có .xls/.xlsx. PDF
là lựa chọn duy nhất, may là text thật chứ không phải ảnh scan.

Mỗi tháng hải quan phát hành 5 biểu, chỉ biểu 5x (xuất) và 5n (nhập) có đủ cả
hai chiều nước và mặt hàng - ba biểu còn lại (3x/3n FDI, 4 theo tỉnh) không
dùng. URL file không đoán được theo quy luật (ngày công bố khác nhau từng
tháng, và tên file có cả lỗi gõ như thừa số ở đầu), nên phải dò qua API JSON
đứng sau trang liệt kê thay vì thử URL.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

API_URL = "https://www.customs.gov.vn/bridge?url=/customs/api/GetTKHQInfo"
# Client gốc của trang gửi body là một chuỗi JSON dưới header
# x-www-form-urlencoded (không phải lỗi của mình - đọc được từ scripts/main.js
# của chính trang: $.ajax({type:"POST", data: JSON.stringify(t), ...}) không
# đặt contentType nên jQuery dùng mặc định). Giữ nguyên cách gọi này vì server
# parse theo đúng kiểu đó; gửi application/json thật sẽ ra lỗi 500.
HEADERS = {"User-Agent": "Mozilla/5.0 (hp-ship-schedule trade fetcher)",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
PAGE_SIZE = 20
# Tiêu đề luôn chứa cụm này ở cả bản xuất và nhập; lọc tại nguồn thay vì tải
# toàn bộ danh sách rồi lọc, cho nhanh và đỡ tốn quota.
KEYWORD = "mặt hàng chủ yếu"

MONTH_RE = re.compile(r"^(\d{2})-(\d{4})$")


class TitleMismatchError(Exception):
    """Tiêu đề không xác định được là bản xuất khẩu hay nhập khẩu."""


def _month_key(ngay_cong_bo):
    """"07-2026" -> "2026-07". Raise nếu định dạng đổi khác."""
    hit = MONTH_RE.match(ngay_cong_bo.strip())
    if not hit:
        raise ValueError(f"NGAY_CONG_BO không đúng định dạng MM-YYYY: {ngay_cong_bo!r}")
    return f"{hit.group(2)}-{hit.group(1)}"


def _flow_of(title):
    """Xác định xuất hay nhập từ tiêu đề. Raise nếu không rõ - đừng đoán."""
    lower = title.lower()
    is_export = "xuất khẩu" in lower
    is_import = "nhập khẩu" in lower
    if is_export == is_import:  # cả hai hoặc không cái nào
        raise TitleMismatchError(f"không xác định được xuất/nhập từ: {title!r}")
    return "export" if is_export else "import"


def list_reports(session=None, start_month="2023-01", max_pages=20):
    """Liệt kê các bản ghi biểu 5x/5n, mới nhất trước, dừng khi đã đủ lịch sử.

    `max_pages` là lưới an toàn (20 trang x 20 bản ghi = đủ ~16 năm dữ liệu
    tháng x 2 chiều) - không phải mốc kỳ vọng bình thường sẽ chạm tới.
    """
    session = session or requests.Session()
    out = []
    for page in range(max_pages):
        payload = {"skip": page * PAGE_SIZE, "take": PAGE_SIZE, "ky": "",
                   "textSearch": KEYWORD, "typeName": "GetListSoLieu",
                   "language": "TIENG_VIET", "thoigianCongBo": ""}
        resp = session.post(API_URL, data=json.dumps(payload, ensure_ascii=False),
                            headers=HEADERS, timeout=30)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("arr") or []
        if not rows:
            break
        done = False
        for row in rows:
            month = _month_key(row["NGAY_CONG_BO"])
            out.append({"month": month, "flow": _flow_of(row["TIEU_DE"]),
                       "title": row["TIEU_DE"], "url": row["FILE_SO_BO"],
                       "label": row.get("TEN_THE_LOAI", "")})
            if month < start_month:
                done = True
        if done:
            break
        time.sleep(0.3)  # đừng dồn dập vào một API công
    return [r for r in out if r["month"] >= start_month]


def download(url, dest_dir, session=None):
    """Tải một PDF về `dest_dir`, trả về đường dẫn. Ghi nguyên tử."""
    session = session or requests.Session()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    dest = dest_dir / name
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if len(resp.content) < 1000:
        raise ValueError(f"file tải về quá nhỏ ({len(resp.content)} byte): {url}")
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)
    return dest


def sync(dest_dir, start_month="2023-01", session=None):
    """Dò danh sách rồi tải mọi file chưa có sẵn trong `dest_dir`."""
    session = session or requests.Session()
    reports = list_reports(session=session, start_month=start_month)
    downloaded = []
    for r in reports:
        name = r["url"].rsplit("/", 1)[-1]
        path = Path(dest_dir) / name
        if not path.exists():
            downloaded.append(download(r["url"], dest_dir, session=session))
    return reports, downloaded
