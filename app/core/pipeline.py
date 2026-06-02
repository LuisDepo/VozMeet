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
    from app.core.transcriber import is_loaded as whisper_is_loaded
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

    # ── Stages 2+3: Transcription AND Diarization (isolated subprocess) ──────
    # Both touch Metal/C-extensions that can abort() the whole process on some
    # machines (e.g. certain M1 configs). Running them in a child process keeps
    # a crash from killing the app; on a hard crash we disable the accelerators
    # and retry on CPU automatically.
    whisper_hint = (
        "Transcribiendo y separando voces en paralelo..." if whisper_is_loaded()
        else "Cargando Whisper (30-60s) · separando voces en paralelo..."
    )
    _notify(recording_id, 10, "Procesando audio", whisper_hint)
    log.info("[%d] Starting transcription + diarization (isolated)", recording_id)

    def _transcription_progress(frac: float):
        pct = 10 + int(frac * 55)  # 10% → 65%
        _notify(recording_id, pct, "Transcribiendo",
                f"{int(frac * 100)}% · {_fmt_duration(frac * duration)} / {_fmt_duration(duration)}")

    try:
        transcript_result, diarization_segments = _run_heavy_stage(
            recording_id, wav_path, _transcription_progress, duration,
            cpu_only=False, no_diarize=False)
    except _AcceleratorCrash as crash:
        log.error("[%d] Heavy stage crashed (rc=%s) — disabling Metal accelerators, "
                  "retrying on CPU.\n%s", recording_id, crash.returncode, crash.tail)
        _disable_accelerators()
        _notify(recording_id, 10, "Optimizando para este equipo",
                "Reintentando en modo CPU (compatible con cualquier Mac)...")
        try:
            transcript_result, diarization_segments = _run_heavy_stage(
                recording_id, wav_path, _transcription_progress, duration,
                cpu_only=True, no_diarize=False)
        except _AcceleratorCrash as crash2:
            # Both metal and CPU attempts crashed (likely torch broken on this machine).
            # Fall back to transcription only — faster-whisper never needs torch.
            log.error("[%d] CPU retry also crashed (rc=%s) — falling back to "
                      "transcription-only (no speaker separation).\n%s",
                      recording_id, crash2.returncode, crash2.tail)
            _notify(recording_id, 10, "Procesando audio",
                    "Transcribiendo sin separación de voces (modo de compatibilidad)...")
            transcript_result, diarization_segments = _run_heavy_stage(
                recording_id, wav_path, _transcription_progress, duration,
                cpu_only=True, no_diarize=True)

    transcript_segments = transcript_result["segments"]
    language = transcript_result["language"]
    language_display = transcript_result["language_display"]
    log.info("[%d] Transcription done: %d segments, lang=%s", recording_id, len(transcript_segments), language)

    # No speech at all (silent/music-only file): finish with a clear status
    # instead of silently completing with 0 segments in an "identifying" state.
    if not transcript_segments:
        log.info("[%d] No speech detected in audio", recording_id)
        with get_db() as conn:
            conn.execute(
                "UPDATE recordings SET language_detected=?, speaker_count=0, "
                "status='completed', pipeline_stage='completed', "
                "completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (language_display, recording_id),
            )
        _notify(recording_id, 100, "Completado",
                "No se detectó voz en el audio.")
        _pipeline_results[recording_id] = {"segments": 0, "speakers": 0}
        return

    # When diarization was skipped (torch unavailable), synthesise a single
    # speaker entry covering the full audio so the merge stage still works.
    if not diarization_segments and transcript_segments:
        full_end = transcript_segments[-1]["end"]
        diarization_segments = [{"start": 0.0, "end": full_end, "speaker": "Hablante 1"}]
        log.info("[%d] No diarization — using single-speaker fallback", recording_id)

    unique_speakers = list({s["speaker"] for s in diarization_segments})
    speaker_count = len(unique_speakers)
    log.info("[%d] Diarization done: %d speakers", recording_id, speaker_count)

    if speaker_count > MAX_SPEAKERS_WARNING:
        _notify(recording_id, 66, "Advertencia", f"{speaker_count} voces detectadas — puede tardar más")

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET language_detected=?, speaker_count=?, pipeline_stage='diarized' WHERE id=?",
            (language_display, speaker_count, recording_id),
        )
    _notify(recording_id, 68, "Transcripción completa",
            f"Idioma: {language_display} · {len(transcript_segments)} fragmentos · {speaker_count} voces")

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


class _AcceleratorCrash(Exception):
    """Raised when the heavy-stage subprocess is killed by a signal (e.g. a
    Metal/C-extension SIGABRT), as opposed to a normal Python error."""

    def __init__(self, returncode: int, tail: str):
        super().__init__(f"heavy stage killed (rc={returncode})")
        self.returncode = returncode
        self.tail = tail


def _disable_accelerators():
    """Persist flags so transcription (mlx) and diarization (MPS) avoid Metal on
    this machine from now on. The data dir is never touched."""
    from app.config import MLX_DISABLED_FLAG, MPS_DISABLED_FLAG
    for flag in (MLX_DISABLED_FLAG, MPS_DISABLED_FLAG):
        try:
            if not flag.exists():
                flag.write_text("auto-disabled after Metal crash\n")
        except Exception:
            log.warning("Could not write %s", flag)


def _run_heavy_stage(recording_id: int, wav_path: str, progress_cb,
                     duration: float, cpu_only: bool, no_diarize: bool = False):
    """Run transcription + diarization in app.core.heavy_worker as a subprocess.

    Streams 'PROGRESS <frac>' lines back to progress_cb and returns
    (transcript_result, diarization_segments). Raises _AcceleratorCrash if the
    child is killed by a signal; re-raises a RuntimeError with the captured tail
    for any other non-zero exit (e.g. a normal Python error like a bad HF token).

    A watchdog thread kills the child if it runs far longer than the audio could
    plausibly need, so a wedged model download or a deadlocked native lib can
    never hang the app forever."""
    import os
    import sys
    import json
    import tempfile
    import threading
    import subprocess
    from app.config import INSTALL_DIR

    out_json = Path(tempfile.gettempdir()) / f"vozmeet_heavy_{recording_id}.json"
    if out_json.exists():
        out_json.unlink()

    env = dict(os.environ)
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["PYTHONPATH"] = str(INSTALL_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    if cpu_only:
        env["VOZMEET_FORCE_CPU"] = "1"

    cmd = [sys.executable, "-m", "app.core.heavy_worker", str(wav_path), str(out_json)]
    if no_diarize:
        cmd.append("--no-diarize")

    proc = subprocess.Popen(
        cmd,
        cwd=str(INSTALL_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )

    # Watchdog: generous upper bound. CPU transcription+diarization of a 1h file
    # can take ~1h; allow 8x audio duration plus a 30-min floor (covers the
    # first-run model download). On timeout the child is killed, which EOFs
    # stdout below and surfaces as a normal failure (then the caller's fallbacks
    # run) rather than an infinite hang.
    timed_out = {"flag": False}
    limit = max(1800.0, float(duration or 0) * 8.0)

    def _kill_after_limit():
        try:
            proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out["flag"] = True
            try:
                proc.kill()
            except Exception:
                pass

    wd = threading.Thread(target=_kill_after_limit, daemon=True)
    wd.start()

    tail: list[str] = []
    for line in proc.stdout:                       # live, line-buffered
        line = line.rstrip("\n")
        if line.startswith("PROGRESS "):
            try:
                progress_cb(float(line.split()[1]))
            except Exception:
                pass
        elif line:
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)
    rc = proc.wait()
    tail_text = "\n".join(tail[-30:])

    if timed_out["flag"]:
        out_json.unlink(missing_ok=True)
        raise RuntimeError(
            "El procesamiento excedió el tiempo máximo y se detuvo.\n" + tail_text)

    if rc == 0 and out_json.exists():
        try:
            with open(out_json) as f:
                data = json.load(f)
        except Exception as e:
            out_json.unlink(missing_ok=True)
            raise RuntimeError("Resultado del procesamiento ilegible: %s\n%s"
                               % (e, tail_text))
        out_json.unlink(missing_ok=True)
        return data["transcript"], data["diarization"]

    out_json.unlink(missing_ok=True)
    # Negative rc = killed by signal; >128 = shell-style signal exit (128+sig).
    if rc < 0 or rc > 128:
        raise _AcceleratorCrash(rc, tail_text)
    if rc == 0:
        # Exited cleanly but produced no output file — treat as a real failure
        # with a clear message instead of silently returning nothing.
        raise RuntimeError("El procesamiento terminó sin resultado.\n" + tail_text)
    raise RuntimeError("Fallo en transcripción/diarización:\n" + tail_text)


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"
