from fastapi import APIRouter, HTTPException
from app.database.db import get_db
from app.logger import get_logger

router = APIRouter()
log = get_logger("summary")


@router.get("/summary/{recording_id}")
def get_summary(recording_id: int):
    from app.core.summarizer import summarize, is_available

    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="El módulo mlx-lm no está instalado. Ejecuta: pip install mlx-lm"
        )

    with get_db() as conn:
        rec = conn.execute(
            "SELECT * FROM recordings WHERE id=?", (recording_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

        segs = conn.execute(
            "SELECT s.start_time, s.end_time, s.text, "
            "COALESCE(sp.display_name, s.raw_speaker_label) as speaker "
            "FROM segments s "
            "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
            "WHERE s.recording_id=? ORDER BY s.start_time",
            (recording_id,),
        ).fetchall()

    segments = [
        {
            "start": row["start_time"],
            "end": row["end_time"],
            "text": row["text"] or "",
            "speaker": row["speaker"] or "Desconocido",
        }
        for row in segs
    ]

    language = rec["language_detected"] or "es"
    lang_code = "es" if "spañol" in language else "en"

    log.info("[%d] Generating meeting summary (%d segments)", recording_id, len(segments))
    result = summarize(segments, lang_code)

    if result is None:
        raise HTTPException(status_code=500, detail="No se pudo generar el resumen.")

    return {"recording_id": recording_id, "summary": result}
