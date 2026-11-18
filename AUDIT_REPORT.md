# AUDIT_REPORT — CareLoop (Closing the Screening-to-Care Loop)

- Tanggal audit: 2026-11-13
- Cakupan: seluruh isi `APP/` (Python API, canonical ledger, simulator, skrip, tests, frontend React/Vite, Dockerfile, dokumentasi)
- Mode: READ-ONLY sampai laporan ini selesai. Perbaikan dilakukan setelah laporan (lihat bagian akhir).
- Lingkungan verifikasi: Windows, Python 3.13.7, Node 24.21.0, npm 11.19.0, FastAPI 0.141.1, Uvicorn 0.52.3, PyYAML 6.0.3.
  Proyek mem-pin Python 3.11.9 (`.python-version`) dan Node 20 (`web/.nvmrc`); kedua versi pin tersebut tidak tersedia di mesin audit, sehingga verifikasi dilakukan pada versi di atas.
- Metode: pembacaan kode penuh, eksekusi test suite, build frontend, run simulator, run API (FastAPI dan WSGI fallback), serta probe perilaku terarah untuk setiap dugaan temuan.

> Catatan: nomor baris mengacu pada kondisi file saat audit. Perbaikan setelah laporan dapat menggeser nomor baris.

---

## 1. Ringkasan Eksekutif

Aplikasi adalah prototipe offline yang tertata: domain ledger E1–E9 terpusat, service SQLite, simulator deterministik, 41 test Python, dan frontend React yang dapat di-build. Fondasi arsitekturnya jelas dan dokumentasinya jujur soal keterbatasan (bukan produk klinis).

Namun, terdapat beberapa masalah yang berdampak nyata:

1. **Integritas ledger rusak untuk event yang ditolak** — `CareLoopLedger.record_event` menambahkan event ke ledger *sebelum* memvalidasi urutan stage, sehingga event ilegal tetap tersimpan permanen (F-001).
2. **Alur utama "Close the loop" di UI tidak pernah berhasil** — frontend tidak mengirim `closure_code`, sementara backend mewajibkannya; API membalas 500 (F-002).
3. **Transport ledger `/loops` tidak persisten** — loop, event, dan closure yang dibuat via `/loops` hilang setelah restart, meski aplikasi dipromosikan sebagai "SQLite-backed" (F-004).
4. **WSGI fallback (mode tanpa FastAPI) mengabaikan query string dan gagal preflight CORS** — filter status/actor tidak bekerja dan data yang dikembalikan bisa salah (F-006).
5. **Angka Simulation Lab di UI tidak konsisten dengan artefak yang dihasilkan** dan merujuk file `out/v2-bounded.json` yang tidak ada (F-007).

**Skor kesehatan: 5/10**

| Aspek | Skor | Alasan singkat |
|---|---:|---|
| Build & run | 8/10 | Test, build web, simulator, API berjalan; Docker belum diverifikasi |
| Correctness | 4/10 | Kontrak frontend/backend putus, ledger menerima event ilegal, state tidak atomik |
| Security | 5/10 | Tidak ada autentikasi nyata (didokumentasikan), CORS longgar di fallback, ada kebocoran pesan internal |
| Performance & skalabilitas | 4/10 | `GET /cases` N+1 (122 query untuk 12 kasus) dan payload penuh tanpa paginasi |
| Maintainability | 6/10 | Struktur baik, test ada, tetapi ada kode mati, artefak build ter-commit, dan gap test kontrak |

---

## 2. Hasil Build / Run / Test

| # | Perintah / aksi | Hasil | Catatan |
|---|---|---|---|
| 1 | `PYTHONPATH=. python -B -m unittest discover -s tests -p "test_*.py"` | **LULUS** — 41 test, 32,9 detik | Dijalankan di Python 3.13.7, bukan 3.11.9 |
| 2 | `python -m careloop.simulator --cohort-size 100 --runs 2 --seed 20261019 --json ... --csv ...` | **LULUS** — exit 0 | 6 arm; `B-full closure_rate = 0.57` |
| 3 | `python -m api --host 127.0.0.1 --port 8765` (FastAPI terpasang) | **BERJALAN** | `GET /health` → 200; `OPTIONS` → 200 (CORS middleware) |
| 4 | `npm test` (`tsc -b`) di `web/` | **LULUS** | Hanya type-check; tidak ada unit test frontend |
| 5 | `npm run build` di `web/` | **LULUS** — 30 modul, JS 221,52 kB (gzip 68,03 kB) | `dist/` ditulis (artefak build) |
| 6 | Docker build / run | **TIDAK DIJALANKAN** | Membutuhkan pull image & jaringan; lihat F-008 untuk cacat konfigurasi yang terbaca dari file |
| 7 | Linter / formatter | **TIDAK ADA** | Tidak ada ESLint, Ruff, mypy, atau pyproject; hanya `tsc` |
| 8 | `npm audit` | **TIDAK DIJALANKAN** | Membutuhkan registry/jaringan |

Probe perilaku tambahan (semua terverifikasi):

| Probe | Hasil |
|---|---|
| `POST /cases/.../actions` `{"action":"close","payload":{"evidence_id":...}}` (payload yang dikirim UI) | **500** `closure requires a typed closure code` |
| `POST /loops` dua kali dengan `loop_id` sama | **500** (bukan 409) |
| `POST /demo/scenario` kedua kali | **400** `case is already closed` |
| `GET /cases?status=notification` via WSGI | 200 tetapi **12 kasus**, filter diabaikan |
| `GET /cases?actor_id=patient-01` via WSGI tanpa header | 200, **12 kasus** (default `navigator-1`, bukan `patient-01`) |
| `OPTIONS /cases` via WSGI | **404** (preflight gagal) |
| `POST /demo/seed` dengan body JSON rusak via FastAPI | **500 Internal Server Error** |
| Transport loop setelah `close_service` + reopen DB | **404** (loop hilang) |
| `create_case(..., stage="notification")` | Error, tetapi ledger menyisakan 1 loop yatim (12 → 13) |
| `record_event(loop, "E8")` saat stage `result_issued` | Ditolak, tetapi `events(loop)` tetap bertambah 0 → 1 |
| Handoff / escalate / appointment pada kasus `closed` | **Diizinkan** |
| `GET /cases` (12 kasus) | **122 statement SQL**; detail satu kasus = 8 query |

---

## 3. Daftar Temuan

Diurutkan dari severity tertinggi. Format: ID — Severity — Kategori — Lokasi.

### F-001 — Critical — Bug (integritas data) — `careloop/loop_engine/ledger.py:576-582`

**Deskripsi.** `record_event` membuat `LoopEvent`, menambahkannya ke `self._events`, lalu baru memvalidasi bahwa `event_type` sesuai stage saat ini. Jika validasi gagal, exception dilempar tetapi event sudah tersimpan. Ledger yang diklaim *append-only* dan menjadi sumber kebenaran menjadi tercemar oleh event yang ditolak; stage tidak berubah, sehingga event tersebut tidak dapat direkonsiliasi.

**Bukti.** Kode:
```python
event = LoopEvent(loop_id, event_type, _aware(timestamp or self._now()), ...)
self._events.append(event)                      # <-- ditambahkan lebih dulu
mapping = ELEVEN_STAGE_MAPPING[next(...)]
if event_type != mapping.expected_event_type:
    raise ValidationError(f"{loop.stage} requires ...")   # event sudah tersimpan
```
Hasil probe: `events before: 0` → panggilan `record_event("E8")` ditolak → `events after rejected call: 1 ['E8']`.

**Dampak.** Audit trail tidak dapat dipercaya; laporan absence/visibility dan rekonsiliasi partner dapat membaca event yang seharusnya tidak pernah ada. Ini melanggar invarian inti proyek.

**Rekomendasi.** Validasi sebelum append. Susun event, tentukan mapping, cek tipe, baru `self._events.append(event)`. Tambahkan test regresi yang menegaskan jumlah event tidak berubah setelah penolakan.

**Estimasi.** S

---

### F-002 — Critical — Bug (kontrak frontend/backend) — `web/src/App.tsx:138-139`, `api/service.py:484-485`

**Deskripsi.** UI mengirim aksi `close` hanya dengan `evidence_id`:
```tsx
await careLoopApi.action(activeCaseId, 'clinician-1', 'close', { evidence_id: evidence.id })
```
Backend mewajibkan closure code bertipe:
```python
if closure_code is None:
    raise ClosureError("closure requires a typed closure code")
```
Akibatnya tombol "Close the loop" **selalu gagal**. UI menangkap error, menampilkan "API action unavailable", lalu tetap memajukan state lokal ke `closed` — sehingga demo tampak berhasil padahal backend tidak menutup apa pun.

**Dampak.** Alur inti (screening → eskalasi → handoff → penutupan berbukti) tidak berfungsi end-to-end; UI memberi kesan sukses palsu. Ini juga menutupi temuan F-003.

**Rekomendasi.** Kirim `closure_code: 'Completed'` (dan `authorization_id`/`authorized_by`/`rationale` untuk kasus `high_risk`). Perbaiki juga penanganan error agar state UI tidak maju saat sinkronisasi gagal.

**Estimasi.** S

---

### F-003 — High — Bug (HTTP semantics / observability) — `api/app.py:47-54`

**Deskripsi.** `_error_status` hanya memetakan `AuthorizationError`, `NotFoundError`, dan `ValidationError`. `ClosureError`, `DuplicateEntityError`, dan `CareLoopError` lain jatuh ke 500. Probe: duplicate `/loops` → 500; closure tanpa kode → 500.

**Dampak.** Kesalahan klien dilaporkan sebagai kesalahan server; monitoring/alert menjadi bising; klien tidak bisa membedakan 400/409. Menyulitkan debugging dan menyesatkan UI.

**Rekomendasi.** Tambahkan pemetaan eksplisit:
```python
if isinstance(error, (ValidationError, ClosureError)):
    return 400
if isinstance(error, DuplicateEntityError):
    return 409
```
(atau ClosureError → 409 bila dianggap konflik state). Tambahkan test HTTP untuk tiap tipe error.

**Estimasi.** S

---

### F-004 — High — Bug (durabilitas) — `api/service.py:613-636`, `api/service.py:148-178`

**Deskripsi.** Endpoint `/loops` (`create_transport_loop`, `record_transport_event`, `close_transport_loop`, `transport_absence`) hanya memutasi `CareLoopLedger` di memori. Tidak ada penulisan ke tabel `cases`/`ledger_events`, dan `_restore_ledger` hanya memulihkan kasus dan event yang diproyeksikan. Probe: buat loop + event, tutup service, buka DB yang sama → `GET /loops/{id}` = 404.

**Dampak.** Data hilang setiap restart meski `CARELOOP_DB` di-set. Dokumentasi menyebut "SQLite-backed projection over one canonical ledger" — klaim ini tidak berlaku untuk API transport (`/loops`), dan dua jalur API memiliki jaminan durabilitas berbeda.

**Rekomendasi.** Pilih satu arsitektur: (a) persist loop/event/handoff/consult/gap ke tabel, dan pulihkan saat init; atau (b) dokumentasikan `/loops` sebagai in-memory/ephemeral dan hapus klaim durabilitas. Perlu keputusan desain sebelum implementasi.

**Estimasi.** M–L

---

### F-005 — High — Bug (konsistensi state) — `api/service.py:285-300`, `api/service.py:386-400`, `api/service.py:414-429`

**Deskripsi.** Mutasi ledger (in-memory) dan SQLite tidak atomik.
- `create_case` memanggil `self.ledger.create_loop(...)` (baris 290), lalu memvalidasi `stage != record.stage` (baris 291-292). Probe: `create_case(stage="notification")` melempar `ValidationError`, tetapi jumlah loop di ledger naik 12 → 13; loop yatim itu terbaca lewat ledger namun tidak punya baris `cases` (404).
- `transition_case`/`handoff_case`/`close_case` memutasi ledger lebih dulu, lalu menulis DB. Jika penulisan DB gagal, ledger dan DB berbeda.

**Dampak.** State "sumber kebenaran" dan proyeksi dapat berbeda tanpa mekanisme pemulihan; loop yatim muncul di `daily_absence_report` tetapi tidak di daftar kasus/analytics.

**Rekomendasi.** Validasi seluruh prasyarat sebelum mutasi ledger; jadikan DB dan ledger satu unit kerja (tulis DB dalam transaksi, commit hanya setelah ledger berhasil, atau sediakan operasi rollback/delete di ledger). Minimal untuk temuan ini: pindahkan validasi `stage` sebelum `create_loop` dan buang cek pasca-mutasi.

**Estimasi.** S (minimal) / M (transaksional penuh)

---

### F-006 — High — Bug (adapter HTTP) — `api/app.py:136-137`, `api/app.py:145-155`

**Deskripsi.** Adapter WSGI mengambil query dari `urlparse(PATH_INFO).query`. Menurut WSGI, query ada di `environ["QUERY_STRING"]`, bukan di `PATH_INFO`; sehingga `parse_qs` selalu kosong. Semua filter (`status`, `patient_id`, `actor_id`, `group_by`) diabaikan. Selain itu `OPTIONS` tidak ditangani dan mengembalikan 404, sehingga preflight untuk header `X-Actor-ID` gagal.

**Bukti.** `GET /cases?status=notification` via WSGI → 12 kasus (campuran stage); `GET /cases?actor_id=patient-01` tanpa header → 12 kasus; `OPTIONS /cases` → 404.

**Dampak.** Mode fallback (tanpa FastAPI — mode default bila `requirements.lock` kosong) mengembalikan data yang salah secara senyap dan tidak dapat dipakai lintas origin. Actor query bisa dianggap kontrol akses, tetapi diabaikan.

**Rekomendasi.** Gunakan `parse_qs(environ.get("QUERY_STRING", ""))`, tangani `OPTIONS` dengan 204 + header CORS, dan tambahkan test WSGI untuk filter dan preflight. Pertimbangkan menjadikan FastAPI dependensi wajib agar hanya ada satu adapter yang diuji.

**Estimasi.** S

---

### F-007 — High — Correctness/Config (kredibilitas data) — `web/src/App.tsx:60-73`, `web/src/App.tsx:256-263`

**Deskripsi.** `generatedV2Run` diberi label "24 cases × 2 runs" dan "linked to the bounded JSON artefact", tetapi:
- `out/v2-bounded.json` **tidak ada**; tidak ada skrip yang menghasilkannya.
- Angka tidak cocok dengan `out/reproduce.json` (24×2) maupun `out/stress-200x10.json` (200×10). Contoh: `fullCore` UI `0.1455`, padahal B-full 24×2 = `0.5417`; `fifoBacklog` UI `6221`, padahal 24×2 = `83` dan 200×10 = `6511`; `unknownRate` UI `0.0535` = B-full 200×10, sedangkan `closure` 0.5834 berasal dari run lain.
- `generatedSmokeRun` (baris 50-58) dideklarasikan tetapi tidak pernah dipakai.

**Dampak.** Panel "GENERATED TEST-RUN OUTPUT" menampilkan campuran angka dari artefak berbeda dengan label dimensi yang salah, plus tautan ke file yang tidak ada. Pada proyek yang mengedepankan pelabelan jujur, ini merusak kredibilitas dan dapat dianggap klaim yang tidak dapat direproduksi.

**Rekomendasi.** Hasilkan angka UI dari satu artefak yang benar-benar ada (mis. `out/reproduce.json`), perbarui label dimensi, dan ganti teks `out/v2-bounded.json` dengan path yang valid; atau hapus panel angka hardcoded dan tampilkan "no artifact loaded".

**Estimasi.** S

---

### F-008 — High — Config (Docker) — `Dockerfile:1-6`

**Deskripsi.**
```dockerfile
COPY . /app
RUN python -m pip install --no-cache-dir -r requirements.lock
EXPOSE 8000
CMD ["python", "-m", "api", "--host", "127.0.0.1", "--port", "8000"]
```
- Aplikasi di dalam container hanya listen di loopback container, sehingga `-p 8000:8000` tidak dapat dijangkau dari host.
- `COPY . /app` membawa `web/node_modules`, `web/dist`, dan `out/` (belasan MB) ke image; tidak ada `.dockerignore`.
- `requirements.lock` kosong, jadi image tidak memuat FastAPI/Uvicorn dan akan memakai WSGI fallback yang cacat (F-006).
- Container berjalan sebagai root; tidak ada healthcheck.

**Dampak.** Image yang di-build dari Dockerfile ini tidak dapat diakses sebagai service, dan mode HTTP yang aktif adalah adapter yang belum benar.

**Rekomendasi.** Bind `0.0.0.0` di dalam container (dengan peringatan), tambahkan `.dockerignore`, putuskan apakah FastAPI wajib (isi lock), dan tambahkan user non-root + healthcheck.

**Estimasi.** S–M

---

### F-009 — High — Performance — `api/app.py:90-92`, `api/service.py:302-316`, `api/service.py:323-334`

**Deskripsi.** `GET /cases` memanggil `list_cases` (1 query + 1 query per kasus untuk `_record`), lalu untuk setiap kasus memanggil `get_case`, yang menjalankan `_allowed_case` (2 query), `_case_row`, dan `_detail` (7 query: events, consents, evidence, escalations, handoffs, appointments, plus ledger). Hasil probe: **122 statement SQL untuk 12 kasus**; respons berisi detail penuh semua kasus tanpa paginasi.

**Dampak.** O(N) query per request dan payload membengkak seiring jumlah kasus; endpoint daftar menjadi mahal dan tidak skalabel. Saat ini belum terasa karena data demo 12 kasus.

**Rekomendasi.** Buat query daftar dengan JOIN ke `ledger_events`/agregat, kembalikan ringkasan (tanpa `events/consents/...`), tambahkan `limit/offset`. Contoh: satu `SELECT` kasus + satu query agregat per tabel; atau endpoint ringkasan terpisah.

**Estimasi.** M

---

### F-010 — Medium — Bug (aturan bisnis) — `api/service.py:402-442`

**Deskripsi.** `handoff_case`, `escalate_case`, `schedule_appointment`, `record_evidence`, `record_consent`, `teach_back`, dan `authorize_closure` tidak memeriksa `record.status`. Probe pada kasus `closed`: handoff, eskalasi, dan appointment semuanya diizinkan (dan menulis audit).

**Dampak.** Kasus yang sudah ditutup dapat diubah lagi; audit menjadi bising dan status "closed" tidak bermakna. Berbeda dengan `transition_case`/`close_case` yang menolak kasus tertutup.

**Rekomendasi.** Tambahkan guard `if record.status is LoopStatus.CLOSED: raise ValidationError("closed case cannot be modified")` untuk aksi operasional (handoff/escalate/appointment); putuskan apakah evidence/consent/teach-back pasca-closure tetap diizinkan sebagai dokumentasi.

**Estimasi.** S

---

### F-011 — Medium — Bug (integritas audit) — `api/service.py:633-636`, `careloop/loop_engine/ledger.py:814-830`

**Deskripsi.** `close_transport_loop` memanggil `ledger.close_loop` langsung. `close_loop` hanya mengubah record; tidak menambahkan event E9. Probe: setelah closure, `events(loop_id)` = 0. Bandingkan dengan `close_case` yang memanggil `record_closure_event` (E9).

**Dampak.** Penutupan via `/loops/{id}/close` tidak memiliki jejak event E9, padahal kontrak menyatakan E9 adalah event penutupan berbukti. Dua jalur penutupan menghasilkan audit trail berbeda.

**Rekomendasi.** Catat `record_closure_event` sebelum `close_loop` di jalur transport (dan persist bila F-004 diperbaiki), atau pusatkan logika closure di satu method service.

**Estimasi.** S

---

### F-012 — Medium — Bug (idempotensi) — `api/service.py:584-609`

**Deskripsi.** `run_stalled_case_scenario` selalu membuat/eskalasi/menambah evidence lalu menutup. Panggilan kedua: kasus sudah `closed`, tetapi eskalasi/handoff/evidence tetap ditambahkan, lalu `close_case` melempar `ValidationError` → HTTP 400. Probe terkonfirmasi.

**Dampak.** Endpoint demo tidak idempoten; demo yang di-refresh menghasilkan error dan data duplikat.

**Rekomendasi.** Jika kasus sudah closed, kembalikan hasil yang ada (200) tanpa mutasi; atau reset skenario secara eksplisit. Tambahkan test panggilan ganda.

**Estimasi.** S

---

### F-013 — Medium — Bug (error handling) — `api/app.py:189`

**Deskripsi.** Pada adapter FastAPI, `payload = await request.json() if ...` tidak dibungkus `try`. Body JSON rusak menghasilkan exception yang tidak ditangani → 500. Probe: `POST /demo/seed` dengan `{not-json` → 500.

**Dampak.** Kesalahan klien menjadi 500 dan traceback di log server; berbeda dengan adapter WSGI yang mengembalikan 400.

**Rekomendasi.** Tangkap `json.JSONDecodeError`/`RequestValidationError` dan kembalikan 400 `{"error": "invalid JSON body"}`.

**Estimasi.** S

---

### F-014 — Medium — Security (identitas) — `api/app.py:43-44`, `api/service.py:219-226`

**Deskripsi.** Aktor sepenuhnya berasal dari header `X-Actor-ID` (atau query) tanpa autentikasi. Siapa pun dapat mengaku `manager-1`, `clinician-1`, atau `patient-01`. Tidak ada session/token, rate limit, atau audit identitas.

**Dampak.** RBAC hanya kosmetik terhadap klien yang tidak jujur. `SECURITY_NOTES.md` sudah menyatakan ini bukan batas identitas produksi — jadi ini **diketahui dan diterima untuk prototipe**, tetapi tetap harus tercatat sebagai blocker sebelum data nyata/deployment.

**Rekomendasi.** Untuk prototipe: pertahankan, tetapi tolak header pada konfigurasi non-loopback atau tambahkan shared secret lokal. Untuk produksi: OIDC/session, TLS, dan audit identitas.

**Estimasi.** L

---

### F-015 — Medium — Config (dokumentasi) — `README.md:40`, `web/vite.config.ts:9`, `web/README.md:15`

**Deskripsi.** README root menyuruh menjalankan API di port **8765**, sedangkan proxy Vite mengarah ke **8000** dan README web memakai **8000**. Pengguna yang mengikuti README root akan mendapat UI yang jatuh ke "Local fallback" tanpa penjelasan.

**Dampak.** Onboarding gagal secara senyap; demo tersaji tanpa sinkronisasi API.

**Rekomendasi.** Samakan port (disarankan 8000) di README, Makefile, proxy, dan `.env.example`.

**Estimasi.** S

---

### F-016 — Medium — Config (side effect) — `api/__init__.py:20`, `api/app.py:199-201`

**Deskripsi.** `api/__init__.py` mengimpor `.app`, dan `api/app.py` membuat `app = create_app()` saat import. Jika `CARELOOP_DB` di-set, sekadar `import api` membuka/membuat file SQLite dan seluruh skema. Probe: setelah `import api`, file DB ada dan berisi 12 tabel; `api.app` adalah instance FastAPI yang tidak dipakai oleh `serve()`. `serve()` kemudian membuat service kedua ke DB yang sama.

**Dampak.** Side effect tak terduga pada skrip/test, dua koneksi ke DB yang sama, dan potensi kebingungan ownership koneksi. Pada Windows, koneksi yang tertinggal dapat mempersulit penghapusan/backup file.

**Rekomendasi.** Lazy-load `app` (mis. `__getattr__` di `__init__`) atau hapus service module-level; buat `serve()` menjadi satu-satunya pemilik service.

**Estimasi.** S–M

---

### F-017 — Medium — Security/Performance (DoS) — `api/app.py:86-87`, `api/service.py:568-582`

**Deskripsi.** `POST /demo/seed` menerima `case_count` dari body dengan `int(...)` tanpa batas. Nilai besar (mis. 10 juta) memicu loop pembuatan user/kasus, query per kasus, dan audit — memblokir event loop/worker.

**Dampak.** Denial of service lokal; payload/DB membengkak. Karena endpoint demo seharusnya kecil, batas wajar mudah diterapkan.

**Rekomendasi.** Batasi `1 <= case_count <= 100` dan `seed` ke rentang integer; validasi tipe sebelum konversi. Return 400 untuk nilai di luar batas.

**Estimasi.** S

---

### F-018 — Medium — Performance — `careloop/simulator/engine.py:1214-1225`, `careloop/simulator/engine.py:1146-1159`

**Deskripsi.** `_stress_scenarios` (stress lama) menjalankan `Simulator(self.config, params)._run_core()` dengan konfigurasi **penuh**, bukan `_analysis_config()`. Dengan `--full --stress`, setiap skenario menjalankan 10.000 × 500 × 6 arm. Sebaliknya `_v2_stress_scenarios` dan sensitivity memakai konfigurasi analisis terbatas. `_workload_comparison` juga selalu menjalankan dua simulasi tambahan (hingga 1.000 × 20).

**Dampak.** Kombinasi flag yang tampak wajar dapat membuat proses berjalan berjam-jam/kehabisan memori. Tidak ada peringatan.

**Rekomendasi.** Gunakan `_analysis_config()` untuk semua analisis turunan, atau dokumentasikan biaya dan minta konfirmasi eksplisit. Batasi `all_rows` (mis. hanya segmen `all` + segmen terpilih) untuk mengurangi memori.

**Estimasi.** S–M

---

### F-019 — Medium — Maintainability (test) — `tests/`, `web/package.json:9`

**Deskripsi.** Test Python baik (41), tetapi tidak ada test untuk: kontrak payload `close` frontend, pemetaan status error HTTP, query string WSGI/preflight, durabilitas `/loops`, guard kasus tertutup, polusi event yang ditolak, dan idempotensi `/demo/scenario`. Frontend hanya menjalankan `tsc` (`"test": "tsc -b"`), tanpa test perilaku.

**Dampak.** Regresi kontrak (F-002) dan integritas (F-001) tidak tertangkap. Klaim README bahwa test mencakup "role checks, ..., SQLite reopen" benar, tetapi tidak mencakup jalur yang rusak.

**Rekomendasi.** Tambahkan test regresi untuk setiap perbaikan F-001…F-013, plus minimal satu test HTTP per status code. Untuk frontend, tambahkan Vitest + React Testing Library atau setidaknya test tipe kontrak request.

**Estimasi.** M

---

### F-020 — Low — Bug (concurrency) — `api/service.py:65`

**Deskripsi.** Satu koneksi SQLite dibuat dengan `check_same_thread=False` dan dipakai bersama tanpa lock. Uvicorn single-worker menjalankan handler pada satu thread, tetapi jika `--workers > 1`/thread pool dipakai, transaksi antar-thread dapat saling mengunci (`database is locked`) atau mencampur state `self.ledger` (dict tanpa sinkronisasi).

**Dampak.** Risiko muncul hanya pada deployment multi-thread/multi-worker; tidak terlihat pada demo.

**Rekomendasi.** Gunakan `threading.Lock` di sekitar mutasi, atau satu koneksi per thread/request, dan jalankan single worker sampai model persistensi diperbaiki. Aktifkan WAL + `busy_timeout` eksplisit.

**Estimasi.** M

---

### F-021 — Low — Bug (ID generation) — `api/service.py:382-384`

**Deskripsi.** `_next_id` memakai `SELECT COUNT(*) + 1` dari tabel. Jika ada penghapusan (belum ada endpoint) atau dua permintaan bersamaan, ID dapat bertabrakan; juga ID bergantung pada urutan global, bukan per kasus.

**Dampak.** Risiko tabrakan/`IntegrityError` yang sulit didiagnosis saat data bertambah.

**Rekomendasi.** Gunakan UUID/ULID atau `AUTOINCREMENT` sebagai sumber ID; atau hitung per kasus dengan `MAX` + unique constraint.

**Estimasi.** S

---

### F-022 — Low — Maintainability (artefak) — `web/vite.config.js:1`, `web/vite.config.d.ts`, `web/tsconfig*.tsbuildinfo`, `APP/NUL`

**Deskripsi.** `vite.config.js` dan `.d.ts` adalah hasil kompilasi `tsconfig.node.json` yang ter-commit. Vite mencari `vite.config.js` sebelum `vite.config.ts`, sehingga perubahan pada file TS bisa diabaikan jika JS tidak ikut di-build. `tsbuildinfo` ikut ter-commit. `APP/NUL` adalah file 38 byte berisi NUL (artefak redirect Windows).

**Dampak.** Konfigurasi dapat "tidak berefek" secara membingungkan; repo kotor.

**Rekomendasi.** Hapus artefak dari repo, tambahkan ke `.gitignore` (`*.tsbuildinfo`, `vite.config.js`, `vite.config.d.ts`, `NUL`), dan set `noEmit`/`emitDeclarationOnly` sesuai kebutuhan.

**Estimasi.** S

---

### F-023 — Low — Maintainability (kode mati) — `web/src/App.tsx:50-58`, `245-249`, `266-270`

**Deskripsi.** `generatedSmokeRun`, komponen `Patient` (versi Arab), dan komponen `Simulation` tidak direferensikan. `PatientEnglish` dan `SimulationV2` yang dipakai. `tsc` lulus karena `noUnusedLocals` tidak diaktifkan.

**Dampak.** Membingungkan pembaca dan menambah permukaan perawatan; versi Arab yang tidak dipakai dapat disalahartikan sebagai fitur aktif.

**Rekomendasi.** Hapus, atau ekspos secara sengaja (mis. toggle bahasa) dengan test. Aktifkan `noUnusedLocals`/`noUnusedParameters`.

**Estimasi.** S

---

### F-024 — Low — Bug (semantik metrik) — `careloop/simulator/engine.py:917`, `936-941`

**Deskripsi.** `unnecessary_escalation_rate = sum(case.unnecessary_escalations)/n` adalah rata-rata *jumlah* eskalasi tak perlu per kasus, bukan rate (bisa > 1). Nama field menyesatkan; `unresolved_30/60/90` juga menghitung `closure_time is None` sama untuk semua horizon. Tidak ada dokumentasi bahwa ini bukan rate.

**Dampak.** Interpretasi hasil bisa salah, terutama di laporan evaluasi yang menekankan ketepatan klaim.

**Rekomendasi.** Ganti nama field atau ubah definisi menjadi proporsi kasus dengan ≥1 eskalasi tak perlu, dan dokumentasikan semantik `unresolved_*`.

**Estimasi.** S

---

### F-025 — Low — Bug/perlu verifikasi (absence report) — `careloop/loop_engine/ledger.py:657-668`

**Deskripsi.** `daily_absence_report(at=...)` mengembalikan **semua loop terbuka**, tanpa membandingkan `loop.due_at` terhadap `at`. Parameter `at` hanya dipakai sebagai `reported_at`. Jika tujuan laporan adalah "event yang belum datang melewati deadline", ini salah; jika tujuannya inventaris harian, ini benar. Dokumentasi menyebut "daily absence-of-event report" tanpa definisi eksplisit.

**Dampak.** Potensi alarm palsu untuk loop yang belum jatuh tempo.

**Rekomendasi.** Klarifikasi kontrak; jika overdue-only, filter `loop.due_at < observed`. Tambahkan test dengan deadline di masa depan.

**Estimasi.** S

---

### F-025b — Low — Reproducibility — `scripts/run_full_study.py:105-111`, `careloop/simulator/engine.py:250-251`

**Deskripsi.** Runner full study menjalankan satu replikasi per proses dengan `seed + run_index - 1` dan `runs=1`; `_cohort` kemudian memakai `config.seed + run_number * 1009` dengan `run_number=1`. Studi in-process (`runs=500`) memakai urutan `seed + run_number * 1009` untuk run 1..500. Keduanya deterministik, tetapi **bukan cohort yang sama**; angka full study tidak identik dengan `Simulator(runs=500)`.

**Dampak.** Klaim reproduksibilitas antar jalur perlu diverifikasi; hasil bisa berbeda dari yang dipublikasikan.

**Rekomendasi.** Teruskan `run_number` eksplisit ke `_cohort` atau jalankan `Simulator(runs=1, seed=seed + 1009*(run_index-1))` lalu gunakan seed yang sama dengan loop in-process. Dokumentasikan pemetaannya.

**Estimasi.** S

---

### F-026 — Low — Security (info disclosure) — `api/app.py:117-122`

**Deskripsi.** Fallback `except Exception` mengembalikan `str(error)` dan `type(error).__name__` ke klien. Untuk error tak terduga (mis. `sqlite3.OperationalError`), detail internal (path file, SQL) dapat bocor.

**Dampak.** Information disclosure pada deployment yang salah konfigurasi; juga menyamarkan 500 sebagai pesan domain.

**Rekomendasi.** Log detail di server; kembalikan pesan generik untuk 500 (`{"error": "internal error"}`) dan sertakan correlation ID.

**Estimasi.** S

---

## 4. Rencana Perbaikan Bertahap

Urutan mempertimbangkan dependensi: integritas ledger dulu, lalu kontrak HTTP, lalu adapter, lalu persistensi.

**Tahap 0 — Quick wins (S, tanpa perubahan arsitektur)**
1. F-001 perbaiki urutan append di ledger + test regresi.
2. F-002 kirim `closure_code` dari UI; jangan majukan state UI saat sinkronisasi gagal.
3. F-003 petakan `ClosureError`/`DuplicateEntityError` ke 400/409.
4. F-013 tangkap JSON rusak → 400.
5. F-015 samakan port (8000) di README/proxy.
6. F-017 batasi `case_count`.
7. F-022/F-023 bersihkan artefak dan kode mati.

**Tahap 1 — Integritas state (S–M, bergantung pada F-001)**
8. F-005 validasi sebelum mutasi ledger; hilangkan loop yatim. Lanjutkan dengan pembungkusan transaksi DB+ledger.
9. F-010 guard kasus tertutup.
10. F-011 catat E9 pada closure transport; F-012 buat skenario idempoten.

**Tahap 2 — Adapter & durability (M)**
11. F-006 perbaiki WSGI query/OPTIONS + test.
12. F-004 putuskan dan implementasikan persistensi transport ledger (perlu keputusan desain).
13. F-009 ringkasan daftar kasus + paginasi.

**Tahap 3 — Deployment & kredibilitas (S–M)**
14. F-008 Docker: bind 0.0.0.0, `.dockerignore`, dependency, non-root, healthcheck.
15. F-007 hubungkan Simulation Lab ke artefak nyata.
16. F-016 hapus side effect import; satukan ownership service.
17. F-018 batasi analisis stress; F-020/F-021 hardening konkurensi/ID.

**Tahap 4 — Kualitas jangka panjang (M)**
18. F-019 perluas test (HTTP status, kontrak frontend, durability, closed-case).
19. F-024/F-025/F-025b perbaiki semantik metrik/absence/reproduksi.

**Quick wins** yang bisa diselesaikan dalam satu sesi: F-001, F-002, F-003, F-005 (minimal), F-006, F-010, F-011, F-012, F-013, F-015, F-017.

---

## 5. Hal yang Tidak Bisa Diverifikasi

1. **Python 3.11.9 dan Node 20**: tidak terpasang. Semua test/build dijalankan di Python 3.13.7 / Node 24.21.0. Kompatibilitas 3.11.9 (dipakai Docker) belum dieksekusi, meski kode hanya memakai fitur ≥3.10.
2. **Docker build/run**: tidak dijalankan (butuh pull image dan jaringan). Temuan F-008 berasal dari pembacaan file, bukan eksekusi.
3. **`npm audit` / kerentanan dependensi**: tidak dijalankan tanpa registry. Versi di `package-lock.json` belum dipindai.
4. **Full study 10.000 × 500**: tidak dijalankan (biaya komputasi). Artefak `out/*` yang ada tidak saya regenerasi; angka di F-007 dibandingkan terhadap artefak yang tersedia.
5. **Provenance artefak `out/`**: tidak dapat dipastikan dari commit/skrip mana setiap angka berasal; label di UI tidak dapat direkonsiliasi sepenuhnya.
6. **Kepatuhan klinis/regulasi, keamanan produksi, identitas, TLS, retensi data**: di luar cakupan kode dan sudah dinyatakan sebagai gap di `SECURITY_NOTES.md`; perlu review manusia/legal.
7. **Apakah mutasi pasca-closure (evidence/consent/teach-back) sengaja diizinkan**: perlu keputusan pemilik produk. Handoff/eskalasi/appointment pasca-closure hampir pasti bug, tetapi dokumentasi tidak eksplisit.
8. **Tujuan `daily_absence_report`**: overdue-only vs inventaris harian; membutuhkan konfirmasi desain.
9. **Dukungan multi-worker Uvicorn**: belum diuji; F-020 bersifat analisis kode.

---

## 6. Status Perbaikan Setelah Laporan

Perbaikan dilakukan satu temuan per langkah dengan test regresi untuk setiap perubahan perilaku. Verifikasi akhir: **52 test Python lulus** (`PYTHONPATH=. python -B -m unittest discover -s tests -t .`), `npm test` (`tsc -b`) lulus, dan `npm run build` (Vite 6) lulus.

| ID | Status | Perubahan | Verifikasi |
|---|---|---|---|
| F-001 | Selesai | `record_event` memvalidasi tipe event terhadap stage **sebelum** append ke `_events`; event ilegal tidak lagi meninggalkan jejak. | Test regresi di `test_ledger_contract.py` dan `test_loop_engine.py`: setelah E8/E9 ditolak, daftar event tidak berubah. |
| F-002 | Selesai | UI mengirim `closure_code: 'Completed'` bersama `evidence_id` pada aksi close. | Backend flow escalate → handoff → evidence → close mengembalikan 200/`closed`; `npm test` lulus. |
| F-003 | Selesai | `_error_status` memetakan `AuthorizationError` 403, `NotFoundError` 404, `DuplicateEntityError` 409, `ValidationError`/`ClosureError` 400, sisanya 500. | Test duplikat `/loops` → 409 dan close tanpa closure code → 400 (`ClosureError`). |
| F-005 | Selesai | `create_case` memvalidasi stage dan duplikasi case sebelum membuat loop di ledger. | Test: stage invalid tidak menambah `_loops` (12 → 12). |
| F-006 | Selesai | Adapter WSGI membaca `QUERY_STRING`, mengembalikan 204 + header CORS untuk `OPTIONS`, dan meneruskan header. | Test: filter `status=open` → 12 item, `actor_id=patient-01` → 1 item, `OPTIONS` → 204. |
| F-007 | Selesai | Angka Simulation Lab diambil dari `out/reproduce.json` (24 kasus × 2 run): closure/core/backlog/visibility per arm dan policy; label artefak diperbaiki; `generatedSmokeRun` dihapus. | `npm test` dan `npm run build` lulus; nilai dicocokkan dengan artefak nyata. |
| F-008 | Selesai (belum dieksekusi) | Docker bind `0.0.0.0`, user non-root, healthcheck, dan `.dockerignore` (node_modules, dist, out, DB, cache). | Build image tidak dijalankan (tanpa jaringan); perubahan berbasis pembacaan file. |
| F-009 | Selesai | `GET /cases` memakai `list_case_summaries` (satu query kasus + lookup ledger in-memory), bukan detail penuh per kasus. | Test trace SQL: ≤ 4 statement untuk 12 kasus; item tidak memuat `events`/`consents`. Catatan kompatibilitas: list kini ringkasan, detail tetap di `GET /cases/{id}`. |
| F-010 | Selesai | Guard `closed case cannot be modified` pada escalate, handoff, appointment, dan authorize_closure; evidence/consent/teach-back pasca-closure tetap diizinkan sebagai dokumentasi. | Test: keempat aksi ditolak setelah close. |
| F-011 | Selesai | `close_transport_loop` memvalidasi kontrak, mencatat E9, lalu menutup loop; loop tertutup menolak closure kedua. | Test: closure tanpa evidence → error dan 0 event; closure valid → `["E9"]`; closure kedua → `ValidationError`. |
| F-012 | Selesai | `run_stalled_case_scenario` mengembalikan hasil `already_closed` tanpa mutasi jika kasus sudah tertutup. | Test: panggilan kedua tidak menambah escalation/handoff/evidence/event. |
| F-013 | Selesai | Adapter FastAPI menangkap JSON rusak dan mengembalikan 400 `{"error": "invalid JSON body"}`. | Test `TestClient` dengan body `{not-json` → 400. |
| F-015 | Selesai | Port disamakan ke 8000 di `README.md` dan `docs/DEMO_SCRIPT.md` (proxy Vite sudah 8000). | Pencarian `8765` tidak menemukan referensi tersisa selain laporan audit. |
| F-016 | Selesai | `api.app` tidak lagi membuat service saat import; `api.app.app` dan `api.create_app` dimuat lazy (PEP 562). `serve()` tetap pemilik tunggal service. | Test subprocess: `import api` dengan `CARELOOP_DB` tidak membuat file DB. |
| F-017 | Selesai | `/demo/seed` memvalidasi integer dan `load_demo_data` membatasi `1 <= case_count <= 100`. | Test: `case_count` 0, 100000, dan `"many"` → 400 `ValidationError`. |
| F-018 | Selesai | `_stress_scenarios` memakai `_analysis_config()` (maks. 1.000 × 20) alih-alih konfigurasi penuh. | `tests.test_simulator_contract` lulus (8 test). |
| F-021 | Selesai | ID evidence/escalation/handoff/appointment memakai suffix UUID 12 hex; `_next_id` COUNT dihapus. | Suite penuh lulus; tidak ada test yang bergantung pada format ID lama. |
| F-022 | Selesai | `web/vite.config.js`, `vite.config.d.ts`, `tsbuildinfo`, dan `NUL` dihapus; `tsconfig.node.json` memakai `emitDeclarationOnly`; artefak masuk `.gitignore`. | `npm test` dan `npm run build` lulus tanpa menghasilkan `vite.config.js`. |
| F-026 | Selesai | Error tak terduga dicatat via `logging` dan klien hanya menerima `{"error": "internal error"}`. | Test patch service → 500 tanpa detail internal. |

**Belum diperbaiki (butuh keputusan/verifikasi):**

- **F-004** (persistensi transport loop/event): memerlukan keputusan desain tentang skema dan atomisitas ledger ↔ SQLite; tidak diubah agar tidak memperluas scope.
- **F-014** (autentikasi): tetap merupakan batasan prototipe yang sudah didokumentasikan di `SECURITY_NOTES.md`.
- **F-019** (gap test): regresi untuk F-001…F-013 sudah ditambahkan, tetapi test runtime frontend (Vitest/RTL) belum ada.
- **F-020** (multi-worker): belum diuji dan belum diubah.
- **F-023** (kode mati): `generatedSmokeRun` dihapus; komponen `Patient` dan `Simulation` yang tidak terpakai masih ada.
- **F-024, F-025, F-025b**: membutuhkan konfirmasi semantik metrik/absence/reproduksi sebelum diubah.

