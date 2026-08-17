// Tra cứu chi tiết TP.HCM. Tách khỏi js/lookup.js (Hải Phòng) vì hai nguồn có
// schema khác nhau: bảng TP.HCM có quốc tịch, hô hiệu, loại hàng hoá, ETA/ETD
// và cụm cảng, nhưng không có GT, không có mã SB và không có cờ nội địa. Gộp
// hai bảng vào một hàm dùng chung sẽ phải rẽ nhánh ở gần như mọi cột.
import { loadJSONFrom, query, sqlString } from "./data.js";

const AGG = "data/hcm/agg";
const DATASET = "hcm";
const SECTION_LABELS = {
  tau_vao: "Tàu vào", tau_roi: "Tàu rời", tau_di_chuyen: "Di chuyển",
};
const ZONE_LABELS = {
  cai_mep: "Cái Mép - Thị Vải", song_sai_gon: "Sông Sài Gòn",
  song_soai_rap: "Sông Soài Rạp (Long An)", vung_tau: "Vũng Tàu",
};
const PAGE = 300;

export async function initHcmLookup(root) {
  root.innerHTML = `<p>Đang tải dữ liệu chi tiết TP.HCM…</p>`;
  const filters = await loadJSONFrom(AGG, "filters");
  const zoneOf = filters.cluster_zones ?? {};

  root.innerHTML = `
    <div class="filters">
      <label>Từ ngày<input type="date" id="x-from" value="${filters.date_min ?? ""}"></label>
      <label>Đến ngày<input type="date" id="x-to" value="${filters.date_max ?? ""}"></label>
      <label>Loại<select id="x-section">
        <option value="">Tất cả</option>
        ${filters.sections.map((s) => `<option value="${s}">${SECTION_LABELS[s] ?? s}</option>`).join("")}
      </select></label>
      <label>Khu vực<select id="x-zone"><option value="">Tất cả</option>
        ${(filters.zones ?? []).map((z) => `<option value="${z}">${ZONE_LABELS[z] ?? z}</option>`).join("")}</select></label>
      <label>Cụm đi<select id="x-from-cluster"><option value="">Tất cả</option>
        ${filters.clusters.map((c) => `<option>${c}</option>`).join("")}</select></label>
      <label>Cụm đến<select id="x-to-cluster"><option value="">Tất cả</option>
        ${filters.clusters.map((c) => `<option>${c}</option>`).join("")}</select></label>
      <label>DWT từ<input type="number" id="x-dwt-min" min="0" placeholder="0"></label>
      <label>DWT đến<input type="number" id="x-dwt-max" min="0" placeholder="${filters.dwt_max}"></label>
      <label>Mớn nước từ<input type="number" id="x-draft-min" step="0.1" placeholder="0"></label>
      <label>Mớn nước đến<input type="number" id="x-draft-max" step="0.1" placeholder="${filters.draft_max}"></label>
      <label>Tên tàu<input id="x-vessel" placeholder="ví dụ: HAI AN"></label>
      <label>Quốc tịch<input id="x-nation" placeholder="VN, PA…"></label>
      <label>Loại hàng<input id="x-cargo" placeholder="CONTAINER, DAU…"></label>
      <label>Đại lý<input id="x-agent" placeholder="tên đại lý"></label>
      <label>Snapshot<select id="x-snapshot">
        <option value="latest">Chỉ bản mới nhất</option>
        <option value="all">Mọi snapshot</option></select></label>
      <button id="x-apply">Áp dụng</button>
      <button id="x-csv">Tải CSV</button>
    </div>
    <div id="x-count" class="badge"></div>
    <div class="scroller"><table class="grid">
      <thead><tr>
        <th>Ngày</th><th>Loại</th><th>Tên tàu</th><th>Quốc tịch</th><th>Hô hiệu</th>
        <th class="num">Mớn</th><th class="num">LOA</th><th class="num">DWT</th>
        <th>Loại hàng</th><th>Từ</th><th>Đến</th><th>Cụm đến</th><th>Khu</th>
        <th>ETA</th><th>ETD</th><th>Tàu lai</th><th>Đại lý</th><th>Luồng</th>
        <th>Snapshot</th>
      </tr></thead><tbody id="x-rows"></tbody>
    </table></div>
    <button id="x-more" hidden>Tải thêm ${PAGE} dòng</button>
    <p class="note">
      Khu Vũng Tàu - Cái Mép - Thị Vải chỉ có dữ liệu từ 01/08/2025 (xem ghi
      chú độ phủ ở tab Phân tích). Cụm Ba Son đã được loại khỏi dữ liệu.
    </p>
  `;

  let offset = 0;
  let currentWhere = "";

  function where() {
    const val = (id) => document.getElementById(id).value.trim();
    const parts = [];
    if (val("x-from")) parts.push(`plan_date >= DATE ${sqlString(val("x-from"))}`);
    if (val("x-to")) parts.push(`plan_date <= DATE ${sqlString(val("x-to"))}`);
    if (val("x-section")) parts.push(`section = ${sqlString(val("x-section"))}`);
    if (val("x-from-cluster")) parts.push(`from_cluster = ${sqlString(val("x-from-cluster"))}`);
    if (val("x-to-cluster")) parts.push(`to_cluster = ${sqlString(val("x-to-cluster"))}`);
    // Zone không có trong Parquet (nó là hàm thuần của cluster, tính ở tầng
    // tổng hợp), nên lọc khu = lọc theo danh sách cụm thuộc khu đó.
    if (val("x-zone")) {
      const members = Object.entries(zoneOf)
        .filter(([, z]) => z === val("x-zone")).map(([c]) => sqlString(c));
      parts.push(members.length
        ? `to_cluster IN (${members.join(", ")})`
        : "FALSE");
    }
    if (val("x-dwt-min")) parts.push(`dwt >= ${Number(val("x-dwt-min"))}`);
    if (val("x-dwt-max")) parts.push(`dwt <= ${Number(val("x-dwt-max"))}`);
    if (val("x-draft-min")) parts.push(`draft_m >= ${Number(val("x-draft-min"))}`);
    if (val("x-draft-max")) parts.push(`draft_m <= ${Number(val("x-draft-max"))}`);
    const like = (id, col) => {
      if (!val(id)) return;
      parts.push(`upper(coalesce(${col},'')) LIKE `
                 + sqlString("%" + val(id).toUpperCase() + "%"));
    };
    like("x-vessel", "vessel_name");
    like("x-nation", "nationality");
    like("x-cargo", "cargo_type");
    like("x-agent", "agent");
    return parts.length ? `WHERE ${parts.join(" AND ")}` : "";
  }

  function view() {
    return document.getElementById("x-snapshot").value === "all"
      ? "hcm_plans" : "hcm_plans_latest";
  }

  function cell(v, cls = "") {
    const text = v === null || v === undefined ? "" : String(v);
    return `<td class="${cls}">${text.replace(/[<>&]/g, "")}</td>`;
  }

  // DuckDB-WASM/Arrow trả DATE/TIMESTAMP về dạng epoch mili-giây, không phải
  // Date hay chuỗi ISO, nên phải tự định dạng.
  function fmtDate(ms) {
    if (ms === null || ms === undefined) return "";
    return new Date(Number(ms)).toISOString().slice(0, 10);
  }

  // ETA/ETD là TIMESTAMP nên cũng về dạng epoch mili-giây; in thẳng ra sẽ là
  // một dãy số 13 chữ số vô nghĩa với người đọc.
  function fmtDateTime(ms) {
    if (ms === null || ms === undefined) return "";
    if (typeof ms === "string") return ms;
    return new Date(Number(ms)).toISOString().slice(0, 16).replace("T", " ");
  }

  function render(rows, append) {
    const html = rows.map((r) => `<tr>
      ${cell(fmtDate(r.plan_date))}
      ${cell(SECTION_LABELS[r.section] ?? r.section)}
      ${cell(r.vessel_name)}${cell(r.nationality)}${cell(r.call_sign)}
      ${cell(r.draft_m, "num")}${cell(r.loa_m, "num")}
      ${cell(r.dwt?.toLocaleString("vi-VN"), "num")}
      ${cell(r.cargo_type)}${cell(r.from_position)}${cell(r.to_position)}
      ${cell(r.to_cluster)}${cell(ZONE_LABELS[zoneOf[r.to_cluster]] ?? "")}
      ${cell(fmtDateTime(r.eta))}${cell(fmtDateTime(r.etd))}${cell(r.tugs)}${cell(r.agent)}
      ${cell(r.channel)}${cell(fmtDate(r.crawled_at))}
    </tr>`).join("");
    const body = document.getElementById("x-rows");
    if (append) body.insertAdjacentHTML("beforeend", html);
    else body.innerHTML = html;
  }

  async function apply(reset = true) {
    if (reset) { offset = 0; currentWhere = where(); }
    const total = await query(
      `SELECT count(*) AS n FROM ${view()} ${currentWhere}`, DATASET);
    const rows = await query(`
      SELECT * FROM ${view()} ${currentWhere}
      ORDER BY plan_date DESC, section
      LIMIT ${PAGE} OFFSET ${offset}`, DATASET);
    render(rows, !reset);
    offset += rows.length;
    const n = Number(total[0].n);
    document.getElementById("x-count").textContent =
      `${n.toLocaleString("vi-VN")} dòng khớp — đang hiện ${offset.toLocaleString("vi-VN")}`;
    document.getElementById("x-more").hidden = offset >= n;
  }

  document.getElementById("x-apply").addEventListener("click", () => apply(true));
  document.getElementById("x-more").addEventListener("click", () => apply(false));
  document.getElementById("x-csv").addEventListener("click", async () => {
    const rows = await query(`SELECT * FROM ${view()} ${currentWhere}
                              ORDER BY plan_date DESC, section`, DATASET);
    const cols = Object.keys(rows[0] ?? {});
    const csv = [cols.join(","), ...rows.map((r) =>
      cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "lich_tau_tphcm.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  await apply(true);
}
