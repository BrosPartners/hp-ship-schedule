// Tab Xuất nhập khẩu Việt Nam. Nguồn: PDF hải quan (customs.gov.vn), không có
// bản Excel. Năm chart đúng như owner đã tự vẽ tay: tổng theo tháng, XK/NK
// theo nhóm hàng, XK/NK theo nhóm nước.
import { loadJSONFrom } from "./data.js";

const ECHARTS =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.esm.min.js";
const AGG = "data/trade/agg";

const CHARTS = [
  ["tr1", "1. Trị giá xuất, nhập khẩu theo tháng"],
  ["tr2", "2. Xuất khẩu theo nhóm hàng"],
  ["tr3", "3. Nhập khẩu theo nhóm hàng"],
  ["tr4", "4. Xuất khẩu theo nhóm nước"],
  ["tr5", "5. Nhập khẩu theo nhóm nước"],
];

const COMMODITY_LABELS = {
  dien_tu: "Hàng điện tử", che_bien_che_tao: "Chế biến chế tạo",
  det_may_giay_dep: "Dệt may, giày dép", nong_nghiep: "Nông nghiệp",
  go: "Gỗ & sản phẩm từ gỗ", khac: "Khác",
  linh_kien_dien_tu: "Linh kiện hàng điện tử",
  nguyen_lieu_det_may: "Nguyên liệu dệt may, giày dép",
  dau_tho: "Dầu thô và các sản phẩm từ dầu",
};
const COMMODITY_ORDER_XK = ["dien_tu", "che_bien_che_tao", "det_may_giay_dep",
                            "nong_nghiep", "go", "khac"];
const COMMODITY_ORDER_NK = ["linh_kien_dien_tu", "che_bien_che_tao",
                            "nguyen_lieu_det_may", "dau_tho", "khac"];

const COUNTRY_LABELS = {
  trung_quoc: "Trung Quốc", my: "Mỹ", asean: "Asean", eu: "EU", khac: "Khác",
  an_do_dai_loan_han_nhat: "Ấn Độ, Đài Loan, Hàn Quốc, Nhật Bản",
};
const COUNTRY_ORDER_XK = ["trung_quoc", "my", "asean", "eu", "khac"];
const COUNTRY_ORDER_NK = ["trung_quoc", "my", "asean", "eu",
                          "an_do_dai_loan_han_nhat", "khac"];

function yoy(rows, idx, key) {
  if (idx < 12 || !rows[idx - 12]) return null;
  const prev = rows[idx - 12][key];
  return prev ? +((100 * (rows[idx][key] - prev)) / prev).toFixed(1) : null;
}

function pickerHtml(prefix, groups, labels) {
  return `<div class="filters berth-picker" id="${prefix}-picker">
    ${groups.map((g) =>
      `<label><input type="checkbox" class="${prefix}-group" value="${g}" checked> ${labels[g]}</label>`
    ).join("")}
    <button type="button" id="${prefix}-all">Chọn tất cả</button>
    <button type="button" id="${prefix}-none">Ẩn tất cả</button>
  </div>`;
}

export async function initTrade(root) {
  root.innerHTML = `<p>Đang tải số liệu xuất nhập khẩu…</p>`;
  const [monthly, cx, cn, gx, gn] = await Promise.all([
    loadJSONFrom(AGG, "monthly"), loadJSONFrom(AGG, "commodity_export"),
    loadJSONFrom(AGG, "commodity_import"), loadJSONFrom(AGG, "country_export"),
    loadJSONFrom(AGG, "country_import"),
  ]);

  root.innerHTML = `
    <div class="filters">
      <label>Đơn vị<select id="tr-unit">
        <option value="1e9">Tỷ USD</option>
        <option value="1e6">Triệu USD</option>
      </select></label>
      <label>Kỳ<select id="tr-year"></select></label>
    </div>
    ${CHARTS.map(([id, title]) => `
      <div class="chart-head">
        <h3>${title}</h3>
        <span><button data-png="${id}">Tải PNG</button>
              <button data-csv="${id}">Tải data</button></span>
      </div>
      ${id === "tr2" ? pickerHtml("tr2", COMMODITY_ORDER_XK, COMMODITY_LABELS) : ""}
      ${id === "tr3" ? pickerHtml("tr3", COMMODITY_ORDER_NK, COMMODITY_LABELS) : ""}
      ${id === "tr4" ? pickerHtml("tr4", COUNTRY_ORDER_XK, COUNTRY_LABELS) : ""}
      ${id === "tr5" ? pickerHtml("tr5", COUNTRY_ORDER_NK, COUNTRY_LABELS) : ""}
      <div class="chart" id="${id}"></div>`).join("")}
    <p class="note">
      Nguồn: Tổng cục Hải quan Việt Nam (customs.gov.vn), biểu "Xuất/Nhập khẩu
      theo nước-vùng lãnh thổ x mặt hàng chủ yếu", công bố hằng tháng dưới dạng
      PDF - cổng hải quan không phát hành bản Excel. Số liệu mang nhãn
      <b>Sơ bộ</b> và có thể được hải quan điều chỉnh lại ở kỳ công bố sau; bản
      mới hơn sẽ đè lên bản cũ khi chạy lại pipeline. Nhóm hàng và nhóm nước là
      cách tự gộp từ ~50 mặt hàng chủ yếu và ~89 nước hải quan liệt kê riêng -
      xem <code>data/trade/commodity_map.csv</code> và
      <code>country_map.csv</code> để đổi cách gộp.
    </p>
  `;

  const inst = {};
  const csvData = {};
  const chart = (id) => (inst[id] ??= echarts.init(document.getElementById(id)));
  const months = monthly.rows.map((r) => r.month);
  const echarts = await import(ECHARTS);

  const yearSel = document.getElementById("tr-year");
  yearSel.insertAdjacentHTML("beforeend", `<option value="">Toàn bộ</option>`);
  for (const y of [...new Set(months.map((m) => m.slice(0, 4)))].sort().reverse()) {
    yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
  }

  function draw() {
    const div = Number(document.getElementById("tr-unit").value);
    const unitLabel = div === 1e9 ? "Tỷ USD" : "Triệu USD";
    const year = yearSel.value;
    const idx = months.map((m, i) => i).filter((i) => !year || months[i].startsWith(year));
    const shownMonths = idx.map((i) => months[i]);

    // Chart 1 - trị giá XK/NK, kèm nhãn %YoY như bản owner tự vẽ.
    csvData.tr1 = monthly.rows;
    chart("tr1").setOption({
      tooltip: { trigger: "axis", valueFormatter: (v) => `${v.toFixed(2)} ${unitLabel}` },
      legend: {}, grid: { left: 70, right: 20 },
      xAxis: { type: "category", data: shownMonths },
      yAxis: { type: "value", name: unitLabel },
      series: ["export", "import"].map((key) => ({
        name: key === "export" ? "Xuất khẩu" : "Nhập khẩu", type: "bar",
        data: idx.map((i) => +(monthly.rows[i][key] / div).toFixed(2)),
        label: idx.length <= 20 ? {
          show: true, position: "top", fontSize: 9,
          formatter: (p) => {
            const y = yoy(monthly.rows, idx[p.dataIndex], key);
            return y === null ? "" : `${y > 0 ? "+" : ""}${y}%`;
          },
        } : undefined,
      })),
    }, true);

    // Chart 2-5: bốn chart cùng một khuôn - cột chồng theo nhóm, lọc bằng
    // checkbox riêng từng chart, giống cách chart 2/8 bên tab Hải Phòng.
    const stacked = (id, data, order, labels, prefix) => {
      const picked = new Set([...root.querySelectorAll(`.${prefix}-group:checked`)]
        .map((cb) => cb.value));
      const rows = data.rows.filter((r) => picked.has(r.group)
        && (!year || r.month.startsWith(year)));
      const byKey = new Map(rows.map((r) => [`${r.month}|${r.group}`, r.usd]));
      const groups = order.filter((g) => picked.has(g));
      csvData[id] = rows;
      chart(id).setOption({
        tooltip: { trigger: "axis", valueFormatter: (v) => `${v.toFixed(2)} ${unitLabel}` },
        legend: {}, grid: { left: 70, right: 20 },
        xAxis: { type: "category", data: shownMonths },
        yAxis: { type: "value", name: unitLabel },
        series: groups.map((g) => ({
          name: labels[g], type: "bar", stack: "s",
          data: shownMonths.map((m) =>
            +((byKey.get(`${m}|${g}`) ?? 0) / div).toFixed(2)),
        })),
      }, true);
    };

    stacked("tr2", gx, COMMODITY_ORDER_XK, COMMODITY_LABELS, "tr2");
    stacked("tr3", gn, COMMODITY_ORDER_NK, COMMODITY_LABELS, "tr3");
    stacked("tr4", cx, COUNTRY_ORDER_XK, COUNTRY_LABELS, "tr4");
    stacked("tr5", cn, COUNTRY_ORDER_NK, COUNTRY_LABELS, "tr5");
  }

  for (const prefix of ["tr2", "tr3", "tr4", "tr5"]) {
    const boxes = () => [...root.querySelectorAll(`.${prefix}-group`)];
    boxes().forEach((cb) => cb.addEventListener("change", draw));
    document.getElementById(`${prefix}-all`).addEventListener("click", () => {
      boxes().forEach((cb) => { cb.checked = true; }); draw();
    });
    document.getElementById(`${prefix}-none`).addEventListener("click", () => {
      boxes().forEach((cb) => { cb.checked = false; }); draw();
    });
  }
  document.getElementById("tr-unit").addEventListener("change", draw);
  yearSel.addEventListener("change", draw);

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
        cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))
      ].join("\n");
      const url = URL.createObjectURL(
        new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${btn.dataset.csv}.csv`; a.click();
      URL.revokeObjectURL(url);
    }));

  window.addEventListener("resize", () =>
    Object.values(inst).forEach((c) => c.resize()));
  draw();
}
