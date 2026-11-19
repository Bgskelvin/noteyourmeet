from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import process_meeting
from app.services.corrections import edit_pairs, new_terms
from tests.test_cancel import _claim, _upload


def _process_new(c: TestClient) -> dict:
    mid = _upload(c)
    _claim(mid)
    process_meeting(mid)
    return c.get(f"/meetings/{mid}").json()


def _cleanup(c: TestClient) -> None:
    for r in c.get("/corrections").json():
        c.delete(f"/corrections/{r['id']}")
    for t in c.get("/glossary").json():
        c.delete(f"/glossary/{t['id']}")


def test_edit_pairs_and_new_terms():
    assert edit_pairs("ke nomor CSILC di chat", "ke nomor CS ALC di chat") == [("CSILC", "CS ALC")]
    assert new_terms("santai rio ada kan", "santai Rio ada kan, Bang") == ["Rio", "Bang"]
    # Menulis ulang kalimat panjang bukan pola salah-dengar → tidak jadi saran aturan
    assert edit_pairs("aku tidak tahu apa apa soal itu", "Kami akan membahas anggaran minggu depan") == []


def test_remembered_replacement_is_applied_to_next_meeting():
    with TestClient(app) as c:
        try:
            first = _process_new(c)
            r = c.post(f"/meetings/{first['id']}/replace",
                       json={"find": "iklan", "replace": "ads", "remember": True}).json()
            assert r["segments_changed"] == 2
            rules = c.get("/corrections").json()
            assert [(x["find"], x["replace"], x["enabled"]) for x in rules] == [("iklan", "ads", True)]

            # Meeting berikutnya: koreksi diterapkan otomatis saat diproses
            second = _process_new(c)
            fixed = [s for s in second["segments"] if s["auto_corrected"]]
            assert len(fixed) == 2 and all("ads" in s["text"] and "iklan" in s["original_text"] for s in fixed)
            assert second["processing_info"]["auto_corrections"] == 2
            assert c.get("/corrections").json()[0]["times_applied"] == 2

            # Edit tangan pada kalimat otomatis → jadi "diedit", bukan "otomatis"
            d = c.patch(f"/segments/{fixed[0]['id']}", json={"text": "Budget ads bagaimana?"}).json()
            assert next(s for s in d["segments"] if s["id"] == fixed[0]["id"])["auto_corrected"] is None

            # Aturan dimatikan → tidak diterapkan lagi
            c.patch(f"/corrections/{rules[0]['id']}", json={"enabled": False})
            third = _process_new(c)
            assert not any(s["auto_corrected"] for s in third["segments"])

            # Hidupkan lagi lalu terapkan ke meeting yang sudah ada tanpa proses ulang
            c.patch(f"/corrections/{rules[0]['id']}", json={"enabled": True})
            r = c.post(f"/meetings/{third['id']}/apply-corrections").json()
            assert r == {"matches": 2, "segments_changed": 2}
            third = c.get(f"/meetings/{third['id']}").json()
            assert sum(1 for s in third["segments"] if s["auto_corrected"]) == 2
        finally:
            _cleanup(c)


def test_suggestions_learned_from_manual_edits():
    with TestClient(app) as c:
        try:
            m = _process_new(c)
            seg = next(s for s in m["segments"] if s["text"].startswith("Desain landing page"))
            c.patch(f"/segments/{seg['id']}", json={"text": "Desain landing page CS ALC selesai hari Jumat."})

            sug = c.get("/suggestions").json()
            assert {"term": "CS ALC", "count": 1, "example": "Desain landing page CS ALC selesai hari Jumat."} in sug[
                "terms"
            ]
            assert any(r["find"] == "targetnya" and r["replace"] == "CS ALC" for r in sug["rules"])

            # Ditambahkan ke kosakata / dijadikan aturan → saran hilang
            c.post("/glossary", json={"term": "CS ALC"})
            c.post("/corrections", json={"find": "targetnya", "replace": "CS ALC"})
            sug = c.get("/suggestions").json()
            assert not any(t["term"] == "CS ALC" for t in sug["terms"])
            assert not any(r["find"] == "targetnya" for r in sug["rules"])

            # Ditolak → tidak muncul lagi
            c.patch(f"/segments/{seg['id']}", json={"text": "Desain landing page Figma selesai hari Jumat."})
            assert any(t["term"] == "Figma" for t in c.get("/suggestions").json()["terms"])
            assert c.post("/suggestions/dismiss", json={"kind": "term", "value": "Figma"}).status_code == 204
            assert not any(t["term"] == "Figma" for t in c.get("/suggestions").json()["terms"])
        finally:
            _cleanup(c)
