// Data access. Aggregates load eagerly (small); a Parquet dataset loads only
// when a tab that needs it is first opened.
const AGG = "data/agg";

// Hai cảng là hai bộ Parquet riêng, schema khác nhau. Dùng chung một instance
// DuckDB nhưng đăng ký riêng từng bộ và đặt tên view khác nhau, thay vì dựng
// hai instance WASM - mỗi instance là một worker và vài chục MB.
const DATASETS = {
  hp: { base: "data", view: "plans" },
  hcm: { base: "data/hcm", view: "hcm_plans" },
};

let connPromise = null;
const registered = new Map();

export async function loadJSON(name) {
  return loadJSONFrom(AGG, name);
}

// Generic variant for datasets outside data/agg (e.g. the TP.HCM dataset,
// which lives under data/hcm/agg).
export async function loadJSONFrom(base, name) {
  const url = new URL(`${base}/${name}.json`, document.baseURI);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`không tải được ${name}.json (${res.status})`);
  return res.json();
}

export async function loadManifest(dataset = "hp") {
  const { base } = DATASETS[dataset];
  const url = new URL(`${base}/manifest.json`, document.baseURI);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`không tải được manifest.json (${res.status})`);
  return res.json();
}

function getConnection() {
  if (!connPromise) connPromise = openDuckDB();
  return connPromise;
}

async function openDuckDB() {
  const duckdb = await import(
    "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm"
  );
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const worker = await duckdb.createWorker(bundle.mainWorker);
  const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  const conn = await db.connect();
  conn._db = db;
  return conn;
}

async function registerDataset(dataset) {
  const { base, view } = DATASETS[dataset];
  const conn = await getConnection();
  const manifest = await loadManifest(dataset);
  const partitions = manifest.partitions ?? [];
  if (!partitions.length) throw new Error("manifest.json không liệt kê partition nào");

  // Each monthly partition is immutable once written (only the current
  // month's file ever changes), so the browser/CDN can cache old months
  // forever - a returning visitor only re-fetches the current month.
  await Promise.all(partitions.map(async (name) => {
    const url = new URL(`${base}/parts/${name}`, document.baseURI);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`không tải được ${name} (${res.status})`);
    // Tên file hai bộ trùng nhau (ship_plan_YYYY-MM.parquet) nên phải đặt tiền
    // tố theo dataset, không thì bộ đăng ký sau đè lên bộ trước.
    await conn._db.registerFileBuffer(`${dataset}_${name}`,
                                      new Uint8Array(await res.arrayBuffer()));
  }));

  const fileList = partitions.map((name) => `'${dataset}_${name}'`).join(", ");
  await conn.query(`
    CREATE VIEW ${view} AS
      SELECT * FROM read_parquet([${fileList}], union_by_name=true);
    CREATE VIEW ${view}_latest AS
      SELECT * FROM (
        SELECT *, max(crawled_at) OVER (PARTITION BY plan_date) AS newest
        FROM ${view}
      ) WHERE crawled_at = newest;
  `);
  return view;
}

/** Tên view của một bộ dữ liệu, đăng ký lần đầu nếu chưa có. */
export async function ensureDataset(dataset = "hp") {
  if (!registered.has(dataset)) registered.set(dataset, registerDataset(dataset));
  return registered.get(dataset);
}

export async function query(sql, dataset = "hp") {
  await ensureDataset(dataset);
  const conn = await getConnection();
  const table = await conn.query(sql);
  return table.toArray().map((row) => row.toJSON());
}

export function sqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}
