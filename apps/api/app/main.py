import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.dataset import stats as dataset_stats
from app.db import get_db, init_db
from app.languages import WHISPER_LANGUAGES
from app.logging_setup import setup_logging
from app.models import (
    PROCESSING_STATUSES,
    CorrectionRule,
    DismissedSuggestion,
    GlossaryTerm,
    Meeting,
    MeetingStatus,
    Speaker,
    TranscriptSegment,
    utcnow,
)
from app.schemas import (
    CorrectionRuleIn,
    CorrectionRuleOut,
    CorrectionRuleUpdate,
    DictionaryEntry,
    DictionaryVariant,
    DismissIn,
    GlossaryTermIn,
    GlossaryTermOut,
    LearnIn,
    LearnOut,
    MeetingDetail,
    MeetingReviewStat,
    MeetingSummary,
    MeetingUpdate,
    ReplaceRequest,
    ReplaceResult,
    RetryRequest,
    ReviewIn,
    ReviewStats,
    RuleSuggestion,
    SegmentOut,
    SegmentUpdate,
    SpeakerMerge,
    SpeakerOut,
    SpeakerUpdate,
    Suggestions,
    TermSuggestion,
)
from app.services.corrections import (
    apply_rules,
    build_pattern,
    edit_pairs,
    is_common,
    is_name_like,
    new_terms,
    normalize_term,
    replace_in_text,
)
from app.services.speakers import CleanSegment, compute_stats

setup_logging("api")
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
    seg.auto_corrected = None  # sekarang diedit tangan
    seg.reviewed_at = seg.reviewed_at or utcnow()  # diedit = sudah diperiksa
    if seg.original_text == new:  # dikembalikan ke teks asli
        seg.original_text = None
    m = _get_meeting(db, seg.meeting_id)
    db.flush()
    _recompute_stats(db, m)
    db.commit()
    db.expire_all()
    return _get_meeting(db, m.id, full=True)


def _replace_in_meeting(
    db: Session, m: Meeting, find: str, replacement: str, *, whole_word: bool = True, match_case: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Ganti kata di semua kalimat meeting. Kembalikan (jumlah kemunculan, jumlah kalimat berubah). Belum commit."""
    pattern = build_pattern(find, match_case=match_case, whole_word=whole_word)
    matches = changed = 0
    for seg in db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id)):
        new, n = replace_in_text(seg.text, pattern, replacement)
        if not n:
            continue
        matches += n
        new = " ".join(new.split())
        if dry_run or new == seg.text or not new:  # jangan sampai kalimat jadi kosong
            continue
        if seg.original_text is None:
            seg.original_text = seg.text
        seg.text = new
        seg.auto_corrected = None
        if seg.original_text == new:
            seg.original_text = None
        changed += 1
    return matches, changed


@app.post("/meetings/{meeting_id}/replace", response_model=ReplaceResult)
def replace_text(meeting_id: int, body: ReplaceRequest, db: Session = Depends(get_db)) -> ReplaceResult:
    """Cari & ganti kata di seluruh transkrip (mis. 'CSILC' → 'CS ALC'). dry_run=true hanya menghitung."""
    m = _get_meeting(db, meeting_id)
    replacement = body.replace.strip()
    matches, changed = _replace_in_meeting(
        db, m, body.find, replacement, whole_word=body.whole_word, match_case=body.match_case, dry_run=body.dry_run
    )
    if not body.dry_run and body.remember and replacement and matches:
        _upsert_rule(db, body.find.strip(), replacement, whole_word=body.whole_word, match_case=body.match_case)
    if not body.dry_run:
        if changed:
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


# ---------- Memori koreksi (salah → benar, diterapkan otomatis) ----------

def _upsert_rule(
    db: Session, find: str, replace: str, *, whole_word: bool = True, match_case: bool = False
) -> CorrectionRule:
    find = normalize_term(find)
    rule = db.scalar(select(CorrectionRule).where(func.lower(CorrectionRule.find) == find.lower()))
    if rule is None:
        rule = CorrectionRule(find=find, replace=normalize_term(replace), whole_word=whole_word, match_case=match_case)
        db.add(rule)
    else:
        rule.replace, rule.whole_word, rule.match_case = normalize_term(replace), whole_word, match_case
        rule.enabled = True
    db.flush()
    return rule


@app.get("/corrections", response_model=list[CorrectionRuleOut])
def list_corrections(db: Session = Depends(get_db)) -> list[CorrectionRule]:
    return list(db.scalars(select(CorrectionRule).order_by(CorrectionRule.find)))


@app.post("/corrections", response_model=CorrectionRuleOut, status_code=201)
def add_correction(body: CorrectionRuleIn, db: Session = Depends(get_db)) -> CorrectionRule:
    if normalize_term(body.find).lower() == normalize_term(body.replace).lower() and not body.match_case:
        raise HTTPException(422, "Kata salah dan kata benar sama")
    rule = _upsert_rule(db, body.find, body.replace, whole_word=body.whole_word, match_case=body.match_case)
    db.commit()
    return rule


@app.patch("/corrections/{rule_id}", response_model=CorrectionRuleOut)
def update_correction(rule_id: int, body: CorrectionRuleUpdate, db: Session = Depends(get_db)) -> CorrectionRule:
    rule = db.get(CorrectionRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Aturan tidak ditemukan")
    rule.enabled = body.enabled
    db.commit()
    return rule


@app.delete("/corrections/{rule_id}", status_code=204)
def delete_correction(rule_id: int, db: Session = Depends(get_db)) -> None:
    if (rule := db.get(CorrectionRule, rule_id)) is not None:
        db.delete(rule)
        db.commit()


@app.post("/meetings/{meeting_id}/apply-corrections", response_model=ReplaceResult)
def apply_corrections(meeting_id: int, db: Session = Depends(get_db)) -> ReplaceResult:
    """Terapkan semua memori koreksi aktif ke meeting yang sudah ada (tanpa proses ulang GPU)."""
    m = _get_meeting(db, meeting_id)
    rules = list(db.scalars(select(CorrectionRule).where(CorrectionRule.enabled).order_by(CorrectionRule.id)))
    matches = changed = 0
    totals = [0] * len(rules)
    for seg in db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id)):
        new, counts = apply_rules(seg.text, rules)
        matches += sum(counts)
        if new == seg.text or not new:
            continue
        totals = [a + b for a, b in zip(totals, counts, strict=True)]
        if seg.original_text is None:
            seg.original_text = seg.text
            seg.auto_corrected = True
        seg.text = new
        changed += 1
    for r, n in zip(rules, totals, strict=True):
        r.times_applied += n
    if changed:
        db.flush()
        _recompute_stats(db, m)
    db.commit()
    return ReplaceResult(matches=matches, segments_changed=changed)


# ---------- Saran dari editan user ----------

MAX_SUGGESTIONS = 30


@app.get("/suggestions", response_model=Suggestions)
def suggestions(db: Session = Depends(get_db)) -> Suggestions:
    """Pelajari editan manual: istilah baru → saran Kosakata tim; 'salah → benar' → saran memori koreksi."""
    glossary = {t.lower() for t in db.scalars(select(GlossaryTerm.term))}
    rule_finds = {f.lower() for f in db.scalars(select(CorrectionRule.find))}
    dismissed = {(d.kind, d.value.lower()) for d in db.scalars(select(DismissedSuggestion))}
    terms: dict[str, list] = {}
    pairs: dict[tuple[str, str], list] = {}
    edited = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.original_text.is_not(None), TranscriptSegment.auto_corrected.is_not(True))
        .order_by(TranscriptSegment.id.desc())
        .limit(5000)
    )
    rules = list(db.scalars(select(CorrectionRule).where(CorrectionRule.enabled)))
    for seg in edited:
        # Bagian yang sudah dijelaskan Kamus (mis. hasil "Perbaiki" yang diingat) bukan saran baru
        original = apply_rules(seg.original_text, rules)[0] if rules else seg.original_text
        for term in new_terms(original, seg.text):
            if term.lower() in glossary or ("term", term.lower()) in dismissed:
                continue
            terms.setdefault(term.lower(), [term, 0, seg.text])[1] += 1
        for old, new in edit_pairs(original, seg.text):
            if old.lower() in rule_finds or ("rule", f"{old}→{new}".lower()) in dismissed:
                continue
            pairs.setdefault((old.lower(), new.lower()), [old, new, 0, seg.text])[2] += 1
    return Suggestions(
        terms=[TermSuggestion(term=t, count=n, example=ex) for t, n, ex in
               sorted(terms.values(), key=lambda v: -v[1])[:MAX_SUGGESTIONS]],
        rules=[RuleSuggestion(find=o, replace=r, count=n, example=ex) for o, r, n, ex in
               sorted(pairs.values(), key=lambda v: -v[2])[:MAX_SUGGESTIONS]],
    )


@app.post("/suggestions/dismiss", status_code=204)
def dismiss_suggestion(body: DismissIn, db: Session = Depends(get_db)) -> None:
    value = body.value.strip()
    exists = db.scalar(
        select(DismissedSuggestion).where(
            DismissedSuggestion.kind == body.kind, func.lower(DismissedSuggestion.value) == value.lower()
        )
    )
    if exists is None:
        db.add(DismissedSuggestion(kind=body.kind, value=value))
        db.commit()


# ---------- Pemeriksaan transkrip (bahan set uji & data latihan) ----------

@app.post("/segments/{segment_id}/review", response_model=SegmentOut)
def review_segment(segment_id: int, body: ReviewIn, db: Session = Depends(get_db)) -> TranscriptSegment:
    """Tandai kalimat sudah diperiksa (benar) atau batalkan tandanya."""
    seg = db.get(TranscriptSegment, segment_id)
    if seg is None:
        raise HTTPException(404, "Kalimat tidak ditemukan")
    seg.reviewed_at = (seg.reviewed_at or utcnow()) if body.reviewed else None
    db.commit()
    return seg


@app.get("/review/stats", response_model=ReviewStats)
def review_stats(db: Session = Depends(get_db)) -> ReviewStats:
    rows = db.execute(
        select(
            Meeting.id, Meeting.title, Meeting.duration_sec,
            func.count(TranscriptSegment.id),
            func.count(TranscriptSegment.reviewed_at),
            func.coalesce(
                func.sum(
                    case((TranscriptSegment.reviewed_at.is_not(None),
                          TranscriptSegment.end_ms - TranscriptSegment.start_ms), else_=0)
                ), 0,
            ),
        )
        .join(TranscriptSegment, TranscriptSegment.meeting_id == Meeting.id)
        .where(Meeting.status == MeetingStatus.DONE)
        .group_by(Meeting.id)
        .order_by(Meeting.created_at.desc())
    ).all()
    stats = [
        MeetingReviewStat(id=i, title=t, duration_sec=d, total_segments=n, reviewed_segments=r, reviewed_ms=ms)
        for i, t, d, n, r, ms in rows
    ]
    return ReviewStats(
        meetings=stats,
        reviewed_ms_total=sum(s.reviewed_ms for s in stats),
        reviewed_segments_total=sum(s.reviewed_segments for s in stats),
        training=dataset_stats(),
    )


# ---------- Perbaiki pintar + Kamus tim (kosakata & memori koreksi dalam satu daftar) ----------

@app.post("/learn", response_model=LearnOut)
def learn(body: LearnIn, db: Session = Depends(get_db)) -> LearnOut:
    """Satu aksi "Perbaiki": sistem memutuskan sendiri ke mana koreksi disimpan.

    - selalu → memori koreksi ("salah → benar", diterapkan ke transkrip berikutnya)
    - kata benar berupa nama/singkatan → juga kosakata Whisper (hotwords) agar terdengar benar dari awal
    - kata salah terlalu umum ("tuh", "ini") → 409, minta konfirmasi user dulu
    - opsional: langsung ganti di seluruh meeting yang sedang dibuka
    """
    find, replacement = normalize_term(body.find), normalize_term(body.replace)
    if not find or not replacement or (find == replacement):
        raise HTTPException(422, "Kata salah dan kata benar harus diisi dan berbeda")
    if is_common(find) and not body.confirm_common:
        raise HTTPException(409, f"'{find}' adalah kata yang sangat umum — yakin ingin selalu menggantinya?")

    rule = _upsert_rule(db, find, replacement, whole_word=body.whole_word)
    glossary_added = False
    in_glossary = db.scalar(select(GlossaryTerm).where(func.lower(GlossaryTerm.term) == replacement.lower()))
    if in_glossary is None and is_name_like(replacement):
        db.add(GlossaryTerm(term=replacement))
        glossary_added = True
    matches = changed = 0
    if body.meeting_id is not None and body.apply_to_meeting:
        m = _get_meeting(db, body.meeting_id)
        matches, changed = _replace_in_meeting(db, m, find, replacement, whole_word=body.whole_word)
        if changed:
            db.flush()
            _recompute_stats(db, m)
    db.commit()
    return LearnOut(
        rule_id=rule.id, heard_by_whisper=glossary_added or in_glossary is not None, glossary_added=glossary_added,
        matches=matches, segments_changed=changed,
    )


@app.get("/dictionary", response_model=list[DictionaryEntry])
def dictionary(db: Session = Depends(get_db)) -> list[DictionaryEntry]:
    """Kamus tim: setiap kata benar + apakah dikenali Whisper + daftar variasi salah dengarnya."""
    entries: dict[str, DictionaryEntry] = {}

    def entry(word: str) -> DictionaryEntry:
        return entries.setdefault(word.lower(), DictionaryEntry(word=word, glossary_id=None, variants=[]))

    for g in db.scalars(select(GlossaryTerm)):
        entry(g.term).glossary_id = g.id
    for r in db.scalars(select(CorrectionRule).order_by(CorrectionRule.find)):
        entry(r.replace).variants.append(
            DictionaryVariant(rule_id=r.id, find=r.find, enabled=r.enabled, times_applied=r.times_applied)
        )
    return sorted(entries.values(), key=lambda e: e.word.lower())


@app.delete("/dictionary", status_code=204)
def delete_dictionary_word(word: str, db: Session = Depends(get_db)) -> None:
    """Hapus satu kata dari Kamus: kosakatanya dan semua variasi salah dengarnya."""
    w = word.strip().lower()
    for g in db.scalars(select(GlossaryTerm).where(func.lower(GlossaryTerm.term) == w)):
        db.delete(g)
    for r in db.scalars(select(CorrectionRule).where(func.lower(CorrectionRule.replace) == w)):
        db.delete(r)
    db.commit()
