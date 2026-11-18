from app.services.metrics import TimedSpeech, normalize_words, speaker_error, word_error_rate


def test_normalize_words():
    assert normalize_words("Udah, di-share bos! Tes_123?") == ["udah", "di", "share", "bos", "tes", "123"]


def test_wer_counts_each_error_type():
    r = word_error_rate("ke nomor CS ALC di chat", "ke nomor CSILC di chat nya")
    # "cs alc" → "csilc" = 1 ganti + 1 hilang; "nya" = 1 berlebih
    assert (r.substitutions, r.deletions, r.insertions) == (1, 1, 1)
    assert r.ref_words == 6 and abs(r.wer - 3 / 6) < 1e-9
    assert word_error_rate("Halo, semua.", "halo semua").wer == 0


def test_speaker_error_maps_labels_by_overlap():
    ref = [TimedSpeech("Budi", 0, 2000), TimedSpeech("Sari", 2000, 4000)]
    perfect = [TimedSpeech("B", 0, 2000), TimedSpeech("A", 2000, 4000)]  # label beda, pembagian sama
    r = speaker_error(ref, perfect)
    assert r.error == 0 and r.mapping == {"B": "Budi", "A": "Sari"}

    # Kata pertama Sari (0,5 dtk) masih dianggap Budi → 0,5 dari 4 dtk salah
    late = [TimedSpeech("A", 0, 2500), TimedSpeech("B", 2500, 4000)]
    assert abs(speaker_error(ref, late).error - 0.125) < 1e-9

    # Pembicara terlewat seluruhnya
    assert speaker_error(ref, [TimedSpeech("A", 0, 2000)]).error == 0.5
