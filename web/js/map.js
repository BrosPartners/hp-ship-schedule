// Tab Bản đồ. Dùng Leaflet như dự án bds-visualize để giữ chung một ngôn ngữ
// hình ảnh: chấm tròn, màu theo một chỉ tiêu, bán kính theo quy mô, kèm thanh
// chỉnh độ mờ nền và nút ẩn nhãn bản đồ.
import { loadJSONFrom } from "./data.js";

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

// Mỗi cảng có bộ khu riêng và file dữ liệu riêng; phần còn lại của bản đồ
// giống hệt nhau nên dùng chung một hàm thay vì chép đôi.
const PORTS = {
  hp: {
    agg: "data/agg",
    facts: "data/port_facts.csv",
    center: [20.83, 106.78],
    store: "hp-ship-schedule.port-geo-overrides.v1",
    zones: { lach_huyen: "Lạch Huyện", ha_nguon: "Đình Vũ (hạ nguồn)",
             thuong_nguon: "Sông Cấm (thượng nguồn)" },
  },
  hcm: {
    agg: "data/hcm/agg",
    facts: "data/hcm/port_facts.csv",
    center: [10.6, 106.9],
    store: "hp-ship-schedule.hcm-geo-overrides.v1",
    zones: { cai_mep: "Cái Mép - Thị Vải", song_sai_gon: "Sông Sài Gòn",
             song_soai_rap: "Sông Soài Rạp (Long An)", vung_tau: "Vũng Tàu" },
  },
};
const GEO_LABELS = {
  osm: "OpenStreetMap", uoc_luong: "ước lượng - cần chỉnh",
  google_maps: "Google Maps (bạn dán link)", sua_tay: "kéo tay trên bản đồ",
  cangvu_api: "API Cảng vụ TP.HCM (cầu/phao chính thức)",
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

function popupHtml(p, window_, zoneLabels) {
  const capacity = p.capacity_shared ?? p.capacity_teu;
  const rows = [
    ["Khu vực", zoneLabels[p.zone] ?? "chưa xếp"],
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

// Thứ tự ưu tiên giống pages/api/parse-maps-link.js của bds-visualize: toạ độ
// ghim địa điểm (!3d/!4d) đứng trước tâm khung nhìn (@lat,lng), vì @ chỉ là
// chỗ camera đang đứng chứ không phải điểm được ghim.
const MAPS_PATTERNS = [
  /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/,
  /[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/,
  /[?&]ll=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/,
  /[?&]destination=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/,
  /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/,
  /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/,   // dán thẳng "20.85, 106.72"
];

export function parseMapsLink(text) {
  const raw = (text || "").trim();
  if (!raw) return { error: "Chưa dán link nào." };
  // Link rút gọn không đọc được từ trình duyệt: Google không trả CORS header
  // nên fetch bị chặn trước cả khi thấy redirect. Nói thẳng cách xử lý thay vì
  // để nút bấm im lặng không làm gì.
  if (/goo\.gl/i.test(raw) && !MAPS_PATTERNS.some((re) => re.test(raw))) {
    return { error: "Link rút gọn (goo.gl) không đọc được toạ độ trực tiếp. "
                  + "Bấm \"Mở link\" bên cạnh, đợi Google Maps tải xong rồi "
                  + "chép URL đầy đủ trên thanh địa chỉ và dán lại.",
             openable: raw };
  }
  for (const re of MAPS_PATTERNS) {
    const hit = raw.match(re);
    if (!hit) continue;
    const lat = parseFloat(hit[1]);
    const lon = parseFloat(hit[2]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      return { error: `Toạ độ đọc được không hợp lệ (${lat}, ${lon}).` };
    }
    return { lat: +lat.toFixed(5), lon: +lon.toFixed(5) };
  }
  return { error: "Không tìm thấy toạ độ trong link này. Mở địa điểm trên "
                + "Google Maps rồi chép URL đầy đủ trên thanh địa chỉ." };
}

// Toạ độ sửa trên giao diện chỉ nằm trong bộ nhớ trang; tải lại là mất, và
// đó đúng là lỗi người dùng gặp phải. Lưu tạm vào localStorage để sửa xong
// không bay mất, nhưng đây vẫn chỉ là bản nháp trên máy này - nguồn thật là
// data/port_facts.csv trong repo, nên giao diện phải nói rõ còn bao nhiêu sửa
// chưa đưa vào repo thay vì để người dùng tưởng đã lưu.
function loadOverrides(storeKey) {
  try {
    const raw = localStorage.getItem(storeKey);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};   // localStorage bị chặn hoặc dữ liệu hỏng: coi như chưa sửa gì
  }
}

function saveOverrides(storeKey, overrides) {
  try {
    localStorage.setItem(storeKey, JSON.stringify(overrides));
    return true;
  } catch {
    return false;
  }
}

function applyOverrides(points, overrides) {
  let applied = 0;
  for (const p of points) {
    const hit = overrides[p.unit];
    // Bỏ qua bản ghi hỏng thay vì để một toạ độ rác đẩy chấm ra giữa đại dương.
    if (!hit || !Number.isFinite(hit.lat) || !Number.isFinite(hit.lon)) continue;
    p.lat = hit.lat;
    p.lon = hit.lon;
    p.geo_source = hit.geo_source || "sua_tay";
    applied += 1;
  }
  return applied;
}

// Dấu " bên trong một field phải nhân đôi thành "" theo chuẩn CSV (RFC 4180) -
// thiếu bước này đã từng làm hỏng cấu trúc file khi ghi chú của HTIT có tên
// node OSM đặt trong dấu ngoặc kép.
function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function toCsv(points, hasVolumeKey) {
  const cols = ["unit", ...(hasVolumeKey ? ["volume_key"] : []),
                "lat", "lon", "geo_source", "capacity_teu",
                "capacity_source", "thc_usd", "zone", "note"];
  return [cols.map(csvCell).join(","), ...points.map((p) =>
    cols.map((c) => csvCell(p[c])).join(","))].join("\n");
}

export async function initMap(root, port = "hp") {
  const cfg = PORTS[port];
  const ZONE_LABELS = cfg.zones;
  root.innerHTML = `<p>Đang tải bản đồ…</p>`;
  const [L, data] = await Promise.all([loadLeaflet(),
                                       loadJSONFrom(cfg.agg, "map_ports")]);
  const hasVolumeKey = data.points.some((p) => p.volume_key
                                            && p.volume_key !== p.unit);

  // Bỏ những đơn vị không còn trong map_ports.json để bản nháp cũ không giữ
  // mãi một cảng đã bị xoá khỏi port_facts.csv.
  const known = new Set(data.points.map((p) => p.unit));
  const overrides = Object.fromEntries(
    Object.entries(loadOverrides(cfg.store)).filter(([unit]) => known.has(unit)));
  applyOverrides(data.points, overrides);

  root.innerHTML = `
    <div class="pending" id="m-pending" hidden></div>
    <div class="pending clash" id="m-clash" hidden></div>
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
      <button type="button" id="m-geo">📍 Dán link Google Maps</button>
      <button type="button" id="m-export">Tải CSV toạ độ</button>
    </div>
    <div class="geo-panel" id="m-geo-panel" hidden>
      <label>Cảng<select id="m-geo-unit">
        ${data.points.map((p, i) =>
          `<option value="${i}">${p.unit}</option>`).join("")}
      </select></label>
      <label class="grow">Link Google Maps
        <input type="text" id="m-geo-link" placeholder="dán link đầy đủ, vd https://www.google.com/maps/place/.../@20.85,106.72,17z/...">
      </label>
      <button type="button" id="m-geo-apply">Lấy toạ độ</button>
      <button type="button" id="m-geo-open" hidden>Mở link</button>
      <button type="button" id="m-geo-close">Đóng</button>
      <div id="m-geo-msg" class="geo-msg"></div>
    </div>
    <div id="m-map" class="map"></div>
    <div id="m-legend" class="map-legend"></div>
    <p class="note">
      Dữ liệu ${data.window} tháng gần nhất (${data.months[0]} →
      ${data.months.at(-1)}). Sản lượng TEU từ VPA, lượt tàu từ kế hoạch tàu.
      <b>Toạ độ, công suất thiết kế và giá THC nằm trong
      <code>${cfg.facts}</code>, không phải số cào được.</b>
      Toạ độ ghi rõ nguồn trong popup: lấy từ OpenStreetMap hay còn là ước
      lượng. Sửa toạ độ bằng cách dán link Google Maps hoặc bật "Kéo chấm để
      sửa toạ độ". <b>Sửa xong chỉ nằm trên trình duyệt này</b> - phải tải CSV
      rồi thay <code>${cfg.facts}</code> trong repo thì người khác mới thấy. Cảng nào chưa có công suất/THC thì hiện "chưa có" chứ không đoán.
    </p>`;

  // Mặc định tô theo chỉ tiêu đầu tiên thực sự có số. TP.HCM chưa nhập công
  // suất cảng nào, nên để nguyên mặc định "% công suất" thì mở bản đồ ra là
  // một rừng chấm xám không nói lên gì.
  const metricSel = document.getElementById("m-metric");
  const firstWithData = [...metricSel.options].find((o) =>
    data.points.some((p) => p[o.value] !== null && p[o.value] !== undefined));
  if (firstWithData) metricSel.value = firstWithData.value;

  const map = L.map("m-map").setView(cfg.center, 10);
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
  const pending = document.getElementById("m-pending");

  function remember(point) {
    overrides[point.unit] = { lat: point.lat, lon: point.lon,
                              geo_source: point.geo_source };
    const stored = saveOverrides(cfg.store, overrides);
    renderPending(stored);
  }

  // Hai cảng nằm chồng nhau gần như luôn là dấu hiệu dán nhầm link, nên báo
  // thường trực chứ không chỉ báo ngay lúc dán - lỗi này từng lọt qua và đi
  // thẳng vào repo.
  function renderClashes() {
    const box = document.getElementById("m-clash");
    const groups = [];
    for (const p of data.points) {
      const hit = groups.find((g) =>
        map.distance([g[0].lat, g[0].lon], [p.lat, p.lon]) < 50);
      if (hit) hit.push(p); else groups.push([p]);
    }
    const dup = groups.filter((g) => g.length > 1);
    box.hidden = !dup.length;
    if (!dup.length) return;
    box.innerHTML = `<b>⚠ ${dup.length} nhóm cảng đang nằm chồng nhau:</b> `
      + dup.map((g) => g.map((p) => p.unit).join(" = ")).join("; ")
      + `. Nếu đây không phải chủ ý thì nhiều khả năng đã dán nhầm link của`
      + ` cùng một cảng cho nhiều dòng - chọn lại từng cảng rồi dán link riêng.`;
  }

  function renderPending(stored = true) {
    renderClashes();
    const units = Object.keys(overrides);
    pending.hidden = !units.length;
    if (!units.length) return;
    pending.innerHTML = `
      <b>${units.length} toạ độ đã sửa nhưng chưa vào repo:</b>
      ${units.join(", ")}.
      ${stored ? "Đang giữ tạm trên trình duyệt này nên tải lại trang không mất."
               : "<b>Trình duyệt không cho lưu tạm</b> - tải lại trang là mất."}
      Bấm <b>Tải CSV toạ độ</b> rồi thay <code>${cfg.facts}</code>
      trong repo để lưu vĩnh viễn.
      <button type="button" id="m-forget">Bỏ các sửa này</button>`;
    document.getElementById("m-forget").addEventListener("click", () => {
      // Nút này xoá công sức chỉnh tay và không hoàn tác được, nên phải hỏi
      // lại kèm đúng tên những cảng sắp mất.
      const list = Object.keys(overrides).join(", ");
      if (!confirm(`Bỏ toạ độ đã sửa của: ${list}?

`
                 + `Các cảng này sẽ quay về toạ độ trong repo. `
                 + `Không hoàn tác được - nếu chưa tải CSV thì nên tải trước.`)) {
        return;
      }
      for (const unit of Object.keys(overrides)) delete overrides[unit];
      saveOverrides(cfg.store, overrides);
      renderPending();
      // Nạp lại toạ độ gốc từ JSON thay vì đoán ngược giá trị cũ.
      loadJSONFrom(cfg.agg, "map_ports").then((fresh) => {
        const byUnit = new Map(fresh.points.map((p) => [p.unit, p]));
        for (const p of data.points) {
          const src = byUnit.get(p.unit);
          if (src) Object.assign(p, { lat: src.lat, lon: src.lon,
                                      geo_source: src.geo_source });
        }
        draw();
        map.fitBounds(data.points.map((p) => [p.lat, p.lon]),
                      { padding: [40, 40] });
      });
    });
  }

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
          remember(p);
          draw();
        });
      } else {
        marker = L.circleMarker([p.lat, p.lon], style);
      }
      marker.bindPopup(popupHtml(p, data.window, ZONE_LABELS));
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

  const panel = document.getElementById("m-geo-panel");
  const msg = document.getElementById("m-geo-msg");
  const openBtn = document.getElementById("m-geo-open");
  document.getElementById("m-geo").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) document.getElementById("m-geo-link").focus();
  });
  document.getElementById("m-geo-close")
    .addEventListener("click", () => { panel.hidden = true; });

  const linkInput = document.getElementById("m-geo-link");

  function applyLink() {
    const link = linkInput.value;
    const point = data.points[+document.getElementById("m-geo-unit").value];
    const hit = parseMapsLink(link);
    openBtn.hidden = !hit.openable;
    if (hit.openable) openBtn.dataset.href = hit.openable;
    if (hit.error) {
      msg.className = "geo-msg err";
      msg.textContent = hit.error;
      return;
    }
    const moved = Math.round(map.distance([point.lat, point.lon],
                                          [hit.lat, hit.lon]));
    point.lat = hit.lat;
    point.lon = hit.lon;
    point.geo_source = "google_maps";
    remember(point);
    draw();
    map.setView([hit.lat, hit.lon], Math.max(map.getZoom(), 14));

    // Xoá ô link ngay sau khi áp. Giữ lại link cũ là cách một cảng khác bị
    // gán nhầm đúng toạ độ của cảng trước: đổi cảng rồi bấm "Lấy toạ độ" lần
    // nữa mà quên dán link mới thì link cũ vẫn còn nguyên và được áp lại.
    linkInput.value = "";
    linkInput.focus();

    const clash = data.points.filter((p) => p !== point
      && map.distance([p.lat, p.lon], [hit.lat, hit.lon]) < 50);
    msg.className = clash.length ? "geo-msg warn" : "geo-msg ok";
    msg.textContent = `${point.unit}: ${hit.lat}, ${hit.lon}`
      + ` (dời ${moved.toLocaleString("vi-VN")} m).`
      + (clash.length
         ? ` ⚠ Trùng chỗ với ${clash.map((p) => p.unit).join(", ")}`
           + ` - kiểm tra lại xem có dán nhầm link của cảng khác không.`
         : ` Bấm "Tải CSV toạ độ" để lưu lại.`);
  }

  document.getElementById("m-geo-apply").addEventListener("click", applyLink);
  document.getElementById("m-geo-link").addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyLink();
  });
  openBtn.addEventListener("click", () =>
    window.open(openBtn.dataset.href, "_blank", "noopener"));

  document.getElementById("m-export").addEventListener("click", () => {
    const blob = new Blob(["﻿" + toCsv(data.points, hasVolumeKey)],
                          { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "port_facts.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  renderPending();
  draw();
  renderClashes();
  map.fitBounds(data.points.map((p) => [p.lat, p.lon]), { padding: [40, 40] });
}
