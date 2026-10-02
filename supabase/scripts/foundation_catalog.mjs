// Generate a clean001 reference in memory, or compare a read-only remote export.
import { PGlite } from "@electric-sql/pglite";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

export const catalogSql = readFileSync(new URL("../operations/foundation_catalog.sql", import.meta.url), "utf8");
export async function cleanFoundation() {
  const db = new PGlite();
  await db.exec(`create role anon nologin; create role authenticated nologin;
    create role service_role nologin bypassrls; create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$select null::uuid$$;`);
  await db.exec(readFileSync(new URL("../migrations/202609290001_scan_foundation.sql", import.meta.url), "utf8"));
  return db;
}
export async function catalog(db) {
  return (await db.exec(catalogSql)).flatMap(r => r.rows).filter(r => r.category);
}
export function compareCatalog(expected, actual) {
  if (!Array.isArray(actual) || actual.length !== expected.length ||
      new Set(actual.map(r => r.category)).size !== expected.length) throw new Error("catalog_incomplete");
  const differences = expected.filter(e => {
    const a = actual.find(r => r.category === e.category);
    return !a || a.object_count !== e.object_count || a.sha256 !== e.sha256;
  }).map(e => e.category);
  return {schema_match: differences.length === 0, differences, history_repaired: false};
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const db = await cleanFoundation();
  try {
    const expected = await catalog(db);
    if (process.argv[2] === "--compare") {
      const actual = JSON.parse(readFileSync(process.argv[3], "utf8"));
      const result = compareCatalog(expected, actual);
      console.log(JSON.stringify(result, null, 2));
      if (!result.schema_match) process.exitCode = 2;
    } else if (process.argv[2] === "--out") {
      writeFileSync(process.argv[3], JSON.stringify(expected, null, 2) + "\n", {flag:"wx"});
      console.log("Clean001 catalog generated; no remote access.");
    } else {
      console.log(JSON.stringify({query_sha256:createHash("sha256").update(catalogSql.replaceAll("\r\n","\n")).digest("hex"), expected}, null, 2));
    }
  } finally { await db.close(); }
}
