# Market revision reconstruction (M2)

Migration 002 introduces append-only series receipts and changed-bar rows.
Migration 003 adds an ordered session manifest and an owner-readable,
security-invoker read_market_series RPC. The read uses each receipt's cutoff,
not today's latest bars. An omitted date stays omitted; an empty provider
result stays empty. Replaying an older receipt keeps its original input.

The adapter stores canonical **normalized Series input**, not the provider's
original HTTP response. Original Python numeric tokens are retained as text
alongside JSONB on changed bars, with receipt metadata text. This preserves
float/int distinctions, scientific notation and negative zero through PostgreSQL.
It costs extra storage on changed bars; unchanged histories are not copied for
each receipt. Storage sizing against real provider histories is still pending.

SQL verifies the reconstructed snapshot/source consistency. Python reconstructs
the typed Series and verifies its SHA-256 engine input_digest against the
expected fetched input. The run orchestrator requires this read-back before
publishing any scan. A persistence/read-back failure aborts publication; earlier
successful immutable receipts can remain and are safe to retry.

Existing 002 receipts without source manifests are not guessed or rewritten.
Reading them fails with market_revision_manifest_missing; reusing their key for
003 ingestion fails with market_digest_conflict. An explicit new namespace is
needed for any deliberate re-import. The original M2 preflight observed no 002 remote
receipts for that slice; this historical observation is not a current database check.

## Setup and rollout evidence

[Status](../IMPLEMENTATION_STATUS.md) owns dated migration/release proof (001–016
at the 15 October cutoff); this cleanup made no remote check. Do not infer
current rollout from the earlier M2 setup notes or replay applied migrations.

[Original revision handoff](archive/MARKET_REVISIONS_BEFORE_HANDOVER_CLEANUP_20261021.md)
preserves guarded development generators, expected results, read-only/execute
separation, local/hosted service-key/JWT evidence and original limits. SQL Editor
application does not reconcile CLI history. A URL/checksum-format guard is not
independent certification of source authenticity or exchange hours.

For any newly authorized setup, inspect exact target/history/schema/mode/owner
first; never drop a present market schema, rerun foundation 001, change production
to fixture or guess missing legacy manifests. Use the [Supabase map](../supabase/README.md),
[scanner runbook](SCANNER_RUN.md) and [release readiness](PRODUCTION_READINESS.md).
Storage sizing against real provider histories retains its original pending
limit until separately measured; no test or sizing run occurred in this cleanup.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/MARKET_REVISIONS_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="development-sql-editor"></a>
<a id="verification-and-rollout-limits"></a>
<a id="remote-development-evidence---2026-09-29"></a>
