"""WhisperX: faster-whisper (teks) + wav2vec2 (timestamp per kata) + pyannote (siapa bicara).

Dirancang untuk GPU 6 GB (GTX 1660 Ti): tiap model dimuat bergantian lalu dilepas dari VRAM.
"""

import gc
import inspect
import logging
from pathlib import Path

from app.config import get_settings
from app.services.transcription.base import ProgressFn, Segment, TranscriptionResult, Word

log = logging.getLogger(__name__)


def _free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _pct(on_progress: ProgressFn, label: str):
    """Ubah callback persen WhisperX jadi teks status, tapi hanya tiap naik ≥5% (hemat tulis DB)."""
    last = -100

    def cb(p: float) -> None:
        nonlocal last
        p = int(p)
        if p - last >= 5 or (p >= 100 > last):
            last = p
            on_progress(f"{label} {min(p, 100)}%")

    return cb


def _load_wav_16k(path: Path):
    """Baca WAV 16 kHz mono PCM16 hasil pipeline (tanpa memanggil ffmpeg lagi) → float32 [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError(f"Audio harus WAV 16 kHz mono 16-bit: {path.name}")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def _ms(v) -> int | None:
    return None if v is None else int(round(float(v) * 1000))


def _diarization_pipeline(token: str, device: str):
    try:  # whisperx >= 3.4
        from whisperx.diarize import DiarizationPipeline
    except ImportError:  # versi lama
        from whisperx import DiarizationPipeline  # type: ignore[no-redef]

    params = inspect.signature(DiarizationPipeline.__init__).parameters
    key = "token" if "token" in params else "use_auth_token"
    return DiarizationPipeline(**{key: token}, device=device)


class WhisperXProvider:
    def __init__(self) -> None:
        self.s = get_settings()

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        min_speakers: int | None,
        max_speakers: int | None,
        on_progress: ProgressFn,
    ) -> TranscriptionResult:
        import whisperx

        s = self.s
        if not s.hf_token:
            raise RuntimeError(
                "HF_TOKEN belum diisi di apps/api/.env — dibutuhkan untuk mendeteksi pembicara (pyannote)."
            )
        device = s.whisper_device
        lang = language or s.whisper_language or None
        if lang == "auto":
            lang = None  # biarkan Whisper mendeteksi bahasa

        on_progress("Memuat audio")
        audio = _load_wav_16k(audio_path)

        # 1) Teks
        on_progress(f"Memuat model {s.whisper_model} (pertama kali: unduh ±1,5 GB)")
        model = whisperx.load_model(s.whisper_model, device, compute_type=s.whisper_compute_type, language=lang)
        result = model.transcribe(
            audio, batch_size=s.whisper_batch_size, language=lang,
            progress_callback=_pct(on_progress, "Mengubah suara jadi teks"),
        )
        lang = result.get("language") or lang or "id"
        del model
        _free_gpu()
        if not result.get("segments"):
            raise RuntimeError(
                "Tidak ada ucapan yang terdeteksi. Jika audio jelas berisi suara, coba WHISPER_COMPUTE_TYPE=int8."
            )

        # 2) Timestamp per kata (opsional; tidak semua bahasa punya model default)
        on_progress("Menyelaraskan timestamp per kata")
        try:
            kwargs = {"model_name": s.align_model} if s.align_model else {}
            align_model, meta = whisperx.load_align_model(language_code=lang, device=device, **kwargs)
            result = whisperx.align(
                result["segments"], align_model, meta, audio, device, return_char_alignments=False,
                progress_callback=_pct(on_progress, "Menyelaraskan timestamp per kata"),
            )
            del align_model
        except Exception as e:
            log.warning("Alignment dilewati (%s): %s", lang, e)
            on_progress("Alignment dilewati — speaker ditentukan per kalimat")
        _free_gpu()

        # 3) Siapa bicara
        on_progress("Mendeteksi siapa yang berbicara")
        diarize = _diarization_pipeline(s.hf_token, device)
        diar_segments = diarize(
            audio, min_speakers=min_speakers, max_speakers=max_speakers,
            progress_callback=_pct(on_progress, "Mendeteksi siapa yang berbicara"),
        )
        result = whisperx.assign_word_speakers(diar_segments, result)
        del diarize
        _free_gpu()

        segments: list[Segment] = []
        for seg in result["segments"]:
            words = [
                Word(
                    text=w.get("word", ""),
                    start_ms=_ms(w.get("start")),
                    end_ms=_ms(w.get("end")),
                    speaker=w.get("speaker"),
                )
                for w in seg.get("words", [])
            ]
            segments.append(
                Segment(
                    speaker=seg.get("speaker"),
                    start_ms=_ms(seg.get("start")) or 0,
                    end_ms=_ms(seg.get("end")) or 0,
                    text=(seg.get("text") or "").strip(),
                    words=words,
                )
            )
        return TranscriptionResult(language=lang, segments=segments)
