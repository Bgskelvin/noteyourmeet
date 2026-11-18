"""Versi kode yang sedang berjalan (commit git) — dicatat di resep pemrosesan tiap meeting."""

import subprocess
from functools import cache

from app.config import API_DIR

REPO_DIR = API_DIR.parent.parent


@cache
def code_version() -> str | None:
    """Mis. 'b99343e' atau 'b99343e+perubahan' bila ada perubahan yang belum di-commit."""
    try:
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", *a], cwd=REPO_DIR, capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
        commit = run("rev-parse", "--short", "HEAD")
        dirty = bool(run("status", "--porcelain", "--untracked-files=no"))
        return f"{commit}+perubahan" if dirty else commit
    except Exception:  # git tidak terpasang / bukan repo
        return None
