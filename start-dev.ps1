# Menjalankan NoteYourMeet untuk development: API, worker GPU, dan web — masing-masing di jendela sendiri.
# Pakai:  powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
# Ambil PATH terbaru dari Windows (agar program yang baru di-install, mis. ffmpeg, langsung terdeteksi)
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

# Cegah jalan dobel: kalau API sudah aktif di port 8000, jangan buka jendela baru
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Write-Warning "NoteYourMeet sepertinya sudah berjalan (port 8000 terpakai). Tutup jendela 'NYM API', 'NYM Worker (GPU)', 'NYM Web' dulu jika ingin restart."
    exit 1
}

$root = $PSScriptRoot
$api = Join-Path $root "apps\api"
$web = Join-Path $root "apps\web"
$py = Join-Path $api ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) { Write-Error "Virtualenv belum ada. Lihat README bagian Instalasi."; exit 1 }
if (-not (Test-Path (Join-Path $api ".env"))) { Copy-Item (Join-Path $api ".env.example") (Join-Path $api ".env"); Write-Host "apps\api\.env dibuat dari contoh - isi HF_TOKEN dulu." }
if (-not (Test-Path (Join-Path $web "node_modules"))) { Push-Location $web; npm install; Pop-Location }

Start-Process powershell -WorkingDirectory $api -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='NYM API'; & '$py' -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -WorkingDirectory $api -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='NYM Worker (GPU)'; & '$py' -m app.worker"
Start-Process powershell -WorkingDirectory $web -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='NYM Web'; npm run dev"

Write-Host "Buka http://localhost:3000  (API: http://localhost:8000/docs)"
