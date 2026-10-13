-- Optimize trade reporting and trade enrichment RPC execution.
-- Eliminates redundant table scans and calendar unnesting while preserving exact contract semantics.
begin;

create or replace function public.reporting_trade_enrichment_v1(p_row jsonb,p_owner uuid,p_mode text,p_data text,p_as_of date)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare t public.paper_trades; a public.actual_trades; reason text; holding bigint; days integer; end_day date; entered boolean; eligible boolean;
begin
  if p_mode='paper' then
    select * into strict t from public.paper_trades where id=p_row->>'id' and owner_id=p_owner and data_mode=p_data;
    reason:=public.paper_exclusion_reason_v1(t); entered:=t.details->>'entry' is not null;
    eligible:=t.state='closed' and reason is null;
  else
    select * into strict a from public.actual_trades where id=(p_row->>'id')::uuid and owner_id=p_owner and data_mode=p_data;
    entered:=(p_row->>'entry_session') is not null;eligible:=a.status='closed';
    p_row:=p_row||jsonb_build_object('state',a.status,'open_quantity',a.open_quantity,'current_stop',a.current_stop,'revision',a.revision);
  end if;
  end_day:=coalesce((p_row->>'exit_session')::date,p_as_of);
  if entered and (p_row->>'entry_session')::date<=end_day then
    with cal as (
      select day from public.paper_calendar_days_v1()
      where day between (p_row->>'entry_session')::date and end_day
    )
    select case when count(*) filter (where day=(p_row->>'entry_session')::date) > 0
                 and count(*) filter (where day=end_day) > 0
                then count(*) else null end
      into holding
      from cal;
    days:=end_day-(p_row->>'entry_session')::date+1;
  end if;
  return p_row||jsonb_build_object('metric_eligible',eligible,'exclusion_reason',reason,
    'cohort',case when p_mode='paper' then t.cohort else null end,'holding_sessions',holding,'holding_calendar_days',days);
end $$;
revoke all on function public.reporting_trade_enrichment_v1(jsonb,uuid,text,text,date) from public,anon,authenticated,service_role;

create or replace function public.read_trade_reporting_v1(p_mode text default 'paper',p_from date default null,p_to date default null,p_strategy text default null,
  p_exit_key text default 'fixed2r',p_page integer default 1,p_exit_version text default null,p_exit_snapshot jsonb default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare r jsonb; owner uuid:=auth.uid(); dm text; trades jsonb; excluded jsonb; reasons jsonb; sl_rows jsonb; tp_rows jsonb; statuses jsonb;
begin
  r:=public.read_trade_reporting_before011(p_mode,p_from,p_to,p_strategy,p_exit_key,p_page,p_exit_version,p_exit_snapshot);
  dm:=r->>'data_mode';statuses:=r->'statuses';
  select coalesce(jsonb_agg(public.reporting_trade_enrichment_v1(x,owner,p_mode,dm,(r->>'as_of_session')::date)),'[]'::jsonb) into trades from jsonb_array_elements(r->'trades')x;
  if p_mode='paper' then
    with rows as(select t,public.paper_exclusion_reason_v1(t) why from public.paper_trades t where t.owner_id=owner and t.data_mode=dm and t.model_version='close-signal-risk-v1'
      and ((p_exit_key='fixed2r' and t.exit_mode='fixed_rr') or(p_exit_key='ma10' and t.exit_mode='ma_close'))
      and(p_strategy is null or t.strategy=p_strategy) and t.state in ('closed','ambiguous_review')
      and(p_from is null or t.exit_session>=p_from) and(p_to is null or t.exit_session<=p_to))
    select jsonb_build_object('closed_excluded',count(*) filter(where why is not null),'reasons',coalesce((select jsonb_object_agg(why,n) from(select why,count(*) n from rows where why is not null group by why)x),'{}'::jsonb)),
      coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',(t).net_pnl_idr,'realized_r',(t).realized_r) order by (t).exit_session,(t).id) filter(where why is null or why='ambiguous_order'),'[]'::jsonb),
      coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',case when why='ambiguous_order' then ((t).details->>'alternate_net_pnl')::numeric else (t).net_pnl_idr end,
        'realized_r',case when why='ambiguous_order' then (t).alternate_r else (t).realized_r end) order by (t).exit_session,(t).id) filter(where why is null or why='ambiguous_order'),'[]'::jsonb)
      into excluded,sl_rows,tp_rows from rows;
    r:=r||jsonb_build_object('sensitivities',jsonb_build_object('sl_first',public.trade_reporting_summary_v1(sl_rows),'tp_first',public.trade_reporting_summary_v1(tp_rows)),
      'experiment_comparison',public.paper_experiment_comparison_v1(owner,dm,p_from,p_to,p_strategy,(r->>'as_of_session')::date));
  else
    excluded:=jsonb_build_object('closed_excluded',0,'reasons','{}'::jsonb);
    statuses:=statuses||jsonb_build_object('pending_entry',0,'draft',(select count(*) from public.actual_trades where owner_id=owner and data_mode=dm and status='draft'
      and(p_strategy is null or primary_strategy=p_strategy) and(p_exit_version is null or exit_policy_snapshot->>'version'=p_exit_version) and(p_exit_snapshot is null or exit_policy_snapshot=p_exit_snapshot)));
  end if;
  return r||jsonb_build_object('trades',trades,'statuses',statuses,'status_scope','all_history','exclusions',excluded,
    'processing_health',case when p_mode='paper' then public.paper_processing_health_v1(owner,dm,now()) else null end);
end $$;
revoke all on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) to authenticated;

commit;
