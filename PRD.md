# Backend product scope

[Workspace PRD](../PRD.md) owns product objectives and acceptance; [SOT](SOT.md) owns
trading rules. Read the relevant sections for the task, not every historical document.
This backend supplies scanner/market validation, persistent paper runtime, actual ledger,
canonical reporting, owner auth/RLS, cloud recovery and immutable chart artifacts.

PLAN.md contains active work; IMPLEMENTATION_STATUS.md contains dated evidence.
A completed chart release does not imply every original product backlog item is delivered.
No backend behavior change is needed for the current frontend50:50 relayout.

Standalone checkout: use local SOT/contracts/source and the
[retained product baseline](docs/archive/PRD_BEFORE_DOC_CLEANUP_20261015.md) as reference;
report inaccessible shared context rather than inventing a new requirement or starting old phases.
