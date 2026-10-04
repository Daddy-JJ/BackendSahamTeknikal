import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { before, after, beforeEach, afterEach, test } from "node:test";
import { readFileSync } from "node:fs";

const owner = "11111111-1111-4111-8111-111111111111";
const outsider = "22222222-2222-4222-8222-222222222222";
const otherOwner = "33333333-3333-4333-8333-333333333333";
const db = new PGlite();
const sql = (query, args = []) => db.query(query, args);

async function role(name, uid = "") {
  await db.exec("set local role " + name);
  await sql("select set_config('request.jwt.claim.sub',$1,true)", [uid]);
}

async function denied(fn, code) {
  await db.exec("savepoint expected_failure");
  await assert.rejects(fn, e => { assert.equal(e.code, code); return true; });
  await db.exec("rollback to savepoint expected_failure");
}

const apply = (action, trade, payload, requestId = crypto.randomUUID()) =>
  sql("select public.apply_actual_journal($1,$2,$3::jsonb,$4) as result",
    [action, trade, JSON.stringify(payload), requestId]).then(r => r.rows[0].result);

const baseTrade = (strategy = "MACD_EMA200_V1") => ({
  ticker: "TEST",
  primary_strategy: strategy,
  initial_stop: 95,
  exit_policy_snapshot: { version: "fixed2r-v1", mode: "fixed_rr", target_r: 2 },
});

const fill = (side, quantity, price_idr, fee_idr, expected_revision, day) => ({
  side, quantity, price_idr, fee_idr, fee_status: "actual",
  filled_at: day, expected_revision,
});

before(async () => {
  await db.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
    $$;
    grant usage on schema auth, public to anon,authenticated,service_role;
    grant execute on function auth.uid() to anon,authenticated,service_role;
  `);
  for (const name of [
    "202609290001_scan_foundation.sql",
    "202609290004_publication_deadline.sql",
    "202609290005_actual_journal.sql",
    "202609300006_actual_journal_conflict_http.sql",
    "202610010007_signal_action_conflict_http.sql",
    "202610040008_canonical_analytics_and_paper.sql"
  ]) {
    await db.exec(readFileSync(new URL("../migrations/" + name, import.meta.url), "utf8"));
  }
  await sql("insert into auth.users values ($1),($2),($3)", [owner, outsider, otherOwner]);
  await sql("insert into public.app_members(user_id) values ($1),($2)", [owner, otherOwner]);
});

beforeEach(async () => { await db.exec("begin"); });
afterEach(async () => { await db.exec("rollback"); });
after(async () => { await db.close(); });

test("actual_journal_r_curve returns empty points and zero summary on empty cohort", async () => {
  await role("authenticated", owner);
  const res = (await sql("select public.actual_journal_r_curve() as curve")).rows[0].curve;
  assert.equal(res.mode, "actual");
  assert.equal(res.total_closed, 0);
  assert.equal(res.final_cumulative_r, 0);
  assert.equal(res.max_drawdown_r, 0);
  assert.deepEqual(res.points, []);
});

test("actual_journal_r_curve computes chronological points, cumulative R, and max drawdown with exact parity", async () => {
  await role("authenticated", owner);

  // Trade 1: Buy @ 100, Stop @ 95 (risk = 5), Sell @ 110 (+2R, PnL = +10)
  const t1 = (await apply("create", null, baseTrade("MACD_EMA200_V1"))).trade_id;
  await apply("fill", t1, fill("buy", 1, 100, 0, 1, "2026-09-01T03:00:00Z"));
  await apply("fill", t1, fill("sell", 1, 110, 0, 2, "2026-09-02T03:00:00Z"));

  // Trade 2: Buy @ 100, Stop @ 95 (risk = 5), Sell @ 95 (-1R, PnL = -5)
  const t2 = (await apply("create", null, baseTrade("FRACTAL_BREAKOUT_V1"))).trade_id;
  await apply("fill", t2, fill("buy", 1, 100, 0, 1, "2026-09-02T03:00:00Z"));
  await apply("fill", t2, fill("sell", 1, 95, 0, 2, "2026-09-03T03:00:00Z"));

  // Trade 3: Buy @ 100, Stop @ 95 (risk = 5), Sell @ 110 (+2R, PnL = +10)
  const t3 = (await apply("create", null, baseTrade("RS_BREAKOUT_V1"))).trade_id;
  await apply("fill", t3, fill("buy", 1, 100, 0, 1, "2026-09-03T03:00:00Z"));
  await apply("fill", t3, fill("sell", 1, 110, 0, 2, "2026-09-04T03:00:00Z"));

  const curve = (await sql("select public.actual_journal_r_curve() as curve")).rows[0].curve;
  assert.equal(curve.total_closed, 3);
  assert.equal(curve.final_cumulative_r, 3); // 2 - 1 + 2 = 3 R
  assert.equal(curve.max_drawdown_r, 1);    // peak was 2, dropped to 1 -> dd = 1 R

  assert.equal(curve.points.length, 3);
  assert.equal(curve.points[0].trade_id, t1);
  assert.equal(curve.points[0].sequence, 1);
  assert.equal(curve.points[0].cumulative_r, 2);
  assert.equal(curve.points[0].drawdown_r, 0);

  assert.equal(curve.points[1].trade_id, t2);
  assert.equal(curve.points[1].sequence, 2);
  assert.equal(curve.points[1].cumulative_r, 1);
  assert.equal(curve.points[1].drawdown_r, 1);

  assert.equal(curve.points[2].trade_id, t3);
  assert.equal(curve.points[2].sequence, 3);
  assert.equal(curve.points[2].cumulative_r, 3);
  assert.equal(curve.points[2].drawdown_r, 0);

  // Parity check against actual_journal_analytics
  const analytics = (await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(analytics.closed, curve.total_closed);
  assert.equal(Number(analytics.net_pnl_idr), Number(curve.points.at(-1).cumulative_pnl_idr));
});

test("actual_journal_attribution returns strategy breakdown matching aggregate analytics exactly", async () => {
  await role("authenticated", owner);

  // Trade 1: MACD win (+10)
  const t1 = (await apply("create", null, baseTrade("MACD_EMA200_V1"))).trade_id;
  await apply("fill", t1, fill("buy", 1, 100, 0, 1, "2026-09-01T03:00:00Z"));
  await apply("fill", t1, fill("sell", 1, 110, 0, 2, "2026-09-02T03:00:00Z"));

  // Trade 2: FRACTAL loss (-5)
  const t2 = (await apply("create", null, baseTrade("FRACTAL_BREAKOUT_V1"))).trade_id;
  await apply("fill", t2, fill("buy", 1, 100, 0, 1, "2026-09-02T03:00:00Z"));
  await apply("fill", t2, fill("sell", 1, 95, 0, 2, "2026-09-03T03:00:00Z"));

  // Trade 3: MACD win (+20)
  const t3 = (await apply("create", null, baseTrade("MACD_EMA200_V1"))).trade_id;
  await apply("fill", t3, fill("buy", 1, 100, 0, 1, "2026-09-03T03:00:00Z"));
  await apply("fill", t3, fill("sell", 1, 120, 0, 2, "2026-09-04T03:00:00Z"));

  const attr = (await sql("select public.actual_journal_attribution() as a")).rows[0].a;
  assert.equal(attr.strategies.length, 2);

  const macd = attr.strategies.find(s => s.strategy === "MACD_EMA200_V1");
  assert.ok(macd);
  assert.equal(macd.closed, 2);
  assert.equal(macd.wins, 2);
  assert.equal(macd.losses, 0);
  assert.equal(Number(macd.net_pnl_idr), 30);
  assert.equal(macd.profit_factor_status, "no_losses");

  const fractal = attr.strategies.find(s => s.strategy === "FRACTAL_BREAKOUT_V1");
  assert.ok(fractal);
  assert.equal(fractal.closed, 1);
  assert.equal(fractal.wins, 0);
  assert.equal(fractal.losses, 1);
  assert.equal(Number(fractal.net_pnl_idr), -5);

  // Parity check against actual_journal_analytics
  const analytics = (await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  const totalNetPnl = attr.strategies.reduce((acc, s) => acc + Number(s.net_pnl_idr), 0);
  assert.equal(totalNetPnl, Number(analytics.net_pnl_idr));
  const totalWins = attr.strategies.reduce((acc, s) => acc + s.wins, 0);
  assert.equal(totalWins, analytics.wins);
  const totalLosses = attr.strategies.reduce((acc, s) => acc + s.losses, 0);
  assert.equal(totalLosses, analytics.losses);
});

test("paper_trades table enforces owner isolation and read_paper_journal RPC functions cleanly", async () => {
  // Service role inserts paper trades
  await role("service_role");
  await sql(`
    insert into public.paper_trades (
      id, owner_id, data_mode, ticker, strategy, experiment_id, exit_mode, state,
      reason, entry_session, entry_price, initial_stop, current_stop, target_price,
      exit_session, exit_price, exit_reason, realized_r, initial_risk_idr
    ) values
    ('paper-1', $1, 'live', 'BBCA', 'MACD_EMA200_V1', 'baseline-MACD', 'fixed_rr', 'closed',
     'target_reached', '2026-09-01', 9000, 8500, 8500, 10000, '2026-09-05', 10000, 'target', 2.0, 500000),
    ('paper-2', $1, 'live', 'BMRI', 'FRACTAL_BREAKOUT_V1', 'baseline-FRACTAL', 'fixed_rr', 'open',
     'pending_exit', '2026-09-03', 6000, 5700, 5700, 6600, null, null, null, null, 300000),
    ('paper-3', $2, 'live', 'TLKM', 'RS_BREAKOUT_V1', 'baseline-RS', 'fixed_rr', 'closed',
     'stop_reached', '2026-09-02', 3000, 2800, 2800, 3400, '2026-09-04', 2800, 'stop', -1.0, 200000)
  `, [owner, otherOwner]);

  // Owner reads paper journal
  await role("authenticated", owner);
  const paper = (await sql("select public.read_paper_journal() as p")).rows[0].p;
  assert.equal(paper.mode, "paper");
  assert.equal(paper.trades_count, 2);
  assert.equal(paper.closed_count, 1);
  assert.equal(paper.open_count, 1);
  assert.equal(paper.wins, 1);
  assert.equal(paper.losses, 0);
  assert.equal(paper.expectancy_r, 2);
  assert.equal(paper.trades.length, 2);
  assert.ok(paper.trades.every(t => t.ticker === "BBCA" || t.ticker === "BMRI"));

  // Invariant #7: paper trades must NOT contaminate actual journal
  const actual = (await sql("select public.actual_journal_analytics() as a")).rows[0].a;
  assert.equal(actual.closed, 0);
  assert.equal(actual.open, 0);

  // Outsider is denied
  await role("authenticated", outsider);
  await denied(() => sql("select public.read_paper_journal()"), "42501");
  assert.equal((await sql("select count(*)::int n from public.paper_trades")).rows[0].n, 0);

  // Other owner sees only their own paper trade
  await role("authenticated", otherOwner);
  const otherPaper = (await sql("select public.read_paper_journal() as p")).rows[0].p;
  assert.equal(otherPaper.trades_count, 1);
  assert.equal(otherPaper.trades[0].ticker, "TLKM");
});
