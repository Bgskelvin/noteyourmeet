from app.services.speakers import label_for_index, process_segments
from app.services.transcription.base import Segment, Word


def test_label_for_index():
    assert [label_for_index(i) for i in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


def test_split_when_speaker_changes_mid_segment_and_relabel():
    seg = Segment(
        speaker="SPEAKER_03", start_ms=0, end_ms=4000, text="halo semua iya halo",
        words=[
            Word("halo", 0, 500, "SPEAKER_03"),
            Word("semua", 500, 1000, "SPEAKER_03"),
            Word("iya", 2000, 2500, "SPEAKER_01"),
            Word("halo", 2500, 3000, None),  # ikut speaker sebelumnya
        ],
    )
    segs, stats = process_segments([seg])
    assert [(s.speaker, s.text) for s in segs] == [("A", "halo semua"), ("B", "iya halo")]
    assert segs[1].start_ms == 2000 and segs[1].end_ms == 3000
    assert {s.label: s.word_count for s in stats} == {"A": 2, "B": 2}


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
