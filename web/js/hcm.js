// TP.HCM tab. Cùng bộ lọc với tab Hải Phòng (lọc theo khu, chọn từng cụm,
// chọn kỳ), nhưng chiều phân tích chính là `cluster` chứ không phải bến, và
// không có chart độ trượt kế hoạch vì nguồn TP.HCM chỉ có một bản kế hoạch.
import { loadJSONFrom, loadManifest, partialMonth } from "./data.js";
import { initTeu, teuCharts, teuControlsHtml } from "./teu.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";
const AGG = "data/hcm/agg";

const CHARTS = [
  ["h1", "1. Lượt di chuyển & tổng DWT theo tháng"],
  ["h2", "2. Thị phần theo cụm cảng"],
  ["h3", "3. Lượt tàu theo ngày (heatmap)"],
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

function pct(cur, prev) {
  if (cur == null || prev == null || !prev) return null;
  return +((100 * (cur - prev)) / prev).toFixed(1);
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
  return `<span class="${cls}">${v > 0 ? "+" : ""}${v}%</span>`;
}

// Bảng tổng lượt tàu theo tháng + %MoM/%YoY dưới heatmap (chart 3) - giống
// hệt bảng dưới chart 4 (Hải Phòng), xem ghi chú ở web/js/analysis.js. Tháng
// chưa tròn tháng chỉ so với đúng N ngày đầu của tháng/kỳ so sánh.
function monthlyGrowthHtml(rows, partial) {
  if (!rows.length) return `<p class="note">Không có cụm nào được chọn.</p>`;
  const byDate = new Map(rows.map((r) => [r.date, r.calls]));
  const monthsUniq = [...new Set(rows.map((r) => r.date.slice(0, 7)))].sort();
  const sumMonth = (month, maxDay) => {
    let s = 0;
    for (const [date, calls] of byDate) {
      if (!date.startsWith(month)) continue;
      if (maxDay && Number(date.slice(8, 10)) > maxDay) continue;
      s += calls;
    }
    return s;
  };
  const prevMonth = (month) => {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(y, m - 2, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  };
  const prevYear = (month) => {
    const [y, m] = month.split("-").map(Number);
    return `${y - 1}-${String(m).padStart(2, "0")}`;
  };
  const rowsOut = monthsUniq.slice().reverse().map((month) => {
    const isPartial = partial && !partial.complete && month === partial.month;
    const dayCap = isPartial ? partial.days : null;
    return {
      month, partial: isPartial, days: dayCap,
      total: sumMonth(month, dayCap),
      mom: pct(sumMonth(month, dayCap), sumMonth(prevMonth(month), dayCap)),
      yoy: pct(sumMonth(month, dayCap), sumMonth(prevYear(month), dayCap)),
    };
  });
  return `
    <p class="note" style="margin-top:6px">Tổng lượt tàu theo tháng, %MoM (so tháng
      trước) và %YoY (so cùng kỳ năm trước). Tháng chưa tròn tháng chỉ so với
      đúng số ngày tương ứng của tháng/kỳ so sánh (ghi rõ ở cột Tháng).</p>
    <div class="growth-table-wrap"><table class="grid growth-table" id="h3-growth-table">
      <thead><tr><th>Tháng</th><th class="num">Tổng lượt tàu</th>
        <th class="num">%MoM</th><th class="num">%YoY</th></tr></thead>
      <tbody>${rowsOut.map((r) => `<tr>
        <td>${r.month}${r.partial ? ` (${r.days} ngày đầu)` : ""}</td>
        <td class="num">${r.total.toLocaleString("vi-VN")}</td>
        <td class="num">${fmtPct(r.mom)}</td>
        <td class="num">${fmtPct(r.yoy)}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
}

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
  const [volume, cluster, coverage, teu, zoneShare, daily, manifest] = await Promise.all([
    loadJSONFrom(AGG, "monthly_volume"), loadJSONFrom(AGG, "cluster_share"),
    loadJSONFrom(AGG, "coverage"), loadJSONFrom(AGG, "teu"),
    loadJSONFrom(AGG, "zone_share"), loadJSONFrom(AGG, "daily_heatmap"),
    loadManifest("hcm"),
  ]);
  const partial = partialMonth(manifest.last_plan_date);
  const partialNote = partial && !partial.complete
    ? `<p class="note partial-note">⚠ Dữ liệu cập nhật tới <b>${partial.lastDate}</b>.
       Tháng <b>${partial.monthLabel}</b> mới có ${partial.days}/${partial.daysInMonth}
       ngày nên <b>chưa đủ tháng</b> - điểm/cột cuối cùng luôn thấp hơn thực tế,
       đừng đọc thành sụt giảm. Vùng tô xám trên biểu đồ 1 là tháng đó.</p>`
    : `<p class="note">Dữ liệu cập nhật tới <b>${partial?.lastDate ?? "—"}</b>.</p>`;
  const zoneOf = new Map(cluster.rows.map((r) => [r.cluster, r.zone]));

  root.innerHTML = `
    <div class="filters">
      <label>Chỉ tiêu<select id="h-metric">
        <option value="calls">Lượt tàu</option>
        <option value="dwt">Tổng DWT</option>
      </select></label>
    </div>
    ${partialNote}
    ${CHARTS.map(([id, title]) => `
      <div class="chart-head">
        <h3>${title}</h3>
        <span><button data-png="${id}">Tải PNG</button>
              <button data-csv="${id}">Tải data</button></span>
      </div>
      ${id === "h1" ? `
      <div class="filters" id="h1-controls">
        <span class="quick">Chọn nhanh:
          ${ZONE_ORDER.filter((z) => z !== "chua_xep").map((z) =>
            `<button type="button" data-h1-zone="${z}">${ZONE_LABELS[z].split(" (")[0]}</button>`).join("")}
          <button type="button" id="h1-all">Chọn tất cả</button>
          <button type="button" id="h1-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="h1-clusters"></div>` : ""}
      ${id === "h2" ? zoneToggles("h2") : ""}
      ${id === "h3" ? `
      <div class="filters" id="h3-controls">
        <span class="quick">Chọn nhanh:
          ${ZONE_ORDER.filter((z) => z !== "chua_xep").map((z) =>
            `<button type="button" data-h3-zone="${z}">${ZONE_LABELS[z].split(" (")[0]}</button>`).join("")}
          <button type="button" id="h3-all">Chọn tất cả</button>
          <button type="button" id="h3-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="h3-clusters"></div>` : ""}
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
      ${id === "h3" ? `<div id="h3-growth"></div>` : ""}
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
  const years = [...new Set(months.map((m) => m.slice(0, 4)))].sort();

  function draw() {
    const metric = document.getElementById("h-metric").value;

    // Chart 1 - tổng theo tháng, cộng từ cluster_share thay vì monthly_volume
    // để lọc được tới từng cụm. Hai nguồn lệch nhau đúng phần bị mốc phủ dữ
    // liệu loại ra (xem source_coverage.csv), và phần đó thì không nên vẽ.
    const picked1 = new Set([...root.querySelectorAll(".h1-cluster:checked")]
      .map((cb) => cb.value));
    const rows1 = cluster.rows.filter((r) => picked1.has(r.cluster));
    const byMonth1 = {};
    for (const r of rows1) byMonth1[r.month] = (byMonth1[r.month] ?? 0) + r[metric];
    csvData.h1 = rows1;
    chart("h1").setOption({
      tooltip: { trigger: "axis" }, grid: { left: 80, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value" },
      series: [{ name: metric === "calls" ? "Lượt tàu" : "Tổng DWT",
                 type: "line", smooth: true, areaStyle: {},
                 data: months.map((m) => byMonth1[m] ?? 0),
                 // Trục X ở đây là "YYYY-MM" (khác chart 1 bên Hải Phòng dùng
                 // "T1".."T12"), nên mốc vùng tô là chính khoá tháng.
                 markArea: (partial && !partial.complete) ? {
                   silent: true,
                   itemStyle: { color: "rgba(0,0,0,0.06)" },
                   label: {
                     show: true, position: "insideTop", fontSize: 10, color: "#888",
                     formatter: `chưa đủ tháng\n(${partial.days}/${partial.daysInMonth} ngày)`,
                   },
                   data: [[{ xAxis: partial.month }, { xAxis: partial.month }]],
                 } : undefined }],
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

    // Chart 3 - calendar heatmap, một khối lịch mỗi năm, giống chart 5 (chart
    // "4." trên UI) của Hải Phòng. daily.rows là một dòng/(ngày, cụm); cộng
    // theo đúng các cụm đang chọn trước khi vẽ.
    const picked3 = new Set([...root.querySelectorAll(".h3-cluster:checked")]
      .map((cb) => cb.value));
    const rows3 = daily.rows.filter((r) => picked3.has(r.cluster));
    const byDate3 = new Map();
    for (const r of rows3) {
      byDate3.set(r.date, (byDate3.get(r.date) ?? 0) + r.calls);
    }
    csvData.h3 = rows3;
    const daily3 = [...byDate3.entries()].map(([date, calls]) => ({ date, calls }));
    const max3 = Math.max(1, ...daily3.map((r) => r.calls));
    chart("h3").setOption({
      tooltip: { formatter: (p) => `${p.value[0]}: ${p.value[1]} lượt` },
      visualMap: { min: 0, max: max3, orient: "horizontal", left: "center", top: 0 },
      calendar: years.map((y, i) => ({
        range: y, top: 60 + i * 130, left: 60, right: 20, cellSize: ["auto", 13],
      })),
      series: years.map((y, i) => ({
        type: "heatmap", coordinateSystem: "calendar", calendarIndex: i,
        data: daily3.filter((r) => r.date.startsWith(y))
                    .map((r) => [r.date, r.calls]),
      })),
    });
    document.getElementById("h3").style.height = `${80 + years.length * 130}px`;
    chart("h3").resize();
    document.getElementById("h3-growth").innerHTML = monthlyGrowthHtml(daily3, partial);

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
  for (const n of ["h2", "h4"]) {
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

  // Chart 1 và chart 3 dùng lại đúng danh sách cụm của chart 5, chỉ khác
  // tiền tố lớp.
  document.getElementById("h1-clusters").innerHTML =
    document.getElementById("h5-clusters").innerHTML
      .replaceAll('class="h5-cluster"', 'class="h1-cluster"');
  document.getElementById("h3-clusters").innerHTML =
    document.getElementById("h5-clusters").innerHTML
      .replaceAll('class="h5-cluster"', 'class="h3-cluster"');

  const h1Boxes = () => [...root.querySelectorAll(".h1-cluster")];
  h1Boxes().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("h1-all").addEventListener("click", () => {
    h1Boxes().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("h1-none").addEventListener("click", () => {
    h1Boxes().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-h1-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      h1Boxes().forEach((cb) => {
        cb.checked = zoneOf.get(cb.value) === btn.dataset.h1Zone;
      });
      draw();
    }));

  const h3Boxes = () => [...root.querySelectorAll(".h3-cluster")];
  h3Boxes().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("h3-all").addEventListener("click", () => {
    h3Boxes().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("h3-none").addEventListener("click", () => {
    h3Boxes().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-h3-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      h3Boxes().forEach((cb) => {
        cb.checked = zoneOf.get(cb.value) === btn.dataset.h3Zone;
      });
      draw();
    }));

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
