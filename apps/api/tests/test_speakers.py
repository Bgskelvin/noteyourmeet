from app.services.speakers import label_for_index, process_segments
from app.services.transcription.base import Segment, Word


def test_label_for_index():
    assert [label_for_index(i) for i in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


def _seg(speaker: str, *words: tuple[str, str | None], start: int = 0, step: int = 300) -> Segment:
    """Buat segmen Whisper dengan kata berurutan, masing-masing `step` ms."""
    ws = [Word(t, start + i * step, start + (i + 1) * step, spk) for i, (t, spk) in enumerate(words)]
    return Segment(speaker, start, start + len(words) * step, " ".join(t for t, _ in words), words=ws)


def test_split_when_speaker_really_changes_mid_segment_and_relabel():
    seg = _seg(
        "SPEAKER_03",
        ("halo", "SPEAKER_03"), ("semua", "SPEAKER_03"), ("apa", "SPEAKER_03"), ("kabar", "SPEAKER_03"),
        # speaker None = ikut kata sebelumnya
        ("iya", "SPEAKER_01"), ("baik", "SPEAKER_01"), ("terima", None), ("kasih", "SPEAKER_01"),
    )
    segs, stats = process_segments([seg])
    assert [(s.speaker, s.text) for s in segs] == [("A", "halo semua apa kabar"), ("B", "iya baik terima kasih")]
    assert segs[1].start_ms == 1200 and segs[1].end_ms == 2400
    assert {s.label: s.word_count for s in stats} == {"A": 4, "B": 4}


def test_boundary_word_follows_its_sentence():
    """Kasus nyata: "Gak pada puasa kan? | Gak pada puasa." — kata pertama ikut pembicara sebelumnya."""
    segs, _ = process_segments([
        _seg("S1", ("Gak", "S1"), ("pada", "S1"), ("puasa", "S1"), ("kan?", "S1")),
        _seg("S0", ("Gak", "S1"), ("pada", "S0"), ("puasa.", "S0"), start=2000),
        _seg("S0", ("Kita", "S1"), ("buka", "S0"), ("dulu", "S0"), ("ya.", "S0"), start=6000),
    ])
    assert [(s.speaker, s.text) for s in segs] == [
        ("A", "Gak pada puasa kan?"),
        ("B", "Gak pada puasa."),
        ("B", "Kita buka dulu ya."),
    ]


def test_single_word_sandwiched_is_absorbed_but_fast_exchange_kept():
    # "nanti aja terakhir [pas] sesi itu" → 1 kata diapit pembicara sama → ikut
    segs, _ = process_segments([
        _seg("B", ("nanti", "B"), ("aja", "B"), ("terakhir", "B"), ("pas", "A"), ("sesi", "B"), ("itu", "B")),
    ])
    assert [s.text for s in segs] == ["nanti aja terakhir pas sesi itu"]

    # Obrolan cepat dalam kalimat panjang tanpa titik: potongan 2 kata di tengah tetap dipisah
    segs, _ = process_segments([
        _seg("X", ("pakaiannya", "X"), ("kudu", "X"), ("formal", "X"), ("nih", "X"),
             ("santai", "Y"), ("aja", "Y"),
             ("Rio", "X"), ("ada", "X"), ("kan", "X"), ("Bang", "X")),
    ])
    assert [(s.speaker, s.text) for s in segs] == [
        ("A", "pakaiannya kudu formal nih"), ("B", "santai aja"), ("A", "Rio ada kan Bang"),
    ]


def test_merge_consecutive_same_speaker_and_stats():
    segs, stats = process_segments([
        Segment("S0", 0, 1000, "satu"),
        Segment("S0", 1500, 2500, "dua"),      # jeda 0,5 dtk -> digabung
        Segment("S1", 3000, 4000, "tiga"),
        Segment("S0", 9000, 10000, "empat"),   # giliran baru
        Segment(None, 10100, 11000, "lima"),   # tanpa speaker -> ikut S0
    ])
    assert [(s.speaker, s.text) for s in segs] == [("A", "satu dua"), ("B", "tiga"), ("A", "empat lima")]
    a = next(s for s in stats if s.label == "A")
    assert a.turn_count == 2
    assert a.talk_time_ms == 2500 + 2000
    assert len(stats) == 2
