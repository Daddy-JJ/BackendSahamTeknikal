// Offline SQL oracle exporter; no credentials, network, production writes, or fallback.
import {mkdirSync,writeFileSync} from 'node:fs';
import {loadRelease} from '../../scripts/plan_production_release.mjs';
import {database,owner,role,init,trade,bookOf,commit,evaluation,observations,report} from './paper-reporting-fixture.mjs';
const db=await database();
try {
  await db.exec('begin');const m=await init(db);
  const fixed=await trade(db,m,{state:'closed'}),ma=await trade(db,m,{mode:'ma_close',state:'open'});
  const loss=await trade(db,m,{key:'b',state:'closed',exitPrice:925,exitDay:'2026-10-12'});
  const ambiguous=await trade(db,m,{key:'c',state:'ambiguous_review',exitPrice:925,alternate:1150});
  const late=await trade(db,m,{key:'d',state:'closed',mode:'ma_close',exitDay:'2026-10-12'});late.actionable=false;
  late.events.at(-1).reason='ma_breakdown';
  late.events.splice(1,0,{session:'2026-10-09',kind:'pending_exit',price:null,reason:'late_model_only',observed_at:'2026-10-12T03:00:00Z',input_digest:'c'.repeat(64),ma_value:'1005',ma_type:'SMA',ma_period:10});
  const pending=await trade(db,m,{key:'e'});
  const e=evaluation(fixed);e.observed_sessions=5;e.last_session='2026-10-15';e.input_digests=observations('2026-10-09','2026-10-12','2026-10-13','2026-10-14','2026-10-15');
  e.results={target_1r:'won',target_2r:'ambiguous',net_5:'won',net_10:'pending'};
  const hold=evaluation(pending);hold.results={target_1r:'data_hold',target_2r:'data_hold',net_5:'data_hold',net_10:'data_hold'};
  await commit(db,bookOf(fixed,ma,loss,ambiguous,late,pending),{[fixed.signal.id]:e,[pending.signal.id]:hold},0,'fixture','2026-10-15');
  const reporting_fixed2r=await report(db),reporting_ma10=await report(db,'ma10');
  const detail_fixed2r=(await db.query('select public.read_paper_trade_v1($1) r',[fixed.id])).rows[0].r;
  const detail_ma10=(await db.query('select public.read_paper_trade_v1($1) r',[ma.id])).rows[0].r;
  const detail_ma10_closed=(await db.query('select public.read_paper_trade_v1($1) r',[late.id])).rows[0].r;
  const evalReport=(await db.query('select public.read_signal_evaluation_v1() r')).rows[0].r;
  const apply=async(action,id,payload)=>(await db.query('select public.apply_actual_journal($1,$2,$3::jsonb,$4) r',[action,id,JSON.stringify(payload),crypto.randomUUID()])).rows[0].r;
  const actualId=(await apply('create',null,{ticker:'TEST',primary_strategy:'MACD_EMA200_V1',initial_stop:925,exit_policy_snapshot:{version:'fixed2r-v1',mode:'fixed_rr',target_r:2}})).trade_id;
  await apply('fill',actualId,{side:'buy',quantity:12600,price_idr:1000,fee_idr:18900,fee_status:'actual',filled_at:'2026-10-09T03:00:00Z',expected_revision:1});
  await apply('finalize',actualId,{expected_revision:2});await apply('fill',actualId,{side:'sell',quantity:12600,price_idr:1150,fee_idr:36225,fee_status:'actual',filled_at:'2026-10-12T03:00:00Z',expected_revision:3});
  await apply('create',null,{ticker:'DRAFT',primary_strategy:'MACD_EMA200_V1',initial_stop:90,exit_policy_snapshot:{version:'fixed2r-v1',mode:'fixed_rr',target_r:2}});
  const actual_reporting=(await db.query("select public.read_trade_reporting_v1('actual',null,null,null,null) r")).rows[0].r;
  const health=(await db.query('select public.read_paper_processing_health_v1() r')).rows[0].r;
  await role(db,'postgres');const ratio_cases={};for(const [key,pnls] of Object.entries({empty:[],no_loss:[100],no_win:[-100],breakeven:[0],mixed:[200,-100,0,100]})) {
    ratio_cases[key]=(await db.query('select public.trade_reporting_summary_v1($1::jsonb) r',[JSON.stringify(pnls.map(p=>({realized_pnl_idr:p,realized_r:p/100})))])).rows[0].r;
  }
  const release=loadRelease();const output={provenance:{fixture:true,source:'PGlite synthetic ledger with applied canonical SQL',migration_versions:release.migrations.map(x=>x.version),sql011_sha256_lf:release.migrations.at(-1).sha256_lf,generated_at:new Date().toISOString(),not_live_market_evidence:true},reporting_fixed2r,reporting_ma10,detail_fixed2r,detail_ma10,detail_ma10_closed,evaluation:evalReport,actual_reporting,health,ratio_cases};
  mkdirSync(new URL('../fixtures/',import.meta.url),{recursive:true});writeFileSync(new URL('../fixtures/paper-reporting-v1.json',import.meta.url),JSON.stringify(output,null,2)+'\n');
  console.log('Exported synthetic SQL oracle: supabase/tests/fixtures/paper-reporting-v1.json');
}finally{await db.close();}
