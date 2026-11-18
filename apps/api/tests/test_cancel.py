from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Meeting, MeetingStatus, utcnow
from app.pipeline import claim_next, process_meeting, requeue_stuck
from app.services.transcription.fake_provider import FakeProvider
from tests.test_api_pipeline import _wav_bytes


def _upload(c: TestClient) -> int:
    r = c.post("/meetings", files={"file": ("a.wav", _wav_bytes(1), "audio/wav")})
    assert r.status_code == 201
    return r.json()["id"]


def _claim(mid: int) -> None:
    """Ambil meeting dari antrean (proses dulu meeting lain yang mungkin tersisa dari test sebelumnya)."""
    with SessionLocal() as db:
        while (got := claim_next(db)) not in (mid, None):
            process_meeting(got)


class CancelDuringTranscription(FakeProvider):
    """Mensimulasikan user menekan Batalkan di tengah transkripsi."""

    def __init__(self, client: TestClient, meeting_id: int) -> None:
        self.c, self.mid, self.progress_after_cancel = client, meeting_id, []

    def transcribe(self, audio_path, *, on_progress, **kw):
        on_progress("Mengubah suara jadi teks 10%")
        r = self.c.post(f"/meetings/{self.mid}/cancel")
        assert r.status_code == 200 and r.json()["cancel_requested_at"]
        on_progress("Mengubah suara jadi teks 15%")  # titik cek → harus berhenti di sini
        self.progress_after_cancel.append("TIDAK BOLEH SAMPAI SINI")
        return super().transcribe(audio_path, on_progress=on_progress, **kw)


def test_cancel_while_queued_is_immediate():
    with TestClient(app) as c:
        mid = _upload(c)
        r = c.post(f"/meetings/{mid}/cancel")
        assert r.json()["status"] == "CANCELLED"
        assert c.post(f"/meetings/{mid}/cancel").status_code == 200  # idempoten
        assert c.delete(f"/meetings/{mid}").status_code == 204  # boleh dihapus


def test_cancel_while_processing_stops_at_checkpoint_and_can_retry():
    with TestClient(app) as c:
        mid = _upload(c)
        _claim(mid)
        provider = CancelDuringTranscription(c, mid)
        process_meeting(mid, provider)
        assert provider.progress_after_cancel == []

        d = c.get(f"/meetings/{mid}").json()
        assert d["status"] == "CANCELLED"
        assert d["cancel_requested_at"] is None
        assert d["segments"] == []

        # Bisa diproses ulang sampai selesai
        assert c.post(f"/meetings/{mid}/retry").json()["status"] == "QUEUED"
        _claim(mid)
        process_meeting(mid, FakeProvider())
        assert c.get(f"/meetings/{mid}").json()["status"] == "DONE"
        assert c.post(f"/meetings/{mid}/cancel").status_code == 409  # sudah selesai


def test_force_cancel_and_worker_restart():
    with TestClient(app) as c:
        # Paksa batal: langsung CANCELLED walau worker tidak merespons
        a = _upload(c)
        _claim(a)
        assert c.post(f"/meetings/{a}/cancel?force=true").json()["status"] == "CANCELLED"

        # Diminta batal lalu worker mati → saat worker start lagi jadi CANCELLED, bukan diantrekan ulang
        b = _upload(c)
        _claim(b)
        with SessionLocal() as db:
            db.get(Meeting, b).cancel_requested_at = utcnow()
            db.commit()
            requeue_stuck(db)
            assert db.get(Meeting, b).status == MeetingStatus.CANCELLED
