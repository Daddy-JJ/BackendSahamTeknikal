## Authorized production release in progress - 2026-10-10 WIB

Action: user authorized commit/push and deployment of the locally verified G01-G17 remediation. Recheck both main branches, pause scanner during a fresh encrypted capture, fully restore/rehearse SQL011, apply backend capability first, commit/push both repos, verify exact-SHA Vercel Production, resume and recover the committed Oct8 paper cohort through Oct9 without publishing historical signals.
Proof: GitHub fetch shows both main branches match origin. Read-only production preflight confirms SQL001-010, live mode/valid owner, no duplicate economics, checkpoint Oct8/revision1, eight pending plans/four evaluations/zero events. Scanner workflow paused with no active job. All prior local checks are retained below; backup/migration/deployment/recovery are not yet claimed complete.

Release receipts: backend/data/production-release-evidence/sql011-release-20261010 (private ignored diagnostics); durable shared handoff: docs/REMEDIATION_RELEASE_20261010.md. No trading rule, provider, activation or actual ledger change is authorized by this rollout. Earlier local/historical evidence follows.

## Incident repair - implemented and verified locally (2026-10-10)

Approved G01-G17 remediation is implemented across both independent repositories. SQL011 adds economic/evaluation integrity, immutable job health, reporting eligibility and IDR/holding/paired metrics; frontend shares canonical exit filters and displays checkpoint/held-data/read errors honestly. Entry/exit rules, actual ledger/CSV and historical activation/config/book are preserved. See [PLAN.md](PLAN.md) for local proof and release gates. Commit/push, migration, deployment and production recovery remain pending separate release authorization; the current production incident has not been recovered by this local work.

# OHLC integrity and reporting coverage follow-up - 2026-10-08

Approved clarification: for the pinned Yahoo Finance baseline with `auto_adjust=False`, known cash-dividend amounts are audit metadata, not a price-quality eligibility gate. Policy `cash_dividend_metadata_nonblocking_v1` records new/mismatched dividends honestly as unreviewed without changing OHLC or crediting cash. Exact reviewed split approvals survive unrelated dividend mismatches. Missing/invalid/stale/gapped price data, unknown action coverage, unresolved splits and unsupported action types remain blocking. Prior signal snapshots and frozen paper configuration/risk remain immutable.

Forward SQL010 adds `scanner_coverage` to paper and signal-evaluation reporting independently of existing journal/observation `coverage_status`; actual reporting returns null scanner coverage. It preserves reader signatures, financial math, owner checks and grants. Deploy the additive migration before the compatible frontend to expose scanner coverage; SQL009-compatible frontend reads explicitly report metadata unavailable until010 exists.

Local evidence: Python343 PASS/5 native skips in full run, focused cash-policy19 PASS including paper/research shared gating and initial-risk preservation; sequential native backup/rehearsal12 PASS; SQL/PGlite98 PASS; Ruff PASS. Read-only evaluation of100 persisted8-Oct series yields100 valid with all OHLC unchanged; this is not a new production scan/publication. Production SQL010 applied and verified2026-10-09 WIB after fresh encrypted backup/full isolated restore; catalog matches rehearsal and all actual/paper/publication rows are unchanged. Hosted read-only owner reports pass strict frontend parsers; outsider/anon SQL-role claims are denied. Fresh released-source scan and Vercel deployment are the next gates, recorded in shared release documents. Current source candidates do not change provider, fees, entry/exit rules or actual ledger.

Earlier dated operational history follows; latest root IMPLEMENTATION_STATUS/CODEX_HANDOFF owns the release status.

---

# BackendSahamTeknikal

Latest finalization2026-10-03: owner production read and anonymous denials PASS;
manual full100 GitHub fetch/evaluation PASS with partial45/100 coverage after
verified archived-source hydration. Mandatory hosted mutation/access/publisher
gates remain BLOCKED; full-stack NO-GO, scheduler off. See
[finalization report](docs/BACKEND_FINALIZATION_REPORT_20261003.md).

Latest scanner evidence (2026-10-03): production partial coverage 45/100, but fresh
Yahoo target candles failed for 100/100. Scheduler/full-stack go-live remain NO-GO.
See [recovery report](docs/SCANNER_RECOVERY_REPORT_20261003.md) and
[frontend handoff](docs/FRONTEND_DEPLOYMENT_HANDOFF.md).

Latest2026-10-02: first production forward/live diagnostic is published with
100 actual market revisions, failed quality coverage0/100,100 holds and0 signals.
Full Yahoo mappings/fetch100 passed; known runtime calendar preflight and manual
GitHub five-symbol provider smoke passed. Scheduler stays disabled; quality and
full-stack readiness remain NO-GO. See docs/SCANNER_LIVE_READINESS.md and latest
IMPLEMENTATION_STATUS for evidence and frontend read-adapter handoff.

Scanner dan data layer untuk IDX Night Scanner. Repository ini menjadi sumber backend: strategi, kalkulasi indikator, provider yfinance/EODHD, kontrak data, migrasi Supabase, serta tes.

## Lokal

Lihat DEVELOPMENT.md untuk perintah Windows PowerShell. Runtime Python 3.12.14 dipin di scanner/.python-version; dependency scanner dikunci dengan uv.lock. Tes SQL memakai PostgreSQL PGlite di memori, jadi tidak menghubungi Supabase.

## Struktur

- scanner/: engine deterministik, adapter sumber data, paper evaluator, persistence adapter, dan tes.
- config/ dan fixtures/: kalender/universe sintetis untuk development.
- contracts/: JSON Schema signal/snapshot dan fixture hasil engine yang frontend gunakan.
- supabase/migrations/: migration SQL versioned; supabase/tests/: akses/RLS/atomicity tests.
- SOT.md: aturan trading canonical. TECHNICAL_DOC.md: kontrak arsitektur dan data.

Backend dan frontend merupakan repository GitHub terpisah. Repo frontend: https://github.com/Daddy-JJ/FrontEndSahamTeknikal. Vercel menggunakan repository frontend; GitHub Actions nantinya menjalankan scanner backend setelah workflow dan secrets dikonfigurasi.

Data demo ditandai fixture dan sintetis. Jangan commit file .env, key, database password, atau respons provider live. data/ diabaikan Git.

## Status batasan

Engine empat strategi, exit paper, provider adapters, migrasi Supabase scan RPC, dan adapter persistence sudah ada dalam kode lokal. Migrasi scan foundation sudah ada di Supabase production dan development; uji fixture serta owner RLS/action berhasil di development. Migrasi revisi market 002-003 sudah diterapkan di development; smoke test simpan, baca ulang digest, dan replay dua revisi fixture berhasil. Orkestrator fetch -> ingest -> verifikasi baca ulang -> publish diuji lokal; CLI manual dengan preflight tersedia; belum ada eksekusi live atau runner GitHub aktif. Kalender/universe resmi, scanner scheduled live, persistence paper, jurnal actual, dan backup-restore masih gate pengembangan. Lihat DEVELOPMENT_ADDENDUM.md dan IMPLEMENTATION_STATUS.md pada checkout sumber kerja saat ini.

Rekonstruksi histori, handoff SQL development, dan batas rollout: lihat docs/MARKET_REVISIONS.md.

CLI scanner manual dan gate live: docs/SCANNER_RUN.md.

M4 actual ledger, analytics, dan kontrak CSV tersedia pada migration 005, yang
sudah diterapkan dan diuji terbatas di Supabase development mode fixture.
Migration 006 memperbaiki stale-revision RPC timeout di development. Production sudah menerima migrations001–007 melalui CLI pada2026-10-02;
smoke mutasi production tetap belum lulus; retest HTTP412 owner JWT dua tab telah lulus menurut
audit frontend2026-10-01. Bukti dan
kontrak UI: [docs/ACTUAL_JOURNAL.md](docs/ACTUAL_JOURNAL.md).

Persiapan production berstatus **NO-GO**, dengan preflight read-only, daftar
migrasi, backup/rollback, env dan smoke checklist di
[PRODUCTION_READINESS](docs/PRODUCTION_READINESS.md). Prompt untuk chat frontend:
[FRONTEND_DEPLOYMENT_HANDOFF](docs/FRONTEND_DEPLOYMENT_HANDOFF.md).

## Jurnal otomatis v1 - 2026-10-08

Implementasi lokal mencakup paper persisten Supabase, dashboard IDR paper/aktual dan evaluasi sinyal independen. Model baru memakai close sinyal sebagai fill pada sesi berikutnya, batas risiko Rp1 juta termasuk fee, Fixed 2R dan SMA10 terpisah. Evaluasi 5/10 sesi tidak menutup posisi. Lihat [SOT](SOT.md), [kontrak teknis](TECHNICAL_DOC.md) dan [status bukti](IMPLEMENTATION_STATUS.md).

Rollout memerlukan migrasi forward `202610080009_persistent_paper_reporting.sql` sebelum frontend, lalu aktivasi/runner baru. Workflow membutuhkan `APP_OWNER_USER_ID` (owner aktif) dan konfigurasi server Supabase yang ada. JSON lokal hanya diagnostik dry-run legacy. Commit/push source candidate di branch `feat/persistent-paper-reporting-v1` telah diotorisasi pada 2026-10-08. Migrasi remote, aktivasi dan deploy production tetap merupakan tahap terpisah yang belum dilakukan.
