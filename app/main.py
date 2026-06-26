from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.database.db import init_db
from app.api import upload, process, speakers, recordings, export, logs, update, summary
from app.config import VOICE_SAMPLES_DIR
from app.database.db import get_db
from app.version import VERSION

APP_VERSION = VERSION
app = FastAPI(title="VozMeet", version=VERSION)

init_db()

app.include_router(upload.router, prefix="/api")
app.include_router(process.router, prefix="/api")
app.include_router(speakers.router, prefix="/api")
app.include_router(recordings.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(update.router, prefix="/api")
app.include_router(summary.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "VozMeet"}


@app.get("/api/version")
def version():
    return {"version": APP_VERSION}


@app.get("/api/audio/sample/{filename}")
def serve_audio_sample(filename: str):
    safe_name = Path(filename).name
    file_path = VOICE_SAMPLES_DIR / safe_name
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"detail": "Muestra no encontrada."})
    return FileResponse(str(file_path), media_type="audio/wav")


@app.get("/api/audio/recording/{recording_id}")
def serve_recording_audio(recording_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT processed_path FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
    if not row or not row["processed_path"]:
        return JSONResponse(status_code=404, content={"detail": "Audio no disponible."})
    file_path = Path(row["processed_path"])
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"detail": "Archivo no encontrado."})
    return FileResponse(str(file_path), media_type="audio/wav")


_static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
