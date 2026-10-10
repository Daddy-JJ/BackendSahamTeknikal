import assert from 'node:assert/strict';
import {before,after,beforeEach,afterEach,test} from 'node:test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {loadRelease} from '../scripts/plan_production_release.mjs';
import {database,owner,outsider,role,init,trade,bookOf,commit,evaluation,observations,report} from './helpers/paper-reporting-fixture.mjs';
let db;
before(async()=>{db=await database();});after(async()=>db?.close());
beforeEach(async()=>db.exec('begin'));afterEach(async()=>db.exec('rollback'));
const denied=async(fn,code)=>{await db.exec('savepoint denied');await assert.rejects(fn,e=>{assert.equal(e.code,code);return true;});await db.exec('rollback to savepoint denied');};
const health=async at=>(await db.query("select public.paper_processing_health_v1($1,'live',$2) r",[owner,at])).rows[0].r;

test('seeded calendar exactly matches checksummed canonical source, no invented historical times',async()=>{
  const source=readFileSync(new URL('../../config/live/idx-calendar-2024-2026.json',import.meta.url),'utf8').replaceAll('\r\n','\n');
  const c=(await db.query('select * from public.paper_calendar_v1')).rows[0];
  assert.deepEqual(c.payload,JSON.parse(source));assert.equal(c.config_sha256_lf,createHash('sha256').update(source).digest('hex'));
  assert.equal((await db.query("select count(*)::int n from public.paper_calendar_days_v1() where day<'2026-10-02' and closes_at is not null")).rows[0].n,0);
});

test('missing jobs cannot conceal overdue Friday processing across Saturday/Sunday and holidays',async()=>{
  await init(db);await commit(db,bookOf(),{},0,'checkpoint','2026-10-08');await role(db,'postgres');
  for(const at of ['2026-10-09T11:00:00Z','2026-10-10T11:00:00Z','2026-10-11T11:00:00Z']){
    const h=await health(at);assert.equal(h.expected_session,'2026-10-09');assert.equal(h.processed_session,'2026-10-08');assert.equal(h.status,'overdue');assert.equal(h.overdue,true);assert.equal(h.last_attempt_at,null);
  }
  const morning=await health('2026-10-09T01:00:00Z');
  assert.equal(morning.expected_session,'2026-10-08');
  assert.equal(new Date(morning.next_eligible_processing_at).toISOString(),'2026-10-09T09:15:00.000Z');
  assert.equal((await health('2026-12-25T12:00:00Z')).expected_session,'2026-12-23');
  assert.equal((await health('2027-01-01T12:00:00Z')).status,'calendar_unknown');
});

test('job stage events sanitize context, replay exactly, retain failures and isolate owner/anon',async()=>{
  await init(db);
  const log=(status='failed',ctx={workflow:'Scanner & Paper (Production)',run_id:'123',event:'schedule',schedule:'18 11 * * 1-5',observed_at:'2026-10-10T01:00:00+07:00',source_sha:'a'.repeat(40)})=>db.query(
    "select public.record_paper_job_v1($1,'live','123-1','paper',$2,'2026-10-09',$3,$4::jsonb) r",[owner,status,status==='failed'?'missing_bar':null,JSON.stringify(ctx)]).then(x=>x.rows[0].r);
  const first=await log();assert.equal(first.replayed,false);assert.deepEqual(await log(),{...first,replayed:true});
  await denied(()=>log('failed',{message:'password=never-log-this'}),'22023');
  await denied(()=>log('failed',{workflow:'different'}),'PT409');
  await log('succeeded');await role(db,'postgres');assert.equal((await health('2026-10-10T11:00:00Z')).latest_job_status,'succeeded');
  assert.equal((await db.query("select count(*)::int n from public.paper_job_events_v1 where status='failed'")).rows[0].n,1);
  for(const [name,uid] of [['anon',''],['authenticated',outsider]]){
    await role(db,name,uid);await denied(()=>db.query('select public.read_paper_processing_health_v1()'),'42501');
    await denied(()=>log(),'42501');
    if(name==='anon') await denied(()=>db.query('select * from public.paper_job_events_v1'),'42501');
    else assert.equal((await db.query('select * from public.paper_job_events_v1')).rows.length,0);
  }
  await role(db,'authenticated',owner);await denied(()=>db.query("update public.paper_calendar_v1 set config_sha256_lf=repeat('a',64)"),'42501');
  for(const name of ['anon','authenticated','service_role']){
    assert.equal((await db.query("select has_function_privilege($1,'public.paper_processing_health_v1(uuid,text,timestamptz)','EXECUTE') allowed",[name])).rows[0].allowed,false);
  }
});

test('economic identity duplicate and experiment alias reject atomically without receipts',async()=>{
  const m=await init(db),t=await trade(db,m,{state:'closed'}),duplicate=structuredClone(t);duplicate.id='different-id';
  await denied(()=>commit(db,bookOf(t,duplicate)),'23505');
  const bad=structuredClone(t);bad.experiment.id+='-alias';await denied(()=>commit(db,bookOf(bad)),'22023');
  assert.equal((await db.query('select count(*)::int n from public.paper_trades')).rows[0].n,0);
  assert.equal((await db.query('select count(*)::int n from public.paper_runtime_requests')).rows[0].n,0);
  const a=await commit(db,bookOf(t));assert.equal((await commit(db,bookOf(t),{},1)).replayed,true);assert.equal(a.revision,1);
});

test('initial research price/date/targets/future/missing/duplicate/skipped digests and early success fail closed',async()=>{
  const m=await init(db),t=await trade(db,m),e=evaluation(t);
  const cases=[x=>x.entry_price='9999',x=>x.initial_stop='1',x=>x.signal_session='2000-01-01',x=>x.entry_session='2000-01-02',x=>x.target_2r='1',
    x=>x.results.target_1r='won',x=>x.results.target_2r='lost',x=>x.results.target_1r='ambiguous',x=>x.results.net_5='lost',
    x=>{x.observed_sessions=10;x.last_session='2099-01-01';x.results.net_10='won';},
    x=>{x.observed_sessions=1;x.last_session='2026-10-09';},
    x=>{x.observed_sessions=1;x.last_session='2026-10-09';x.input_digests=observations('2026-10-09');x.results.net_5='won';},
    x=>{x.observed_sessions=2;x.last_session='2026-10-12';x.input_digests=observations('2026-10-09','2026-10-09');},
    x=>{x.observed_sessions=2;x.last_session='2026-10-13';x.input_digests=observations('2026-10-09','2026-10-13');},
    x=>{x.observed_sessions=1;x.last_session='2026-10-09';x.input_digests=observations('2026-10-09');x.input_digests[0].observed_at='2026-10-09T02:00:00Z';}];
  for(const change of cases){const bad=structuredClone(e);change(bad);await denied(()=>commit(db,bookOf(t),{[t.signal.id]:bad},0,crypto.randomUUID(),'2026-10-13'),'22023');}
  const good=structuredClone(e);good.observed_sessions=1;good.last_session='2026-10-09';good.input_digests=observations('2026-10-09');good.results.target_1r='won';good.results.net_5='lost';
  await commit(db,bookOf(t),{[t.signal.id]:good});await role(db,'authenticated',owner);
  const r=(await db.query('select public.read_signal_evaluation_v1() r')).rows[0].r;assert.equal(r.strategies[0].cells.net_5.assessed,1);assert.equal(r.strategies[0].cells.net_10.assessed,0);
});

test('verified untradable entry exclusions and suspended-session digest retain zero/known checkpoint semantics',async()=>{
  const m=await init(db),t=await trade(db,m),e=evaluation(t);
  for(const k of Object.keys(e.results)){e.results[k]='excluded';e.exclusion_reasons[k]='official_untradable_entry';}
  e.untradable_evidence=[{version:'verified_untradable_v1',ticker:t.signal.ticker,data_mode:'live',
    session:'2026-10-09',document_sha256:'c'.repeat(64),digest:'d'.repeat(64),source_url:'https://www.idx.co.id/synthetic-proof',
    reason:'official_whole_session_suspension',verified_at:'2026-10-09T10:00:00Z',observed_at:'2026-10-09T10:00:00Z'}];
  await commit(db,bookOf(t),{[t.signal.id]:e});await role(db,'authenticated',owner);
  const r=(await db.query('select public.read_signal_evaluation_v1() r')).rows[0].r;assert.equal(r.evaluations[0].observed_sessions,0);assert.equal(r.strategies[0].cells.net_5.excluded,1);assert.equal(r.strategies[0].cells.net_5.excluded_reasons.official_untradable_entry,1);
});

test('exclusions require matching reviewed evidence and cannot rewrite their reason on retry',async()=>{
  const m=await init(db),t=await trade(db,m),e=evaluation(t);
  e.results.net_5='excluded';e.exclusion_reasons.net_5='official_untradable_entry';
  await denied(()=>commit(db,bookOf(t),{[t.signal.id]:e}),'22023');
  const proof={version:'verified_untradable_v1',ticker:t.signal.ticker,data_mode:'live',session:'2026-10-09',
    document_sha256:'c'.repeat(64),digest:'d'.repeat(64),source_url:'https://www.idx.co.id/synthetic-proof',
    reason:'official_whole_session_suspension',verified_at:'2026-10-09T10:00:00Z',observed_at:'2026-10-09T10:00:00Z'};
  for(const change of [x=>delete x.document_sha256,x=>x.ticker='OTHER',x=>x.data_mode='fixture',
    x=>x.verified_at='2099-01-01T00:00:00Z',x=>x.source_url='https://unverified.example.test/proof']){
    const bad=structuredClone(e);bad.untradable_evidence=[structuredClone(proof)];change(bad.untradable_evidence[0]);
    await denied(()=>commit(db,bookOf(t),{[t.signal.id]:bad},0,crypto.randomUUID()),'22023');
  }
  e.untradable_evidence=[proof];await commit(db,bookOf(t),{[t.signal.id]:e});
  const changed=structuredClone(e);changed.exclusion_reasons.net_5='invented';
  await denied(()=>commit(db,bookOf(t),{[t.signal.id]:changed},1,'rewrite-reason'),'22023');
});

test('existing evaluation cannot advance date or resolve targets without a new observation',async()=>{
  const m=await init(db),t=await trade(db,m),e=evaluation(t);
  e.observed_sessions=1;e.last_session='2026-10-09';e.input_digests=observations('2026-10-09');
  await commit(db,bookOf(t),{[t.signal.id]:e});
  for(const change of [x=>x.last_session='2026-10-12',x=>x.results.target_1r='won',x=>x.results.target_2r='lost']){
    const bad=structuredClone(e);change(bad);
    await denied(()=>commit(db,bookOf(t),{[t.signal.id]:bad},1,crypto.randomUUID(),'2026-10-12'),'22023');
  }
  const held=structuredClone(e);held.results.target_1r='data_hold';held.results.net_5='data_hold';
  await commit(db,bookOf(t),{[t.signal.id]:held},1,'hold-without-bar','2026-10-12');
  const runtime=(await db.query("select public.load_paper_runtime_v1($1,'live') r",[owner])).rows[0].r;
  assert.equal(runtime.evaluations[t.signal.id].last_session,'2026-10-09');
  assert.equal(runtime.evaluations[t.signal.id].observed_sessions,1);
});

test('late exclusion is visible and absent from main/sensitivity; ambiguity remains eligible only for sensitivity',async()=>{
  const m=await init(db),late=await trade(db,m,{key:'a',state:'closed',mode:'ma_close'}),ambiguous=await trade(db,m,{key:'b',state:'ambiguous_review',mode:'ma_close',exitPrice:925,alternate:1150}),lateAmbiguous=await trade(db,m,{key:'c',state:'ambiguous_review',mode:'ma_close',exitPrice:925,alternate:1150});
  late.actionable=false;late.events.splice(1,0,{session:'2026-10-09',kind:'pending_exit',price:null,reason:'late_model_only',observed_at:'2026-10-09T10:00:00Z',input_digest:'c'.repeat(64)});
  lateAmbiguous.events.splice(1,0,{...late.events[1]});
  await commit(db,bookOf(late,ambiguous,lateAmbiguous));const r=await report(db,'ma10');
  assert.equal(r.summary.closed,0);assert.equal(r.statuses.closed,1);assert.equal(r.exclusions.closed_excluded,3);assert.equal(r.exclusions.reasons.late_model_only,2);
  assert.equal(r.sensitivities.sl_first.closed,1);assert.equal(r.sensitivities.tp_first.closed,1);assert.equal(r.sensitivities.sl_first.net_pnl_idr,-993037.5);
  const row=r.trades.find(x=>x.id===late.id);assert.equal(row.metric_eligible,false);assert.equal(row.exclusion_reason,'late_model_only');assert.equal(r.status_scope,'all_history');
});

test('IDR profit factor/payoff define all zero-denominator states and preserve R denominator',async()=>{
  const summarize=async pnls=>(await db.query('select public.trade_reporting_summary_v1($1::jsonb) r',[JSON.stringify(pnls.map(p=>({realized_pnl_idr:p,realized_r:p/100})))])).rows[0].r;
  assert.equal((await summarize([])).profit_factor_state,'no_closed');assert.equal((await summarize([0])).profit_factor_state,'no_directional_results');
  assert.equal((await summarize([100,200])).payoff_ratio_state,'no_losses');assert.equal((await summarize([-100])).profit_factor_idr,0);assert.equal((await summarize([-100])).payoff_ratio_state,'no_wins');
  const s=await summarize([200,-100,0,100]);assert.equal(s.profit_factor_idr,3);assert.equal(s.payoff_ratio_idr,1.5);assert.equal(s.expectancy_r,.5);
});

test('paired comparison retains open counterpart and unpaired entered IDs without summing experiments',async()=>{
  const m=await init(db),fixed=await trade(db,m,{key:'a',state:'closed'}),ma=await trade(db,m,{key:'a',mode:'ma_close',state:'open'}),only=await trade(db,m,{key:'b',state:'closed',exitPrice:925});
  await commit(db,bookOf(fixed,ma,only),{},0,'paired','2026-10-12');const r=await report(db),c=r.experiment_comparison;
  assert.equal(r.summary.closed,2);assert.equal(c.fixed2r.closed_assessed,2);assert.equal(c.ma10.open,1);
  assert.deepEqual(c.common_entry_signal_ids,[fixed.signal.id]);assert.deepEqual(c.fixed_only_entry_signal_ids,[only.signal.id]);assert.deepEqual(c.sma_only_entry_signal_ids,[]);
  assert.equal(c.paired[0].ma10.state,'open');assert.equal(c.paired[0].ma10.pnl_idr,null);assert.equal(c.paired[0].ma10.holding_sessions,2);
  assert.equal(c.paired[0].fixed2r.holding_sessions,1);assert.equal(c.ma10.summary.closed,0);
});

test('global successful checkpoint cannot hide individual trade/research data holds',async()=>{
  const m=await init(db),t=await trade(db,m,{state:'data_hold'}),e=evaluation(t);t.reason='missing_bar';
  e.results={target_1r:'data_hold',target_2r:'data_hold',net_5:'data_hold',net_10:'data_hold'};
  await commit(db,bookOf(t),{[t.signal.id]:e},0,'held-checkpoint','2026-10-09');await role(db,'postgres');
  const h=await health('2026-10-10T11:00:00Z');assert.equal(h.processed_session,'2026-10-09');assert.equal(h.expected_session,'2026-10-09');
  assert.equal(h.status,'data_hold');assert.equal(h.overdue,true);assert.equal(h.data_hold_count,2);assert.equal(h.held_since_session,'2026-10-09');assert.equal(h.pending_entry_due,1);
});

test('new plans cannot spoof missing/legacy sizing policy while existing frozen plans remain supported',async()=>{
  const m=await init(db),t=await trade(db,m);
  for(const policy of [undefined,'rounded_net_v1']){
    const bad=structuredClone(t);if(policy===undefined)delete bad.sizing_policy_version;else bad.sizing_policy_version=policy;
    await denied(()=>commit(db,bookOf(bad)),'22023');
  }
  await commit(db,bookOf(t));const bad=structuredClone(t);bad.sizing_policy_version='rounded_net_v1';await denied(()=>commit(db,bookOf(bad),{},1,'change-policy'),'22023');
});

// Preserve engine money/events/proof payloads; normalize its terse test signal IDs
// to the public persistence contract. Only this disposable DB gets a fixture calendar.
const engineCases=JSON.parse(readFileSync(new URL('./fixtures/paper-engine-canonical-v1.json',import.meta.url),'utf8'));
for(const [name,original] of Object.entries(engineCases.cases)) test('Python engine canonical SQL roundtrip: '+name,async()=>{
  assert.equal(engineCases.provenance.fixture,true);const x=structuredClone(original),signal=structuredClone(x.signal);
  signal.id='f'.repeat(64);signal.config_hash='c'.repeat(64);signal.input_digest='d'.repeat(64);
  await db.exec("update public.deployment_settings set data_mode='fixture';alter table public.paper_calendar_v1 disable trigger immutable_calendar");
  const cal={...x.calendar,version:'synthetic-engine-fixture-v1',source:'fixture'};
  await db.query('update public.paper_calendar_v1 set payload=$1::jsonb',[JSON.stringify(cal)]);await db.exec('alter table public.paper_calendar_v1 enable trigger immutable_calendar');
  await db.query("insert into public.paper_models(owner_id,data_mode,activated_at) values($1,'fixture',$2)",[owner,x.activated_at]);
  await db.query(`insert into public.signals(id,namespace,data_mode,ticker,strategy,session_date,config_hash,input_digest,universe_version,calendar_version,provider,price_basis,planned_entry_session,cohort,published_at,snapshot)
    values($1,'test','fixture',$2,$3,$4,$5,$6,'synthetic','synthetic','fixture','test',$7,'forward',$8,$9::jsonb)`,
    [signal.id,signal.ticker,signal.candidate.strategy,signal.session,signal.config_hash,signal.input_digest,signal.planned_entry_session,signal.published_at,JSON.stringify(signal)]);
  for(const t of Object.values(x.book.trades)) t.signal=signal;
  const evs={};for(const e of Object.values(x.evaluations)){e.signal_id=signal.id;e.signal=signal;evs[signal.id]=e;}
  await role(db,'service_role');const result=(await db.query("select public.commit_paper_session_v1($1,'fixture',0,$2,$3,$4::jsonb,$5::jsonb) r",[owner,name,x.session,JSON.stringify(x.book),JSON.stringify(evs)])).rows[0].r;
  assert.deepEqual(result.book,x.book);assert.deepEqual(result.evaluations,evs);
  const restored=(await db.query("select public.load_paper_runtime_v1($1,'fixture') r",[owner])).rows[0].r;assert.deepEqual(restored.book,x.book);
  if(name==='exact_cap_zero_lot') for(const t of Object.values(restored.book.trades)){assert.equal(t.lots,0);assert.equal(t.reason,'skipped_budget');}
});

test('populated001-010 upgrade preserves old runtime/events/config/ledger and grandfathered evaluation prefix',async()=>{
  const old=await database({through:'202610080010'});
  try{
    await old.exec('begin');const m=await init(old),t=await trade(old,m);delete t.sizing_policy_version;
    const e=evaluation(t);e.observed_sessions=1;e.last_session='2026-10-09';e.input_digests=['legacy-digest'];e.results.target_1r='won';
    await commit(old,bookOf(t),{[t.signal.id]:e});await role(old,'postgres');
    await old.query("insert into public.paper_trades(id,owner_id,data_mode,ticker,strategy,experiment_id,exit_mode,state,reason) values('legacy',$1,'live','TEST','MACD_EMA200_V1','legacy','fixed_rr','closed','legacy')",[owner]);
    const state=async()=>{const r={};for(const table of ['paper_models','paper_trades','paper_events','signal_evaluations','paper_runtime_requests','actual_trades','actual_fills'])r[table]=(await old.query('select to_jsonb(x) r from public.'+table+' x order by to_jsonb(x)::text')).rows;return r;};
    const before=await state();await old.exec(readFileSync(new URL('../migrations/202610100011_paper_integrity_and_processing_health.sql',import.meta.url),'utf8'));assert.deepEqual(await state(),before);
    await role(old,'service_role');const replay=await commit(old,bookOf(t),{[t.signal.id]:e},1);assert.equal(replay.replayed,true);
    const next=structuredClone(e);next.observed_sessions=2;next.last_session='2026-10-12';next.input_digests.push(...observations('2026-10-12'));
    await commit(old,bookOf(t),{[t.signal.id]:next},1,'progress','2026-10-12');assert.equal((await old.query("select public.load_paper_runtime_v1($1,'live') r",[owner])).rows[0].r.revision,2);
  }finally{await old.close();}
});

test('011 refuses duplicate historical economics and transaction rolls back without deleting rows',async()=>{
  const old=await database({through:'202610080010'});
  try{await old.exec('begin');const m=await init(old),t=await trade(old,m),d=structuredClone(t);delete t.sizing_policy_version;delete d.sizing_policy_version;d.id='duplicate';await commit(old,bookOf(t,d));await old.exec('commit');
    await role(old,'postgres');await assert.rejects(()=>old.exec(readFileSync(new URL('../migrations/202610100011_paper_integrity_and_processing_health.sql',import.meta.url),'utf8')),e=>e.code==='23505');await old.exec('rollback');
    assert.equal((await old.query('select count(*)::int n from public.paper_trades')).rows[0].n,2);assert.equal((await old.query("select to_regclass('public.paper_calendar_v1') r")).rows[0].r,null);
  }finally{await old.close();}
});
