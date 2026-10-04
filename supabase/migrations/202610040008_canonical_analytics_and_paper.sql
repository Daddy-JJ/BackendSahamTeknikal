-- Additive canonical analytics RPCs (R-curve, strategy attribution) and live paper persistence.
-- Preserves existing migration 001-007 behavior, signatures, RLS and ledger immutability.
begin;

-- 1. Canonical R-Curve RPC
create function public.actual_journal_r_curve(
  p_from date default null, p_to date default null,
  p_strategy text default null, p_exit_version text default null,
  p_exit_snapshot jsonb default null
) returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_mode text;
  v_total_closed integer := 0;
  v_final_r numeric := 0;
  v_max_dd_r numeric := 0;
  v_points jsonb := '[]'::jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_from > p_to then
    raise exception 'invalid_cohort_range' using errcode = '22023';
  end if;
  select data_mode into strict v_mode from public.deployment_settings where singleton;

  with scoped as (
    select t.* from public.actual_trades t
    where t.owner_id = v_owner and t.data_mode = v_mode
      and (p_strategy is null or t.primary_strategy = p_strategy)
      and (p_exit_version is null or t.exit_policy_snapshot->>'version' = p_exit_version)
      and (p_exit_snapshot is null or t.exit_policy_snapshot = p_exit_snapshot)
  ), closed as (
    select * from scoped
    where status = 'closed'
      and (p_from is null or (closed_at at time zone 'Asia/Jakarta')::date >= p_from)
      and (p_to is null or (closed_at at time zone 'Asia/Jakarta')::date <= p_to)
  ), ordered as (
    select
      c.id,
      c.ticker,
      c.primary_strategy,
      (c.closed_at at time zone 'Asia/Jakarta')::date as exit_session,
      c.closed_at,
      coalesce(c.realized_r, 0) as realized_r,
      c.realized_pnl_idr,
      row_number() over (order by c.closed_at asc, c.id asc) as seq,
      sum(coalesce(c.realized_r, 0)) over (
        order by c.closed_at asc, c.id asc
        rows between unbounded preceding and current row
      ) as cum_r,
      sum(c.realized_pnl_idr) over (
        order by c.closed_at asc, c.id asc
        rows between unbounded preceding and current row
      ) as cum_pnl_idr
    from closed c
  ), with_dd as (
    select
      o.*,
      max(o.cum_r) over (
        order by o.seq asc
        rows between unbounded preceding and current row
      ) as peak_r
    from ordered o
  ), calculated as (
    select
      w.*,
      (w.peak_r - w.cum_r) as drawdown_r
    from with_dd w
  )
  select
    coalesce(count(*), 0),
    coalesce(max(cum_r) filter (where seq = (select max(seq) from calculated)), 0),
    coalesce(max(drawdown_r), 0),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'sequence', seq,
          'trade_id', id,
          'ticker', ticker,
          'strategy', primary_strategy,
          'exit_session', exit_session,
          'closed_at', closed_at,
          'realized_r', realized_r,
          'cumulative_r', cum_r,
          'drawdown_r', drawdown_r,
          'realized_pnl_idr', realized_pnl_idr,
          'cumulative_pnl_idr', cum_pnl_idr
        )
        order by seq asc
      ),
      '[]'::jsonb
    )
  into v_total_closed, v_final_r, v_max_dd_r, v_points
  from calculated;

  return jsonb_build_object(
    'mode', 'actual',
    'data_mode', v_mode,
    'basis', 'IDR',
    'cohort_date', 'exit_session_Asia_Jakarta',
    'from', p_from,
    'to', p_to,
    'primary_strategy', p_strategy,
    'exit_version', p_exit_version,
    'exit_snapshot', p_exit_snapshot,
    'total_closed', v_total_closed,
    'final_cumulative_r', v_final_r,
    'max_drawdown_r', v_max_dd_r,
    'points', v_points
  );
end $$;
revoke all on function public.actual_journal_r_curve(date,date,text,text,jsonb)
  from public, anon, service_role;
grant execute on function public.actual_journal_r_curve(date,date,text,text,jsonb)
  to authenticated;

-- 2. Canonical Strategy Attribution RPC
create function public.actual_journal_attribution(
  p_from date default null, p_to date default null,
  p_exit_version text default null, p_exit_snapshot jsonb default null
) returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_mode text;
  v_rows jsonb := '[]'::jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_from > p_to then
    raise exception 'invalid_cohort_range' using errcode = '22023';
  end if;
  select data_mode into strict v_mode from public.deployment_settings where singleton;

  with scoped as (
    select t.* from public.actual_trades t
    where t.owner_id = v_owner and t.data_mode = v_mode
      and (p_exit_version is null or t.exit_policy_snapshot->>'version' = p_exit_version)
      and (p_exit_snapshot is null or t.exit_policy_snapshot = p_exit_snapshot)
  ), closed as (
    select * from scoped
    where status = 'closed'
      and (p_from is null or (closed_at at time zone 'Asia/Jakarta')::date >= p_from)
      and (p_to is null or (closed_at at time zone 'Asia/Jakarta')::date <= p_to)
  ), grouped as (
    select
      primary_strategy as strategy,
      count(*) as closed_count,
      count(*) filter (where round(realized_pnl_idr,4) > 0) as wins,
      count(*) filter (where round(realized_pnl_idr,4) < 0) as losses,
      count(*) filter (where round(realized_pnl_idr,4) = 0) as breakeven,
      coalesce(sum(realized_pnl_idr), 0) as net_pnl_idr,
      coalesce(sum(realized_pnl_idr) filter (where realized_pnl_idr > 0), 0) as positive_pnl_idr,
      coalesce(sum(realized_pnl_idr) filter (where realized_pnl_idr < 0), 0) as negative_pnl_idr,
      avg(realized_r) as expectancy_r,
      avg(realized_pnl_idr) filter (where realized_pnl_idr > 0) as mean_win_idr,
      avg(realized_pnl_idr) filter (where realized_pnl_idr < 0) as mean_loss_idr
    from closed
    group by primary_strategy
  )
  select
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'strategy', strategy,
          'closed', closed_count,
          'wins', wins,
          'losses', losses,
          'breakeven', breakeven,
          'net_pnl_idr', net_pnl_idr,
          'expectancy_r', expectancy_r,
          'win_rate', case when closed_count > 0 then wins::numeric / closed_count else null end,
          'profit_factor', case when losses > 0 then positive_pnl_idr / abs(negative_pnl_idr) else null end,
          'profit_factor_status', case when closed_count = 0 then 'no_closed'
            when losses = 0 then 'no_losses' else 'defined' end,
          'payoff_ratio', case when wins > 0 and losses > 0 then mean_win_idr / abs(mean_loss_idr) else null end,
          'payoff_status', case when closed_count = 0 then 'no_closed'
            when wins = 0 then 'no_wins' when losses = 0 then 'no_losses' else 'defined' end
        )
        order by net_pnl_idr desc, strategy asc
      ),
      '[]'::jsonb
    )
  into v_rows
  from grouped;

  return jsonb_build_object(
    'mode', 'actual',
    'data_mode', v_mode,
    'basis', 'IDR',
    'cohort_date', 'exit_session_Asia_Jakarta',
    'from', p_from,
    'to', p_to,
    'exit_version', p_exit_version,
    'exit_snapshot', p_exit_snapshot,
    'strategies', v_rows
  );
end $$;
revoke all on function public.actual_journal_attribution(date,date,text,jsonb)
  from public, anon, service_role;
grant execute on function public.actual_journal_attribution(date,date,text,jsonb)
  to authenticated;

-- 3. Live Paper Trading Persistence Table
create table public.paper_trades (
  id text not null,
  owner_id uuid not null default auth.uid() references auth.users(id),
  data_mode text not null check (data_mode in ('fixture', 'live')),
  run_id uuid references public.scan_runs(id),
  signal_id text references public.signals(id),
  ticker text not null,
  strategy text not null,
  experiment_id text not null,
  exit_mode text not null check (exit_mode in ('fixed_rr', 'ma_close', 'manual')),
  state text not null check (state in ('pending_entry', 'open', 'closed', 'data_hold')),
  reason text not null,
  entry_session date,
  entry_price numeric(18,4),
  initial_stop numeric(18,4),
  current_stop numeric(18,4),
  target_price numeric(18,4),
  exit_session date,
  exit_price numeric(18,4),
  exit_reason text,
  realized_r numeric(28,12),
  alternate_r numeric(28,12),
  initial_risk_idr numeric(28,4),
  details jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  primary key (id, owner_id)
);

alter table public.paper_trades enable row level security;
revoke all on public.paper_trades from public, anon, authenticated, service_role;
grant select on public.paper_trades to authenticated, service_role;
grant insert, update on public.paper_trades to service_role;

create policy owner_read on public.paper_trades for select to authenticated
  using ((select public.is_app_owner()) and owner_id = (select auth.uid()));

-- 4. Owner Paper Journal Reader RPC
create function public.read_paper_journal(
  p_experiment_id text default null,
  p_strategy text default null,
  p_state text default null
) returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_mode text;
  v_trades jsonb := '[]'::jsonb;
  v_closed_count integer := 0;
  v_open_count integer := 0;
  v_hold_count integer := 0;
  v_ambiguous_count integer := 0;
  v_win_count integer := 0;
  v_loss_count integer := 0;
  v_sum_r numeric := 0;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  select data_mode into strict v_mode from public.deployment_settings where singleton;

  with scoped as (
    select * from public.paper_trades
    where owner_id = v_owner and data_mode = v_mode
      and (p_experiment_id is null or experiment_id = p_experiment_id)
      and (p_strategy is null or strategy = p_strategy)
      and (p_state is null or state = p_state)
    order by created_at desc, id desc
  )
  select
    coalesce(count(*) filter (where state = 'closed'), 0),
    coalesce(count(*) filter (where state in ('open', 'pending_entry')), 0),
    coalesce(count(*) filter (where state = 'data_hold'), 0),
    coalesce(count(*) filter (where state = 'closed' and alternate_r is not null), 0),
    coalesce(count(*) filter (where state = 'closed' and realized_r > 0), 0),
    coalesce(count(*) filter (where state = 'closed' and realized_r < 0), 0),
    coalesce(sum(realized_r) filter (where state = 'closed'), 0),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'id', id,
          'run_id', run_id,
          'signal_id', signal_id,
          'ticker', ticker,
          'strategy', strategy,
          'experiment_id', experiment_id,
          'exit_mode', exit_mode,
          'state', state,
          'reason', reason,
          'entry_session', entry_session,
          'entry_price', entry_price,
          'initial_stop', initial_stop,
          'current_stop', current_stop,
          'target_price', target_price,
          'exit_session', exit_session,
          'exit_price', exit_price,
          'exit_reason', exit_reason,
          'realized_r', realized_r,
          'alternate_r', alternate_r,
          'initial_risk_idr', initial_risk_idr,
          'updated_at', updated_at
        )
      ),
      '[]'::jsonb
    )
  into v_closed_count, v_open_count, v_hold_count, v_ambiguous_count,
       v_win_count, v_loss_count, v_sum_r, v_trades
  from scoped;

  return jsonb_build_object(
    'mode', 'paper',
    'data_mode', v_mode,
    'trades_count', v_closed_count + v_open_count + v_hold_count,
    'closed_count', v_closed_count,
    'open_count', v_open_count,
    'data_hold_count', v_hold_count,
    'ambiguous_count', v_ambiguous_count,
    'wins', v_win_count,
    'losses', v_loss_count,
    'win_rate', case when v_closed_count > 0 then v_win_count::numeric / v_closed_count else null end,
    'expectancy_r', case when v_closed_count > 0 then v_sum_r / v_closed_count else null end,
    'cumulative_r', v_sum_r,
    'trades', v_trades
  );
end $$;
revoke all on function public.read_paper_journal(text,text,text)
  from public, anon, service_role;
grant execute on function public.read_paper_journal(text,text,text)
  to authenticated;

commit;
