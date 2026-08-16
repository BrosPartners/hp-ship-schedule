// Sản lượng container VPA. Dùng chung cho cả tab Hải Phòng và tab TP.HCM:
// hai tab đọc hai file teu.json khác nhau nhưng schema và cách đọc giống hệt
// nhau, nên phần này ở chung một chỗ thay vì chép đôi.
export function teuCharts(prefix, from) {
  return [
    [`${prefix}-vol`, `${from}. Sản lượng container theo tháng (TEU)`],
    [`${prefix}-call`, `${from + 1}. TEU / lượt tàu cập bến`],
    [`${prefix}-dwt`, `${from + 2}. TEU / 1.000 DWT`],
  ];
}

export function teuControlsHtml(prefix) {
  return `
    <div class="filters" id="${prefix}-controls">
      <label>Kỳ<select id="${prefix}-year"></select></label>
      <span class="quick">
        <button type="button" id="${prefix}-all">Chọn tất cả</button>
        <button type="button" id="${prefix}-none">Ẩn tất cả</button>
      </span>
    </div>
    <div class="filters berth-picker" id="${prefix}-units"></div>`;
}

// TEU là sản lượng cả tháng; số tháng có ý nghĩa nên trục X luôn là toàn bộ
// các tháng có TEU, kể cả tháng chưa có dữ liệu tàu.
function monthsOf(teu) {
  return [...new Set(teu.rows.map((r) => r.month))].sort();
}

export function initTeu({ root, echarts, teu, prefix, chart, csvData, redraw }) {
  const units = teu.units;
  document.getElementById(`${prefix}-units`).innerHTML = units.map((u) =>
    `<label><input type="checkbox" class="${prefix}-unit" value="${u}" checked> ${u}</label>`
  ).join("");

  const yearSel = document.getElementById(`${prefix}-year`);
  yearSel.insertAdjacentHTML("beforeend", `<option value="">Toàn bộ</option>`);
  for (const y of [...new Set(monthsOf(teu).map((m) => m.slice(0, 4)))]
       .sort().reverse()) {
    yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }

  const picks = () => [...root.querySelectorAll(`.${prefix}-unit`)];
  picks().forEach((cb) => cb.addEventListener("change", redraw));
  yearSel.addEventListener("change", redraw);
  const setAll = (checked) => {
    picks().forEach((cb) => { cb.checked = checked; });
    redraw();
  };
  document.getElementById(`${prefix}-all`)
    .addEventListener("click", () => setAll(true));
  document.getElementById(`${prefix}-none`)
    .addEventListener("click", () => setAll(false));

  return function drawTeu() {
    const chosen = new Set(picks().filter((cb) => cb.checked)
                                  .map((cb) => cb.value));
    const year = yearSel.value;
    const months = monthsOf(teu).filter((m) => !year || m.startsWith(year));
    const rows = teu.rows.filter((r) => chosen.has(r.unit)
                                     && (!year || r.month.startsWith(year)));
    const cell = new Map(rows.map((r) => [`${r.month}|${r.unit}`, r]));
    const shown = units.filter((u) => chosen.has(u));

    // Tháng thiếu số thì trả null để đường bị đứt đoạn. Điền 0 sẽ vẽ ra một
    // cú sụp sản lượng không có thật - VPA luôn công bố trễ 1-2 tháng so với
    // dữ liệu lịch tàu.
    const series = (pick) => shown.map((u) => ({
      name: u, type: "line", smooth: true, connectNulls: false,
      showSymbol: months.length <= 24, emphasis: { focus: "series" },
      data: months.map((m) => pick(cell.get(`${m}|${u}`))),
    }));
    const axis = (name, fmt) => ({
      tooltip: { trigger: "axis", order: "valueDesc" },
      legend: { type: "scroll" }, grid: { left: 80, right: 20 },
      xAxis: { type: "category", data: months },
      yAxis: { type: "value", name, axisLabel: fmt ? { formatter: fmt } : {} },
    });

    const flat = rows.map((r) => ({
      month: r.month, unit: r.unit, teu: r.teu, derived: r.derived,
      calls: r.calls, dwt: r.dwt,
      teu_per_call: r.calls ? +(r.teu / r.calls).toFixed(1) : "",
      teu_per_1000_dwt: r.dwt ? +((1000 * r.teu) / r.dwt).toFixed(2) : "",
    }));
    for (const suffix of ["vol", "call", "dwt"]) csvData[`${prefix}-${suffix}`] = flat;
    chart(`${prefix}-vol`).setOption({
      ...axis("TEU"),
      series: series((r) => (r ? Math.round(r.teu) : null)),
    }, true);

    chart(`${prefix}-call`).setOption({
      ...axis("TEU / lượt"),
      series: series((r) => (r && r.calls ? +(r.teu / r.calls).toFixed(1) : null)),
    }, true);

    chart(`${prefix}-dwt`).setOption({
      ...axis("TEU / 1.000 DWT"),
      series: series((r) =>
        (r && r.dwt ? +((1000 * r.teu) / r.dwt).toFixed(2) : null)),
    }, true);
  };
}
