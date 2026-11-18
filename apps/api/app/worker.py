"""Worker: ambil meeting dari antrean (tabel meetings) lalu proses satu per satu di GPU.

Jalankan:  python -m app.worker
"""

import logging
import signal
import time

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.pipeline import claim_next, process_meeting, requeue_stuck
from app.services.transcription import get_provider

log = logging.getLogger("worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True
    log.info("Berhenti setelah pekerjaan saat ini selesai...")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    s = get_settings()
    init_db()
    provider = get_provider()
    with SessionLocal() as db:
        n = requeue_stuck(db)
    log.info("Worker siap (provider=%s, model=%s). %d meeting dilanjutkan.",
             s.transcription_provider, s.whisper_model, n)
    while not _stop:
        with SessionLocal() as db:
            mid = claim_next(db)
        if mid is None:
            time.sleep(s.worker_poll_seconds)
            continue
        log.info("Memproses meeting %s", mid)
        process_meeting(mid, provider)


if __name__ == "__main__":
    main()
