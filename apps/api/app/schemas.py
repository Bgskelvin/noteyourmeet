from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Json

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
    original_text: str | None = None  # terisi = kalimat ini sudah diedit (manual atau otomatis)
    auto_corrected: bool | None = None  # True = diubah otomatis oleh memori koreksi
    reviewed_at: UtcDatetime | None = None  # terisi = sudah diperiksa user


class SegmentUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class ReviewIn(BaseModel):
    reviewed: bool = True


class MeetingReviewStat(BaseModel):
    id: int
    title: str
    duration_sec: float | None
    total_segments: int
    reviewed_segments: int
    reviewed_ms: int


class ReviewStats(BaseModel):
    meetings: list[MeetingReviewStat]
    reviewed_ms_total: int
    reviewed_segments_total: int
    training: dict  # ringkasan dataset latihan: usable_minutes, target_hours, progress_pct, ...


class ReplaceRequest(BaseModel):
    find: str = Field(min_length=1, max_length=200)
    replace: str = Field(max_length=200)
    match_case: bool = False
    whole_word: bool = True
    dry_run: bool = False  # true = hanya hitung, tidak mengubah
    remember: bool = False  # true = simpan sebagai memori koreksi untuk meeting berikutnya


class ReplaceResult(BaseModel):
    matches: int
    segments_changed: int


class GlossaryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str


class GlossaryTermIn(BaseModel):
    term: str = Field(min_length=1, max_length=100)


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
    processing_info: Json[dict] | None = None  # resep pemrosesan (disimpan sebagai teks JSON)
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


class CorrectionRuleIn(BaseModel):
    find: str = Field(min_length=1, max_length=200)
    replace: str = Field(min_length=1, max_length=200)
    whole_word: bool = True
    match_case: bool = False


class CorrectionRuleUpdate(BaseModel):
    enabled: bool


class CorrectionRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    find: str
    replace: str
    whole_word: bool
    match_case: bool
    enabled: bool
    times_applied: int


class TermSuggestion(BaseModel):
    term: str
    count: int  # berapa kali muncul di editan
    example: str  # contoh kalimat setelah diedit


class RuleSuggestion(BaseModel):
    find: str
    replace: str
    count: int
    example: str


class Suggestions(BaseModel):
    terms: list[TermSuggestion]
    rules: list[RuleSuggestion]


class DismissIn(BaseModel):
    kind: str = Field(pattern="^(term|rule)$")
    value: str = Field(min_length=1, max_length=420)  # rule: "salah→benar"
