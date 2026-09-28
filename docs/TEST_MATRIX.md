# Test matrix and remaining gates

| Risk / handoff ID | Test suite |
| --- | --- |
| T01-T04, T28 seed/indicator/pivot numerics | test_indicators_strategies |
| T05-T09 fractal available-at and lookahead | test_indicators_strategies, test_engine |
| T10-T13, T21 next-session/missing/gap/dual-hit/late | test_paper, test_engine |
| T14 in-memory + atomic scan/request idempotency | test_engine, test_paper, test_persistence, scan.test.mjs; multi-connection concurrency remains M2 |
| T15-T16 partial data/corporate action/immutable snapshot | test_engine, test_contracts_pipeline |
| T19 closed denominators/null/no-loss | test_paper |
| T25-T27 RS ties/barrier/prior20/reclaim | test_indicators_strategies, test_engine |
| T29 separate immutable experiments | test_paper |
| T30-T32 MA modes/next-open/stop priority/late | test_paper, test_ma_lifecycle |
| Provider dates, retries, safe errors, missing key | test_providers |
| T20 owner-only SQL permissions/RLS and spoofed IDs | scan.test.mjs on PGlite with simulated auth; remote JWT/API still pending |
| Persistence retry, origin/key safety, reload/pagination/prefix guards | test_persistence |
| Schema/reproducibility/current generated fixture | test_contracts_pipeline |
| UI fixture labels, filters, reference vs fill, command menu, actual separation | workspace.spec.ts: desktop/mobile/tablet |

Remaining: T17/T18 actual ledger/stop revision, T20 remote JWT/API RLS, T22 tag attribution,
T24 backup restore, T33 full experiment comparison. AI T23 remains disabled P1.
Source-rule tests are not evidence of profitability, live feed access, or TradingView parity.
