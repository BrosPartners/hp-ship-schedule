// Tab Bản đồ. Dùng Leaflet như dự án bds-visualize để giữ chung một ngôn ngữ
// hình ảnh: chấm tròn, màu theo một chỉ tiêu, bán kính theo quy mô, kèm thanh
// chỉnh độ mờ nền và nút ẩn nhãn bản đồ.
import { loadJSON } from "./data.js";

const LEAFLET_JS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";

// Mỗi nền có hai biến thể: có nhãn và không nhãn. Ảnh vệ tinh vốn không có
// nhãn nên hai biến thể trùng nhau - giữ cùng cấu trúc để nút "ẩn nhãn" hoạt
// động thống nhất thay vì phải đặc cách.
const TILES = {
  anh: {
    label: "Ảnh vệ tinh",
    normal: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    noLabels: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attrib: "Esri World Imagery",
  },
  duong: {
    label: "Bản đồ đường",
    normal: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    noLabels: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    attrib: "© OpenStreetMap, © CARTO",
  },
  mo: {
    label: "Nền mờ",
    normal: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    noLabels: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    attrib: "© CARTO",
  },
};

const ZONE_LABELS = {
  lach_huyen: "Lạch Huyện", ha_nguon: "Đình Vũ (hạ nguồn)",
  thuong_nguon: "Sông Cấm (thượng nguồn)",
};
const GEO_LABELS = {
  osm: "OpenStreetMap", uoc_luong: "ước lượng - cần chỉnh",
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
  const capacity = p.capacity_shared ?? p.capacity_teu;
  const rows = [
    ["Khu vực", ZONE_LABELS[p.zone] ?? "chưa xếp"],
    [`Sản lượng ${window_} tháng`, fmt(p.teu_12m, " TEU")
      + (p.teu_shared ? ` <i>(VPA gộp: ${p.teu_shared})</i>` : "")],
    ["Công suất thiết kế", fmt(capacity, " TEU/năm")
      + (p.capacity_shared ? " <i>(cả cụm)</i>" : "")],
    ["% công suất", p.utilisation === null ? "chưa có"
      : `<b>${p.utilisation}%</b>`],
    ["Giá THC", p.thc_usd === null ? "chưa có" : `${p.thc_usd} USD`],
    [`Lượt tàu ${window_} tháng`, fmt(p.calls_12m)],
    ["TEU / lượt tàu", fmt(p.teu_per_call)],
    ["Toạ độ", `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}<br>
                <i>${GEO_LABELS[p.geo_source] ?? "không rõ nguồn"}</i>`],
  ];
  const foot = [p.capacity_source && `Nguồn công suất: ${p.capacity_source}`,
                p.note].filter(Boolean);
  return `<h4>${p.unit}</h4><table>${rows.map(([k, v]) =>
    `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>`
    + foot.map((t) => `<p class="note">${t}</p>`).join("");
}

function toCsv(points) {
  const cols = ["unit", "lat", "lon", "geo_source", "capacity_teu",
                "capacity_source", "thc_usd", "zone", "note"];
  return [cols.join(","), ...points.map((p) =>
    cols.map((c) => `"${String(p[c] ?? "")}"`).join(","))].join("\n");
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
        ${Object.entries(TILES).map(([k, t]) =>
          `<option value="${k}">${t.label}</option>`).join("")}
      </select></label>
      <label>Độ mờ bản đồ nền
        <input type="range" id="m-opacity" min="20" max="100" value="100">
        <span id="m-opacity-val">100%</span></label>
      <label><input type="checkbox" id="m-nolabels"> Ẩn tên đường/nhãn bản đồ</label>
      <label><input type="checkbox" id="m-labels" checked> Hiện tên cảng</label>
      <label><input type="checkbox" id="m-drag"> Kéo chấm để sửa toạ độ</label>
      <button type="button" id="m-export">Tải CSV toạ độ</button>
    </div>
    <div id="m-map" class="map"></div>
    <div id="m-legend" class="map-legend"></div>
    <p class="note">
      Dữ liệu ${data.window} tháng gần nhất (${data.months[0]} →
      ${data.months.at(-1)}). Sản lượng TEU từ VPA, lượt tàu từ kế hoạch tàu.
      <b>Toạ độ, công suất thiết kế và giá THC nằm trong
      <code>data/port_facts.csv</code>, không phải số cào được.</b>
      Toạ độ ghi rõ nguồn trong popup: lấy từ OpenStreetMap hay còn là ước
      lượng. Bật "Kéo chấm để sửa toạ độ", kéo về đúng vị trí rồi bấm
      "Tải CSV toạ độ" để lấy file thay cho <code>port_facts.csv</code>.
      Cảng nào chưa có công suất/THC thì hiện "chưa có" chứ không đoán.
    </p>`;

  const map = L.map("m-map").setView([20.83, 106.78], 11);
  let tiles = null;
  const applyTile = () => {
    const key = document.getElementById("m-tile").value;
    const hide = document.getElementById("m-nolabels").checked;
    const opacity = document.getElementById("m-opacity").value / 100;
    if (tiles) map.removeLayer(tiles);
    const spec = TILES[key];
    tiles = L.tileLayer(hide ? spec.noLabels : spec.normal,
                        { attribution: spec.attrib, maxZoom: 18, opacity })
             .addTo(map);
    tiles.bringToBack();
  };
  applyTile();

  const layer = L.layerGroup().addTo(map);

  function draw() {
    const metric = document.getElementById("m-metric").value;
    const sizeBy = document.getElementById("m-size").value;
    const labels = document.getElementById("m-labels").checked;
    const draggable = document.getElementById("m-drag").checked;
    layer.clearLayers();

    const vals = data.points.map((p) => p[metric]).filter((v) => v !== null);
    const sizes = data.points.map((p) => p[sizeBy]).filter((v) => v !== null);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const smax = Math.max(...sizes, 1);

    for (const p of data.points) {
      const v = p[metric];
      // Cảng thiếu số của chỉ tiêu đang tô sẽ là chấm xám mờ, vẫn hiện trên
      // bản đồ. Ẩn đi sẽ khiến bản đồ trông như cảng đó không tồn tại.
      const colour = v === null ? "#9aa5ad"
        : lerp(hi === lo ? 0.5 : (v - lo) / (hi - lo));
      const size = p[sizeBy] ? p[sizeBy] / smax : 0;
      const radius = 7 + Math.sqrt(size) * 17;
      const style = { radius, color: "#22303a", weight: 1, fillColor: colour,
                      fillOpacity: v === null ? 0.35 : 0.85 };

      let marker;
      if (draggable) {
        // circleMarker không kéo được, nên ở chế độ sửa toạ độ dùng marker
        // thường với icon vẽ bằng CSS cho giống chấm tròn.
        marker = L.marker([p.lat, p.lon], {
          draggable: true,
          icon: L.divIcon({
            className: "map-dot",
            html: `<span style="width:${2 * radius}px;height:${2 * radius}px;
                   background:${colour};opacity:${style.fillOpacity}"></span>`,
            iconSize: [2 * radius, 2 * radius],
          }),
        }).on("dragend", (e) => {
          const ll = e.target.getLatLng();
          p.lat = +ll.lat.toFixed(5);
          p.lon = +ll.lng.toFixed(5);
          p.geo_source = "sua_tay";
          draw();
        });
      } else {
        marker = L.circleMarker([p.lat, p.lon], style);
      }
      marker.bindPopup(popupHtml(p, data.window));
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

  ["m-metric", "m-size", "m-labels", "m-drag"].forEach((id) =>
    document.getElementById(id).addEventListener("change", draw));
  ["m-tile", "m-nolabels"].forEach((id) =>
    document.getElementById(id).addEventListener("change", applyTile));

  const slider = document.getElementById("m-opacity");
  slider.addEventListener("input", () => {
    document.getElementById("m-opacity-val").textContent = `${slider.value}%`;
    if (tiles) tiles.setOpacity(slider.value / 100);
  });

  document.getElementById("m-export").addEventListener("click", () => {
    const blob = new Blob(["﻿" + toCsv(data.points)],
                          { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "port_facts.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  draw();
  map.fitBounds(data.points.map((p) => [p.lat, p.lon]), { padding: [40, 40] });
}
