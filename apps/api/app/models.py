import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MeetingStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


PROCESSING_STATUSES = {
    MeetingStatus.PREPROCESSING,
    MeetingStatus.TRANSCRIBING,
    MeetingStatus.ANALYZING,
}


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus, native_enum=False, length=20), default=MeetingStatus.QUEUED, index=True
    )
    status_detail: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    original_filename: Mapped[str] = mapped_column(String(512))
    audio_path: Mapped[str] = mapped_column(String(1024))  # relatif ke storage_dir
    processed_audio_path: Mapped[str | None] = mapped_column(String(1024))
    duration_sec: Mapped[float | None] = mapped_column(Float)
    language: Mapped[str | None] = mapped_column(String(10))  # hasil transkripsi
    requested_language: Mapped[str | None] = mapped_column(String(10))  # pilihan user saat upload

    min_speakers: Mapped[int | None] = mapped_column(Integer)
    max_speakers: Mapped[int | None] = mapped_column(Integer)
    speaker_count: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Diisi saat user menekan "Batalkan" ketika worker sedang memproses; worker mengeceknya berkala
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # JSON "resep" pemrosesan: model, pengaturan, kosakata, versi kode, durasi tiap langkah
    processing_info: Mapped[str | None] = mapped_column(Text)

    speakers: Mapped[list["Speaker"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="Speaker.label"
    )
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="TranscriptSegment.start_ms"
    )


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(20))  # "A", "B", ...
    display_name: Mapped[str] = mapped_column(String(255))
    talk_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    meeting: Mapped[Meeting] = relationship(back_populates="speakers")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    speaker_id: Mapped[int | None] = mapped_column(
        ForeignKey("speakers.id", ondelete="SET NULL"), index=True
    )
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Teks asli hasil AI, diisi saat pertama kali diedit manual (agar bisa dikembalikan)
    original_text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    meeting: Mapped[Meeting] = relationship(back_populates="segments")


class GlossaryTerm(Base):
    """Kosakata tim: nama orang, singkatan, istilah — dipakai sebagai 'hotwords' Whisper."""

    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
