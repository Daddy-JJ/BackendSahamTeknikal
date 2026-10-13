import assert from "node:assert/strict";
import test from "node:test";
import { createHandler } from "../functions/idx-paper-watchdog/handler.mjs";

const project = "https://hcjfxbynqzsaidlwvdfx.supabase.co";
const ticket = "11111111-1111-4111-8111-111111111111";
const claim = { contract_version: 1, receipt_id: 1, owner_id: ticket, data_mode: "live",
  target_date: "2026-10-12", paper_only: true, expires_at: "2026-10-13T01:10:00Z" };
const env = (key) => ({ SUPABASE_URL: project, SUPABASE_SERVICE_ROLE_KEY: "synthetic-service",
  GITHUB_WATCHDOG_DISPATCH_TOKEN: "github_pat_synthetic-only" })[key];
const request = (body = { ticket }) => new Request(`${project}/functions/v1/idx-paper-watchdog`, {
  method: "POST", body: JSON.stringify(body),
});
const json = (data) => new Response(JSON.stringify(data), { status: 200 });
const now = () => Date.parse("2026-10-13T01:00:00Z");

test("one-use claim precedes fixed main dispatch; secrets stay in their server destinations", async () => {
  const calls = [];
  const handler = createHandler({ env, now, fetchImpl: async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("consume_paper_watchdog_ticket_v1")) return json(claim);
    if (url.endsWith("dispatches")) return new Response(null, { status: 204 });
    return json({ contract_version: 1, receipt_id: 1, status: "accepted" });
  } });
  const response = await handler(request());
  assert.equal(response.status, 200);
  assert.equal(calls.length, 3);
  assert.equal(calls[1].url, "https://api.github.com/repos/Daddy-JJ/BackendSahamTeknikal/actions/workflows/scheduled-scanner.yml/dispatches");
  assert.deepEqual(JSON.parse(calls[1].options.body), { ref: "main", inputs: {
    target_date: "2026-10-12", execute_publication: "true", paper_only: "true" } });
  assert.equal(calls[0].options.headers.Authorization, "Bearer synthetic-service");
  assert.equal(calls[1].options.headers.Authorization, "Bearer github_pat_synthetic-only");
  assert.equal(calls[1].options.redirect, "error");
  assert.equal((await response.text()).includes("synthetic"), false);
});

test("invalid, replayed, expired or arbitrary target requests cannot dispatch", async () => {
  for (const payload of [{}, { ticket: "invalid" }, { ticket, ref: "evil" }]) {
    const handler = createHandler({ env, now, fetchImpl: () => assert.fail("must not fetch") });
    assert.equal((await handler(request(payload))).status, 400);
  }
  for (const source of [new Response(null, { status: 409 }), json({ ...claim,
    expires_at: "2026-10-13T00:59:59Z" })]) {
    let calls = 0;
    const handler = createHandler({ env, now, fetchImpl: async () => { calls++; return source; } });
    assert.notEqual((await handler(request())).status, 200);
    assert.equal(calls, 1);
  }
});

test("credential/configuration failure is explicit and does not consume a ticket", async () => {
  const handler = createHandler({ env: (name) => name === "SUPABASE_URL" ? "https://other.supabase.co" : env(name),
    fetchImpl: () => assert.fail("must not fetch") });
  assert.equal((await handler(request())).status, 503);
  assert.equal((await handler(new Request(project))).status, 405);
});

test("GitHub auth/rate-limit/transport outcomes record safe canonical statuses", async () => {
  for (const httpStatus of [401, 403, 429, 500, 0]) {
    const calls = [];
    const handler = createHandler({ env, now, fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith("consume_paper_watchdog_ticket_v1")) return json(claim);
      if (url.endsWith("dispatches")) {
        if (!httpStatus) throw new Error("private transport details");
        return new Response(null, { status: httpStatus });
      }
      return json({ contract_version: 1, receipt_id: 1, status: "failed" });
    } });
    const response = await handler(request());
    assert.equal(response.status, 200);
    assert.deepEqual(JSON.parse(calls[2].options.body), { p_receipt_id: 1,
      p_http_status: httpStatus, p_transport_failed: httpStatus === 0 });
    assert.equal(await response.text(), '{"code":"dispatch_failed"}');
  }
});
