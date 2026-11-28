-- Unschedule legacy empty pg_cron job; GitHub Actions daily_broker_flow_sync.py owns scheduled syncing.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'sync-broker-flow-nightly') THEN
      PERFORM cron.unschedule('sync-broker-flow-nightly');
    END IF;
  END IF;
END $$;
