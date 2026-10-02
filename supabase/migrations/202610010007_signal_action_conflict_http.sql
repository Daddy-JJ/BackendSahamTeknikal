-- Forward-only business-conflict fix; migration 001 remains immutable.
-- Preserve signature, owner lock, idempotency, receipts, audit and grants.
begin;

create or replace function public.set_signal_action(
  p_signal_id text, p_action text, p_expected_revision integer, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_request jsonb := jsonb_build_object('signal_id',p_signal_id,'action',p_action,
    'expected_revision',p_expected_revision);
  v_prior public.signal_action_requests;
  v_revision integer;
  v_result jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_request_id is null or p_action is null
    or p_action not in ('watchlist','planned','skipped','none')
    or p_expected_revision is null or p_expected_revision < 0 then
    raise exception 'invalid_action' using errcode = '22023';
  end if;
  -- Same owner serializes request replay and optimistic revision validation.
  perform pg_advisory_xact_lock(hashtextextended('idx:action:' || v_owner::text, 0));
  select * into v_prior from public.signal_action_requests
    where owner_id = v_owner and request_id = p_request_id;
  if found then
    if v_prior.request is distinct from v_request then
      raise exception 'idempotency_conflict' using errcode = '23514';
    end if;
    return v_prior.result;
  end if;
  if not exists (select 1 from public.signals where id = p_signal_id) then
    raise exception 'signal_not_found' using errcode = '22023';
  end if;
  select revision into v_revision from public.signal_actions
    where owner_id = v_owner and signal_id = p_signal_id;
  if coalesce(v_revision, 0) <> p_expected_revision then
    raise exception 'revision_conflict' using errcode = 'PT412';
  end if;
  v_revision := coalesce(v_revision,0) + 1;
  insert into public.signal_actions values (v_owner,p_signal_id,p_action,v_revision,now())
  on conflict(owner_id,signal_id) do update
    set action = excluded.action, revision = excluded.revision, updated_at = excluded.updated_at;
  v_result := jsonb_build_object('signal_id',p_signal_id,'action',p_action,'revision',v_revision);
  insert into public.signal_action_requests values (v_owner,p_request_id,v_request,v_result);
  insert into public.audit_events(owner_id,entity_id,action,details)
    values(v_owner,p_signal_id,'signal_action_set',v_result);
  return v_result;
end; $$;
revoke all on function public.set_signal_action(text,text,integer,uuid) from public, anon, service_role;
grant execute on function public.set_signal_action(text,text,integer,uuid) to authenticated;
commit;
