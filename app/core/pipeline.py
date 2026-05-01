import time
import threading
import traceback
from pathlib import Path
from typing import Callable, Optional
from app.config import MIN_AUDIO_DURATION_SECONDS, MAX_SPEAKERS_WARNING
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

    if percent not in (-1, 100):
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET status='processing', pipeline_stage=? WHERE id=?",
                (stage, recording_id),
            )


def run_pipeline(recording_id: int, file_path: str):
    t = threading.Thread(
        target=_pipeline_worker,
        args=(recording_id, file_path),
        daemon=True,
    )
    t.start()


def _pipeline_worker(recording_id: int, file_path: str):
    start_time = time.time()
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET last_started_at=CURRENT_TIMESTAMP WHERE id=?",
                (recording_id,),
            )
        _execute_pipeline(recording_id, file_path)
    except Exception as e:
        elapsed = time.time() - start_time
        full_error = traceback.format_exc()
        log.error("[%d] Pipeline error:\n%s", recording_id, full_error)
        _pipeline_errors[recording_id] = full_error
        cb = _progress_callbacks.get(recording_id)
        if cb:
            cb({"percent": -1, "stage": "error", "detail": str(e)})
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET status='error', error_message=?, "
                "total_processing_seconds=COALESCE(total_processing_seconds,0)+? WHERE id=?",
                (full_error[:2000], round(elapsed, 1), recording_id),
            )
    else:
        elapsed = time.time() - start_time
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET total_processing_seconds=COALESCE(total_processing_seconds,0)+? WHERE id=?",
                (round(elapsed, 1), recording_id),
            )


def _execute_pipeline(recording_id: int, file_path: str):
    from app.core.audio_extractor import extract_audio
    from app.core.transcriber import transcribe, is_loaded as whisper_is_loaded
    from app.core.diarizer import diarize
    from app.core.embedder import get_embedding, extract_sample
    from app.core.merger import merge

    log.info("[%d] Pipeline starting for: %s", recording_id, file_path)

    # ── Read current DB state for checkpointing ───────────────────────────────
    with get_db() as conn:
        rec = conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone()

    existing_wav = rec["processed_path"]
    existing_duration = rec["duration_seconds"]
    wav_exists = existing_wav and Path(existing_wav).exists()

    # ── Stage 1: Audio extraction (skip if WAV already on disk) ──────────────
    if wav_exists:
        wav_path = existing_wav
        duration = existing_duration or 0.0
        log.info("[%d] Skipping audio extraction, WAV exists: %s", recording_id, wav_path)
        _notify(recording_id, 8, "Audio listo", f"Reutilizando audio previo · {_fmt_duration(duration)}")
    else:
        _notify(recording_id, 3, "Extrayendo audio", "Convirtiendo a WAV 16 kHz mono con ffmpeg...")
        output_name = f"recording_{recording_id}.wav"
        audio_info = extract_audio(file_path, output_name)
        wav_path = audio_info["output_path"]
        duration = audio_info["duration"]
        log.info("[%d] Audio extracted: %s (%.1fs)", recording_id, wav_path, duration)
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET processed_path=?, duration_seconds=?, pipeline_stage='audio' WHERE id=?",
                (wav_path, duration, recording_id),
            )
        _notify(recording_id, 8, "Audio listo", f"Duración: {_fmt_duration(duration)}")

    if duration < MIN_AUDIO_DURATION_SECONDS:
        _notify(recording_id, 9, "Advertencia", f"Audio corto ({duration:.1f}s). Procesando igualmente.")

    # ── Stage 2: Transcription ────────────────────────────────────────────────
    whisper_hint = (
        "Transcribiendo audio..." if whisper_is_loaded()
        else "Cargando modelo Whisper en memoria (30-60s)..."
    )
    _notify(recording_id, 10, "Iniciando transcripción", whisper_hint)
    log.info("[%d] Starting transcription", recording_id)

    def _transcription_progress(frac: float):
        # Maps 0-1 → 10%-52% on overall bar
        pct = 10 + int(frac * 42)
        _notify(recording_id, pct, "Transcribiendo",
                f"{int(frac * 100)}% del audio · {_fmt_duration(frac * duration)} / {_fmt_duration(duration)}")

    transcript_result = transcribe(wav_path, progress_cb=_transcription_progress)
    transcript_segments = transcript_result["segments"]
    language = transcript_result["language"]
    language_display = transcript_result["language_display"]
    log.info("[%d] Transcription done: %d segments, lang=%s", recording_id, len(transcript_segments), language)

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET language_detected=?, pipeline_stage='transcribed' WHERE id=?",
            (language_display, recording_id),
        )
    _notify(recording_id, 53, "Transcripción completa",
            f"Idioma: {language_display} · {len(transcript_segments)} fragmentos")

    # ── Stage 3: Diarization ─────────────────────────────────────────────────
    _notify(recording_id, 55, "Iniciando diarización", "Separando hablantes con pyannote (puede tardar)...")
    log.info("[%d] Starting diarization", recording_id)
    diarization_segments = diarize(wav_path)

    unique_speakers = list({s["speaker"] for s in diarization_segments})
    speaker_count = len(unique_speakers)
    log.info("[%d] Diarization done: %d speakers", recording_id, speaker_count)

    if speaker_count > MAX_SPEAKERS_WARNING:
        _notify(recording_id, 73, "Advertencia", f"{speaker_count} voces detectadas")

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET speaker_count=?, pipeline_stage='diarized' WHERE id=?",
            (speaker_count, recording_id),
        )
    _notify(recording_id, 75, "Diarización completa", f"{speaker_count} hablantes detectados")

    # ── Stage 4: Merge ───────────────────────────────────────────────────────
    _notify(recording_id, 78, "Fusionando resultados", "Combinando transcripción y diarización...")
    merged = merge(transcript_segments, diarization_segments)
    log.info("[%d] Merge done: %d segments", recording_id, len(merged))

    # ── Stage 5: Embeddings ──────────────────────────────────────────────────
    _notify(recording_id, 82, "Generando huellas vocales", "Calculando embeddings por hablante...")

    speaker_embeddings: dict[str, list] = {s: [] for s in unique_speakers}
    speaker_time: dict[str, float] = {s: 0.0 for s in unique_speakers}

    for d_seg in diarization_segments:
        spk = d_seg["speaker"]
        speaker_time[spk] = speaker_time.get(spk, 0.0) + (d_seg["end"] - d_seg["start"])

    for i, spk in enumerate(unique_speakers):
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
        pct = 82 + int((i + 1) / max(len(unique_speakers), 1) * 8)
        _notify(recording_id, pct, "Generando huellas vocales",
                f"Voz {i + 1}/{len(unique_speakers)} procesada")

    # ── Stage 6: Speaker matching ─────────────────────────────────────────────
    _notify(recording_id, 91, "Comparando con base de datos", "Buscando perfiles conocidos...")

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

    # ── Save segments + mark identifying ─────────────────────────────────────
    _notify(recording_id, 96, "Guardando transcripción", "Almacenando segmentos en base de datos...")
    with get_db() as conn:
        for seg in merged:
            conn.execute(
                "INSERT INTO segments (recording_id, raw_speaker_label, start_time, end_time, text, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (recording_id, seg["speaker_label"], seg["start"], seg["end"],
                 seg["text"], seg["confidence"]),
            )
        conn.execute(
            "UPDATE recordings SET status='identifying', pipeline_stage='identifying' WHERE id=?",
            (recording_id,),
        )

    _pipeline_results[recording_id] = {
        "suggestions": suggestions,
        "speaker_time": speaker_time,
        "total_duration": duration,
        "language": language_display,
    }

    log.info("[%d] Pipeline completed successfully", recording_id)
    _notify(recording_id, 100, "Listo para identificación", "Análisis completado")


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"
