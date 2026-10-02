-- DEVELOPMENT fixture only. SQL role/claim simulation, NOT a real Auth JWT test.
-- The entire synthetic ledger and disabled-owner change are rolled back.
begin;
lock table public.deployment_settings in share mode;
do $$ begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'fixture' then raise exception 'fixture_required'; end if;
  if (select count(*) from public.app_members where role='owner' and enabled) <> 1
    then raise exception 'single_dev_owner_required'; end if;
end $$;
select set_config('request.jwt.claim.sub',
  (select user_id::text from public.app_members where role='owner' and enabled),true);
set local role authenticated;
do $smoke$
declare
  t uuid; buy_id uuid; sell_id uuid; rid uuid := gen_random_uuid();
  r jsonb; first_receipt jsonb; p jsonb; a jsonb; e jsonb; n integer;
  snapshot jsonb := '{"version":"dev-m4-sql-smoke-v1","mode":"fixed_rr","target_r":2}';
begin
  r := public.apply_actual_journal('create',null,jsonb_build_object(
    'ticker','TEST','primary_strategy','MACD_EMA200_V1','initial_stop',95,
    'exit_policy_snapshot',snapshot),gen_random_uuid());
  t := (r->>'trade_id')::uuid;
  p := '{"expected_revision":1,"side":"buy","quantity":100,"price_idr":100,
    "fee_idr":25,"fee_status":"estimated","filled_at":"2026-09-01T03:00:00Z"}';
  first_receipt := public.apply_actual_journal('fill',t,p,rid);
  buy_id := (first_receipt#>>'{ledger,fill_id}')::uuid;
  if public.apply_actual_journal('fill',t,p,rid) <> first_receipt then
    raise exception 'replay_mismatch'; end if;
  begin
    perform public.apply_actual_journal('fill',t,p || '{"fee_idr":26}',rid);
    raise exception 'changed_replay_accepted';
  exception when check_violation then null; end;
  begin
    perform public.apply_actual_journal('finalize',t,'{"expected_revision":1}',gen_random_uuid());
    raise exception 'stale_revision_accepted';
  exception when sqlstate 'PT412' then null; end;
  r := public.apply_actual_journal('fill',t,
    '{"expected_revision":2,"side":"buy","quantity":100,"price_idr":102,
    "fee_idr":25,"fee_status":"actual","filled_at":"2026-09-01T04:00:00Z"}',gen_random_uuid());
  r := public.apply_actual_journal('finalize',t,'{"expected_revision":3}',gen_random_uuid());
  r := public.apply_actual_journal('stop',t,
    '{"expected_revision":4,"new_stop":99,"reason":"Synthetic dev stop check"}',gen_random_uuid());
  if (r#>>'{ledger,initial_risk_idr}')::numeric <> 1200 then raise exception 'risk_changed'; end if;
  select count(*) into n from public.actual_journal_requests;
  begin
    perform public.apply_actual_journal('fill',t,
      '{"expected_revision":5,"side":"sell","quantity":201,"price_idr":105,
      "fee_idr":25,"fee_status":"actual","filled_at":"2026-09-03T03:00:00Z"}',gen_random_uuid());
    raise exception 'oversell_accepted';
  exception when check_violation then null; end;
  if (select count(*) from public.actual_journal_requests) <> n then
    raise exception 'failed_request_residue'; end if;
  r := public.apply_actual_journal('fill',t,
    '{"expected_revision":5,"side":"sell","quantity":100,"price_idr":105,
    "fee_idr":25,"fee_status":"actual","filled_at":"2026-09-03T03:00:00Z"}',gen_random_uuid());
  if r#>>'{ledger,status}' <> 'open' or (r#>>'{ledger,realized_pnl_idr}')::numeric <> 350
    or (r#>>'{ledger,remaining_cost_idr}')::numeric <> 10125
    or r#>>'{ledger,realized_r}' is not null then raise exception 'partial_ledger'; end if;
  a := public.actual_journal_analytics(p_exit_snapshot=>snapshot);
  if (a->>'closed')::int <> 0 or (a->>'open')::int <> 1 then raise exception 'partial_cohort'; end if;
  r := public.apply_actual_journal('fill',t,
    '{"expected_revision":6,"side":"sell","quantity":100,"price_idr":108,
    "fee_idr":25,"fee_status":"actual","filled_at":"2026-09-04T03:00:00Z"}',gen_random_uuid());
  sell_id := (r#>>'{ledger,fill_id}')::uuid;
  if (r#>>'{ledger,initial_risk_idr}')::numeric <> 1200
    or (r#>>'{ledger,fee_total_idr}')::numeric <> 100
    or (r#>>'{ledger,realized_pnl_idr}')::numeric <> 1000
    or (r#>>'{ledger,realized_r}')::numeric <> 0.833333333333 then
    raise exception 'canonical_sot_mismatch'; end if;
  a := public.actual_journal_analytics(p_exit_snapshot=>snapshot);
  if (a->>'estimated_fee_trades')::int <> 1 then raise exception 'estimated_fee_hidden'; end if;
  p := jsonb_build_object('expected_revision',7,'fill_id',buy_id,'quantity',100,
    'price_idr',100,'fee_idr',25,'fee_status','actual','reason','Synthetic broker confirmation');
  r := public.apply_actual_journal('correct_fill',t,p,gen_random_uuid());
  p := jsonb_build_object('expected_revision',8,'fill_id',sell_id,'quantity',100,
    'price_idr',108,'fee_idr',30,'fee_status','actual','reason','Synthetic fee correction');
  r := public.apply_actual_journal('correct_fill',t,p,gen_random_uuid());
  if (r#>>'{ledger,realized_pnl_idr}')::numeric <> 995 then raise exception 'correction_math'; end if;
  r := public.apply_actual_journal('correct_fill',t,
    p || '{"expected_revision":9,"fee_idr":25}',gen_random_uuid());
  r := public.apply_actual_journal('note',t,
    '{"expected_revision":10,"body":"Synthetic rollback-only M4 verification"}',gen_random_uuid());
  r := public.apply_actual_journal('tag',t,
    '{"expected_revision":11,"tag":"synthetic_m4"}',gen_random_uuid());
  a := public.actual_journal_analytics(p_from=>'2026-09-04',p_to=>'2026-09-04',
    p_strategy=>'MACD_EMA200_V1',p_exit_version=>'dev-m4-sql-smoke-v1',p_exit_snapshot=>snapshot);
  e := public.export_actual_journal(p_from=>'2026-09-04',p_to=>'2026-09-04',
    p_strategy=>'MACD_EMA200_V1',p_exit_version=>'dev-m4-sql-smoke-v1',p_exit_snapshot=>snapshot,
    p_status=>'closed',p_after=>null,p_limit=>200);
  if (a->>'closed')::int <> 1 or (a->>'estimated_fee_trades')::int <> 0
    or (a->>'net_pnl_idr')::numeric <> 1000 or jsonb_array_length(e->'rows') <> 1
    or (e#>>'{rows,0,realized_pnl_idr}')::numeric <> 1000
    or e#>>'{rows,0,fee_quality}' <> 'actual' then raise exception 'export_analytics_mismatch'; end if;
  begin
    perform public.export_actual_journal(p_limit=>201);
    raise exception 'oversized_export_accepted';
  exception when invalid_parameter_value then null; end;
  if public.apply_actual_journal('fill',t,
    '{"expected_revision":1,"side":"buy","quantity":100,"price_idr":100,
    "fee_idr":25,"fee_status":"estimated","filled_at":"2026-09-01T03:00:00Z"}',rid)
    <> first_receipt then raise exception 'historical_replay_changed'; end if;
  perform set_config('idx.m4.result',jsonb_build_object('sql_ledger_passed',true,
    'risk',1200,'fee',100,'net',1000,'r',0.833333333333,'partial_passed',true,
    'correction_passed',true,'estimated_fee_passed',true,'export_analytics_passed',true)::text,true);
end $smoke$;
reset role;
-- Disable only within this uncommitted transaction; no other session sees it.
update public.app_members set enabled=false where user_id=auth.uid();
set local role authenticated;
do $$ declare t text; n integer; begin
  foreach t in array array['actual_trades','actual_fills','actual_fill_corrections',
    'actual_stop_events','actual_notes','actual_trade_tags','actual_journal_requests'] loop
    execute format('select count(*) from public.%I',t) into n;
    if n<>0 then raise exception 'disabled_owner_read_leak'; end if;
  end loop;
  begin
    perform public.actual_journal_analytics(); raise exception 'disabled_owner_rpc_leak';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
set local role authenticated;
do $$ begin
  if (select count(*) from public.actual_fills)<>0 then raise exception 'outsider_read_leak'; end if;
  begin
    perform public.export_actual_journal(); raise exception 'outsider_export_leak';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
select current_setting('idx.m4.result')::jsonb ||
  '{"disabled_owner_sql_passed":true,"outsider_sql_passed":true,"real_owner_jwt":false,
    "concurrency_tested":false,"rollback_only":true}' as m4_sql_smoke;
rollback;
