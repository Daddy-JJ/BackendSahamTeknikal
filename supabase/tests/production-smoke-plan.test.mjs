// Local SQL only: validates executable production smoke assets, not hosted proof.
import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

async function setup() {
  const db = new PGlite();
  await db.exec(`create role anon nologin; create role authenticated nologin;
    create role service_role nologin bypassrls; create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema auth,public to anon,authenticated,service_role;
    grant execute on function auth.uid() to anon,authenticated,service_role;`);
  const release=JSON.parse(readFileSync(new URL('../release-manifest.json',import.meta.url),'utf8'));
  for (const m of release.migrations) {
    await db.exec(readFileSync(new URL('../migrations/'+m.file,import.meta.url),'utf8'));
  }
  await db.exec(`insert into auth.users values ('11111111-1111-4111-8111-111111111111');
    insert into public.app_members(user_id) values ('11111111-1111-4111-8111-111111111111');
    create schema supabase_migrations;
    create table supabase_migrations.schema_migrations(version text primary key);
    insert into supabase_migrations.schema_migrations values ('202610010007');`);
  return db;
}
const asset = name => readFileSync(new URL('../operations/'+name,import.meta.url),'utf8');

for (const name of ['production_actual_rollback_smoke.sql',
  'production_actual_cursor_rollback_smoke.sql']) {
  test(name+' executes financial assertions and leaves no journal/audit rows',async()=>{
    const db=await setup();
    try {
      const sql=asset(name);
      assert.ok(sql.trimEnd().endsWith('rollback;'));
      assert.ok(!/\bcommit\s*;/i.test(sql.replaceAll(/^--.*$/gm,'')));
      const results=await db.exec(sql);
      assert.ok(results.some(r=>r.rows.length>0));
      const count=await db.query(`select
        (select count(*)::int from actual_trades) trades,
        (select count(*)::int from actual_fills) fills,
        (select count(*)::int from actual_journal_requests) receipts,
        (select count(*)::int from audit_events) audits,
        (select bool_and(enabled) from app_members) owner_enabled,
        (select data_mode from deployment_settings) mode`);
      assert.deepEqual(count.rows[0],{trades:0,fills:0,receipts:0,audits:0,
        owner_enabled:true,mode:'live'});
    } finally { await db.close(); }
  });
}

test('production smoke rejects fixture mode and missing release history',async()=>{
  const db=await setup();
  try {
    await db.exec("update deployment_settings set data_mode='fixture'");
    await assert.rejects(()=>db.exec(asset('production_actual_rollback_smoke.sql')),
      /production_live_required/);
    await db.exec('rollback');
    await db.exec("update deployment_settings set data_mode='live'; delete from supabase_migrations.schema_migrations");
    await assert.rejects(()=>db.exec(asset('production_actual_rollback_smoke.sql')),
      /production_release007_required/);
    await db.exec('rollback');
  } finally { await db.close(); }
});
