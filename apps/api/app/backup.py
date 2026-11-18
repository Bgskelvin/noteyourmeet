"""Backup database + data meeting ke satu file zip.

Pakai (dari folder apps/api):
    .venv\\Scripts\\python -m app.backup                         # ke data/backups (disk yang sama)
    .venv\\Scripts\\python -m app.backup --dest "D:\\Backup NYM"   # sebaiknya disk lain / OneDrive / GDrive
    .venv\\Scripts\\python -m app.backup --with-audio            # ikut rekaman asli (besar)

Restore: tutup aplikasi, ekstrak isi zip ke folder apps/api/data (timpa), jalankan lagi.
"""

import argparse
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import get_settings


def make_backup(dest: Path, *, with_audio: bool = False, keep: int = 10) -> Path:
    s = get_settings()
    if not s.db_url.startswith("sqlite"):
        raise SystemExit("Backup otomatis ini hanya untuk SQLite. Untuk Postgres gunakan pg_dump.")
    db_path = s.data_dir / "noteyourmeet.db"
    if not db_path.exists():
        raise SystemExit(f"Database tidak ditemukan: {db_path}")

    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"noteyourmeet-{datetime.now():%Y%m%d-%H%M%S}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        # Salin DB lewat API backup SQLite → aman walau API/worker sedang berjalan
        snap = Path(tmp) / "noteyourmeet.db"
        src, dst = sqlite3.connect(db_path), sqlite3.connect(snap)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "noteyourmeet.db")
            meetings = s.storage_dir / "meetings"
            for f in sorted(meetings.rglob("*")) if meetings.exists() else []:
                if not f.is_file():
                    continue
                is_audio = f.name.startswith("original") or f.name == "processed.wav"
                if is_audio and not (with_audio and f.name.startswith("original")):
                    continue  # processed.wav selalu bisa dibuat ulang dari original
                z.write(f, f.relative_to(s.data_dir).as_posix())

    # Simpan hanya `keep` backup terbaru di folder tujuan
    olds = sorted(dest.glob("noteyourmeet-*.zip"))[:-keep] if keep > 0 else []
    for old in olds:
        old.unlink()
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Backup data NoteYourMeet ke file zip")
    p.add_argument("--dest", type=Path, default=None, help="Folder tujuan (default: data/backups)")
    p.add_argument("--with-audio", action="store_true", help="Ikutkan file rekaman asli")
    p.add_argument("--keep", type=int, default=10, help="Jumlah backup terbaru yang disimpan (default 10)")
    a = p.parse_args()
    dest = a.dest or get_settings().data_dir / "backups"
    out = make_backup(dest, with_audio=a.with_audio, keep=a.keep)
    print(f"Backup selesai: {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
