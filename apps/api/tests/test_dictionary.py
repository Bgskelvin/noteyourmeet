from fastapi.testclient import TestClient

from app.main import app
from app.services.corrections import is_common, is_name_like
from tests.test_learning import _cleanup, _process_new


def test_classifiers():
    assert is_name_like("CS ALC") and is_name_like("Rio") and is_name_like("iPhone")
    assert not is_name_like("Dua") and not is_name_like("dua menit") and not is_name_like("di-save")
    assert is_common("Tuh") and is_common("ini") and is_common("ya")
    assert not is_common("CSILC") and not is_common("tuh menit")


def test_learn_routes_names_to_whisper_and_common_words_need_confirmation():
    with TestClient(app) as c:
        try:
            m = _process_new(c)

            # Nama/singkatan → memori + kosakata Whisper, sekaligus diganti di meeting
            r = c.post("/learn", json={"find": "iklan", "replace": "Iklan ALC", "meeting_id": m["id"]}).json()
            assert r["glossary_added"] and r["heard_by_whisper"] and r["segments_changed"] == 2
            # Kata biasa → hanya memori
            r = c.post("/learn", json={"find": "persetujuan", "replace": "approval"}).json()
            assert not r["glossary_added"] and not r["heard_by_whisper"] and r["segments_changed"] == 0
            # Kata sangat umum → 409 sampai dikonfirmasi
            assert c.post("/learn", json={"find": "Tuh", "replace": "Dua"}).status_code == 409
            assert c.post("/learn", json={"find": "Tuh", "replace": "Dua", "confirm_common": True}).status_code == 200
            # Variasi salah dengar kedua untuk kata yang sama
            r = c.post("/learn", json={"find": "iklan elsi", "replace": "Iklan ALC"}).json()
            assert r["heard_by_whisper"] and not r["glossary_added"]  # sudah ada di kosakata

            words = {e["word"]: e for e in c.get("/dictionary").json()}
            assert sorted(v["find"] for v in words["Iklan ALC"]["variants"]) == ["iklan", "iklan elsi"]
            assert words["Iklan ALC"]["glossary_id"] is not None
            assert words["approval"]["glossary_id"] is None and len(words["approval"]["variants"]) == 1

            # Hapus satu kata dari Kamus → kosakata & semua variasinya hilang
            assert c.request("DELETE", "/dictionary", params={"word": "iklan alc"}).status_code == 204
            words = {e["word"] for e in c.get("/dictionary").json()}
            assert "Iklan ALC" not in words and "approval" in words
            assert not any(t["term"] == "Iklan ALC" for t in c.get("/glossary").json())
        finally:
            _cleanup(c)


def test_suggestions_ignore_edits_already_explained_by_dictionary():
    with TestClient(app) as c:
        try:
            m = _process_new(c)
            # "Perbaiki" lewat Kamus mengubah 2 kalimat → itu bukan saran baru
            c.post("/learn", json={"find": "iklan", "replace": "Iklan ALC", "meeting_id": m["id"]})
            sug = c.get("/suggestions").json()
            assert not any("ALC" in t["term"] for t in sug["terms"])
            assert not any(r["replace"].startswith("Iklan") for r in sug["rules"])

            # Editan tangan dengan nama ber-akhiran "-nya" → disarankan tanpa akhiran
            seg = next(s for s in m["segments"] if s["text"].startswith("Desain"))
            c.patch(f"/segments/{seg['id']}", json={"text": "Desain landing page Canva-nya selesai hari Jumat."})
            assert any(t["term"] == "Canva" for t in c.get("/suggestions").json()["terms"])
        finally:
            _cleanup(c)
            c.post("/suggestions/dismiss", json={"kind": "term", "value": "Canva"})
