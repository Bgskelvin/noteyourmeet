from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import process_meeting
from app.services.corrections import build_pattern, replace_in_text
from app.services.transcription.fake_provider import FakeProvider
from app.services.transcription.whisperx_provider import HOTWORDS_MAX_CHARS, _hotwords_text
from tests.test_cancel import _claim, _upload


def test_pattern_whole_word_and_case():
    p = build_pattern("csilc", match_case=False, whole_word=True)
    assert replace_in_text("ke nomor CSILC di chat, csilc.", p, "CS ALC") == ("ke nomor CS ALC di chat, CS ALC.", 2)
    assert replace_in_text("CSILCX tidak kena", p, "CS ALC")[1] == 0
    exact = build_pattern("Rio", match_case=True, whole_word=False)
    assert replace_in_text("Rio rio Riordan", exact, "Ryo") == ("Ryo rio Ryordan", 2)
    # karakter khusus di pencarian/pengganti tidak dianggap regex
    assert replace_in_text("C++ dan C#", build_pattern("C++", match_case=True, whole_word=True), r"\1") == (
        r"\1 dan C#", 1,
    )


def test_hotwords_text_is_capped():
    terms = [f"Istilah{i:03d}" for i in range(200)]
    txt = _hotwords_text(terms)
    assert txt.startswith("Istilah000, Istilah001") and len(txt) <= HOTWORDS_MAX_CHARS


class RecordingProvider(FakeProvider):
    def transcribe(self, audio_path, *, hotwords=None, **kw):
        self.hotwords = hotwords
        return super().transcribe(audio_path, hotwords=hotwords, **kw)


def test_edit_replace_and_glossary_flow():
    with TestClient(app) as c:
        # Kosakata tim: bisa tambah banyak sekaligus, duplikat (beda huruf besar) diabaikan
        terms = c.post("/glossary", json={"term": "ALC, CS ALC\nRio , alc"}).json()
        assert sorted(t["term"] for t in terms) == ["ALC", "CS ALC", "Rio"]

        mid = _upload(c)
        _claim(mid)
        prov = RecordingProvider()
        process_meeting(mid, prov)
        assert prov.hotwords == ["ALC", "CS ALC", "Rio"]  # dikirim ke Whisper sebagai hotwords

        d = c.get(f"/meetings/{mid}").json()
        seg = d["segments"][1]  # "Desain landing page targetnya selesai hari Jumat."

        # Edit satu kalimat → teks asli disimpan, lalu bisa dikembalikan
        d = c.patch(f"/segments/{seg['id']}", json={"text": "Desain landing page selesai Kamis."}).json()
        s1 = next(s for s in d["segments"] if s["id"] == seg["id"])
        assert s1["text"] == "Desain landing page selesai Kamis." and s1["original_text"] == seg["text"]
        d = c.patch(f"/segments/{seg['id']}", json={"text": seg["text"]}).json()
        assert next(s for s in d["segments"] if s["id"] == seg["id"])["original_text"] is None

        # Cari & ganti: dry run hanya menghitung
        r = c.post(f"/meetings/{mid}/replace", json={"find": "iklan", "replace": "ads", "dry_run": True}).json()
        assert r == {"matches": 2, "segments_changed": 0}
        r = c.post(f"/meetings/{mid}/replace", json={"find": "iklan", "replace": "ads"}).json()
        assert r == {"matches": 2, "segments_changed": 2}
        texts = [s["text"] for s in c.get(f"/meetings/{mid}").json()["segments"]]
        assert not any("iklan" in t for t in texts) and sum("ads" in t for t in texts) == 2

        for t in terms:
            assert c.delete(f"/glossary/{t['id']}").status_code == 204
        assert c.get("/glossary").json() == []
