import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { before, after, beforeEach, afterEach, test } from "node:test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const owner = "11111111-1111-4111-8111-111111111111";
const outsider = "22222222-2222-4222-8222-222222222222";
const otherOwner = "33333333-3333-4333-8333-333333333333";
const requestId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const root = new URL("../", import.meta.url);
const python = fileURLToPath(new URL(process.platform === "win32" ? "../../scanner/.venv/Scripts/python.exe" : "../../scanner/.venv/bin/python", import.meta.url));
const payload = JSON.parse(execFileSync(python,
  [fileURLToPath(new URL("./export_scan_fixture.py", import.meta.url))], { encoding: "utf8" }));
const firstSignal = payload.p_signals[0].id;
const db = new PGlite();
const sql = (query, args = []) => db.query(query, args);
const publish = (p = payload) => sql("select public.publish_scan($1::jsonb,$2::jsonb) as result",
  [JSON.stringify(p.p_run), JSON.stringify(p.p_signals)]);
async function role(name, uid = "") {
  assert.ok(["anon", "authenticated", "service_role"].includes(name));
  await db.exec("set local role " + name);
  await sql("select set_config('request.jwt.claim.sub',$1,true)", [uid]);
}
async function denied(fn, code) {
  await db.exec("savepoint expected_failure");
  await assert.rejects(fn, (e) => { assert.equal(e.code, code); return true; });
  await db.exec("rollback to savepoint expected_failure");
}
before(async () => {
  await db.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
    $$;
    grant usage on schema auth, public to anon,authenticated,service_role;
    grant execute on function auth.uid() to anon,authenticated,service_role;
  `);
  await db.exec(readFileSync(new URL("migrations/202609290001_scan_foundation.sql",root),"utf8"));
  await sql("insert into auth.users values ($1),($2),($3)",[owner,outsider,otherOwner]);
  await sql("insert into public.app_members(user_id) values ($1),($2)",[owner,otherOwner]);
});
beforeEach(async () => { await db.exec("begin"); });
afterEach(async () => { await db.exec("rollback"); });
after(async () => { await db.close(); });
async function seed() {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const result = (await publish()).rows[0].result;
  assert.ok(result.inserted > 0);
  return result;
}

test("production defaults reject fixture, no partial rows are stored",async () => {
  await role("service_role");
  await denied(() => publish(), "22023");
  assert.equal((await sql("select count(*)::int as n from public.scan_runs")).rows[0].n,0);
});
test("atomic publication and replay preserve one run, signal and audit set",async () => {
  const initial = await seed();
  const replay = (await publish()).rows[0].result;
  assert.equal(replay.run_id,initial.run_id);
  assert.equal(replay.replayed,true);
  assert.equal((await sql("select count(*)::int as n from public.scan_runs")).rows[0].n,1);
  assert.equal((await sql("select count(*)::int as n from public.signals")).rows[0].n,payload.p_signals.length);
  assert.equal((await sql("select count(*)::int as n from public.audit_events")).rows[0].n,1);
});
test("anon denied read, write and RPC execution",async () => {
  await seed();
  await role("anon");
  for (const query of ["select * from public.signals",
    "insert into public.app_members(user_id) values ('"+outsider+"')",
    "update public.signals set ticker='spoof'",
    "delete from public.scan_runs"]) {
    await denied(() => sql(query),"42501");
  }
  await denied(() => publish(),"42501");
});
test("authenticated outsider sees no app data and cannot promote membership",async () => {
  await seed();
  await role("authenticated",outsider);
  for (const table of ["signals","scan_runs","scan_run_items","scan_run_signals","app_members","deployment_settings","audit_events"]) {
    assert.equal((await sql("select count(*)::int as n from public."+table)).rows[0].n,0);
  }
  await denied(() => sql("insert into public.app_members(user_id) values ($1)",[outsider]),"42501");
  await denied(() => sql("select public.set_signal_action($1,'planned',0,$2)",[firstSignal,requestId]),"42501");
  await denied(() => publish(),"42501");
});
test("owner can read snapshots but cannot directly change data or call publisher",async () => {
  await seed();
  await role("authenticated",owner);
  assert.equal((await sql("select count(*)::int as n from public.signals")).rows[0].n,payload.p_signals.length);
  for (const query of ["update public.signals set ticker='spoof'",
    "delete from public.signals","insert into public.scan_runs select * from public.scan_runs",
    "update public.signal_actions set action='planned'"]) {
    await denied(() => sql(query),"42501");
  }
  await denied(() => publish(),"42501");
});
test("disabled owner immediately loses reads and actions",async () => {
  await seed();
  await db.exec("reset role");
  await sql("update public.app_members set enabled=false where user_id=$1",[owner]);
  await role("authenticated",owner);
  assert.equal((await sql("select count(*)::int as n from public.signals")).rows[0].n,0);
  await denied(() => sql("select public.set_signal_action($1,'planned',0,$2)",[firstSignal,requestId]),"42501");
});
test("request replay, stale revision and different-body reuse do not duplicate actions",async () => {
  await seed();
  await role("authenticated",owner);
  const call = () => sql("select public.set_signal_action($1,'planned',0,$2) as result",[firstSignal,requestId]);
  const first = (await call()).rows[0].result;
  assert.deepEqual((await call()).rows[0].result,first);
  assert.equal(first.revision,1);
  await denied(() => sql("select public.set_signal_action($1,'skipped',0,$2)",[firstSignal,requestId]),"23514");
  await denied(() => sql("select public.set_signal_action($1,'skipped',0,gen_random_uuid())",[firstSignal]),"40001");
  assert.equal((await sql("select count(*)::int as n from public.signal_actions")).rows[0].n,1);
  assert.equal((await sql("select count(*)::int as n from public.audit_events where owner_id=$1",[owner])).rows[0].n,1);
});
test("another enabled owner cannot read or change private actions using guessed IDs",async () => {
  await seed();
  await role("authenticated",owner);
  await sql("select public.set_signal_action($1,'planned',0,$2)",[firstSignal,requestId]);
  await role("authenticated",otherOwner);
  for (const table of ["signal_actions","signal_action_requests"]) {
    assert.equal((await sql("select count(*)::int as n from public."+table+" where owner_id=$1",[owner])).rows[0].n,0);
  }
  await sql("select public.set_signal_action($1,'skipped',0,$2)",[firstSignal,requestId]);
  await role("authenticated",owner);
  assert.equal((await sql("select action from public.signal_actions")).rows[0].action,"planned");
});
test("nonexistent signal rejected with no request or audit residue",async () => {
  await seed();
  await role("authenticated",owner);
  await denied(() => sql("select public.set_signal_action($1,'planned',0,$2)",["f".repeat(64),requestId]),"22023");
  assert.equal((await sql("select count(*)::int as n from public.signal_action_requests")).rows[0].n,0);
});
test("invalid second signal rolls back complete run, first signal and audit",async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const bad = structuredClone(payload);
  bad.p_signals[1] = {...bad.p_signals[0],id:"e".repeat(64),planned_entry_session:"2000-01-01"};
  await denied(() => publish(bad),"23514");
  for (const table of ["scan_runs","scan_run_items","signals","audit_events"]) {
    assert.equal((await sql("select count(*)::int as n from public."+table)).rows[0].n,0);
  }
});
test("revised input cannot overwrite a published signal",async () => {
  await seed();
  const revised = structuredClone(payload);
  revised.p_run.run_digest = "a".repeat(64);
  revised.p_signals[0].input_digest = "b".repeat(64);
  await denied(() => publish(revised),"23514");
  assert.equal((await sql("select count(*)::int as n from public.scan_runs")).rows[0].n,1);
  await db.exec("reset role");
  await denied(() => sql("update public.signals set ticker='spoof'"),"23514");
});
test("fractal guard survives fresh state on later session, without duplicate publication",async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const first = structuredClone(payload);
  first.p_signals = [first.p_signals[0]];
  first.p_signals[0].candidate.fractal_id = "synthetic-level-1";
  await publish(first);
  const next = structuredClone(first);
  next.p_run.run_digest = "c".repeat(64);
  next.p_run.session = "2030-01-02";
  next.p_signals[0].id = "d".repeat(64);
  next.p_signals[0].session = "2030-01-02";
  next.p_signals[0].planned_entry_session = "2030-01-03";
  const result = (await publish(next)).rows[0].result;
  assert.equal(result.guard_skips,1);
  assert.equal(result.inserted,0);
  assert.equal((await sql("select count(*)::int as n from public.signals")).rows[0].n,1);
});

test("every application table has RLS and no client/service direct mutation grants",async () => {
  const tables = (await sql("select tablename, rowsecurity from pg_tables where schemaname='public' order by tablename")).rows;
  assert.equal(tables.length,9);
  for (const {tablename,rowsecurity} of tables) {
    assert.equal(rowsecurity,true,tablename);
    for (const roleName of ["anon","authenticated","service_role"]) {
      const allowed = (await sql("select has_table_privilege($1,$2,'INSERT,UPDATE,DELETE,TRUNCATE') as allowed",[roleName,"public."+tablename])).rows[0].allowed;
      assert.equal(allowed,false,roleName+":"+tablename);
    }
  }
});
