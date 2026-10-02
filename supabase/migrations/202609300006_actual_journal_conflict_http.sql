-- Map stale expected_revision to a non-retryable HTTP 412. Migration 005 remains immutable.
-- PostgreSQL SQLSTATE 40001 is reserved for transient serialization failures.
begin;
create or replace function public.apply_actual_journal(
  p_action text, p_trade_id uuid, p_payload jsonb, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_request jsonb := jsonb_build_object('action',p_action,'trade_id',p_trade_id,'payload',p_payload);
  v_prior public.actual_journal_requests;
  v_trade public.actual_trades;
  v_fill public.actual_fills;
  v_mode text;
  v_risk numeric;
  v_reason text;
  v_result jsonb;
  v_ledger jsonb;
  v_before jsonb;
  v_allowed text[];
  v_exit jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_request_id is null or jsonb_typeof(p_payload) is distinct from 'object' then
    raise exception 'invalid_journal_request' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('idx:journal:' || v_owner::text, 0));
  select * into v_prior from public.actual_journal_requests
    where owner_id = v_owner and request_id = p_request_id;
  if found then
    if v_prior.request is distinct from v_request then
      raise exception 'idempotency_conflict' using errcode = '23514';
    end if;
    return v_prior.result;
  end if;
  v_allowed := case p_action
    when 'create' then array['ticker','primary_strategy','signal_id','initial_stop','exit_policy_snapshot']
    when 'fill' then array['expected_revision','side','quantity','price_idr','fee_idr','fee_status','filled_at']
    when 'finalize' then array['expected_revision']
    when 'stop' then array['expected_revision','new_stop','reason']
    when 'note' then array['expected_revision','body']
    when 'tag' then array['expected_revision','tag']
    when 'correct_fill' then array['expected_revision','fill_id','quantity','price_idr','fee_idr',
      'fee_status','reason','restate_initial_risk','filled_at'] end;
  if v_allowed is null or (p_payload - v_allowed) <> '{}'::jsonb then
    raise exception 'unsupported_action_or_field' using errcode = '22023';
  end if;
  if p_action in ('fill','correct_fill') then
    if not public.valid_actual_decimal(p_payload->>'price_idr')
       or not public.valid_actual_decimal(p_payload->>'fee_idr',true)
       or coalesce(p_payload->>'quantity','') !~ '^[1-9][0-9]{0,18}$'
       or coalesce(p_payload->>'fee_status','') not in ('actual','estimated') then
      raise exception 'invalid_fill_values' using errcode = '22023';
    end if;
  end if;
  -- Shared lock keeps deployment mode fixed throughout this mutation.
  select data_mode into strict v_mode from public.deployment_settings where singleton for share;
  if p_action = 'create' then
    v_exit := p_payload->'exit_policy_snapshot';
    if p_trade_id is not null
       or coalesce(p_payload->>'ticker','') !~ '^[A-Z0-9]{2,12}$'
       or coalesce(p_payload->>'primary_strategy','') not in
         ('MACD_EMA200_V1','FRACTAL_BREAKOUT_V1','RS_BREAKOUT_V1','PULLBACK_RECLAIM_V1')
       or not public.valid_actual_decimal(p_payload->>'initial_stop')
       or jsonb_typeof(p_payload->'exit_policy_snapshot') is distinct from 'object'
       or jsonb_typeof(v_exit->'version') is distinct from 'string'
       or coalesce(length(trim(v_exit->>'version')),0) not between 1 and 100
       or coalesce(v_exit->>'mode','') not in ('fixed_rr','ma_close','manual')
    then raise exception 'invalid_trade_draft' using errcode = '22023'; end if;
    if (v_exit - array['version','mode','target_r','ma_type','period','config_hash']) <> '{}'::jsonb
       or (v_exit->>'mode'='fixed_rr' and
          (not public.valid_actual_decimal(v_exit->>'target_r')
           or v_exit ?| array['ma_type','period']))
       or (v_exit->>'mode'='ma_close' and
          (coalesce(v_exit->>'ma_type','') not in ('SMA','EMA')
           or coalesce(v_exit->>'period','') not in ('5','10','20')
           or (v_exit->'target_r' is not null and v_exit->'target_r' <> 'null'::jsonb)))
       or (v_exit->>'mode'='manual' and v_exit ?| array['target_r','ma_type','period']) then
      raise exception 'invalid_exit_policy' using errcode = '22023';
    end if;
    if p_payload->>'signal_id' is not null and not exists (
      select 1 from public.signals where id = p_payload->>'signal_id'
        and ticker = p_payload->>'ticker'
        and strategy = p_payload->>'primary_strategy' and data_mode = v_mode
    ) then raise exception 'signal_context_mismatch' using errcode = '22023'; end if;
    insert into public.actual_trades(owner_id,data_mode,ticker,primary_strategy,
      signal_id,exit_policy_snapshot,initial_stop,current_stop)
    values (v_owner,v_mode,p_payload->>'ticker',p_payload->>'primary_strategy',
      p_payload->>'signal_id',p_payload->'exit_policy_snapshot',
      (p_payload->>'initial_stop')::numeric,(p_payload->>'initial_stop')::numeric)
    returning * into v_trade;
    v_ledger := jsonb_build_object('status','draft','open_quantity',0,'provisional_risk_idr',0);
  else
    select * into v_trade from public.actual_trades
      where id = p_trade_id and owner_id = v_owner for update;
    if not found then raise exception 'trade_not_found' using errcode = '22023'; end if;
    v_before := to_jsonb(v_trade);
    if v_trade.data_mode is distinct from v_mode then
      raise exception 'journal_mode_changed' using errcode = '23514';
    end if;
    if coalesce(p_payload->>'expected_revision','') !~ '^[1-9][0-9]{0,9}$' then
      raise exception 'invalid_expected_revision' using errcode = '22023'; end if;
    if (p_payload->>'expected_revision')::integer is distinct from v_trade.revision then
      raise exception 'revision_conflict' using errcode = 'PT412';
    end if;
    if p_action = 'fill' then
      if coalesce(p_payload->>'side','') not in ('buy','sell')
         or (p_payload->>'quantity')::bigint <= 0
         or (p_payload->>'price_idr')::numeric <= 0
         or (p_payload->>'fee_idr')::numeric < 0
         or p_payload->>'fee_status' not in ('actual','estimated')
         or p_payload->>'filled_at' is null
      then raise exception 'invalid_fill' using errcode = '22023'; end if;
      if p_payload->>'side' = 'buy' and
        (v_trade.entry_finalized_at is not null or
          (p_payload->>'price_idr')::numeric <= v_trade.initial_stop)
      then raise exception 'entry_batch_closed_or_stop_invalid' using errcode = '23514'; end if;
      if p_payload->>'side' = 'sell' then
        if v_trade.open_quantity < (p_payload->>'quantity')::bigint then
          raise exception 'oversell' using errcode = '23514';
        end if;
        if v_trade.entry_finalized_at is null then
          select public.actual_entry_risk(p_trade_id,v_trade.initial_stop) into v_risk;
          if v_risk is null or v_risk <= 0 then
            raise exception 'invalid_initial_risk' using errcode = '23514';
          end if;
          update public.actual_trades set entry_finalized_at=now(),
            initial_risk_idr=v_risk where id=p_trade_id;
        end if;
      end if;
      if not isfinite((p_payload->>'filled_at')::timestamptz) then
        raise exception 'invalid_fill_time' using errcode = '22023'; end if;
      insert into public.actual_fills(trade_id,owner_id,side,filled_at,quantity,
        price_idr,fee_idr,fee_status)
      values (p_trade_id,v_owner,p_payload->>'side',
        (p_payload->>'filled_at')::timestamptz,(p_payload->>'quantity')::bigint,
        (p_payload->>'price_idr')::numeric,(p_payload->>'fee_idr')::numeric,
        p_payload->>'fee_status') returning * into v_fill;
      v_ledger := public.recalculate_actual_trade(p_trade_id);
      v_ledger := v_ledger || jsonb_build_object('fill_id',v_fill.id);
    elsif p_action = 'finalize' then
      if v_trade.entry_finalized_at is not null or v_trade.open_quantity = 0 then
        raise exception 'cannot_finalize' using errcode = '23514'; end if;
      select public.actual_entry_risk(p_trade_id,v_trade.initial_stop) into v_risk;
      if v_risk is null or v_risk <= 0 then
        raise exception 'invalid_initial_risk' using errcode = '23514'; end if;
      update public.actual_trades set entry_finalized_at=now(),
        initial_risk_idr=v_risk where id=p_trade_id;
      v_ledger := public.recalculate_actual_trade(p_trade_id);
    elsif p_action = 'stop' then
      v_reason := trim(p_payload->>'reason');
      if v_trade.entry_finalized_at is null or v_trade.status='closed'
        or not public.valid_actual_decimal(p_payload->>'new_stop')
        or coalesce(length(v_reason),0) not between 3 and 500
      then raise exception 'invalid_stop_change' using errcode = '22023'; end if;
      insert into public.actual_stop_events(trade_id,owner_id,old_stop,new_stop,reason)
      values (p_trade_id,v_owner,v_trade.current_stop,(p_payload->>'new_stop')::numeric,v_reason);
      update public.actual_trades set current_stop=(p_payload->>'new_stop')::numeric
        where id=p_trade_id;
      v_ledger := jsonb_build_object('initial_risk_idr',v_trade.initial_risk_idr,
        'current_stop', (p_payload->>'new_stop')::numeric);
    elsif p_action = 'note' then
      if coalesce(length(trim(p_payload->>'body')),0) not between 1 and 4000 then
        raise exception 'invalid_note' using errcode = '22023'; end if;
      insert into public.actual_notes(trade_id,owner_id,body)
        values (p_trade_id,v_owner,trim(p_payload->>'body'));
      v_ledger := jsonb_build_object('note_added',true);
    elsif p_action = 'tag' then
      if coalesce(p_payload->>'tag','') !~ '^[A-Za-z0-9_-]{2,40}$' then
        raise exception 'invalid_tag' using errcode = '22023'; end if;
      insert into public.actual_trade_tags(trade_id,owner_id,tag)
        values (p_trade_id,v_owner,p_payload->>'tag')
        on conflict (trade_id,tag) do nothing;
      v_ledger := jsonb_build_object('tag',p_payload->>'tag');
    elsif p_action = 'correct_fill' then
      v_reason := trim(p_payload->>'reason');
      select * into v_fill from public.actual_fills
        where id=(p_payload->>'fill_id')::uuid and trade_id=p_trade_id and owner_id=v_owner;
      if not found or coalesce(length(v_reason),0) not between 3 and 500
         or (p_payload->>'quantity')::bigint <= 0
         or (p_payload->>'price_idr')::numeric <= 0
         or (p_payload->>'fee_idr')::numeric < 0
         or p_payload->>'fee_status' not in ('actual','estimated')
      then raise exception 'invalid_fill_correction' using errcode = '22023'; end if;
      if p_payload ? 'filled_at' and
        (p_payload->>'filled_at' is null or not isfinite((p_payload->>'filled_at')::timestamptz)) then
        raise exception 'invalid_fill_time' using errcode = '22023'; end if;
      if p_payload ? 'restate_initial_risk' and
        jsonb_typeof(p_payload->'restate_initial_risk') is distinct from 'boolean' then
        raise exception 'invalid_restatement_flag' using errcode = '22023'; end if;
      insert into public.actual_fill_corrections(fill_id,trade_id,owner_id,filled_at,
        quantity,price_idr,fee_idr,fee_status,reason)
      values (v_fill.id,p_trade_id,v_owner,
        coalesce((p_payload->>'filled_at')::timestamptz,
          (select filled_at from public.actual_fill_corrections where fill_id=v_fill.id
            order by sequence desc limit 1),v_fill.filled_at),
        (p_payload->>'quantity')::bigint,
        (p_payload->>'price_idr')::numeric,(p_payload->>'fee_idr')::numeric,
        p_payload->>'fee_status',v_reason);
      v_ledger := public.recalculate_actual_trade(p_trade_id,
        v_fill.side='buy' and (p_payload->>'restate_initial_risk')::boolean is true);
      v_ledger := v_ledger || jsonb_build_object('corrected_fill_id',v_fill.id);
    else
      raise exception 'unsupported_journal_action' using errcode = '22023';
    end if;
    update public.actual_trades set revision=revision+1 where id=p_trade_id
      returning * into v_trade;
  end if;
  v_result := jsonb_build_object('trade_id',v_trade.id,'revision',v_trade.revision,
    'action',p_action,'ledger',v_ledger);
  insert into public.actual_journal_requests(owner_id,request_id,request,result)
    values(v_owner,p_request_id,v_request,v_result);
  insert into public.audit_events(owner_id,entity_id,action,details)
    values(v_owner,v_trade.id::text,'actual_journal_' || p_action,
      jsonb_build_object('request_id',p_request_id,'revision',v_trade.revision,
        'payload',p_payload,'before',v_before,'result',v_result));
  return v_result;
end $$;
commit;
