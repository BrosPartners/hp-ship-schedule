// Data access. Aggregates load eagerly (small); the Parquet loads only when the
// lookup tab is first opened.
const AGG = "data/agg";
let connPromise = null;

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

export async function loadManifest() {
  const url = new URL("data/manifest.json", document.baseURI);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`không tải được manifest.json (${res.status})`);
  return res.json();
}

export function getConnection() {
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

  const manifest = await loadManifest();
  const partitions = manifest.partitions ?? [];
  if (!partitions.length) throw new Error("manifest.json không liệt kê partition nào");

  // Each monthly partition is immutable once written (only the current
  // month's file ever changes), so the browser/CDN can cache old months
  // forever - a returning visitor only re-fetches the current month.
  await Promise.all(partitions.map(async (name) => {
    const url = new URL(`data/parts/${name}`, document.baseURI);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`không tải được ${name} (${res.status})`);
    await db.registerFileBuffer(name, new Uint8Array(await res.arrayBuffer()));
  }));

  const fileList = partitions.map((name) => `'${name}'`).join(", ");
  const conn = await db.connect();
  await conn.query(`
    CREATE VIEW plans AS
      SELECT * FROM read_parquet([${fileList}], union_by_name=true);
    CREATE VIEW plans_latest AS
      SELECT * FROM (
        SELECT *, max(crawled_at) OVER (PARTITION BY plan_date) AS newest
        FROM plans
      ) WHERE crawled_at = newest;
  `);
  return conn;
}

export async function query(sql) {
  const conn = await getConnection();
  const table = await conn.query(sql);
  return table.toArray().map((row) => row.toJSON());
}

export function sqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}
