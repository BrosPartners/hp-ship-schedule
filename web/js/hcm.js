// TP.HCM tab. Deliberately simpler than js/analysis.js (Hai Phong): three
// charts instead of seven, no ticker/zone filtering, no plan-slippage
// equivalent. The owner has not asked for feature parity between the two
// ports, and a smaller honest tab beats a padded one.
import { loadJSONFrom } from "./data.js";
import { initTeu, teuCharts, teuControlsHtml } from "./teu.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";
const AGG = "data/hcm/agg";

const CHARTS = [
  ["h1", "1. Lượt di chuyển & tổng DWT theo tháng"],
  ["h2", "2. Thị phần theo cụm cảng (cluster)"],
  ["h3", "3. Cỡ tàu bình quân theo tháng"],
  ...teuCharts("ht", 4),
];

export async function initHcm(root) {
  root.innerHTML = `<p>Đang tải số liệu tổng hợp TP.HCM…</p>`;
  const echarts = await import(ECHARTS);
  const [volume, cluster, size, coverage, teu] = await Promise.all([
    loadJSONFrom(AGG, "monthly_volume"), loadJSONFrom(AGG, "cluster_share"),
    loadJSONFrom(AGG, "vessel_size"), loadJSONFrom(AGG, "coverage"),
    loadJSONFrom(AGG, "teu"),
  ]);

  root.innerHTML = `
    <div class="filters">
      <label>Chỉ tiêu<select id="h-metric">
        <option value="calls">Lượt tàu</option>
        <option value="dwt">Tổng DWT</option>
      </select></label>
    </div>
    ${CHARTS.map(([id, title]) => `
      <div class="chart-head">
        <h3>${title}</h3>
        <span><button data-png="${id}">Tải PNG</button>
              <button data-csv="${id}">Tải data</button></span>
      </div>
      ${id === "ht-vol" ? teuControlsHtml("ht") : ""}
      <div class="chart" id="${id}"></div>
      ${id === "ht-dwt" ? `<p class="note">
        Nguồn: Hiệp hội Cảng biển Việt Nam (VPA). ${teu.derived_note}
        Chỉ 4 cụm có số container đối chiếu được (Cát Lái, Cái Mép, SP-ITC,
        Tân Cảng Hiệp Phước); Vũng Tàu, Phú Mỹ, Long An và các phao dầu khí
        không có sản lượng container nên không xuất hiện ở đây. Cái Mép lấy
        dòng tổng khu vực Cái Mép - Thị Vải của VPA vì cụm này gộp toàn bộ
        TCIT/TCTT/CMIT/SSIT/Gemalink.
      </p>` : ""}`).join("")}
    <h3>Ghi chú độ phủ dữ liệu</h3>
    <p>
      <b>${coverage.unmapped_pct_all}%</b> tổng số lượt (và
      <b>${coverage.unmapped_pct_30d}%</b> trong 30 ngày gần nhất) có vị trí
      đi/đến chưa map được vào bến/cụm cảng nào, nên không nằm trong bất kỳ
      biểu đồ nào ở trên.
    </p>
    <p>
      Số liệu thông qua (lượt tàu) ở đây <b>chỉ tính tàu vào (tàu_vao) và
      tàu di chuyển (tau_di_chuyen) có điểm đến là bến cảng thương mại</b>.
      Tàu rời cảng không được tính (để tránh đếm trùng một lượt tàu ở cả hai
      chiều). Lượt neo đậu (phao neo, vùng nước chờ) và lượt phục vụ công
      trình (nạo vét, đổ bùn thải, lấn biển) bị loại khỏi số thông qua vì đây
      không phải lượt cập cầu bến thương mại - kế hoạch tàu TP.HCM có rất
      nhiều tàu nạo vét/xà lan công trình mà Hải Phòng không có, nên nếu tính
      cả sẽ làm phóng đại đáng kể sản lượng thông qua thực tế.
    </p>
  `;

  const inst = {};
  const csvData = {};
  const chart = (id) => (inst[id] ??= echarts.init(document.getElementById(id)));
  const months = [...new Set(volume.rows.map((r) => r.month))].sort();

  function draw() {
    const metric = document.getElementById("h-metric").value;

    // Chart 1 - monthly totals
    csvData.h1 = volume.rows;
    chart("h1").setOption({
      tooltip: { trigger: "axis" }, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value" },
      series: [{ name: metric === "calls" ? "Lượt tàu" : "Tổng DWT",
                 type: "line", smooth: true, areaStyle: {},
                 data: months.map((m) => volume.rows.find((r) => r.month === m)?.[metric] ?? 0) }],
    });

    // Chart 2 - cluster share, 100% stacked area
    const clusters = [...new Set(cluster.rows.map((r) => r.cluster))];
    const totals = {};
    for (const r of cluster.rows) totals[r.month] = (totals[r.month] ?? 0) + r[metric];
    csvData.h2 = cluster.rows;
    chart("h2").setOption({
      tooltip: { trigger: "axis" }, legend: { type: "scroll" },
      grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: clusters.map((c) => ({
        name: c, type: "line", stack: "s", areaStyle: {},
        emphasis: { focus: "series" },
        data: months.map((m) => {
          const hit = cluster.rows.find((r) => r.month === m && r.cluster === c);
          const total = totals[m] ?? 0;
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    });

    // Chart 3 - average vessel size by month
    csvData.h3 = size.monthly;
    chart("h3").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: size.monthly.map((r) => r.month) },
      yAxis: [{ type: "value", name: "DWT bình quân" },
              { type: "value", name: "m", position: "right" }],
      series: [
        { name: "DWT bình quân", type: "line",
          data: size.monthly.map((r) => r.dwt_avg) },
        { name: "LOA bình quân (m)", type: "line", yAxisIndex: 1,
          data: size.monthly.map((r) => r.loa_avg) },
        { name: "Mớn nước bình quân (m)", type: "line", yAxisIndex: 1,
          data: size.monthly.map((r) => r.draft_avg) },
      ],
    });

    drawTeu();
  }

  root.querySelectorAll("[data-png]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const url = chart(btn.dataset.png).getDataURL({ pixelRatio: 2,
                                                      backgroundColor: "#fff" });
      const a = document.createElement("a");
      a.href = url; a.download = `${btn.dataset.png}.png`; a.click();
    }));

  root.querySelectorAll("[data-csv]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const rows = csvData[btn.dataset.csv] ?? [];
      if (!rows.length) return;
      const cols = Object.keys(rows[0]);
      const csv = [cols.join(","), ...rows.map((r) =>
        cols.map((c) => `"${String(r[c] ?? "")}"`).join(","))].join("\n");
      const url = URL.createObjectURL(
        new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${btn.dataset.csv}.csv`; a.click();
      URL.revokeObjectURL(url);
    }));

  const drawTeu = initTeu({ root, echarts, teu, prefix: "ht", chart, csvData,
                            redraw: () => drawTeu() });

  document.getElementById("h-metric").addEventListener("change", draw);
  window.addEventListener("resize", () =>
    Object.values(inst).forEach((c) => c.resize()));
  draw();
}
