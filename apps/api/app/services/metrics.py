"""Ukuran kualitas transkrip (dibandingkan dengan transkrip acuan yang sudah dikoreksi manusia).

- WER (word error rate): persentase kata yang salah/hilang/berlebih. 0% = sempurna.
- Speaker error: persentase waktu bicara yang diberikan ke pembicara yang salah (atau terlewat).
"""

import re
from collections import defaultdict
from dataclasses import dataclass

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def normalize_words(text: str) -> list[str]:
    """Huruf kecil, tanpa tanda baca. 'Di-share, bos!' → ['di', 'share', 'bos']."""
    return _WORD.findall(text.lower())


@dataclass
class WerResult:
    wer: float  # 0.0–1.0+ (bisa > 1 bila banyak kata berlebih)
    ref_words: int
    substitutions: int
    deletions: int
    insertions: int


def word_error_rate(reference: str, hypothesis: str) -> WerResult:
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    # DP Levenshtein dengan pencatatan jenis kesalahan: (biaya, sub, del, ins)
    prev = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        cur = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                cur.append(prev[j - 1])
                continue
            s, d, n = prev[j - 1], prev[j], cur[j - 1]
            cur.append(min(
                (s[0] + 1, s[1] + 1, s[2], s[3]),  # ganti
                (d[0] + 1, d[1], d[2] + 1, d[3]),  # hilang
                (n[0] + 1, n[1], n[2], n[3] + 1),  # berlebih
            ))
        prev = cur
    cost, sub, dele, ins = prev[-1]
    return WerResult(cost / max(1, len(ref)), len(ref), sub, dele, ins)


@dataclass
class TimedSpeech:
    speaker: str
    start_ms: int
    end_ms: int


@dataclass
class SpeakerResult:
    error: float  # 0.0–1.0
    ref_speakers: int
    hyp_speakers: int
    mapping: dict[str, str]  # label hasil → label acuan


FRAME_MS = 100


def _frames(segs: list[TimedSpeech]) -> dict[int, str]:
    out: dict[int, str] = {}
    for s in segs:
        for f in range(s.start_ms // FRAME_MS, max(s.start_ms // FRAME_MS + 1, s.end_ms // FRAME_MS)):
            out.setdefault(f, s.speaker)
    return out


def speaker_error(reference: list[TimedSpeech], hypothesis: list[TimedSpeech]) -> SpeakerResult:
    """Label hasil (A, B, ...) dipasangkan ke nama acuan berdasarkan waktu tumpang tindih terbesar."""
    ref, hyp = _frames(reference), _frames(hypothesis)
    overlap: dict[tuple[str, str], int] = defaultdict(int)
    for f, r in ref.items():
        if (h := hyp.get(f)) is not None:
            overlap[(h, r)] += 1
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for (h, r), _ in sorted(overlap.items(), key=lambda kv: -kv[1]):
        if h not in mapping and r not in used:
            mapping[h] = r
            used.add(r)
    wrong = sum(1 for f, r in ref.items() if mapping.get(hyp.get(f, ""), None) != r)
    return SpeakerResult(
        wrong / max(1, len(ref)),
        len({s.speaker for s in reference}),
        len({s.speaker for s in hypothesis}),
        mapping,
    )
