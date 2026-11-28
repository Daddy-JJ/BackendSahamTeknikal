import assert from "node:assert/strict";
import test from "node:test";
import { createHandler } from "./handler.mjs";

const env = (key) =>
  ({
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: "test-service-role",
  })[key];

test("sync-broker-flow rejects GET, unauthorized POST, and empty/zero payloads", async () => {
  const handler = createHandler({
    env,
    fetchImpl: async () => assert.fail("must not write to Supabase on invalid request"),
  });

  const getRes = await handler(new Request("https://example.supabase.co/functions/v1/sync-broker-flow"));
  assert.equal(getRes.status, 405);

  const unauthRes = await handler(
    new Request("https://example.supabase.co/functions/v1/sync-broker-flow", {
      method: "POST",
      body: "{}",
    })
  );
  assert.equal(unauthRes.status, 401);

  const emptyRes = await handler(
    new Request("https://example.supabase.co/functions/v1/sync-broker-flow", {
      method: "POST",
      headers: { Authorization: "Bearer test-service-role" },
      body: "",
    })
  );
  assert.equal(emptyRes.status, 400);

  const missingSummaryRes = await handler(
    new Request("https://example.supabase.co/functions/v1/sync-broker-flow", {
      method: "POST",
      headers: { Authorization: "Bearer test-service-role" },
      body: JSON.stringify({ snapshot_date: "2026-11-27" }),
    })
  );
  assert.equal(missingSummaryRes.status, 400);
});

test("sync-broker-flow upserts valid snapshot and ticker_horizons payloads", async () => {
  const calls = [];
  const handler = createHandler({
    env,
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ ok: true }), { status: 201 });
    },
  });

  const res = await handler(
    new Request("https://example.supabase.co/functions/v1/sync-broker-flow", {
      method: "POST",
      headers: { Authorization: "Bearer test-service-role" },
      body: JSON.stringify({
        snapshot_date: "2026-11-27",
        market_summary: {
          date: "2026-11-27",
          quadrant_counts: { markup_akumulasi: 10, markup_distribusi: 5, markdown_akumulasi: 4, markdown_distribusi: 8 },
          total_classified: 27,
          smart_money_net: 150000000000,
          total_turnover: 12000000000000,
        },
        top_accumulations: [],
        top_distributions: [],
        ticker_horizons: {
          BBCA: { "2D": { ticker: "BBCA" }, "5D": { ticker: "BBCA" }, "10D": { ticker: "BBCA" } },
        },
      }),
    })
  );

  assert.equal(res.status, 200);
  assert.equal(calls.length, 2);
  assert.ok(calls[0].url.endsWith("/rest/v1/broker_flow_snapshots"));
  assert.ok(calls[1].url.endsWith("/rest/v1/broker_flow_ticker_horizons"));
});
