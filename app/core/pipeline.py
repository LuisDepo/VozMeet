import threading
import traceback
from pathlib import Path
from typing import Callable, Optional
from app.config import (
    MIN_AUDIO_DURATION_SECONDS, MAX_SPEAKERS_WARNING,
)
from app.database.db import get_db
from app.database.voice_store import find_matching_speaker
from app.logger import get_logger

log = get_logger("pipeline")

_progress_callbacks: dict[int, Callable] = {}
_pipeline_results: dict[int, dict] = {}
_pipeline_errors: dict[int, str] = {}


def register_progress_callback(recording_id: int, callback: Callable):
    _progress_callbacks[recording_id] = callback


def get_pipeline_result(recording_id: int) -> Optional[dict]:
    return _pipeline_results.get(recording_id)


def get_pipeline_error(recording_id: int) -> Optional[str]:
    return _pipeline_errors.get(recording_id)


def _notify(recording_id: int, percent: int, stage: str, detail: str = ""):
    log.info("[%d] %d%% — %s %s", recording_id, percent, stage, detail)
    cb = _progress_callbacks.get(recording_id)
    if cb:
        cb({"percent": percent, "stage": stage, "detail": detail})

    if percent != -1:
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET status = 'processing' WHERE id = ?",
                (recording_id,),
            )


def run_pipeline(recording_id: int, file_path: str):
    t = threading.Thread(
        target=_pipeline_worker,
        args=(recording_id, file_path),
        daemon=True,
    )
    t.start()


def _pipeline_worker(recording_id: int, file_path: str):
    try:
        _execute_pipeline(recording_id, file_path)
    except Exception as e:
        full_error = traceback.format_exc()
        log.error("[%d] Pipeline error:\n%s", recording_id, full_error)
        short_msg = str(e)
        _pipeline_errors[recording_id] = full_error
        cb = _progress_callbacks.get(recording_id)
        if cb:
            cb({"percent": -1, "stage": "error", "detail": short_msg})
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET status = 'error', error_message = ? WHERE id = ?",
                (full_error[:2000], recording_id),
            )


def _execute_pipeline(recording_id: int, file_path: str):
    from app.core.audio_extractor import extract_audio
    from app.core.transcriber import transcribe
    from app.core.diarizer import diarize
    from app.core.embedder import get_embedding, extract_sample
    from app.core.merger import merge

    log.info("[%d] Pipeline starting for: %s", recording_id, file_path)

    _notify(recording_id, 5, "Extrayendo audio", "Procesando con ffmpeg...")
    output_name = f"recording_{recording_id}.wav"
    audio_info = extract_audio(file_path, output_name)
    wav_path = audio_info["output_path"]
    duration = audio_info["duration"]
    log.info("[%d] Audio extracted: %s (%.1fs)", recording_id, wav_path, duration)

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET processed_path = ?, duration_seconds = ? WHERE id = ?",
            (wav_path, duration, recording_id),
        )

    _notify(recording_id, 15, "Audio listo", f"Duración: {_fmt_duration(duration)}")

    if duration < MIN_AUDIO_DURATION_SECONDS:
        _notify(recording_id, 18, "Advertencia", f"Audio corto ({duration:.1f}s). Procesando igualmente.")

    _notify(recording_id, 20, "Iniciando transcripción", "Cargando modelo Whisper large-v3 (primera vez: varios minutos)...")
    log.info("[%d] Starting transcription", recording_id)
    transcript_result = transcribe(wav_path)
    transcript_segments = transcript_result["segments"]
    language = transcript_result["language"]
    language_display = transcript_result["language_display"]
    log.info("[%d] Transcription done: %d segments, lang=%s", recording_id, len(transcript_segments), language)

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET language_detected = ? WHERE id = ?",
            (language_display, recording_id),
        )

    _notify(recording_id, 55, "Transcripción completa", f"Idioma: {language_display} · {len(transcript_segments)} segmentos")

    _notify(recording_id, 60, "Iniciando diarización", "Identificando hablantes con pyannote (primera vez: varios minutos)...")
    log.info("[%d] Starting diarization", recording_id)
    diarization_segments = diarize(wav_path)

    unique_speakers = list({s["speaker"] for s in diarization_segments})
    speaker_count = len(unique_speakers)
    log.info("[%d] Diarization done: %d speakers", recording_id, speaker_count)

    if speaker_count > MAX_SPEAKERS_WARNING:
        _notify(recording_id, 75, "Advertencia", f"{speaker_count} voces detectadas (reunión muy numerosa)")

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET speaker_count = ? WHERE id = ?",
            (speaker_count, recording_id),
        )

    _notify(recording_id, 80, "Diarización completa", f"{speaker_count} hablantes detectados")
    _notify(recording_id, 85, "Fusionando resultados", "Combinando transcripción y diarización...")

    merged = merge(transcript_segments, diarization_segments)
    log.info("[%d] Merge done: %d merged segments", recording_id, len(merged))

    _notify(recording_id, 90, "Generando huellas vocales", "Calculando embeddings por hablante...")

    speaker_embeddings: dict[str, list] = {s: [] for s in unique_speakers}
    speaker_time: dict[str, float] = {s: 0.0 for s in unique_speakers}

    for d_seg in diarization_segments:
        spk = d_seg["speaker"]
        speaker_time[spk] = speaker_time.get(spk, 0.0) + (d_seg["end"] - d_seg["start"])

    for spk in unique_speakers:
        best_seg = max(
            [s for s in diarization_segments if s["speaker"] == spk],
            key=lambda x: x["end"] - x["start"],
            default=None,
        )
        if best_seg:
            try:
                emb = get_embedding(wav_path, best_seg["start"], best_seg["end"])
                speaker_embeddings[spk].append(emb)
                log.info("[%d] Embedding OK for %s", recording_id, spk)
            except Exception:
                log.warning("[%d] Embedding failed for %s:\n%s", recording_id, spk, traceback.format_exc())

    _notify(recording_id, 95, "Comparando con base de datos", "Buscando perfiles conocidos...")

    suggestions: dict[str, dict] = {}
    for spk in unique_speakers:
        embs = speaker_embeddings.get(spk, [])
        if not embs:
            suggestions[spk] = {"speaker_id": None, "confidence": 0.0, "display_name": None}
            continue

        from app.core.embedder import average_embeddings
        avg_emb = average_embeddings(embs) if len(embs) > 1 else embs[0]
        matched_speaker, score = find_matching_speaker(avg_emb)

        sample_name = f"rec{recording_id}_{spk}.wav"
        best_seg = max(
            [s for s in diarization_segments if s["speaker"] == spk],
            key=lambda x: x["end"] - x["start"],
            default=None,
        )
        sample_path = None
        if best_seg:
            try:
                sample_path = extract_sample(wav_path, best_seg["start"], best_seg["end"], sample_name)
            except Exception:
                log.warning("[%d] Sample extraction failed for %s", recording_id, spk)

        with get_db() as conn:
            existing = conn.execute(
                "SELECT 1 FROM recording_speakers WHERE recording_id=? AND raw_label=?",
                (recording_id, spk),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO recording_speakers (recording_id, raw_label, speaker_id, match_confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (recording_id, spk,
                     matched_speaker.id if matched_speaker else None,
                     round(score, 4)),
                )

        suggestions[spk] = {
            "speaker_id": matched_speaker.id if matched_speaker else None,
            "display_name": matched_speaker.display_name if matched_speaker else None,
            "confidence": round(score, 4),
            "sample_path": sample_path,
            "talk_time": round(speaker_time.get(spk, 0.0), 1),
            "embedding": avg_emb.tolist(),
        }

    with get_db() as conn:
        for seg in merged:
            conn.execute(
                "INSERT INTO segments (recording_id, raw_speaker_label, start_time, end_time, text, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (recording_id, seg["speaker_label"], seg["start"], seg["end"],
                 seg["text"], seg["confidence"]),
            )
        conn.execute(
            "UPDATE recordings SET status = 'identifying' WHERE id = ?",
            (recording_id,),
        )

    _pipeline_results[recording_id] = {
        "suggestions": suggestions,
        "speaker_time": speaker_time,
        "total_duration": duration,
        "language": language_display,
    }

    log.info("[%d] Pipeline completed successfully", recording_id)
    _notify(recording_id, 100, "Listo para identificación", "Pipeline completado")


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"
