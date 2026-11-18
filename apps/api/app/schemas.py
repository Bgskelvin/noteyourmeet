from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import MeetingStatus


def _as_utc(v: datetime | None) -> datetime | None:
    # SQLite menyimpan waktu tanpa zona; semua waktu kita simpan dalam UTC
    return v.replace(tzinfo=UTC) if v is not None and v.tzinfo is None else v


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    display_name: str
    talk_time_ms: int
    turn_count: int
    word_count: int


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    speaker_id: int | None
    start_ms: int
    end_ms: int
    text: str


class MeetingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: MeetingStatus
    status_detail: str | None
    cancel_requested_at: UtcDatetime | None = None
    error_message: str | None
    original_filename: str
    duration_sec: float | None
    speaker_count: int | None
    created_at: UtcDatetime


class MeetingDetail(MeetingSummary):
    language: str | None  # bahasa yang dipakai/terdeteksi saat transkripsi
    requested_language: str | None  # pilihan user: "id", "en", "auto", ...
    min_speakers: int | None
    max_speakers: int | None
    processing_started_at: UtcDatetime | None
    processing_finished_at: UtcDatetime | None
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]


class MeetingUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class RetryRequest(BaseModel):
    language: str | None = None  # isi untuk memproses ulang dengan bahasa lain


class SpeakerUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class SpeakerMerge(BaseModel):
    source_ids: list[int] = Field(min_length=1)
    target_id: int
