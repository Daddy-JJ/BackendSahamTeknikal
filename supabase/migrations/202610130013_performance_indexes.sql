-- Performance optimization indexes for query execution and reporting.
-- Preserves all economic rules, schema definitions, and RLS policies.
begin;

-- 1. Eliminate Sequential Scans on actual journal child event lookups and export subqueries
create index if not exists idx_actual_notes_trade_id
  on public.actual_notes(trade_id, created_at desc, id desc);

create index if not exists idx_actual_stop_events_trade_id
  on public.actual_stop_events(trade_id, occurred_at desc, id desc);

-- 2. Covering composite index for scanner forward runs lookup
create index if not exists idx_scan_runs_forward_lookup
  on public.scan_runs(namespace, data_mode, session_date desc, stored_at desc, id desc);

-- 3. Composite covering index for persistent paper reporting
create index if not exists idx_paper_trades_reporting_composite
  on public.paper_trades(owner_id, data_mode, model_version, exit_mode, strategy, state);

commit;
