"""Logika murni (tanpa AI) untuk merapikan segmen per pembicara & menghitung statistik."""

from dataclasses import dataclass

from app.services.transcription.base import Segment, Word

MERGE_GAP_MS = 1500  # gabung kalimat berurutan dari orang yang sama jika jedanya < 1,5 dtk
MAX_SEGMENT_MS = 45_000  # tapi jangan sampai satu blok > 45 dtk (agar enak dibaca & diklik)
# Pergantian pembicara di tengah kalimat baru dianggap nyata jika potongannya ≥ 3 kata DAN ≥ 0,7 dtk
MIN_RUN_WORDS = 3
MIN_RUN_MS = 700


@dataclass
class CleanSegment:
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None


@dataclass
class SpeakerStats:
    label: str
    talk_time_ms: int
    turn_count: int
    word_count: int


def label_for_index(i: int) -> str:
    """0->A, 25->Z, 26->AA, ..."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


Run = tuple[str | None, list[Word]]


def _run_ms(run: list[Word]) -> int:
    start = next((w.start_ms for w in run if w.start_ms is not None), None)
    end = next((w.end_ms for w in reversed(run) if w.end_ms is not None), None)
    return 0 if start is None or end is None else max(0, end - start)


def _is_short(run: list[Word]) -> bool:
    return len(run) < MIN_RUN_WORDS or _run_ms(run) < MIN_RUN_MS


def absorb_short_runs(runs: list[Run], seg: Segment) -> list[Run]:
    """Satu kalimat Whisper = satu pembicara, kecuali ada orang lain bicara cukup panjang di dalamnya.

    Diarization sering meleset ±0,5 dtk di batas giliran bicara, sehingga 1–2 kata pertama/terakhir
    kalimat ikut pembicara sebelumnya ("Gak | pada puasa", "Kita | buka dulu"). Potongan pendek seperti
    itu digabung ke tetangga yang lebih panjang; potongan panjang tetap dipisah (benar-benar ganti orang).
    """
    runs = [(spk, list(ws)) for spk, ws in runs]
    while len(runs) > 1:
        last = len(runs) - 1
        shorts = [
            i
            for i, (_, ws) in enumerate(runs)
            # (1) potongan pendek di awal/akhir kalimat = kesalahan batas giliran bicara
            if (i in (0, last) and _is_short(ws))
            # (2) satu kata di tengah yang diapit pembicara yang sama ("terakhir [pas] sesi")
            or (0 < i < last and len(ws) == 1 and runs[i - 1][0] == runs[i + 1][0])
        ]
        # Selain itu (mis. obrolan cepat bergantian di kalimat panjang tanpa titik) dibiarkan terpisah.
        if not shorts:
            break
        # Proses potongan terpendek dulu agar hasilnya stabil
        i = min(shorts, key=lambda k: (len(runs[k][1]), _run_ms(runs[k][1])))
        neighbors = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
        # Utamakan tetangga dengan speaker = speaker kalimat (hasil voting WhisperX), lalu yang terpanjang
        j = max(neighbors, key=lambda k: (runs[k][0] == seg.speaker, _run_ms(runs[k][1]), len(runs[k][1])))
        lo, hi = min(i, j), max(i, j)
        runs[lo : hi + 1] = [(runs[j][0], runs[lo][1] + runs[hi][1])]
        # Tetangga yang kini ber-speaker sama digabung juga
        merged: list[Run] = []
        for spk, ws in runs:
            if merged and merged[-1][0] == spk:
                merged[-1][1].extend(ws)
            else:
                merged.append((spk, ws))
        runs = merged
    return runs


def split_by_word_speaker(segments: list[Segment]) -> list[CleanSegment]:
    """Pecah segmen bila speaker berganti di tengah kalimat (pakai info speaker per kata)."""
    out: list[CleanSegment] = []
    for seg in segments:
        words = [w for w in seg.words if w.text.strip()]
        if not words or all(w.speaker is None for w in words):
            out.append(CleanSegment(seg.speaker or "", seg.start_ms, seg.end_ms, seg.text.strip(), seg.confidence))
            continue
        # Kelompokkan kata berurutan dengan speaker yang sama; kata tanpa speaker ikut sebelumnya
        runs: list[tuple[str | None, list[Word]]] = []
        for w in words:
            spk = w.speaker or (runs[-1][0] if runs else seg.speaker)
            if runs and runs[-1][0] == spk:
                runs[-1][1].append(w)
            else:
                runs.append((spk, [w]))
        for spk, run in absorb_short_runs(runs, seg):
            start = next((w.start_ms for w in run if w.start_ms is not None), seg.start_ms)
            end = next((w.end_ms for w in reversed(run) if w.end_ms is not None), seg.end_ms)
            text = " ".join(w.text.strip() for w in run)
            out.append(CleanSegment(spk or seg.speaker or "", start, max(end, start), text, seg.confidence))
    return [s for s in out if s.text]


def fill_unknown_speakers(segs: list[CleanSegment]) -> None:
    """Segmen tanpa speaker ikut speaker sebelumnya (atau sesudahnya jika di awal)."""
    known = next((s.speaker for s in segs if s.speaker), "SPEAKER_00")
    prev = None
    for s in segs:
        if not s.speaker:
            s.speaker = prev or known
        prev = s.speaker


def merge_consecutive(segs: list[CleanSegment]) -> list[CleanSegment]:
    merged: list[CleanSegment] = []
    for s in segs:
        last = merged[-1] if merged else None
        if (
            last
            and last.speaker == s.speaker
            and s.start_ms - last.end_ms <= MERGE_GAP_MS
            and s.end_ms - last.start_ms <= MAX_SEGMENT_MS
        ):
            last.text = f"{last.text} {s.text}"
            last.end_ms = max(last.end_ms, s.end_ms)
            last.confidence = None
        else:
            merged.append(CleanSegment(s.speaker, s.start_ms, s.end_ms, s.text, s.confidence))
    return merged


def relabel(segs: list[CleanSegment]) -> list[str]:
    """Ganti label mentah (SPEAKER_03) jadi A, B, C sesuai urutan pertama kali bicara."""
    mapping: dict[str, str] = {}
    for s in segs:
        if s.speaker not in mapping:
            mapping[s.speaker] = label_for_index(len(mapping))
        s.speaker = mapping[s.speaker]
    return list(mapping.values())


def compute_stats(segs: list[CleanSegment]) -> list[SpeakerStats]:
    stats: dict[str, SpeakerStats] = {}
    prev = None
    for s in segs:
        st = stats.setdefault(s.speaker, SpeakerStats(s.speaker, 0, 0, 0))
        st.talk_time_ms += max(0, s.end_ms - s.start_ms)
        st.word_count += len(s.text.split())
        if s.speaker != prev:
            st.turn_count += 1
        prev = s.speaker
    return sorted(stats.values(), key=lambda x: x.label)


def process_segments(segments: list[Segment]) -> tuple[list[CleanSegment], list[SpeakerStats]]:
    segs = split_by_word_speaker(sorted(segments, key=lambda s: s.start_ms))
    fill_unknown_speakers(segs)
    segs = merge_consecutive(segs)
    relabel(segs)
    return segs, compute_stats(segs)
