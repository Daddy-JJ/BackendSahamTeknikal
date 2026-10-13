import assert from 'node:assert/strict';
import { test, before, after, beforeEach, afterEach } from 'node:test';
import { database, owner, outsider, role, init, trade, bookOf, commit, report } from './helpers/paper-reporting-fixture.mjs';

let db;
before(async () => {
  db = await database();
});
after(async () => {
  await db?.close();
});
beforeEach(async () => db.exec('begin'));
afterEach(async () => db.exec('rollback'));

test('optimized read_trade_reporting_v1 and reporting_trade_enrichment_v1 retain exact reporting semantics', async () => {
  const m = await init(db);
  const regularWin = await trade(db, m, { key: 'a', state: 'closed', exitPrice: 1150, exitDay: '2026-10-12' });
  const ambiguousTrade = await trade(db, m, { key: 'b', state: 'ambiguous_review', exitPrice: 925, alternate: 1150, exitDay: '2026-10-12' });
  const lateTrade = await trade(db, m, { key: 'c', state: 'closed', exitPrice: 1150, exitDay: '2026-10-12' });
  lateTrade.actionable = false;
  lateTrade.events.splice(1, 0, {
    session: '2026-10-09',
    kind: 'pending_exit',
    price: null,
    reason: 'late_model_only',
    observed_at: '2026-10-09T10:00:00Z',
    input_digest: 'c'.repeat(64),
  });

  await commit(db, bookOf(regularWin, ambiguousTrade, lateTrade), {}, 0, 'optimized-smoke', '2026-10-12');

  const r = await report(db, 'fixed2r');

  // Primary summary: regularWin counts as closed; ambiguous and late are excluded
  assert.equal(r.summary.closed, 1);
  assert.equal(r.summary.wins, 1);
  assert.equal(r.summary.losses, 0);

  // Exclusions: late_model_only and ambiguous_order tracked correctly
  assert.equal(r.exclusions.closed_excluded, 2);
  assert.equal(r.exclusions.reasons.late_model_only, 1);
  assert.equal(r.exclusions.reasons.ambiguous_order, 1);

  // Status counts
  assert.equal(r.statuses.closed, 2);
  assert.equal(r.statuses.ambiguous, 1);

  // Sensitivities: sl_first has 2 trades (regular win + ambiguous SL), tp_first has 2 trades (regular win + ambiguous TP)
  assert.equal(r.sensitivities.sl_first.closed, 2);
  assert.equal(r.sensitivities.tp_first.closed, 2);
  assert.equal(r.sensitivities.sl_first.wins, 1);
  assert.equal(r.sensitivities.sl_first.losses, 1);
  assert.equal(r.sensitivities.tp_first.wins, 2);
  assert.equal(r.sensitivities.tp_first.losses, 0);

  // Trades enrichment on returned page
  assert.equal(r.trades.length, 3);
  const winRow = r.trades.find(x => x.id === regularWin.id);
  assert.equal(winRow.metric_eligible, true);
  assert.equal(winRow.exclusion_reason, null);
  assert.equal(winRow.holding_sessions, 2); // 2026-10-09 (Fri) to 2026-10-12 (Mon) = 2 exchange sessions
  assert.equal(winRow.holding_calendar_days, 4); // Oct 9 to Oct 12 = 4 calendar days

  const lateRow = r.trades.find(x => x.id === lateTrade.id);
  assert.equal(lateRow.metric_eligible, false);
  assert.equal(lateRow.exclusion_reason, 'late_model_only');

  const ambRow = r.trades.find(x => x.id === ambiguousTrade.id);
  assert.equal(ambRow.metric_eligible, false);
  assert.equal(ambRow.exclusion_reason, 'ambiguous_order');

  // Verify access control
  await role(db, 'authenticated', outsider);
  await assert.rejects(
    async () => db.query('select public.read_trade_reporting_v1()'),
    e => e.code === '42501'
  );
});
