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
needed for any deliberate re-import. No 002 remote receipts were observed during
the preflight for this slice.

## Development SQL Editor

The owner selected manual SQL Editor application. Generate the ignored file:

    scanner/.venv/Scripts/python.exe supabase/scripts/prepare_dev_market_setup.py

Open backend/data/dev-market-revisions-vgmkpsestahkfahzdtae.sql and run its entire
contents once in project vgmkpsestahkfahzdtae. It applies 002+003 in one transaction,
requires fixture mode and the expected enabled owner, and refuses an existing
market schema. Verify the project URL yourself: the database-side guard checks
mode/owner, not Supabase's project reference. Expected final result:
revision_schema_ready=true, data_mode=fixture.

If the market schema already exists, stop and inspect its migration state.
Do not drop tables or rerun foundation 001. Manual SQL does not automatically
reconcile Supabase CLI migration history; that remains a deployment task.

After application, first run the read-only preflight, then the explicitly
authorized fixture proof:

    scanner/.venv/Scripts/python.exe supabase/scripts/smoke_dev_market_revisions.py
    scanner/.venv/Scripts/python.exe supabase/scripts/smoke_dev_market_revisions.py --execute

This script only accepts the allowlisted dev URL from ignored .env.development.
It writes two small, labeled synthetic revisions under dev_market_revision_m2
and verifies both originals plus replay. It never publishes trading signals.
Remote owner/outsider RLS verification remains separate from this service-key proof.

## Verification and rollout limits

Local PGlite tests cover timestamp/cutoff isolation, omitted sessions, empty data,
source mismatch, legacy rejection, owner/outsider/anonymous access, and a real
Python -> PostgreSQL -> Python digest round-trip. The SQL Editor wrapper itself
is tested against wrong mode, missing owner and duplicate application.
Python tests cover response corruption and blocking publication on read failure.

Deploy migration 003 before using the updated scanner adapter (002 alone is
insufficient). No production migration, GitHub schedule or live market proof is
implied by these local tests. Official calendar/universe and remaining M2 gates
are recorded in IMPLEMENTATION_STATUS.md.

## Remote development evidence - 2026-09-29

The owner applied the SQL Editor handoff successfully. Independent schema
preflight and the guarded --execute smoke passed on the allowlisted dev project:
two receipts, bar counts 3 and 2, four changed-bar rows, exact digest read-back
and replay verified. These checks used a backend service key. Remote JWT/RLS
checks for this new RPC, live provider inputs and production rollout remain open.
