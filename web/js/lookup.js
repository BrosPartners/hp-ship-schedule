import { loadJSON, query, sqlString } from "./data.js";

const SECTION_LABELS = {
  roi_cang: "Rời cảng", di_chuyen: "Di chuyển",
  vao_cang: "Vào cảng", qua_luong: "Qua luồng",
};
const PAGE = 300;

export async function initLookup(root) {
  root.innerHTML = `<p>Đang tải dữ liệu chi tiết…</p>`;
  const filters = await loadJSON("filters");

  root.innerHTML = `
    <div class="filters">
      <label>Từ ngày<input type="date" id="f-from" value="${filters.date_min ?? ""}"></label>
      <label>Đến ngày<input type="date" id="f-to" value="${filters.date_max ?? ""}"></label>
      <label>Loại<select id="f-section">
        <option value="">Tất cả</option>
        ${filters.sections.map((s) => `<option value="${s}">${SECTION_LABELS[s]}</option>`).join("")}
      </select></label>
      <label>Bến đi<select id="f-from-berth"><option value="">Tất cả</option>
        ${filters.berths.map((b) => `<option>${b}</option>`).join("")}</select></label>
      <label>Bến đến<select id="f-to-berth"><option value="">Tất cả</option>
        ${filters.berths.map((b) => `<option>${b}</option>`).join("")}</select></label>
      <label>Mã CK<select id="f-ticker"><option value="">Tất cả</option>
        ${filters.tickers.map((t) => `<option>${t}</option>`).join("")}</select></label>
      <label>DWT từ<input type="number" id="f-dwt-min" min="0" placeholder="0"></label>
      <label>DWT đến<input type="number" id="f-dwt-max" min="0" placeholder="${filters.dwt_max}"></label>
      <label>Mớn nước từ<input type="number" id="f-draft-min" step="0.1" placeholder="0"></label>
      <label>Mớn nước đến<input type="number" id="f-draft-max" step="0.1" placeholder="${filters.draft_max}"></label>
      <label>Tên tàu<input id="f-vessel" placeholder="ví dụ: HAI AN"></label>
      <label>Đại lý<input id="f-agent" placeholder="tên đại lý"></label>
      <label>Tuyến<select id="f-domestic">
        <option value="">Tất cả</option><option value="1">Nội địa</option>
        <option value="0">Quốc tế</option></select></label>
      <label>Snapshot<select id="f-snapshot">
        <option value="latest">Chỉ bản mới nhất</option>
        <option value="all">Mọi snapshot</option></select></label>
      <button id="f-apply">Áp dụng</button>
      <button id="f-csv">Tải CSV</button>
    </div>
    <div id="count" class="badge"></div>
    <div class="scroller"><table class="grid">
      <thead><tr>
        <th>Ngày</th><th>Giờ</th><th>Loại</th><th>Tên tàu</th><th>SB</th>
        <th class="num">Mớn</th><th class="num">LOA</th>
        <th class="num">DWT</th><th class="num">GT</th>
        <th>Luồng</th><th>Từ</th><th>Đến</th><th>Bến đến</th><th>Mã CK</th>
        <th>Đại lý</th><th>Hoa tiêu</th><th>Snapshot</th>
      </tr></thead><tbody id="rows"></tbody>
    </table></div>
    <button id="more" hidden>Tải thêm ${PAGE} dòng</button>
  `;

  let offset = 0;
  let currentWhere = "";

  function where() {
    const val = (id) => document.getElementById(id).value.trim();
    const parts = [];
    if (val("f-from")) parts.push(`plan_date >= DATE ${sqlString(val("f-from"))}`);
    if (val("f-to")) parts.push(`plan_date <= DATE ${sqlString(val("f-to"))}`);
    if (val("f-section")) parts.push(`section = ${sqlString(val("f-section"))}`);
    if (val("f-from-berth")) parts.push(`from_berth = ${sqlString(val("f-from-berth"))}`);
    if (val("f-to-berth")) parts.push(`to_berth = ${sqlString(val("f-to-berth"))}`);
    if (val("f-ticker"))
      parts.push(`(from_ticker = ${sqlString(val("f-ticker"))} OR to_ticker = ${sqlString(val("f-ticker"))})`);
    if (val("f-dwt-min")) parts.push(`dwt >= ${Number(val("f-dwt-min"))}`);
    if (val("f-dwt-max")) parts.push(`dwt <= ${Number(val("f-dwt-max"))}`);
    if (val("f-draft-min")) parts.push(`draft_m >= ${Number(val("f-draft-min"))}`);
    if (val("f-draft-max")) parts.push(`draft_m <= ${Number(val("f-draft-max"))}`);
    if (val("f-vessel"))
      parts.push(`upper(vessel_name) LIKE ${sqlString("%" + val("f-vessel").toUpperCase() + "%")}`);
    if (val("f-agent"))
      parts.push(`upper(coalesce(agent,'')) LIKE ${sqlString("%" + val("f-agent").toUpperCase() + "%")}`);
    if (val("f-domestic")) parts.push(`is_domestic = ${val("f-domestic") === "1"}`);
    return parts.length ? `WHERE ${parts.join(" AND ")}` : "";
  }

  function view() {
    return document.getElementById("f-snapshot").value === "all"
      ? "plans" : "plans_latest";
  }

  function cell(v, cls = "") {
    const text = v === null || v === undefined ? "" : String(v);
    return `<td class="${cls}">${text.replace(/[<>&]/g, "")}</td>`;
  }

  // DuckDB-WASM/Arrow returns DATE/TIMESTAMP columns as raw epoch-millisecond
  // numbers (not Date objects or ISO strings), so format them explicitly.
  function fmtDate(ms) {
    if (ms === null || ms === undefined) return "";
    return new Date(Number(ms)).toISOString().slice(0, 10);
  }
  function fmtTime(ms) {
    if (ms === null || ms === undefined) return "";
    return new Date(Number(ms)).toISOString().slice(11, 16);
  }

  function render(rows, append) {
    const html = rows.map((r) => `<tr>
      ${cell(fmtDate(r.plan_date))}
      ${cell(fmtTime(r.plan_time))}
      ${cell(SECTION_LABELS[r.section] ?? r.section)}
      ${cell(r.vessel_name)}${cell(r.is_sb ? "SB" : "")}
      ${cell(r.draft_m, "num")}${cell(r.loa_m, "num")}
      ${cell(r.dwt?.toLocaleString("vi-VN"), "num")}
      ${cell(r.gt?.toLocaleString("vi-VN"), "num")}
      ${cell(r.channel_code)}${cell(r.from_raw)}${cell(r.to_raw)}
      ${cell(r.to_berth)}${cell(r.to_ticker)}${cell(r.agent)}${cell(r.pilot)}
      ${cell(fmtDate(r.crawled_at))}
    </tr>`).join("");
    const body = document.getElementById("rows");
    if (append) body.insertAdjacentHTML("beforeend", html);
    else body.innerHTML = html;
  }

  async function apply(reset = true) {
    if (reset) { offset = 0; currentWhere = where(); }
    const total = await query(
      `SELECT count(*) AS n FROM ${view()} ${currentWhere}`);
    const rows = await query(`
      SELECT * FROM ${view()} ${currentWhere}
      ORDER BY plan_date DESC, section, plan_time
      LIMIT ${PAGE} OFFSET ${offset}`);
    render(rows, !reset);
    offset += rows.length;
    const n = Number(total[0].n);
    document.getElementById("count").textContent =
      `${n.toLocaleString("vi-VN")} dòng khớp — đang hiện ${offset.toLocaleString("vi-VN")}`;
    document.getElementById("more").hidden = offset >= n;
  }

  document.getElementById("f-apply").addEventListener("click", () => apply(true));
  document.getElementById("more").addEventListener("click", () => apply(false));
  document.getElementById("f-csv").addEventListener("click", async () => {
    const rows = await query(`SELECT * FROM ${view()} ${currentWhere}
                              ORDER BY plan_date DESC, section, plan_time`);
    const cols = Object.keys(rows[0] ?? {});
    const csv = [cols.join(","), ...rows.map((r) =>
      cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "lich_tau_hai_phong.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  await apply(true);
}
