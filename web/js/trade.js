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
  ["tr6", "6. Xuất khẩu một số mặt hàng chủ lực"],
  ["tr7", "7. Nhập khẩu một số mặt hàng chủ lực"],
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

// Mặt hàng chủ lực xem riêng lẻ (chart 6/7) - không phải mọi mặt hàng đều có
// cả hai chiều XK/NK (VD Việt Nam không có dòng xuất khẩu riêng cho khí đốt
// hoá lỏng hay dược phẩm trong bảng nguồn), nên hai order khác nhau.
const ITEM_LABELS = {
  than: "Than", dau_tho: "Dầu thô", xang_dau: "Xăng dầu",
  khi_dot_hoa_long: "Khí đốt hóa lỏng", giay: "Giấy các loại",
  may_vi_tinh_dien_tu: "Máy vi tính, sản phẩm điện tử và linh kiện",
  dien_thoai: "Điện thoại các loại và linh kiện",
  dien_gia_dung: "Hàng điện gia dụng và linh kiện", duoc_pham: "Dược phẩm",
};
const ITEM_ORDER_XK = ["than", "dau_tho", "xang_dau", "giay",
                       "may_vi_tinh_dien_tu", "dien_thoai", "dien_gia_dung"];
const ITEM_ORDER_NK = ["than", "dau_tho", "xang_dau", "khi_dot_hoa_long", "giay",
                       "may_vi_tinh_dien_tu", "dien_thoai", "dien_gia_dung",
                       "duoc_pham"];

function yoy(rows, idx, key) {
  if (idx < 12 || !rows[idx - 12]) return null;
  const prev = rows[idx - 12][key];
  return prev ? +((100 * (rows[idx][key] - prev)) / prev).toFixed(1) : null;
}

function pct(cur, prev) {
  if (cur == null || prev == null || !prev) return null;
  return +((100 * (cur - prev)) / prev).toFixed(1);
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
  return `<span class="${cls}">${v > 0 ? "+" : ""}${v}%</span>`;
}

function fmtVal(v, div) {
  return v === null || v === undefined ? "—" : (v / div).toFixed(2);
}

// Bảng tăng trưởng liệt kê MỌI tháng (không chỉ tháng mới nhất) - mỗi tháng
// một khối "Nhóm x Giá trị/%MoM/%YoY" (cộng dòng Tổng nếu có >1 nhóm và
// truyền totalLabel). %MoM/%YoY của một tháng luôn so với tháng liền trước/
// cùng kỳ năm ngoái lấy từ TOÀN BỘ lịch sử tháng của nhóm đó (`rows`), không
// phải từ danh sách tháng đang hiển thị theo bộ lọc "Kỳ" - nếu không, lọc về
// một năm đơn lẻ sẽ làm mất luôn tháng liền trước/cùng kỳ để so.
function groupGrowthHtml(id, rows, groups, labels, shownMonths, div, unitLabel, totalLabel) {
  if (!groups.length) return `<p class="note">Chưa chọn nhóm nào để tính tăng trưởng.</p>`;
  const monthsFull = [...new Set(rows.map((r) => r.month))].sort();
  const monthIdx = new Map(monthsFull.map((m, i) => [m, i]));
  const byKey = new Map(rows.map((r) => [`${r.month}|${r.group}`, r.usd]));
  const val = (g, m) => (m ? byKey.get(`${m}|${g}`) : undefined);
  const shownSet = new Set(shownMonths);
  const monthsShown = monthsFull.filter((m) => shownSet.has(m)).slice().reverse();

  const lines = [];
  for (const m of monthsShown) {
    const i = monthIdx.get(m);
    const prevM = i >= 1 ? monthsFull[i - 1] : null;
    const yoyM = i >= 12 ? monthsFull[i - 12] : null;
    for (const g of groups) {
      lines.push({
        month: m, label: labels[g], value: val(g, m),
        mom: pct(val(g, m), val(g, prevM)), yoy: pct(val(g, m), val(g, yoyM)),
      });
    }
    if (totalLabel && groups.length > 1) {
      const sum = (mm) => (mm ? groups.reduce((s, g) => s + (val(g, mm) ?? 0), 0) : null);
      const cur = sum(m);
      lines.push({ month: m, label: totalLabel, value: cur, isTotal: true,
                   mom: pct(cur, sum(prevM)), yoy: pct(cur, sum(yoyM)) });
    }
  }
  return `
    <div class="growth-table-wrap"><table class="grid growth-table" id="${id}-growth-table">
      <thead><tr><th>Tháng</th><th>${groups.length > 1 || totalLabel ? "Nhóm" : "Chỉ tiêu"}</th>
        <th class="num">Giá trị (${unitLabel})</th>
        <th class="num">%MoM (so tháng trước)</th>
        <th class="num">%YoY (so cùng kỳ năm trước)</th></tr></thead>
      <tbody>${lines.map((r) => `<tr${r.isTotal ? ' class="total"' : ""}>
        <td>${r.month}</td>
        <td>${r.label}</td>
        <td class="num">${fmtVal(r.value, div)}</td>
        <td class="num">${fmtPct(r.mom)}</td>
        <td class="num">${fmtPct(r.yoy)}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
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
  // Tên biến khớp đúng thứ tự fetch bên dưới - lần trước từng bị đảo (gx/cx
  // gán nhầm giữa commodity và country) khiến chart 2/3 vẽ nhầm dữ liệu nước
  // còn chart 4/5 vẽ nhầm dữ liệu mặt hàng, chỉ lộ ra khi so số thực tế.
  const [monthly, commodityExport, commodityImport, countryExport, countryImport,
         itemExport, itemImport] = await Promise.all([
      loadJSONFrom(AGG, "monthly"), loadJSONFrom(AGG, "commodity_export"),
      loadJSONFrom(AGG, "commodity_import"), loadJSONFrom(AGG, "country_export"),
      loadJSONFrom(AGG, "country_import"), loadJSONFrom(AGG, "commodity_items_export"),
      loadJSONFrom(AGG, "commodity_items_import"),
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
      ${id === "tr6" ? pickerHtml("tr6", ITEM_ORDER_XK, ITEM_LABELS) : ""}
      ${id === "tr7" ? pickerHtml("tr7", ITEM_ORDER_NK, ITEM_LABELS) : ""}
      <div class="chart" id="${id}"></div>
      <div id="${id}-growth"></div>`).join("")}
    <p class="note">
      Nguồn: bảng "Trị giá và mặt hàng xuất/nhập khẩu" và "Kim ngạch XNK phân
      theo nước, khối nước" (Tổng cục Thống kê/Hải quan), owner tải file Excel
      về và cập nhật vào repo hằng tháng. Số liệu mang nhãn <b>Sơ bộ</b> và có
      thể được cơ quan thống kê điều chỉnh lại ở kỳ công bố sau. Khối EU/ASEAN
      lấy trực tiếp từ dòng tổng khối do chính nguồn tính sẵn, không phải tự
      cộng từng nước. Nhóm hàng và nhóm nước còn lại là cách tự gộp từ ~50-90
      mặt hàng/nước liệt kê riêng - xem
      <code>data/trade/commodity_map_xls.csv</code> và
      <code>country_map_xls.csv</code> để đổi cách gộp. Chart 6/7 lấy thẳng
      từ dòng mặt hàng gốc (không qua gộp nhóm) cho một số mặt hàng owner
      quan tâm; mặt hàng nào không có dòng riêng ở chiều xuất hoặc nhập thì
      không xuất hiện ở chart đó - xem danh sách trong
      <code>scraper/trade/build_xls.py</code> (<code>WATCH_ITEMS</code>).
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

    {
      // Chart 1 không có "Tổng" (Xuất+Nhập cộng lại không có ý nghĩa kinh tế
      // rõ ràng như cán cân thương mại), nên gọi groupGrowthHtml không kèm
      // totalLabel. Chuyển monthly.rows (một dòng/tháng, 2 cột export/import)
      // sang dạng "dài" (một dòng/tháng/nhóm) để dùng chung hàm với chart 2-7.
      const longRows = monthly.rows.flatMap((r) => [
        { month: r.month, group: "export", usd: r.export },
        { month: r.month, group: "import", usd: r.import },
      ]);
      document.getElementById("tr1-growth").innerHTML = groupGrowthHtml(
        "tr1", longRows, ["export", "import"],
        { export: "Xuất khẩu", import: "Nhập khẩu" }, shownMonths, div, unitLabel, null);
    }

    // Bảng tăng trưởng dùng chung cho chart 2-7: luôn tính MoM/YoY trên TOÀN
    // BỘ lịch sử tháng của data.rows (chỉ lọc theo nhóm đang tick, KHÔNG lọc
    // theo "Kỳ" khi so sánh) - xem ghi chú ở groupGrowthHtml(). Hàng hiển thị
    // vẫn theo `shownMonths` (tôn trọng bộ lọc "Kỳ").
    const renderGrowthTable = (id, data, groups, labels, totalLabel) => {
      const rows = data.rows.filter((r) => groups.includes(r.group));
      document.getElementById(`${id}-growth`).innerHTML =
        groupGrowthHtml(id, rows, groups, labels, shownMonths, div, unitLabel, totalLabel);
    };

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
      renderGrowthTable(id, data, groups, labels, "Tổng (các nhóm hiển thị)");
    };

    stacked("tr2", commodityExport, COMMODITY_ORDER_XK, COMMODITY_LABELS, "tr2");
    stacked("tr3", commodityImport, COMMODITY_ORDER_NK, COMMODITY_LABELS, "tr3");
    stacked("tr4", countryExport, COUNTRY_ORDER_XK, COUNTRY_LABELS, "tr4");
    stacked("tr5", countryImport, COUNTRY_ORDER_NK, COUNTRY_LABELS, "tr5");

    // Chart 6/7 - mặt hàng chủ lực chênh lệch quy mô rất lớn (máy vi tính
    // ~12 tỷ USD/tháng so với than ~30 triệu), nên vẽ đường riêng từng mặt
    // hàng thay vì cột chồng - chồng cột sẽ làm mặt hàng nhỏ biến mất.
    const lines = (id, data, order, labels, prefix) => {
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
          name: labels[g], type: "line",
          data: shownMonths.map((m) => {
            const v = byKey.get(`${m}|${g}`);
            return v === undefined ? null : +(v / div).toFixed(2);
          }),
        })),
      }, true);
      renderGrowthTable(id, data, groups, labels, "Tổng (các mặt hàng hiển thị)");
    };
    lines("tr6", itemExport, ITEM_ORDER_XK, ITEM_LABELS, "tr6");
    lines("tr7", itemImport, ITEM_ORDER_NK, ITEM_LABELS, "tr7");
  }

  for (const prefix of ["tr2", "tr3", "tr4", "tr5", "tr6", "tr7"]) {
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
