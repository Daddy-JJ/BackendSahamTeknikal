import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { before, after, beforeEach, afterEach, test } from "node:test";
import { readFileSync } from "node:fs";
import { actualJournalCsv, COLUMNS } from "../../contracts/actual-journal-export.mjs";

const owner = "11111111-1111-4111-8111-111111111111";
const outsider = "22222222-2222-4222-8222-222222222222";
const otherOwner = "33333333-3333-4333-8333-333333333333";
const db = new PGlite();
const sql = (query, args = []) => db.query(query, args);
async function role(name, uid = "") {
  await db.exec("set local role " + name);
  await sql("select set_config('request.jwt.claim.sub',$1,true)", [uid]);
}
async function denied(fn, code) {
  await db.exec("savepoint expected_failure");
  await assert.rejects(fn, e => { assert.equal(e.code, code); return true; });
  await db.exec("rollback to savepoint expected_failure");
}
const apply = (action, trade, payload, requestId = crypto.randomUUID()) =>
  sql("select public.apply_actual_journal($1,$2,$3::jsonb,$4) as result",
    [action, trade, JSON.stringify(payload), requestId]).then(r => r.rows[0].result);
const base = {
  ticker: "TEST", primary_strategy: "MACD_EMA200_V1",
  initial_stop: 95, exit_policy_snapshot: { version: "fixed2r-v1", mode: "fixed_rr", target_r: 2 },
};
const fill = (side, quantity, price_idr, fee_idr, expected_revision, day) => ({
  side, quantity, price_idr, fee_idr, fee_status: "actual",
  filled_at: day, expected_revision,
});
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
  for (const name of ["202609290001_scan_foundation.sql",
    "202609290004_publication_deadline.sql",
    "202609290005_actual_journal.sql",
    "202609300006_actual_journal_conflict_http.sql"]) {
    await db.exec(readFileSync(new URL("../migrations/" + name, import.meta.url), "utf8"));
  }
  await sql("insert into auth.users values ($1),($2),($3)", [owner, outsider, otherOwner]);
  await sql("insert into public.app_members(user_id) values ($1),($2)", [owner,otherOwner]);
});
beforeEach(async () => { await db.exec("begin"); });
afterEach(async () => { await db.exec("rollback"); });
after(async () => { await db.close(); });

test("rollback-only development SQL smoke validates its assertions before remote use", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await sql("update public.app_members set enabled=false where user_id=$1",[otherOwner]);
  const smoke=readFileSync(new URL('./dev_actual_smoke.sql',import.meta.url),'utf8')
    .replace('begin;','').replace(/\nrollback;\s*$/,'\n');
  const results=await db.exec(smoke);
  assert.equal(results.at(-1).rows[0].m4_sql_smoke.sql_ledger_passed,true);
  assert.equal(results.at(-1).rows[0].m4_sql_smoke.disabled_owner_sql_passed,true);
});

test("rollback-only 201-closed-trade development cursor smoke is executable", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await sql("update public.app_members set enabled=false where user_id=$1",[otherOwner]);
  const smoke=readFileSync(new URL('./dev_actual_cursor_smoke.sql',import.meta.url),'utf8')
    .replace('begin;','').replace(/\nrollback;\s*$/,'\n');
  const results=await db.exec(smoke);
  assert.deepEqual(results.at(-1).rows[0].m4_cursor_smoke,{
    closed:201,page1:200,page2:1,has_more_after_page2:false,
    net_pnl_idr:2010,rollback_only:true,real_owner_jwt:false,
  });
});

test("frontend named RPC arguments and explicit latest-correction FK are stable", async () => {
  for (const [name,args] of [
    ["apply_actual_journal",["p_action","p_trade_id","p_payload","p_request_id"]],
    ["actual_journal_analytics",["p_from","p_to","p_strategy","p_exit_version","p_exit_snapshot"]],
    ["export_actual_journal",["p_from","p_to","p_strategy","p_exit_version","p_exit_snapshot","p_after","p_limit","p_status"]],
  ]) {
    const rows=(await sql("select proargnames from pg_proc where pronamespace='public'::regnamespace and proname=$1",[name])).rows;
    assert.equal(rows.length,1,"PostgREST overload ambiguity: "+name);
    assert.deepEqual(rows[0].proargnames,args);
  }
  const fk=(await sql(`select pg_get_constraintdef(oid) definition from pg_constraint
    where conrelid='public.actual_fill_corrections'::regclass
      and conname='actual_fill_corrections_fill_id_fkey'`)).rows;
  assert.equal(fk.length,1);
  assert.equal(fk[0].definition,"FOREIGN KEY (fill_id) REFERENCES actual_fills(id)");
  await role("authenticated",owner);
  for (const snapshot of [
    {version:"actual-fixed2r-v1",mode:"fixed_rr",target_r:2},
    {version:"actual-ma10-v1",mode:"ma_close",ma_type:"SMA",period:10},
    {version:"actual-manual-v1",mode:"manual"},
  ]) {
    await apply("create",null,{...base,exit_policy_snapshot:snapshot});
    const a=(await sql("select public.actual_journal_analytics(p_exit_snapshot=>$1) a",[JSON.stringify(snapshot)])).rows[0].a;
    assert.equal(a.draft,1);
    const e=(await sql("select public.export_actual_journal(p_exit_snapshot=>$1,p_status=>'closed',p_limit=>200,p_after=>null) e",[JSON.stringify(snapshot)])).rows[0].e;
    assert.deepEqual(e.rows,[]); assert.equal(e.has_more,false);
  }
});

test("SOT multiple fills, partial exits, actual fees and frozen initial risk", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("authenticated", owner);
  const created = await apply("create", null, base);
  const id = created.trade_id;
  let r = await apply("fill", id, fill("buy",100,100,25,1,"2026-09-01T03:00:00Z"));
  r = await apply("fill", id, fill("buy",100,102,25,2,"2026-09-01T04:00:00Z"));
  r = await apply("finalize", id, { expected_revision: 3 });
  assert.equal(Number(r.ledger.initial_risk_idr),1200);
  r = await apply("stop", id, {expected_revision:4,new_stop:99,reason:"Manual trailing stop"});
  assert.equal(Number(r.ledger.initial_risk_idr),1200);
  r = await apply("fill", id, fill("sell",100,105,25,5,"2026-09-03T03:00:00Z"));
  assert.equal(r.ledger.status,"open");
  assert.equal(Number(r.ledger.realized_pnl_idr),350);
  assert.equal(r.ledger.realized_r,null);
  r = await apply("fill", id, fill("sell",100,108,25,6,"2026-09-04T03:00:00Z"));
  assert.equal(r.ledger.status,"closed");
  assert.equal(Number(r.ledger.realized_pnl_idr),1000);
  assert.equal(Number(r.ledger.initial_risk_idr),1200);
  assert.ok(Math.abs(Number(r.ledger.realized_r)-5/6)<1e-10);
  const trade = (await sql("select * from public.actual_trades where id=$1",[id])).rows[0];
  assert.equal(trade.status,"closed");
  assert.equal(Number(trade.initial_risk_idr),1200);
  assert.equal(Number(trade.fee_total_idr),100);
  assert.equal((await sql("select count(*)::int n from public.actual_fills where trade_id=$1",[id])).rows[0].n,4);
});

test("same request replays exactly; changed body and oversell leave no residue", async () => {
  await role("authenticated", owner);
  const request = crypto.randomUUID();
  const one = await apply("create",null,base,request);
  assert.deepEqual(await apply("create",null,base,request),one);
  await denied(() => apply("create",null,{...base,ticker:"OTHER"},request),"23514");
  const first = await apply("fill",one.trade_id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  assert.deepEqual(await apply("fill",one.trade_id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"),
    (await sql("select request_id from public.actual_journal_requests where result->>'action'='fill'")).rows[0].request_id),first);
  await denied(() => apply("fill",one.trade_id,fill("sell",101,105,0,2,"2026-09-02T03:00:00Z")),"23514");
  assert.equal((await sql("select count(*)::int n from public.actual_fills where trade_id=$1",[one.trade_id])).rows[0].n,1);
});

test("non-owner and anon cannot read or mutate journal", async () => {
  await role("authenticated",owner);
  await apply("create",null,base);
  await role("authenticated",outsider);
  assert.equal((await sql("select count(*)::int n from public.actual_trades")).rows[0].n,0);
  await denied(() => apply("create",null,base),"42501");
  await denied(() => sql("insert into public.actual_trades(owner_id,data_mode,ticker,primary_strategy,exit_policy_snapshot,initial_stop,current_stop) values ($1,'live','TEST','MACD_EMA200_V1','{}',95,95)",[outsider]),"42501");
  await role("anon");
  await denied(() => sql("select * from public.actual_trades"),"42501");
  await denied(() => apply("create",null,base),"42501");
});



test("sell auto-finalizes effective buy batch and blocks later scale-in", async () => {
  await role("authenticated",owner);
  const created = await apply("create",null,base);
  const id=created.trade_id;
  await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  const partial=await apply("fill",id,fill("sell",50,105,0,2,"2026-09-02T03:00:00Z"));
  assert.equal(partial.ledger.status,"open");
  assert.equal(Number(partial.ledger.initial_risk_idr),500);
  assert.equal(Number(partial.ledger.realized_pnl_idr),250);
  await denied(() => apply("fill",id,fill("buy",50,101,0,3,"2026-09-03T03:00:00Z")),"23514");
  assert.equal((await sql("select count(*)::int n from public.actual_fills where trade_id=$1",[id])).rows[0].n,2);
});

test("audited correction recalculates partial/closed ledger; risk restatement must be explicit", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const buy=await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  await apply("finalize",id,{expected_revision:2});
  const sell=await apply("fill",id,fill("sell",50,105,0,3,"2026-09-02T03:00:00Z"));
  const correction={
    expected_revision:4, fill_id:sell.ledger.fill_id, quantity:100,
    price_idr:105,fee_idr:0,fee_status:"actual",reason:"Broker statement corrected quantity",
  };
  const request=crypto.randomUUID();
  const closed=await apply("correct_fill",id,correction,request);
  assert.equal(closed.ledger.status,"closed");
  assert.equal(Number(closed.ledger.realized_pnl_idr),500);
  assert.deepEqual(await apply("correct_fill",id,correction,request),closed);
  const entryCorrection={
    expected_revision:5,fill_id:buy.ledger.fill_id,quantity:100,
    price_idr:102,fee_idr:0,fee_status:"actual",reason:"Broker statement corrected price",
  };
  await denied(() => apply("correct_fill",id,entryCorrection),"23514");
  const restated=await apply("correct_fill",id,{...entryCorrection,restate_initial_risk:true});
  assert.equal(Number(restated.ledger.initial_risk_idr),700);
  assert.equal(Number(restated.ledger.realized_pnl_idr),300);
  assert.ok(Math.abs(Number(restated.ledger.realized_r)-3/7)<1e-10);
  assert.equal((await sql("select count(*)::int n from public.actual_fill_corrections where trade_id=$1",[id])).rows[0].n,2);
});

test("actual analytics use closed exit-date cohort, IDR basis and primary attribution once", async () => {
  await role("authenticated",owner);
  async function trade(exitPrice, exitDay, tag) {
    const id=(await apply("create",null,base)).trade_id;
    await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
    await apply("finalize",id,{expected_revision:2});
    if (exitPrice !== null) {
      await apply("fill",id,fill("sell",100,exitPrice,0,3,exitDay));
      if (tag) await apply("tag",id,{expected_revision:4,tag});
    }
    return id;
  }
  await trade(110,"2026-09-02T03:00:00Z","breakout");
  await trade(95,"2026-09-03T03:00:00Z","momentum");
  await trade(100,"2026-09-04T03:00:00Z",null);
  await trade(null,null,null);
  const a=(await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(a.basis,"IDR");
  assert.equal(a.closed,3);
  assert.equal(a.open,1);
  assert.equal(a.wins,1);
  assert.equal(a.losses,1);
  assert.equal(a.breakeven,1);
  assert.equal(Number(a.net_pnl_idr),500);
  assert.ok(Math.abs(Number(a.win_rate)-1/3)<1e-10);
  assert.ok(Math.abs(Number(a.expectancy_r)-1/3)<1e-10);
  assert.equal(Number(a.profit_factor),2);
  assert.equal(Number(a.payoff_ratio),2);
  const filtered=(await sql("select public.actual_journal_analytics($1,$2) as a",
    ["2026-09-03","2026-09-03"])).rows[0].a;
  assert.equal(filtered.closed,1);
  assert.equal(filtered.losses,1);
  assert.equal(filtered.open,1);
  assert.equal(Number(filtered.profit_factor),0);
  await denied(() => sql("select public.actual_journal_analytics($1,$2)",
    ["2026-09-05","2026-09-01"]),"22023");
});

test("analytics deny outsider and do not expose fixture after mode changes", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("authenticated",owner);
  await apply("create",null,base);
  const fixture=(await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(fixture.draft,1);
  await role("authenticated",outsider);
  await denied(() => sql("select public.actual_journal_analytics()"),"42501");
  await db.exec("reset role");
  await db.exec("update public.deployment_settings set data_mode='live'");
  await role("authenticated",owner);
  const live=(await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(live.draft,0);
  assert.equal(live.closed,0);
  assert.equal(live.win_rate,null);
  assert.equal(live.profit_factor_status,"no_closed");
});

test("another enabled owner cannot inspect or mutate a guessed trade", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  await role("authenticated",otherOwner);
  for (const table of ["actual_trades","actual_fills","actual_fill_corrections",
    "actual_stop_events","actual_notes","actual_trade_tags","actual_journal_requests"]) {
    assert.equal((await sql("select count(*)::int n from public."+table)).rows[0].n,0);
  }
  assert.equal((await sql("select public.actual_journal_analytics() as a")).rows[0].a.draft,0);
  await denied(() => apply("note",id,{expected_revision:1,body:"Unauthorized edit"}),"22023");
  await role("authenticated",owner);
  assert.equal((await sql("select revision from public.actual_trades where id=$1",[id])).rows[0].revision,1);
});

test("estimated fees are disclosed, correction changes quality without changing P&L", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const buy=await apply("fill",id,{...fill("buy",100,100,10,1,"2026-09-01T03:00:00Z"),fee_status:"estimated"});
  await apply("fill",id,fill("sell",100,110,0,2,"2026-09-02T03:00:00Z"));
  const before=(await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(before.estimated_fee_trades,1);
  assert.equal(Number(before.net_pnl_idr),990);
  await apply("correct_fill",id,{expected_revision:3,fill_id:buy.ledger.fill_id,
    quantity:100,price_idr:100,fee_idr:10,fee_status:"actual",
    reason:"Broker fee statement confirmed"});
  const after=(await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(after.estimated_fee_trades,0);
  assert.equal(Number(after.net_pnl_idr),990);
});

test("oversell correction rolls back correction, request and audit", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  const sell=await apply("fill",id,fill("sell",50,105,0,2,"2026-09-02T03:00:00Z"));
  const before=(await sql("select count(*)::int n from public.audit_events where entity_id=$1",[id])).rows[0].n;
  await denied(() => apply("correct_fill",id,{expected_revision:3,fill_id:sell.ledger.fill_id,
    quantity:101,price_idr:105,fee_idr:0,fee_status:"actual",
    reason:"Invalid correction should roll back"}),"23514");
  assert.equal((await sql("select count(*)::int n from public.actual_fill_corrections where trade_id=$1",[id])).rows[0].n,0);
  assert.equal((await sql("select revision from public.actual_trades where id=$1",[id])).rows[0].revision,3);
  assert.equal((await sql("select count(*)::int n from public.audit_events where entity_id=$1",[id])).rows[0].n,before);
});

test("new journal tables enforce owner RLS and deny direct client mutation", async () => {
  for (const table of ["actual_trades","actual_fills","actual_fill_corrections",
    "actual_stop_events","actual_notes","actual_trade_tags","actual_journal_requests"]) {
    const r=(await sql("select relrowsecurity, has_table_privilege('authenticated',$1,'INSERT') can_insert, has_table_privilege('authenticated',$1,'UPDATE') can_update, has_table_privilege('authenticated',$1,'DELETE') can_delete from pg_class where oid=$1::regclass",["public."+table])).rows[0];
    assert.equal(r.relrowsecurity,true,table);
    assert.equal(r.can_insert,false,table);
    assert.equal(r.can_update,false,table);
    assert.equal(r.can_delete,false,table);
  }
  await role("authenticated",owner);
  await denied(() => sql("select public.recalculate_actual_trade(gen_random_uuid())"),"42501");
  await denied(() => sql("select public.actual_entry_risk(gen_random_uuid(),95)"),"42501");
});

test("buy makes open provisional position; partial stays outside closed metrics", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const buy=await apply("fill",id,fill("buy",3,100,1,1,"2026-09-01T03:00:00Z"));
  assert.equal(buy.ledger.status,"open");
  assert.equal(buy.ledger.initial_risk_idr,null);
  assert.equal(buy.ledger.provisional_risk_idr,15);
  await apply("fill",id,fill("sell",1,101,0,2,"2026-09-02T03:00:00Z"));
  let a=(await sql("select public.actual_journal_analytics() a")).rows[0].a;
  assert.equal(a.open,1); assert.equal(a.closed,0); assert.equal(a.win_rate,null);
  const closed=await apply("fill",id,fill("sell",2,101,0,3,"2026-09-02T04:00:00Z"));
  assert.equal(closed.ledger.remaining_cost_idr,0);
  assert.equal(closed.ledger.realized_pnl_idr,2);
  const row=(await sql("select * from public.actual_trades where id=$1",[id])).rows[0];
  assert.equal(Number(row.realized_pnl_idr),2);
  assert.equal(Number(row.realized_r),closed.ledger.realized_r);
});

test("nonfinite, missing, overprecision and invalid exit inputs cannot enter ledger", async () => {
  await role("authenticated",owner);
  for (const initial_stop of ["NaN","Infinity","0.00001","95.00001",null]) {
    await denied(() => apply("create",null,{...base,initial_stop}),"22023");
  }
  for (const exit_policy_snapshot of [
    {version:"v1"}, {version:"v1",mode:"fixed_rr",target_r:"NaN"},
    {version:"v1",mode:"fixed_rr",target_r:0},
    {version:"v1",mode:"fixed_rr",target_r:2,period:10},
    {version:"v1",mode:"ma_close",ma_type:"SMA",period:7},
    {version:"v1",mode:"ma_close",ma_type:"SMA",period:10,target_r:2},
  ]) await denied(() => apply("create",null,{...base,exit_policy_snapshot}),"22023");
  const id=(await apply("create",null,base)).trade_id;
  for (const patch of [
    {price_idr:"NaN"},{fee_idr:"NaN"},{price_idr:"100.00001"},{fee_idr:null},
    {quantity:"1.5"},{quantity:0},{fee_status:null},{filled_at:"infinity"},
    {side:"sell",quantity:1},
  ]) {
    await denied(() => apply("fill",id,{...fill("buy",1,100,0,1,"2026-09-01T03:00:00Z"),...patch}),
      patch.side ? "23514" : "22023");
  }
  await denied(() => apply("fill",id,{...fill("buy",1,100,0,1,"2026-09-01T03:00:00Z"),surprise:true}),"22023");
  assert.equal((await sql("select count(*)::int n from public.actual_fills")).rows[0].n,0);
});

test("equal timestamps have stable insertion order; backdated sells fail atomically", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  await denied(() => apply("fill",id,fill("sell",100,110,0,2,"2026-08-31T03:00:00Z")),"23514");
  const sold=await apply("fill",id,fill("sell",100,110,0,2,"2026-09-01T03:00:00Z"));
  assert.equal(sold.ledger.status,"closed"); assert.equal(sold.ledger.realized_pnl_idr,1000);
});

test("corrections retain original, latest revision wins, closed can reopen, risk audit retained", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const buy=await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  const sold=await apply("fill",id,fill("sell",100,110,0,2,"2026-09-02T03:00:00Z"));
  const corrected=await apply("correct_fill",id,{expected_revision:3,fill_id:sold.ledger.fill_id,
    quantity:50,price_idr:110,fee_idr:5,fee_status:"estimated",reason:"Correct broker quantity"});
  assert.equal(corrected.ledger.status,"open"); assert.equal(corrected.ledger.realized_r,null);
  assert.equal((await sql("select closed_at from public.actual_trades where id=$1",[id])).rows[0].closed_at,null);
  assert.equal((await sql("select public.actual_journal_analytics() a")).rows[0].a.closed,0);
  await apply("correct_fill",id,{expected_revision:4,fill_id:buy.ledger.fill_id,
    quantity:100,price_idr:102,fee_idr:0,fee_status:"actual",reason:"Correct broker price",restate_initial_risk:true});
  const audit=(await sql("select details from public.audit_events where entity_id=$1 and details->>'revision'='5'",[id])).rows[0].details;
  assert.equal(audit.before.initial_risk_idr,500);
  assert.equal(audit.result.ledger.initial_risk_idr,700);
  const done=await apply("correct_fill",id,{expected_revision:5,fill_id:sold.ledger.fill_id,
    quantity:100,price_idr:110,fee_idr:10,fee_status:"actual",reason:"Final broker statement"});
  assert.equal(done.ledger.realized_pnl_idr,790);
  assert.equal((await sql("select quantity::text q from public.actual_fills where id=$1",[sold.ledger.fill_id])).rows[0].q,"100");
  assert.equal((await sql("select public.actual_journal_analytics() a")).rows[0].a.estimated_fee_trades,0);
  await db.exec("reset role");
  await denied(() => sql("update public.actual_fills set price_idr=1 where id=$1",[buy.ledger.fill_id]),"23514");
});

test("populated event tables and audit isolate owner, outsider, disabled member and service mutations", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const buy=await apply("fill",id,fill("buy",100,100,0,1,"2026-09-01T03:00:00Z"));
  await apply("finalize",id,{expected_revision:2});
  await apply("stop",id,{expected_revision:3,new_stop:99,reason:"Owner manual stop"});
  await apply("note",id,{expected_revision:4,body:"Private owner note"});
  await apply("tag",id,{expected_revision:5,tag:"momentum"});
  await apply("correct_fill",id,{expected_revision:6,fill_id:buy.ledger.fill_id,
    quantity:100,price_idr:100,fee_idr:1,fee_status:"actual",reason:"Confirmed fee"});
  const tables=["actual_trades","actual_fills","actual_fill_corrections","actual_stop_events",
    "actual_notes","actual_trade_tags","actual_journal_requests","audit_events"];
  for (const t of tables) assert.ok((await sql("select count(*)::int n from public."+t)).rows[0].n>0,t);
  for (const uid of [outsider,otherOwner]) {
    await role("authenticated",uid);
    for (const t of tables) assert.equal((await sql("select count(*)::int n from public."+t)).rows[0].n,0,t);
    if (uid===outsider) await denied(() => sql("select public.export_actual_journal()"),"42501");
    else assert.equal((await sql("select public.export_actual_journal() a")).rows[0].a.rows.length,0);
    await denied(() => apply("note",id,{expected_revision:7,body:"Intruder"}),uid===outsider?"42501":"22023");
  }
  await role("anon");
  for (const t of tables) await denied(() => sql("select * from public."+t),"42501");
  await denied(() => sql("select public.export_actual_journal()"),"42501");
  await role("service_role",owner);
  await denied(() => apply("note",id,{expected_revision:7,body:"Privileged spoof"}),"42501");
  await db.exec("reset role");
  await sql("update public.app_members set enabled=false where user_id=$1",[owner]);
  await role("authenticated",owner);
  for (const t of tables) assert.equal((await sql("select count(*)::int n from public."+t)).rows[0].n,0,t);
  await denied(() => apply("note",id,{expected_revision:7,body:"Disabled"}),"42501");
});

test("stale revisions, failed requests and changed-mode mutation cannot alter ledger", async () => {
  await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  const rid=crypto.randomUUID();
  const payload=fill("buy",1,100,0,1,"2026-09-01T03:00:00Z");
  const bought=await apply("fill",id,payload,rid);
  await apply("note",id,{expected_revision:2,body:"Newer revision"});
  assert.deepEqual(await apply("fill",id,payload,rid),bought);
  await denied(() => apply("fill",id,{...payload,fee_idr:1},rid),"23514");
  const failed=crypto.randomUUID();
  await denied(() => apply("finalize",id,{expected_revision:2},failed),"PT412");
  assert.equal((await sql("select count(*)::int n from public.actual_journal_requests where request_id=$1",[failed])).rows[0].n,0);
  await db.exec("reset role; update public.deployment_settings set data_mode='live'");
  await role("authenticated",owner);
  await denied(() => apply("finalize",id,{expected_revision:3}),"23514");
  assert.equal((await sql("select public.export_actual_journal() a")).rows[0].a.rows.length,0);
});

test("exit cohort uses Jakarta date, config filter, fee quality and no-loss semantics", async () => {
  await role("authenticated",owner);
  const snapshot={version:"ma10-v1",mode:"ma_close",ma_type:"SMA",period:10,target_r:null};
  const id=(await apply("create",null,{...base,exit_policy_snapshot:snapshot})).trade_id;
  await apply("fill",id,{...fill("buy",1,100,1,1,"2026-09-01T03:00:00Z"),fee_status:"estimated"});
  await apply("fill",id,fill("sell",1,102,0,2,"2026-09-01T17:00:00Z"));
  await apply("tag",id,{expected_revision:3,tag:"breakout"});
  await apply("tag",id,{expected_revision:4,tag:"momentum"});
  const a=(await sql("select public.actual_journal_analytics($1,$2,$3,$4,$5) a",
    ["2026-09-02","2026-09-02","MACD_EMA200_V1","ma10-v1",JSON.stringify(snapshot)])).rows[0].a;
  assert.equal(a.closed,1); assert.equal(a.net_pnl_idr,1); assert.equal(a.profit_factor,null);
  assert.equal(a.profit_factor_status,"no_losses"); assert.equal(a.fee_quality,"includes_estimates");
  assert.equal((await sql("select public.actual_journal_analytics($1,$2) a",["2026-09-01","2026-09-01"])).rows[0].a.closed,0);
  assert.equal((await sql("select public.actual_journal_analytics(null,null,null,null,$1) a",[JSON.stringify(base.exit_policy_snapshot)])).rows[0].a.closed,0);
});

test("actual export pagination, exact decimals, corrected quality and CSV contract", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  await apply("fill",id,fill("buy",1,100,0,1,"2026-09-01T03:00:00Z"));
  await apply("fill",id,fill("sell",1,"99.1234",0,2,"2026-09-02T03:00:00Z"));
  await apply("note",id,{expected_revision:3,body:'=HYPERLINK("evil")\nprivate, note'});
  await apply("create",null,base);
  let page=(await sql("select public.export_actual_journal(p_limit=>1) a")).rows[0].a;
  assert.equal(page.has_more,true); assert.ok(page.next_after);
  const next=(await sql("select public.export_actual_journal(p_after=>$1,p_limit=>1) a",[page.next_after])).rows[0].a;
  assert.equal(next.rows.length,1); assert.equal(next.has_more,false); assert.equal(next.next_after,null);
  assert.notEqual(next.rows[0].trade_id,page.rows[0].trade_id);
  page=(await sql("select public.export_actual_journal($1,$2) a",["2026-09-02","2026-09-02"])).rows[0].a;
  assert.equal(page.rows.length,1);
  assert.equal((await sql("select public.export_actual_journal(p_status=>'closed') a")).rows[0].a.rows.length,1);
  assert.equal((await sql("select public.export_actual_journal(p_status=>'draft') a")).rows[0].a.rows.length,1);
  assert.equal(page.rows[0].realized_pnl_idr,"-0.8766");
  assert.equal(page.rows[0].initial_risk_idr,"5.0000");
  assert.equal(page.rows[0].mode,"actual"); assert.equal(page.rows[0].fee_quality,"actual");
  assert.deepEqual(Object.keys(page.rows[0]).sort(),[...COLUMNS].sort());
  const csv=actualJournalCsv(page);
  assert.ok(csv.startsWith('"contract_version","mode","data_mode"'));
  assert.ok(csv.includes('"-0.8766"')); assert.ok(csv.endsWith("\r\n"));
  for (const payload of ["=1+1"," +cmd","\t@SUM(1)","\r-1+2"]) {
    const malicious=structuredClone(page); malicious.rows[0].ticker=payload;
    assert.ok(actualJournalCsv(malicious).includes('"\''+payload+'"'));
  }
  assert.throws(() => actualJournalCsv({...page,mode:"paper"}),/invalid_actual_export/);
  const imprecise=structuredClone(page); imprecise.rows[0].realized_pnl_idr=-0.8766;
  assert.throws(() => actualJournalCsv(imprecise),/decimal_string/);
  await denied(() => sql("select public.export_actual_journal(p_limit=>201)"),"22023");
  await denied(() => sql("select public.export_actual_journal(p_status=>'paper')"),"22023");
});

test("closed export continues after the 200-row cursor without duplicating ledger rows", async () => {
  await role("authenticated",owner);
  const snapshot={version:"export200-fixture-v1",mode:"fixed_rr",target_r:2};
  for (let i=0;i<201;i++) {
    const id=(await apply("create",null,{...base,exit_policy_snapshot:snapshot})).trade_id;
    await apply("fill",id,fill("buy",1,100,0,1,"2026-09-01T03:00:00Z"));
    await apply("fill",id,fill("sell",1,110,0,2,"2026-09-02T03:00:00Z"));
  }
  const args=["2026-09-02","2026-09-02","MACD_EMA200_V1","export200-fixture-v1",JSON.stringify(snapshot)];
  const page1=(await sql("select public.export_actual_journal($1,$2,$3,$4,$5::jsonb,null,200,'closed') a",args)).rows[0].a;
  assert.equal(page1.rows.length,200);
  assert.equal(page1.has_more,true);
  assert.equal(page1.next_after,page1.rows.at(-1).trade_id);
  const page2=(await sql("select public.export_actual_journal($1,$2,$3,$4,$5::jsonb,$6,200,'closed') a",
    [...args,page1.next_after])).rows[0].a;
  assert.equal(page2.rows.length,1);
  assert.equal(page2.has_more,false);
  assert.equal(page2.next_after,null);
  const ids=[...page1.rows,...page2.rows].map(row=>row.trade_id);
  assert.equal(new Set(ids).size,201);
  assert.ok(ids.every((id,index)=>index===0 || ids[index-1]<id));
  assert.ok([...page1.rows,...page2.rows].every(row=>
    row.status==="closed" && row.fee_quality==="actual" && row.realized_pnl_idr==="10.0000"));
  const analytics=(await sql("select public.actual_journal_analytics($1,$2,$3,$4,$5::jsonb) a",args)).rows[0].a;
  assert.equal(analytics.closed,201);
  assert.equal(analytics.net_pnl_idr,2010);
});

test("timestamp corrections move exit cohort and survive later fee correction", async () => {
  await role("authenticated",owner);
  const id=(await apply("create",null,base)).trade_id;
  await apply("fill",id,fill("buy",1,100,0,1,"2026-09-01T03:00:00Z"));
  const sell=await apply("fill",id,fill("sell",1,110,0,2,"2026-09-02T03:00:00Z"));
  const correction={expected_revision:3,fill_id:sell.ledger.fill_id,quantity:1,
    price_idr:110,fee_idr:0,fee_status:"actual",reason:"Correct broker timestamp"};
  await denied(() => apply("correct_fill",id,{...correction,filled_at:"2026-08-31T03:00:00Z"}),"23514");
  await apply("correct_fill",id,{...correction,filled_at:"2026-09-02T17:00:00Z"});
  await apply("correct_fill",id,{...correction,expected_revision:4,fee_idr:1});
  const a=(await sql("select public.actual_journal_analytics($1,$2) a",["2026-09-03","2026-09-03"])).rows[0].a;
  assert.equal(a.closed,1); assert.equal(a.net_pnl_idr,9);
  const row=(await sql("select public.export_actual_journal() a")).rows[0].a.rows[0];
  assert.equal(row.exit_session,"2026-09-03");
});
