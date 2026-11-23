-- Migration: Broker Flow Ticker Horizons Table & Dynamic Aggregation
-- Project: SahamTeknikal (hcjfxbynqzsaidlwvdfx)

CREATE TABLE IF NOT EXISTS public.broker_flow_ticker_horizons (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    horizon_2d JSONB NOT NULL,
    horizon_5d JSONB NOT NULL,
    horizon_10d JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE (ticker, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_bf_horizons_lookup 
ON public.broker_flow_ticker_horizons (ticker, snapshot_date DESC);

-- Row Level Security
ALTER TABLE public.broker_flow_ticker_horizons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access for broker_flow_ticker_horizons"
ON public.broker_flow_ticker_horizons
FOR SELECT
TO public
USING (true);

CREATE POLICY "Allow service role write access for broker_flow_ticker_horizons"
ON public.broker_flow_ticker_horizons
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
