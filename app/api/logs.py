from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

LOG_PATH = Path(__file__).parent.parent.parent / "data" / "vozmeet.log"


@router.get("/logs")
def get_logs(lines: int = 100):
    if not LOG_PATH.exists():
        return PlainTextResponse("(sin logs todavía)")
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-lines:])
    return PlainTextResponse(tail)

# Note: GET /recordings/{id}/error lives in recordings.py (the canonical owner).
# A duplicate previously here was shadowed by router registration order.
