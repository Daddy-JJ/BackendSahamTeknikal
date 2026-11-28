-- Migration: Redevelop SahamTeknikal v2 Schema
-- Tables: idx_ticker_master, idx_eod_bars_cache, daily_market_dashboard,
--         daily_sector_snapshots, daily_screening_signals
-- Project: SahamTeknikal (vsdfegfapxyjighkhuxb)

CREATE TABLE IF NOT EXISTS public.idx_ticker_master (
    ticker TEXT PRIMARY KEY,
    sector TEXT NOT NULL,
    sector_slug TEXT NOT NULL,
    market_cap NUMERIC,
    free_float_pct NUMERIC,
    weight_proxy NUMERIC,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_ticker_master_sector_slug
ON public.idx_ticker_master (sector_slug);

CREATE TABLE IF NOT EXISTS public.idx_eod_bars_cache (
    ticker TEXT PRIMARY KEY,
    latest_date DATE NOT NULL,
    bar_count INTEGER NOT NULL,
    bars_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.daily_market_dashboard (
    session_date DATE PRIMARY KEY,
    ihsg_close NUMERIC NOT NULL,
    ihsg_change NUMERIC NOT NULL,
    ihsg_change_pct NUMERIC NOT NULL,
    market_regime TEXT NOT NULL CHECK (market_regime IN ('BULL', 'NEUTRAL', 'BEAR')),
    breadth JSONB NOT NULL,
    ihsg_chart_data JSONB NOT NULL,
    contributors JSONB NOT NULL,
    sector_heatmap JSONB NOT NULL,
    quadrant_summary JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.daily_sector_snapshots (
    session_date DATE NOT NULL,
    sector_slug TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    summary JSONB NOT NULL,
    chart_series JSONB NOT NULL,
    stocks JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    PRIMARY KEY (session_date, sector_slug)
);

CREATE INDEX IF NOT EXISTS idx_daily_sector_lookup
ON public.daily_sector_snapshots (sector_slug, session_date DESC);

CREATE TABLE IF NOT EXISTS public.daily_screening_signals (
    id BIGSERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    sector TEXT,
    sector_slug TEXT,
    signal_type TEXT NOT NULL,
    signal_source TEXT NOT NULL DEFAULT 'engine_v2',
    close_price NUMERIC NOT NULL,
    change_pct NUMERIC,
    entry_price NUMERIC NOT NULL,
    stop_loss NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    rr_tp1 NUMERIC,
    rr_tp2 NUMERIC,
    regime TEXT NOT NULL CHECK (regime IN ('MARKUP', 'CONSOLIDATING', 'MARKDOWN')),
    regime_action TEXT NOT NULL,
    smart_money_score INTEGER NOT NULL CHECK (smart_money_score BETWEEN 0 AND 3),
    smart_money_label TEXT NOT NULL CHECK (
        smart_money_label IN ('STRONG CONFIRMATION', 'CONFIRMED', 'PARTIAL', 'NOT CONFIRMED')
    ),
    smart_money_factors JSONB NOT NULL,
    rule_checklist JSONB NOT NULL,
    notes TEXT,
    eval_tp1_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        eval_tp1_status IN ('win', 'loss', 'pending', 'ambiguous', 'excluded')
    ),
    eval_tp2_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        eval_tp2_status IN ('win', 'loss', 'pending', 'ambiguous', 'excluded')
    ),
    eval_up_5d_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        eval_up_5d_status IN ('win', 'loss', 'pending', 'ambiguous', 'excluded')
    ),
    eval_up_10d_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        eval_up_10d_status IN ('win', 'loss', 'pending', 'ambiguous', 'excluded')
    ),
    eval_up_latest_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        eval_up_latest_status IN ('win', 'loss', 'pending', 'ambiguous', 'excluded')
    ),
    evaluated_until_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE (signal_date, ticker, signal_type)
);

CREATE INDEX IF NOT EXISTS idx_signals_date_type
ON public.daily_screening_signals (signal_date DESC, signal_type);

CREATE INDEX IF NOT EXISTS idx_signals_ticker
ON public.daily_screening_signals (ticker, signal_date DESC);

CREATE INDEX IF NOT EXISTS idx_signals_score
ON public.daily_screening_signals (smart_money_score DESC, signal_date DESC);

-- Enable Row Level Security across all new tables
ALTER TABLE public.idx_ticker_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.idx_eod_bars_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_market_dashboard ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_sector_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_screening_signals ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'idx_ticker_master',
        'idx_eod_bars_cache',
        'daily_market_dashboard',
        'daily_sector_snapshots',
        'daily_screening_signals'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = tbl AND policyname = 'Allow public read ' || tbl
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT TO public USING (true);',
                'Allow public read ' || tbl,
                tbl
            );
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = tbl AND policyname = 'Allow service role write ' || tbl
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true);',
                'Allow service role write ' || tbl,
                tbl
            );
        END IF;
    END LOOP;
END $$;
