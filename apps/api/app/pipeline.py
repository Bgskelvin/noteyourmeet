"""Pipeline pemrosesan satu meeting. Tiap langkah menyimpan hasilnya, jadi bisa diulang dengan aman."""

import gc
import json
import logging
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    PROCESSING_STATUSES,
    GlossaryTerm,
    Meeting,
    MeetingStatus,
    Speaker,
    TranscriptSegment,
    utcnow,
)
from app.services import audio
from app.services.speakers import MIN_RUN_MS, MIN_RUN_WORDS, process_segments
from app.services.transcription import TranscriptionProvider, get_provider
from app.version import code_version

log = logging.getLogger(__name__)


class Cancelled(BaseException):  # BaseException: tidak tertelan "except Exception" di library
    """User menekan Batalkan; dilempar dari titik cek agar proses berhenti dengan rapi."""


def _set(db: Session, m: Meeting, status: MeetingStatus | None = None, detail: str | None = None) -> None:
    if status is not None:
        m.status = status
    m.status_detail = detail
    db.commit()
    log.info("meeting %s: %s %s", m.id, m.status.value, detail or "")


def _check_cancel(db: Session, meeting_id: int) -> None:
    """Titik cek: baca langsung dari DB apakah user meminta pembatalan (atau sudah dipaksa batal)."""
    row = db.execute(
        select(Meeting.cancel_requested_at, Meeting.status).where(Meeting.id == meeting_id)
    ).one_or_none()
    if row is None or row.cancel_requested_at is not None or row.status == MeetingStatus.CANCELLED:
        raise Cancelled()


def _release_gpu() -> None:
    """Lepas VRAM yang mungkin masih dipegang model setelah proses berhenti di tengah jalan."""
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def claim_next(db: Session) -> int | None:
    """Ambil 1 meeting QUEUED secara atomik (aman bila ada lebih dari satu worker)."""
    mid = db.scalar(
        select(Meeting.id).where(Meeting.status == MeetingStatus.QUEUED).order_by(Meeting.created_at).limit(1)
    )
    if mid is None:
        return None
    res = db.execute(
        update(Meeting)
        .where(Meeting.id == mid, Meeting.status == MeetingStatus.QUEUED)
        .values(status=MeetingStatus.PREPROCESSING, status_detail="Diambil worker", error_message=None,
                processing_started_at=utcnow(), processing_finished_at=None, cancel_requested_at=None)
    )
    db.commit()
    return mid if res.rowcount == 1 else None


def requeue_stuck(db: Session) -> int:
    """Saat worker start: meeting yang terhenti di tengah proses (PC mati, dll) dimasukkan antrean lagi.

    Kecuali yang sudah diminta batal saat worker mati → langsung jadi CANCELLED.
    """
    db.execute(
        update(Meeting)
        .where(Meeting.status.in_(PROCESSING_STATUSES), Meeting.cancel_requested_at.is_not(None))
        .values(status=MeetingStatus.CANCELLED, status_detail="Dibatalkan", cancel_requested_at=None,
                processing_finished_at=utcnow())
    )
    res = db.execute(
        update(Meeting).where(Meeting.status.in_(PROCESSING_STATUSES))
        .values(status=MeetingStatus.QUEUED, status_detail="Dilanjutkan setelah worker restart")
    )
    db.commit()
    return res.rowcount


def process_meeting(meeting_id: int, provider: TranscriptionProvider | None = None) -> None:
    s = get_settings()
    with SessionLocal() as db:
        m = db.get(Meeting, meeting_id)
        if m is None:
            return
        hotwords = list(db.scalars(select(GlossaryTerm.term).order_by(GlossaryTerm.term)))
        # "Resep" pemrosesan: dicatat per meeting agar hasil bisa dilacak & dibandingkan
        info: dict = {
            "code_version": code_version(),
            "provider": s.transcription_provider,
            "whisper_model": s.whisper_model,
            "compute_type": s.whisper_compute_type,
            "batch_size": s.whisper_batch_size,
            "device": s.whisper_device,
            "language_requested": m.requested_language or s.whisper_language,
            "align_model": s.align_model or "default",
            "hotwords": hotwords,
            "min_speakers": m.min_speakers,
            "max_speakers": m.max_speakers,
            "speaker_rules": {"min_run_words": MIN_RUN_WORDS, "min_run_ms": MIN_RUN_MS},
            "timings_sec": {},
        }
        m.processing_info = json.dumps(info, ensure_ascii=False)
        t0 = time.monotonic()
        try:
            # 1) Pra-proses audio
            _set(db, m, MeetingStatus.PREPROCESSING, "Mengonversi audio (ffmpeg)")
            src = s.storage_dir / m.audio_path
            processed_rel = m.processed_audio_path or str(Path(m.audio_path).parent / "processed.wav")
            processed = s.storage_dir / processed_rel
            if not processed.exists():
                audio.to_wav_16k_mono(src, processed)
            m.processed_audio_path = processed_rel
            m.duration_sec = audio.probe_duration(processed)
            info["timings_sec"]["preprocess"] = round(time.monotonic() - t0, 1)
            t0 = time.monotonic()
            m.processing_info = json.dumps(info, ensure_ascii=False)
            db.commit()
            _check_cancel(db, m.id)

            # 2) Transkripsi + diarization
            _set(db, m, MeetingStatus.TRANSCRIBING, "Memulai transkripsi")

            def on_progress(detail: str) -> None:
                # Dipanggil WhisperX tiap naik ~5% → sekaligus jadi titik cek pembatalan
                _check_cancel(db, m.id)
                _set(db, m, None, detail)

            provider = provider or get_provider()
            result = provider.transcribe(
                processed,
                language=m.requested_language or s.whisper_language,  # "auto" = deteksi otomatis
                min_speakers=m.min_speakers,
                max_speakers=m.max_speakers,
                hotwords=hotwords,
                on_progress=on_progress,
            )
            _check_cancel(db, m.id)
            info["timings_sec"]["transcribe"] = round(time.monotonic() - t0, 1)
            t0 = time.monotonic()
            # Simpan hasil mentah (kata + speaker) agar pembagian pembicara bisa dirapikan ulang tanpa GPU
            raw = {"language": result.language, "segments": [asdict(sg) for sg in result.segments]}
            (processed.parent / "transcription.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

            # 3) Rapikan per pembicara + statistik
            _set(db, m, MeetingStatus.ANALYZING, "Menghitung statistik pembicara")
            segs, stats = process_segments(result.segments)
            db.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id))
            db.execute(delete(Speaker).where(Speaker.meeting_id == m.id))
            speakers = {
                st.label: Speaker(
                    meeting_id=m.id, label=st.label, display_name=f"Pembicara {st.label}",
                    talk_time_ms=st.talk_time_ms, turn_count=st.turn_count, word_count=st.word_count,
                )
                for st in stats
            }
            db.add_all(speakers.values())
            db.flush()
            db.add_all(
                TranscriptSegment(
                    meeting_id=m.id, speaker_id=speakers[sg.speaker].id,
                    start_ms=sg.start_ms, end_ms=sg.end_ms, text=sg.text, confidence=sg.confidence,
                )
                for sg in segs
            )
            m.language = result.language
            m.speaker_count = len(speakers)
            info["timings_sec"]["analyze"] = round(time.monotonic() - t0, 1)
            info["language_detected"] = result.language
            m.processing_info = json.dumps(info, ensure_ascii=False)
            m.processing_finished_at = utcnow()
            db.flush()
            _check_cancel(db, m.id)  # batal di detik terakhir → jangan timpa jadi DONE
            _set(db, m, MeetingStatus.DONE, None)
        except Cancelled:
            db.rollback()
            log.info("meeting %s dibatalkan oleh user", meeting_id)
            m = db.get(Meeting, meeting_id)
            if m is not None:
                m.cancel_requested_at = None
                m.error_message = None
                m.processing_finished_at = utcnow()
                _set(db, m, MeetingStatus.CANCELLED, "Dibatalkan")
        except Exception as e:
            db.rollback()
            log.error("meeting %s gagal:\n%s", meeting_id, traceback.format_exc())
            m = db.get(Meeting, meeting_id)
            if m is not None:
                m.error_message = f"{type(e).__name__}: {e}"
                m.cancel_requested_at = None
                m.processing_finished_at = utcnow()
                _set(db, m, MeetingStatus.FAILED, None)
    # Di luar blok except: traceback sudah dilepas, jadi model yang tertahan di frame bisa dibersihkan
    _release_gpu()
