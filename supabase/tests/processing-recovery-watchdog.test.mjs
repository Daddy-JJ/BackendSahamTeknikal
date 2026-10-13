// Disposable synthetic SQL/Vault/HTTP fixtures; never performs network requests.
import assert from 'node:assert/strict';
import {before,after,beforeEach,afterEach,test} from 'node:test';
import {readFileSync} from 'node:fs';
import {database,owner,outsider,role,init,trade,bookOf,commit,evaluation,observations} from './helpers/paper-reporting-fixture.mjs';
let db;
before(async()=>{db=await database();});after(async()=>db?.close());
beforeEach(async()=>db.exec('begin'));afterEach(async()=>db.exec('rollback'));
const denied=async(fn,code)=>{await db.exec('savepoint denied');await assert.rejects(fn,e=>{assert.equal(e.code,code);return true;});await db.exec('rollback to savepoint denied');};
const health=async at=>(await db.query("select public.paper_processing_health_v1($1,'live',$2) r",[owner,at])).rows[0].r;
const policy=async at=>(await db.query('select paper_ops_private.watchdog_plan_v1($1) r',[at])).rows[0].r;
const cfg=async()=>{await role(db,'postgres');await db.query("update paper_ops_private.watchdog_config set enabled=true,edge_ready=true,owner_id=$1,data_mode='live' where singleton",[owner]);};
const checkpoint=async(day='2026-10-08')=>{await init(db);await commit(db,bookOf(),{},0,'initial',day);await role(db,'postgres');};
const receipt=async(at,number=1,status='completed',target='2026-10-09',lease=at)=>db.query(`insert into public.paper_watchdog_receipts_v1
  (owner_id,data_mode,session_date,attempt,paper_only,requested_at,lease_until,status)
  values($1,'live',$2,$3,true,$4,$5,$6)`,[owner,target,number,at,lease,status]);

test('012 is inactive until operator configuration and migration never dispatches',async()=>{
  assert.deepEqual(await policy('2026-10-10T11:00:00Z'),{dispatch:false,reason:'disabled'});
  assert.deepEqual((await db.query('select public.run_paper_watchdog_v1() r')).rows[0].r,{dispatch:false,reason:'disabled'});
  assert.equal((await db.query('select count(*)::int n from public.paper_watchdog_receipts_v1')).rows[0].n,0);
  const sql=readFileSync(new URL('../migrations/202610130012_processing_recovery_watchdog.sql',import.meta.url),'utf8');
  assert.doesNotMatch(sql,/create extension|cron\.schedule\(/i);
});

test('attempt checkpoint cannot hide unfilled/filled trade and research cursors; counts are explicit',async()=>{
  const m=await init(db),filled=await trade(db,m,{key:'a',state:'open'}),unfilled=await trade(db,m,{key:'b',state:'data_hold'});
  filled.state='data_hold';filled.reason='missing_bar';unfilled.reason='missing_bar';
  const e=evaluation(filled);e.last_session='2026-10-09';e.observed_sessions=1;e.input_digests=observations('2026-10-09');
  e.results={target_1r:'data_hold',target_2r:'data_hold',net_5:'data_hold',net_10:'data_hold'};
  await commit(db,bookOf(filled,unfilled),{[e.signal_id]:e},0,'held','2026-10-12');await role(db,'postgres');
  const h=await health('2026-10-12T11:00:00Z');
  assert.equal(h.attempt_session,'2026-10-12');assert.equal(h.processed_session,h.attempt_session);
  assert.equal(h.earliest_unresolved_session,'2026-10-09');assert.equal(h.overdue,true);
  assert.equal(h.trade_data_hold_count,2);assert.equal(h.evaluation_data_hold_count,1);assert.equal(h.data_hold_count,3);
  assert.equal(h.filled_trade_data_hold_count,1);assert.equal(h.unfilled_trade_data_hold_count,1);
  assert.equal(h.scope,'all_experiments_and_evaluations');assert.equal(h.last_fully_resolved_session,'2026-10-08');
});

test('open positions and pending research need data through expected day, not a forced exit',async()=>{
  const m=await init(db),t=await trade(db,m,{state:'open'}),e=evaluation(t);
  e.last_session='2026-10-09';e.observed_sessions=1;e.input_digests=observations('2026-10-09');
  e.results.target_1r='won';e.results.target_2r='won';
  await commit(db,bookOf(t),{[e.signal_id]:e},0,'open','2026-10-12');await role(db,'postgres');
  const before=await health('2026-10-12T01:00:00Z');
  assert.equal(before.overdue,false);assert.equal(before.last_fully_resolved_session,'2026-10-09');
  const after=await health('2026-10-12T11:00:00Z');
  assert.equal(after.overdue,true);assert.equal(after.earliest_unresolved_session,'2026-10-12');
  assert.equal(after.last_fully_resolved_session,'2026-10-09');assert.equal(after.trade_data_hold_count,0);
  const frozen=(await db.query('select details from public.paper_trades where id=$1',[t.id])).rows[0].details;
  assert.equal(frozen.state,'open');assert.equal(frozen.initial_risk,'945000');
});

test('legitimate ambiguity and finished research are resolved with no additional processing',async()=>{
  const m=await init(db),t=await trade(db,m,{state:'ambiguous_review',exitPrice:925,alternate:1150}),e=evaluation(t);
  e.last_session='2026-10-09';e.observed_sessions=1;e.input_digests=observations('2026-10-09');
  e.results={target_1r:'lost',target_2r:'ambiguous',net_5:'lost',net_10:'lost'};
  await commit(db,bookOf(t),{[e.signal_id]:e},0,'ambiguous','2026-10-12');await role(db,'postgres');
  const h=await health('2026-10-12T11:00:00Z');
  assert.equal(h.overdue,false);assert.equal(h.last_fully_resolved_session,'2026-10-12');assert.equal(h.earliest_unresolved_session,null);
});

test('detail processing timestamp is persisted time, independent from historical entry session',async()=>{
  const m=await init(db),t=await trade(db,m,{state:'open'});await commit(db,bookOf(t));await role(db,'authenticated',owner);
  const r=(await db.query('select public.read_paper_trade_v1($1) r',[t.id])).rows[0].r;
  assert.equal(r.trade.entry_session,'2026-10-09');assert.equal(r.trade.processing.last_processed_session,'2026-10-09');
  assert.equal(r.trade.processing.contract_version,1);assert.ok(r.trade.processing.entry_processed_at);
  assert.equal(r.events[0].recorded_at,r.trade.processing.entry_processed_at);
  assert.notEqual(r.events[0].recorded_at,t.events[0].observed_at);
  await role(db,'postgres');assert.equal((await db.query('select created_at from public.paper_events where trade_id=$1',[t.id])).rows[0].created_at.toISOString(),new Date(r.events[0].recorded_at).toISOString());
});

test('owner/outsider/anonymous cannot dispatch, configure, inspect secrets, leases or private health helpers',async()=>{
  await checkpoint();await cfg();await receipt('2026-10-10T10:00:00Z');
  for(const [name,id] of [['anon',''],['authenticated',owner],['authenticated',outsider],['service_role','']]){
    await role(db,name,id);
    for(const query of ['select public.run_paper_watchdog_v1()',"select public.configure_paper_watchdog_v1($1,'live',false,false)",
      "select paper_ops_private.watchdog_plan_v1(now())",'select * from paper_ops_private.watchdog_config','select * from paper_ops_private.runtime_lease'])
      await denied(()=>db.query(query,query.includes('$1')?[owner]:[]),'42501');
    if(name==='authenticated')assert.equal((await db.query('select * from public.paper_watchdog_receipts_v1')).rows.length,id===owner?1:0);
    if(name==='anon')await denied(()=>db.query('select * from public.paper_watchdog_receipts_v1'),'42501');
  }
  await role(db,'authenticated',owner);
  const h=(await db.query('select public.read_paper_processing_health_v1() r')).rows[0].r;
  assert.equal(h.watchdog.enabled,true);assert.equal(JSON.stringify(h).includes('vault_secret_id'),false);
  await denied(()=>db.query("select public.claim_paper_runtime_lease_v1($1,'live','owner-abuse','2026-10-09')",[owner]),'42501');
});

test('lease claim retries for same job are safe; other live jobs cannot take over or release it',async()=>{
  await init(db);await role(db,'service_role');
  const claim=async job=>(await db.query("select public.claim_paper_runtime_lease_v1($1,'live',$2,'2026-10-09') r",[owner,job])).rows[0].r;
  assert.equal((await claim('run-a')).acquired,true);assert.equal((await claim('run-a')).acquired,true);
  assert.equal((await claim('run-b')).acquired,false);
  await denied(()=>db.query("select public.heartbeat_paper_runtime_lease_v1($1,'live','run-b')",[owner]),'PT409');
  await db.query("select public.release_paper_runtime_lease_v1($1,'live','run-b')",[owner]);assert.equal((await claim('run-b')).acquired,false);
  await db.query("select public.heartbeat_paper_runtime_lease_v1($1,'live','run-a')",[owner]);
  await db.query("select public.release_paper_runtime_lease_v1($1,'live','run-a')",[owner]);assert.equal((await claim('run-b')).acquired,true);
  await denied(()=>db.query("select public.claim_paper_runtime_lease_v1($1,'live','run-future','2099-01-01')",[owner]),'22023');
  await denied(()=>db.query("select public.claim_paper_runtime_lease_v1($1,'fixture','run-mismatch','2026-10-09')",[owner]),'22023');
});

test('expired/replaced worker cannot win revision CAS or publish, and rotation is stable per job',async()=>{
  const model=await init(db), t=await trade(db,model,{state:'open'});
  await role(db,'service_role');
  const claim=async job=>(await db.query("select public.claim_paper_runtime_lease_v1($1,'live',$2,'2026-10-09') r",[owner,job])).rows[0].r;
  const first=await claim('old');assert.equal((await claim('old')).recovery_sequence,first.recovery_sequence);
  await role(db,'postgres');await db.exec("update paper_ops_private.runtime_lease set expires_at=clock_timestamp()-interval '1 second'");
  await role(db,'service_role');const second=await claim('new');assert.ok(second.recovery_sequence>first.recovery_sequence);
  const write=async job=>db.query(`select public.commit_paper_session_with_lease_v1($1,'live',0,$2,'2026-10-09',$3,'{}',null,$4) r`,[owner,'fenced-'+job,bookOf(t),job]);
  await denied(()=>write('old'),'PT409');
  await denied(()=>db.query("select public.publish_scan_with_lease_v1($1,'[]',$2,'old')",[{data_mode:'live',session:'2026-10-09'},owner]),'PT409');
  await denied(()=>commit(db,bookOf(t),{},0,'legacy-bypass','2026-10-09'),'PT409');
  await role(db,'service_role');
  await denied(()=>db.query("select public.publish_scan($1,'[]')",[{data_mode:'live',session:'2026-10-09'}]),'PT409');
  assert.equal((await write('new')).rows[0].r.revision,1);
  await db.query("select public.release_paper_runtime_lease_v1($1,'live','new')",[owner]);
  await denied(()=>write('old'),'PT409');
  await role(db,'postgres');
  assert.equal((await db.query('select revision from public.paper_models where owner_id=$1',[owner])).rows[0].revision,1);
});

test('fresh runtime lease suppresses watchdog; stale heartbeat is visible and permits bounded recovery',async()=>{
  await checkpoint();await cfg();
  await db.query("insert into paper_ops_private.runtime_lease values($1,'live','run-a','2026-10-09','2026-10-10T10:59:00Z','2026-10-10T11:09:00Z')",[owner]);
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'runtime_active');
  assert.equal((await health('2026-10-10T11:00:00Z')).status,'running');
  assert.equal((await health('2026-10-10T11:10:00Z')).runtime_stalled,true);
  assert.equal((await policy('2026-10-10T11:10:00Z')).dispatch,true);
});

test('stalled finalization remains degraded even when all economic cursors are resolved',async()=>{
  await checkpoint('2026-10-09');await cfg();
  await db.query("insert into paper_ops_private.runtime_lease values($1,'live','killed-after-commit','2026-10-09','2026-10-10T10:00:00Z','2026-10-10T10:10:00Z')",[owner]);
  const h=await health('2026-10-10T11:00:00Z');
  assert.equal(h.status,'overdue');assert.equal(h.overdue,true);assert.equal(h.earliest_unresolved_session,null);
  assert.equal(h.last_fully_resolved_session,'2026-10-09');assert.equal(h.runtime_stalled,true);
  assert.equal(h.operational_failure_code,'heartbeat_stalled');assert.equal(h.latest_job_status,null);
});

test('policy dispatches only verified closed calendar sessions; pre-market full and expired-window paper-only',async()=>{
  await checkpoint();await cfg();
  assert.equal((await policy('2026-10-09T00:00:00Z')).dispatch,true); // missing prior publication, still in window
  assert.equal((await policy('2026-10-09T11:00:00Z')).reason,'primary_grace');
  assert.deepEqual(await policy('2026-10-09T11:40:00Z'),{dispatch:true,reason:'unresolved_closed_session',session:'2026-10-09',paper_only:false,attempt:1});
  assert.equal((await policy('2026-10-10T11:00:00Z')).paper_only,false); // Friday publication window lasts to Monday open
  assert.equal((await policy('2026-10-12T02:00:00Z')).paper_only,true);
  assert.equal((await policy('2027-01-01T12:00:00Z')).reason,'calendar_unknown');
  assert.equal((await policy('2026-10-01T12:00:00Z')).reason,'calendar_unknown');
});

test('resolved book + committed complete/partial scanner does not create recovery storms',async()=>{
  await checkpoint('2026-10-09');await cfg();
  await db.query("insert into public.scan_runs(namespace,run_digest,data_mode,session_date,status,coverage_valid,coverage_total,snapshot) values('test',$1,'live','2026-10-09','partial',95,100,'{}')",['f'.repeat(64)]);
  assert.equal((await policy('2026-10-09T11:40:00Z')).reason,'resolved');
  assert.equal((await policy('2026-10-12T02:00:00Z')).reason,'resolved');
});

test('pending async dispatch, cooldown, cap, backoff and permanent failures bound independent ticks',async()=>{
  await checkpoint();await cfg();
  await receipt('2026-10-10T10:00:00Z',1,'accepted','2026-10-09','2026-10-10T11:30:00Z');
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'dispatch_pending');
  await db.query("update public.paper_watchdog_receipts_v1 set status='completed'");
  await db.exec("update paper_ops_private.watchdog_config set last_dispatch_at='2026-10-10T10:40:00Z'");
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'cooldown');
  await db.exec("update paper_ops_private.watchdog_config set last_dispatch_at=null,backoff_until='2026-10-10T12:00:00Z'");
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'backoff');
  await db.exec('update paper_ops_private.watchdog_config set backoff_until=null');
  await role(db,'service_role');await db.query("select public.record_paper_job_v1($1,'live','bad-config','job','failed','2026-10-09','blocked_configuration')",[owner]);await role(db,'postgres');
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'permanent_configuration');
  for(let n=2;n<=4;n++)await receipt('2026-10-10T10:00:00Z',n);
  assert.equal((await policy('2026-10-10T11:00:00Z')).reason,'session_cap');
});

async function mockExtensions(){
  await db.exec(`create schema net;
    create table net.http_request_queue(id bigint generated always as identity,url text,body jsonb,headers jsonb);
    create table net._http_response(id bigint,status_code integer,timed_out boolean,error_msg text);
    create function net.http_post(url text,body jsonb default '{}',params jsonb default '{}',headers jsonb default '{}',timeout_milliseconds integer default 2000)
      returns bigint language plpgsql as $$ declare request bigint;begin
        insert into net.http_request_queue(url,body,headers) values($1,$2,$4) returning id into request;return request;end $$;
    -- Emulate hosted queue visibility instead of assuming unsupported ACL repair.
    grant usage on schema net to anon,authenticated,service_role;
    grant select on all tables in schema net to anon,authenticated,service_role;`);
}

test('operator enable requires extension and explicitly verified Edge; SQL never decrypts or queues long-lived credentials',async()=>{
  await checkpoint();
  const enable=()=>db.query("select public.configure_paper_watchdog_v1($1,'live',true,true)",[owner]);
  await denied(enable,'22023');await mockExtensions();
  await denied(()=>db.query("select public.configure_paper_watchdog_v1($1,'live',true,false)",[owner]),'22023');
  await enable();
  const fn=(await db.query("select pg_get_functiondef('public.run_paper_watchdog_v1()'::regprocedure) body")).rows[0].body;
  assert.doesNotMatch(fn,/decrypted_secret|Authorization|Bearer|api\.github\.com/i);
  assert.match(fn,/jsonb_build_object\('ticket',ticket_value\)/);
  assert.match(fn,/functions\/v1\/idx-paper-watchdog/);
});

test('gateway response alone cannot claim GitHub success or deactivate its credential',async()=>{
  await checkpoint();await cfg();await mockExtensions();
  await receipt('2026-10-10T10:00:00Z',1,'dispatching','2026-10-09','2026-10-10T11:30:00Z');
  await db.exec('update public.paper_watchdog_receipts_v1 set request_id=1;insert into net._http_response values(1,204,false,null)');
  await db.query("select paper_ops_private.collect_watchdog_responses_v1('2026-10-10T11:00:00Z')");
  assert.equal((await db.query('select status from public.paper_watchdog_receipts_v1')).rows[0].status,'http_failed');
  await db.exec("update public.paper_watchdog_receipts_v1 set status='dispatching';update net._http_response set status_code=401");
  await db.query("select paper_ops_private.collect_watchdog_responses_v1('2026-10-10T11:00:00Z')");
  assert.equal((await db.query('select enabled from paper_ops_private.watchdog_config')).rows[0].enabled,true);
  assert.equal((await db.query('select status from public.paper_watchdog_receipts_v1')).rows[0].status,'http_failed');
});

async function ticket(number=1,expiry='10 minutes'){
  const r=(await db.query(`insert into public.paper_watchdog_receipts_v1(owner_id,data_mode,session_date,attempt,paper_only,requested_at,lease_until,status)
    values($1,'live','2026-10-09',$2,true,clock_timestamp(),clock_timestamp()+interval '90 minutes','dispatching') returning id`,[owner,number])).rows[0];
  return (await db.query("insert into paper_ops_private.dispatch_ticket(receipt_id,expires_at) values($1,clock_timestamp()+$2::interval) returning ticket",[r.id,expiry])).rows[0].ticket;
}

test('known queue ticket cannot be consumed by owner/anon; service consumption is single-use with fixed scope and expiry',async()=>{
  await checkpoint();await cfg();const nonce=await ticket();
  for(const [name,id] of [['anon',''],['authenticated',owner],['authenticated',outsider]]){
    await role(db,name,id);
    await denied(()=>db.query('select public.consume_paper_watchdog_ticket_v1($1)',[nonce]),'42501');
    await denied(()=>db.query('select public.complete_paper_watchdog_dispatch_v1(1,204,false)'),'42501');
  }
  await role(db,'service_role');
  const r=(await db.query('select public.consume_paper_watchdog_ticket_v1($1) r',[nonce])).rows[0].r;
  assert.equal(r.target_date,'2026-10-09');assert.equal(r.paper_only,true);assert.equal(r.owner_id,owner);assert.equal(r.data_mode,'live');
  assert.equal(Object.hasOwn(r,'github_token'),false);assert.equal(Object.hasOwn(r,'endpoint'),false);
  await denied(()=>db.query('select public.consume_paper_watchdog_ticket_v1($1)',[nonce]),'42501');
  await denied(()=>db.query("select public.consume_paper_watchdog_ticket_v1('44444444-4444-4444-8444-444444444444')"),'42501');
  await role(db,'postgres');const expired=await ticket(2,'-1 second');await role(db,'service_role');
  await denied(()=>db.query('select public.consume_paper_watchdog_ticket_v1($1)',[expired]),'42501');
});

test('only claimed Edge completion decides GitHub204, authentication stop and rate-limit backoff',async()=>{
  await checkpoint();await cfg();
  for(const [attempt,http,expected] of [[1,204,'accepted'],[2,429,'rate_limited'],[3,401,'auth_failed']]){
    await role(db,'postgres');const nonce=await ticket(attempt);await role(db,'service_role');
    const r=(await db.query('select public.consume_paper_watchdog_ticket_v1($1) r',[nonce])).rows[0].r;
    const result=(await db.query('select public.complete_paper_watchdog_dispatch_v1($1,$2,false) r',[r.receipt_id,http])).rows[0].r;
    assert.equal(result.status,expected);
    assert.deepEqual((await db.query('select public.complete_paper_watchdog_dispatch_v1($1,$2,false) r',[r.receipt_id,http])).rows[0].r,result);
    await denied(()=>db.query('select public.complete_paper_watchdog_dispatch_v1($1,$2,false)',[r.receipt_id,http===204?500:204]),'PT409');
    await role(db,'postgres');const config=(await db.query('select enabled,backoff_until from paper_ops_private.watchdog_config')).rows[0];
    if(http===429)assert.ok(config.backoff_until);if(http===401)assert.equal(config.enabled,false);
  }
});

test('accepted runner claiming before Edge completion does not lose receipt/lease or fabricate a failure',async()=>{
  await checkpoint();await cfg();const nonce=await ticket();await role(db,'service_role');
  const r=(await db.query('select public.consume_paper_watchdog_ticket_v1($1) r',[nonce])).rows[0].r;
  await db.query("select public.claim_paper_runtime_lease_v1($1,'live','fast-runner','2026-10-09')",[owner]);
  assert.equal((await db.query('select public.complete_paper_watchdog_dispatch_v1($1,204,false) r',[r.receipt_id])).rows[0].r.status,'started');
  await db.query("select public.release_paper_runtime_lease_v1($1,'live','fast-runner')",[owner]);
  assert.equal((await db.query('select public.complete_paper_watchdog_dispatch_v1($1,204,false) r',[r.receipt_id])).rows[0].r.status,'completed');
  await role(db,'postgres');assert.equal((await db.query('select last_dispatch_status from paper_ops_private.watchdog_config')).rows[0].last_dispatch_status,'completed');
});

test('populated 001-011 to012 upgrade preserves every economic/configuration/event row',async()=>{
  const old=await database({through:'202610100011'});
  try{
    await old.exec('begin');const m=await init(old),t=await trade(old,m,{state:'open'}),e=evaluation(t);
    e.last_session='2026-10-09';e.observed_sessions=1;e.input_digests=observations('2026-10-09');
    await commit(old,bookOf(t),{[e.signal_id]:e});await role(old,'postgres');
    const state=async()=>{const r={};for(const table of ['paper_models','paper_trades','paper_events','signal_evaluations','paper_runtime_requests','actual_trades','actual_fills','signals','scan_runs','paper_job_events_v1'])
      r[table]=(await old.query('select to_jsonb(x) r from public.'+table+' x order by to_jsonb(x)::text')).rows;return r;};
    const before=await state();await old.exec(readFileSync(new URL('../migrations/202610130012_processing_recovery_watchdog.sql',import.meta.url),'utf8'));assert.deepEqual(await state(),before);await old.exec('begin');
    await role(old,'service_role');assert.equal((await commit(old,bookOf(t),{[e.signal_id]:e},1)).replayed,true);
    await role(old,'authenticated',owner);assert.ok((await old.query('select public.read_paper_trade_v1($1) r',[t.id])).rows[0].r.trade.processing.entry_processed_at);
  }finally{await old.close();}
});
