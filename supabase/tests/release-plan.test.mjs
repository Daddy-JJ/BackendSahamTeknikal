import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, cpSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, basename, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { loadRelease, pendingMigrations } from "../scripts/plan_production_release.mjs";

const release = loadRelease();
const migrationSql = m => readFileSync(new URL("../migrations/" + m.file, import.meta.url), "utf8");
async function bootstrap(db) {
  await db.exec(`create role anon nologin; create role authenticated nologin;
    create role service_role nologin bypassrls; create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;`);
}

test("complete 001-007 release applies in order, preserves live mode, and planned replay is empty", async () => {
  const db = new PGlite();
  try {
    await bootstrap(db);
    const history = [];
    for (const m of pendingMigrations(release, history)) {
      await db.exec(migrationSql(m));
      // Simulated apply-once history; this is NOT a hosted CLI migration test.
      history.push(m.version);
    }
    assert.equal(history.length, 7);
    assert.deepEqual(pendingMigrations(release, history), []);
    assert.deepEqual((await db.query("select data_mode from public.deployment_settings")).rows,
      [{data_mode:"live"}]);
    assert.equal((await db.query("select count(*)::int n from public.actual_trades")).rows[0].n, 0);
    assert.equal((await db.query("select count(*)::int n from public.app_members")).rows[0].n, 0);
    await db.exec(migrationSql(release.migrations.at(-2))); // 006 is replace-only.
    await db.exec(migrationSql(release.migrations.at(-1))); // 007 is replace-only.
    assert.match((await db.query(`select pg_get_functiondef(
      'public.apply_actual_journal(text,uuid,jsonb,uuid)'::regprocedure) def`)).rows[0].def, /PT412/);
    const preflight = await db.exec(readFileSync(new URL("../operations/production_preflight.sql", import.meta.url), "utf8"));
    assert.equal(preflight.flatMap(r => r.rows).find(r => r.check_name === "database").result.read_only, "on");
    const relationship = preflight.flatMap(r => r.rows).find(r => r.check_name === "correction_relationship").result;
    assert.equal(relationship.length, 1);
    assert.match(relationship[0], /FOREIGN KEY \(fill_id\) REFERENCES actual_fills\(id\)/);
    assert.equal((await db.query(`select has_function_privilege('authenticated',
      'public.apply_actual_journal(text,uuid,jsonb,uuid)', 'EXECUTE') allowed`)).rows[0].allowed, true);
    await db.exec(readFileSync(new URL("../operations/production_contain_journal.sql", import.meta.url), "utf8"));
    assert.equal((await db.query(`select has_function_privilege('authenticated',
      'public.apply_actual_journal(text,uuid,jsonb,uuid)', 'EXECUTE') allowed`)).rows[0].allowed, false);
    assert.equal((await db.query("select count(*)::int n from public.actual_trades")).rows[0].n, 0);
  } finally { await db.close(); }
});

test("existing 001 upgrades with 002-007; a failed 005 rolls back DDL and can resume", async () => {
  const db = new PGlite();
  try {
    await bootstrap(db);
    await db.exec(migrationSql(release.migrations[0]));
    const pending = pendingMigrations(release, [release.migrations[0].version]);
    assert.equal(pending.length, 6);
    for (const m of pending.slice(0, 3)) await db.exec(migrationSql(m));
    const actual = migrationSql(pending[3]);
    await assert.rejects(() => db.exec(actual.replace(/commit;\s*$/, () =>
      "do $$ begin raise exception 'injected_release_failure'; end $$; commit;")), /injected_release_failure/);
    await db.exec("rollback");
    assert.equal((await db.query("select to_regclass('public.actual_trades') t")).rows[0].t, null);
    await db.exec(actual);
    await db.exec(migrationSql(pending[4]));
    await db.exec(migrationSql(pending[5]));
    assert.equal((await db.query("select count(*)::int n from public.actual_journal_requests")).rows[0].n, 0);
  } finally { await db.close(); }
});

test("unknown, gapped, duplicated and unreconciled history fail closed", () => {
  assert.throws(() => pendingMigrations(release, null), /reconciliation_required/);
  for (const history of [["unknown"], [release.migrations[1].version],
    [release.migrations[0].version, release.migrations[0].version]]) {
    assert.throws(() => pendingMigrations(release, history), /not_exact_prefix/);
  }
});

test("changed applied SQL is rejected by the frozen release checksum", () => {
  const dir = mkdtempSync(join(tmpdir(), "idx-release-check-"));
  try {
    mkdirSync(join(dir, "migrations"));
    cpSync(new URL("../release-manifest.json", import.meta.url), join(dir, "release-manifest.json"));
    for (const m of release.migrations) writeFileSync(join(dir, "migrations", m.file), migrationSql(m));
    writeFileSync(join(dir, "migrations", release.migrations[0].file), "-- changed\n");
    assert.throws(() => loadRelease(pathToFileURL(dir + "/")), /checksum_mismatch/);
  } finally {
    assert.equal(dirname(resolve(dir)), resolve(tmpdir()));
    assert.ok(basename(dir).startsWith("idx-release-check-"));
    rmSync(dir, {recursive:true});
  }
});
