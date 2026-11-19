"""Ekspor kalimat yang SUDAH DIPERIKSA menjadi dataset latihan (potongan audio + teks yang benar).

Pakai (dari folder apps/api):
    .venv\\Scripts\\python -m app.dataset stats
    .venv\\Scripts\\python -m app.dataset export --dest "D:\\dataset-nym"

Format: "audiofolder" ala Hugging Face — folder audio/*.wav + metadata.jsonl
(file_name, text, speaker, meeting_id, start_ms, end_ms, language). Bisa langsung dipakai
untuk fine-tune Whisper (mis. di Google Colab / GPU sewaan) ketika data sudah ± 10 jam.
Hanya kalimat yang ditandai "sudah diperiksa" yang diekspor — kesalahan AI tidak ikut jadi bahan latihan.
"""

import argparse
import json
import wave
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import Meeting, MeetingStatus, Speaker, TranscriptSegment

MIN_MS = 1_000  # terlalu pendek → tidak berguna untuk latihan
MAX_MS = 30_000  # Whisper memproses maksimal 30 dtk per potongan
TARGET_HOURS = 10


def _reviewed(db):
    return db.execute(
        select(TranscriptSegment, Meeting, Speaker.display_name)
        .join(Meeting, Meeting.id == TranscriptSegment.meeting_id)
        .outerjoin(Speaker, Speaker.id == TranscriptSegment.speaker_id)
        .where(TranscriptSegment.reviewed_at.is_not(None), Meeting.status == MeetingStatus.DONE)
        .order_by(Meeting.id, TranscriptSegment.start_ms)
    ).all()


def stats() -> dict:
    init_db()
    with SessionLocal() as db:
        rows = _reviewed(db)
    usable = [s for s, _, _ in rows if MIN_MS <= s.end_ms - s.start_ms <= MAX_MS]
    total_ms = sum(s.end_ms - s.start_ms for s in usable)
    return {
        "reviewed_segments": len(rows),
        "usable_segments": len(usable),
        "usable_minutes": round(total_ms / 60_000, 1),
        "target_hours": TARGET_HOURS,
        "progress_pct": round(total_ms / (TARGET_HOURS * 3_600_000) * 100, 1),
    }


def export(dest: Path) -> dict:
    s = get_settings()
    init_db()
    audio_dir = dest / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    total_ms = 0
    open_wavs: dict[str, wave.Wave_read] = {}
    try:
        with SessionLocal() as db, (dest / "metadata.jsonl").open("w", encoding="utf-8") as meta:
            for seg, m, speaker in _reviewed(db):
                dur = seg.end_ms - seg.start_ms
                if not (MIN_MS <= dur <= MAX_MS) or not m.processed_audio_path:
                    skipped += 1
                    continue
                src_path = s.storage_dir / m.processed_audio_path
                if not src_path.exists():
                    skipped += 1
                    continue
                key = str(src_path)
                if key not in open_wavs:
                    open_wavs[key] = wave.open(key, "rb")
                src = open_wavs[key]
                rate = src.getframerate()
                first = seg.start_ms * rate // 1000
                last = min(seg.end_ms * rate // 1000, src.getnframes())  # timestamp bisa melewati akhir audio
                if last - first < MIN_MS * rate // 1000:
                    skipped += 1
                    continue
                src.setpos(first)
                frames = src.readframes(last - first)
                dur = (last - first) * 1000 // rate
                name = f"m{m.id}_s{seg.id}.wav"
                with wave.open(str(audio_dir / name), "wb") as out:
                    out.setparams(src.getparams())
                    out.writeframes(frames)
                meta.write(json.dumps({
                    "file_name": f"audio/{name}", "text": seg.text, "speaker": speaker,
                    "meeting_id": m.id, "start_ms": seg.start_ms, "end_ms": seg.end_ms,
                    "language": m.language,
                }, ensure_ascii=False) + "\n")
                written += 1
                total_ms += dur
    finally:
        for w in open_wavs.values():
            w.close()
    return {"written": written, "skipped": skipped, "minutes": round(total_ms / 60_000, 1), "dest": str(dest)}


def main() -> None:
    p = argparse.ArgumentParser(description="Dataset latihan dari kalimat yang sudah diperiksa")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats", help="Berapa banyak data latihan yang sudah terkumpul")
    e = sub.add_parser("export", help="Ekspor potongan audio + teks ke sebuah folder")
    e.add_argument("--dest", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "stats":
        st = stats()
        print(f"Kalimat diperiksa: {st['reviewed_segments']} (layak latihan: {st['usable_segments']})")
        print(f"Durasi layak latihan: {st['usable_minutes']} menit"
              f" = {st['progress_pct']}% dari target {TARGET_HOURS} jam")
    else:
        r = export(a.dest)
        print(f"Selesai: {r['written']} potongan ({r['minutes']} menit) → {r['dest']}  (dilewati: {r['skipped']})")


if __name__ == "__main__":
    main()
