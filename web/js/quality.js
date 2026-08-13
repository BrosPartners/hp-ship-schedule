import { loadJSON, loadManifest } from "./data.js";

export async function initQuality(root) {
  const [manifest, coverage] = await Promise.all([loadManifest(),
                                                   loadJSON("coverage")]);
  const missing = manifest.missing_days ?? [];
  const empty = manifest.empty_days ?? [];

  root.innerHTML = `
    <h3>Độ phủ dữ liệu</h3>
    <table class="grid">
      <tr><th>Số dòng</th><td class="num">${(manifest.row_count ?? 0).toLocaleString("vi-VN")}</td></tr>
      <tr><th>Ngày kế hoạch mới nhất</th><td>${manifest.last_plan_date ?? "—"}</td></tr>
      <tr><th>Lần cào cuối</th><td>${manifest.last_crawled_at ?? "—"}</td></tr>
      <tr><th>Ngày đã có dữ liệu</th><td class="num">${manifest.days_covered ?? 0} / ${manifest.days_expected ?? 0}</td></tr>
      <tr><th>Ngày rỗng (đã cào, 0 dòng)</th><td class="num">${empty.length}</td></tr>
      <tr><th>Ngày còn thiếu (chưa cào)</th><td class="num">${missing.length}</td></tr>
    </table>

    <h3>Ngày còn thiếu</h3>
    <p>${missing.length ? missing.join(", ") : "Không thiếu ngày nào."}</p>

    <h3>Chuẩn hoá bến</h3>
    <p>Chưa map: <b>${coverage.unmapped_pct_30d}%</b> lượt trong 30 ngày gần nhất,
       <b>${coverage.unmapped_pct_all}%</b> trên toàn bộ dữ liệu.
       Ngưỡng cảnh báo là 10%.</p>
    <table class="grid">
      <thead><tr><th>Giá trị chưa map</th><th class="num">Số lượt</th></tr></thead>
      <tbody>${coverage.top_unmapped.map((r) =>
        `<tr><td>${r.raw_name}</td><td class="num">${r.n.toLocaleString("vi-VN")}</td></tr>`
      ).join("")}</tbody>
    </table>
    <p>Sửa <code>data/berth_map.csv</code> trong repo để map thêm; dashboard tự
       cập nhật sau lần chạy kế tiếp.</p>
  `;
}

export async function initFreshness(el) {
  try {
    const [manifest, coverage] = await Promise.all([loadManifest(),
                                                     loadJSON("coverage")]);
    const last = manifest.last_plan_date;
    const ageDays = last
      ? Math.floor((Date.now() - new Date(last).getTime()) / 86400000)
      : Infinity;

    if (ageDays > 2) {
      el.className = "badge err";
      el.textContent = `Dữ liệu cũ ${ageDays} ngày — mới nhất ${last ?? "—"}`;
    } else if ((coverage.unmapped_pct_30d ?? 0) > 10) {
      el.className = "badge warn";
      el.textContent = `Dữ liệu tới ${last} — ${coverage.unmapped_pct_30d}% lượt chưa map bến`;
    } else {
      el.className = "badge";
      el.textContent = `Dữ liệu tới ${last}`;
    }
  } catch (err) {
    el.className = "badge err";
    el.textContent = "Không tải được manifest";
  }
}
