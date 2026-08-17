"""Mốc thời điểm nguồn lịch tàu thực sự bắt đầu có dữ liệu cho một cụm cảng.

Cảng vụ TP.HCM chỉ đăng khu Vũng Tàu - Cái Mép - Thị Vải từ 01/08/2025, sau
khi Bà Rịa - Vũng Tàu sáp nhập vào TP.HCM; số dòng thô trong ngày nhảy từ
~120 lên ~210 đúng ngày 01/08. Vài lượt tàu lẻ xuất hiện trước mốc đó không
phải là "thị phần gần bằng 0" mà là *chưa có dữ liệu*, và hai chỗ sẽ nói dối
nếu để nguyên:

- Chart thị phần vẽ Cái Mép gần 0% suốt 2023-2025 rồi bùng nổ - một cú tăng
  trưởng không có thật.
- Tỷ lệ TEU/lượt tàu lấy tử số VPA (đủ từ 2023) chia cho mẫu số thiếu:
  Gemalink tháng 7/2025 từng ra 87.202 TEU/lượt, gấp 28 lần mức thật.

Module này đứng riêng thay vì nằm trong `scraper.vpa.build` vì cả
`scraper.hcm.aggregate` lẫn `scraper.vpa.build` đều cần, mà hai module đó đã
phụ thuộc lẫn nhau một chiều.
"""
from __future__ import annotations

import csv
from pathlib import Path


def load_coverage(path):
    """{tên cụm: tháng đầu tiên có dữ liệu, dạng "YYYY-MM"}."""
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {row["cluster"].strip(): row["from_month"].strip()
                for row in csv.DictReader(fh) if row["cluster"].strip()}


def load_cluster_zones(path):
    """{tên cụm: zone}. Xem `data/hcm/cluster_zones_notes.md`."""
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {row["cluster"].strip(): row["zone"].strip()
                for row in csv.DictReader(fh)
                if row["cluster"].strip() and row["zone"].strip()}


def apply_coverage(volume, coverage):
    """Bỏ các khoá (tháng, cụm) nằm trước mốc nguồn bắt đầu đăng.

    Cụm không khai báo trong file thì giữ nguyên toàn bộ lịch sử.
    """
    return {(month, member): v for (month, member), v in volume.items()
            if month >= coverage.get(member, "")}
