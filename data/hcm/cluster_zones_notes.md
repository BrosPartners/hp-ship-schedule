# Phân vùng cụm cảng TP.HCM

`cluster_zones.csv` chia 28 cụm thành 4 khu, tương tự cách `berth_map.csv` của
Hải Phòng chia `lach_huyen` / `ha_nguon` / `thuong_nguon`.

Zone được suy ra ở tầng tổng hợp (`scraper/hcm/aggregate.py`) chứ **không** ghi
vào Parquet, vì zone là hàm thuần của `cluster` - thứ đã có sẵn trong dữ liệu.
Nhờ vậy sửa file này chỉ cần chạy lại aggregate, không phải remap 44 partition
như khi sửa `cluster`.

| Zone | Nghĩa | Đối chiếu Hải Phòng |
|---|---|---|
| `cai_mep` | Cụm nước sâu Cái Mép - Thị Vải - Phú Mỹ | ~ `lach_huyen` |
| `song_sai_gon` | Cảng sông trong TP.HCM (Cát Lái, SP-ITC, TC Hiệp Phước) | ~ `ha_nguon` |
| `song_soai_rap` | Cảng sông Soài Rạp / Long An | ~ `thuong_nguon` |
| `vung_tau` | Vùng nước Vũng Tàu: neo, phao dầu khí, dịch vụ dầu khí | không có tương đương |

## Những chỗ tôi tự phán đoán, cần owner xác nhận

- **Phú Mỹ xếp vào `cai_mep`.** Phú Mỹ nằm trên sông Thị Vải, thường được gộp
  chung cụm "Cái Mép - Thị Vải" trong thống kê ngành. Nếu bạn muốn tách riêng
  thì đổi thành một zone mới, con số của `cai_mep` sẽ giảm tương ứng (Phú Mỹ
  chiếm khoảng 10 bến).
- **Ba Son và Đông Xuyên xếp vào `vung_tau`.** Hai cụm này chỉ xuất hiện từ
  08/2025 cùng nhóm Vũng Tàu (xem `source_coverage.csv`), nên nhiều khả năng là
  cơ sở ở Bà Rịa - Vũng Tàu chứ không phải Ba Son cũ trong nội thành TP.HCM.
- **Long An để riêng thành `song_soai_rap`** thay vì gộp vào `song_sai_gon`, vì
  đây là luồng khác và thuộc tỉnh khác.

Cụm thuộc `vung_tau` phần lớn là phao dầu khí và vùng neo, **không có sản lượng
container**, nên chúng chỉ xuất hiện ở chart lượt tàu chứ không có ở chart TEU.

Một cụm không khai báo trong file sẽ hiện là `(chưa xếp)` chứ không bị bỏ khỏi
chart - im lặng bỏ đi là cách một cụm mới biến mất mà không ai biết.

## Cụm đã loại khỏi dữ liệu

- **Ba Son** (`CẦU CẢNG SỐ 2 - BA SON`, 196 lượt, 0,5% tổng): owner yêu cầu bỏ.
  Đặt `type=external` trong `berth_map.csv` thay vì xoá hẳn dòng map, để tên thô
  vẫn được nhận diện và không quay lại trong `unmapped_report.csv` như một vị
  trí lạ. `throughput_rows` chỉ đếm `to_type == "berth"` nên cụm này biến khỏi
  mọi chart. Sửa xong phải chạy `python -m tools.remap_berths --dataset hcm
  --apply` vì `type` được ghi cứng vào Parquet.
