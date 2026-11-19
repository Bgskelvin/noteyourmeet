import json

from fastapi.testclient import TestClient

from app import dataset
from app.main import app
from app.pipeline import process_meeting
from tests.test_api_pipeline import _wav_bytes
from tests.test_cancel import _claim


def test_review_marks_stats_and_dataset_export(tmp_path):
    with TestClient(app) as c:
        mid = c.post("/meetings", files={"file": ("d.wav", _wav_bytes(40), "audio/wav")}).json()["id"]
        _claim(mid)
        process_meeting(mid)
        segs = c.get(f"/meetings/{mid}").json()["segments"]
        assert all(s["reviewed_at"] is None for s in segs)

        # Tandai benar (tanpa edit) + edit (otomatis dianggap diperiksa)
        assert c.post(f"/segments/{segs[0]['id']}/review", json={"reviewed": True}).json()["reviewed_at"]
        c.patch(f"/segments/{segs[1]['id']}", json={"text": "Desain landing page selesai hari Kamis."})
        # Tandai lalu batalkan
        c.post(f"/segments/{segs[2]['id']}/review", json={"reviewed": True})
        assert c.post(f"/segments/{segs[2]['id']}/review", json={"reviewed": False}).json()["reviewed_at"] is None

        st = c.get("/review/stats").json()
        mine = next(m for m in st["meetings"] if m["id"] == mid)
        assert (mine["total_segments"], mine["reviewed_segments"]) == (5, 2)
        assert mine["reviewed_ms"] == sum(s["end_ms"] - s["start_ms"] for s in segs[:2])
        assert st["training"]["target_hours"] == 10

    out = dataset.export(tmp_path / "ds")
    lines = [json.loads(x) for x in (tmp_path / "ds" / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    mine = [x for x in lines if x["meeting_id"] == mid]
    assert [x["text"] for x in mine] == [segs[0]["text"], "Desain landing page selesai hari Kamis."]
    for x in mine:
        wav = tmp_path / "ds" / x["file_name"]
        # WAV 16 kHz mono 16-bit: 32 byte per ms (+ header)
        assert abs(wav.stat().st_size - 44 - (x["end_ms"] - x["start_ms"]) * 32) < 64
    assert out["written"] >= 2
