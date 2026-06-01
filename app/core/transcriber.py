from pathlib import Path
from typing import Optional, Callable
from app.config import WHISPER_MODEL, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, MLX_WHISPER_REPO

_model = None
_backend = None  # "mlx" or "faster_whisper"


def _t(msg: str):
    """Append a timestamped line to the shared startup trace log (fsync'd so it
    survives a fatal C-extension abort)."""
    try:
        import datetime, os
        log_dir = Path.home() / "Library" / "Logs" / "VozMeet"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(str(log_dir / "startup.log"), "a") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')}] transcriber: {msg}\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass


def is_loaded() -> bool:
    return _model is not None


def _get_model():
    global _model, _backend
    if _model is None:
        # Try mlx-whisper first (Apple Silicon — uses Neural Engine, ~3-5× faster)
        try:
            _t("import mlx_whisper")
            import mlx_whisper  # noqa: F401
            _t("import mlx.core (initialises Metal)")
            import mlx.core  # confirm mlx itself is available
            _t("mlx backend ready")
            _backend = "mlx"
            # mlx_whisper loads lazily on first transcribe call; store sentinel
            _model = {"backend": "mlx", "repo": MLX_WHISPER_REPO}
        except Exception as e:
            # Any non-fatal failure (mlx not installed, or Metal init raised a
            # Python error) falls back to faster-whisper. A *fatal* C-extension
            # abort (signal) can't be caught here — the startup.log line above
            # will be the last entry, telling us which import killed the process.
            _t("mlx unavailable (" + repr(e) + "), falling back to faster_whisper")
            _t("import faster_whisper")
            from faster_whisper import WhisperModel
            device = WHISPER_DEVICE
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            _t("creating WhisperModel device=" + device)
            _model = WhisperModel(WHISPER_MODEL, device=device, compute_type=WHISPER_COMPUTE_TYPE)
            _backend = "faster_whisper"
        _t("backend selected: " + str(_backend))
    return _model


def transcribe(
    audio_path: str | Path,
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> dict:
    model = _get_model()
    audio_path = str(audio_path)

    if _backend == "mlx":
        return _transcribe_mlx(audio_path, language, progress_cb, model["repo"])
    else:
        return _transcribe_faster_whisper(audio_path, language, progress_cb, model)


def _transcribe_mlx(audio_path, language, progress_cb, repo):
    import mlx_whisper

    kwargs = {"path_or_hf_repo": repo, "word_timestamps": False}
    if language:
        kwargs["language"] = language

    result = mlx_whisper.transcribe(audio_path, **kwargs)

    raw_segments = result.get("segments", [])
    lang = result.get("language", "es")

    # Estimate total duration from last segment
    total_duration = raw_segments[-1]["end"] if raw_segments else 1.0

    segments = []
    for seg in raw_segments:
        segments.append({
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "text": seg["text"].strip(),
            "confidence": round(float(seg.get("avg_logprob", 0.0)), 4),
        })
        if progress_cb:
            progress_cb(min(float(seg["end"]) / max(total_duration, 1.0), 1.0))

    return {
        "segments": segments,
        "language": lang,
        "language_display": _lang_display(lang),
        "duration": round(total_duration, 2),
    }


def _transcribe_faster_whisper(audio_path, language, progress_cb, model):
    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=1,
        word_timestamps=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
        temperature=0,
    )

    total_duration = info.duration or 1.0
    segments = []
    for seg in segments_iter:
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "confidence": round(getattr(seg, "avg_logprob", 0.0), 4),
        })
        if progress_cb:
            progress_cb(min(seg.end / total_duration, 1.0))

    lang = info.language
    return {
        "segments": segments,
        "language": lang,
        "language_display": _lang_display(lang),
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
