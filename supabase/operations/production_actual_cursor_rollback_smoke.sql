-- AUTHORIZED PRODUCTION ROLLBACK-ONLY SQL SMOKE for hcjfxbynqzsaidlwvdfx.
-- Synthetic values are uncommitted, visible only inside this transaction.
-- No JWT/HTTP/concurrency claim. Do not replace final ROLLBACK with COMMIT.
-- Requires empty journal, one owner, LIVE mode and release007 history.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';
do $production_guard$ begin
  if current_user <> 'postgres' then raise exception 'postgres_operator_required'; end if;
  if (select count(*) from public.actual_trades) <> 0 then
    raise exception 'empty_production_journal_required'; end if;
  if not exists(select 1 from supabase_migrations.schema_migrations
    where version='202610010007') then raise exception 'production_release007_required'; end if;
end $production_guard$;

lock table public.deployment_settings in share mode;
do $$ begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'live' then raise exception 'production_live_required'; end if;
  if (select count(*) from public.app_members where role='owner' and enabled) <> 1
    then raise exception 'single_production_owner_required'; end if;
end $$;
select set_config('request.jwt.claim.sub',
  (select user_id::text from public.app_members where role='owner' and enabled),true);
set local role authenticated;
do $cursor_smoke$
declare
  i integer; t uuid; r jsonb; page1 jsonb; page2 jsonb; metrics jsonb;
  snapshot jsonb := '{"version":"prod-rollback-m4-cursor-smoke-v1","mode":"fixed_rr","target_r":2}';
begin
  if (public.actual_journal_analytics(p_exit_snapshot=>snapshot)->>'closed')::integer <> 0
    then raise exception 'cursor_fixture_collision'; end if;
  for i in 1..201 loop
    r := public.apply_actual_journal('create',null,jsonb_build_object(
      'ticker','TEST','primary_strategy','MACD_EMA200_V1','initial_stop',95,
      'exit_policy_snapshot',snapshot),gen_random_uuid());
    t := (r->>'trade_id')::uuid;
    perform public.apply_actual_journal('fill',t,
      '{"expected_revision":1,"side":"buy","quantity":1,"price_idr":100,
        "fee_idr":0,"fee_status":"actual","filled_at":"2026-09-01T03:00:00Z"}'::jsonb,
      gen_random_uuid());
    perform public.apply_actual_journal('fill',t,
      '{"expected_revision":2,"side":"sell","quantity":1,"price_idr":110,
        "fee_idr":0,"fee_status":"actual","filled_at":"2026-09-02T03:00:00Z"}'::jsonb,
      gen_random_uuid());
  end loop;
  page1 := public.export_actual_journal(p_exit_snapshot=>snapshot,p_status=>'closed',
    p_limit=>200);
  if jsonb_array_length(page1->'rows')<>200 or page1->>'has_more'<>'true'
     or page1->>'next_after' is null then raise exception 'first_cursor_page_invalid'; end if;
  page2 := public.export_actual_journal(p_exit_snapshot=>snapshot,p_status=>'closed',
    p_limit=>200,p_after=>(page1->>'next_after')::uuid);
  if jsonb_array_length(page2->'rows')<>1 or page2->>'has_more'<>'false'
     or page2->>'next_after' is not null
     or (page2#>>'{rows,0,trade_id}')::uuid <= (page1->>'next_after')::uuid
    then raise exception 'second_cursor_page_invalid'; end if;
  metrics := public.actual_journal_analytics(p_exit_snapshot=>snapshot);
  if (metrics->>'closed')::integer<>201
     or (metrics->>'net_pnl_idr')::numeric<>2010 then
    raise exception 'cursor_analytics_mismatch'; end if;
  perform set_config('idx.m4.cursor_result',jsonb_build_object(
    'closed',201,'page1',200,'page2',1,'has_more_after_page2',false,
    'net_pnl_idr',2010,'rollback_only',true,'real_owner_jwt',false)::text,true);
end $cursor_smoke$;
select current_setting('idx.m4.cursor_result')::jsonb as m4_cursor_smoke;
rollback;
