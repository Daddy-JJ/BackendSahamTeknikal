// Offline planner only. Never connects, repairs history, or executes SQL.
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const base = new URL("../", import.meta.url);
export function loadRelease(root = base) {
  const manifest = JSON.parse(readFileSync(new URL("release-manifest.json", root), "utf8"));
  const names = readdirSync(new URL("migrations/", root)).filter(n => n.endsWith(".sql")).sort();
  if (JSON.stringify(names) !== JSON.stringify(manifest.migrations.map(m => m.file))) {
    throw new Error("migration_chain_changed_review_manifest");
  }
  for (const migration of manifest.migrations) {
    const sql = readFileSync(new URL("migrations/" + migration.file, root), "utf8")
      .replaceAll("\r\n", "\n");
    if (createHash("sha256").update(sql).digest("hex") !== migration.sha256_lf) {
      throw new Error("migration_checksum_mismatch:" + migration.version);
    }
    if (!sql.includes("\nbegin;\n") || !sql.trimEnd().endsWith("commit;")) {
      throw new Error("migration_transaction_missing");
    }
  }
  return manifest;
}

export function pendingMigrations(release, reviewedHistory) {
  if (reviewedHistory === null) throw new Error("migration_history_reconciliation_required");
  if (!Array.isArray(reviewedHistory)) throw new Error("invalid_migration_history");
  const versions = release.migrations.map(m => m.version);
  if (reviewedHistory.length > versions.length || reviewedHistory.some((v, i) => v !== versions[i])) {
    throw new Error("migration_history_not_exact_prefix");
  }
  return release.migrations.slice(reviewedHistory.length);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const release = loadRelease();
    const historyFile = process.argv[2];
    const pending = pendingMigrations(release,
      historyFile ? JSON.parse(readFileSync(historyFile, "utf8")) : null);
    console.log(JSON.stringify({project_ref: release.project_ref,
      manifest: fileURLToPath(new URL("release-manifest.json", base)),
      pending, execution: "none; offline plan only", deployment_authorized: false}, null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}
