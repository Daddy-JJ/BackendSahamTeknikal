// Synthetic financial contract fixture. Never a live market-data fallback.
import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { loadRelease } from '../../scripts/plan_production_release.mjs';

export const owner='11111111-1111-4111-8111-111111111111';
export const outsider='22222222-2222-4222-8222-222222222222';
export async function database({through='999999999999'}={}) {
  const db=new PGlite();
  await db.exec(`create role anon nologin;create role authenticated nologin;create role service_role nologin bypassrls;
    create schema auth;create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema public,auth to anon,authenticated,service_role;grant execute on function auth.uid() to anon,authenticated,service_role;`);
  for(const m of loadRelease().migrations.filter(m=>m.version<=through)) await db.exec(readFileSync(new URL('../../migrations/'+m.file,import.meta.url),'utf8'));
  await db.query('insert into auth.users values($1),($2)',[owner,outsider]);
  await db.query('insert into public.app_members(user_id) values($1)',[owner]);
  return db;
}
export const role=async(db,name,uid='')=>{await db.exec('set local role '+name);await db.query("select set_config('request.jwt.claim.sub',$1,true)",[uid]);};
export const init=async db=>{await role(db,'service_role');return(await db.query("select public.init_paper_model_v1($1,'live') r",[owner])).rows[0].r;};
export const commit=(db,book,evaluations={},revision=0,request='test',day='2026-10-09')=>db.query(
  "select public.commit_paper_session_v1($1,'live',$2,$3,$4,$5::jsonb,$6::jsonb) r",
  [owner,revision,request,day,JSON.stringify(book),JSON.stringify(evaluations)]).then(x=>x.rows[0].r);
export const bookOf=(...trades)=>({experiments:Object.fromEntries(trades.map(t=>[t.experiment.id,'immutable-config-hash'])),trades:Object.fromEntries(trades.map(t=>[t.id,t]))});
export const observations=(...days)=>days.map(day=>({session:day,digest:'c'.repeat(64),observed_at:day+'T10:00:00Z'}));

export async function trade(db,m,{key='a',mode='fixed_rr',state='pending_entry',exitPrice=1150,alternate=null,exitDay='2026-10-09'}={}) {
  const id=key.repeat(64),ticker='TEST'+key.toUpperCase(),strategy='MACD_EMA200_V1';
  const signal={id,ticker,session:'2026-10-08',candidate:{strategy,stop:925,reference_close:1000},planned_entry_session:'2026-10-09',published_at:m.activated_at,cohort:'forward',data_mode:'live',input_digest:'c'.repeat(64)};
  await role(db,'postgres');
  await db.query(`insert into public.signals(id,namespace,data_mode,ticker,strategy,session_date,config_hash,input_digest,universe_version,calendar_version,provider,price_basis,planned_entry_session,cohort,published_at,snapshot)
    values($1,'test','live',$2,$3,'2026-10-08',$4,$4,'synthetic','synthetic','yfinance','raw','2026-10-09','forward',$5,$6::jsonb) on conflict do nothing`,
    [id,ticker,strategy,'c'.repeat(64),m.activated_at,JSON.stringify(signal)]);
  await role(db,'service_role');
  const experiment={id:'close-signal-risk-v1-'+(mode==='fixed_rr'?'fixed2r':'ma10')+'-'+strategy,strategy,
    exit:mode==='fixed_rr'?{mode,target_r:'2',ma_type:null,period:null,version:'fixed2r-v1'}:{mode,target_r:null,ma_type:'SMA',period:10,version:'ma10-v1'},
    costs:{buy_bps:'15',sell_bps:'25',slippage_bps:'0',status:'verified'},activated_at:m.activated_at,entry_model:'signal_close',risk_budget_idr:'1000000',lot_size:100,model_version:'close-signal-risk-v1'};
  const done=['closed','ambiguous_review'].includes(state),entered=done||state==='open';
  const fee=done?Math.round(12600*exitPrice*.0025*100)/100:null,pnl=done?12600*(exitPrice-1000)-18900-fee:null;
  const alt=alternate===null?null:12600*(alternate-1000)-18900-Math.round(12600*alternate*.0025*100)/100;
  const events=entered?[{session:'2026-10-09',kind:'entry',price:'1000',reason:'assumed_signal_close',observed_at:'2026-10-09T10:00:00Z',input_digest:'c'.repeat(64)}]:[];
  if(done) events.push({session:exitDay,kind:'exit',price:String(exitPrice),reason:alternate===null?'take_profit':'ambiguous_sl_first',observed_at:exitDay+'T10:00:00Z',input_digest:'c'.repeat(64),alternate_price:alternate===null?null:String(alternate)});
  return {id:key+'-'+mode,signal,experiment,state,reason:done?'exit':state,entry:entered?'1000':null,stop:'925',target:mode==='fixed_rr'?'1150':null,
    initial_risk:'945000',pending_exit:null,last_session:entered?exitDay:null,events,net_pnl:pnl===null?null:String(pnl),realized_r:pnl===null?null:String(pnl/945000),
    alternate_r:alt===null?null:String(alt/945000),actionable:alternate===null,planned_entry_price:'1000',quantity:12600,lots:126,
    planned_stop_loss_idr:'993037.50',entry_fee_idr:'18900.00',exit_fee_idr:fee===null?null:String(fee),alternate_net_pnl:alt===null?null:String(alt),sizing_policy_version:'exact_risk_fees_v2'};
}
export const evaluation=t=>({signal_id:t.signal.id,ticker:t.signal.ticker,strategy:t.experiment.strategy,
  signal_session:'2026-10-08',entry_session:'2026-10-09',entry_price:'1000',initial_stop:'925',target_1r:'1075',target_2r:'1150',
  observed_sessions:0,last_session:null,results:{target_1r:'pending',target_2r:'pending',net_5:'pending',net_10:'pending'},exclusion_reasons:{},input_digests:[]});
export const report=async(db,exit='fixed2r',from=null,to=null)=>{await role(db,'authenticated',owner);return(await db.query('select public.read_trade_reporting_v1($1,$2,$3,null,$4) r',['paper',from,to,exit])).rows[0].r;};
