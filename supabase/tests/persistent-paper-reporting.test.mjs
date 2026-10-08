import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import { before,after,beforeEach,afterEach,test } from 'node:test';
import { readFileSync,existsSync } from 'node:fs';
import { loadRelease } from '../scripts/plan_production_release.mjs';
const db=new PGlite();
const owner='11111111-1111-4111-8111-111111111111';
const outsider='22222222-2222-4222-8222-222222222222';
const second='33333333-3333-4333-8333-333333333333';
const sql=(q,a=[])=>db.query(q,a);
const role=async(name,uid='')=>{await db.exec('set local role '+name);await sql("select set_config('request.jwt.claim.sub',$1,true)",[uid]);};
const denied=async(fn,code)=>{await db.exec('savepoint expected_failure');await assert.rejects(fn,e=>{assert.equal(e.code,code);return true;});await db.exec('rollback to savepoint expected_failure');};
const init=()=>sql("select public.init_paper_model_v1($1,'live') r",[owner]).then(x=>x.rows[0].r);
const commit=(revision,request,book={experiments:{},trades:{}},evaluations={},day='2026-10-08')=>sql("select public.commit_paper_session_v1($1,'live',$2,$3,$4,$5::jsonb,$6::jsonb) r",[owner,revision,request,day,JSON.stringify(book),JSON.stringify(evaluations)]).then(x=>x.rows[0].r);
before(async()=>{
await db.exec(`create role anon nologin;create role authenticated nologin;create role service_role nologin bypassrls;
create schema auth;create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
grant usage on schema public,auth to anon,authenticated,service_role;
grant execute on function auth.uid() to anon,authenticated,service_role;`);
for(const m of loadRelease().migrations)await db.exec(readFileSync(new URL('../migrations/'+m.file,import.meta.url),'utf8'));
await sql('insert into auth.users values($1),($2),($3)',[owner,outsider,second]);
await sql('insert into public.app_members(user_id) values($1),($2)',[owner,second]);
});
after(async()=>db.close());beforeEach(async()=>db.exec('begin'));afterEach(async()=>db.exec('rollback'));
test('runtime init is immutable and restart restores state without local JSON',async()=>{
await role('service_role');const a=await init();const b=await init();assert.equal(a.activated_at,b.activated_at);assert.equal(a.revision,0);
const r=await commit(0,'first');assert.equal(r.revision,1);
const restored=(await sql("select public.load_paper_runtime_v1($1,'live') r",[owner])).rows[0].r;
assert.deepEqual(restored.book,{experiments:{},trades:{}});assert.equal(restored.last_session,'2026-10-08');assert.equal(restored.revision,1);
});
test('idempotent exact requests replay and altered or stale requests conflict',async()=>{
await role('service_role');await init();const a=await commit(0,'same');assert.deepEqual(await commit(1,'same'),{...a,replayed:true});assert.equal(a.replayed,false);
await denied(()=>commit(1,'same',{experiments:{changed:'hash'},trades:{}}),'PT409');await denied(()=>commit(0,'new'),'PT409');
assert.equal((await sql('select count(*)::int n from public.paper_runtime_requests')).rows[0].n,1);
});
test('service-only runtime and enabled owner/mode validation',async()=>{
await role('authenticated',owner);await denied(init,'42501');
await role('anon');await denied(init,'42501');
await role('service_role');await denied(()=>sql("select public.init_paper_model_v1($1,'live')",[outsider]),'42501');
await denied(()=>sql("select public.init_paper_model_v1($1,'fixture')",[owner]),'22023');
});
test('empty reporting preserves null ratios and denies outsiders',async()=>{
await role('authenticated',owner);const r=(await sql('select public.read_trade_reporting_v1() r')).rows[0].r;
assert.equal(r.summary.closed,0);assert.equal(r.summary.win_rate,null);assert.equal(r.coverage_status,'missing');assert.deepEqual(r.curve,[]);
const ev=(await sql('select public.read_signal_evaluation_v1() r')).rows[0].r;assert.deepEqual(ev.strategies,[]);
await role('authenticated',outsider);await denied(()=>sql('select public.read_trade_reporting_v1()'),'42501');
await denied(()=>sql('select public.read_signal_evaluation_v1()'),'42501');
});

// Synthetic market data only: verifies contracts and monetary invariants, not live outcomes.
async function syntheticTrade(model,{key='a',exit='fixed_rr',state='pending_entry',exitPrice=1150,alternate=null,day='2026-10-09',technicalStop=925}={}){
 const signalId=key.repeat(64);const ticker='TEST'+key.toUpperCase();const strategy='MACD_EMA200_V1';
 const snapshot={id:signalId,ticker,session:'2026-10-08',candidate:{strategy,stop:technicalStop,reference_close:1000},planned_entry_session:'2026-10-09',published_at:model.activated_at,cohort:'forward',data_mode:'live',input_digest:'c'.repeat(64)};
 await role('postgres');
 await sql(`insert into public.signals(id,namespace,data_mode,ticker,strategy,session_date,config_hash,input_digest,universe_version,calendar_version,provider,price_basis,planned_entry_session,cohort,published_at,snapshot)
 values($1,'test','live',$6,$2,'2026-10-08',$3,$3,'synthetic-v1','synthetic-v1','yfinance','raw','2026-10-09','forward',$4,$5::jsonb) on conflict do nothing`,[signalId,strategy,'c'.repeat(64),model.activated_at,JSON.stringify(snapshot),ticker]);
 await role('service_role');
 const experiment={id:'close-signal-risk-v1-'+(exit==='fixed_rr'?'fixed2r':'ma10')+'-'+strategy,strategy,
  exit:exit==='fixed_rr'?{mode:exit,target_r:'2',ma_type:null,period:null,version:'fixed2r-v1'}:{mode:exit,target_r:null,ma_type:'SMA',period:10,version:'ma10-v1'},
  costs:{buy_bps:'15',sell_bps:'25',slippage_bps:'0',status:'verified'},activated_at:model.activated_at,entry_model:'signal_close',risk_budget_idr:'1000000',lot_size:100,model_version:'close-signal-risk-v1'};
 const id=key+'-'+exit;const done=['closed','ambiguous_review'].includes(state);const fee=done?Math.round(12600*exitPrice*0.0025*100)/100:null;const net=done?12600*(exitPrice-1000)-18900-fee:null;
 const events=done?[{session:day,kind:'entry',price:'1000',reason:'assumed_signal_close',observed_at:model.activated_at,input_digest:'c'.repeat(64)},
  {session:day,kind:'exit',price:String(exitPrice),reason:alternate===null?'take_profit':'ambiguous_sl_first',observed_at:model.activated_at,input_digest:'c'.repeat(64),alternate_price:alternate===null?null:String(alternate)}]:[];
 const alt=alternate===null?null:12600*(alternate-1000)-18900-Math.round(12600*alternate*0.0025*100)/100;
 return {id,signal:snapshot,experiment,state,reason:done?'exit':state,entry:done?'1000':null,stop:String(technicalStop),target:exit==='fixed_rr'?String(1000+2*(1000-technicalStop)):null,
  initial_risk:'945000',pending_exit:null,last_session:done?day:null,events,net_pnl:net===null?null:String(net),realized_r:net===null?null:String(net/945000),
  alternate_r:alt===null?null:String(alt/945000),actionable:alternate===null,planned_entry_price:'1000',quantity:12600,lots:126,
  planned_stop_loss_idr:'993037.50',entry_fee_idr:'18900.00',exit_fee_idr:fee===null?null:String(fee),alternate_net_pnl:alt===null?null:String(alt)};
}
const bookOf=(...ts)=>({experiments:Object.fromEntries(ts.map(t=>[t.experiment.id,'immutable-config-hash'])),trades:Object.fromEntries(ts.map(t=>[t.id,t]))});
const report=async(exit='fixed2r',from=null,to=null)=>{await role('authenticated',owner);return(await sql('select public.read_trade_reporting_v1($1,$2,$3,null,$4) r',['paper',from,to,exit])).rows[0].r;};
test('126 lots persists fee-inclusive risk and 127 lots is rejected atomically',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m);const b=bookOf(t);
 await commit(0,'sizing',b);await role('authenticated',owner);const r=await report();
 assert.equal(r.trades[0].lots,126);assert.equal(r.trades[0].planned_loss_idr,993037.5);assert.equal(r.trades[0].initial_price_risk_idr,945000);
 assert.equal(r.trades[0].entry_price,1000);assert.equal(r.trades[0].fee_total_idr,0);assert.equal(r.summary.closed,0);
 await role('service_role');await denied(()=>sql('update public.paper_trades set initial_stop=924 where id=$1',[t.id]),'42501');const changed=structuredClone(b);changed.trades[t.id].lots=127;changed.trades[t.id].quantity=12700;
 await denied(()=>commit(1,'over-budget',changed),'22023');
 assert.equal((await sql('select public.load_paper_runtime_v1($1,$2) r',[owner,'live'])).rows[0].r.revision,1);
});
test('closed PnL, fees, drawdown from zero, and isolated experiment cohorts are canonical',async()=>{
 await role('service_role');const m=await init();const loss=await syntheticTrade(m,{key:'a',state:'closed',exitPrice:925});
 const win=await syntheticTrade(m,{key:'b',state:'closed',day:'2026-10-12'});const ma=await syntheticTrade(m,{key:'c',state:'closed',exit:'ma_close'});
 await commit(0,'closed',bookOf(loss,win,ma),{},'2026-10-12');const r=await report();
 assert.equal(r.summary.closed,2);assert.equal(r.summary.wins,1);assert.equal(r.summary.losses,1);assert.equal(r.summary.win_rate,0.5);
 assert.equal(r.summary.net_pnl_idr,841837.5);assert.equal(r.summary.max_drawdown_idr,993037.5);
 assert.equal(r.curve[0].cumulative_pnl_idr,-993037.5);assert.equal(r.curve[1].cumulative_pnl_idr,841837.5);
 assert.equal(r.strategies[0].net_pnl_idr,r.summary.net_pnl_idr);assert.equal((await report('ma10')).summary.closed,1);
 const filtered=await report('fixed2r','2026-10-12','2026-10-12');assert.equal(filtered.summary.closed,1);assert.equal(filtered.trades.length,1);
 const legacy=(await sql('select public.read_paper_journal() r')).rows[0].r;assert.equal(legacy.trades_count,0);
});
test('ambiguous is excluded from primary but both sensitivity totals retain an explicit denominator',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m,{state:'ambiguous_review',exitPrice:925,alternate:1150});
 await commit(0,'ambiguous',bookOf(t),{},'2026-10-09');const r=await report();
 assert.equal(r.summary.closed,0);assert.equal(r.summary.win_rate,null);assert.equal(r.statuses.ambiguous,1);
 assert.equal(r.sensitivities.sl_first.closed,1);assert.equal(r.sensitivities.sl_first.net_pnl_idr,-993037.5);
 assert.equal(r.sensitivities.tp_first.closed,1);assert.equal(r.sensitivities.tp_first.net_pnl_idr,1834875);
 const detail=(await sql('select public.read_paper_trade_v1($1) r',[t.id])).rows[0].r;
 assert.equal(detail.events.length,2);assert.equal(detail.trade.entry_fee_idr,18900);assert.equal(detail.trade.exit_fee_idr,29137.5);
 assert.equal(detail.trade.config_snapshot.entry_model,'signal_close');assert.equal(detail.trade.alternate_pnl_idr,1834875);
});
test('plans and event prefix are immutable and commit rollback leaves no projection',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m);const b=bookOf(t);await commit(0,'plan',b);
 const closed=await syntheticTrade(m,{state:'closed'});await commit(1,'close',bookOf(closed),{},'2026-10-09');
 const bad=structuredClone(closed);bad.events[0].price='999';await denied(()=>commit(2,'edit-event',bookOf(bad),{},'2026-10-09'),'22023');
 const removed=bookOf();await denied(()=>commit(2,'remove',removed,{},'2026-10-09'),'22023');
 assert.equal((await sql('select count(*)::int n from public.paper_events')).rows[0].n,2);
 await denied(()=>sql('update public.paper_events set event_type=$1',['changed']),'42501');
 await role('authenticated',second);assert.equal((await sql('select * from public.paper_trades')).rows.length,0);
 assert.equal((await sql('select * from public.paper_models')).rows.length,0);assert.equal((await sql('select * from public.paper_events')).rows.length,0);
 assert.equal((await sql('select public.read_paper_trade_v1($1) r',[t.id])).rows[0].r,null);
 assert.equal((await sql('select public.read_trade_reporting_v1() r')).rows[0].r.trades.length,0);
});
test('research denominators distinguish pending, ambiguous, hold and excluded without changing trades',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m);
 const e={signal_id:t.signal.id,ticker:t.signal.ticker,strategy:t.experiment.strategy,signal_session:'2026-10-08',entry_session:'2026-10-09',entry_price:'1000',initial_stop:'925',target_1r:'1075',target_2r:'1150',observed_sessions:5,
  results:{target_1r:'won',target_2r:'ambiguous',net_5:'lost',net_10:'data_hold'},exclusion_reasons:{},signal:t.signal,input_digests:[],provider_symbol:'TEST.JK',model_version:'close-signal-risk-v1',data_mode:'live'};
 await commit(0,'research',bookOf(t),{[t.signal.id]:e});await role('authenticated',owner);
 const r=(await sql('select public.read_signal_evaluation_v1() r')).rows[0].r;
 const c=r.strategies[0].cells;assert.equal(c.target_1r.assessed,1);assert.equal(c.target_1r.win_rate,1);assert.equal(c.target_2r.assessed,0);assert.equal(c.target_2r.ambiguous,1);
 assert.equal(c.net_5.win_rate,0);assert.equal(c.net_10.data_hold,1);assert.equal(c.net_10.win_rate,null);assert.equal(r.coverage_status,'partial');
 assert.equal((await report()).statuses.pending_entry,1);assert.equal((await report()).summary.closed,0);
 const filtered=(await sql('select public.read_signal_evaluation_v1($1,$2) r',['2026-10-09','2026-10-12'])).rows[0].r;assert.deepEqual(filtered.strategies,[]);
 await role('authenticated',second);assert.equal((await sql('select * from public.signal_evaluations')).rows.length,0);
});

test('precise technical stop preserves initial risk and cent-rounded nominal ledger',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m,{technicalStop:925.123456,state:'closed',exitPrice:1149.753088});
 Object.assign(t,{quantity:12700,lots:127,stop:'925.123456',target:'1149.753088',initial_risk:'950932.108800',planned_stop_loss_idr:'999354.78',entry_fee_idr:'19050.00',exit_fee_idr:'36504.66',net_pnl:'1846309.56',realized_r:String(1846309.56/950932.1088)});
 t.events[1].price='1149.753088';await commit(0,'precise',bookOf(t),{},'2026-10-09');const r=await report();
 assert.equal(r.trades[0].initial_stop,925.123456);assert.equal(r.trades[0].initial_price_risk_idr,950932.1088);
 assert.equal(r.trades[0].planned_loss_idr,999354.78);assert.equal(r.trades[0].realized_pnl_idr,1846309.56);
});
test('same semantic request retries with refreshed revision and changed run metadata',async()=>{
 await role('service_role');await init();const a=await commit(0,'stable');
 const b=(await sql('select public.commit_paper_session_v1($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::uuid) r',
  [owner,'live',a.revision,'stable','2026-10-08',JSON.stringify({experiments:{},trades:{}}),'{}',crypto.randomUUID()])).rows[0].r;
 assert.equal(a.replayed,false);assert.equal(b.replayed,true);assert.equal(b.revision,a.revision);assert.equal(b.owner_id,owner);assert.equal(b.data_mode,'live');
});
test('research resolved outcomes, observation chronology and input digest prefix cannot be rewritten',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m);const e={signal_id:t.signal.id,ticker:t.signal.ticker,strategy:t.experiment.strategy,
  signal_session:'2026-10-08',entry_session:'2026-10-09',entry_price:'1000',initial_stop:'925',target_1r:'1075',target_2r:'1150',observed_sessions:1,last_session:'2026-10-09',
  results:{target_1r:'won',target_2r:'pending',net_5:'pending',net_10:'pending'},exclusion_reasons:{},input_digests:['first-bar-digest']};
 await commit(0,'research-start',bookOf(t),{[t.signal.id]:e},'2026-10-09');
 for(const change of [x=>x.results.target_1r='lost',x=>x.input_digests[0]='changed',x=>x.observed_sessions=0,x=>x.last_session='2026-10-08']){
  const bad=structuredClone(e);change(bad);await denied(()=>commit(1,'bad-'+crypto.randomUUID(),bookOf(t),{[t.signal.id]:bad},'2026-10-09'),'22023');
 }
 const progressed=structuredClone(e);progressed.observed_sessions=2;progressed.last_session='2026-10-12';progressed.input_digests.push('second-bar-digest');progressed.results.target_2r='data_hold';
 await commit(1,'research-progress',bookOf(t),{[t.signal.id]:progressed},'2026-10-12');await role('authenticated',owner);
 const r=(await sql('select public.read_signal_evaluation_v1() r')).rows[0].r;assert.equal(r.evaluations[0].entry_price,1000);assert.equal(r.evaluations[0].observed_sessions,2);
});
test('actual reporting uses existing fill ledger, Jakarta exit cohort, and exact exit snapshot filter',async()=>{
 await role('authenticated',owner);const snapshot={version:'fixed2r-v1',mode:'fixed_rr',target_r:2};
 const apply=async(action,id,payload)=>(await sql('select public.apply_actual_journal($1,$2,$3::jsonb,$4) r',[action,id,JSON.stringify(payload),crypto.randomUUID()])).rows[0].r;
 const id=(await apply('create',null,{ticker:'TEST',primary_strategy:'MACD_EMA200_V1',initial_stop:925,exit_policy_snapshot:snapshot})).trade_id;
 await apply('fill',id,{side:'buy',quantity:12600,price_idr:1000,fee_idr:18900,fee_status:'actual',filled_at:'2026-10-08T03:00:00Z',expected_revision:1});
 await apply('finalize',id,{expected_revision:2});
 await apply('fill',id,{side:'sell',quantity:12600,price_idr:1150,fee_idr:36225,fee_status:'actual',filled_at:'2026-10-09T17:01:00Z',expected_revision:3});
 const r=(await sql('select public.read_trade_reporting_v1($1,$2,$3,null,$4,1,$5,$6::jsonb) r',['actual','2026-10-10','2026-10-10',null,'fixed2r-v1',JSON.stringify(snapshot)])).rows[0].r;
 assert.equal(r.summary.closed,1);assert.equal(r.summary.net_pnl_idr,1834875);assert.equal(r.trades[0].entry_price,1000);assert.equal(r.trades[0].exit_session,'2026-10-10');
 const excluded=(await sql('select public.read_trade_reporting_v1($1,null,null,null,$2,1,null,$3::jsonb) r',['actual','fixed2r',JSON.stringify({...snapshot,target_r:3})])).rows[0].r;assert.equal(excluded.summary.closed,0);
});

test('actual curve orders same-session exits by close timestamp before UUID',async()=>{
 await role('authenticated',owner);const apply=async(action,id,payload)=>(await sql('select public.apply_actual_journal($1,$2,$3::jsonb,$4) r',[action,id,JSON.stringify(payload),crypto.randomUUID()])).rows[0].r;
 const create=()=>apply('create',null,{ticker:'TEST',primary_strategy:'MACD_EMA200_V1',initial_stop:90,exit_policy_snapshot:{version:'fixed2r-v1',mode:'fixed_rr',target_r:2}});
 const ids=[(await create()).trade_id,(await create()).trade_id].sort();const lossId=ids[1],winId=ids[0];
 for(const [id,price,time] of [[lossId,95,'2026-10-09T03:00:00Z'],[winId,110,'2026-10-09T04:00:00Z']]){
  await apply('fill',id,{side:'buy',quantity:100,price_idr:100,fee_idr:0,fee_status:'actual',filled_at:'2026-10-08T03:00:00Z',expected_revision:1});
  await apply('finalize',id,{expected_revision:2});
  await apply('fill',id,{side:'sell',quantity:100,price_idr:price,fee_idr:0,fee_status:'actual',filled_at:time,expected_revision:3});
 }
 const r=(await sql('select public.read_trade_reporting_v1($1,null,null,null,null) r',['actual'])).rows[0].r;
 assert.equal(r.curve[0].trade_id,lossId);assert.equal(r.curve[1].trade_id,winId);assert.equal(r.summary.max_drawdown_idr,500);
 assert.equal(r.sensitivities.sl_first.max_drawdown_idr,500);
});
test('legacy paper rows remain visible only through legacy reader',async()=>{
 await sql(`insert into public.paper_trades(id,owner_id,data_mode,ticker,strategy,experiment_id,exit_mode,state,reason,realized_r)
 values('legacy-only',$1,'live','TEST','MACD_EMA200_V1','old-fixed2r','fixed_rr','closed','legacy',2)`,[owner]);
 await role('service_role');const m=await init();const t=await syntheticTrade(m);await commit(0,'new-only',bookOf(t));
 await role('authenticated',owner);const legacy=(await sql('select public.read_paper_journal() r')).rows[0].r;
 assert.equal(legacy.trades_count,1);assert.equal(legacy.trades[0].id,'legacy-only');assert.equal((await report()).trades.length,1);
});

test('local sibling frontend parsers accept canonical SQL reporting, research and detail responses',
 {skip:!existsSync(new URL('../../../frontend/src/lib/trade-reporting.ts',import.meta.url))},async()=>{
 const {parseTradeReporting,parseSignalEvaluation,parsePaperTradeDetail}=await import('../../../frontend/src/lib/trade-reporting.ts');
 const f={from:null,to:null,strategy:null,exitVersion:null,exitSnapshot:null,exitSnapshotKey:null,exitKey:'fixed2r',page:1};
 await role('service_role');const m=await init();const t=await syntheticTrade(m,{state:'closed'});
 const e={signal_id:t.signal.id,ticker:t.signal.ticker,strategy:t.experiment.strategy,signal_session:'2026-10-08',entry_session:'2026-10-09',entry_price:'1000',initial_stop:'925',target_1r:'1075',target_2r:'1150',observed_sessions:1,last_session:'2026-10-09',results:{target_1r:'won',target_2r:'won',net_5:'pending',net_10:'pending'},exclusion_reasons:{},input_digests:[]};
 await commit(0,'cross-repo',bookOf(t),{[t.signal.id]:e},'2026-10-09');const paper=await report();
 assert.ok(parseTradeReporting(paper,'live','paper',f),'paper SQL response parses');
 const actual=(await sql('select public.read_trade_reporting_v1($1,null,null,null,null) r',['actual'])).rows[0].r;
 assert.ok(parseTradeReporting(actual,'live','actual',f),'actual SQL response parses');
 const research=(await sql('select public.read_signal_evaluation_v1() r')).rows[0].r;
 assert.ok(parseSignalEvaluation(research,'live',f),'research SQL response parses');
 const detail=(await sql('select public.read_paper_trade_v1($1) r',[t.id])).rows[0].r;
 assert.ok(parsePaperTradeDetail(detail,'live',t.id),'paper detail SQL response parses');
});

test('missing RR or mismatched frozen target fails closed before any projection',async()=>{
 await role('service_role');const m=await init();const t=await syntheticTrade(m);
 const missing=structuredClone(t);missing.experiment.exit.target_r=null;
 await denied(()=>commit(0,'missing-rr',bookOf(missing)),'22023');
 const wrong=structuredClone(t);wrong.target='1200';await denied(()=>commit(0,'wrong-target',bookOf(wrong)),'22023');
 assert.equal((await sql('select count(*)::int n from public.paper_trades')).rows[0].n,0);
 assert.equal((await sql('select public.load_paper_runtime_v1($1,$2) r',[owner,'live'])).rows[0].r.revision,0);
});
