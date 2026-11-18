import logging
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db, init_db
from app.languages import WHISPER_LANGUAGES
from app.models import (
    PROCESSING_STATUSES,
    GlossaryTerm,
    Meeting,
    MeetingStatus,
    Speaker,
    TranscriptSegment,
    utcnow,
)
from app.schemas import (
    GlossaryTermIn,
    GlossaryTermOut,
    MeetingDetail,
    MeetingSummary,
    MeetingUpdate,
    ReplaceRequest,
    ReplaceResult,
    RetryRequest,
    SegmentUpdate,
    SpeakerMerge,
    SpeakerOut,
    SpeakerUpdate,
)
from app.services.corrections import build_pattern, normalize_term, replace_in_text
from app.services.speakers import CleanSegment, compute_stats

logging.basicConfig(level=logging.INFO)
settings = get_settings()

ALLOWED_EXT = {
    ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus", ".flac", ".webm",
    ".mp4", ".mkv", ".mov", ".3gp", ".amr", ".wma",
}
CHUNK = 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="NoteYourMeet API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_meeting(db: Session, meeting_id: int, *, full: bool = False) -> Meeting:
    q = select(Meeting).where(Meeting.id == meeting_id)
    if full:
        q = q.options(selectinload(Meeting.speakers), selectinload(Meeting.segments))
    m = db.scalar(q)
    if m is None:
        raise HTTPException(404, "Meeting tidak ditemukan")
    return m


def _int_or_none(v: str | None, name: str) -> int | None:
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except ValueError:
        raise HTTPException(422, f"{name} harus angka") from None
    if not 1 <= n <= 50:
        raise HTTPException(422, f"{name} harus antara 1 dan 50")
    return n


def _language_or_default(v: str | None) -> str:
    """'auto' atau kode bahasa Whisper (id, en, ...). Kosong = default dari .env."""
    v = (v or "").strip().lower() or settings.whisper_language
    if v not in WHISPER_LANGUAGES:
        raise HTTPException(422, f"Bahasa '{v}' tidak didukung")
    return v


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/config")
def public_config() -> dict:
    """Pengaturan yang perlu diketahui frontend."""
    return {"default_language": settings.whisper_language}


@app.post("/meetings", response_model=MeetingSummary, status_code=201)
def create_meeting(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    min_speakers: str | None = Form(None),
    max_speakers: str | None = Form(None),
    language: str | None = Form(None),
    db: Session = Depends(get_db),
) -> Meeting:
    lang = _language_or_default(language)
    filename = Path(file.filename or "audio").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Format {ext or '(tanpa ekstensi)'} tidak didukung")
    mn = _int_or_none(min_speakers, "min_speakers")
    mx = _int_or_none(max_speakers, "max_speakers")
    if mn and mx and mn > mx:
        raise HTTPException(422, "min_speakers tidak boleh lebih besar dari max_speakers")

    rel_dir = Path("meetings") / uuid.uuid4().hex
    dest_dir = settings.storage_dir / rel_dir
    dest_dir.mkdir(parents=True)
    dest = dest_dir / f"original{ext}"
    limit = settings.max_upload_mb * CHUNK
    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File melebihi {settings.max_upload_mb} MB")
                f.write(chunk)
        if size == 0:
            raise HTTPException(422, "File kosong")
    except BaseException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    m = Meeting(
        title=(title or "").strip() or Path(filename).stem,
        original_filename=filename,
        audio_path=(rel_dir / dest.name).as_posix(),
        min_speakers=mn,
        max_speakers=mx,
        requested_language=lang,
        status=MeetingStatus.QUEUED,
        status_detail="Menunggu antrean",
    )
    db.add(m)
    db.commit()
    return m


@app.get("/meetings", response_model=list[MeetingSummary])
def list_meetings(db: Session = Depends(get_db)) -> list[Meeting]:
    return list(db.scalars(select(Meeting).order_by(Meeting.created_at.desc())))


@app.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> Meeting:
    return _get_meeting(db, meeting_id, full=True)


@app.patch("/meetings/{meeting_id}", response_model=MeetingSummary)
def update_meeting(meeting_id: int, body: MeetingUpdate, db: Session = Depends(get_db)) -> Meeting:
    m = _get_meeting(db, meeting_id)
    m.title = body.title.strip()
    db.commit()
    return m


@app.get("/meetings/{meeting_id}/audio")
def get_audio(meeting_id: int, db: Session = Depends(get_db)) -> FileResponse:
    m = _get_meeting(db, meeting_id)
    # Utamakan WAV hasil konversi: pasti bisa diputar browser & timestamp-nya sama dengan transkrip
    for rel in (m.processed_audio_path, m.audio_path):
        if rel and (p := settings.storage_dir / rel).exists():
            return FileResponse(p, filename=Path(rel).name)
    raise HTTPException(404, "File audio tidak ditemukan")


@app.post("/meetings/{meeting_id}/retry", response_model=MeetingSummary)
def retry_meeting(
    meeting_id: int, body: RetryRequest | None = None, db: Session = Depends(get_db)
) -> Meeting:
    m = _get_meeting(db, meeting_id)
    if m.status in PROCESSING_STATUSES or m.status == MeetingStatus.QUEUED:
        raise HTTPException(409, "Meeting sedang diproses / sudah di antrean")
    if body and body.language:
        m.requested_language = _language_or_default(body.language)
    m.cancel_requested_at = None
    m.status = MeetingStatus.QUEUED
    m.status_detail = "Menunggu antrean (proses ulang)"
    m.error_message = None
    db.commit()
    return m


@app.post("/meetings/{meeting_id}/cancel", response_model=MeetingSummary)
def cancel_meeting(meeting_id: int, force: bool = False, db: Session = Depends(get_db)) -> Meeting:
    """Batalkan proses.

    - Masih antre → langsung CANCELLED.
    - Sedang diproses → tandai; worker berhenti di titik cek berikutnya (beberapa detik).
    - force=true → langsung CANCELLED (untuk kasus worker sudah mati/tidak merespons).
    """
    m = _get_meeting(db, meeting_id)
    if m.status == MeetingStatus.QUEUED:
        res = db.execute(
            update(Meeting)
            .where(Meeting.id == m.id, Meeting.status == MeetingStatus.QUEUED)
            .values(status=MeetingStatus.CANCELLED, status_detail="Dibatalkan", processing_finished_at=utcnow())
        )
        db.commit()
        if res.rowcount == 0:  # baru saja diambil worker → perlakukan sebagai sedang diproses
            db.refresh(m)
    if m.status in PROCESSING_STATUSES:
        if force:
            m.status = MeetingStatus.CANCELLED
            m.status_detail = "Dibatalkan (paksa)"
            m.processing_finished_at = utcnow()
        else:
            m.cancel_requested_at = m.cancel_requested_at or utcnow()
            m.status_detail = "Membatalkan… menunggu worker berhenti"
        db.commit()
    elif m.status != MeetingStatus.CANCELLED:
        raise HTTPException(409, "Meeting tidak sedang diproses")
    db.refresh(m)
    return m


@app.delete("/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)) -> None:
    m = _get_meeting(db, meeting_id)
    if m.status in PROCESSING_STATUSES:
        raise HTTPException(409, "Tunggu sampai proses selesai sebelum menghapus")
    folder = (settings.storage_dir / m.audio_path).parent
    db.delete(m)
    db.commit()
    if folder.is_relative_to(settings.storage_dir / "meetings"):
        shutil.rmtree(folder, ignore_errors=True)


# ---------- Speaker ----------

def _recompute_stats(db: Session, meeting: Meeting) -> None:
    segs = db.scalars(
        select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting.id).order_by(TranscriptSegment.start_ms)
    ).all()
    stats = {
        st.label: st
        for st in compute_stats(
            [CleanSegment(str(s.speaker_id), s.start_ms, s.end_ms, s.text) for s in segs if s.speaker_id]
        )
    }
    speakers = db.scalars(select(Speaker).where(Speaker.meeting_id == meeting.id)).all()
    for sp in speakers:
        st = stats.get(str(sp.id))
        sp.talk_time_ms = st.talk_time_ms if st else 0
        sp.turn_count = st.turn_count if st else 0
        sp.word_count = st.word_count if st else 0
    meeting.speaker_count = len(speakers)


@app.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
def rename_speaker(speaker_id: int, body: SpeakerUpdate, db: Session = Depends(get_db)) -> Speaker:
    sp = db.get(Speaker, speaker_id)
    if sp is None:
        raise HTTPException(404, "Pembicara tidak ditemukan")
    sp.display_name = body.display_name.strip()
    db.commit()
    return sp


@app.post("/meetings/{meeting_id}/speakers/merge", response_model=MeetingDetail)
def merge_speakers(meeting_id: int, body: SpeakerMerge, db: Session = Depends(get_db)) -> Meeting:
    """Gabungkan beberapa label (mis. 1 orang terdeteksi jadi B dan D) ke satu pembicara."""
    m = _get_meeting(db, meeting_id)
    ids = set(body.source_ids) - {body.target_id}
    if not ids:
        raise HTTPException(422, "Pilih minimal satu pembicara lain untuk digabung")
    valid = set(db.scalars(select(Speaker.id).where(Speaker.meeting_id == m.id)))
    if body.target_id not in valid or not ids <= valid:
        raise HTTPException(422, "Pembicara bukan bagian dari meeting ini")
    for seg in db.scalars(select(TranscriptSegment).where(TranscriptSegment.speaker_id.in_(ids))):
        seg.speaker_id = body.target_id
    for sp in db.scalars(select(Speaker).where(Speaker.id.in_(ids))):
        db.delete(sp)
    db.flush()
    _recompute_stats(db, m)
    db.commit()
    db.expire_all()
    return _get_meeting(db, meeting_id, full=True)


@app.post("/segments/{segment_id}/speaker", response_model=MeetingDetail)
def reassign_segment(segment_id: int, speaker_id: int, db: Session = Depends(get_db)) -> Meeting:
    """Pindahkan satu kalimat ke pembicara lain (koreksi manual)."""
    seg = db.get(TranscriptSegment, segment_id)
    sp = db.get(Speaker, speaker_id)
    if seg is None or sp is None or sp.meeting_id != seg.meeting_id:
        raise HTTPException(422, "Segmen/pembicara tidak valid")
    seg.speaker_id = sp.id
    m = _get_meeting(db, seg.meeting_id)
    db.flush()
    _recompute_stats(db, m)
    db.commit()
    db.expire_all()
    return _get_meeting(db, m.id, full=True)


# ---------- Koreksi transkrip ----------

@app.patch("/segments/{segment_id}", response_model=MeetingDetail)
def edit_segment(segment_id: int, body: SegmentUpdate, db: Session = Depends(get_db)) -> Meeting:
    """Edit teks satu kalimat. Teks asli AI disimpan di original_text agar bisa dikembalikan."""
    seg = db.get(TranscriptSegment, segment_id)
    if seg is None:
        raise HTTPException(404, "Kalimat tidak ditemukan")
    new = body.text.strip()
    if seg.original_text is None and new != seg.text:
        seg.original_text = seg.text
    seg.text = new
    if seg.original_text == new:  # dikembalikan ke teks asli
        seg.original_text = None
    m = _get_meeting(db, seg.meeting_id)
    db.flush()
    _recompute_stats(db, m)
    db.commit()
    db.expire_all()
    return _get_meeting(db, m.id, full=True)


@app.post("/meetings/{meeting_id}/replace", response_model=ReplaceResult)
def replace_text(meeting_id: int, body: ReplaceRequest, db: Session = Depends(get_db)) -> ReplaceResult:
    """Cari & ganti kata di seluruh transkrip (mis. 'CSILC' → 'CS ALC'). dry_run=true hanya menghitung."""
    m = _get_meeting(db, meeting_id)
    pattern = build_pattern(body.find, match_case=body.match_case, whole_word=body.whole_word)
    replacement = body.replace.strip()
    matches = changed = 0
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id))
    for seg in segs:
        new, n = replace_in_text(seg.text, pattern, replacement)
        if not n:
            continue
        matches += n
        new = " ".join(new.split())
        if body.dry_run or new == seg.text:
            continue
        if not new:
            continue  # jangan sampai kalimat jadi kosong
        if seg.original_text is None:
            seg.original_text = seg.text
        seg.text = new
        if seg.original_text == new:
            seg.original_text = None
        changed += 1
    if not body.dry_run and changed:
        db.flush()
        _recompute_stats(db, m)
        db.commit()
    return ReplaceResult(matches=matches, segments_changed=changed)


# ---------- Kosakata tim (hotwords Whisper) ----------

@app.get("/glossary", response_model=list[GlossaryTermOut])
def list_glossary(db: Session = Depends(get_db)) -> list[GlossaryTerm]:
    return list(db.scalars(select(GlossaryTerm).order_by(GlossaryTerm.term)))


@app.post("/glossary", response_model=list[GlossaryTermOut], status_code=201)
def add_glossary(body: GlossaryTermIn, db: Session = Depends(get_db)) -> list[GlossaryTerm]:
    """Tambah satu atau beberapa istilah sekaligus (pisahkan dengan koma atau baris baru)."""
    existing = {t.lower() for t in db.scalars(select(GlossaryTerm.term))}
    for raw in re.split(r"[,\n]", body.term):
        term = normalize_term(raw)
        if term and len(term) <= 100 and term.lower() not in existing:
            db.add(GlossaryTerm(term=term))
            existing.add(term.lower())
    db.commit()
    return list_glossary(db)


@app.delete("/glossary/{term_id}", status_code=204)
def delete_glossary(term_id: int, db: Session = Depends(get_db)) -> None:
    t = db.get(GlossaryTerm, term_id)
    if t is not None:
        db.delete(t)
        db.commit()
