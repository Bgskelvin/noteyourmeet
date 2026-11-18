from app.config import get_settings
from app.services.transcription.base import Segment, TranscriptionProvider, TranscriptionResult

__all__ = ["Segment", "TranscriptionProvider", "TranscriptionResult", "get_provider"]


def get_provider() -> TranscriptionProvider:
    name = get_settings().transcription_provider.lower()
    if name == "whisperx":
        from app.services.transcription.whisperx_provider import WhisperXProvider

        return WhisperXProvider()
    if name == "fake":
        from app.services.transcription.fake_provider import FakeProvider

        return FakeProvider()
    raise ValueError(f"TRANSCRIPTION_PROVIDER tidak dikenal: {name}")
