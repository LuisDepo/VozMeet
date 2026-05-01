import numpy as np
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database.db import get_db
from app.database.voice_store import save_speaker, update_speaker_embedding, find_matching_speaker
from app.core.pipeline import get_pipeline_result
from app.logger import get_logger

router = APIRouter()
log = get_logger("recordings")


class IdentifyPayload(BaseModel):
    assignments: list[dict]


@router.get("/recordings")
def list_recordings():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename, duration_seconds, language_detected, speaker_count, "
            "status, created_at, completed_at, total_processing_seconds, last_started_at "
            "FROM recordings ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/recordings/{recording_id}")
def get_recording(recording_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Grabación no encontrada.")
    return dict(row)


@router.get("/recordings/{recording_id}/speakers")
def get_recording_speakers(recording_id: int):
    pipeline_result = get_pipeline_result(recording_id)

    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

        rs_rows = conn.execute(
            "SELECT rs.raw_label, rs.speaker_id, rs.match_confidence, rs.confirmed_by_user, "
            "s.display_name "
            "FROM recording_speakers rs "
            "LEFT JOIN speakers s ON rs.speaker_id = s.id "
            "WHERE rs.recording_id = ?",
            (recording_id,),
        ).fetchall()

    total_duration = rec["duration_seconds"] or 1.0
    speakers_out = []

    for row in rs_rows:
        raw_label = row["raw_label"]
        talk_time = 0.0

        if pipeline_result:
            st = pipeline_result.get("speaker_time", {})
            talk_time = st.get(raw_label, 0.0)
        else:
            with get_db() as conn:
                segs = conn.execute(
                    "SELECT start_time, end_time FROM segments "
                    "WHERE recording_id = ? AND raw_speaker_label = ?",
                    (recording_id, raw_label),
                ).fetchall()
            talk_time = sum(s["end_time"] - s["start_time"] for s in segs)

        sample_path = None
        if pipeline_result:
            sugg = pipeline_result.get("suggestions", {}).get(raw_label, {})
            sample_path = sugg.get("sample_path")

        if not sample_path:
            from app.config import VOICE_SAMPLES_DIR
            candidate = VOICE_SAMPLES_DIR / f"rec{recording_id}_{raw_label}.wav"
            if candidate.exists():
                sample_path = str(candidate)

        speakers_out.append({
            "raw_label": raw_label,
            "speaker_id": row["speaker_id"],
            "display_name": row["display_name"],
            "match_confidence": row["match_confidence"],
            "confirmed_by_user": bool(row["confirmed_by_user"]),
            "talk_time": round(talk_time, 1),
            "talk_percent": round(talk_time / total_duration * 100, 1),
            "sample_filename": f"rec{recording_id}_{raw_label}.wav" if sample_path else None,
        })

    speakers_out.sort(key=lambda x: x["talk_time"], reverse=True)
    return speakers_out


@router.post("/recordings/{recording_id}/identify")
def identify_speakers(recording_id: int, payload: IdentifyPayload):
    try:
        return _identify_speakers_impl(recording_id, payload)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[%d] Error in identify endpoint", recording_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


def _identify_speakers_impl(recording_id: int, payload: IdentifyPayload):
    pipeline_result = get_pipeline_result(recording_id)

    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

    for assignment in payload.assignments:
        raw_label = assignment.get("raw_label")
        display_name = (assignment.get("display_name") or "").strip()
        speaker_id = assignment.get("speaker_id")

        if not raw_label:
            continue

        # No name provided — mark as confirmed but leave speaker_id NULL
        if not display_name:
            with get_db() as conn:
                conn.execute(
                    "UPDATE recording_speakers SET confirmed_by_user=1 "
                    "WHERE recording_id=? AND raw_label=?",
                    (recording_id, raw_label),
                )
            continue

        embedding_list = None
        if pipeline_result:
            sugg = pipeline_result.get("suggestions", {}).get(raw_label, {})
            emb_list = sugg.get("embedding")
            if emb_list:
                embedding_list = np.array(emb_list, dtype=np.float32)

        if speaker_id:
            if embedding_list is not None:
                update_speaker_embedding(speaker_id, embedding_list)
        else:
            if embedding_list is not None:
                matched, score = find_matching_speaker(embedding_list)
                from app.config import SIMILARITY_THRESHOLD
                if matched and score >= SIMILARITY_THRESHOLD:
                    speaker_id = matched.id
                    update_speaker_embedding(speaker_id, embedding_list)
                else:
                    name_key = display_name.lower().replace(" ", "_")
                    sample_path = None
                    if pipeline_result:
                        sugg = pipeline_result.get("suggestions", {}).get(raw_label, {})
                        sample_path = sugg.get("sample_path")
                    speaker_id = save_speaker(name_key, display_name, embedding_list, sample_path)
            else:
                from app.database.voice_store import get_all_speakers
                existing = next(
                    (s for s in get_all_speakers() if s.display_name.lower() == display_name.lower()),
                    None,
                )
                if existing:
                    speaker_id = existing.id
                else:
                    dummy_emb = np.zeros(192, dtype=np.float32)
                    name_key = display_name.lower().replace(" ", "_")
                    speaker_id = save_speaker(name_key, display_name, dummy_emb)

        with get_db() as conn:
            conn.execute(
                "UPDATE recording_speakers SET speaker_id=?, confirmed_by_user=1 "
                "WHERE recording_id=? AND raw_label=?",
                (speaker_id, recording_id, raw_label),
            )
            conn.execute(
                "UPDATE segments SET speaker_id=? "
                "WHERE recording_id=? AND raw_speaker_label=?",
                (speaker_id, recording_id, raw_label),
            )

    with get_db() as conn:
        conn.execute(
            "UPDATE recordings SET status='done', completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (recording_id,),
        )

    return {"ok": True, "recording_id": recording_id}


@router.post("/recordings/{recording_id}/resume")
def resume_recording(recording_id: int):
    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id=?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

        # Already at identify stage — pipeline is done, just navigate there
        if rec["status"] == "identifying":
            return {"ok": True, "recording_id": recording_id, "status": "identifying"}

        # Reset segments and speakers for a fresh pipeline run
        conn.execute("DELETE FROM segments WHERE recording_id=?", (recording_id,))
        conn.execute("DELETE FROM recording_speakers WHERE recording_id=?", (recording_id,))

        # Keep the WAV file if it's already on disk (skips audio extraction on resume)
        processed_path = rec["processed_path"]
        wav_exists = processed_path and Path(processed_path).exists()

        if wav_exists:
            conn.execute(
                "UPDATE recordings SET status='uploaded', error_message=NULL, "
                "pipeline_stage=NULL WHERE id=?",
                (recording_id,),
            )
        else:
            conn.execute(
                "UPDATE recordings SET status='uploaded', error_message=NULL, "
                "processed_path=NULL, duration_seconds=NULL, pipeline_stage=NULL WHERE id=?",
                (recording_id,),
            )

    return {"ok": True, "recording_id": recording_id, "status": "uploaded"}


@router.get("/recordings/{recording_id}/transcript")
def get_transcript(recording_id: int):
    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id=?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

        segs = conn.execute(
            "SELECT s.start_time, s.end_time, s.text, s.confidence, "
            "sp.display_name, s.raw_speaker_label "
            "FROM segments s "
            "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
            "WHERE s.recording_id=? ORDER BY s.start_time",
            (recording_id,),
        ).fetchall()

        participants_rows = conn.execute(
            "SELECT DISTINCT sp.display_name FROM segments s "
            "JOIN speakers sp ON s.speaker_id = sp.id "
            "WHERE s.recording_id=?",
            (recording_id,),
        ).fetchall()

    participants = [r["display_name"] for r in participants_rows if r["display_name"]]

    return {
        "recording": dict(rec),
        "participants": participants,
        "segments": [
            {
                "start": seg["start_time"],
                "end": seg["end_time"],
                "text": seg["text"],
                "speaker": seg["display_name"] or seg["raw_speaker_label"] or "Sin identificar",
                "confidence": seg["confidence"],
            }
            for seg in segs
        ],
    }


@router.get("/recordings/{recording_id}/error")
def get_recording_error(recording_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT error_message FROM recordings WHERE id=?", (recording_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Grabación no encontrada.")
    return {"error": row["error_message"] or "Sin detalles de error."}


@router.delete("/recordings/{recording_id}")
def delete_recording(recording_id: int):
    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id=?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")
        conn.execute("DELETE FROM segments WHERE recording_id=?", (recording_id,))
        conn.execute("DELETE FROM recording_speakers WHERE recording_id=?", (recording_id,))
        conn.execute("DELETE FROM recordings WHERE id=?", (recording_id,))
    return {"ok": True}
