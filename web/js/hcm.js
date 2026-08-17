// TP.HCM tab. Cùng bộ lọc với tab Hải Phòng (lọc theo khu, chọn từng cụm,
// chọn kỳ), nhưng chiều phân tích chính là `cluster` chứ không phải bến, và
// không có chart độ trượt kế hoạch vì nguồn TP.HCM chỉ có một bản kế hoạch.
import { loadJSONFrom } from "./data.js";
import { initTeu, teuCharts, teuControlsHtml } from "./teu.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";
const AGG = "data/hcm/agg";

const CHARTS = [
  ["h1", "1. Lượt di chuyển & tổng DWT theo tháng"],
  ["h2", "2. Thị phần theo cụm cảng"],
  ["h3", "3. Cỡ tàu bình quân theo tháng"],
  ["h4", "4. Dịch chuyển theo khu vực"],
  ["h5", "5. Lượt tàu / tổng DWT theo từng cụm, theo tháng"],
  ...teuCharts("ht", 6),
];

const ZONE_LABELS = {
  cai_mep: "Cái Mép - Thị Vải (nước sâu)",
  song_sai_gon: "Sông Sài Gòn (Cát Lái, SP-ITC…)",
  song_soai_rap: "Sông Soài Rạp (Long An)",
  vung_tau: "Vũng Tàu (neo, phao dầu khí)",
  chua_xep: "(chưa xếp khu)",
};
const ZONE_ORDER = ["song_sai_gon", "song_soai_rap", "cai_mep", "vung_tau",
                    "chua_xep"];

function zoneToggles(prefix) {
  return `<div class="filters" id="${prefix}-zone-filters">
    ${ZONE_ORDER.map((z) =>
      `<label><input type="checkbox" class="${prefix}-zone" value="${z}" checked>
       ${ZONE_LABELS[z]}</label>`).join("")}
    <button type="button" id="${prefix}-all">Chọn tất cả</button>
    <button type="button" id="${prefix}-none">Ẩn tất cả</button>
  </div>`;
}

export async function initHcm(root) {
  root.innerHTML = `<p>Đang tải số liệu tổng hợp TP.HCM…</p>`;
  const echarts = await import(ECHARTS);
  const [volume, cluster, size, coverage, teu, zoneShare] = await Promise.all([
    loadJSONFrom(AGG, "monthly_volume"), loadJSONFrom(AGG, "cluster_share"),
    loadJSONFrom(AGG, "vessel_size"), loadJSONFrom(AGG, "coverage"),
    loadJSONFrom(AGG, "teu"), loadJSONFrom(AGG, "zone_share"),
  ]);
  const zoneOf = new Map(cluster.rows.map((r) => [r.cluster, r.zone]));

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
      ${id === "h1" ? zoneToggles("h1") : ""}
      ${id === "h2" ? zoneToggles("h2") : ""}
      ${id === "h4" ? zoneToggles("h4") : ""}
      ${id === "h5" ? `
      <div class="filters" id="h5-controls">
        <label>Chỉ tiêu<select id="h5-metric">
          <option value="calls">Lượt tàu</option>
          <option value="dwt">Tổng DWT</option>
        </select></label>
        <label>Kỳ<select id="h5-year"></select></label>
        <span class="quick">
          ${ZONE_ORDER.filter((z) => z !== "chua_xep").map((z) =>
            `<button type="button" data-h5-zone="${z}">${ZONE_LABELS[z].split(" (")[0]}</button>`).join("")}
          <button type="button" id="h5-all">Chọn tất cả</button>
          <button type="button" id="h5-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="h5-clusters"></div>` : ""}
      ${id === "ht-vol" ? teuControlsHtml("ht") : ""}
      <div class="chart" id="${id}"></div>
      ${id === "ht-dwt" ? `<p class="note">
        Nguồn: Hiệp hội Cảng biển Việt Nam (VPA). ${teu.derived_note}
        Chỉ những cụm có số container đối chiếu được mới xuất hiện ở đây
        (Cát Lái, SP-ITC, Tân Cảng Hiệp Phước và từng terminal Cái Mép:
        CMIT, Gemalink, TCIT, TCTT, SSIT, SP-PSA, SITV). Khu Vũng Tàu,
        Long An và các phao dầu khí không có sản lượng container nên không
        có mặt.
      </p>` : ""}`).join("")}
    <h3>Ghi chú độ phủ dữ liệu</h3>
    <p>
      <b>Khu Vũng Tàu - Cái Mép - Thị Vải chỉ có dữ liệu lịch tàu từ
      01/08/2025.</b> Cảng vụ TP.HCM bắt đầu đăng khu vực này sau khi Bà Rịa -
      Vũng Tàu sáp nhập vào TP.HCM; số dòng trong kế hoạch ngày nhảy từ ~120
      lên ~210 đúng ngày đó. Các cụm thuộc khu này (Cái Mép, Phú Mỹ, Vũng Tàu,
      Vietsovpetro...) vì vậy <b>không xuất hiện trước mốc trên</b> - đây là
      thiếu dữ liệu, không phải sản lượng bằng 0. Sản lượng container (TEU) từ
      VPA thì vẫn đủ từ 2023, nên chart TEU chạy dài hơn chart lượt tàu; tỷ lệ
      TEU/lượt tàu chỉ tính từ 08/2025 cho khu này. Cát Lái, SP-ITC và Tân
      Cảng Hiệp Phước không bị ảnh hưởng.
    </p>
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

    // Chart 1 - tổng theo tháng, cộng từ zone_share thay vì monthly_volume để
    // lọc được theo khu. Hai nguồn lệch nhau đúng phần bị mốc phủ dữ liệu loại
    // ra (xem source_coverage.csv), và phần đó thì không nên vẽ.
    const zones1 = [...root.querySelectorAll(".h1-zone:checked")]
      .map((cb) => cb.value);
    const rows1 = zoneShare.rows.filter((r) => zones1.includes(r.zone));
    const byMonth1 = {};
    for (const r of rows1) byMonth1[r.month] = (byMonth1[r.month] ?? 0) + r[metric];
    csvData.h1 = rows1;
    chart("h1").setOption({
      tooltip: { trigger: "axis" }, grid: { left: 80, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value" },
      series: [{ name: metric === "calls" ? "Lượt tàu" : "Tổng DWT",
                 type: "line", smooth: true, areaStyle: {},
                 data: months.map((m) => byMonth1[m] ?? 0) }],
    }, true);

    // Chart 2 - cluster share, 100% stacked area. Lọc theo khu rồi chuẩn hoá
    // lại về 100% của phần đang chọn, giống chart 2/7 bên Hải Phòng.
    const zones2 = [...root.querySelectorAll(".h2-zone:checked")]
      .map((cb) => cb.value);
    const rows2 = cluster.rows.filter((r) => zones2.includes(r.zone));
    const clusters = [...new Set(rows2.map((r) => r.cluster))];
    const totals = {};
    for (const r of rows2) totals[r.month] = (totals[r.month] ?? 0) + r[metric];
    csvData.h2 = rows2;
    chart("h2").setOption({
      tooltip: { trigger: "axis" }, legend: { type: "scroll" },
      grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: clusters.map((c) => ({
        name: c, type: "line", stack: "s", areaStyle: {},
        emphasis: { focus: "series" },
        data: months.map((m) => {
          const hit = rows2.find((r) => r.month === m && r.cluster === c);
          const total = totals[m] ?? 0;
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    }, true); // notMerge: số cụm đổi theo bộ lọc khu

    // Chart 3 - average vessel size by month
    csvData.h3 = size.monthly;
    chart("h3").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: size.monthly.map((r) => r.month) },
      grid: { left: 80, right: 120 },
      // Ba đại lượng ba thang khác nhau (DWT ~18.000, LOA ~114, mớn ~6). Mớn
      // nước có trục riêng cố định 0-20 m để đọc được thay đổi vài tấc; LOA
      // tách sang trục thứ ba thay vì dùng chung, vì 114 m sẽ bị trục 0-20 cắt.
      yAxis: [{ type: "value", name: "DWT bình quân" },
              { type: "value", name: "Mớn nước (m)", position: "right",
                min: 0, max: 20 },
              { type: "value", name: "LOA (m)", position: "right", offset: 58 }],
      series: [
        { name: "DWT bình quân", type: "line",
          data: size.monthly.map((r) => r.dwt_avg) },
        { name: "LOA bình quân (m)", type: "line", yAxisIndex: 2,
          data: size.monthly.map((r) => r.loa_avg) },
        { name: "Mớn nước bình quân (m)", type: "line", yAxisIndex: 1,
          data: size.monthly.map((r) => r.draft_avg) },
      ],
    }, true);

    // Chart 4 - thị phần theo khu, đối xứng với chart 7 của Hải Phòng
    const zones4 = [...root.querySelectorAll(".h4-zone:checked")]
      .map((cb) => cb.value);
    const rows4 = zoneShare.rows.filter((r) => zones4.includes(r.zone));
    const zTotals = {};
    for (const r of rows4) zTotals[r.month] = (zTotals[r.month] ?? 0) + r[metric];
    csvData.h4 = rows4;
    chart("h4").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: ZONE_ORDER.filter((z) => zones4.includes(z)
        && zoneShare.rows.some((r) => r.zone === z)).map((z) => ({
        name: ZONE_LABELS[z] ?? z, type: "line", stack: "s", areaStyle: {},
        emphasis: { focus: "series" },
        data: months.map((m) => {
          const hit = rows4.find((r) => r.month === m && r.zone === z);
          const total = zTotals[m] ?? 0;
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    }, true);

    // Chart 5 - số tuyệt đối từng cụm theo tháng, chọn cụm như chart 8 bên HP
    const metric5 = document.getElementById("h5-metric").value;
    const picked5 = new Set([...root.querySelectorAll(".h5-cluster:checked")]
      .map((cb) => cb.value));
    const year5 = document.getElementById("h5-year").value;
    const rows5 = cluster.rows.filter((r) => picked5.has(r.cluster)
      && (!year5 || r.month.startsWith(year5)));
    const months5 = months.filter((m) => !year5 || m.startsWith(year5));
    const tot5 = new Map();
    for (const r of rows5) {
      tot5.set(r.cluster, (tot5.get(r.cluster) ?? 0) + r[metric5]);
    }
    const shown5 = [...tot5.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
    const cell5 = new Map(rows5.map((r) => [`${r.month}|${r.cluster}`, r[metric5]]));
    csvData.h5 = rows5;
    chart("h5").setOption({
      tooltip: { trigger: "axis", order: "valueDesc" },
      legend: { type: "scroll" }, grid: { left: 80, right: 20 },
      xAxis: { type: "category", data: months5 },
      yAxis: { type: "value",
               name: metric5 === "calls" ? "Lượt tàu" : "Tổng DWT" },
      series: shown5.map((c) => ({
        name: c, type: "line", smooth: true, connectNulls: false,
        showSymbol: months5.length <= 24, emphasis: { focus: "series" },
        // Cụm chưa có dữ liệu tháng đó để null cho đứt đoạn, không điền 0:
        // khu Vũng Tàu chỉ có số từ 08/2025 (xem ghi chú độ phủ).
        data: months5.map((m) => cell5.get(`${m}|${c}`) ?? null),
      })),
    }, true);

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

  // Danh sách cụm cho chart 5, nhóm theo khu để nút chọn nhanh và cách hiển
  // thị khớp nhau.
  const allClusters = [...new Set(cluster.rows.map((r) => r.cluster))]
    .sort((a, b) => a.localeCompare(b, "vi"));
  document.getElementById("h5-clusters").innerHTML = ZONE_ORDER
    .filter((z) => allClusters.some((c) => zoneOf.get(c) === z))
    .map((z) => `<span class="zone-group"><b>${ZONE_LABELS[z]}:</b>
      ${allClusters.filter((c) => zoneOf.get(c) === z).map((c) =>
        `<label><input type="checkbox" class="h5-cluster" value="${c}" checked> ${c}</label>`
      ).join("")}</span>`).join("");

  const yearSel = document.getElementById("h5-year");
  yearSel.insertAdjacentHTML("beforeend", `<option value="">Toàn bộ</option>`);
  for (const y of [...new Set(months.map((m) => m.slice(0, 4)))].sort().reverse()) {
    yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }
  yearSel.addEventListener("change", draw);
  document.getElementById("h5-metric").addEventListener("change", draw);

  // Bộ lọc khu của chart 2 và 4 dùng chung một cách nối sự kiện.
  for (const n of ["h1", "h2", "h4"]) {
    const boxes = () => [...root.querySelectorAll(`.${n}-zone`)];
    boxes().forEach((cb) => cb.addEventListener("change", draw));
    const setAll = (checked) => {
      boxes().forEach((cb) => { cb.checked = checked; });
      draw();
    };
    document.getElementById(`${n}-all`)
      .addEventListener("click", () => setAll(true));
    document.getElementById(`${n}-none`)
      .addEventListener("click", () => setAll(false));
  }

  const h5Boxes = () => [...root.querySelectorAll(".h5-cluster")];
  h5Boxes().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("h5-all").addEventListener("click", () => {
    h5Boxes().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("h5-none").addEventListener("click", () => {
    h5Boxes().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-h5-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      h5Boxes().forEach((cb) => {
        cb.checked = zoneOf.get(cb.value) === btn.dataset.h5Zone;
      });
      draw();
    }));

  const drawTeu = initTeu({ root, echarts, teu, prefix: "ht", chart, csvData,
                            redraw: () => drawTeu() });

  document.getElementById("h-metric").addEventListener("change", draw);
  window.addEventListener("resize", () =>
    Object.values(inst).forEach((c) => c.resize()));
  draw();
}
