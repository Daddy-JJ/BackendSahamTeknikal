# API/data contracts

Schema JSON berversi milik backend menjadi sumber kontrak signal dan snapshot. Frontend tidak menghitung ulang indikator atau metrik resmi.

- signal.schema.json: bentuk snapshot satu signal.
- demo-snapshot.schema.json: bentuk fixture UI sintetis.
- demo-snapshot.fixture.json: fixture yang engine test bandingkan secara deterministik.

Setelah mengubah engine atau schema, regenerate fixture dari scanner/:

```powershell
cd scanner
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ..\contracts\demo-snapshot.fixture.json
```

Snapshot untuk repo frontend dikeluarkan dari backend secara sadar lalu disalin ke frontend/src/generated/demo.json. Commit kedua sisi yang bersesuaian agar UI preview dan schema memiliki versi yang cocok. Jangan menaruh data live/provider response pada fixture ini.
