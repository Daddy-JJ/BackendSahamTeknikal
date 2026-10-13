// GitHub credential stays in Edge secrets; pg_net carries only a one-use ticket.
const PROJECT_URL = "https://hcjfxbynqzsaidlwvdfx.supabase.co";
const DISPATCH_URL = "https://api.github.com/repos/Daddy-JJ/BackendSahamTeknikal/actions/workflows/scheduled-scanner.yml/dispatches";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function reply(status, code) {
  return new Response(JSON.stringify({ code }), {
    status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export function createHandler({ env, fetchImpl = fetch, now = () => Date.now() }) {
  return async (request) => {
    if (request.method !== "POST") return reply(405, "method_not_allowed");
    const url = env("SUPABASE_URL");
    const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
    const dispatchToken = env("GITHUB_WATCHDOG_DISPATCH_TOKEN");
    if (url !== PROJECT_URL || !serviceKey || !dispatchToken?.startsWith("github_pat_")) {
      return reply(503, "watchdog_not_configured");
    }
    let ticket;
    try {
      const body = await request.text();
      if (body.length > 1024) return reply(400, "invalid_ticket");
      const data = JSON.parse(body);
      if (Object.keys(data).length !== 1 || !UUID.test(data.ticket)) {
        return reply(400, "invalid_ticket");
      }
      ticket = data.ticket;
    } catch {
      return reply(400, "invalid_ticket");
    }
    const rpc = (name, body) => fetchImpl(`${PROJECT_URL}/rest/v1/rpc/${name}`, {
      method: "POST", headers: { "Content-Type": "application/json", apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}` }, body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    let claim;
    try {
      const consumed = await rpc("consume_paper_watchdog_ticket_v1", { p_ticket: ticket });
      if (!consumed.ok) return reply(409, "ticket_unavailable");
      claim = await consumed.json();
      if (claim.contract_version !== 1 || !Number.isSafeInteger(claim.receipt_id)
        || claim.receipt_id < 1 || !/^\d{4}-\d{2}-\d{2}$/.test(claim.target_date)
        || typeof claim.paper_only !== "boolean" || claim.data_mode !== "live"
        || !UUID.test(claim.owner_id) || !Number.isFinite(Date.parse(claim.expires_at))
        || Date.parse(claim.expires_at) <= now()) {
        return reply(502, "invalid_dispatch_contract");
      }
    } catch {
      return reply(503, "ticket_service_unavailable");
    }
    let status = 0;
    let transportFailed = false;
    try {
      const dispatched = await fetchImpl(DISPATCH_URL, {
        method: "POST", headers: { "Content-Type": "application/json",
          Accept: "application/vnd.github+json", Authorization: `Bearer ${dispatchToken}`,
          "X-GitHub-Api-Version": "2022-11-28" },
        body: JSON.stringify({ ref: "main", inputs: { target_date: claim.target_date,
          execute_publication: "true", paper_only: String(claim.paper_only) } }),
        signal: AbortSignal.timeout(15000), redirect: "error",
      });
      status = dispatched.status;
    } catch {
      transportFailed = true;
    }
    try {
      const completed = await rpc("complete_paper_watchdog_dispatch_v1", {
        p_receipt_id: claim.receipt_id, p_http_status: status,
        p_transport_failed: transportFailed,
      });
      if (!completed.ok) return reply(503, "dispatch_receipt_unavailable");
      const receipt = await completed.json();
      if (receipt.contract_version !== 1 || receipt.receipt_id !== claim.receipt_id
        || typeof receipt.status !== "string") return reply(502, "invalid_dispatch_receipt");
      return reply(200, status === 204 ? "dispatch_accepted" : "dispatch_failed");
    } catch {
      return reply(503, "dispatch_receipt_unavailable");
    }
  };
}
