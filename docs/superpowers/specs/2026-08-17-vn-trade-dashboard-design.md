# Thiết kế — tab Xuất nhập khẩu Việt Nam

- **Ngày:** 2026-08-17
- **Trạng thái:** đã duyệt thiết kế, chờ duyệt spec và lập kế hoạch triển khai
- **Phạm vi:** thêm một dataset quốc gia và tab dashboard mới, bên cạnh hai dataset lịch tàu Hải Phòng và TP.HCM.

## 1. Mục tiêu

Theo dõi kim ngạch thương mại hàng hóa của Việt Nam từ **01/2023**, tự cập nhật khi Cục Hải quan công bố báo cáo tháng mới. Tab phục vụ phân tích đầu tư, không phải thay thế số liệu thống kê chính thức.

Người dùng xem được, theo tháng:

1. Tổng trị giá xuất khẩu và nhập khẩu.
2. Cơ cấu xuất khẩu theo nhóm ngành.
3. Cơ cấu nhập khẩu theo nhóm ngành.
4. Cơ cấu xuất khẩu theo thị trường.
5. Cơ cấu nhập khẩu theo thị trường.

Đơn vị gốc là USD; giao diện mặc định hiển thị tỷ USD. Kỳ chưa được công bố phải là `chưa có dữ liệu`, tuyệt đối không là 0.

## 2. Nguồn và định nghĩa kỳ

Nguồn duy nhất là các báo cáo thống kê xuất nhập khẩu công khai của **Cục Hải quan** (`customs.gov.vn` và kho tệp `files.customs.gov.vn`). Pipeline lưu URL nguồn, tiêu đề báo cáo, thời điểm tải và checksum PDF để mỗi số trên dashboard truy nguyên được về báo cáo gốc.

Hai loại bảng cần trích xuất:

| Lớp dữ liệu | Bảng chính thức cần dùng | Mục đích |
|---|---|---|
| Tổng và mặt hàng | Bảng xuất khẩu / nhập khẩu theo nhóm, mặt hàng chủ yếu | Tổng tháng và nhóm ngành |
| Đối tác | Bảng xuất khẩu theo nước/vùng lãnh thổ và nhập khẩu theo nước/vùng lãnh thổ | Cơ cấu thị trường |

Báo cáo có thể công bố theo kỳ 1/kỳ 2 và có cột **cộng dồn đến hết kỳ báo cáo**. Dataset chuẩn hoá về tháng dương lịch như sau:

- Giá trị tháng `M` = trị giá cộng dồn cuối `M` trừ trị giá cộng dồn cuối `M-1`.
- Tháng 1 lấy trực tiếp từ số cộng dồn cuối tháng 1.
- Nếu có bản cập nhật số hồi tố cho một kỳ đã lưu, dữ liệu của tháng đó được ghi phiên bản mới, thay thế aggregate cũ chỉ sau khi qua đối chiếu.
- Một kỳ chỉ được phát hành khi có đủ tổng XK, tổng NK và những bảng cần thiết cho chart tương ứng. Phần thị trường có thể chờ riêng, và chart sẽ ghi rõ tình trạng thay vì bịa số `Khác`.

Không suy diễn từ tăng trưởng phần trăm, bài viết báo chí, hoặc nguồn bên thứ ba.

## 3. Chuẩn hoá và mapping

### 3.1 Schema lưu trữ

Raw record có các trường tối thiểu: `month`, `direction` (`export`/`import`), `dimension` (`total`/`commodity`/`partner`), `source_label`, `value_usd`, `cumulative_value_usd`, `source_url`, `published_at`, `downloaded_at`, `source_sha256` và `revision_id`.

Derived record dùng `month`, `direction`, `dimension`, `bucket`, `value_usd`, `source_url`, `revision_id`. Các file aggregate JSON chỉ được sinh từ derived record đã kiểm tra.

### 3.2 Nhóm ngành do owner duyệt

| Chiều | Nhóm hiển thị |
|---|---|
| Xuất khẩu | Hàng điện tử; Chế biến chế tạo; Dệt may, giày dép; Nông nghiệp; Gỗ và sản phẩm từ gỗ; Khác |
| Nhập khẩu | Linh kiện hàng điện tử; Chế biến chế tạo; Nguyên liệu dệt may, giày dép; Dầu thô và các sản phẩm từ dầu; Khác |

`data/trade/commodity_map.csv` là bảng mapping phiên bản hoá từ nhãn mặt hàng nguyên bản sang nhóm hiển thị. Chỉ các nhãn được map rõ ràng mới vào nhóm cụ thể; tất cả phần còn lại vào `Khác`. Không được map theo fuzzy matching âm thầm.

### 3.3 Nhóm thị trường do owner duyệt

Năm bucket: Trung Quốc, Mỹ, ASEAN, EU, Khác. `data/trade/partner_map.csv` nêu rõ quốc gia/vùng lãnh thổ và bucket; ASEAN/EU được định nghĩa bằng danh sách thành viên theo bảng mapping, có hiệu lực theo tháng nếu cần xử lý thay đổi thành viên. `Khác` là tổng các đối tác còn lại, không phải một quốc gia chưa nhận diện.

## 4. Giao diện

Thêm port/tab cấp cao **Xuất nhập khẩu VN**, không là tab con của Hải Phòng hoặc TP.HCM. Bộ lọc chung gồm khoảng thời gian, chiều thương mại, và picker nhóm ngành/thị trường. Picker có **Chọn tất cả** và **Ẩn tất cả** nhưng từng mục có thể được bật lại độc lập.

| Chart | Dạng | Nội dung |
|---|---|---|
| 1 | Line chart | Tổng XK và NK theo tháng; lựa chọn trị giá hoặc YoY |
| 2 | Stacked column | Xuất khẩu theo nhóm ngành |
| 3 | Stacked column | Nhập khẩu theo nhóm ngành |
| 4 | Stacked column | Xuất khẩu theo thị trường |
| 5 | Stacked column | Nhập khẩu theo thị trường |

Tooltip hiển thị trị giá, tỷ trọng trong tổng của chiều tương ứng, YoY khi có đủ cùng kỳ năm trước, và link nguồn. Header ghi kỳ số liệu mới nhất cho từng lớp dữ liệu. Tất cả biểu đồ dùng monthly flow, không dùng số cộng dồn trừ khi tương lai có lựa chọn riêng.

## 5. Pipeline và lưu trữ

Thêm package `scraper/trade/` gồm:

- `discover.py`: tìm tệp báo cáo mới từ kho chính thức, không dựa vào một URL cố định.
- `fetch.py`: tải có retry, kiểm tra content type/kích thước/checksum và cache raw PDF.
- `parse.py`: trích bảng PDF và chuẩn hoá tiền tệ/nhãn/kỳ.
- `normalize.py`: chuyển cumulative thành monthly flow, áp mapping ngành/quốc gia.
- `store.py`: upsert raw/derived records theo tháng và revision.
- `build.py`: tạo JSON nhẹ cho dashboard.
- `daily.py`: orchestration độc lập, không khiến crawl lịch tàu thất bại chỉ vì báo cáo Hải quan bị trễ.

Dữ liệu sống trong `data/trade/`: raw metadata, mapping CSV, dataset chuẩn hoá theo năm/tháng, aggregates và `manifest.json`. PDF gốc chỉ giữ khi kích thước hợp lý; nếu không commit được vào Pages/repo thì giữ checksum + URL bất biến, còn derived data vẫn phải tái tạo được từ URL đó. File Excel/PDF nguồn không được tải về trình duyệt khách; Pages chỉ phục vụ aggregate JSON.

Workflow hàng ngày chạy sau crawl các cảng. Nó chỉ commit các tháng có thay đổi đã được kiểm tra; do dữ liệu phân mảnh theo tháng, update một tháng không làm phình lịch sử git.

## 6. Kiểm soát chất lượng và lỗi

Các invariant bắt buộc trước khi publish:

1. Không trùng `(month, direction, dimension, source_label, revision_id)`.
2. Tổng ngành không vượt tổng kim ngạch cùng tháng/cùng chiều; phần không map được được cộng rõ vào `Khác`.
3. Tổng thị trường phải reconcile với tổng kim ngạch theo sai số làm tròn công bố; không đủ đối tác thì trạng thái chart là `chưa hoàn chỉnh`.
4. Cumulative phải không âm; monthly delta âm chỉ được chấp nhận khi báo cáo nguồn có revision và được ghi lý do.
5. Không ghi 0 cho một kỳ parser không đọc được hoặc báo cáo chưa phát hành.
6. Cảnh báo khi `Khác` thay đổi bất thường, mapping mất nhãn cũ, hoặc PDF đổi cấu trúc.

Parser không nhận diện được cột/bảng bắt buộc phải fail rõ ràng, giữ dữ liệu đã publish trước đó và để workflow báo lỗi. Không có fallback sang số tổng từ tin bài.

## 7. Kiểm thử và nghiệm thu

- Fixture PDF đại diện cho XK, NK, bảng đối tác, tháng 1 và một tháng có revision.
- Unit test parse số Việt/Anh, tiêu đề bảng, cumulative-to-monthly, mapping nhóm, `Khác`, union ASEAN/EU và ngưỡng reconcile.
- Integration test: build JSON, dashboard tải đủ 5 chart và thể hiện trạng thái thiếu dữ liệu đúng.
- Backfill 01/2023 đến tháng công bố mới nhất; spot-check tối thiểu 3 tháng/năm với PDF gốc.
- CI chạy toàn bộ test cũ + trade tests; một lỗi trade không được làm hỏng dữ liệu lịch tàu hoặc deployment đang sống.

## 8. Ngoài phạm vi lần này

- Dữ liệu theo doanh nghiệp, HS code, tỉnh/thành, cảng, phương thức vận tải hoặc sản lượng vật lý.
- Dự báo thương mại, nhận định đầu tư tự động, hoặc so sánh với dữ liệu bên thứ ba.
- Cập nhật bán nguyệt/tuần; phiên bản đầu tiên lấy kỳ tháng chính thức.
