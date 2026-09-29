-- M2 market history: compact immutable receipts plus changed-bar revisions.
-- Apply after 202609290001 on the isolated development project first.
begin;

create table public.market_series_revisions (
  id uuid primary key default gen_random_uuid(),
  namespace text not null check (namespace ~ '^[a-z0-9_-]{1,64}$'),
  data_mode text not null check (data_mode in ('fixture','live')),
  provider text not null check (provider in ('fixture','yfinance','eodhd')),
  ticker text not null check (ticker ~ '^[A-Z0-9_-]{1,20}$'),
  provider_symbol text not null,
  price_basis text not null,
  provider_version text not null,
  input_digest text not null check (input_digest ~ '^[a-f0-9]{64}$'),
  snapshot_hash text not null check (snapshot_hash ~ '^[a-f0-9]{32}$'),
  metadata jsonb not null check (jsonb_typeof(metadata) = 'object'),
  bar_count integer not null check (bar_count >= 0),
  bar_cutoff bigint not null check (bar_cutoff >= 0),
  fetched_at timestamptz not null,
  stored_at timestamptz not null default now(),
  unique (namespace,data_mode,provider,ticker,provider_version,input_digest),
  check ((data_mode = 'fixture') = (provider = 'fixture'))
);
create index market_series_revisions_lookup on public.market_series_revisions
  (namespace,data_mode,ticker,stored_at desc);

create table public.market_bar_revisions (
  revision_seq bigint generated always as identity primary key,
  series_id uuid not null references public.market_series_revisions(id) deferrable initially deferred,
  namespace text not null,
  data_mode text not null check (data_mode in ('fixture','live')),
  provider text not null check (provider in ('fixture','yfinance','eodhd')),
  ticker text not null,
  session_date date not null,
  bar jsonb not null check (jsonb_typeof(bar) = 'object'),
  stored_at timestamptz not null default now()
);
create index market_bar_revisions_history on public.market_bar_revisions
  (namespace,data_mode,provider,ticker,session_date,revision_seq desc);

do $$
declare t text;
begin
  foreach t in array array['market_series_revisions','market_bar_revisions'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
    execute format('grant select on public.%I to authenticated,service_role',t);
    execute format('create policy owner_read on public.%I for select to authenticated using ((select public.is_app_owner()))',t);
    execute format('create trigger immutable_record before update or delete on public.%I for each row execute function public.reject_immutable_mutation()',t);
  end loop;
end;
$$;

create function public.ingest_market_series(p_record jsonb) returns jsonb
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
  v_bar jsonb;
  v_session date;
  v_previous jsonb;
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
    or jsonb_typeof(v_snapshot->'bars') <> 'array'
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
  v_hash := pg_catalog.md5(v_snapshot::text);
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
    v_namespace || ':' || v_mode || ':' || v_provider || ':' || v_ticker,0));
  select * into v_existing from public.market_series_revisions
    where namespace=v_namespace and data_mode=v_mode and provider=v_provider
      and ticker=v_ticker and provider_version=v_version and input_digest=v_digest;
  if found then
    if v_existing.snapshot_hash is distinct from v_hash
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
    v_session := (v_bar->>'session')::date;
    if v_session = any(v_seen) then
      raise exception 'duplicate_market_session' using errcode = '22023';
    end if;
    v_seen := pg_catalog.array_append(v_seen,v_session);
    select bar into v_previous from public.market_bar_revisions
      where namespace=v_namespace and data_mode=v_mode and provider=v_provider
        and ticker=v_ticker and session_date=v_session
      order by revision_seq desc limit 1;
    if not found or v_previous is distinct from v_bar then
      insert into public.market_bar_revisions
        (series_id,namespace,data_mode,provider,ticker,session_date,bar)
      values (v_id,v_namespace,v_mode,v_provider,v_ticker,v_session,v_bar);
      v_inserted := v_inserted+1;
    end if;
  end loop;
  select coalesce(max(revision_seq),0) into v_cutoff from public.market_bar_revisions
    where namespace=v_namespace and data_mode=v_mode and provider=v_provider and ticker=v_ticker;
  insert into public.market_series_revisions
    (id,namespace,data_mode,provider,ticker,provider_symbol,price_basis,provider_version,input_digest,
     snapshot_hash,metadata,bar_count,bar_cutoff,fetched_at)
  values
    (v_id,v_namespace,v_mode,v_provider,v_ticker,p_record->>'provider_symbol',
     p_record->>'price_basis',v_version,v_digest,v_hash,v_snapshot - 'bars',
     jsonb_array_length(v_snapshot->'bars'),v_cutoff,(p_record->>'fetched_at')::timestamptz);
  return pg_catalog.jsonb_build_object('revision_id',v_id,'replayed',false,'bars_changed',v_inserted);
end;
$$;
revoke all on function public.ingest_market_series(jsonb) from public,anon,authenticated;
grant execute on function public.ingest_market_series(jsonb) to service_role;
commit;
