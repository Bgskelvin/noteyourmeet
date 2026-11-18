from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", extra="ignore")

    # Penyimpanan
    data_dir: Path = API_DIR / "data"
    database_url: str = ""  # kosong = SQLite di data_dir

    # Web
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 2048

    # Audio
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # Transkripsi
    transcription_provider: str = "whisperx"  # whisperx | fake
    hf_token: str = ""
    whisper_model: str = "large-v3-turbo"
    whisper_compute_type: str = "int8_float16"  # coba "int8" jika hasil kosong/error
    whisper_batch_size: int = 4
    whisper_language: str = "id"
    whisper_device: str = "cuda"
    align_model: str = ""  # kosong = default WhisperX untuk bahasa tsb (jika ada)

    # Worker
    worker_poll_seconds: float = 3.0

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'noteyourmeet.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s
