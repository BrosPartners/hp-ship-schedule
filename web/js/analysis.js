import { loadJSON } from "./data.js";

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
  ["c8", "8. Lượt tàu & tổng DWT theo từng cảng (kèm thị phần)"],
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
  const [volume, share, size, mix, daily, slip, zoneShare] = await Promise.all([
    loadJSON("monthly_volume"), loadJSON("berth_share"), loadJSON("vessel_size"),
    loadJSON("route_mix"), loadJSON("daily_heatmap"), loadJSON("plan_slippage"),
    loadJSON("zone_share"),
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
      <div class="filters" id="c8-zone-filters">
        <label><input type="checkbox" class="c8-zone-toggle" value="lach_huyen" checked> Lạch Huyện</label>
        <label><input type="checkbox" class="c8-zone-toggle" value="ha_nguon" checked> Đình Vũ (hạ nguồn)</label>
        <label><input type="checkbox" class="c8-zone-toggle" value="thuong_nguon" checked> Sông Cấm (thượng nguồn)</label>
        <label>Kỳ<select id="c8-year"></select></label>
        <button type="button" id="c8-all">Chọn tất cả</button>
        <button type="button" id="c8-none">Ẩn tất cả</button>
      </div>` : ""}
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
      <div class="chart" id="${id}"></div>
      ${id === "c8" ? `<div class="berth-table" id="c8-table"></div>` : ""}`).join("")}
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
      yAxis: [{ type: "value", name: "DWT bình quân" },
              { type: "value", gridIndex: 1, name: "Lượt" }],
      series: [
        { name: "DWT bình quân", type: "line",
          data: size.monthly.map((r) => r.dwt_avg) },
        { name: "Mớn nước bình quân", type: "line", yAxisIndex: 0,
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

    // Chart 8 - absolute calls and DWT per berth, with the share the owner
    // reads alongside them. Two x-axes because calls (~10^3) and DWT (~10^7)
    // cannot share a scale; the table below carries the exact figures.
    const zones8 = [...root.querySelectorAll(".c8-zone-toggle:checked")]
      .map((cb) => cb.value);
    const year8 = document.getElementById("c8-year").value;
    const rows8src = share.rows.filter((r) =>
      (!ticker || r.ticker === ticker) &&
      zones8.includes(r.zone ?? "unmapped") &&
      (!year8 || r.month.startsWith(year8)));
    const agg8 = new Map();
    for (const r of rows8src) {
      const cur = agg8.get(r.berth) ??
        { berth: r.berth, ticker: r.ticker, zone: r.zone, calls: 0, dwt: 0 };
      cur.calls += r.calls; cur.dwt += r.dwt;
      agg8.set(r.berth, cur);
    }
    // Sorted by the metric the owner picked in the top selector, so the same
    // control drives which ranking they see.
    const list8 = [...agg8.values()].sort((a, b) => a[metric] - b[metric]);
    const sumCalls = list8.reduce((a, r) => a + r.calls, 0);
    const sumDwt = list8.reduce((a, r) => a + r.dwt, 0);
    const pct = (v, total) => (total ? +((100 * v) / total).toFixed(2) : 0);
    csvData.c8 = list8.map((r) => ({
      berth: r.berth, ticker: r.ticker, zone: r.zone,
      calls: r.calls, share_calls_pct: pct(r.calls, sumCalls),
      dwt: r.dwt, share_dwt_pct: pct(r.dwt, sumDwt),
    }));
    chart("c8").setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: {}, grid: { left: 130, right: 30, top: 60,
                          height: Math.max(120, list8.length * 22) },
      xAxis: [{ type: "value", name: "Lượt tàu", position: "top" },
              { type: "value", name: "Tổng DWT", position: "bottom" }],
      yAxis: { type: "category", data: list8.map((r) => r.berth) },
      series: [
        { name: "Lượt tàu", type: "bar", xAxisIndex: 0,
          data: list8.map((r) => r.calls),
          label: { show: true, position: "right",
                   formatter: (p) => `${p.value.toLocaleString("vi-VN")} `
                     + `(${pct(p.value, sumCalls).toFixed(1)}%)` } },
        { name: "Tổng DWT", type: "bar", xAxisIndex: 1,
          data: list8.map((r) => r.dwt),
          label: { show: true, position: "right",
                   formatter: (p) => `${pct(p.value, sumDwt).toFixed(1)}%` } },
      ],
    }, true);
    document.getElementById("c8").style.height =
      `${Math.max(260, list8.length * 22 + 140)}px`;
    chart("c8").resize();

    const fmt = (v) => v.toLocaleString("vi-VN");
    document.getElementById("c8-table").innerHTML = list8.length ? `
      <table class="grid">
        <thead><tr><th>Bến</th><th>Mã CK</th><th>Lượt tàu</th><th>Thị phần lượt</th>
          <th>Tổng DWT</th><th>Thị phần DWT</th></tr></thead>
        <tbody>${[...list8].reverse().map((r) => `<tr>
          <td>${r.berth}</td><td>${r.ticker === "(không niêm yết)" ? "" : r.ticker}</td>
          <td class="num">${fmt(r.calls)}</td>
          <td class="num">${pct(r.calls, sumCalls).toFixed(2)}%</td>
          <td class="num">${fmt(r.dwt)}</td>
          <td class="num">${pct(r.dwt, sumDwt).toFixed(2)}%</td></tr>`).join("")}</tbody>
        <tfoot><tr><td>Tổng</td><td></td><td class="num">${fmt(sumCalls)}</td>
          <td class="num">100%</td><td class="num">${fmt(sumDwt)}</td>
          <td class="num">100%</td></tr></tfoot>
      </table>` : `<p>Không có bến nào được chọn.</p>`;
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

  // Chart 2 and chart 8 share the same select-all / hide-all wiring.
  for (const n of ["c2", "c8"]) {
    const toggles = () => [...root.querySelectorAll(`.${n}-zone-toggle`)];
    toggles().forEach((cb) => cb.addEventListener("change", draw));
    const setAll = (checked) => {
      toggles().forEach((cb) => { cb.checked = checked; });
      draw();
    };
    document.getElementById(`${n}-all`).addEventListener("click", () => setAll(true));
    document.getElementById(`${n}-none`).addEventListener("click", () => setAll(false));
  }

  const yearSel = document.getElementById("c8-year");
  yearSel.insertAdjacentHTML("beforeend", `<option value="">Toàn bộ</option>`);
  for (const y of [...new Set(months.map((m) => m.slice(0, 4)))].sort().reverse()) {
    yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }
  yearSel.addEventListener("change", draw);
  window.addEventListener("resize", () =>
    Object.values(inst).forEach((c) => c.resize()));
  draw();
}
