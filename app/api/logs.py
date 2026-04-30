from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from app.database.db import get_db

router = APIRouter()

LOG_PATH = Path.home() / "VozMeet" / "data" / "vozmeet.log"


@router.get("/logs")
def get_logs(lines: int = 100):
    if not LOG_PATH.exists():
        return PlainTextResponse("(sin logs todavía)")
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-lines:])
    return PlainTextResponse(tail)


@router.get("/recordings/{recording_id}/error")
def get_recording_error(recording_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT error_message, status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()
    if not row:
        return {"error": None, "status": "not_found"}
    return {"error": row["error_message"], "status": row["status"]}
