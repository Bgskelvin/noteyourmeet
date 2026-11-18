"""Provider palsu untuk mengembangkan UI / test tanpa GPU. Set TRANSCRIPTION_PROVIDER=fake."""

from pathlib import Path

from app.services.transcription.base import ProgressFn, Segment, TranscriptionResult

_LINES = [
    ("SPEAKER_00", "Oke, kita mulai ya. Agenda pertama soal persiapan launching."),
    ("SPEAKER_01", "Desain landing page targetnya selesai hari Jumat."),
    ("SPEAKER_00", "Siap. Budget iklan bagaimana?"),
    ("SPEAKER_02", "Masih menunggu persetujuan, mungkin minggu depan."),
    ("SPEAKER_01", "Kalau begitu saya siapkan dua opsi materi iklan dulu."),
]


class FakeProvider:
    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        min_speakers: int | None,
        max_speakers: int | None,
        hotwords: list[str] | None = None,
        on_progress: ProgressFn,
    ) -> TranscriptionResult:
        on_progress("Transkripsi palsu (mode fake)")
        segs, t = [], 0
        for spk, text in _LINES:
            dur = 1000 + 300 * len(text.split())
            segs.append(Segment(speaker=spk, start_ms=t, end_ms=t + dur, text=text))
            t += dur + 400
        return TranscriptionResult(language=language if language and language != "auto" else "id", segments=segs)
