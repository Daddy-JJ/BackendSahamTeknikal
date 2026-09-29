import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { before, after, beforeEach, afterEach, test } from "node:test";
import { readFileSync } from "node:fs";

const owner = "11111111-1111-4111-8111-111111111111";
const outsider = "22222222-2222-4222-8222-222222222222";
const db = new PGlite();
const sql = (query, args = []) => db.query(query, args);
const record = {
  namespace: "forward", data_mode: "fixture", provider: "fixture",
  ticker: "DEMO-A", provider_symbol: "DEMO-A", price_basis: "synthetic", provider_version: "fixture-v1",
  input_digest: "a".repeat(64), fetched_at: "2030-01-02T13:00:00Z",
  snapshot: {
    ticker: "DEMO-A", provider: "fixture", provider_symbol: "DEMO-A",
    price_basis: "synthetic",
    bars: [{session: "2030-01-02", open: 100, high: 105, low: 99, close: 103, volume: 1000}],
    actions: [], actions_complete: true, reconciled_actions: [],
    provider_missing_sessions: [], provider_row_issues: []
  }
};
const ingest = (value = record) => sql("select public.ingest_market_series($1::jsonb) as result", [JSON.stringify(value)]);
async function role(name, uid = "") {
  await db.exec("set local role " + name);
  await sql("select set_config('request.jwt.claim.sub',$1,true)", [uid]);
}
async function denied(fn, code) {
  await db.exec("savepoint expected_failure");
  await assert.rejects(fn, (error) => { assert.equal(error.code, code); return true; });
  await db.exec("rollback to savepoint expected_failure");
}
before(async () => {
  await db.exec([
    "create role anon nologin",
    "create role authenticated nologin",
    "create role service_role nologin bypassrls",
    "create schema auth",
    "create table auth.users(id uuid primary key)",
    "create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$",
    "grant usage on schema auth, public to anon,authenticated,service_role",
    "grant execute on function auth.uid() to anon,authenticated,service_role"
  ].join(";") + ";");
  await db.exec(readFileSync(new URL("../migrations/202609290001_scan_foundation.sql", import.meta.url), "utf8"));
  await db.exec(readFileSync(new URL("../migrations/202609290002_market_series_revisions.sql", import.meta.url), "utf8"));
  await sql("insert into auth.users values ($1),($2)", [owner, outsider]);
  await sql("insert into public.app_members(user_id) values ($1)", [owner]);
});
beforeEach(async () => { await db.exec("begin"); });
afterEach(async () => { await db.exec("rollback"); });
after(async () => { await db.close(); });

test("fixture market revisions are blocked in production mode", async () => {
  await role("service_role");
  await denied(() => ingest(), "22023");
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 0);
});
test("same content replays, changed bars create an immutable second revision", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const first = (await ingest()).rows[0].result;
  const replay = (await ingest()).rows[0].result;
  assert.equal(first.replayed, false);
  assert.equal(replay.replayed, true);
  assert.equal(replay.revision_id, first.revision_id);
  const changed = structuredClone(record);
  changed.input_digest = "b".repeat(64);
  changed.snapshot.bars[0].close = 104;
  const second = (await ingest(changed)).rows[0].result;
  assert.notEqual(second.revision_id, first.revision_id);
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 2);
  assert.equal((await sql("select count(*)::int as n from public.market_bar_revisions")).rows[0].n, 2);
  const old = (await sql("select bar from public.market_bar_revisions order by revision_seq")).rows[0].bar;
  assert.equal(old.close, 103);
  await denied(() => sql("update public.market_series_revisions set ticker='SPOOF'"), "42501");
  await db.exec("reset role");
  await denied(() => sql("update public.market_series_revisions set ticker='SPOOF'"), "23514");
});
test("unchanged bars are not duplicated by a new series receipt", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  await ingest();
  const later = structuredClone(record);
  later.input_digest = "c".repeat(64);
  later.snapshot.actions = [{session: "2030-01-02", kind: "dividend", value: "1"}];
  const receipt = (await ingest(later)).rows[0].result;
  assert.equal(receipt.bars_changed, 0);
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 2);
  assert.equal((await sql("select count(*)::int as n from public.market_bar_revisions")).rows[0].n, 1);
});
test("duplicate sessions roll back receipt and bar rows", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const duplicate = structuredClone(record);
  duplicate.snapshot.bars.push(structuredClone(duplicate.snapshot.bars[0]));
  await denied(() => ingest(duplicate), "22023");
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 0);
  assert.equal((await sql("select count(*)::int as n from public.market_bar_revisions")).rows[0].n, 0);
});
test("no-bar provider result remains an auditable missing-data receipt", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  const missing = structuredClone(record);
  missing.input_digest = "d".repeat(64);
  missing.snapshot.bars = [];
  missing.snapshot.provider_row_issues = [{session: "2030-01-02", code: "incomplete_ohlcv"}];
  const receipt = (await ingest(missing)).rows[0].result;
  assert.equal(receipt.bars_changed, 0);
  assert.equal((await sql("select bar_count from public.market_series_revisions")).rows[0].bar_count, 0);
  assert.equal((await sql("select count(*)::int as n from public.market_bar_revisions")).rows[0].n, 0);
});
test("digest reuse with changed content is rejected without overwrite", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  await ingest();
  const changed = structuredClone(record);
  changed.snapshot.bars[0].close = 104;
  await denied(() => ingest(changed), "23514");
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 1);
});
test("owner alone reads; anon, outsider and direct writes are denied", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("service_role");
  await ingest();
  await role("authenticated", owner);
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 1);
  await denied(() => ingest(), "42501");
  await denied(() => sql("delete from public.market_series_revisions"), "42501");
  await role("authenticated", outsider);
  assert.equal((await sql("select count(*)::int as n from public.market_series_revisions")).rows[0].n, 0);
  await role("anon");
  await denied(() => sql("select * from public.market_series_revisions"), "42501");
  await denied(() => ingest(), "42501");
});
