import json
import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

from app.config import get_settings


class AudioError(RuntimeError):
    pass


@cache
def find_binary(configured: str) -> str:
    """Cari ffmpeg/ffprobe: path dari .env → PATH → lokasi install winget / umum di Windows.

    Penting karena terminal yang dibuka sebelum ffmpeg di-install belum punya PATH terbaru.
    """
    if Path(configured).is_file() or shutil.which(configured):
        return configured
    name = Path(configured).stem  # "ffmpeg" / "ffprobe"
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates += Path(local, "Microsoft", "WinGet", "Links").glob(f"{name}.exe")
        candidates += sorted(Path(local, "Microsoft", "WinGet", "Packages").glob(f"*FFmpeg*/*/bin/{name}.exe"))
    for base in (r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin", r"C:\ProgramData\chocolatey\bin"):
        candidates.append(Path(base, f"{name}.exe"))
    for c in candidates:
        if c.is_file():
            return str(c)
    return configured  # biarkan _run memberi pesan error yang jelas


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [find_binary(cmd[0]), *cmd[1:]]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
    except FileNotFoundError as e:
        raise AudioError(
            f"Program tidak ditemukan: {cmd[0]}. Install ffmpeg (winget install Gyan.FFmpeg) "
            "atau isi path lengkapnya di FFMPEG_BIN/FFPROBE_BIN pada apps/api/.env"
        ) from e
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip().splitlines()[-5:]
        raise AudioError("ffmpeg gagal: " + " | ".join(tail)) from e


def probe_duration(path: Path) -> float:
    s = get_settings()
    out = _run([s.ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError) as e:
        raise AudioError("File tidak berisi audio yang bisa dibaca") from e


def to_wav_16k_mono(src: Path, dst: Path) -> None:
    """Konversi format apa pun (m4a, mp3, opus, mp4, ...) ke WAV 16 kHz mono + normalisasi volume."""
    s = get_settings()
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    _run([
        s.ffmpeg_bin, "-hide_banner", "-y", "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000",
        "-af", "loudnorm=I=-18:TP=-2:LRA=11",
        "-c:a", "pcm_s16le", str(tmp),
    ])
    tmp.replace(dst)
