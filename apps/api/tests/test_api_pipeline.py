import io
import math
import struct
import wave

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.pipeline import claim_next, process_meeting


def _wav_bytes(seconds: float = 2.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        frames = b"".join(
            struct.pack("<hh", v, v)
            for v in (int(8000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(int(44100 * seconds)))
        )
        w.writeframes(frames)
    return buf.getvalue()


def test_upload_process_rename_merge():
    with TestClient(app) as c:
        r = c.post("/meetings", files={"file": ("rapat.wav", _wav_bytes(), "audio/wav")},
                   data={"title": "Rapat Tes", "min_speakers": "2", "max_speakers": "4"})
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        assert r.json()["status"] == "QUEUED"

        with SessionLocal() as db:
            assert claim_next(db) == mid
        process_meeting(mid)

        d = c.get(f"/meetings/{mid}").json()
        assert d["status"] == "DONE", d["error_message"]
        assert d["speaker_count"] == 3
        assert abs(d["duration_sec"] - 2.0) < 0.1
        assert len(d["segments"]) == 5
        a, b, cc = d["speakers"]

        assert c.patch(f"/speakers/{a['id']}", json={"display_name": "Budi"}).json()["display_name"] == "Budi"

        merged = c.post(f"/meetings/{mid}/speakers/merge",
                        json={"source_ids": [cc["id"]], "target_id": b["id"]}).json()
        assert merged["speaker_count"] == 2
        assert {s["speaker_id"] for s in merged["segments"]} == {a["id"], b["id"]}

        audio = c.get(f"/meetings/{mid}/audio")
        assert audio.status_code == 200 and audio.content[:4] == b"RIFF"

        assert c.post(f"/meetings/{mid}/retry").json()["status"] == "QUEUED"


def test_rejects_unsupported_format():
    with TestClient(app) as c:
        r = c.post("/meetings", files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 415


def test_language_per_meeting_and_retry_with_other_language():
    with TestClient(app) as c:
        assert c.get("/config").json()["default_language"]
        bad = c.post("/meetings", files={"file": ("a.wav", _wav_bytes(1), "audio/wav")}, data={"language": "klingon"})
        assert bad.status_code == 422

        mid = c.post("/meetings", files={"file": ("a.wav", _wav_bytes(1), "audio/wav")},
                     data={"language": "EN"}).json()["id"]
        with SessionLocal() as db:
            while (got := claim_next(db)) not in (mid, None):
                process_meeting(got)
        process_meeting(mid)
        d = c.get(f"/meetings/{mid}").json()
        assert (d["requested_language"], d["language"]) == ("en", "en")

        assert c.post(f"/meetings/{mid}/retry", json={"language": "auto"}).status_code == 200
        assert c.get(f"/meetings/{mid}").json()["requested_language"] == "auto"
        assert c.post(f"/meetings/{mid}/retry", json={"language": "xx"}).status_code == 409  # sudah antre


def test_raw_transcription_saved_for_later_reanalysis():
    import json

    from app.config import get_settings

    with TestClient(app) as c:
        mid = c.post("/meetings", files={"file": ("r.wav", _wav_bytes(1), "audio/wav")}).json()["id"]
        with SessionLocal() as db:
            while (got := claim_next(db)) not in (mid, None):
                process_meeting(got)
        process_meeting(mid)
        with SessionLocal() as db:
            from app.models import Meeting

            folder = (get_settings().storage_dir / db.get(Meeting, mid).audio_path).parent
        raw = json.loads((folder / "transcription.json").read_text(encoding="utf-8"))
        assert raw["language"] and len(raw["segments"]) == 5 and "words" in raw["segments"][0]
