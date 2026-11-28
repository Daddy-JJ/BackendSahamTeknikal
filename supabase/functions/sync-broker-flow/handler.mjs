// Supabase Edge Function: Daily EOD Broker Flow & Bandarmology Aggregator

function reply(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export function createHandler({ env, fetchImpl = fetch }) {
  return async (request) => {
    if (request.method !== "POST") {
      return reply(405, { error: "method_not_allowed" });
    }

    const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
    const supabaseUrl = env("SUPABASE_URL");

    if (!serviceKey || !supabaseUrl) {
      return reply(503, { error: "supabase_env_not_configured" });
    }

    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${serviceKey}`) {
      return reply(401, { error: "unauthorized" });
    }

    let incomingPayload = null;
    try {
      const bodyText = await request.text();
      if (!bodyText || bodyText.trim().length === 0) {
        return reply(400, { error: "empty_payload" });
      }
      incomingPayload = JSON.parse(bodyText);
    } catch (err) {
      return reply(400, { error: "invalid_json_body", details: String(err) });
    }

    const snapshotDate = incomingPayload?.snapshot_date;
    const marketSummary = incomingPayload?.market_summary;
    if (
      typeof snapshotDate !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(snapshotDate) ||
      !marketSummary ||
      typeof marketSummary !== "object"
    ) {
      return reply(400, {
        error: "invalid_snapshot_payload",
        message: "snapshot_date (YYYY-MM-DD) and market_summary are required.",
      });
    }

    const payload = {
      snapshot_date: snapshotDate,
      data_mode: "live",
      market_summary: marketSummary,
      top_accumulations: Array.isArray(incomingPayload.top_accumulations)
        ? incomingPayload.top_accumulations
        : [],
      top_distributions: Array.isArray(incomingPayload.top_distributions)
        ? incomingPayload.top_distributions
        : [],
      top_brokers: Array.isArray(incomingPayload.top_brokers) ? incomingPayload.top_brokers : [],
      sector_flows: Array.isArray(incomingPayload.sector_flows) ? incomingPayload.sector_flows : [],
      quadrant_maps:
        incomingPayload.quadrant_maps && typeof incomingPayload.quadrant_maps === "object"
          ? incomingPayload.quadrant_maps
          : {},
    };

    try {
      const insertRes = await fetchImpl(`${supabaseUrl}/rest/v1/broker_flow_snapshots`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: serviceKey,
          Authorization: `Bearer ${serviceKey}`,
          Prefer: "resolution=merge-duplicates",
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(10000),
      });

      if (!insertRes.ok) {
        return reply(502, {
          success: false,
          error: "supabase_snapshot_upsert_failed",
          status: insertRes.status,
        });
      }

      if (incomingPayload.ticker_horizons && typeof incomingPayload.ticker_horizons === "object") {
        const tickerRows = Object.entries(incomingPayload.ticker_horizons).map(([ticker, horizons]) => ({
          ticker: ticker.toUpperCase().trim(),
          snapshot_date: snapshotDate,
          horizon_2d: horizons["2D"] || {},
          horizon_5d: horizons["5D"] || {},
          horizon_10d: horizons["10D"] || {},
        }));

        if (tickerRows.length > 0) {
          const tickerRes = await fetchImpl(`${supabaseUrl}/rest/v1/broker_flow_ticker_horizons`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              apikey: serviceKey,
              Authorization: `Bearer ${serviceKey}`,
              Prefer: "resolution=merge-duplicates",
            },
            body: JSON.stringify(tickerRows),
            signal: AbortSignal.timeout(15000),
          });
          if (!tickerRes.ok) {
            return reply(502, {
              success: false,
              error: "supabase_horizons_upsert_failed",
              status: tickerRes.status,
            });
          }
        }
      }

      return reply(200, {
        success: true,
        message: `Snapshot broker flow untuk ${snapshotDate} berhasil diperbarui di Supabase database.`,
        data: payload,
      });
    } catch (err) {
      return reply(502, {
        success: false,
        error: "supabase_unreachable",
        details: String(err),
      });
    }
  };
}
