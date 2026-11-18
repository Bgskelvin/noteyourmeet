import logging
import zipfile

from fastapi.testclient import TestClient

from app.backup import make_backup
from app.config import get_settings
from app.main import app
from tests.test_cancel import _claim, _upload


def test_backup_contains_db_and_transcripts_but_audio_is_optional(tmp_path):
    from app.pipeline import process_meeting

    with TestClient(app) as c:
        mid = _upload(c)
        _claim(mid)
        process_meeting(mid)

    out = make_backup(tmp_path, keep=2)
    names = zipfile.ZipFile(out).namelist()
    assert "noteyourmeet.db" in names
    assert any(n.endswith("transcription.json") for n in names)
    assert not any("original" in n or n.endswith("processed.wav") for n in names)

    with_audio = zipfile.ZipFile(make_backup(tmp_path / "a", with_audio=True)).namelist()
    assert any(n.endswith("original.wav") for n in with_audio)
    assert not any(n.endswith("processed.wav") for n in with_audio)


def test_logs_written_to_file():
    with TestClient(app):
        logging.getLogger("tes").warning("halo log file")
    for h in logging.getLogger().handlers:
        h.flush()
    log = (get_settings().data_dir / "logs" / "api.log").read_text(encoding="utf-8")
    assert "halo log file" in log
