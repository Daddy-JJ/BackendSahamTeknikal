import assert from 'node:assert/strict';
import {before, after, beforeEach, afterEach, test} from 'node:test';
import {readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {PGlite} from '@electric-sql/pglite';
import {owner, outsider, role} from './helpers/paper-reporting-fixture.mjs';

let db;
before(async()=>{
  db=new PGlite();
  await db.exec(`create role anon nologin;create role authenticated nologin;create role service_role nologin bypassrls;
    create schema auth;create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema public,auth to anon,authenticated,service_role;grant execute on function auth.uid() to anon,authenticated,service_role;`);
  for(const file of readdirSync(new URL('../migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())
    await db.exec(readFileSync(new URL('../migrations/'+file,import.meta.url),'utf8'));
  await db.query('insert into auth.users values($1),($2)',[owner,outsider]);
  await db.query('insert into public.app_members(user_id) values($1)',[owner]);
});
after(async()=>db?.close());
beforeEach(async()=>db.exec('begin'));
afterEach(async()=>db.exec('rollback'));

const days=['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09'];
const indicators=Object.fromEntries(['sma10','ema200','macd','macd_signal','macd_histogram'].map(name=>[name,{
  status:'ready',reason:null,definition_version:'canonical-v1',artifact_digest:'c'.repeat(64),history_count:5,eligible_from:null,
  points:days.map(session=>({session,value:1}))
}]));
async function seed({revision='d'.repeat(64),scope='forward',context='latest',contextId=null,overlays=null}={}){
  await role(db,'postgres');
  const series='33333333-3333-4333-8333-333333333333';
  await db.query(`insert into public.market_series_revisions(id,namespace,data_mode,provider,ticker,provider_symbol,price_basis,
    provider_version,input_digest,snapshot_hash,metadata,bar_count,bar_cutoff,fetched_at)
    values($1,'forward','live','yfinance','ADRO','ADRO.JK','yahoo_provider_ohlcv_auto_adjust_false_v1','v1',repeat('a',64),repeat('a',32),'{}',0,0,'2026-10-09T10:00:00Z')
    on conflict do nothing`,[series]);
  const source={series_id:series,input_digest:'a'.repeat(64),resolved_input_digest:'b'.repeat(64),resolved_cutoff:days.at(-1),
    provider:'yfinance',provider_version:'v1',price_basis:'yahoo_provider_ohlcv_auto_adjust_false_v1',scope,
    fetched_at:'2026-10-09T10:00:00Z',stored_at:'2026-10-09T10:01:00Z',history_start:days[0],last_market_session:days.at(-1)};
  const data={ticker:'ADRO',data_mode:'live',timeframe:'1d',exchange:'XIDX',timezone:'Asia/Jakarta',currency:'IDR',volume_unit:'shares',
    context:{kind:context,id:contextId,view:'followup',signal_session:null,snapshot_cutoff:null,model_version:null,experiment:null,engine_source_revision:null},
    revision,source,signal_source:null,quality:{completeness:'partial',freshness:'stale',expected_session:'2026-10-09',reasons:['missing_bar'],warnings:[]},
    sessions:days,bars:days.filter((_,i)=>i!==2).map(session=>({session,open:'100',high:'110',low:'90',close:'105',volume:'1000'})),
    gaps:[{session:days[2],reason:'missing_bar'}],indicators,
    overlays:overlays??{status:'ready',reason:null,levels:[],markers:[],has_more:false,next_cursor:null}};
  await role(db,'service_role');
  return {record:{owner_id:owner,data_mode:'live',ticker:'ADRO',context_kind:context,context_id:contextId,view:'followup',revision,data},data};
}
const write=async record=>(await db.query('select public.persist_ticker_chart_artifact_v1($1::jsonb) r',[JSON.stringify(record)])).rows[0].r;
const read=async request=>(await db.query('select public.read_ticker_chart_v1($1::jsonb) r',[JSON.stringify(request)])).rows[0].r;
async function denied(fn,code){await db.exec('savepoint denied');await assert.rejects(fn,e=>{assert.equal(e.code,code);return true;});await db.exec('rollback to savepoint denied');}

test('artifact writer replays immutable content and rejects changed revision payload',async()=>{
  const {record}=await seed(); assert.equal((await write(record)).replayed,false);assert.equal((await write(record)).replayed,true);
  const altered=structuredClone(record);altered.data.bars[0].close='106';await denied(()=>write(altered),'23514');
});
test('reader owner-only and writer service-only; direct tables cannot bypass reader limiter',async()=>{
  const {record}=await seed();await write(record);
  await role(db,'authenticated',owner);assert.equal((await read({ticker:'ADRO'})).success,true);
  await denied(()=>write(record),'42501');await denied(()=>db.query('select * from public.ticker_chart_artifacts_v1'),'42501');
  await role(db,'authenticated',outsider);assert.equal((await read({ticker:'ADRO'})).error.code,'FORBIDDEN');
  await role(db,'anon');await denied(()=>read({ticker:'ADRO'}),'42501');
});
test('strict request bounds reject arbitrary scope, mode, malformed dates and boolean limit',async()=>{
  const {record}=await seed();await write(record);await role(db,'authenticated',owner);
  for(const request of [null,[],"ADRO",{ticker:'ADRO',data_mode:'fixture'},{ticker:'ADRO',limit:true},{ticker:'ADRO',limit:1.5},{ticker:'ADRO',limit:501},
    {ticker:'ADRO',from:'2026-02-30'},{ticker:'ADRO',context:'actual',context_id:'x',view:'snapshot'},
    {ticker:'ADRO',from:'99999-01-01'},{ticker:'ADRO',cursor:'x'.repeat(2049)},
    {ticker:'ADRO',cursor:'x',to:'2026-10-09'}]) assert.equal((await read(request)).error.code,'INVALID_REQUEST');
});
test('bar pagination includes gap slots, crops indicator points, and pins immutable revision',async()=>{
  const {record}=await seed();await write(record);await role(db,'authenticated',owner);
  const first=(await read({ticker:'ADRO',limit:2,to:'2026-10-09'})).data;
  assert.deepEqual(first.sessions,days.slice(-2));assert.equal(first.pagination.has_more,true);assert.equal(first.indicators.sma10.points.length,2);
  await role(db,'service_role');const later=structuredClone(record);later.revision='e'.repeat(64);later.data.revision=later.revision;await write(later);
  await role(db,'authenticated',owner);const next=(await read({ticker:'ADRO',limit:2,cursor:first.pagination.next_cursor})).data;
  assert.equal(next.revision,record.revision);assert.deepEqual(next.sessions,days.slice(1,3));assert.equal(next.gaps.length,1);assert.equal(next.bars.length,1);
  assert.equal((await read({ticker:'OTHER',limit:2,cursor:first.pagination.next_cursor})).error.code,'INVALID_REQUEST');
});
test('overlay pages retain revision and contain no candle slots',async()=>{
  const markers=Array.from({length:503},(_,i)=>({id:'event-'+String(i).padStart(4,'0'),kind:'signal',session:days.at(-1),available_session:days.at(-1),price:'100',source_id:'s',status:'confirmed'}));
  const {record}=await seed({overlays:{status:'ready',reason:null,levels:[],markers,has_more:false,next_cursor:null}});await write(record);await role(db,'authenticated',owner);
  const first=(await read({ticker:'ADRO',limit:5,to:'2026-10-09'})).data;assert.equal(first.overlays.markers.length,500);assert.equal(first.overlays.has_more,true);
  const next=(await read({ticker:'ADRO',limit:5,cursor:first.overlays.next_cursor})).data;
  assert.equal(next.overlays.markers.length,3);assert.deepEqual(next.sessions,[]);assert.equal(next.pagination.returned_slots,0);
  assert.equal(next.indicators.macd.reason,'overlay_page');assert.equal(next.revision,first.revision);
});
test('burst limiter shared by direct RPC calls; expired cursor cannot fallback latest',async()=>{
  const {record}=await seed();await write(record);await role(db,'authenticated',owner);
  for(let i=0;i<10;i++) assert.equal((await read({ticker:'ADRO'})).success,true);
  // Shared CPU load may take >1s and legitimately refill tokens. Pin an exhausted
  // token balance in the fixture rather than depending on wall-clock speed.
  await role(db,'postgres');
  assert.equal((await db.query('select cardinality(reads)::int n from chart_private.read_limits_v1 where owner_id=$1',[owner])).rows[0].n,10);
  await db.exec("update chart_private.read_limits_v1 set tokens=0,updated_at=clock_timestamp()+interval '1 minute'");
  await role(db,'authenticated',owner);
  assert.equal((await read({ticker:'ADRO'})).error.code,'RATE_LIMITED');
  await role(db,'postgres');await db.exec('delete from chart_private.read_limits_v1');await role(db,'authenticated',owner);
  const first=(await read({ticker:'ADRO',limit:2})).data;await role(db,'postgres');await db.exec("update chart_private.cursors_v1 set expires_at=now()-interval '1 day'");
  await role(db,'authenticated',owner);assert.equal((await read({ticker:'ADRO',limit:2,cursor:first.pagination.next_cursor})).error.code,'REVISION_UNAVAILABLE');
});
test('paper recovery scope never serves latest context; missing chart remains explicit',async()=>{
  const {record}=await seed({scope:'paper_recovery'});await denied(()=>write(record),'22023');
  await role(db,'authenticated',owner);assert.equal((await read({ticker:'ADRO'})).error.code,'DATA_UNAVAILABLE');
});

test('snapshot proves frozen digest and excludes fills known after cutoff while retaining future plans',async()=>{
  const id='f'.repeat(64),{record}=await seed({context:'signal',contextId:'f'.repeat(64)});
  await role(db,'postgres');
  await db.query(`insert into public.signals(id,namespace,data_mode,ticker,strategy,session_date,config_hash,input_digest,
    universe_version,calendar_version,provider,price_basis,planned_entry_session,cohort,published_at,snapshot)
    values($1,'forward','live','ADRO','MACD_EMA200_V1','2026-10-08',repeat('b',64),repeat('b',64),'v1','v1','yfinance',
    'yahoo_provider_ohlcv_auto_adjust_false_v1','2026-10-09','forward','2026-10-08T10:00:00Z','{}')`,[id]);
  record.view='snapshot';record.data.context={...record.data.context,view:'snapshot',signal_session:'2026-10-08',snapshot_cutoff:'2026-10-08'};
  record.data.source={...record.data.source,resolved_cutoff:'2026-10-08',last_market_session:'2026-10-08'};
  record.data.signal_source=structuredClone(record.data.source);record.data.sessions=days.slice(0,4);
  record.data.bars=record.data.bars.filter(b=>b.session<='2026-10-08');
  record.data.indicators=Object.fromEntries(Object.entries(record.data.indicators).map(([key,value])=>[key,{...value,points:value.points.slice(0,4)}]));
  record.data.overlays={status:'ready',reason:null,has_more:false,next_cursor:null,
    levels:[{id:'planned',kind:'planned_entry',price:'100',starts_at:'2026-10-09',ends_at:null,available_session:'2026-10-08',origin_session:null,source_id:id,status:'planned'}],
    markers:[{id:'future-fill',kind:'entry_fill',session:'2026-10-09',available_session:'2026-10-09',price:'100',source_id:id,status:'simulated'}]};
  await role(db,'service_role');await write(record);await role(db,'authenticated',owner);
  const result=(await read({ticker:'ADRO',context:'signal',context_id:id})).data;
  assert.equal(result.quality.freshness,'current');assert.equal(result.quality.expected_session,'2026-10-08');
  assert.equal(result.overlays.levels.length,1);assert.deepEqual(result.overlays.markers,[]);assert.equal(result.pagination.window_to,'2026-10-08');
  assert.equal((await read({ticker:'ADRO',context:'signal',context_id:id,to:'2026-10-09'})).error.code,'INVALID_REQUEST');
  await role(db,'postgres');
  await db.query(`insert into public.paper_trades(id,owner_id,data_mode,signal_id,ticker,strategy,experiment_id,exit_mode,state,reason)
    values('legacy-paper-not-uuid',$1,'live',$2,'ADRO','MACD_EMA200_V1','legacy-fixed','fixed_rr','pending_entry','planned')`,[owner,id]);
  const paper=structuredClone(record);paper.context_kind='paper';paper.context_id='legacy-paper-not-uuid';paper.revision='9'.repeat(64);
  paper.data.revision=paper.revision;paper.data.context={...paper.data.context,kind:'paper',id:paper.context_id};
  await role(db,'service_role');await write(paper);await role(db,'authenticated',owner);
  assert.equal((await read({ticker:'ADRO',context:'paper',context_id:paper.context_id,view:'snapshot'})).success,true);
  assert.equal((await read({ticker:'INDY',context:'paper',context_id:paper.context_id,view:'snapshot'})).error.code,'NOT_FOUND');
  await role(db,'service_role');const bad=structuredClone(record);bad.data.signal_source.resolved_input_digest='0'.repeat(64);
  await denied(()=>write(bad),'22023');
});

test('actual context ownership is checked independently of app membership and ticker',async()=>{
  const {record}=await seed();await write(record);await role(db,'postgres');
  const actual=(await db.query(`insert into public.actual_trades(owner_id,data_mode,ticker,primary_strategy,exit_policy_snapshot,initial_stop,current_stop)
    values($1,'live','ADRO','MACD_EMA200_V1','{}',90,90) returning id`,[outsider])).rows[0].id;
  await role(db,'authenticated',owner);
  assert.equal((await read({ticker:'ADRO',context:'actual',context_id:actual})).error.code,'NOT_FOUND');
  const loadedDenied=()=>db.query('select public.load_ticker_chart_inputs_v1($1,$2)',[owner,'ADRO']);
  await denied(loadedDenied,'42501');await role(db,'service_role');
  const loaded=(await db.query('select public.load_ticker_chart_inputs_v1($1,$2) r',[owner,'ADRO'])).rows[0].r;
  assert.deepEqual(loaded.actual_trades,[]);
});

test('rolling minute budget is enforced even when burst tokens remain',async()=>{
  const {record}=await seed();await write(record);await role(db,'authenticated',owner);await read({ticker:'ADRO'});
  await role(db,'postgres');await db.exec("update chart_private.read_limits_v1 set reads=array_fill(clock_timestamp(),array[60]),tokens=10");
  await role(db,'authenticated',owner);assert.equal((await read({ticker:'ADRO'})).error.code,'RATE_LIMITED');
});

test('invalid OHLC partition, prices and indicator session order reject atomically',async()=>{
  const {record}=await seed();
  for(const change of [d=>d.bars[0].low='106',d=>d.bars[0].volume='-1',d=>d.gaps=[],
    d=>d.indicators.sma10.points[0].session=days[1],d=>d.sessions.reverse()]) {
    const bad=structuredClone(record);change(bad.data);await denied(()=>write(bad),'22023');
  }
  await role(db,'postgres');
  assert.equal((await db.query('select count(*)::int n from public.ticker_chart_artifacts_v1')).rows[0].n,0);
});

test('the same source artifact revision can belong to separate active owners without conflict',async()=>{
  const {record}=await seed();await write(record);await role(db,'postgres');
  await db.query('insert into public.app_members(user_id) values($1)',[outsider]);
  await role(db,'service_role');await write({...record,owner_id:outsider});
  await role(db,'authenticated',outsider);assert.equal((await read({ticker:'ADRO'})).success,true);
  await role(db,'postgres');await db.query('update public.app_members set enabled=false where user_id=$1',[outsider]);
  await role(db,'authenticated',outsider);assert.equal((await read({ticker:'ADRO'})).error.code,'FORBIDDEN');
});

test('canonical Python artifact roundtrips market receipt, SQL writer and bounded chart reader',async()=>{
  const python=process.env.SCANNER_TEST_PYTHON||fileURLToPath(new URL(process.platform==='win32'?'../../scanner/.venv/Scripts/python.exe':'../../scanner/.venv/bin/python',import.meta.url));
  const helper=fileURLToPath(new URL('./helpers/export-chart-artifact.py',import.meta.url));
  const exported=id=>JSON.parse(execFileSync(python,[helper,'--owner-id',owner,...(id?['--series-id',id]:[])],{encoding:'utf8'}));
  const raw=exported();await db.exec("update public.deployment_settings set data_mode='fixture'");await role(db,'service_role');
  const receipt=(await db.query('select public.ingest_market_series($1::jsonb) r',[JSON.stringify(raw.market_record)])).rows[0].r;
  const canonical=exported(receipt.revision_id);await write(canonical.p_record);await role(db,'authenticated',owner);
  const request={ticker:canonical.p_record.ticker,limit:5};const result=await read(request);
  assert.equal(result.success,true);assert.deepEqual(result.data.sessions,canonical.p_record.data.sessions.slice(-5));
  assert.deepEqual(result.data.indicators.sma10.points,canonical.p_record.data.indicators.sma10.points.slice(-5));
  assert.equal(result.data.source.series_id,receipt.revision_id);assert.equal(result.data.source.input_digest,raw.market_record.input_digest);
  const previous=await read({...request,cursor:result.data.pagination.next_cursor});
  assert.equal(previous.data.revision,result.data.revision);
  if(process.env.CHART_EXPORT_FIXTURE==='1') writeFileSync(new URL('./fixtures/ticker-chart-v1.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
});

test('fallback from an unusable newer receipt stays stale even when its valid session matches expected',async()=>{
  const python=process.env.SCANNER_TEST_PYTHON||fileURLToPath(new URL(process.platform==='win32'?'../../scanner/.venv/Scripts/python.exe':'../../scanner/.venv/bin/python',import.meta.url));
  const exported=id=>JSON.parse(execFileSync(python,['-c',
    `import json;from idx_scanner.chart_fixture import synthetic_chart_export;print(json.dumps(synthetic_chart_export('${owner}','${id}')))`],{encoding:'utf8'}));
  await role(db,'postgres');await db.exec("update public.deployment_settings set data_mode='fixture'");
  await role(db,'service_role');const raw=exported('33333333-3333-4333-8333-333333333333');
  const receipt=(await db.query('select public.ingest_market_series($1::jsonb) r',[JSON.stringify(raw.market_record)])).rows[0].r;
  const canonical=exported(receipt.revision_id);
  canonical.p_record.data.quality={...canonical.p_record.data.quality,freshness:'stale',completeness:'partial',warnings:['newer_receipt_unusable']};
  await write(canonical.p_record);await role(db,'authenticated',owner);
  const result=await read({ticker:canonical.p_record.ticker,limit:5});
  assert.equal(result.success,true);
  assert.equal(result.data.quality.expected_session,result.data.source.last_market_session);
  assert.equal(result.data.quality.freshness,'stale');
  assert.ok(result.data.quality.warnings.includes('newer_receipt_unusable'));
});
