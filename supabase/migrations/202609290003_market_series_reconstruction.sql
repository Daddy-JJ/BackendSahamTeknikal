-- Exact provider-input reconstruction. Apply after 002, development first.
-- Legacy receipts remain immutable and cannot be reconstructed by guessing.
begin;
alter table public.market_series_revisions
  add column bar_sessions date[],
  add column metadata_source text,
  add column source_hash text,
  add constraint market_session_manifest_count check
    (bar_sessions is null or cardinality(bar_sessions) = bar_count),
  add constraint market_source_hash_format check
    (source_hash is null or source_hash ~ '^[a-f0-9]{32}$');
alter table public.market_bar_revisions add column bar_source text;

create or replace function public.ingest_market_series(p_record jsonb) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  v_namespace text := p_record->>'namespace';
  v_mode text := p_record->>'data_mode';
  v_provider text := p_record->>'provider';
  v_ticker text := p_record->>'ticker';
  v_digest text := p_record->>'input_digest';
  v_version text := p_record->>'provider_version';
  v_snapshot jsonb := p_record->'snapshot';
  v_hash text;
  v_source_hash text;
  v_bar_source text;
  v_sources jsonb := p_record->'bar_sources';
  v_metadata_source text := p_record->>'metadata_source';
  v_bar jsonb;
  v_session date;
  v_previous jsonb;
  v_previous_source text;
  v_index integer := 0;
  v_existing public.market_series_revisions;
  v_id uuid;
  v_inserted integer := 0;
  v_cutoff bigint;
  v_seen date[] := array[]::date[];
begin
  if v_namespace is null or v_namespace !~ '^[a-z0-9_-]{1,64}$'
    or v_mode is null or v_mode not in ('fixture','live')
    or v_provider is null or v_provider not in ('fixture','yfinance','eodhd')
    or v_ticker is null or v_ticker !~ '^[A-Z0-9_-]{1,20}$'
    or v_digest is null or v_digest !~ '^[a-f0-9]{64}$'
    or v_version is null or length(v_version) not between 1 and 80
    or v_snapshot is null or jsonb_typeof(v_snapshot) <> 'object'
    or jsonb_typeof(v_snapshot->'bars') is distinct from 'array'
    or (v_mode = 'fixture') <> (v_provider = 'fixture')
    or v_snapshot->>'ticker' is distinct from v_ticker
    or v_snapshot->>'provider' is distinct from v_provider
    or v_snapshot->>'provider_symbol' is distinct from p_record->>'provider_symbol'
    or v_snapshot->>'price_basis' is distinct from p_record->>'price_basis'
  then
    raise exception 'invalid_market_series' using errcode = '22023';
  end if;
  if p_record->>'fetched_at' is null
    or p_record->>'provider_symbol' is null
    or p_record->>'price_basis' is null then
    raise exception 'invalid_market_series' using errcode = '22023';
  end if;
  if (select data_mode from public.deployment_settings where singleton) is distinct from v_mode then
    raise exception 'deployment_mode_mismatch' using errcode = '22023';
  end if;
  if jsonb_typeof(v_sources) is distinct from 'array'
    or v_metadata_source is null then
    raise exception 'market_source_missing' using errcode = '22023';
  end if;
  if jsonb_array_length(v_sources) <> jsonb_array_length(v_snapshot->'bars')
    or v_metadata_source::jsonb is distinct from (v_snapshot - 'bars') then
    raise exception 'market_source_mismatch' using errcode = '22023';
  end if;
  v_hash := pg_catalog.md5(v_snapshot::text);
  v_source_hash := pg_catalog.md5(v_metadata_source || v_sources::text);
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
    v_namespace || ':' || v_mode || ':' || v_provider || ':' || v_ticker,0));
  select * into v_existing from public.market_series_revisions
    where namespace=v_namespace and data_mode=v_mode and provider=v_provider
      and ticker=v_ticker and provider_version=v_version and input_digest=v_digest;
  if found then
    if v_existing.snapshot_hash is distinct from v_hash
      or v_existing.source_hash is distinct from v_source_hash
      or v_existing.provider_symbol is distinct from p_record->>'provider_symbol'
      or v_existing.price_basis is distinct from p_record->>'price_basis' then
      raise exception 'market_digest_conflict' using errcode = '23514';
    end if;
    return pg_catalog.jsonb_build_object('revision_id',v_existing.id,'replayed',true,'bars_changed',0);
  end if;
  v_id := pg_catalog.gen_random_uuid();
  for v_bar in select value from pg_catalog.jsonb_array_elements(v_snapshot->'bars') loop
    if pg_catalog.jsonb_typeof(v_bar) <> 'object' or v_bar->>'session' is null then
      raise exception 'invalid_market_bar' using errcode = '22023';
    end if;
    if jsonb_typeof(v_sources->v_index) is distinct from 'string' then
      raise exception 'invalid_market_bar_source' using errcode = '22023';
    end if;
    v_bar_source := v_sources->>v_index;
    v_index := v_index + 1;
    if v_bar_source::jsonb is distinct from v_bar then
      raise exception 'market_source_mismatch' using errcode = '22023';
    end if;
    v_session := (v_bar->>'session')::date;
    if v_session = any(v_seen) then
      raise exception 'duplicate_market_session' using errcode = '22023';
    end if;
    v_seen := pg_catalog.array_append(v_seen,v_session);
    select bar,bar_source into v_previous,v_previous_source from public.market_bar_revisions
      where namespace=v_namespace and data_mode=v_mode and provider=v_provider
        and ticker=v_ticker and session_date=v_session
      order by revision_seq desc limit 1;
    if not found or v_previous is distinct from v_bar or v_previous_source is distinct from v_bar_source then
      insert into public.market_bar_revisions
        (series_id,namespace,data_mode,provider,ticker,session_date,bar,bar_source)
      values (v_id,v_namespace,v_mode,v_provider,v_ticker,v_session,v_bar,v_bar_source);
      v_inserted := v_inserted+1;
    end if;
  end loop;
  select coalesce(max(revision_seq),0) into v_cutoff from public.market_bar_revisions
    where namespace=v_namespace and data_mode=v_mode and provider=v_provider and ticker=v_ticker;
  insert into public.market_series_revisions
    (id,namespace,data_mode,provider,ticker,provider_symbol,price_basis,provider_version,input_digest,
     snapshot_hash,metadata,bar_count,bar_cutoff,fetched_at,
     bar_sessions,metadata_source,source_hash)
  values
    (v_id,v_namespace,v_mode,v_provider,v_ticker,p_record->>'provider_symbol',
     p_record->>'price_basis',v_version,v_digest,v_hash,v_snapshot - 'bars',
     jsonb_array_length(v_snapshot->'bars'),v_cutoff,(p_record->>'fetched_at')::timestamptz,
     v_seen,v_metadata_source,v_source_hash);
  return pg_catalog.jsonb_build_object('revision_id',v_id,'replayed',false,'bars_changed',v_inserted);
end;
$$;

revoke all on function public.ingest_market_series(jsonb) from public,anon,authenticated;
grant execute on function public.ingest_market_series(jsonb) to service_role;

-- Invoker deliberately retains table RLS: an outsider sees no receipt.
create function public.read_market_series(p_revision_id uuid) returns jsonb
language plpgsql stable security invoker set search_path = ''
as $$
declare
  r public.market_series_revisions;
  v_bars jsonb;
  v_sources jsonb;
  v_count integer;
  v_snapshot jsonb;
begin
  select * into r from public.market_series_revisions where id=p_revision_id;
  if not found then
    raise exception 'market_revision_not_found' using errcode = 'P0002';
  end if;
  if r.bar_sessions is null or r.metadata_source is null or r.source_hash is null then
    raise exception 'market_revision_manifest_missing' using errcode = '23514';
  end if;
  select coalesce(jsonb_agg(b.bar order by s.position),'[]'::jsonb),
         coalesce(jsonb_agg(b.bar_source order by s.position),'[]'::jsonb),
         count(b.bar_source)
    into v_bars,v_sources,v_count
    from unnest(r.bar_sessions) with ordinality as s(day,position)
    join lateral (
      select bar,bar_source from public.market_bar_revisions
      where namespace=r.namespace and data_mode=r.data_mode and provider=r.provider
        and ticker=r.ticker and session_date=s.day and revision_seq<=r.bar_cutoff
      order by revision_seq desc limit 1
    ) b on true;
  v_snapshot := r.metadata || jsonb_build_object('bars',v_bars);
  if v_count <> r.bar_count
    or pg_catalog.md5(v_snapshot::text) is distinct from r.snapshot_hash
    or r.metadata_source::jsonb is distinct from r.metadata
    or pg_catalog.md5(r.metadata_source || v_sources::text) is distinct from r.source_hash then
    raise exception 'market_revision_integrity_failed' using errcode = '23514';
  end if;
  return jsonb_build_object(
    'revision_id',r.id,'namespace',r.namespace,'data_mode',r.data_mode,
    'input_digest',r.input_digest,'provider_version',r.provider_version,
    'fetched_at',r.fetched_at,'metadata_source',r.metadata_source,'bar_sources',v_sources);
end;
$$;
revoke all on function public.read_market_series(uuid) from public,anon;
grant execute on function public.read_market_series(uuid) to authenticated,service_role;
commit;
