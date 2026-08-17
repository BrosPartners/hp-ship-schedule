import { loadJSON } from "./data.js";
import { initTeu, teuCharts, teuControlsHtml } from "./teu.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";

const CHARTS = [
  ["c1", "1. Lượt tàu & tổng DWT theo tháng (so YoY)"],
  ["c2", "2. Thị phần theo bến / doanh nghiệp"],
  ["c3", "3. Cỡ tàu bình quân & phân bố mớn nước"],
  ["c4", "4. Mix tuyến nội địa vs quốc tế"],
  ["c5", "5. Lượt tàu theo ngày (heatmap)"],
  ["c6", "6. Độ trượt kế hoạch"],
  ["c7", "7. Dịch chuyển theo khu vực"],
  ["c8", "8. Lượt tàu / tổng DWT theo từng cảng, theo tháng"],
  ...teuCharts("t", 9),
];

const ZONE_LABELS = {
  lach_huyen: "Lạch Huyện",
  ha_nguon: "Hạ nguồn (Đình Vũ)",
  thuong_nguon: "Thượng nguồn (sông Cấm)",
  unmapped: "(chưa map)",
};
const ZONE_ORDER = ["thuong_nguon", "ha_nguon", "lach_huyen", "unmapped"];

export async function initAnalysis(root) {
  root.innerHTML = `<p>Đang tải số liệu tổng hợp…</p>`;
  const echarts = await import(ECHARTS);
  const [volume, share, size, mix, daily, slip, zoneShare, teu] =
    await Promise.all([
      loadJSON("monthly_volume"), loadJSON("berth_share"), loadJSON("vessel_size"),
      loadJSON("route_mix"), loadJSON("daily_heatmap"), loadJSON("plan_slippage"),
      loadJSON("zone_share"), loadJSON("teu"),
    ]);

  root.innerHTML = `
    <div class="filters">
      <label>Chỉ tiêu<select id="a-metric">
        <option value="calls">Lượt tàu</option>
        <option value="dwt">Tổng DWT</option>
      </select></label>
      <label>Lọc mã CK<select id="a-ticker"><option value="">Tất cả</option></select></label>
    </div>
    ${CHARTS.map(([id, title]) => `
      <div class="chart-head">
        <h3>${title}</h3>
        <span><button data-png="${id}">Tải PNG</button>
              <button data-csv="${id}">Tải data</button></span>
      </div>
      ${id === "c2" ? `
      <div class="filters" id="c2-zone-filters">
        <label><input type="checkbox" class="c2-zone-toggle" value="lach_huyen" checked> Lạch Huyện</label>
        <label><input type="checkbox" class="c2-zone-toggle" value="ha_nguon" checked> Đình Vũ (hạ nguồn)</label>
        <label><input type="checkbox" class="c2-zone-toggle" value="thuong_nguon" checked> Sông Cấm (thượng nguồn)</label>
        <button type="button" id="c2-all">Chọn tất cả</button>
        <button type="button" id="c2-none">Ẩn tất cả</button>
      </div>` : ""}
      ${id === "c8" ? `
      <div class="filters" id="c8-controls">
        <label>Chỉ tiêu<select id="c8-metric">
          <option value="calls">Lượt tàu</option>
          <option value="dwt">Tổng DWT</option>
        </select></label>
        <label>Kỳ<select id="c8-year"></select></label>
        <span class="quick">Chọn nhanh:
          <button type="button" data-c8-zone="lach_huyen">Lạch Huyện</button>
          <button type="button" data-c8-zone="ha_nguon">Đình Vũ</button>
          <button type="button" data-c8-zone="thuong_nguon">Sông Cấm</button>
          <button type="button" id="c8-all">Chọn tất cả</button>
          <button type="button" id="c8-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="c8-berths"></div>` : ""}
      ${id === "c7" ? `
      <div class="filters" id="c7-zone-filters">
        <label><input type="checkbox" class="c7-zone-toggle" value="lach_huyen" checked> Lạch Huyện</label>
        <label><input type="checkbox" class="c7-zone-toggle" value="ha_nguon" checked> Hạ nguồn (Đình Vũ)</label>
        <label><input type="checkbox" class="c7-zone-toggle" value="thuong_nguon" checked> Thượng nguồn (sông Cấm)</label>
        <label><input type="checkbox" class="c7-zone-toggle" value="unmapped" checked> (chưa map)</label>
        <button type="button" id="c7-only-lach-huyen">Chỉ Lạch Huyện</button>
        <button type="button" id="c7-only-song">Chỉ cảng sông</button>
        <button type="button" id="c7-all">Chọn tất cả</button>
        <button type="button" id="c7-none">Ẩn tất cả</button>
      </div>` : ""}
      ${id === "t-vol" ? teuControlsHtml("t") : ""}
      <div class="chart" id="${id}"></div>
      ${id === "c8" ? `<div class="berth-table" id="c8-table"></div>` : ""}
      ${id === "t-dwt" ? `<p class="note">
        Nguồn: Hiệp hội Cảng biển Việt Nam (VPA), sản lượng container thông qua
        hằng tháng. ${teu.derived_note} Tháng chưa có số VPA để trống chứ không
        điền 0, nên đường bị đứt đoạn là đúng. Mẫu số (lượt tàu, DWT) đếm
        <b>mọi</b> lượt cập bến, kể cả tàu không chở container, nên các bến
        hàng tổng hợp có tỷ lệ thấp giả tạo.
        VPA gộp Chùa Vẽ và Tân Vũ thành một dòng nên hai bến này tính chung.
      </p>` : ""}`).join("")}
  `;

  const tickerSel = document.getElementById("a-ticker");
  for (const t of [...new Set(share.rows.map((r) => r.ticker))].sort()) {
    tickerSel.insertAdjacentHTML("beforeend", `<option>${t}</option>`);
  }

  const inst = {};
  const csvData = {};
  const chart = (id) => (inst[id] ??= echarts.init(document.getElementById(id)));
  const months = [...new Set(volume.rows.map((r) => r.month))].sort();

  function draw() {
    const metric = document.getElementById("a-metric").value;
    const ticker = tickerSel.value;

    // Chart 1 - monthly totals, one series per calendar year for YoY reading
    const years = [...new Set(months.map((m) => m.slice(0, 4)))].sort();
    const byMonth = Object.fromEntries(volume.rows.map((r) => [r.month, r]));
    csvData.c1 = volume.rows;
    chart("c1").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category",
               data: Array.from({ length: 12 }, (_, i) => `T${i + 1}`) },
      yAxis: { type: "value" },
      series: years.map((y) => ({
        name: y, type: "line", smooth: true,
        data: Array.from({ length: 12 }, (_, i) =>
          byMonth[`${y}-${String(i + 1).padStart(2, "0")}`]?.[metric] ?? null),
      })),
    });

    // Chart 2 - stacked share by berth
    // Zone filter behaves like chart 7's: the remaining berths renormalize to
    // 100% of the *selected* zones, so "chỉ Lạch Huyện" reads as share within
    // Lạch Huyện. Unchecking everything renders an empty chart on purpose -
    // "Ẩn tất cả" is a filter state the owner asked for, not an error.
    const zones2 = [...root.querySelectorAll(".c2-zone-toggle:checked")]
      .map((cb) => cb.value);
    const rows2 = share.rows.filter((r) =>
      (!ticker || r.ticker === ticker) && zones2.includes(r.zone ?? "unmapped"));
    const berths = [...new Set(rows2.map((r) => r.berth))];
    const totals = {};
    for (const r of rows2) totals[r.month] = (totals[r.month] ?? 0) + r[metric];
    csvData.c2 = rows2;
    chart("c2").setOption({
      tooltip: { trigger: "axis" },
      legend: { type: "scroll" }, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: berths.map((b) => ({
        name: b, type: "line", stack: "s", areaStyle: {},
        emphasis: { focus: "series" },
        data: months.map((m) => {
          const hit = rows2.find((r) => r.month === m && r.berth === b);
          const total = totals[m] ?? 0;
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    }, true); // notMerge: the berth count changes with the zone filter, so a
              // merge would leave the unselected zones' series on the chart.

    // Chart 3 - average size line plus draft distribution bars
    csvData.c3 = size.monthly;
    const bands = [...new Set(size.draft_hist.map((r) => r.band))].sort();
    chart("c3").setOption({
      tooltip: { trigger: "axis" }, legend: {},
      grid: [{ left: 70, right: 20, height: "40%" },
             { left: 70, right: 20, top: "62%", height: "28%" }],
      xAxis: [{ type: "category", data: size.monthly.map((r) => r.month) },
              { type: "category", gridIndex: 1, data: bands }],
      // Mớn nước (~6,7 m) từng nằm chung trục với DWT (~18.700) nên bị ép dẹp
      // sát đáy, không đọc được gì. Cho nó trục riêng cố định 0-20 m: thang cố
      // định để so được giữa các lần xem, và đủ rộng cho tàu sâu nhất.
      yAxis: [{ type: "value", name: "DWT bình quân" },
              { type: "value", gridIndex: 1, name: "Lượt" },
              { type: "value", name: "Mớn nước (m)", position: "right",
                min: 0, max: 20 }],
      series: [
        { name: "DWT bình quân", type: "line",
          data: size.monthly.map((r) => r.dwt_avg) },
        { name: "Mớn nước bình quân", type: "line", yAxisIndex: 2,
          data: size.monthly.map((r) => r.draft_avg) },
        { name: "Phân bố mớn nước", type: "bar", xAxisIndex: 1, yAxisIndex: 1,
          data: bands.map((b) => size.draft_hist
            .filter((r) => r.band === b)
            .reduce((sum, r) => sum + r.calls, 0)) },
      ],
    });

    // Chart 4 - domestic vs international
    csvData.c4 = mix.rows;
    chart("c4").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: [true, false].map((dom) => ({
        name: dom ? "Nội địa" : "Quốc tế", type: "line", stack: "s",
        areaStyle: {},
        data: months.map((m) => {
          const all = mix.rows.filter((r) => r.month === m);
          const total = all.reduce((s, r) => s + r[metric], 0);
          const hit = all.find((r) => r.domestic === dom);
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    });

    // Chart 5 - calendar heatmap, one calendar block per year
    csvData.c5 = daily.rows;
    const max = Math.max(1, ...daily.rows.map((r) => r.calls));
    chart("c5").setOption({
      tooltip: { formatter: (p) => `${p.value[0]}: ${p.value[1]} lượt` },
      visualMap: { min: 0, max, orient: "horizontal", left: "center", top: 0 },
      calendar: years.map((y, i) => ({
        range: y, top: 60 + i * 130, left: 60, right: 20, cellSize: ["auto", 13],
      })),
      series: years.map((y, i) => ({
        type: "heatmap", coordinateSystem: "calendar", calendarIndex: i,
        data: daily.rows.filter((r) => r.date.startsWith(y))
                        .map((r) => [r.date, r.calls]),
      })),
    });
    document.getElementById("c5").style.height = `${80 + years.length * 130}px`;
    chart("c5").resize();

    // Chart 6 - plan slippage, empty for the backfill period by construction
    csvData.c6 = slip.rows;
    chart("c6").setOption(slip.rows.length ? {
      tooltip: { trigger: "axis" }, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: slip.rows.map((r) => r.plan_date) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ name: "% đổi giờ/đổi bến", type: "bar",
                 data: slip.rows.map((r) => r.pct_changed) }],
    } : {
      title: {
        text: slip.note ?? "Chưa có dữ liệu nhiều snapshot",
        subtext: "Chỉ tiêu này bắt đầu có số từ ngày bot chạy hằng ngày; "
               + "toàn bộ giai đoạn backfill chỉ có một bản kế hoạch.",
        left: "center", top: "middle", textStyle: { fontSize: 14 },
        subtextStyle: { fontSize: 12 },
      },
    });

    // Chart 7 - zone share by month, 100% stacked area
    // Zone filter: when a subset of zones is checked, the series renormalize
    // to 100% of only the selected zones (not the unfiltered total), so the
    // chart still reads correctly as a share breakdown. Unchecking everything
    // renders an empty chart on purpose - "Ẩn tất cả" is a filter state the
    // owner asked for, not an error to be second-guessed.
    const selectedZones = [...document.querySelectorAll(".c7-zone-toggle:checked")]
      .map((cb) => cb.value);
    const zones = ZONE_ORDER.filter((z) => selectedZones.includes(z) &&
      zoneShare.rows.some((r) => r.zone === z));
    const rows7 = zoneShare.rows.filter((r) => selectedZones.includes(r.zone));
    csvData.c7 = rows7;
    const zoneTotals = {};
    for (const r of rows7) zoneTotals[r.month] = (zoneTotals[r.month] ?? 0) + r[metric];
    chart("c7").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, max: 100 },
      series: zones.map((z) => ({
        name: ZONE_LABELS[z] ?? z, type: "line", stack: "s", areaStyle: {},
        emphasis: { focus: "series" },
        data: months.map((m) => {
          const hit = rows7.find((r) => r.month === m && r.zone === z);
          const total = zoneTotals[m] ?? 0;
          return total ? +((100 * (hit?.[metric] ?? 0)) / total).toFixed(2) : 0;
        }),
      })),
    }, true); // notMerge: series count varies with the zone filter, and
              // echarts merges series by index by default, so a shrinking
              // selection would otherwise leave stale series behind.

    // Chart 8 - absolute volume per berth over time, one line per berth. No
    // share here: chart 2 already answers the share question, and this chart
    // exists to show the level. Selection is per berth (the zone buttons are
    // only shortcuts that set those checkboxes) so a one-or-two-berth
    // comparison is two clicks away from "Ẩn tất cả".
    const metric8 = document.getElementById("c8-metric").value;
    const picked8 = new Set([...root.querySelectorAll(".c8-berth:checked")]
      .map((cb) => cb.value));
    const year8 = document.getElementById("c8-year").value;
    const rows8 = share.rows.filter((r) =>
      (!ticker || r.ticker === ticker) &&
      picked8.has(r.berth) &&
      (!year8 || r.month.startsWith(year8)));
    const months8 = months.filter((m) => !year8 || m.startsWith(year8));
    // Berths ordered by total size of the plotted metric so the legend and the
    // table columns both read biggest-first.
    const totals8 = new Map();
    for (const r of rows8) {
      totals8.set(r.berth, (totals8.get(r.berth) ?? 0) + r[metric8]);
    }
    const berths8 = [...totals8.entries()].sort((a, b) => b[1] - a[1])
      .map(([b]) => b);
    const cell = new Map(rows8.map((r) => [`${r.month}|${r.berth}`, r[metric8]]));
    csvData.c8 = rows8.map((r) => ({
      month: r.month, berth: r.berth, ticker: r.ticker, zone: r.zone,
      calls: r.calls, dwt: r.dwt,
    }));
    const metricLabel = metric8 === "calls" ? "Lượt tàu" : "Tổng DWT";
    chart("c8").setOption({
      tooltip: { trigger: "axis", order: "valueDesc" },
      legend: { type: "scroll" }, grid: { left: 80, right: 20 },
      xAxis: { type: "category", data: months8 },
      yAxis: { type: "value", name: metricLabel },
      series: berths8.map((b) => ({
        name: b, type: "line", smooth: true, showSymbol: months8.length <= 24,
        emphasis: { focus: "series" },
        data: months8.map((m) => cell.get(`${m}|${b}`) ?? 0),
      })),
    }, true); // notMerge: the berth count changes with the zone filter.
    document.getElementById("c8").style.height = "420px";
    chart("c8").resize();

    const fmt = (v) => v.toLocaleString("vi-VN");
    document.getElementById("c8-table").innerHTML = berths8.length ? `
      <table class="grid">
        <thead><tr><th>Tháng</th>
          ${berths8.map((b) => `<th class="num">${b}</th>`).join("")}
          <th class="num">Tổng</th></tr></thead>
        <tbody>${months8.map((m) => {
          const vals = berths8.map((b) => cell.get(`${m}|${b}`) ?? 0);
          return `<tr><td>${m}</td>
            ${vals.map((v) => `<td class="num">${fmt(v)}</td>`).join("")}
            <td class="num">${fmt(vals.reduce((a, v) => a + v, 0))}</td></tr>`;
        }).join("")}</tbody>
        <tfoot><tr><td>Tổng</td>
          ${berths8.map((b) => `<td class="num">${fmt(totals8.get(b))}</td>`).join("")}
          <td class="num">${fmt([...totals8.values()].reduce((a, v) => a + v, 0))}</td>
        </tr></tfoot>
      </table>` : `<p>Không có bến nào được chọn.</p>`;

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

  document.getElementById("a-metric").addEventListener("change", draw);
  tickerSel.addEventListener("change", draw);

  const zoneToggles = () => [...root.querySelectorAll(".c7-zone-toggle")];
  const setZones = (values) => {
    zoneToggles().forEach((cb) => { cb.checked = values.includes(cb.value); });
    draw();
  };
  zoneToggles().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("c7-only-lach-huyen")
    .addEventListener("click", () => setZones(["lach_huyen"]));
  document.getElementById("c7-only-song")
    .addEventListener("click", () => setZones(["ha_nguon", "thuong_nguon"]));
  document.getElementById("c7-all")
    .addEventListener("click", () => setZones(ZONE_ORDER));
  document.getElementById("c7-none").addEventListener("click", () => setZones([]));

  const c2Toggles = () => [...root.querySelectorAll(".c2-zone-toggle")];
  c2Toggles().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("c2-all").addEventListener("click", () => {
    c2Toggles().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("c2-none").addEventListener("click", () => {
    c2Toggles().forEach((cb) => { cb.checked = false; }); draw();
  });

  // Chart 8 picks berths individually. The berth list is derived once from the
  // aggregate (it does not change with any filter), grouped by zone so the
  // quick-select buttons and the visual grouping agree.
  const berthZone = new Map();
  for (const r of share.rows) berthZone.set(r.berth, r.zone ?? "unmapped");
  const allBerths = [...berthZone.keys()].sort((a, b) =>
    a.localeCompare(b, "vi"));
  document.getElementById("c8-berths").innerHTML = ZONE_ORDER
    .filter((z) => allBerths.some((b) => berthZone.get(b) === z))
    .map((z) => `<span class="zone-group"><b>${ZONE_LABELS[z] ?? z}:</b>
      ${allBerths.filter((b) => berthZone.get(b) === z).map((b) =>
        `<label><input type="checkbox" class="c8-berth" value="${b}" checked> ${b}</label>`
      ).join("")}</span>`).join("");

  const c8Berths = () => [...root.querySelectorAll(".c8-berth")];
  c8Berths().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("c8-all").addEventListener("click", () => {
    c8Berths().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("c8-none").addEventListener("click", () => {
    c8Berths().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-c8-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const z = btn.dataset.c8Zone;
      c8Berths().forEach((cb) => { cb.checked = berthZone.get(cb.value) === z; });
      draw();
    }));
  document.getElementById("c8-metric").addEventListener("change", draw);

  const yearSel = document.getElementById("c8-year");
  yearSel.insertAdjacentHTML("beforeend", `<option value="">Toàn bộ</option>`);
  for (const y of [...new Set(months.map((m) => m.slice(0, 4)))].sort().reverse()) {
    yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }
  yearSel.addEventListener("change", draw);

  const drawTeu = initTeu({ root, echarts, teu, prefix: "t", chart, csvData,
                            redraw: () => drawTeu() });
  window.addEventListener("resize", () =>
    Object.values(inst).forEach((c) => c.resize()));
  draw();
}
