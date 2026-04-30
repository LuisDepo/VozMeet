from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database.voice_store import get_all_speakers, get_speaker_by_id, delete_speaker
from app.database.db import get_db

router = APIRouter()


class SpeakerUpdate(BaseModel):
    display_name: str


@router.get("/speakers")
def list_speakers():
    speakers = get_all_speakers()
    result = []
    for s in speakers:
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(DISTINCT recording_id) as cnt FROM recording_speakers WHERE speaker_id = ?",
                (s.id,),
            ).fetchone()["cnt"]
        result.append({
            "id": s.id,
            "name": s.name,
            "display_name": s.display_name,
            "embedding_count": s.embedding_count,
            "sample_audio_path": s.sample_audio_path,
            "created_at": s.created_at,
            "recording_count": count,
        })
    return result


@router.get("/speakers/{speaker_id}")
def get_speaker(speaker_id: int):
    s = get_speaker_by_id(speaker_id)
    if not s:
        raise HTTPException(status_code=404, detail="Perfil de voz no encontrado.")
    return {
        "id": s.id,
        "name": s.name,
        "display_name": s.display_name,
        "embedding_count": s.embedding_count,
        "sample_audio_path": s.sample_audio_path,
        "created_at": s.created_at,
    }


@router.put("/speakers/{speaker_id}")
def update_speaker(speaker_id: int, body: SpeakerUpdate):
    s = get_speaker_by_id(speaker_id)
    if not s:
        raise HTTPException(status_code=404, detail="Perfil de voz no encontrado.")
    with get_db() as conn:
        conn.execute(
            "UPDATE speakers SET display_name = ?, name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (body.display_name, body.display_name.lower().replace(" ", "_"), speaker_id),
        )
        conn.execute(
            "UPDATE segments SET raw_speaker_label = raw_speaker_label WHERE speaker_id = ?",
            (speaker_id,),
        )
    return {"ok": True, "display_name": body.display_name}


@router.delete("/speakers/{speaker_id}")
def remove_speaker(speaker_id: int):
    s = get_speaker_by_id(speaker_id)
    if not s:
        raise HTTPException(status_code=404, detail="Perfil de voz no encontrado.")
    delete_speaker(speaker_id)
    return {"ok": True}
