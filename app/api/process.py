import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.database.db import get_db
from app.core.pipeline import run_pipeline, register_progress_callback, get_pipeline_result, get_pipeline_error

router = APIRouter()

_sse_queues: dict[int, asyncio.Queue] = {}

# Models can take several minutes to load on first run
_SSE_TIMEOUT = 600.0      # 10 minutes max total wait
_HEARTBEAT_INTERVAL = 15.0  # send keepalive every 15s so connection stays open


@router.post("/process/{recording_id}")
async def start_processing(recording_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, original_path, status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Grabación no encontrada.")

    if row["status"] == "processing":
        raise HTTPException(status_code=409, detail="Ya está siendo procesada.")

    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues[recording_id] = queue

    loop = asyncio.get_event_loop()

    def progress_callback(data: dict):
        loop.call_soon_threadsafe(queue.put_nowait, data)

    register_progress_callback(recording_id, progress_callback)
    run_pipeline(recording_id, row["original_path"])

    return {"recording_id": recording_id, "status": "processing"}


@router.get("/process/{recording_id}/progress")
async def progress_stream(recording_id: int):
    async def event_generator():
        queue = _sse_queues.get(recording_id)
        if not queue:
            queue = asyncio.Queue()
            _sse_queues[recording_id] = queue

        deadline = asyncio.get_event_loop().time() + _SSE_TIMEOUT

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                yield f"data: {json.dumps({'percent': -1, 'stage': 'error', 'detail': 'Tiempo máximo de procesamiento agotado (10 min)'})}\n\n"
                break

            try:
                data = await asyncio.wait_for(
                    queue.get(),
                    timeout=min(_HEARTBEAT_INTERVAL, remaining)
                )
                yield f"data: {json.dumps(data)}\n\n"

                if data.get("percent") == 100 or data.get("percent") == -1:
                    break

            except asyncio.TimeoutError:
                # Send keepalive comment so the connection stays open
                # The frontend ignores lines starting with ':'
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
