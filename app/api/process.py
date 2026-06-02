import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.database.db import get_db
from app.core.pipeline import run_pipeline, register_progress_callback, get_pipeline_result, get_pipeline_error

router = APIRouter()

_sse_queues: dict[int, asyncio.Queue] = {}

_HEARTBEAT_INTERVAL = 20.0  # send keepalive every 20s so connection stays open


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

    loop = asyncio.get_running_loop()

    def progress_callback(data: dict):
        # The pipeline runs in a worker thread; deliver to the asyncio loop
        # safely. Guard against the loop being closed (client gone).
        try:
            loop.call_soon_threadsafe(queue.put_nowait, data)
        except RuntimeError:
            pass

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

        # No absolute deadline — recordings can be 4-5 hours long.
        # Only keepalives prevent the connection from dropping.
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_INTERVAL)
                    yield f"data: {json.dumps(data)}\n\n"
                    if data.get("percent") == 100 or data.get("percent") == -1:
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            # Drop the queue so it doesn't leak for the app's lifetime and so a
            # later reprocess of the same recording starts with a clean queue.
            if _sse_queues.get(recording_id) is queue:
                _sse_queues.pop(recording_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
