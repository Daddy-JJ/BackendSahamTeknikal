import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { cleanFoundation, catalog, compareCatalog } from "../scripts/foundation_catalog.mjs";

const reconcileSql = readFileSync(new URL("../operations/reconcile_foundation_acl.sql", import.meta.url),"utf8");

test("clean001 catalog matches itself and detects schema, body, grant, RLS and policy drift",async () => {
  const db=await cleanFoundation();
  try {
    const expected=await catalog(db);
    assert.equal(expected.length,10);
    assert.equal(compareCatalog(expected,await catalog(db)).schema_match,true);
    const cases=[
      ["alter table public.app_members alter enabled set default false","columns"],
      ["alter table public.app_members add constraint test_enabled check(enabled)","constraints"],
      ["create index test_members on public.app_members(enabled)","indexes"],
      ["alter table public.signals disable trigger immutable_record","triggers"],
      ["alter function public.is_app_owner() stable security invoker","functions"],
      ["grant update on public.signals to anon","table_grants"],
      ["grant execute on function public.publish_scan(jsonb,jsonb) to anon","function_grants"],
      ["grant update(ticker) on public.signals to anon","column_grants"],
      ["alter table public.signals disable row level security","relations"],
      ["alter policy owner_read on public.signals using(true)","policies"],
    ];
    // catalog() owns a READ ONLY transaction; restore each mutation with its inverse
    // by using a fresh in-memory database, avoiding nested transaction commits.
    for(const [mutation,category] of cases) {
      const changed=await cleanFoundation();
      try {
        await changed.exec(mutation);
        const result=compareCatalog(expected,await catalog(changed));
        assert.equal(result.schema_match,false);
        assert.ok(result.differences.includes(category));
      } finally {await changed.close();}
    }
    assert.throws(()=>compareCatalog(expected,expected.slice(1)),/incomplete/);
  } finally {await db.close();}
});

test("targeted production ACL plan restores clean001 fingerprint and keeps immutable trigger",async () => {
  const db=await cleanFoundation();
  try {
    const clean=await catalog(db);
    await db.exec("grant execute on function public.reject_immutable_mutation() to service_role");
    assert.deepEqual(compareCatalog(clean,await catalog(db)).differences,["function_grants"]);
    await db.exec(reconcileSql);
    assert.equal(compareCatalog(clean,await catalog(db)).schema_match,true);
    await db.exec(`insert into public.scan_runs(namespace,run_digest,data_mode,session_date,
      status,coverage_valid,coverage_total,snapshot) values
      ('acl_rehearsal',repeat('a',64),'live',current_date,'complete',1,1,'{}'::jsonb)`);
    await db.exec("grant update on public.scan_runs to service_role");
    await db.exec("set role service_role");
    try {
      await assert.rejects(()=>db.exec("update public.scan_runs set status='failed'"),/immutable_record/);
    } finally { await db.exec("reset role"); }
  } finally { await db.close(); }
});

test("targeted production ACL plan refuses fixture mode",async () => {
  const db=await cleanFoundation();
  try {
    await db.exec("grant execute on function public.reject_immutable_mutation() to service_role");
    await db.exec("update public.deployment_settings set data_mode='fixture'");
    await assert.rejects(()=>db.exec(reconcileSql),/production_live_mode_required/);
    await db.exec("rollback");
    assert.equal((await db.query(`select has_function_privilege('service_role',
      'public.reject_immutable_mutation()', 'EXECUTE') allowed`)).rows[0].allowed,true);
  } finally { await db.close(); }
});
