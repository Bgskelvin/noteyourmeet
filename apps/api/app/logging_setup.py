"""Log ke layar DAN ke file (data/logs/<nama>.log), dirotasi agar tidak membengkak.

Tujuannya: error yang terjadi saat jendela sudah ditutup tetap bisa dilacak.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import get_settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(name: str, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_nym", False) for h in root.handlers):
        return  # sudah dipasang (mis. uvicorn --reload memuat ulang modul)
    log_dir = get_settings().data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(log_dir / f"{name}.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    console = logging.StreamHandler(sys.stderr)
    for h in (file_handler, console):
        h.setFormatter(logging.Formatter(FORMAT))
        h._nym = True  # type: ignore[attr-defined]
        root.addHandler(h)
    root.setLevel(level)
    # Library yang terlalu "berisik"
    for noisy in ("httpx", "urllib3", "matplotlib", "speechbrain", "pytorch_lightning", "lightning"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.captureWarnings(True)
