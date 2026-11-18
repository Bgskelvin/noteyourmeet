"""Set uji kualitas: ukur akurasi transkrip & pembicara dengan angka, bukan perasaan.

Langkah (dari folder apps/api, aplikasi boleh tetap berjalan):

1. Pilih ±5 menit dari meeting asli, lalu KOREKSI di aplikasi: teks (✎ Edit / Ganti kata) dan
   pembicara (ganti nama, gabung, pindah kalimat) sampai benar-benar sesuai rekaman.
2. Jadikan acuan:
       .venv\\Scripts\\python -m app.evaluate add 2 --start 1:40 --end 6:40 --name alc-pembukaan
3. Ukur dengan pengaturan sekarang (pakai GPU, ± 1–2 menit per potongan):
       .venv\\Scripts\\python -m app.evaluate run --note "baseline"
   Setelah mengubah aturan pembicara saja (tanpa GPU, hitungan detik):
       .venv\\Scripts\\python -m app.evaluate run --cached --note "aturan baru"
4. Lihat riwayat skor:
       .venv\\Scripts\\python -m app.evaluate history

Data set uji ada di apps/api/data/evalset (rekaman pribadi → TIDAK ikut git).
"""

import argparse
import csv
import json
import sys
import wave
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import GlossaryTerm, Meeting, Speaker, TranscriptSegment
from app.services.metrics import TimedSpeech, speaker_error, word_error_rate
from app.services.speakers import process_segments
from app.services.transcription.base import Segment, Word
from app.version import code_version

RESULT_FIELDS = [
    "waktu", "item", "wer_pct", "speaker_err_pct", "ref_spk", "hyp_spk", "ref_words",
    "salah_ganti", "hilang", "berlebih", "model", "compute_type", "kosakata", "cached", "kode", "catatan",
]


def evalset_dir() -> Path:
    d = get_settings().data_dir / "evalset"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_time(t: str) -> int:
    """'1:40' / '01:02:03' / '100' (detik) → milidetik."""
    sec = 0.0
    for part in t.split(":"):
        sec = sec * 60 + float(part)
    return int(sec * 1000)


# ---------- add ----------

def cmd_add(meeting_id: int, start: str, end: str, name: str | None) -> None:
    s = get_settings()
    init_db()
    a, b = parse_time(start), parse_time(end)
    if b - a < 30_000:
        sys.exit("Potongan minimal 30 detik (disarankan 3–5 menit).")
    with SessionLocal() as db:
        m = db.get(Meeting, meeting_id)
        if m is None or not m.processed_audio_path:
            sys.exit(f"Meeting {meeting_id} tidak ada / belum selesai diproses.")
        names = {sp.id: sp.display_name for sp in db.scalars(select(Speaker).where(Speaker.meeting_id == m.id))}
        segs = db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == m.id)
            .where(TranscriptSegment.start_ms >= a, TranscriptSegment.start_ms < b)
            .order_by(TranscriptSegment.start_ms)
        ).all()
        if not segs:
            sys.exit("Tidak ada kalimat di rentang waktu itu.")
        name = name or f"meeting{m.id}-{a // 1000}s"
        out = evalset_dir() / name
        out.mkdir(parents=True, exist_ok=True)

        with wave.open(str(s.storage_dir / m.processed_audio_path), "rb") as src:
            rate = src.getframerate()
            src.setpos(a * rate // 1000)
            frames = src.readframes((b - a) * rate // 1000)
            with wave.open(str(out / "audio.wav"), "wb") as dst:
                dst.setparams(src.getparams())
                dst.writeframes(frames)

        reference = {
            "meeting_id": m.id, "meeting_title": m.title, "start_ms": a, "end_ms": b,
            "language": m.requested_language or m.language, "min_speakers": m.min_speakers,
            "max_speakers": m.max_speakers,
            "segments": [
                {"speaker": names.get(sg.speaker_id, "?"), "start_ms": sg.start_ms - a,
                 "end_ms": min(sg.end_ms, b) - a, "text": sg.text}
                for sg in segs
            ],
        }
        (out / "reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=1), encoding="utf-8")
        edited = sum(1 for sg in segs if sg.original_text is not None)
        default_names = sum(1 for n in {names.get(sg.speaker_id) for sg in segs} if (n or "").startswith("Pembicara "))
    print(f"Ditambahkan: {out}  ({len(segs)} kalimat, {(b - a) / 60000:.1f} menit, {edited} kalimat sudah dikoreksi)")
    if edited == 0:
        print("⚠ Belum ada kalimat yang dikoreksi. Acuan harus transkrip yang BENAR —"
              " koreksi dulu di aplikasi, lalu 'add' ulang.")
    if default_names:
        print("⚠ Masih ada nama 'Pembicara X'. Ganti ke nama asli agar mudah dibaca (tidak memengaruhi skor).")


# ---------- run ----------

def _segments_from_json(items: list[dict]) -> list[Segment]:
    return [
        Segment(d["speaker"], d["start_ms"], d["end_ms"], d["text"], d.get("confidence"),
                [Word(**w) for w in d.get("words", [])])
        for d in items
    ]


def cmd_run(cached: bool, note: str, only: str | None) -> None:
    from dataclasses import asdict

    s = get_settings()
    init_db()
    items = sorted(p for p in evalset_dir().iterdir() if (p / "reference.json").exists())
    if only:
        items = [p for p in items if p.name == only]
    if not items:
        sys.exit("Set uji masih kosong. Tambahkan dulu: python -m app.evaluate add <meeting_id> --start .. --end ..")
    with SessionLocal() as db:
        hotwords = list(db.scalars(select(GlossaryTerm.term).order_by(GlossaryTerm.term)))

    provider = None
    rows = []
    for item in items:
        ref = json.loads((item / "reference.json").read_text(encoding="utf-8"))
        raw_path = item / "hypothesis_raw.json"
        if cached and raw_path.exists():
            raw = _segments_from_json(json.loads(raw_path.read_text(encoding="utf-8")))
        else:
            if cached:
                print(f"[{item.name}] belum ada hasil tersimpan → transkripsi ulang")
            if provider is None:
                from app.services.transcription import get_provider

                provider = get_provider()
            print(f"[{item.name}] transkripsi…", flush=True)
            res = provider.transcribe(
                item / "audio.wav", language=ref.get("language") or s.whisper_language,
                min_speakers=ref.get("min_speakers"), max_speakers=ref.get("max_speakers"),
                hotwords=hotwords, on_progress=lambda _d: None,
            )
            raw = res.segments
            raw_path.write_text(json.dumps([asdict(x) for x in raw], ensure_ascii=False), encoding="utf-8")

        hyp, _ = process_segments(raw)
        ref_segs = ref["segments"]
        w = word_error_rate(" ".join(x["text"] for x in ref_segs), " ".join(x.text for x in hyp))
        sp = speaker_error(
            [TimedSpeech(x["speaker"], x["start_ms"], x["end_ms"]) for x in ref_segs],
            [TimedSpeech(x.speaker, x.start_ms, x.end_ms) for x in hyp],
        )
        (item / "hypothesis.txt").write_text(
            "\n".join(f"[{x.start_ms / 1000:7.1f}] {sp.mapping.get(x.speaker, x.speaker)}: {x.text}" for x in hyp),
            encoding="utf-8",
        )
        rows.append({
            "waktu": datetime.now().isoformat(timespec="seconds"), "item": item.name,
            "wer_pct": round(w.wer * 100, 1), "speaker_err_pct": round(sp.error * 100, 1),
            "ref_spk": sp.ref_speakers, "hyp_spk": sp.hyp_speakers, "ref_words": w.ref_words,
            "salah_ganti": w.substitutions, "hilang": w.deletions, "berlebih": w.insertions,
            "model": s.whisper_model, "compute_type": s.whisper_compute_type, "kosakata": len(hotwords),
            "cached": cached, "kode": code_version(), "catatan": note,
        })

    results = evalset_dir() / "results.csv"
    new = not results.exists()
    with results.open("a", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if new:
            wr.writeheader()
        wr.writerows(rows)

    print(f"\n{'Potongan':<28}{'Salah kata':>11}{'Salah pembicara':>17}{'Pembicara (acuan→hasil)':>26}")
    for r in rows:
        print(f"{r['item']:<28}{r['wer_pct']:>10}%{r['speaker_err_pct']:>16}%{r['ref_spk']:>18} → {r['hyp_spk']}")
    if len(rows) > 1:
        avg = lambda k: round(sum(r[k] for r in rows) / len(rows), 1)  # noqa: E731
        print(f"{'RATA-RATA':<28}{avg('wer_pct'):>10}%{avg('speaker_err_pct'):>16}%")
    print(f"\nTersimpan di {results}. Detail hasil per potongan: <potongan>/hypothesis.txt")


def cmd_history(last: int) -> None:
    results = evalset_dir() / "results.csv"
    if not results.exists():
        sys.exit("Belum ada hasil. Jalankan: python -m app.evaluate run")
    rows = list(csv.DictReader(results.open(encoding="utf-8")))[-last:]
    print(f"{'waktu':<20}{'potongan':<24}{'kata%':>7}{'spk%':>7}  {'model':<16}{'kosakata':>9}  {'kode':<18}catatan")
    for r in rows:
        print(f"{r['waktu']:<20}{r['item']:<24}{r['wer_pct']:>7}{r['speaker_err_pct']:>7}  {r['model']:<16}"
              f"{r['kosakata']:>9}  {r['kode'] or '-':<18}{r['catatan']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Set uji kualitas transkrip NoteYourMeet")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="Jadikan potongan meeting (yang sudah dikoreksi) sebagai acuan")
    a.add_argument("meeting_id", type=int)
    a.add_argument("--start", required=True, help="mis. 1:40")
    a.add_argument("--end", required=True, help="mis. 6:40")
    a.add_argument("--name", help="nama potongan (default: meeting<id>-<detik>s)")
    r = sub.add_parser("run", help="Ukur akurasi dengan pengaturan sekarang")
    r.add_argument("--cached", action="store_true", help="Pakai hasil transkripsi terakhir (tanpa GPU)")
    r.add_argument("--note", default="", help="Catatan perubahan yang sedang diuji")
    r.add_argument("--only", help="Hanya potongan dengan nama ini")
    h = sub.add_parser("history", help="Lihat riwayat skor")
    h.add_argument("--last", type=int, default=20)
    args = p.parse_args()
    if args.cmd == "add":
        cmd_add(args.meeting_id, args.start, args.end, args.name)
    elif args.cmd == "run":
        cmd_run(args.cached, args.note, args.only)
    else:
        cmd_history(args.last)


if __name__ == "__main__":
    main()
