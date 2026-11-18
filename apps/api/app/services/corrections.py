"""Koreksi manual transkrip: cari & ganti kata di semua kalimat sebuah meeting."""

import re


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
