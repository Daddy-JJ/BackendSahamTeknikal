// Synthetic bounded chart payload and lookup-plan proofs; no hosted connection.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {database, owner, role} from './helpers/paper-reporting-fixture.mjs';

const python=process.env.SCANNER_TEST_PYTHON||fileURLToPath(new URL(process.platform==='win32'?'../../scanner/.venv/Scripts/python.exe':'../../scanner/.venv/bin/python',import.meta.url));
const exportChart=(id,count=1200)=>JSON.parse(execFileSync(python,['-c',
  `import json;from idx_scanner.chart_fixture import synthetic_chart_export;print(json.dumps(synthetic_chart_export('${owner}','${id}',count=${count})))`],{encoding:'utf8',maxBuffer:10*1024*1024}));

test('500-slot canonical chart with 500 overlays remains below the initial 1 MiB budget',async t=>{
  const db=await database();
  try {
    await db.exec('begin');
    await db.exec("update public.deployment_settings set data_mode='fixture'");
    await role(db,'service_role');
    const raw=exportChart('33333333-3333-4333-8333-333333333333');
    const receipt=(await db.query('select public.ingest_market_series($1::jsonb) r',[JSON.stringify(raw.market_record)])).rows[0].r;
    const canonical=exportChart(receipt.revision_id);
    const cutoff=canonical.p_record.data.sessions.at(-1);
    canonical.p_record.data.overlays.markers=Array.from({length:503},(_,i)=>({
      id:'synthetic-event-'+String(i).padStart(5,'0'),kind:'entry_fill',session:cutoff,
      available_session:cutoff,price:'1234.50',source_id:'synthetic-source-'+String(i).padStart(5,'0'),status:'simulated'}));
    await db.query('select public.persist_ticker_chart_artifact_v1($1::jsonb)',[JSON.stringify(canonical.p_record)]);
    await role(db,'authenticated',owner);
    const results=[];
    for(let i=0;i<5;i++) {
      const start=performance.now();
      const result=(await db.query('select public.read_ticker_chart_v1($1::jsonb) r',[JSON.stringify({ticker:canonical.p_record.ticker,limit:500})])).rows[0].r;
      results.push(performance.now()-start);
      assert.equal(result.success,true);
      assert.equal(result.data.sessions.length,500);
      assert.equal(result.data.overlays.markers.length,500);
      assert.equal(result.data.overlays.has_more,true);
      const bytes=Buffer.byteLength(JSON.stringify(result),'utf8');
      assert.ok(bytes<=1024*1024,`canonical page exceeds 1 MiB: ${bytes}`);
      if(i===0)t.diagnostic(JSON.stringify({scope:'local-PGlite-synthetic',slots:500,markers:500,payload_bytes:bytes}));
    }
    t.diagnostic(JSON.stringify({rpc_ms:results,median_ms:[...results].sort((a,b)=>a-b)[2],scope:'PGlite-not-cloud-latency'}));
    await db.exec('rollback');
  } finally {await db.close();}
});

test('expired cursor maintenance is service-only, bounded and leaves active cursors intact',async()=>{
  const db=await database();
  try {
    await db.exec('begin');await db.exec("update public.deployment_settings set data_mode='fixture'");
    await role(db,'service_role');
    const raw=exportChart('33333333-3333-4333-8333-333333333333',40);
    const receipt=(await db.query('select public.ingest_market_series($1::jsonb) r',[JSON.stringify(raw.market_record)])).rows[0].r;
    const artifact=exportChart(receipt.revision_id,40).p_record;
    await db.query('select public.persist_ticker_chart_artifact_v1($1::jsonb)',[JSON.stringify(artifact)]);
    await role(db,'postgres');
    await db.query(`insert into chart_private.cursors_v1(owner_id,revision,ticker,data_mode,context_kind,view,page_limit,kind,window_from,window_to,lower_bound,expires_at)
      select $1,$2,$3,'fixture','latest','followup',5,'bars','2026-01-01','2026-01-02','2026-01-01',
      case when i<=3 then now()-interval '1 day' else now()+interval '1 day' end from generate_series(1,5) i`,[owner,artifact.revision,artifact.ticker]);
    await role(db,'service_role');
    const cleaned=(await db.query('select public.prune_ticker_chart_cursors_v1(2) r')).rows[0].r;
    assert.equal(cleaned.deleted,2);assert.equal(cleaned.has_more,true);
    await role(db,'postgres');
    assert.equal((await db.query('select count(*)::int n from chart_private.cursors_v1 where expires_at>now()')).rows[0].n,2);
    for(const name of ['anon','authenticated']) {
      await role(db,name,owner);await db.exec('savepoint denied');
      await assert.rejects(()=>db.query('select public.prune_ticker_chart_cursors_v1(2)'),e=>e.code==='42501');
      await db.exec('rollback to savepoint denied');
    }
    await role(db,'service_role');await db.exec('savepoint bounds');
    await assert.rejects(()=>db.query('select public.prune_ticker_chart_cursors_v1(10001)'),e=>e.code==='22023');
    await db.exec('rollback to savepoint bounds');
    const next=(await db.query('select public.prune_ticker_chart_cursors_v1(1000) r')).rows[0].r;
    assert.equal(next.deleted,1);assert.equal(next.has_more,false);
    await role(db,'authenticated',owner);await db.exec('savepoint core');
    await assert.rejects(()=>db.query("select chart_private.read_ticker_chart_core_v1('{\"ticker\":\"TEST\"}')"),e=>e.code==='42501');
    await db.exec('rollback to savepoint core');
    await db.exec('rollback');
  }finally{await db.close();}
});

test('oversized projected page fails honestly without truncation or economic writes',async()=>{
  const db=await database();
  try {
    await db.exec('begin');await db.exec("update public.deployment_settings set data_mode='fixture'");
    await role(db,'service_role');
    const raw=exportChart('33333333-3333-4333-8333-333333333333',660);
    const receipt=(await db.query('select public.ingest_market_series($1::jsonb) r',[JSON.stringify(raw.market_record)])).rows[0].r;
    const artifact=exportChart(receipt.revision_id,660).p_record;
    artifact.data.bars=artifact.data.bars.map(bar=>({...bar,volume:'0'.repeat(3000)+bar.volume}));
    await db.query('select public.persist_ticker_chart_artifact_v1($1::jsonb)',[JSON.stringify(artifact)]);
    await role(db,'authenticated',owner);
    const result=(await db.query('select public.read_ticker_chart_v1($1::jsonb) r',[JSON.stringify({ticker:artifact.ticker,limit:500})])).rows[0].r;
    assert.equal(result.success,false);assert.equal(result.data,null);
    assert.equal(result.error.code,'DATA_UNAVAILABLE');assert.equal(result.error.message,'payload_budget_exceeded');
    await role(db,'postgres');
    assert.equal((await db.query('select count(*)::int n from public.actual_fills')).rows[0].n,0);
    assert.equal((await db.query('select count(*)::int n from public.paper_events')).rows[0].n,0);
    await db.exec('rollback');
  }finally{await db.close();}
});

test('chart artifact primary key and newest-context lookup have usable indexes',async t=>{
  const db=await database();
  try {
    await db.exec('begin');
    await db.query(`insert into public.ticker_chart_artifacts_v1(revision,owner_id,data_mode,ticker,context_kind,context_id,view,data)
      select md5(i::text)||md5(i::text),$1,'live','ADRO','signal',md5((i%100)::text)||md5((i%100)::text),'snapshot','{}'::jsonb
      from generate_series(1,5000) i`,[owner]);
    await db.exec('analyze public.ticker_chart_artifacts_v1');
    // Disable sequential scans only to prove that index access is available.
    // This is not a populated production cost estimate or latency measurement.
    await db.exec('set local enable_seqscan=off');
    const newest=(await db.query(`explain (format json) select * from public.ticker_chart_artifacts_v1
      where owner_id=$1 and data_mode='live' and ticker='ADRO' and context_kind='signal'
      and context_id=$2 and view='snapshot'
      order by stored_at desc,revision desc limit 1`,[owner,'c4ca4238a0b923820dcc509a6f75849b'.repeat(2)])).rows[0]['QUERY PLAN'];
    const primary=(await db.query(`explain (format json) select * from public.ticker_chart_artifacts_v1
      where owner_id=$1 and revision=$2`,[owner,'b'.repeat(64)])).rows[0]['QUERY PLAN'];
    assert.match(JSON.stringify(newest),/ticker_chart_lookup_v1/);
    assert.match(JSON.stringify(primary),/ticker_chart_artifacts_v1_pkey/);
    assert.match(JSON.stringify(newest),/context_id =/);
    t.diagnostic(JSON.stringify({newest,primary}));
    await db.exec('rollback');
  } finally {await db.close();}
});

test('forward core copy preserves all 015 auth, limiter, cutoff and pagination logic',()=>{
  const original=readFileSync(new URL('../migrations/202610140015_ticker_chart_artifacts.sql',import.meta.url),'utf8');
  const current=readFileSync(new URL('../migrations/202610140016_chart_reader_budgets.sql',import.meta.url),'utf8');
  const body=(raw,start)=>{
    const sql=raw.replace(/\r\n/g,'\n');
    return sql.slice(sql.indexOf(start),sql.indexOf('\n$$;',sql.indexOf(start))+4);
  };
  const oldQuery=`    select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
      and context_id is not distinct from cid and view=vw order by stored_at desc,revision desc limit 1;`;
  const newQuery=`    if cid is null then
      select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
        and context_id is null and view=vw order by stored_at desc,revision desc limit 1;
    else
      select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
        and context_id=cid and view=vw order by stored_at desc,revision desc limit 1;
    end if;`;
  const oldBody=body(original,'create function public.read_ticker_chart_v1(');
  const newBody=body(current,'create or replace function chart_private.read_ticker_chart_core_v1(');
  assert.ok(oldBody.includes(oldQuery));assert.ok(newBody.includes(newQuery));
  assert.equal(newBody.replace('create or replace function chart_private.read_ticker_chart_core_v1(',
    'create function public.read_ticker_chart_v1(').replace(newQuery,oldQuery),oldBody);
});
