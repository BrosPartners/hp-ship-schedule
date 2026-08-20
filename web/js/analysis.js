import { loadJSON, loadManifest, partialMonth } from "./data.js";
import { initTeu, teuCharts, teuControlsHtml } from "./teu.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";

const CHARTS = [
  ["c1", "1. Lượt tàu & tổng DWT theo tháng (so YoY)"],
  ["c2", "2. Thị phần theo bến / doanh nghiệp"],
  ["c4", "3. Mix tuyến nội địa vs quốc tế"],
  ["c5", "4. Lượt tàu theo ngày (heatmap)"],
  ["c7", "5. Dịch chuyển theo khu vực"],
  ["c8", "6. Lượt tàu / tổng DWT theo từng cảng, theo tháng"],
  ...teuCharts("t", 7),
];

const ZONE_LABELS = {
  lach_huyen: "Lạch Huyện",
  ha_nguon: "Hạ nguồn (Đình Vũ)",
  thuong_nguon: "Thượng nguồn (sông Cấm)",
  unmapped: "(chưa map)",
};
const ZONE_ORDER = ["thuong_nguon", "ha_nguon", "lach_huyen", "unmapped"];

function pct(cur, prev) {
  if (cur == null || prev == null || !prev) return null;
  return +((100 * (cur - prev)) / prev).toFixed(1);
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
  return `<span class="${cls}">${v > 0 ? "+" : ""}${v}%</span>`;
}

// Bảng tổng lượt tàu theo tháng + %MoM/%YoY, dưới heatmap (chart 5). `rows`
// là danh sách {date, calls} đã cộng theo đúng các bến đang chọn. Tháng mới
// nhất chưa tròn tháng (`partial`) thì so với đúng N ngày đầu của tháng liền
// trước / cùng kỳ năm ngoái - so full tháng trước với vài ngày của tháng này
// sẽ luôn ra sụt giảm giả, không phản ánh đúng tốc độ tăng trưởng.
function monthlyGrowthHtml(rows, partial) {
  if (!rows.length) return `<p class="note">Không có bến nào được chọn.</p>`;
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
    <div class="growth-table-wrap"><table class="grid growth-table" id="c5-growth-table">
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

export async function initAnalysis(root) {
  root.innerHTML = `<p>Đang tải số liệu tổng hợp…</p>`;
  const echarts = await import(ECHARTS);
  const [volume, share, mix, daily, zoneShare, teu, manifest] = await Promise.all([
    loadJSON("monthly_volume"), loadJSON("berth_share"), loadJSON("route_mix"),
    loadJSON("daily_heatmap"), loadJSON("zone_share"), loadJSON("teu"),
    loadManifest("hp"),
  ]);
  const partial = partialMonth(manifest.last_plan_date);
  const partialNote = partial && !partial.complete
    ? `<p class="note partial-note">⚠ Dữ liệu cập nhật tới <b>${partial.lastDate}</b>.
       Tháng <b>${partial.monthLabel}</b> mới có ${partial.days}/${partial.daysInMonth}
       ngày nên <b>chưa đủ tháng</b> - điểm/cột cuối cùng luôn thấp hơn thực tế,
       đừng đọc thành sụt giảm. Vùng tô xám trên biểu đồ 1 là tháng đó.</p>`
    : `<p class="note">Dữ liệu cập nhật tới <b>${partial?.lastDate ?? "—"}</b>.</p>`;

  root.innerHTML = `
    <div class="filters">
      <label>Chỉ tiêu<select id="a-metric">
        <option value="calls">Lượt tàu</option>
        <option value="dwt">Tổng DWT</option>
      </select></label>
      <label>Lọc mã CK<select id="a-ticker"><option value="">Tất cả</option></select></label>
    </div>
    ${partialNote}
    ${CHARTS.map(([id, title]) => `
      <div class="chart-head">
        <h3>${title}</h3>
        <span><button data-png="${id}">Tải PNG</button>
              <button data-csv="${id}">Tải data</button></span>
      </div>
      ${id === "c1" ? `
      <div class="filters" id="c1-controls">
        <span class="quick">Chọn nhanh:
          <button type="button" data-c1-zone="lach_huyen">Lạch Huyện</button>
          <button type="button" data-c1-zone="ha_nguon">Đình Vũ</button>
          <button type="button" data-c1-zone="thuong_nguon">Sông Cấm</button>
          <button type="button" id="c1-all">Chọn tất cả</button>
          <button type="button" id="c1-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="c1-berths"></div>` : ""}
      ${id === "c5" ? `
      <div class="filters" id="c5-controls">
        <span class="quick">Chọn nhanh:
          <button type="button" data-c5-zone="lach_huyen">Lạch Huyện</button>
          <button type="button" data-c5-zone="ha_nguon">Đình Vũ</button>
          <button type="button" data-c5-zone="thuong_nguon">Sông Cấm</button>
          <button type="button" id="c5-all">Chọn tất cả</button>
          <button type="button" id="c5-none">Ẩn tất cả</button>
        </span>
      </div>
      <div class="filters berth-picker" id="c5-berths"></div>` : ""}
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
      ${id === "c5" ? `<div id="c5-growth"></div>` : ""}
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

    // Chart 1 - monthly totals, one series per calendar year for YoY reading.
    // Cộng từ berth_share thay vì monthly_volume để lọc được theo bến; hai
    // nguồn bằng nhau khi chọn hết vì cùng đi ra từ throughput_rows.
    const years = [...new Set(months.map((m) => m.slice(0, 4)))].sort();
    const picked1 = new Set([...root.querySelectorAll(".c1-berth:checked")]
      .map((cb) => cb.value));
    const rows1 = share.rows.filter((r) => picked1.has(r.berth)
      && (!ticker || r.ticker === ticker));
    const byMonth = {};
    for (const r of rows1) {
      byMonth[r.month] = (byMonth[r.month] ?? 0) + r[metric];
    }
    csvData.c1 = rows1;
    chart("c1").setOption({
      tooltip: { trigger: "axis" }, legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category",
               data: Array.from({ length: 12 }, (_, i) => `T${i + 1}`) },
      yAxis: { type: "value" },
      series: years.map((y, si) => ({
        name: y, type: "line", smooth: true,
        data: Array.from({ length: 12 }, (_, i) =>
          byMonth[`${y}-${String(i + 1).padStart(2, "0")}`] ?? null),
        // Chỉ gắn vùng tô một lần (series đầu) - gắn ở mọi series thì ECharts
        // vẽ chồng 4 lớp, vùng xám đậm dần lên trông như lỗi.
        markArea: (si === 0 && partial && !partial.complete) ? {
          silent: true,
          itemStyle: { color: "rgba(0,0,0,0.06)" },
          label: {
            show: true, position: "insideTop", fontSize: 10, color: "#888",
            formatter: `chưa đủ tháng\n(${partial.days}/${partial.daysInMonth} ngày)`,
          },
          data: [[{ xAxis: partial.axisLabel }, { xAxis: partial.axisLabel }]],
        } : undefined,
      })),
    }, true);

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

    // Chart 5 - calendar heatmap, one calendar block per year. daily.rows is
    // one row per (date, berth); sum the picked berths' calls per day so the
    // filter behaves like chart 1/8's berth picker.
    const picked5 = new Set([...root.querySelectorAll(".c5-berth:checked")]
      .map((cb) => cb.value));
    const rows5 = daily.rows.filter((r) => picked5.has(r.berth));
    const byDate5 = new Map();
    for (const r of rows5) {
      byDate5.set(r.date, (byDate5.get(r.date) ?? 0) + r.calls);
    }
    csvData.c5 = rows5;
    const daily5 = [...byDate5.entries()].map(([date, calls]) => ({ date, calls }));
    const max = Math.max(1, ...daily5.map((r) => r.calls));
    chart("c5").setOption({
      tooltip: { formatter: (p) => `${p.value[0]}: ${p.value[1]} lượt` },
      visualMap: { min: 0, max, orient: "horizontal", left: "center", top: 0 },
      calendar: years.map((y, i) => ({
        range: y, top: 60 + i * 130, left: 60, right: 20, cellSize: ["auto", 13],
      })),
      series: years.map((y, i) => ({
        type: "heatmap", coordinateSystem: "calendar", calendarIndex: i,
        data: daily5.filter((r) => r.date.startsWith(y))
                    .map((r) => [r.date, r.calls]),
      })),
    });
    document.getElementById("c5").style.height = `${80 + years.length * 130}px`;
    chart("c5").resize();
    document.getElementById("c5-growth").innerHTML = monthlyGrowthHtml(daily5, partial);

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

  // Chart 1 và chart 5 dùng lại đúng danh sách bến của chart 8, chỉ khác
  // tiền tố lớp.
  document.getElementById("c1-berths").innerHTML =
    document.getElementById("c8-berths").innerHTML
      .replaceAll('class="c8-berth"', 'class="c1-berth"');
  document.getElementById("c5-berths").innerHTML =
    document.getElementById("c8-berths").innerHTML
      .replaceAll('class="c8-berth"', 'class="c5-berth"');

  const c1Berths = () => [...root.querySelectorAll(".c1-berth")];
  c1Berths().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("c1-all").addEventListener("click", () => {
    c1Berths().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("c1-none").addEventListener("click", () => {
    c1Berths().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-c1-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      c1Berths().forEach((cb) => {
        cb.checked = berthZone.get(cb.value) === btn.dataset.c1Zone;
      });
      draw();
    }));

  const c5Berths = () => [...root.querySelectorAll(".c5-berth")];
  c5Berths().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("c5-all").addEventListener("click", () => {
    c5Berths().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("c5-none").addEventListener("click", () => {
    c5Berths().forEach((cb) => { cb.checked = false; }); draw();
  });
  root.querySelectorAll("[data-c5-zone]").forEach((btn) =>
    btn.addEventListener("click", () => {
      c5Berths().forEach((cb) => {
        cb.checked = berthZone.get(cb.value) === btn.dataset.c5Zone;
      });
      draw();
    }));

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
