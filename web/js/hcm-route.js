// Tab Tuyến của TP.HCM. KHÔNG có tuyến cảng đi/đến thật - xem ghi chú dưới.
// Chart duy nhất ở đây là tỷ trọng cờ tàu (flag of convenience) theo tháng,
// một proxy rất yếu và không nên bị đọc thành tuyến hàng hải.
import { loadJSONFrom } from "./data.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";
const AGG = "data/hcm/agg";

const NOTE = `
  <h3>Chưa dựng được tuyến cho TP.HCM</h3>
  <p class="note">
    Bản đồ tuyến của Hải Phòng dựng được là nhờ lịch tàu Cảng vụ Hải Phòng
    ghi thẳng tên nước ở đầu đi/đầu đến của mỗi lượt (ví dụ
    <code>CHINA → NAM DINH VU</code>).
    <br><br>
    Bảng lịch tàu của Cảng vụ TP.HCM <b>không có cột cảng đi hay cảng
    đến</b>. Các cột họ công bố là: tên tàu, quốc tịch, hô hiệu, DWT,
    chiều dài, mớn nước, loại hàng hoá, <b>vị trí neo đậu</b>, giờ dự kiến,
    tàu lai, đại lý, tuyến luồng. Toàn bộ 47.396 giá trị vị trí đều là bến
    trong cảng, không có giá trị nào là tên nước. Đã dò thêm các mục khác
    trên trang Cảng vụ TP.HCM (vị trí tàu tại cảng, tuyến hoạt động cố định,
    tra cứu giấy phép rời cảng...) - không mục nào có cảng đích; "tuyến hoạt
    động cố định" chỉ dành cho ghe/sà lan thủy nội địa, không phải tàu biển.
    <br><br>
    Muốn có tab này cho TP.HCM cần một nguồn khác có cảng đi/cảng đến
    (dữ liệu hãng tàu, khai báo hải quan theo chuyến, hoặc AIS).
  </p>
  <h3>Tạm thay bằng: tỷ trọng cờ tàu theo tháng</h3>
  <p class="note geo-msg warn">
    ⚠ Đây <b>KHÔNG phải tuyến hàng hải</b>. Cột "quốc tịch" trong dữ liệu là
    <b>cờ tàu</b> (nơi tàu đăng ký), không phải cảng đi/đến - phần lớn tàu
    cờ Panama/Liberia/Marshall Islands không hề đi các nước đó, đây là
    "cờ thuận tiện" (flag of convenience), một quy ước hàng hải phổ biến
    không liên quan tới hải trình thực tế. Chart dưới chỉ cho biết tỷ trọng
    tàu Việt Nam so với tàu nước ngoài (và vài cờ phổ biến nhất) theo thời
    gian, không suy ra được tàu đi/đến nước nào.
  </p>`;

export async function initHcmRoute(root) {
  root.innerHTML = NOTE + `<div class="chart-head">
      <h4>Tỷ trọng cờ tàu theo tháng (lượt cập bến)</h4>
      <span><button data-png="hr1">Tải PNG</button>
            <button data-csv="hr1">Tải data</button></span>
    </div>
    <div class="chart" id="hr1"></div>`;

  const [mix] = await Promise.all([loadJSONFrom(AGG, "nationality_mix")]);
  const echarts = await import(ECHARTS);
  const chart = echarts.init(document.getElementById("hr1"));

  const months = [...new Set(mix.rows.map((r) => r.month))].sort();
  // Sắp "Khác" xuống cuối, còn lại theo tổng lượt giảm dần - cờ phổ biến
  // nhất (thường là VIỆT NAM) vẽ trước để lên đầu legend.
  const totals = new Map();
  for (const r of mix.rows) {
    totals.set(r.nationality, (totals.get(r.nationality) ?? 0) + r.calls);
  }
  const flags = [...totals.keys()].filter((f) => f !== "Khác")
    .sort((a, b) => totals.get(b) - totals.get(a));
  if (totals.has("Khác")) flags.push("Khác");

  const byKey = new Map(mix.rows.map((r) => [`${r.month}|${r.nationality}`, r.calls]));
  const monthTotals = new Map();
  for (const r of mix.rows) {
    monthTotals.set(r.month, (monthTotals.get(r.month) ?? 0) + r.calls);
  }

  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { type: "scroll" }, grid: { left: 70, right: 20 },
    xAxis: { type: "category", data: months },
    yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
    series: flags.map((f) => ({
      name: f, type: "line", stack: "s", areaStyle: {},
      emphasis: { focus: "series" },
      data: months.map((m) => {
        const total = monthTotals.get(m) ?? 0;
        return total ? +((100 * (byKey.get(`${m}|${f}`) ?? 0)) / total).toFixed(2) : 0;
      }),
    })),
  });

  document.querySelector('[data-png="hr1"]').addEventListener("click", () => {
    const url = chart.getDataURL({ pixelRatio: 2, backgroundColor: "#fff" });
    const a = document.createElement("a");
    a.href = url; a.download = "hr1.png"; a.click();
  });
  document.querySelector('[data-csv="hr1"]').addEventListener("click", () => {
    const rows = mix.rows;
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    const csv = [cols.join(","), ...rows.map((r) =>
      cols.map((c) => `"${String(r[c] ?? "")}"`).join(","))].join("\n");
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "hr1.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  window.addEventListener("resize", () => chart.resize());
}
