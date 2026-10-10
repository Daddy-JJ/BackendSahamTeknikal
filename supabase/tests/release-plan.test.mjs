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

test("complete 001-011 release applies in order, preserves live mode, and planned replay is empty", async () => {
  const db = new PGlite();
  try {
    await bootstrap(db);
    const history = [];
    for (const m of pendingMigrations(release, history)) {
      await db.exec(migrationSql(m));
      // Simulated apply-once history; this is NOT a hosted CLI migration test.
      history.push(m.version);
    }
    assert.equal(history.length, release.migrations.length);
    assert.deepEqual(pendingMigrations(release, history), []);
    assert.deepEqual((await db.query("select data_mode from public.deployment_settings")).rows,
      [{data_mode:"live"}]);
    assert.equal((await db.query("select count(*)::int n from public.actual_trades")).rows[0].n, 0);
    assert.equal((await db.query("select count(*)::int n from public.app_members")).rows[0].n, 0);
    await db.exec(migrationSql(release.migrations.find(m => m.version === "202609300006"))); // 006 is replace-only.
    await db.exec(migrationSql(release.migrations.find(m => m.version === "202610010007"))); // 007 is replace-only.
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

test("existing 001 upgrades with 002-011; a failed 005 rolls back DDL and can resume", async () => {
  const db = new PGlite();
  try {
    await bootstrap(db);
    await db.exec(migrationSql(release.migrations[0]));
    const pending = pendingMigrations(release, [release.migrations[0].version]);
    assert.equal(pending.length, release.migrations.length - 1);
    for (const m of pending.slice(0, 3)) await db.exec(migrationSql(m));
    const actual = migrationSql(pending[3]);
    await assert.rejects(() => db.exec(actual.replace(/commit;\s*$/, () =>
      "do $$ begin raise exception 'injected_release_failure'; end $$; commit;")), /injected_release_failure/);
    await db.exec("rollback");
    assert.equal((await db.query("select to_regclass('public.actual_trades') t")).rows[0].t, null);
    await db.exec(actual);
    for (const migration of pending.slice(4)) await db.exec(migrationSql(migration));
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


test("populated 001-009 upgrades to010 without changing runtime, actual ledger or existing reporting values", async () => {
  const db = new PGlite();
  try {
    await bootstrap(db);
    const previous=release.migrations.filter(m=>m.version<'202610080010');
    for(const m of previous) await db.exec(migrationSql(m));
    await db.exec(`create or replace function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      insert into auth.users values('11111111-1111-4111-8111-111111111111');
      insert into public.app_members(user_id) values('11111111-1111-4111-8111-111111111111');
      set role service_role;
      select public.init_paper_model_v1('11111111-1111-4111-8111-111111111111','live');
      select public.commit_paper_session_v1('11111111-1111-4111-8111-111111111111','live',0,'upgrade-checkpoint','2026-10-08','{"experiments":{},"trades":{}}','{}');
      reset role;
      insert into public.scan_runs(namespace,run_digest,data_mode,session_date,status,coverage_valid,coverage_total,snapshot)
      values('forward',repeat('a',64),'live','2026-10-08','partial',95,100,'{}');
      select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',false);
      set role authenticated;`);
    const apply=async(action,id,payload)=>(await db.query('select public.apply_actual_journal($1,$2,$3::jsonb,$4) r',[action,id,JSON.stringify(payload),crypto.randomUUID()])).rows[0].r;
    const id=(await apply('create',null,{ticker:'TEST',primary_strategy:'MACD_EMA200_V1',initial_stop:925,exit_policy_snapshot:{version:'fixed2r-v1',mode:'fixed_rr',target_r:2}})).trade_id;
    await apply('fill',id,{side:'buy',quantity:12600,price_idr:1000,fee_idr:18900,fee_status:'actual',filled_at:'2026-10-08T03:00:00Z',expected_revision:1});
    await apply('finalize',id,{expected_revision:2});
    await apply('fill',id,{side:'sell',quantity:12600,price_idr:1150,fee_idr:36225,fee_status:'actual',filled_at:'2026-10-09T03:00:00Z',expected_revision:3});
    const read=async fn=>(await db.query(`select public.${fn}() r`)).rows[0].r;
    const actualRead=async()=>(await db.query("select public.read_trade_reporting_v1('actual') r")).rows[0].r;
    const paperBefore=await read('read_trade_reporting_v1');
    const evaluationBefore=await read('read_signal_evaluation_v1');
    const actualBefore=await actualRead();
    assert.equal(Object.hasOwn(paperBefore,'scanner_coverage'),false);
    assert.equal(actualBefore.summary.net_pnl_idr,1834875);
    await db.exec('reset role');
    const state=async()=>(await db.query(`select jsonb_build_object(
      'models',(select jsonb_agg(to_jsonb(x)) from public.paper_models x),
      'requests',(select jsonb_agg(to_jsonb(x)) from public.paper_runtime_requests x),
      'settings',(select jsonb_agg(to_jsonb(x)) from public.deployment_settings x),
      'scans',(select jsonb_agg(to_jsonb(x)) from public.scan_runs x),
      'actual_trades',(select jsonb_agg(to_jsonb(x)) from public.actual_trades x),
      'actual_fills',(select jsonb_agg(to_jsonb(x)) from public.actual_fills x)) value`)).rows[0].value;
    const before=await state();
    const pending=pendingMigrations(release,previous.map(m=>m.version));
    assert.deepEqual(pending.map(m=>m.version),['202610080010','202610100011']);
    await db.exec(migrationSql(pending[0]));
    assert.deepEqual(await state(),before);
    await db.exec('set role authenticated');
    const scanner={status:'partial',session_date:'2026-10-08',coverage_valid:95,coverage_total:100};
    assert.deepEqual(await read('read_trade_reporting_v1'),{...paperBefore,scanner_coverage:scanner});
    assert.deepEqual(await read('read_signal_evaluation_v1'),{...evaluationBefore,scanner_coverage:scanner});
    assert.deepEqual(await actualRead(),{...actualBefore,scanner_coverage:null});
  } finally { await db.close(); }
});
