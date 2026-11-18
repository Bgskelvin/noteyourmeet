from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Word:
    text: str
    start_ms: int | None
    end_ms: int | None
    speaker: str | None


@dataclass
class Segment:
    speaker: str | None  # label mentah dari diarization, mis. "SPEAKER_00"
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    language: str
    segments: list[Segment]


ProgressFn = Callable[[str], None]


class TranscriptionProvider(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        min_speakers: int | None,
        max_speakers: int | None,
        on_progress: ProgressFn,
    ) -> TranscriptionResult: ...
