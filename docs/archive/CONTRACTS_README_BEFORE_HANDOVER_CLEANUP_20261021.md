# HISTORICAL / NOT AN ACTIVE TASK / NOT AUTHORIZATION

Archived 21 October 2026 during documentation-only handover cleanup.
Source: `contracts/README.md` at backend `719bc8c7f4deff2f945a0825cc92f6685cf48661`.
Source SHA-256 (original bytes): `feaca3046ba755ba3d29e40b7fc029a021d4b3261ed1288ba1f2f985490d1c94`.
Source dates and proof boundaries remain those stated in the body. Earlier pending,
NO-GO, approval and execution language is historical and authorizes no new action.
Superseded for navigation by [current document](../../contracts/README.md)
and [dated status](../../IMPLEMENTATION_STATUS.md); archiving does not resolve gaps.
Only this wrapper and relative Markdown link rebasing alter the retained original.

---

# API/data contracts

Schema JSON berversi milik backend menjadi sumber kontrak signal dan snapshot. Frontend tidak menghitung ulang indikator atau metrik resmi.

- signal.schema.json: bentuk snapshot satu signal.
- demo-snapshot.schema.json: bentuk fixture UI sintetis.
- demo-snapshot.fixture.json: fixture yang engine test bandingkan secara deterministik.
- actual-journal-export.mjs: kontrak header CSV actual dan serializer tanpa
  perhitungan finansial. Input berasal dari RPC export_actual_journal dengan
  decimal strings, mode/data_mode, revision, dan fee_quality. Detail filter,
  pagination dan handoff UI: [ACTUAL_JOURNAL.md](../ACTUAL_JOURNAL.md).

Setelah mengubah engine atau schema, regenerate fixture dari scanner/:

```powershell
cd scanner
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ..\contracts\demo-snapshot.fixture.json
```

Snapshot untuk repo frontend dikeluarkan dari backend secara sadar lalu disalin ke frontend/src/generated/demo.json. Commit kedua sisi yang bersesuaian agar UI preview dan schema memiliki versi yang cocok. Jangan menaruh data live/provider response pada fixture ini.
