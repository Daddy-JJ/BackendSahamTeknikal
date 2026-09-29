# BackendSahamTeknikal

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

Engine empat strategi, exit paper, provider adapters, migrasi Supabase scan RPC, dan adapter persistence sudah ada dalam kode lokal. Migrasi scan foundation sudah ada di Supabase production dan development; uji fixture serta owner RLS/action berhasil di development. Migrasi revisi market 002-003 sudah diterapkan di development; smoke test simpan, baca ulang digest, dan replay dua revisi fixture berhasil. Orkestrator fetch -> ingest -> verifikasi baca ulang -> publish diuji lokal; belum ada CLI/runner GitHub aktif. Kalender/universe resmi, scanner scheduled live, persistence paper, jurnal actual, dan backup-restore masih gate pengembangan. Lihat DEVELOPMENT_ADDENDUM.md dan IMPLEMENTATION_STATUS.md pada checkout sumber kerja saat ini.

Rekonstruksi histori, handoff SQL development, dan batas rollout: lihat docs/MARKET_REVISIONS.md.
