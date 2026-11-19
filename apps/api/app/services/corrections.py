"""Koreksi manual transkrip: cari & ganti kata di semua kalimat sebuah meeting."""

import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Protocol


def build_pattern(find: str, *, match_case: bool, whole_word: bool) -> re.Pattern[str]:
    body = re.escape(find.strip())
    if whole_word:
        # \b tidak cocok untuk kata yang diawali/diakhiri tanda baca (mis. "C++"), jadi pakai lookaround
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, 0 if match_case else re.IGNORECASE)


def replace_in_text(text: str, pattern: re.Pattern[str], replacement: str) -> tuple[str, int]:
    # lambda: agar karakter seperti "\1" atau "\n" di teks pengganti tidak ditafsirkan sebagai regex
    return pattern.subn(lambda _: replacement, text)


def normalize_term(term: str) -> str:
    return " ".join(term.split())


# ---------- Memori koreksi ----------

class RuleLike(Protocol):
    find: str
    replace: str
    whole_word: bool
    match_case: bool


def apply_rules(text: str, rules: Sequence[RuleLike]) -> tuple[str, list[int]]:
    """Terapkan aturan berurutan. Kembalikan teks baru + jumlah penggantian per aturan (urutan sama)."""
    counts = []
    for r in rules:
        pattern = build_pattern(r.find, match_case=r.match_case, whole_word=r.whole_word)
        text, n = replace_in_text(text, pattern, r.replace)
        counts.append(n)
    return " ".join(text.split()), counts


# ---------- Belajar dari editan ----------

_PUNCT = ".,?!;:\"'()[]…“”‘’"
_CLITIC = re.compile(r"-(nya|ku|mu|lah|kah|pun)$", re.IGNORECASE)
MAX_PAIR_WORDS = 3


def _core(tok: str) -> str:
    return tok.strip(_PUNCT)


def edit_pairs(original: str, corrected: str) -> list[tuple[str, str]]:
    """Pasangan 'salah → benar' yang pendek dari satu kalimat yang diedit.

    'ke nomor CSILC di chat' → 'ke nomor CS ALC di chat' menghasilkan [('CSILC', 'CS ALC')].
    Perubahan besar (menulis ulang kalimat) diabaikan karena bukan pola salah-dengar.
    """
    a = [_core(t) for t in original.split()]
    b = [_core(t) for t in corrected.split()]
    pairs = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op != "replace" or i2 - i1 > MAX_PAIR_WORDS or j2 - j1 > MAX_PAIR_WORDS:
            continue
        old, new = " ".join(t for t in a[i1:i2] if t), " ".join(t for t in b[j1:j2] if t)
        if old and new and old != new:
            pairs.append((old, new))
    return pairs


def _term_like(tok: str) -> bool:
    """Calon istilah: mengandung huruf besar (selain huruf pertama saja) atau angka, mis. 'ALC', 'iPhone', 'Q3'.

    Kata berhuruf besar di awal saja (nama: 'Rio', 'Asti') juga dihitung — tapi hanya bila dari bagian yang diedit.
    """
    t = _core(tok)
    return len(t) >= 2 and any(c.isalpha() for c in t) and (any(c.isupper() for c in t) or any(c.isdigit() for c in t))


def new_terms(original: str, corrected: str) -> list[str]:
    """Istilah (nama/singkatan) yang muncul di bagian yang diubah/ditambah user."""
    a = [_core(t) for t in original.split()]
    b = corrected.split()
    terms = []
    for op, _i1, _i2, j1, j2 in SequenceMatcher(a=a, b=[_core(t) for t in b], autojunk=False).get_opcodes():
        if op not in ("replace", "insert"):
            continue
        run: list[str] = []
        for tok in [*b[j1:j2], ""]:  # "" = penutup agar run terakhir diproses
            if tok and _term_like(tok):
                run.append(_CLITIC.sub("", _core(tok)))  # "ALC-nya" → "ALC"
            elif run:
                terms.append(" ".join(run))
                run = []
    return terms


# ---------- Perbaiki pintar: tentukan ke mana sebuah koreksi disimpan ----------

# Kata sehari-hari yang terlalu umum untuk diganti otomatis di semua meeting (butuh konfirmasi user).
COMMON_WORDS = frozenset("""
ini itu tuh nih sih dong deh kok lah kan ya yah yak iya ia oke ok sip nah eh ah oh wah loh lho
yang di ke dari dan atau tapi tetapi juga aja saja udah sudah belum ada apa siapa mana kapan gimana bagaimana
kita kami saya aku gue gua lu lo kamu anda dia mereka bos bang mas mbak pak bu
gak nggak enggak ngga tidak bukan jangan mau bisa akan lagi masih baru terus jadi kalau kalo karena biar
untuk buat sama dengan pada dalam atas bawah sini situ sana mungkin harus perlu
satu dua tiga empat lima enam tujuh delapan sembilan sepuluh
the a an and or but is are to of in on at it this that yes no so ok okay
""".split())


def is_name_like(text: str) -> bool:
    """Nama orang / singkatan / produk ('ALC', 'CS ALC', 'Rio', 'Q3') → layak jadi kosakata Whisper."""
    for tok in text.split():
        core = _core(tok)
        if not _term_like(core):
            continue
        # "Dua" di awal kalimat bukan nama: kapital hanya di huruf pertama + kata umum
        if core[1:].islower() and core.lower() in COMMON_WORDS:
            continue
        return True
    return False


def is_common(find: str) -> bool:
    """Kata salah yang terlalu umum: mengganti semua kemunculannya bisa merusak kalimat lain."""
    words = [_core(t).lower() for t in find.split() if _core(t)]
    return not words or len(_core(find)) <= 2 or all(w in COMMON_WORDS for w in words)
