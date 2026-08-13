# hp-ship-schedule

Dashboard lịch tàu cảng Hải Phòng, dữ liệu từ 2023-01-01, tự cập nhật hằng ngày.

Live: https://brospartners.github.io/hp-ship-schedule/ — deploy bằng GitHub
Pages (`.github/workflows/pages.yml`), tự chạy lại mỗi khi bot cào dữ liệu
hằng ngày commit vào `master` (`daily.yml`), nên dashboard luôn hiện dữ liệu
mới nhất mà không cần thao tác gì thêm.

Nguồn: `csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx?d=<offset>` — offset là
số ngày lệch so với hôm nay, **luôn tính lại**, không hardcode.

## Chạy

    python -m pip install -r requirements.txt
    python -m pytest                                   # test offline
    python -m scraper.backfill --start 2023-01-01       # chạy tay, ~40 phút
    python tools/unmapped_report.py                     # xem giá trị bến chưa map
    python -m scraper.daily                             # cập nhật 3 ngày gần nhất

## Lưu ý

- Parser **bắt buộc** dùng `lxml`. `html.parser` làm sập bảng mà không báo lỗi.
- Section `qua_luong` có 10 cột, khác 3 section còn lại (13 cột).
- Số kiểu Việt Nam: `.` là phân cách nghìn, `,` là thập phân.
- `data/berth_map.csv` sửa tay được; sửa xong lần chạy kế tiếp sẽ áp dụng.
- Chỉ tiêu "độ trượt kế hoạch" trống cho toàn bộ giai đoạn backfill — dữ liệu lịch
  sử chỉ có một snapshot mỗi ngày.

Chi tiết thiết kế: `../docs/superpowers/specs/2026-08-12-hp-ship-schedule-design.md`
