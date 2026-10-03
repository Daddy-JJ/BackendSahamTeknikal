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
