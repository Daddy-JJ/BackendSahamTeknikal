-- Migration: Broker Flow & Bandarmology Snapshots Table
-- Project: SahamTeknikal (hcjfxbynqzsaidlwvdfx)

CREATE TABLE IF NOT EXISTS public.broker_flow_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    data_mode TEXT NOT NULL DEFAULT 'live',
    market_summary JSONB NOT NULL,
    top_accumulations JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_distributions JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_brokers JSONB NOT NULL DEFAULT '[]'::jsonb,
    sector_flows JSONB NOT NULL DEFAULT '[]'::jsonb,
    quadrant_maps JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Row Level Security
ALTER TABLE public.broker_flow_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access for broker_flow_snapshots"
ON public.broker_flow_snapshots
FOR SELECT
TO public
USING (true);

CREATE POLICY "Allow service role write access for broker_flow_snapshots"
ON public.broker_flow_snapshots
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- pg_cron Schedule for Supabase
-- Scheduled every Monday to Friday at 18:30 WIB (11:30 UTC)
-- Runs the sync-broker-flow Edge Function to refresh EOD bandarmology data
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule(
      'sync-broker-flow-nightly',
      '30 11 * * 1-5',
      $cron$
      SELECT net.http_post(
        url := 'https://hcjfxbynqzsaidlwvdfx.supabase.co/functions/v1/sync-broker-flow',
        headers := '{"Content-Type": "application/json"}'::jsonb
      );
      $cron$
    );
  END IF;
END $$;
