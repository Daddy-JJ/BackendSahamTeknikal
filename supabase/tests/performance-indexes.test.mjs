import assert from 'node:assert/strict';
import { test, before, after } from 'node:test';
import { database } from './helpers/paper-reporting-fixture.mjs';

let db;
before(async () => {
  db = await database();
});
after(async () => {
  await db?.close();
});

test('performance optimization indexes (migration 013) exist on target tables', async () => {
  const result = await db.query(`
    select tablename, indexname 
    from pg_indexes 
    where schemaname = 'public' 
      and indexname in (
        'idx_actual_notes_trade_id',
        'idx_actual_stop_events_trade_id',
        'idx_scan_runs_forward_lookup',
        'idx_paper_trades_reporting_composite'
      )
    order by indexname;
  `);

  const indexes = result.rows;
  assert.equal(indexes.length, 4, 'Expected all 4 performance indexes to be present');

  const map = Object.fromEntries(indexes.map(r => [r.indexname, r.tablename]));
  assert.equal(map.idx_actual_notes_trade_id, 'actual_notes');
  assert.equal(map.idx_actual_stop_events_trade_id, 'actual_stop_events');
  assert.equal(map.idx_scan_runs_forward_lookup, 'scan_runs');
  assert.equal(map.idx_paper_trades_reporting_composite, 'paper_trades');
});
