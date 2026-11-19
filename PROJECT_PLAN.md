# NoteYourMeet — Rencana Proyek & Konteks untuk Sesi Baru

> **Tujuan dokumen ini:** jadi "ingatan" proyek. Kalau pindah ke sesi chat baru, cukup bilang:
> *"Baca `PROJECT_PLAN.md` dulu, lalu lanjutkan dari bagian **Status & Langkah Berikutnya**."*
> Setiap selesai satu tahap, **update bagian paling bawah** (Status, Log Keputusan).

---

## 1. Ringkasan Produk

**NoteYourMeet** adalah aplikasi web pribadi (khusus tim internal) untuk mengolah **rekaman suara meeting**
(dari HP, laptop, recorder, atau file hasil Zoom/Meet) menjadi:

- Transkrip lengkap dengan **siapa bicara apa** dan **timestamp**
- **Notulen** otomatis (ringkasan, topik, keputusan, action item)
- **Jumlah peserta** + statistik siapa paling banyak bicara
- Bisa ditanya-tanya ("Tadi deadline desain kapan?") dan dicari lintas meeting

Pengguna: tim kecil (± 2–20 orang), bahasa utama **Indonesia** (sering campur Inggris), tidak untuk publik.

---

## 2. Keputusan Teknologi (FINAL untuk MVP)

| Lapisan | Pilihan | Alasan |
|---|---|---|
| **Frontend** | **Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui**, dijadikan **PWA** | Satu codebase untuk HP & desktop; PWA bisa di-"install" di HP dan merekam langsung lewat browser (MediaRecorder API) tanpa bikin app native. |
| Player audio | **wavesurfer.js** | Waveform + klik kalimat di transkrip → audio lompat ke detik itu. |
| State/data fetching | **TanStack Query** | Polling/cache status proses meeting dengan rapi. |
| **Backend API** | **Python 3.12 + FastAPI** | Ekosistem audio/AI (ffmpeg, pyannote, whisper, SDK Anthropic) paling matang di Python. |
| ORM & migrasi | **SQLAlchemy 2 + Alembic**, validasi **Pydantic v2** | Standar, typed, gampang dirawat. |
| **Background job** | **Celery + Redis** | Proses audio bisa makan menit; harus di luar request HTTP, dengan retry. |
| **Database** | **PostgreSQL 16 + pgvector** | Data relasional + embedding untuk pencarian semantik & "chat dengan meeting". |
| **Penyimpanan file** | **S3-compatible**: MinIO (lokal/VPS) atau Cloudflare R2 (cloud) | Upload langsung dari browser via *presigned URL* (file besar tidak lewat API). |
| Pra-proses audio | **ffmpeg** | Konversi semua format (m4a, mp3, aac, opus, mp4) → WAV/FLAC 16 kHz mono + normalisasi volume. |
| **Speech-to-Text + Diarization** | **Self-host di GPU sendiri (GTX 1660 Ti, 6 GB VRAM)**: **WhisperX** = faster-whisper (`large-v3-turbo`, `compute_type="int8_float16"`, `batch_size` 4–8) + **pyannote** `speaker-diarization-3.1`. Tetap lewat interface `TranscriptionProvider`; cadangan: AssemblyAI/Deepgram API | Gratis per jam audio, **audio tidak keluar dari PC** (privasi). Muat di 6 GB jika model Whisper & pyannote dijalankan **bergantian** (lepas VRAM di antaranya). Terukur: rekaman 43 menit diproses 16 menit (± 0,37× durasi audio). Jika kualitas kurang, coba `large-v3` int8 (lebih lambat). Butuh token Hugging Face + setujui syarat model pyannote. |
| **AI Notulen (LLM)** | **Claude API — `claude-opus-5-5`** (SDK Python `anthropic`) dengan **structured output** (Pydantic) | Kualitas ringkasan & ekstraksi terbaik; konteks 1M token → transkrip meeting berjam-jam muat tanpa dipotong. |
| Tugas ringan LLM | `claude-haiku-5-5` | Judul otomatis, tag, klasifikasi — murah & cepat. |
| Embedding | Model embedding (mis. `voyage-3` / `bge-m3` lokal) → pgvector | Pencarian semantik lintas meeting. Putuskan saat fase 3. |
| **Auth** | Login email + password **invite-only** (hash argon2), session cookie httpOnly | Aplikasi privat; tidak perlu registrasi publik. |
| Realtime status | **Server-Sent Events (SSE)** atau polling 3 detik | Tampilkan progres: "Mentranskrip… 45%". |
| **Deploy (Tahap A — sekarang)** | **Semua di PC sendiri** (Windows + Docker Desktop/WSL2 dengan GPU NVIDIA) via **Docker Compose**, diakses tim lewat **Cloudflare Tunnel + Cloudflare Access** (HTTPS gratis, tanpa buka port router, login email tim) | Rp0 tambahan, GPU sudah ada. Kekurangan: PC harus menyala saat dipakai. |
| **Deploy (Tahap B — kalau PC sering mati)** | Web + API + Postgres + Redis + MinIO pindah ke **VPS kecil** (2 vCPU/4 GB, ± Rp100–150 rb/bulan); **worker GPU tetap di PC** dan terhubung ke VPS lewat **Tailscale**. Upload tetap diterima kapan saja; diproses saat PC menyala | Aplikasi selalu online, biaya GPU tetap nol. Kode sudah siap karena worker terpisah lewat antrean Redis. |
| Kualitas kode | Python: **ruff + mypy + pytest**; TS: **ESLint + Prettier + Vitest**; Playwright untuk E2E | |

### ⚠️ Implementasi SAAT INI (disederhanakan, 2026-11-18)
Karena pemakaian kecil (1–2 meeting/bulan) dan PC belum punya Docker/WSL, versi berjalan sekarang memakai:
- **Jalan langsung di Windows** (Python 3.12 venv + Node), tanpa Docker.
- **SQLite** (`apps/api/data/noteyourmeet.db`) — bisa pindah ke Postgres cukup dengan `DATABASE_URL`.
- **Antrean = tabel `meetings`** (status `QUEUED`), worker polling tiap 3 dtk — **tanpa Celery/Redis**.
- **File disimpan di disk** (`apps/api/data/storage/meetings/<uuid>/`) — belum MinIO/S3.
- Upload biasa (multipart form) dengan progress bar; belum resumable.
- **Belum ada login** → hanya aman diakses dari PC sendiri. **Wajib tambah auth sebelum dibuka lewat Cloudflare Tunnel.**
- Frontend: **Next.js 16.4** + Tailwind 4 (tanpa shadcn dulu). `cacheComponents` aktif → halaman dinamis dibungkus `<Suspense>`.
- WhisperX **3.8.6**, model diarization `pyannote/speaker-diarization-community-1`, alignment Indonesia `cahya/wav2vec2-large-xlsr-indonesian`.
- PyTorch **2.8.0+cu128** (harus dari index CUDA, bukan PyPI).

### Kenapa bukan alternatif lain?
- **Native app (Flutter/React Native)**: lebih berat untuk dibangun; PWA sudah cukup untuk merekam & upload. Bisa dipertimbangkan nanti kalau perlu rekam di background saat layar HP mati (keterbatasan PWA).
- **Full Node.js**: tooling audio/ML di Python jauh lebih kuat.
- **Whisper biasa tanpa diarization**: tidak bisa tahu *siapa* bicara → jumlah peserta & action item per orang jadi tidak akurat.

---

## 3. Daftar Fitur

### MVP (Fase 1–2) — wajib
1. **Upload rekaman** (drag & drop, multi-format, file besar s/d ±2 GB, upload multipart + bisa resume).
2. **Rekam langsung** dari browser/HP (PWA) → otomatis ter-upload per potongan agar tidak hilang kalau koneksi putus.
3. **Transkrip** dengan label pembicara + timestamp, bisa diklik untuk memutar audio.
4. **Ganti nama pembicara** ("Speaker A" → "Budi"), berlaku di seluruh transkrip & notulen.
   **Gabung / pisah speaker**: jumlah peserta tiap meeting berbeda-beda dan dideteksi otomatis, jadi diarization kadang memecah 1 orang jadi 2 label (atau sebaliknya) — UI harus bisa menggabungkan label. Saat upload, isian opsional "perkiraan jumlah peserta (min–maks)" diteruskan ke pyannote (`min_speakers`/`max_speakers`) untuk akurasi lebih baik.
5. **Notulen otomatis**:
   - Judul meeting & ringkasan eksekutif (3–5 kalimat)
   - Agenda/topik yang dibahas (+ timestamp mulai)
   - **Poin penting** per topik
   - **Keputusan** yang diambil
   - **Action items**: tugas, PIC, deadline (jika disebut), prioritas
   - Pertanyaan/isu yang belum terjawab
   - Risiko/kendala yang disebut
6. **Statistik peserta**: jumlah pembicara terdeteksi, durasi bicara & persentase per orang, jumlah giliran bicara.
7. **Edit notulen** manual (hasil AI bukan final).
8. **Export**: Markdown, PDF, DOCX; tombol "Copy untuk WhatsApp".
9. **Daftar meeting** + pencarian kata kunci + filter tanggal/tag.
10. **Template notulen**: Umum, Daily Standup, Meeting Klien, Brainstorming, Rapat Evaluasi.

### Fase 3 — sangat berguna
11. **Tanya jawab dengan meeting** ("Apa alasan kita pilih vendor X?") — jawaban menyertakan kutipan + timestamp.
12. **Pencarian semantik lintas meeting** ("kapan terakhir bahas budget marketing?").
13. **Action item tracker** lintas meeting (status: open/done, filter per orang).
14. **Pengenalan suara anggota tim** (voice enrollment): sekali daftar sampel suara → speaker otomatis dinamai.
15. **Glosarium tim** (nama produk, istilah internal, nama orang) dimasukkan ke STT (custom vocabulary) & prompt LLM agar ejaan benar.

### Fase 4 — nice to have
16. Transkripsi live saat meeting berlangsung.
17. Integrasi Google Calendar (judul & peserta otomatis).
18. Kirim notulen otomatis ke email/Telegram/Slack.
19. Analitik: sentimen, topik yang paling sering dibahas per bulan.
20. Export ke Notion / Google Docs.

---

## 4. Alur Aplikasi (Flow)

### 4.1 Alur pengguna
```
Login → Dashboard (daftar meeting)
   ├─ [+ Meeting Baru] → pilih: Rekam sekarang | Upload file
   │     → isi (opsional): judul, tanggal, template, peserta yang diharapkan
   │     → upload berjalan (progress bar)
   │     → halaman Meeting menampilkan status proses real-time
   └─ Buka Meeting
         ├─ Tab Notulen (bisa edit, export)
         ├─ Tab Transkrip (player audio + teks per speaker, rename speaker)
         ├─ Tab Peserta & Statistik
         └─ Tab Tanya AI (fase 3)
```

### 4.2 Alur pemrosesan (pipeline di worker)
```
[Browser] --presigned URL--> [S3/MinIO]  (file asli)
     |
     └─ POST /meetings/{id}/complete-upload
            |
            v
[API] buat job → status = QUEUED → kirim task ke Celery
            |
            v
[Worker]
 1. PREPROCESSING : ffmpeg → mono 16 kHz, normalisasi, hitung durasi
 2. TRANSCRIBING  : TranscriptionProvider → segmen {speaker, start, end, text, confidence}
 3. ANALYZING     : hitung jumlah speaker, talk-time, giliran bicara (tanpa AI, murni hitungan)
 4. SUMMARIZING   : kirim transkrip berformat ke Claude → JSON notulen tervalidasi (Pydantic)
 5. INDEXING      : (fase 3) chunk transkrip → embedding → pgvector
 6. DONE          : simpan semua, kirim event SSE ke frontend
 (gagal di langkah mana pun → status FAILED + pesan error, bisa "Coba lagi" dari langkah itu)
```

Status disimpan di kolom `meetings.status`:
`UPLOADING → QUEUED → PREPROCESSING → TRANSCRIBING → ANALYZING → SUMMARIZING → DONE | FAILED`

**Prinsip penting:** setiap langkah **idempotent** dan hasilnya disimpan, jadi kalau langkah 4 gagal, tidak perlu transkrip ulang (hemat biaya).

---

## 5. Model Data (PostgreSQL)

```
users            (id, name, email, password_hash, role[admin|member], created_at)
teams            (id, name)                       -- MVP cukup 1 tim
meetings         (id, team_id, created_by, title, meeting_date, template, status,
                  error_message, duration_sec, language, audio_key, audio_processed_key,
                  created_at, updated_at)
speakers         (id, meeting_id, label["A","B"], display_name, user_id NULL,
                  talk_time_sec, turn_count, word_count)
transcript_segments (id, meeting_id, speaker_id, start_ms, end_ms, text, confidence)
minutes          (id, meeting_id, version, summary, content_json JSONB,
                  edited_by NULL, model_used, created_at)   -- simpan versi, jangan timpa
action_items     (id, meeting_id, description, assignee_speaker_id NULL, assignee_user_id NULL,
                  due_date NULL, priority, status[open|done], source_segment_id)
decisions        (id, meeting_id, description, source_segment_id)
tags / meeting_tags
glossary_terms   (id, team_id, term, notes)                  -- fase 3
segment_embeddings (id, meeting_id, chunk_text, start_ms, end_ms, embedding vector)  -- fase 3
voice_profiles   (id, user_id, embedding vector)             -- fase 3
processing_jobs  (id, meeting_id, step, status, attempts, started_at, finished_at, log)
```

---

## 6. Struktur Folder (Monorepo)

```
Noteyourmeet/
├─ PROJECT_PLAN.md          ← dokumen ini
├─ CLAUDE.md                ← instruksi singkat untuk AI assistant
├─ docker-compose.yml
├─ .env.example
├─ apps/
│  ├─ web/                  ← Next.js (PWA)
│  │  ├─ app/               (login, dashboard, meetings/[id], settings)
│  │  ├─ components/        (AudioPlayer, TranscriptView, MinutesEditor, Recorder, UploadDropzone)
│  │  ├─ lib/               (api client, hooks, utils)
│  │  └─ public/manifest.json, service worker
│  └─ api/                  ← FastAPI + Celery worker (satu codebase Python)
│     ├─ app/
│     │  ├─ main.py
│     │  ├─ core/           (config, security, db, storage)
│     │  ├─ models/         (SQLAlchemy)
│     │  ├─ schemas/        (Pydantic: request/response + MinutesSchema)
│     │  ├─ routers/        (auth, meetings, uploads, speakers, minutes, export, events)
│     │  ├─ services/
│     │  │  ├─ transcription/ (base.py = interface, assemblyai.py, whisperx.py)
│     │  │  ├─ audio.py       (ffmpeg)
│     │  │  ├─ analytics.py   (talk-time, speaker count)
│     │  │  ├─ summarizer.py  (Claude)
│     │  │  └─ exporter.py    (md/pdf/docx)
│     │  ├─ prompts/        (template prompt per jenis meeting, file .md)
│     │  └─ workers/        (celery_app.py, pipeline.py)
│     ├─ alembic/
│     └─ tests/             (unit + fixture audio pendek)
└─ infra/
   └─ Caddyfile
```

---

## 7. Cara Coding (Panduan & Contoh Inti)

### 7.1 Prinsip
- **Provider pattern** untuk STT (dan nanti embedding): kode pipeline hanya kenal interface, bukan vendor.
- **Pipeline per langkah, idempotent, hasil disimpan** (lihat 4.2).
- **Jangan proses file di request HTTP** — selalu lewat worker.
- **Rahasia di `.env`** (`ANTHROPIC_API_KEY`, `ASSEMBLYAI_API_KEY`, `DATABASE_URL`, dll.), jangan pernah di-commit.
- **Typed end-to-end**: Pydantic di backend; generate tipe TypeScript dari OpenAPI FastAPI (`openapi-typescript`).
- **Hasil AI selalu bisa diedit** dan diberi versi.
- Tulis test untuk: pipeline (pakai audio 30 detik fixture), parser hasil STT, perhitungan statistik, schema notulen.

### 7.2 Interface Transkripsi
```python
# app/services/transcription/base.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class Segment:
    speaker: str        # "A", "B", ...
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None

@dataclass
class TranscriptionResult:
    language: str
    segments: list[Segment]

class TranscriptionProvider(Protocol):
    def transcribe(self, audio_url: str, *, language: str = "id",
                   vocabulary: list[str] | None = None,
                   expected_speakers: int | None = None) -> TranscriptionResult: ...
```

### 7.3 Statistik peserta (tanpa AI)
```python
from collections import defaultdict

def speaker_stats(segments):
    talk = defaultdict(int); turns = defaultdict(int); prev = None
    for s in segments:
        talk[s.speaker] += s.end_ms - s.start_ms
        if s.speaker != prev:
            turns[s.speaker] += 1
        prev = s.speaker
    total = sum(talk.values()) or 1
    return {
        "speaker_count": len(talk),
        "speakers": [{"label": k, "talk_ms": v, "pct": round(v * 100 / total, 1),
                      "turns": turns[k]} for k, v in sorted(talk.items(), key=lambda x: -x[1])],
    }
```

### 7.4 Notulen dengan Claude (structured output)
```python
# app/services/summarizer.py
import anthropic
from pydantic import BaseModel

class ActionItem(BaseModel):
    task: str
    assignee: str | None          # nama/label speaker
    due: str | None               # sesuai yang diucapkan, mis. "Jumat depan"
    priority: str                 # "tinggi" | "sedang" | "rendah"
    timestamp: str                # "00:12:34" sumber kutipan

class Topic(BaseModel):
    title: str
    start: str
    key_points: list[str]

class Minutes(BaseModel):
    title: str
    executive_summary: str
    topics: list[Topic]
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    risks: list[str]

client = anthropic.Anthropic()  # baca ANTHROPIC_API_KEY dari env

def generate_minutes(transcript_text: str, template_prompt: str, glossary: list[str]) -> Minutes:
    response = client.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        output_config={"effort": "high"},
        system=(
            "Kamu adalah notulis profesional untuk tim internal. Tulis dalam Bahasa Indonesia "
            "yang rapi. Hanya gunakan informasi yang ada di transkrip; jika tidak disebut, "
            "isi null/kosong — jangan mengarang. Sertakan timestamp sumber untuk setiap "
            "keputusan dan action item.\n\n"
            f"Template: {template_prompt}\nGlosarium tim: {', '.join(glossary)}"
        ),
        messages=[{"role": "user", "content": f"<transkrip>\n{transcript_text}\n</transkrip>"}],
        output_format=Minutes,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model menolak memproses transkrip")
    return response.parsed_output
```
Format transkrip yang dikirim ke LLM (ringkas, hemat token):
```
[00:00:05] Budi: Oke kita mulai ya, agenda pertama soal launching.
[00:00:12] Sari: Desain landing page targetnya Jumat.
```
Catatan teknis Claude API (per Nov 2026):
- `claude-opus-5-5`: thinking selalu aktif — atur kedalaman lewat `output_config.effort` (default `medium`), **jangan** kirim `budget_tokens` / `thinking: disabled` (error 400).
- Pertimbangkan parameter `fallbacks` (beta `server-side-fallback-2026-07-01`) agar request yang ditolak classifier otomatis dialihkan.
- Untuk "Tanya AI": taruh transkrip di awal prompt + `cache_control` (prompt caching) supaya pertanyaan berikutnya jauh lebih murah.
- Meeting > ~6 jam pun masih muat di konteks 1M token; tidak perlu chunking untuk notulen.

### 7.5 Upload besar dari HP
- Frontend minta `POST /uploads/init` → API membuat **multipart upload S3** dan mengembalikan presigned URL per part (mis. 10 MB).
- Browser upload part paralel, simpan progres di IndexedDB → bisa **resume** jika sinyal putus.
- `POST /uploads/complete` → API menyelesaikan multipart → enqueue pipeline.
- Recorder PWA: `MediaRecorder` dengan `timeslice` 10 detik, potongan langsung di-upload; minta **Wake Lock API** agar layar tidak mati.

### 7.6 Keamanan & privasi (rekaman meeting = data sensitif)
- Semua endpoint wajib login; cek `team_id` di setiap query.
- Bucket S3 **privat**, akses audio hanya via presigned URL berumur pendek.
- HTTPS wajib (Caddy). Backup Postgres harian.
- Opsi "hapus audio asli setelah X hari" (simpan transkrip saja).
- Cek kebijakan retensi data provider STT/LLM yang dipakai.

---

## 8. Roadmap Pengerjaan

**Fase 0 — Setup**
- [x] Init monorepo + git (belum ada commit), `.gitignore`
- [x] Skeleton FastAPI + healthcheck; Next.js 16 + Tailwind
- [x] `.env.example`, ruff, eslint, pytest
- [x] CI GitHub Actions (`.github/workflows/ci.yml`: ruff + pytest + eslint + tsc, tanpa GPU) — aktif setelah repo di-push ke GitHub
- [ ] docker-compose (ditunda — jalan native Windows dulu), Alembic (pakai `create_all` dulu)

**Fase 1 — Inti pipeline (audio → teks + siapa bicara)**
- [x] Upload file (API simpan ke disk) + model `meetings`, `speakers`, `transcript_segments`
- [x] Worker: ffmpeg → WhisperX (teks, alignment, diarization pyannote) → statistik
- [x] Halaman meeting: progres real-time (polling) + transkrip + player audio (klik → lompat)
- [x] Rename speaker, gabung speaker, pindah kalimat ke speaker lain, cari di transkrip, salin transkrip
- [x] Test otomatis (mode fake) lulus; UI diuji di browser dengan mode fake
- [x] HF_TOKEN terisi & akses model pyannote OK; uji GPU end-to-end (2 suara TTS, 34 dtk): 2 pembicara terdeteksi, 6/6 kalimat benar
- [x] Bug: worker tidak menemukan ffmpeg (terminal lama tanpa PATH baru) → `find_binary()` cari otomatis + `start-dev.ps1` refresh PATH & cegah jalan dobel
- [x] Rekaman asli user (meeting Inggris 43 menit, mp3 61 MB): DONE dalam 16 menit, 7 pembicara, 215 segmen
- [x] Bahasa per meeting: pilihan Indonesia/English/Otomatis saat upload & saat proses ulang (kolom `requested_language`, migrasi otomatis `_add_missing_columns`)
- [x] Tombol Batalkan: antre → langsung batal; sedang diproses → `cancel_requested_at`, worker cek di tiap progres (≈5%) & antar langkah, lalu `CANCELLED` + VRAM dilepas (uji GPU: berhenti 6 dtk, VRAM 432→44 MB). "Paksa batalkan" setelah 60 dtk. Worker restart: yang diminta batal → `CANCELLED`, bukan diantrekan ulang
- [x] Commit pertama ke git
- [x] Uji rekaman meeting Bahasa Indonesia (user, 86 menit Zoom, 7 pembicara): bahasa santai tertangkap baik; masalah = kata/nama salah dengar (mis. "CSILC" → "CS ALC") & kalimat terbelah antar pembicara
- [x] Koreksi transkrip: edit kalimat inline (`original_text` disimpan, bisa dikembalikan), cari & ganti semua (kata utuh, dry-run), **Kosakata tim** (`glossary_terms`, halaman /kosakata) → dikirim ke Whisper sebagai `hotwords` (maks 600 karakter)
- [x] Kalimat terbelah antar pembicara: `absorb_short_runs()` — 1 kalimat Whisper = 1 pembicara; potongan pendek (<3 kata atau <0,7 dtk) di awal/akhir kalimat ikut tetangga, 1 kata yang diapit pembicara sama ikut; obrolan cepat di tengah tetap dipisah. Uji 5 menit rekaman user: 49 → 34 potongan, "Gak | pada puasa", "Kita | buka dulu", "pas / sesi / online" beres. Meeting lama perlu *Proses ulang*
- [x] Worker menyimpan `transcription.json` (kata + speaker mentah) per meeting → kelak bisa "rapikan ulang pembicara" tanpa GPU
- [x] Fondasi pengembangan: log ke file (`data/logs`), backup (`python -m app.backup`), resep pemrosesan per meeting (`processing_info` + "Detail proses" di UI), set uji kualitas (`python -m app.evaluate`: WER & salah pembicara, `--cached` tanpa GPU)
- [x] Push repo ke GitHub (private) `Bgskelvin/noteyourmeet`, branch `main`; riwayat dicek bersih dari .env/token/data
- [x] Sistem belajar dari koreksi: **memori koreksi** (`correction_rules`; "Ganti kata" + opsi Ingat → diterapkan otomatis di pipeline, tanda *otomatis*, endpoint `apply-corrections` untuk meeting lama) + **saran** dari editan manual (`/suggestions`: istilah baru → kosakata, pasangan salah→benar ≤3 kata → aturan; bisa diabaikan). Halaman jadi "Kosakata & koreksi"
- [x] **Mode Periksa** (`/meetings/[id]/periksa`): kalimat per kalimat + audio otomatis, seleksi kata → perbaiki (seluruh meeting / ingat / kosakata), beri nama pembicara di tempat, Enter = benar & lanjut. Tanda `reviewed_at` per kalimat (edit = otomatis diperiksa), progres di halaman meeting & hub "Kosakata & koreksi" (`/review/stats`)
- [x] Ekspor data latihan `python -m app.dataset` (hanya kalimat ✓, 1–30 dtk, format audiofolder HF; target 10 jam ditampilkan di hub)
- [ ] User membuat set uji: 2–3 potongan ±5 menit yang sudah dikoreksi, lalu `evaluate run --note baseline`
- [ ] Fase 3: kenali suara anggota tim (voice enrollment dari pembicara yang sudah dinamai); jangka panjang: fine-tune Whisper bila ≥10 jam koreksi terkumpul (perlu GPU cloud)
- [ ] Auth invite-only (wajib sebelum online)

**Fase 2 — Notulen (± 1 minggu)**
- [ ] `summarizer.py` + schema + template prompt
- [ ] Tab notulen (tampil, edit, versi), action items & keputusan
- [ ] Export MD/PDF/DOCX + copy WhatsApp
- [ ] Recorder PWA di HP + resume upload
- [ ] Deploy ke VPS (Caddy + HTTPS) → **mulai dipakai tim**

**Fase 3 — Pintar (± 2 minggu)**
- [ ] Embedding + pencarian semantik; Tanya AI dengan kutipan timestamp
- [ ] Action item tracker lintas meeting
- [ ] Glosarium tim; voice enrollment

**Fase 4 —** live transcription, integrasi kalender/Slack/Telegram, analitik.

---

## 9. Perkiraan Biaya (kasar, cek harga terbaru)
- Claude Opus 5.5: $4 / 1M token input, $20 / 1M output. Meeting 1 jam ≈ 15–25 rb token input + ~3 rb output → **± $0.10–0.20 per meeting** untuk notulen.
- STT: **Rp0** (WhisperX di GTX 1660 Ti), hanya listrik PC.
- Hosting Tahap A: **Rp0** (PC sendiri + Cloudflare Tunnel/Access gratis). Tahap B: VPS kecil ± Rp100–150 rb/bulan.
- Satu-satunya API key yang wajib: **Anthropic** (console.anthropic.com, isi saldo prabayar). Plus token **Hugging Face** (gratis) untuk pyannote.
- Privasi: audio tetap di PC; yang dikirim ke Claude hanya teks transkrip.

---

## 10. Status & Langkah Berikutnya  ← UPDATE BAGIAN INI SETIAP SESI

**Tanggal update terakhir:** 2026-11-19
**Status:** Fase 1 (audio → teks + siapa bicara) selesai & terbukti jalan di GPU (GTX 1660 Ti, CUDA). `HF_TOKEN` sudah diisi user. Cara jalan: [README.md](README.md) (`start-dev.ps1`).

Fitur Fase 1 lengkap: upload + bahasa per meeting, progres real-time, **batalkan**, proses ulang, transkrip + pembicara (rename/gabung/pindah kalimat), statistik. Kode di git branch `main`, tersimpan di GitHub **private**: https://github.com/Bgskelvin/noteyourmeet (CI jalan otomatis tiap push).

**Alur kerja pengembangan** (detail: README → "Alur kerja pengembangan"): masalah/ide → cek log + Detail proses → perbaiki + tambah test → ukur dengan `app.evaluate` → commit + push (CI) → catat di dokumen ini.

**Urutan kerja yang disepakati (2026-11-18):**
1. ~~Rapikan: tombol Batalkan + commit git~~ ✅
2. ~~User uji rekaman meeting Bahasa Indonesia~~ ✅ → ditambah edit kalimat, cari & ganti, Kosakata tim (hotwords). User perlu mengisi Kosakata tim (nama anggota, singkatan, produk).
3. **Fase 2: notulen dengan Claude** — user perlu API key Anthropic + saldo (± $5 cukup puluhan meeting).
4. Export & berbagi (copy WhatsApp, Markdown, Word, PDF).
5. Login undangan-saja + online via Cloudflare Tunnel.
6. Fase 3 (Tanya AI, pencarian lintas meeting, tracker action item, pengenalan suara). Rekam langsung dari browser HP diprioritaskan rendah (tim bisa rekam pakai app recorder HP lalu upload).

**Catatan teknis:** warning `libtorchcodec ... could not load` & `symlinks on Windows` aman diabaikan (audio dikirim sebagai array, bukan file).

**Fakta yang sudah diketahui:**
- GPU: NVIDIA GTX 1660 Ti (6 GB VRAM) di PC Windows → STT self-host (WhisperX).
- Jumlah peserta meeting acak → deteksi otomatis + fitur gabung speaker + hint min/maks opsional.
- Deploy: Tahap A di PC sendiri + Cloudflare Tunnel; Tahap B (opsional) VPS + worker GPU di PC.

**Yang perlu disiapkan user:**
- [ ] API key Anthropic (console.anthropic.com)
- [x] Akun & token Hugging Face (sudah, model `pyannote/speaker-diarization-community-1`)
- [x] Akun GitHub + repo private (`Bgskelvin/noteyourmeet`)
- [ ] (Nanti, saat deploy) Docker Desktop (WSL2) — belum perlu selama jalan native
- [ ] (Saat deploy) akun Cloudflare + domain (bisa domain murah)

**Pertanyaan terbuka:** rata-rata durasi & jumlah meeting per minggu (untuk estimasi antrean GPU).

## 11. Log Keputusan
| Tanggal | Keputusan | Alasan |
|---|---|---|
| 2026-11-18 | Stack: Next.js PWA + FastAPI + Celery/Redis + Postgres/pgvector + S3/MinIO | Lihat bagian 2 |
| 2026-11-18 | ~~STT default AssemblyAI~~ → **STT self-host WhisperX di GTX 1660 Ti** (interface tetap, API sebagai cadangan) | User punya GPU; gratis & privat |
| 2026-11-18 | Deploy Tahap A: PC sendiri + Cloudflare Tunnel/Access; Tahap B: VPS + worker GPU di PC via Tailscale | Biaya nol di awal, bisa naik kelas tanpa ubah arsitektur |
| 2026-11-18 | Fitur gabung/pisah speaker + hint jumlah peserta | Jumlah peserta tiap meeting acak |
| 2026-11-18 | Jalan native di Windows; SQLite + antrean di tabel DB (tanpa Celery/Redis); file di disk lokal | Pemakaian kecil, PC belum ada Docker; lebih sedikit komponen. Upgrade ke Postgres/S3/Docker saat deploy |
| 2026-11-18 | Login ditunda sampai sebelum online | Fokus pipeline dulu; hanya diakses dari PC sendiri |
| 2026-11-18 | Pembatalan kooperatif (flag di DB + titik cek di callback progres), `Cancelled` turunan `BaseException` | Tanpa membunuh proses worker; tidak tertelan `except Exception` di library; VRAM bisa dilepas rapi |
| 2026-11-18 | Pembagian pembicara: per kalimat Whisper, bukan per kata mentah | Diarization meleset ±0,5 dtk di batas giliran → kata pertama/terakhir sering ikut orang sebelumnya. Dibuktikan pada rekaman user |
| 2026-11-18 | Kualitas diukur dengan set uji (WER + salah pembicara berbasis waktu, pemetaan label via overlap) dari potongan meeting asli yang dikoreksi user | Perubahan model/kosakata/aturan dinilai dengan angka. Uji GPU: potongan 1 menit diproses sendiri hanya terdeteksi 2 dari 5 pembicara → potongan uji harus ±5 menit &/atau isi min/maks peserta |
| 2026-11-19 | "Belajar" = memori koreksi + saran yang DISETUJUI user, bukan otomatis penuh; model Whisper/pyannote tidak dilatih ulang | Model pretrained tidak belajar dari pemakaian. Pasangan dari editan bisa berbahaya bila diterapkan buta (mis. "Tuh→Dua", kata umum) → selalu lewat persetujuan. Fine-tuning butuh ≥10 jam data terkoreksi & GPU lebih besar |
| 2026-11-19 | Koreksi dipusatkan di "Mode Periksa" per kalimat + penanda `reviewed_at` | Satu layar untuk dengar–perbaiki–beri nama; penanda membedakan "sudah benar" vs "belum dicek" sehingga hanya data terperiksa yang dipakai untuk set uji & fine-tune |
| 2026-11-18 | Migrasi skema sederhana `_add_missing_columns()` (tambah kolom nullable) alih-alih Alembic | Cukup untuk SQLite & perubahan kecil; pindah ke Alembic saat ke Postgres |
| 2026-11-18 | LLM notulen: `claude-opus-5-5`, tugas ringan `claude-haiku-5-5` | Kualitas + konteks 1M |
| 2026-11-18 | Kosakata tim global dipakai sebagai `hotwords` (bukan `initial_prompt`); model tetap `large-v3-turbo` | Uji 3 menit rekaman Indonesia user: hotwords membetulkan "CSILC"→"CS ALC" tanpa halusinasi, tapi tanda baca berkurang; initial_prompt → tanda baca rapi tapi 30 dtk pertama jadi halusinasi "Terima kasih ×3" (isi hilang). large-v3: "2 menit" benar tapi istilah Inggris lebih buruk ("kanva", "disep") & ±1,5× lebih lambat. Nanti juga dipakai di prompt notulen Claude |
