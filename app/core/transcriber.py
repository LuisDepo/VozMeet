from pathlib import Path
from typing import Optional
from app.config import WHISPER_MODEL, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        device = WHISPER_DEVICE
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        _model = WhisperModel(WHISPER_MODEL, device=device, compute_type=WHISPER_COMPUTE_TYPE)
    return _model


def transcribe(audio_path: str | Path, language: Optional[str] = None) -> dict:
    model = _get_model()
    audio_path = str(audio_path)

    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        word_timestamps=False,
    )

    segments = []
    for seg in segments_iter:
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "confidence": round(getattr(seg, "avg_logprob", 0.0), 4),
        })

    lang = info.language
    lang_display = _lang_display(lang)

    return {
        "segments": segments,
        "language": lang,
        "language_display": lang_display,
        "duration": round(info.duration, 2),
    }


def _lang_display(code: str) -> str:
    mapping = {
        "es": "Español",
        "en": "Inglés",
        "fr": "Francés",
        "pt": "Portugués",
        "de": "Alemán",
        "it": "Italiano",
    }
    return mapping.get(code, code.upper())
