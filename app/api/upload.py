import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import UPLOADS_DIR, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS
from app.database.db import get_db

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {ext}. Usa MP3, MP4, M4A o WAV.",
        )

    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / unique_name

    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Archivo demasiado grande. Máximo {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
                )
            f.write(chunk)

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO recordings (filename, original_path, status) VALUES (?, ?, 'uploaded')",
            (file.filename, str(dest)),
        )
        recording_id = cur.lastrowid

    return {
        "recording_id": recording_id,
        "filename": file.filename,
        "size_bytes": size,
        "status": "uploaded",
    }
