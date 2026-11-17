# Backend contract registry

Backend owns versioned engine schemas and canonical ledger/reporting/chart output.
Frontend validates/parses/formats that output; it does not rebuild official financial
math or silently substitute fixtures. This registry is a reference, not an implementation queue.

| Contract/source | Owner and consumer boundary |
| --- | --- |
| [signal.schema.json](signal.schema.json) | backend signal shape; temporal/source/strategy semantics remain in SOT/source |
| [demo-snapshot.schema.json](demo-snapshot.schema.json), [synthetic demo fixture](demo-snapshot.fixture.json) | explicit UI preview/test data; never live/provider responses |
| [Actual journal](../docs/ACTUAL_JOURNAL.md) | owner-only mutation/revision/replay, ledger/analytics and decimal-string export |
| [actual-journal-export.mjs](actual-journal-export.mjs) | ordered CSV header/serializer only; consumes canonical RPC values without financial arithmetic |
| [Signal action conflict](../docs/SIGNAL_ACTION_CONFLICT.md) | PT412/HTTP412 vs idempotency conflict; same-intent retry vs new intent |
| [Market revisions](../docs/MARKET_REVISIONS.md) | immutable normalized inputs, manifests, digest read-back and provenance |
| [Recovery V1](../docs/INCIDENT_RECOVERY_CONTRACT_V1.md) | source/lease fencing, processing health, private watchdog ticket/dispatch |
| [SQL 008](../supabase/migrations/202610040008_canonical_analytics_and_paper.sql), [009](../supabase/migrations/202610080009_persistent_paper_reporting.sql), [010](../supabase/migrations/202610080010_reporting_scanner_coverage.sql) | canonical analytics, persistent paper/reporting and explicit scanner coverage |
| [SQL 011](../supabase/migrations/202610100011_paper_integrity_and_processing_health.sql), [012](../supabase/migrations/202610130012_processing_recovery_watchdog.sql) | paper integrity, processing state and recovery RPC additions |
| [ticker-chart-v1.md](ticker-chart-v1.md), [checksum](ticker-chart-v1.sha256) | root-owned versioned chart protocol; local synchronized snapshot, immutable artifacts and owner reader |
| [SQL 015](../supabase/migrations/202610140015_ticker_chart_artifacts.sql), [016](../supabase/migrations/202610140016_chart_reader_budgets.sql) | chart RPC/grants/budgets; source signature is implementation evidence |

## Change and synchronization protocol

Identify current/proposed contract, named arguments, frontend impact, versioning,
compatibility, rollout order and tests before material changes; obtain the required
scope approval. Deploy a needed backend capability before its compatible consumer.
Do not simplify an API by silently changing consumer semantics.

For an authorized schema/engine fixture change, regenerate the synthetic demo from
backend and review the resulting diff:

```powershell
cd scanner
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ..\contracts\demo-snapshot.fixture.json
```

Coordinate the matching frontend `src/generated/demo.json` and contract/serializer
copies through the independent repo handoff. Record source/version/hash and delivery
ref in both scopes; do not commit/push either repo without authorization.
Shared SOT/chart copies remain snapshots of the workspace canonical documents.
Compare available bytes/checksums without rewriting the protocol/checksum for cleanup;
if a source or sibling is unavailable, record sync pending and its missing ref.
Equal hashes prove available-snapshot agreement, not unavailable-root freshness.
[PROJECT_CONTEXT](../PROJECT_CONTEXT.md) owns the portable snapshot metadata.

<!-- Compatibility anchors for consolidated historical sections. Original content is in ../docs/archive/CONTRACTS_README_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="apidata-contracts"></a>
