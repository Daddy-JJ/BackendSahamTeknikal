-- Separate scanner cross-section coverage from journal/observation completeness.
-- Additive metadata only: retain the existing reader signatures, math and grants.
begin;

create function public.paper_scan_coverage_v1(p_data_mode text) returns jsonb
language sql stable security definer set search_path='' as $$
  select coalesce((
    select jsonb_build_object('status',r.status,'session_date',r.session_date,
      'coverage_valid',r.coverage_valid,'coverage_total',r.coverage_total)
    from public.scan_runs r
    where r.data_mode=p_data_mode and r.namespace='forward'
    order by r.session_date desc,r.stored_at desc,r.id desc limit 1
  ),jsonb_build_object('status','missing','session_date',null,
    'coverage_valid',null,'coverage_total',null));
$$;
revoke all on function public.paper_scan_coverage_v1(text) from public,anon,authenticated,service_role;

create or replace function public.read_trade_reporting_v1(
  p_mode text default 'paper',p_from date default null,p_to date default null,p_strategy text default null,
  p_exit_key text default 'fixed2r',p_page integer default 1,p_exit_version text default null,p_exit_snapshot jsonb default null
) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare
  owner uuid:=auth.uid(); dm text; scoped jsonb; closed_rows jsonb; summary jsonb; statuses jsonb;
  curve jsonb; attribution jsonb; trades jsonb; sl_rows jsonb; tp_rows jsonb; model public.paper_models;
  as_of date; updated timestamptz; coverage text; has_more boolean; max_dd numeric; latest_scan date;
begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  if p_mode not in ('paper','actual') or p_mode is null or (p_mode='paper' and (p_exit_key not in ('fixed2r','ma10') or p_exit_key is null))
    or p_page is null or p_page<1 or p_page>1000000 or p_from>p_to then
    raise exception 'invalid_reporting_filter' using errcode='22023';
  end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  select * into model from public.paper_models where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1';
  select coalesce(jsonb_agg(to_jsonb(r)),'[]') into scoped from public.trade_reporting_rows_v1(owner,dm,p_mode,p_exit_key,p_strategy,p_exit_version,p_exit_snapshot)r;
  with r as(select * from jsonb_to_recordset(scoped) x(state text,ambiguous boolean,actionable boolean,exit_session date,realized_pnl_idr numeric,realized_r numeric,id text,ticker text,strategy text,updated_at timestamptz))
  select coalesce(jsonb_agg(to_jsonb(r) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]') into closed_rows from r
    where state='closed' and not ambiguous and actionable and (p_from is null or exit_session>=p_from) and (p_to is null or exit_session<=p_to);
  summary:=public.trade_reporting_summary_v1(closed_rows);
  with r as(select * from jsonb_to_recordset(scoped) x(state text,ambiguous boolean))
  select jsonb_build_object('pending_entry',count(*) filter(where state='pending_entry'),'open',count(*) filter(where state='open'),
    'closed',count(*) filter(where state='closed' and not ambiguous),'skipped',count(*) filter(where state='skipped'),
    'expired',count(*) filter(where state='expired'),'data_hold',count(*) filter(where state='data_hold'),
    'ambiguous',count(*) filter(where ambiguous)) into statuses from r;
  with r as(select * from jsonb_to_recordset(closed_rows) x(id text,ticker text,strategy text,exit_session date,realized_pnl_idr numeric,updated_at timestamptz)),
  ordered as(select *,row_number() over(order by exit_session,case when p_mode='actual' then updated_at else null end,id) seq,sum(realized_pnl_idr) over(order by exit_session,case when p_mode='actual' then updated_at else null end,id) cum from r),
  dd as(select *,greatest(0,max(cum) over(order by seq))-cum drawdown from ordered)
  select coalesce(jsonb_agg(jsonb_build_object('sequence',seq,'trade_id',id,'ticker',ticker,'strategy',strategy,'exit_session',exit_session,
    'realized_pnl_idr',realized_pnl_idr,'cumulative_pnl_idr',cum) order by seq),'[]'),coalesce(max(drawdown),0) into curve,max_dd from dd;
  summary:=summary||jsonb_build_object('max_drawdown_idr',max_dd);
  with r as(select * from jsonb_to_recordset(closed_rows) x(strategy text,realized_pnl_idr numeric,realized_r numeric)),
  groups as(select strategy,public.trade_reporting_summary_v1(jsonb_agg(to_jsonb(r))) s from r group by strategy)
  select coalesce(jsonb_agg((s-'max_drawdown_idr')||jsonb_build_object('strategy',strategy) order by (s->>'net_pnl_idr')::numeric desc,strategy),'[]') into attribution from groups;
  with r as(select value from jsonb_array_elements(scoped)), eligible as(
    select value from r where value->>'state' not in ('closed','ambiguous_review')
      or ((p_from is null or (value->>'exit_session')::date>=p_from) and (p_to is null or (value->>'exit_session')::date<=p_to))
  ), page as(select value from eligible order by coalesce((value->>'exit_session')::date,(value->>'entry_session')::date) desc nulls last,value->>'id' limit 25 offset (p_page-1)*25)
  select coalesce(jsonb_agg(value-'actionable'-'alternate_pnl'-'alternate_r'-'updated_at'),'[]'),
    (select count(*)>(p_page::bigint*25) from eligible) into trades,has_more from page;
  with r as(select * from jsonb_to_recordset(scoped)x(state text,ambiguous boolean,actionable boolean,id text,exit_session date,realized_pnl_idr numeric,realized_r numeric,alternate_pnl numeric,alternate_r numeric,updated_at timestamptz))
  select coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',realized_pnl_idr,'realized_r',realized_r) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]'),
    coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',case when ambiguous then alternate_pnl else realized_pnl_idr end,'realized_r',case when ambiguous then alternate_r else realized_r end) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]')
    into sl_rows,tp_rows from r where (state='closed' and actionable or ambiguous) and (p_from is null or exit_session>=p_from) and (p_to is null or exit_session<=p_to);
  if p_mode='paper' then
    as_of:=model.last_session; updated:=model.updated_at;
    select max(session_date) into latest_scan from public.scan_runs where data_mode=dm and status<>'failed';
    coverage:=case when model.owner_id is null or model.last_session is null then 'missing'
      when (statuses->>'data_hold')::integer>0 then 'partial'
      when as_of<latest_scan then 'stale' else 'complete' end;
  else
    select max((x->>'exit_session')::date),max((x->>'updated_at')::timestamptz) into as_of,updated from jsonb_array_elements(scoped)x;
    coverage:='complete';
  end if;
  return jsonb_build_object('contract_version',1,'mode',p_mode,'data_mode',dm,'basis','IDR','cohort_date','exit_session_Asia_Jakarta',
    'model_version',case when p_mode='paper' then 'close-signal-risk-v1' else null end,'from',p_from,'to',p_to,'primary_strategy',p_strategy,
    'exit_key',case when p_mode='paper' then p_exit_key else null end,'exit_version',p_exit_version,'exit_snapshot',p_exit_snapshot,
    'as_of_session',as_of,'updated_at',updated,'coverage_status',coverage,
    'scanner_coverage',case when p_mode='paper' then public.paper_scan_coverage_v1(dm) else null end,
    'summary',summary,'statuses',statuses,'curve',curve,
    'strategies',attribution,'trades',trades,'paging',jsonb_build_object('page',p_page,'page_size',25,'has_more',has_more),
    'sensitivities',jsonb_build_object('sl_first',public.trade_reporting_summary_v1(sl_rows),'tp_first',public.trade_reporting_summary_v1(tp_rows)));
end $$;
revoke all on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) to authenticated;

create or replace function public.read_signal_evaluation_v1(p_from date default null,p_to date default null,p_strategy text default null,p_page integer default 1)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare owner uuid:=auth.uid(); dm text; rows_json jsonb; strategies jsonb; evaluations jsonb; model public.paper_models; coverage text; latest_scan date; more boolean;
begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  if p_page is null or p_page<1 or p_page>1000000 or p_from>p_to then raise exception 'invalid_reporting_filter' using errcode='22023'; end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  select * into model from public.paper_models where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1';
  select coalesce(jsonb_agg(payload),'[]') into rows_json from public.signal_evaluations
    where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1'
      and(p_from is null or signal_session>=p_from) and(p_to is null or signal_session<=p_to) and(p_strategy is null or strategy=p_strategy);
  with rows as(select value from jsonb_array_elements(rows_json)), cells as(
    select r.value->>'strategy' strategy,k.key metric,k.value#>>'{}' state,coalesce(r.value->'exclusion_reasons'->>k.key,'unspecified') exclusion
    from rows r cross join lateral jsonb_each(r.value->'results')k
  ), grouped as(select strategy,metric,count(*) filter(where state='won') wins,count(*) filter(where state in('won','lost')) assessed,
    count(*) filter(where state='pending') pending,count(*) filter(where state='ambiguous') ambiguous,count(*) filter(where state='data_hold') data_hold,
    count(*) filter(where state='excluded') excluded from cells group by strategy,metric), cell_json as(
    select g.strategy,g.metric,jsonb_build_object('wins',g.wins,'assessed',g.assessed,'pending',g.pending,'ambiguous',g.ambiguous,'data_hold',g.data_hold,'excluded',g.excluded,
      'win_rate',case when g.assessed>0 then g.wins::numeric/g.assessed else null end,'excluded_reasons',coalesce((select jsonb_object_agg(exclusion,n) from(
        select exclusion,count(*) n from cells c where c.strategy=g.strategy and c.metric=g.metric and c.state='excluded' group by exclusion)x),'{}')) val from grouped g
  ), strat as(select strategy,jsonb_object_agg(metric,val) cells from cell_json group by strategy)
  select coalesce(jsonb_agg(jsonb_build_object('strategy',s.strategy,'signals',(select count(*) from rows where value->>'strategy'=s.strategy),'cells',s.cells) order by s.strategy),'[]') into strategies from strat s;
  with rows as(select value from jsonb_array_elements(rows_json)), page as(select value from rows order by value->>'signal_session' desc,value->>'signal_id' limit 25 offset(p_page-1)*25)
  select coalesce(jsonb_agg((value-'signal'-'input_digests'-'provider_symbol'-'data_mode'-'model_version')||jsonb_build_object('entry_price',(value->>'entry_price')::numeric,'initial_stop',(value->>'initial_stop')::numeric,'target_1r',(value->>'target_1r')::numeric,'target_2r',(value->>'target_2r')::numeric)),'[]'),(select count(*)>p_page::bigint*25 from rows) into evaluations,more from page;
  select max(session_date) into latest_scan from public.scan_runs where data_mode=dm and status<>'failed';
  coverage:=case when model.owner_id is null or model.last_session is null then 'missing'
    when exists(select 1 from jsonb_array_elements(rows_json)r cross join lateral jsonb_each_text(r->'results')v where v.value='data_hold') then 'partial'
    when model.last_session<latest_scan then 'stale' else 'complete' end;
  return jsonb_build_object('contract_version',1,'mode','signal_evaluation','data_mode',dm,'basis','IDR','cohort_date','signal_session',
    'model_version','close-signal-risk-v1','from',p_from,'to',p_to,'primary_strategy',p_strategy,'exit_key',null,'exit_version',null,'exit_snapshot',null,
    'as_of_session',model.last_session,'updated_at',model.updated_at,'coverage_status',coverage,
    'scanner_coverage',public.paper_scan_coverage_v1(dm),'strategies',strategies,'evaluations',evaluations,
    'paging',jsonb_build_object('page',p_page,'page_size',25,'has_more',more));
end $$;
revoke all on function public.read_signal_evaluation_v1(date,date,text,integer) from public,anon,authenticated,service_role;
grant execute on function public.read_signal_evaluation_v1(date,date,text,integer) to authenticated;

commit;
