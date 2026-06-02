from pathlib import Path
from typing import Optional, Callable
from app.config import (
    WHISPER_MODEL, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, MLX_WHISPER_REPO,
    mlx_disabled,
)

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
        # mlx is skipped when config.mlx_disabled() is true — set by the installer
        # (or the heavy-stage CPU fallback) when mlx's Metal init/compute crashes
        # on this machine (e.g. some M1 configs). A Metal SIGABRT can't be caught
        # in-process, so we avoid it entirely and use faster-whisper, which works
        # on every Mac.
        if not mlx_disabled():
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
                _t("mlx unavailable (" + repr(e) + "), falling back to faster_whisper")
        else:
            _t("mlx disabled for this machine — using faster_whisper directly")

        if _model is None:
            import os
            _t("import faster_whisper")
            from faster_whisper import WhisperModel
            device = WHISPER_DEVICE
            if device == "auto":
                # Any failure importing torch (missing, numpy-2 ABI break, or an
                # x86_64 build on arm64 raising OSError on dlopen) must fall back
                # to CPU — faster-whisper uses ctranslate2, not torch, so it works
                # regardless. Catch broadly, not just ImportError.
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    device = "cpu"
            # Use every CPU core so the int8 model runs as fast as the machine allows.
            cpu_threads = os.cpu_count() or 4
            _t("creating WhisperModel device=" + device + " cpu_threads=" + str(cpu_threads))
            _model = WhisperModel(
                WHISPER_MODEL, device=device,
                compute_type=WHISPER_COMPUTE_TYPE, cpu_threads=cpu_threads,
            )
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


def _load_wav_f32(path: str):
    """Load a 16 kHz mono PCM WAV (what audio_extractor always produces) into a
    float32 numpy array in [-1, 1]. Returns None for unexpected formats so the
    caller can fall back to letting mlx decode via ffmpeg."""
    import wave
    import numpy as np
    try:
        with wave.open(path, "rb") as wf:
            ch, sw, sr, n = (wf.getnchannels(), wf.getsampwidth(),
                             wf.getframerate(), wf.getnframes())
            raw = wf.readframes(n)
        if sr != 16000:
            return None
        if sw == 2:
            a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            a = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
        elif sw == 1:
            a = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            return None
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        return np.ascontiguousarray(a, dtype=np.float32)
    except Exception:
        return None


def _transcribe_mlx(audio_path, language, progress_cb, repo):
    import mlx_whisper

    kwargs = {"path_or_hf_repo": repo, "word_timestamps": False, "verbose": False}
    if language:
        kwargs["language"] = language

    # Feed mlx a preloaded float32 array instead of the path. This avoids
    # mlx_whisper.load_audio() shelling out to the bare `ffmpeg` binary (which
    # fails inside a .app bundle that lacks ffmpeg on PATH) and skips a redundant
    # full-file decode. Falls back to the path if the WAV isn't the expected form.
    audio_input = _load_wav_f32(audio_path)
    if audio_input is None:
        audio_input = audio_path

    result = mlx_whisper.transcribe(audio_input, **kwargs)

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
