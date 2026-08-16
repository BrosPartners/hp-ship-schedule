// Tab Bản đồ. Dùng Leaflet như dự án bds-visualize để giữ chung một ngôn ngữ
// hình ảnh: chấm tròn, màu theo một chỉ tiêu, bán kính theo quy mô.
import { loadJSON } from "./data.js";

const LEAFLET_JS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
const TILES = {
  anh: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri World Imagery"],
  duong: ["https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
          "© OpenStreetMap"],
  mo: ["https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
       "© CARTO"],
};

const ZONE_LABELS = {
  lach_huyen: "Lạch Huyện", ha_nguon: "Đình Vũ (hạ nguồn)",
  thuong_nguon: "Sông Cấm (thượng nguồn)",
};
// Thang màu: xanh (rẻ / rảnh) → đỏ (đắt / kín). Cùng hướng cho cả hai chỉ
// tiêu nên đọc bản đồ không phải đổi não giữa hai chế độ.
const LOW = [40, 130, 200];
const HIGH = [200, 30, 20];

function lerp(t) {
  const c = LOW.map((v, i) => Math.round(v + (HIGH[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

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

const fmt = (v, unit = "") =>
  (v === null || v === undefined ? "chưa có"
   : v.toLocaleString("vi-VN") + unit);

function popupHtml(p, window_) {
  const rows = [
    ["Khu vực", ZONE_LABELS[p.zone] ?? "chưa xếp"],
    [`Sản lượng ${window_} tháng`, fmt(p.teu_12m, " TEU")
      + (p.teu_shared ? ` <i>(VPA gộp: ${p.teu_shared})</i>` : "")],
    ["Công suất thiết kế", fmt(p.capacity_teu, " TEU/năm")],
    ["% công suất", p.utilisation === null ? "chưa có"
      : `<b>${p.utilisation}%</b>`],
    ["Giá THC", p.thc_usd === null ? "chưa có" : `${p.thc_usd} USD`],
    [`Lượt tàu ${window_} tháng`, fmt(p.calls_12m)],
    ["TEU / lượt tàu", fmt(p.teu_per_call)],
  ];
  return `<h4>${p.unit}</h4><table>${rows.map(([k, v]) =>
    `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>`
    + (p.note ? `<p class="note">${p.note}</p>` : "");
}

export async function initMap(root) {
  root.innerHTML = `<p>Đang tải bản đồ…</p>`;
  const [L, data] = await Promise.all([loadLeaflet(), loadJSON("map_ports")]);

  root.innerHTML = `
    <div class="filters">
      <label>Tô màu theo<select id="m-metric">
        <option value="utilisation">% công suất</option>
        <option value="thc_usd">Giá THC (USD)</option>
        <option value="teu_per_call">TEU / lượt tàu</option>
      </select></label>
      <label>Kích thước chấm<select id="m-size">
        <option value="teu_12m">Sản lượng TEU</option>
        <option value="calls_12m">Lượt tàu</option>
      </select></label>
      <label>Nền<select id="m-tile">
        <option value="anh">Ảnh vệ tinh</option>
        <option value="duong">Bản đồ đường</option>
        <option value="mo">Nền mờ</option>
      </select></label>
      <label><input type="checkbox" id="m-labels" checked> Hiện tên cảng</label>
    </div>
    <div id="m-map" class="map"></div>
    <div id="m-legend" class="map-legend"></div>
    <p class="note">
      Dữ liệu ${data.window} tháng gần nhất (${data.months[0]} →
      ${data.months.at(-1)}). Sản lượng TEU từ VPA, lượt tàu từ kế hoạch tàu.
      <b>Toạ độ, công suất thiết kế và giá THC là số nhập tay trong
      <code>data/port_facts.csv</code>, không phải số cào được</b> - toạ độ hiện
      đặt gần đúng để dựng demo, cảng nào chưa có công suất/THC thì ô đó hiện
      "chưa có" chứ không đoán.
    </p>`;

  const map = L.map("m-map").setView([20.83, 106.78], 11);
  let tiles = null;
  const setTile = (key) => {
    if (tiles) map.removeLayer(tiles);
    const [url, attrib] = TILES[key];
    tiles = L.tileLayer(url, { attribution: attrib, maxZoom: 18 }).addTo(map);
  };
  setTile("anh");

  const layer = L.layerGroup().addTo(map);

  function draw() {
    const metric = document.getElementById("m-metric").value;
    const sizeBy = document.getElementById("m-size").value;
    const labels = document.getElementById("m-labels").checked;
    layer.clearLayers();

    const vals = data.points.map((p) => p[metric]).filter((v) => v !== null);
    const sizes = data.points.map((p) => p[sizeBy]).filter((v) => v !== null);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const smax = Math.max(...sizes, 1);

    for (const p of data.points) {
      const v = p[metric];
      // Cảng thiếu số của chỉ tiêu đang tô sẽ là chấm xám rỗng, vẫn hiện trên
      // bản đồ. Ẩn đi sẽ khiến bản đồ trông như cảng đó không tồn tại.
      const colour = v === null ? "#9aa5ad"
        : lerp(hi === lo ? 0.5 : (v - lo) / (hi - lo));
      const size = p[sizeBy] ? p[sizeBy] / smax : 0;
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 7 + Math.sqrt(size) * 17,
        color: "#22303a", weight: 1,
        fillColor: colour, fillOpacity: v === null ? 0.35 : 0.85,
      }).bindPopup(popupHtml(p, data.window));
      if (labels) {
        marker.bindTooltip(p.unit, { permanent: true, direction: "right",
                                     className: "map-label" });
      }
      layer.addLayer(marker);
    }

    const unit = metric === "thc_usd" ? " USD"
      : metric === "utilisation" ? "%" : " TEU/lượt";
    document.getElementById("m-legend").innerHTML = vals.length ? `
      <span>Thấp ${lo.toLocaleString("vi-VN")}${unit}</span>
      <span class="ramp"></span>
      <span>Cao ${hi.toLocaleString("vi-VN")}${unit}</span>
      <span class="na">● chưa có số</span>` : "";
  }

  ["m-metric", "m-size", "m-labels"].forEach((id) =>
    document.getElementById(id).addEventListener("change", draw));
  document.getElementById("m-tile").addEventListener("change", (e) =>
    setTile(e.target.value));

  draw();
  map.fitBounds(data.points.map((p) => [p.lat, p.lon]), { padding: [40, 40] });
}
