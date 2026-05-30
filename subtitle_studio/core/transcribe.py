"""Speech-to-text via faster-whisper with GPU acceleration and CPU fallback.

Produces word-level timestamps which are then re-segmented into readable,
length-limited subtitle cues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from subtitle_studio import config
from subtitle_studio.core import cuda_setup


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    cues: List[Cue]
    language: str
    duration: float


# Picked the device/compute lazily and cached so the (slow) model load happens once.
_model_cache: dict = {}


def _resolve_device(device: str, compute_type: str) -> tuple[str, str]:
    """Resolve 'auto' device/compute_type, preferring CUDA when usable."""
    if device == "auto":
        try:
            cuda_setup.register_cuda_dlls()
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device = "cuda"
            else:
                device = "cpu"
        except Exception:
            device = "cpu"
    elif device == "cuda":
        cuda_setup.register_cuda_dlls()

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def load_model(model: str, device: str, compute_type: str):
    """Load (and cache) a WhisperModel, falling back from CUDA to CPU on failure."""
    from faster_whisper import WhisperModel

    device, compute_type = _resolve_device(device, compute_type)
    key = (model, device, compute_type)
    if key in _model_cache:
        return _model_cache[key], device

    try:
        m = WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            download_root=str(config.model_cache_dir()),
        )
    except Exception:
        if device == "cuda":
            # GPU stack unavailable/incompatible -> degrade gracefully to CPU.
            device, compute_type = "cpu", "int8"
            key = (model, device, compute_type)
            m = WhisperModel(
                model,
                device=device,
                compute_type=compute_type,
                download_root=str(config.model_cache_dir()),
            )
        else:
            raise
    _model_cache[key] = m
    return m, device


def transcribe(
    audio_path: str | Path,
    settings: config.Settings,
    progress: Optional[Callable[[float, str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> TranscriptionResult:
    """Transcribe an audio file into re-segmented subtitle cues.

    ``progress(fraction, message)`` is called as audio is processed.
    ``cancelled()`` is polled; returning True aborts with a RuntimeError.
    """
    if progress:
        progress(0.0, "Loading model…")

    lang = None if settings.source_language == "auto" else settings.source_language

    def run(device: str, compute_type: str):
        """Load + fully consume the segment generator on the given device.

        Iteration is what actually triggers CUDA kernels, so any GPU failure
        surfaces here and is caught by the caller for CPU fallback.
        """
        model, used = load_model(settings.model, device, compute_type)
        if progress:
            progress(0.02, f"Transcribing on {used.upper()}…")
        segments, info = model.transcribe(
            str(audio_path),
            language=lang,
            word_timestamps=True,
            vad_filter=True,                 # skip silence -> cleaner timing
            vad_parameters={"min_silence_duration_ms": 500},
            beam_size=5,                     # higher accuracy
        )
        dur = float(getattr(info, "duration", 0.0)) or 1.0
        words: List[Word] = []
        plain: List[Cue] = []
        for seg in segments:
            if cancelled and cancelled():
                raise RuntimeError("Cancelled")
            if seg.words:
                for w in seg.words:
                    if w.word and w.word.strip():
                        words.append(Word(w.start, w.end, w.word))
            else:
                plain.append(Cue(seg.start, seg.end, seg.text.strip()))
            if progress and dur:
                frac = max(0.02, min(0.99, seg.end / dur))
                progress(frac, f"Transcribing on {used.upper()}…")
        detected = getattr(info, "language", lang or "unknown")
        return words, plain, dur, detected

    try:
        raw_words, plain_cues, duration, detected_lang = run(
            settings.device, settings.compute_type
        )
    except RuntimeError as exc:
        msg = str(exc)
        # CUDA libraries missing/incompatible at inference time -> retry on CPU.
        if msg != "Cancelled" and settings.device != "cpu" and \
                any(k in msg.lower() for k in ("cuda", "cublas", "cudnn", "gpu", "library")):
            if progress:
                progress(0.02, "GPU unavailable — falling back to CPU…")
            raw_words, plain_cues, duration, detected_lang = run("cpu", "int8")
        else:
            raise

    if raw_words:
        cues = _resegment(
            raw_words,
            max_chars=settings.max_chars_per_line * settings.max_lines,
        )
    else:
        cues = plain_cues

    if progress:
        progress(1.0, "Transcription complete")

    return TranscriptionResult(
        cues=cues,
        language=detected_lang,
        duration=duration,
    )


# Sentence-ending punctuation we prefer to break cues on.
_SENTENCE_END = ".!?。！？…"
_CLAUSE_END = ",;:、，；："


def _resegment(words: List[Word], max_chars: int, max_gap: float = 0.8) -> List[Cue]:
    """Group word-level timestamps into readable cues.

    Breaks on sentence punctuation, long pauses, or when the character budget is
    exceeded - this is what makes the timing feel accurate and natural.
    """
    cues: List[Cue] = []
    cur: List[Word] = []

    def flush() -> None:
        if not cur:
            return
        text = "".join(w.text for w in cur).strip()
        text = " ".join(text.split())
        cues.append(Cue(cur[0].start, cur[-1].end, text, list(cur)))
        cur.clear()

    for i, w in enumerate(words):
        if cur:
            gap = w.start - cur[-1].end
            cur_len = sum(len(x.text) for x in cur)
            if gap > max_gap or cur_len >= max_chars:
                flush()
        cur.append(w)
        stripped = w.text.strip()
        if stripped and stripped[-1] in _SENTENCE_END:
            flush()
        elif stripped and stripped[-1] in _CLAUSE_END and \
                sum(len(x.text) for x in cur) >= max_chars * 0.6:
            flush()
    flush()
    return cues
