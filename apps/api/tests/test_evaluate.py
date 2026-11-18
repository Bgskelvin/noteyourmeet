import csv

from fastapi.testclient import TestClient

from app import evaluate
from app.main import app
from app.pipeline import process_meeting
from tests.test_api_pipeline import _wav_bytes
from tests.test_cancel import _claim


def test_parse_time():
    assert evaluate.parse_time("1:40") == 100_000
    assert evaluate.parse_time("01:02:03") == 3_723_000
    assert evaluate.parse_time("90") == 90_000


def test_add_run_cached_and_history(capsys):
    with TestClient(app) as c:
        mid = c.post("/meetings", files={"file": ("e.wav", _wav_bytes(40), "audio/wav")}).json()["id"]
        _claim(mid)
        process_meeting(mid)
        d = c.get(f"/meetings/{mid}").json()
        # Koreksi seperti user: 1 kalimat diubah, 1 pembicara diberi nama
        c.patch(f"/segments/{d['segments'][1]['id']}", json={"text": "Desain landing page selesai hari Kamis."})
        c.patch(f"/speakers/{d['speakers'][0]['id']}", json={"display_name": "Budi"})

    evaluate.cmd_add(mid, "0:00", "0:40", "tes-item")
    item = evaluate.evalset_dir() / "tes-item"
    assert (item / "audio.wav").stat().st_size > 1_000_000  # 40 dtk WAV 16 kHz
    assert "1 kalimat sudah dikoreksi" in capsys.readouterr().out

    evaluate.cmd_run(cached=False, note="baseline", only="tes-item")  # provider fake
    evaluate.cmd_run(cached=True, note="tanpa gpu", only="tes-item")
    rows = list(csv.DictReader((evaluate.evalset_dir() / "results.csv").open(encoding="utf-8")))
    last = rows[-1]
    assert last["catatan"] == "tanpa gpu" and last["cached"] == "True"
    # Hasil fake: 1 kalimat beda dari acuan ("Jumat" vs "Kamis", "targetnya" hilang) → WER > 0; pembicara cocok
    assert 0 < float(last["wer_pct"]) < 20 and float(last["speaker_err_pct"]) == 0
    assert "Budi:" in (item / "hypothesis.txt").read_text(encoding="utf-8")

    evaluate.cmd_history(5)
    assert "tanpa gpu" in capsys.readouterr().out
