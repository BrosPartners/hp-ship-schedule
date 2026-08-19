// Tab Tuyến: bản đồ thế giới, cung nối Hải Phòng với từng nước, độ dày cung
// theo lượt tàu hoặc DWT. Dùng lại Leaflet như tab Bản đồ để giữ chung ngôn
// ngữ hình ảnh, nhưng ở đây nền luôn là bản đồ mờ không nhãn - cung và chấm
// mới là nội dung chính, nhãn nền chỉ làm rối.
import { loadJSONFrom } from "./data.js";

const LEAFLET_JS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
const TILE = "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png";

const HP = { lat: 20.83, lon: 106.78, name: "Hải Phòng" };
const IN_COLOR = "#1f77b4";    // hàng về
const OUT_COLOR = "#d62728";   // hàng đi

function loadCss(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

async function loadLeaflet() {
  loadCss(LEAFLET_CSS);
  if (window.L) return window.L;
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = LEAFLET_JS;
    s.onload = resolve;
    s.onerror = () => reject(new Error("không tải được Leaflet"));
    document.head.appendChild(s);
  });
  return window.L;
}

// Hoa Kỳ/Canada nằm ở kinh độ âm; nối thẳng từ Hải Phòng (106,8°Đ) sẽ vẽ ngược
// qua châu Âu - sai hoàn toàn so với tuyến hàng hải thật (vượt Thái Bình
// Dương). Cộng 360° để cung đi về phía đông. Leaflet nhận kinh độ >180 nên
// không cần xử lý gì thêm.
function unwrapLon(lon) {
  return lon - HP.lon < -180 ? lon + 360 : lon;
}

// Cung bậc hai; điểm điều khiển đẩy vuông góc với dây cung nên mọi tuyến đều
// cong cùng một phía, không rối như khi bẻ cong ngẫu nhiên.
function arcPoints(to, bend = 0.22, steps = 48) {
  const [x1, y1] = [HP.lon, HP.lat];
  const [x2, y2] = [unwrapLon(to.lon), to.lat];
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const cx = mx + (y2 - y1) * bend;
  const cy = my - (x2 - x1) * bend;
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    pts.push([u * u * y1 + 2 * u * t * cy + t * t * y2,
              u * u * x1 + 2 * u * t * cx + t * t * x2]);
  }
  return pts;
}

const fmt = (v) => Math.round(v).toLocaleString("vi-VN");

export async function initRoute(root) {
  root.innerHTML = `<p>Đang tải dữ liệu tuyến…</p>`;
  const [L, data] = await Promise.all([
    loadLeaflet(), loadJSONFrom("data/agg", "route_flows"),
  ]);
  const rows = data.rows;
  const points = data.points;
  const months = [...new Set(rows.map((r) => r.month))].sort();
  const years = [...new Set(months.map((m) => m.slice(0, 4)))].sort().reverse();
  const locs = [...new Set(rows.map((r) => r.loc))].sort((a, b) =>
    a.localeCompare(b, "vi"));
  const locType = new Map(rows.map((r) => [r.loc, r.loc_type]));

  root.innerHTML = `
    <div class="filters">
      <label>Đo bằng<select id="rt-metric">
        <option value="calls">Lượt tàu</option>
        <option value="dwt">Tổng DWT</option>
      </select></label>
      <label>Chiều<select id="rt-dir">
        <option value="both">Cả hai chiều</option>
        <option value="in">Tàu đến Hải Phòng</option>
        <option value="out">Tàu rời Hải Phòng</option>
      </select></label>
      <label>Kỳ<select id="rt-year">
        <option value="">Toàn bộ (${months[0]} → ${months[months.length - 1]})</option>
        ${years.map((y) => `<option value="${y}">${y}</option>`).join("")}
      </select></label>
    </div>
    <div class="filters berth-picker" id="rt-picker">
      ${locs.map((l) => `<label><input type="checkbox" class="rt-loc" value="${l}" checked> ${l}${
        locType.get(l) === "anchorage" ? " <i>(khu neo)</i>" : ""}</label>`).join("")}
      <button type="button" id="rt-all">Chọn tất cả</button>
      <button type="button" id="rt-none">Ẩn tất cả</button>
      <button type="button" id="rt-berths">Chỉ bến (bỏ khu neo)</button>
    </div>
    <div id="rt-map" class="chart" style="height:520px"></div>
    <div class="chart-head"><h3>Xếp hạng tuyến</h3>
      <span><button id="rt-csv">Tải data</button></span></div>
    <div id="rt-table"></div>
    <p class="note">
      Nguồn: chính lịch tàu Cảng vụ Hải Phòng - mỗi lượt <b>tàu vào</b> ghi tên
      nước ở đầu đi, mỗi lượt <b>tàu rời</b> ghi tên nước ở đầu đến, nên tuyến
      ở đây là số đếm thật chứ không phải ước lượng. Đầu Hải Phòng tính cả bến
      lẫn khu neo (Hòn Dấu, Vật Cách, Thượng Lý, Nam Cát Bà): tàu quốc tế vào
      thẳng khu neo là lượt quốc tế thật, bỏ đi sẽ hụt ~1.200 lượt và làm lệch
      hồ sơ tuyến của hàng rời/hàng lỏng.
      <br><b>Chấm nước đặt ở cảng cửa ngõ chính</b> (Trung Quốc lấy điểm giữa
      bờ biển vì lưu lượng trải từ Quảng Tây tới Thượng Hải), không phải tâm
      địa lý - xem <code>data/country_points.csv</code>. Cung chỉ là đường nối
      thị giác, không phải hải trình thực tế.
      <br><b>TP.HCM chưa có tab này</b> vì nguồn cảng vụ TP.HCM không công bố
      cảng đi/cảng đến - bảng của họ chỉ có vị trí neo đậu trong cảng.
    </p>`;

  const map = L.map("rt-map", { worldCopyJump: false, minZoom: 1 })
    .setView([18, 130], 3);
  L.tileLayer(TILE, { attribution: "© CARTO", maxZoom: 10 }).addTo(map);
  const layer = L.layerGroup().addTo(map);

  const picked = () => new Set([...root.querySelectorAll(".rt-loc:checked")]
    .map((cb) => cb.value));

  function draw() {
    layer.clearLayers();
    const metric = document.getElementById("rt-metric").value;
    const dir = document.getElementById("rt-dir").value;
    const year = document.getElementById("rt-year").value;
    const keep = picked();

    const totals = new Map();
    for (const r of rows) {
      if (!keep.has(r.loc)) continue;
      if (dir !== "both" && r.direction !== dir) continue;
      if (year && !r.month.startsWith(year)) continue;
      const cur = totals.get(r.country) ?? { in: 0, out: 0 };
      cur[r.direction] += r[metric];
      totals.set(r.country, cur);
    }
    const rank = [...totals.entries()]
      .map(([country, v]) => ({ country, ...v, total: v.in + v.out }))
      .filter((d) => d.total > 0)
      .sort((a, b) => b.total - a.total);

    const max = rank.length ? rank[0].total : 1;
    const unit = metric === "calls" ? "lượt" : "DWT";

    for (const d of rank) {
      const p = points[d.country];
      if (!p) continue;   // build đã chặn trường hợp này, giữ cho chắc
      // Căn theo căn bậc hai để tuyến nhỏ không biến mất hẳn khi Trung Quốc
      // lớn gấp hàng chục lần phần còn lại.
      const w = 1 + 11 * Math.sqrt(d.total / max);
      const color = d.out > d.in ? OUT_COLOR : IN_COLOR;
      const tip = `<b>${d.country}</b><br>
        Tàu đến Hải Phòng: ${fmt(d.in)} ${unit}<br>
        Tàu rời Hải Phòng: ${fmt(d.out)} ${unit}<br>
        Tổng: <b>${fmt(d.total)} ${unit}</b><br>
        <i>Chấm đặt tại: ${p.anchor || "—"}</i>`;
      L.polyline(arcPoints(p), { color, weight: w, opacity: 0.55 })
        .bindPopup(tip).addTo(layer);
      L.circleMarker([p.lat, unwrapLon(p.lon)], {
        radius: 4 + 9 * Math.sqrt(d.total / max), color, fillColor: color,
        fillOpacity: 0.75, weight: 1,
      }).bindPopup(tip).bindTooltip(d.country).addTo(layer);
    }
    L.circleMarker([HP.lat, HP.lon], {
      radius: 7, color: "#111", fillColor: "#fff", fillOpacity: 1, weight: 2,
    }).bindTooltip("Hải Phòng", { permanent: true, direction: "left" })
      .addTo(layer);

    const head = metric === "calls" ? "Lượt tàu" : "DWT";
    document.getElementById("rt-table").innerHTML = rank.length ? `
      <table class="grid"><thead><tr><th>#</th><th>Nước</th>
        <th>Đến HP (${head})</th><th>Rời HP (${head})</th><th>Tổng</th>
        <th>Tỷ trọng</th></tr></thead><tbody>
        ${rank.map((d, i) => `<tr><td>${i + 1}</td><td>${d.country}</td>
          <td>${fmt(d.in)}</td><td>${fmt(d.out)}</td><td><b>${fmt(d.total)}</b></td>
          <td>${(100 * d.total / rank.reduce((s, x) => s + x.total, 0)).toFixed(1)}%</td>
          </tr>`).join("")}
      </tbody></table>` : `<p>Không có tuyến nào khớp bộ lọc.</p>`;
    root._rank = rank;
  }

  for (const id of ["rt-metric", "rt-dir", "rt-year"]) {
    document.getElementById(id).addEventListener("change", draw);
  }
  const boxes = () => [...root.querySelectorAll(".rt-loc")];
  boxes().forEach((cb) => cb.addEventListener("change", draw));
  document.getElementById("rt-all").addEventListener("click", () => {
    boxes().forEach((cb) => { cb.checked = true; }); draw();
  });
  document.getElementById("rt-none").addEventListener("click", () => {
    boxes().forEach((cb) => { cb.checked = false; }); draw();
  });
  document.getElementById("rt-berths").addEventListener("click", () => {
    boxes().forEach((cb) => { cb.checked = locType.get(cb.value) !== "anchorage"; });
    draw();
  });
  document.getElementById("rt-csv").addEventListener("click", () => {
    const rank = root._rank ?? [];
    if (!rank.length) return;
    const cols = ["country", "in", "out", "total"];
    const csv = [cols.join(","), ...rank.map((r) =>
      cols.map((c) => `"${String(r[c] ?? "")}"`).join(","))].join("\n");
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "tuyen.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  draw();
  setTimeout(() => map.invalidateSize(), 0);
}
