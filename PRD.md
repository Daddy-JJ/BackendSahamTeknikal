# Backend product scope

SahamTeknikal supports IDX end-of-day scanning and research, persistent paper
experiments, a separate owner actual journal, canonical reporting and immutable
chart views. The backend validates market inputs, computes deterministic indicators/
signals/fills/risk/statistics and serves versioned authenticated consumer contracts.
It owns source/revision provenance, owner auth/RLS, scheduling and cloud recovery.

[Local SOT snapshot](SOT.md) owns trading rules; [contracts](contracts/README.md)
own published interfaces. Frontend validates and formats official output. It does
not recalculate authoritative financial results. Paper and actual remain separate.

The shared workspace `PRD.md` owns full objectives/acceptance when available;
its absence does not prevent local orientation. Read relevant local rules/source
and the [retained product baseline](docs/archive/PRD_BEFORE_DOC_CLEANUP_20261015.md);
identify unavailable requirements rather than treating historical phases as work.
[PROJECT_CONTEXT](PROJECT_CONTEXT.md) records snapshot origin and synchronization.

[PLAN](PLAN.md) contains authorized active work. [Status](IMPLEMENTATION_STATUS.md)
contains dated proof/gaps; a released chart or presentation change does not establish
completion of every product backlog item. No backend behavior change is authorized
by this documentation cleanup.
