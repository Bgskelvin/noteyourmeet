import os
import shutil
import tempfile
from pathlib import Path

# Harus di-set sebelum modul app diimpor (settings di-cache)
_tmp = Path(tempfile.mkdtemp(prefix="nym-test-"))
os.environ["DATA_DIR"] = str(_tmp)
os.environ["DATABASE_URL"] = ""
os.environ["TRANSCRIPTION_PROVIDER"] = "fake"

if not shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg")):
    # Lokasi default winget di Windows bila PATH belum di-refresh
    pkgs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    for exe in pkgs.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
        os.environ["FFMPEG_BIN"] = str(exe)
        os.environ["FFPROBE_BIN"] = str(exe.with_name("ffprobe.exe"))
        break
