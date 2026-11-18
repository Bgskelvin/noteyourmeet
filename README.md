# NoteYourMeet

Rekaman meeting → **transkrip** + **siapa yang berbicara** + statistik pembicara. Berjalan di PC sendiri dengan GPU NVIDIA.
Rencana lengkap & status: [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Struktur

```
apps/api   Backend FastAPI + worker GPU (Python 3.12, WhisperX, SQLite)
apps/web   Frontend Next.js (React, Tailwind)
```

Alur: Web upload → API simpan file + buat meeting `QUEUED` → **worker** ambil antrean → ffmpeg → WhisperX
(teks → timestamp per kata → deteksi pembicara) → statistik → `DONE`.

## Persiapan (sekali saja)

1. **Token Hugging Face (gratis)** — dibutuhkan untuk deteksi pembicara:
   - Daftar di https://huggingface.co → *Settings → Access Tokens* → buat token tipe **Read**.
   - Buka https://huggingface.co/pyannote/speaker-diarization-community-1, isi form, klik **Agree**.
2. Salin `apps/api/.env.example` menjadi `apps/api/.env`, lalu isi `HF_TOKEN=...`.

Instalasi dari nol (sudah dilakukan di PC ini):

```powershell
winget install -e --id Python.Python.3.12 --scope user
winget install -e --id Gyan.FFmpeg
cd apps\api
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-worker.txt -r requirements-dev.txt
# PyTorch versi CUDA (yang dari PyPI hanya CPU):
.venv\Scripts\python -m pip install --force-reinstall --no-deps torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
cd ..\web
npm install
```

## Menjalankan

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

Ini membuka 3 jendela: **API** (port 8000), **Worker GPU**, **Web** (port 3000). Buka http://localhost:3000.
Dokumentasi API: http://localhost:8000/docs.

Pertama kali memproses, worker mengunduh model (±3 GB total) ke cache Hugging Face — sekali saja.

### Memperbaiki kata yang salah
- **Edit satu kalimat:** arahkan kursor ke kalimat → klik **✎ Edit** → Enter untuk simpan. Teks asli AI tetap tersimpan (tanda *diedit*, bisa *Kembalikan teks asli*).
- **Ganti kata di seluruh transkrip:** klik **Ganti kata**, isi kata yang salah & yang benar → **Ganti semua**.
- **Kosakata tim** (menu atas): daftar nama orang, singkatan, istilah. Whisper memprioritaskan ejaan ini
  untuk meeting yang diproses berikutnya — mencegah kesalahan yang sama terulang.

### Membatalkan proses
Di halaman meeting yang sedang diproses, klik **Batalkan**. Worker berhenti di titik cek berikutnya
(biasanya beberapa detik; teruji: 6 dtk saat transkripsi 40%), GPU dibebaskan, status jadi **Dibatalkan**.
Setelah itu bisa **Proses lagi** (boleh ganti bahasa) atau **Hapus**.
Jika worker tidak berjalan/tidak merespons selama 60 dtk, muncul tombol **Paksa batalkan**.

> Setelah update kode backend, **restart jendela Worker** (API & Web memuat ulang sendiri).

### Coba tanpa GPU
Set `TRANSCRIPTION_PROVIDER=fake` di `apps/api/.env` → worker menghasilkan transkrip contoh.

## Pengaturan penting (`apps/api/.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `WHISPER_MODEL` | `large-v3-turbo` | Cepat & akurat. `large-v3` sedikit lebih akurat tapi lebih lambat. |
| `WHISPER_COMPUTE_TYPE` | `int8_float16` | Jika hasil kosong/aneh di GTX 16xx, ganti `int8`. |
| `WHISPER_BATCH_SIZE` | `4` | Turunkan ke 2 jika muncul *CUDA out of memory*. |
| `WHISPER_LANGUAGE` | `id` | `auto` untuk deteksi otomatis. |

## Test

```powershell
cd apps\api; .venv\Scripts\python -m pytest
cd apps\web; npm run lint
```
Di GitHub, test yang sama berjalan otomatis setiap `git push` (`.github/workflows/ci.yml`, tanpa GPU).

## Alur kerja pengembangan

```
Ada masalah / ide
  → lihat log (apps/api/data/logs/) + "Detail proses" di halaman meeting
  → perbaiki kode + tambah test untuk kasus itu
  → ukur dengan set uji kualitas → angkanya membaik?
  → commit + git push → test otomatis di GitHub
  → catat di PROJECT_PLAN.md (status & log keputusan)
```

### Log
API & worker menulis log ke `apps/api/data/logs/api.log` dan `worker.log` (maks 5 MB × 6 file, dirotasi).
Saat melaporkan error, lampirkan bagian log di sekitar waktu kejadian.

### Detail proses per meeting
Di bawah halaman meeting ada **Detail proses**: model, pengaturan, bahasa, kosakata, versi kode (commit git),
dan durasi tiap langkah. Gunakan untuk tahu *kenapa* sebuah hasil berbeda dari yang lain.

### Set uji kualitas (angka, bukan perasaan)
1. Pilih potongan **±5 menit** (lebih panjang lebih baik untuk menilai pembicara) dari meeting asli,
   lalu **koreksi sampai benar** di aplikasi: teks (✎ Edit / Ganti kata) dan pembicara (nama, gabung, pindah kalimat).
2. Jadikan acuan:
   ```powershell
   cd apps\api; .venv\Scripts\python -m app.evaluate add 2 --start 1:40 --end 6:40 --name alc-pembukaan
   ```
3. Ukur (pakai GPU): `.venv\Scripts\python -m app.evaluate run --note "baseline"`
4. Setelah mengubah pengaturan/kosakata/model, ukur lagi dengan `--note` berbeda dan bandingkan:
   `.venv\Scripts\python -m app.evaluate history`
5. Jika yang diubah **hanya aturan pembagian pembicara**, pakai `--cached` (tanpa GPU, beberapa detik).

Skor: **Salah kata** (WER) dan **Salah pembicara** (% waktu bicara yang diberikan ke orang yang salah) — makin kecil makin baik.
Data set uji di `apps/api/data/evalset/` — berisi rekaman pribadi, **tidak** ikut git.

### Backup
```powershell
cd apps\api
.venv\Scripts\python -m app.backup --dest "D:\Backup NYM"      # sebaiknya disk lain / folder OneDrive / Google Drive
.venv\Scripts\python -m app.backup --dest "D:\Backup NYM" --with-audio   # ikut rekaman asli (besar)
```
Berisi database, transkrip mentah, dan (opsional) rekaman asli; menyimpan 10 backup terbaru.
**Restore:** tutup aplikasi → ekstrak zip ke `apps/api/data` → jalankan lagi.

## Masalah umum

- **`HF_TOKEN belum diisi`** → isi token di `apps/api/.env`, restart worker, klik *Coba lagi*.
- **Error 401/403 dari Hugging Face** → belum klik *Agree* di halaman model pyannote.
- **CUDA out of memory** → `WHISPER_BATCH_SIZE=2`, tutup aplikasi lain yang memakai GPU (game, browser dengan akselerasi berat).
- **Meeting macet di "Antre"** → jendela Worker belum jalan.
