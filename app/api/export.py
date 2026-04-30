import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from app.database.db import get_db
from app.config import TRANSCRIPTS_DIR

router = APIRouter()


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_duration_hms(seconds: float) -> str:
    return _fmt_ts(seconds)


def _build_transcript_data(recording_id: int) -> dict:
    with get_db() as conn:
        rec = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")

        segs = conn.execute(
            "SELECT s.start_time, s.end_time, s.text, sp.display_name, s.raw_speaker_label "
            "FROM segments s "
            "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
            "WHERE s.recording_id = ? ORDER BY s.start_time",
            (recording_id,),
        ).fetchall()

        participants_rows = conn.execute(
            "SELECT DISTINCT sp.display_name FROM segments s "
            "JOIN speakers sp ON s.speaker_id = sp.id "
            "WHERE s.recording_id = ?",
            (recording_id,),
        ).fetchall()

    participants = [r["display_name"] for r in participants_rows if r["display_name"]]
    segments = [
        {
            "start": seg["start_time"],
            "end": seg["end_time"],
            "text": seg["text"],
            "speaker": seg["display_name"] or seg["raw_speaker_label"] or "Desconocido",
        }
        for seg in segs
    ]

    speaker_times: dict[str, float] = {}
    for seg in segments:
        name = seg["speaker"]
        speaker_times[name] = speaker_times.get(name, 0.0) + (seg["end"] - seg["start"])

    total_duration = rec["duration_seconds"] or sum(s["end"] - s["start"] for s in segments)

    return {
        "filename": rec["filename"],
        "created_at": rec["created_at"],
        "completed_at": rec["completed_at"],
        "duration": total_duration,
        "language": rec["language_detected"] or "Desconocido",
        "participants": participants,
        "segments": segments,
        "speaker_times": speaker_times,
        "segment_count": len(segments),
    }


def _to_txt(data: dict) -> str:
    lines = [
        "TRANSCRIPCIÓN DE REUNIÓN",
        "========================",
        f"Título: {data['filename']}",
        f"Fecha: {data['completed_at'] or data['created_at'] or 'Desconocida'}",
        f"Duración: {_fmt_duration_hms(data['duration'])}",
        f"Participantes: {', '.join(data['participants']) or 'No identificados'}",
        f"Idioma: {data['language']}",
        "Procesado con: VozMeet",
        "========================",
        "",
    ]
    for seg in data["segments"]:
        lines.append(f"[{_fmt_ts(seg['start'])}] {seg['speaker']}")
        lines.append(seg["text"])
        lines.append("")

    total = data["duration"]
    lines += [
        "========================",
        "FIN DE TRANSCRIPCIÓN",
        f"Total de intervenciones: {data['segment_count']}",
        "Tiempo hablado por persona:",
    ]
    for name, t in sorted(data["speaker_times"].items(), key=lambda x: -x[1]):
        pct = round(t / total * 100, 1) if total else 0
        m, s = divmod(int(t), 60)
        lines.append(f"  {name}: {m} min {s} seg ({pct}%)")
    lines.append("========================")

    return "\n".join(lines)


def _to_md(data: dict) -> str:
    lines = [
        f"# Transcripción: {data['filename']}",
        "",
        f"**Fecha:** {data['completed_at'] or data['created_at'] or 'Desconocida'}  ",
        f"**Duración:** {_fmt_duration_hms(data['duration'])}  ",
        f"**Participantes:** {', '.join(data['participants']) or 'No identificados'}  ",
        f"**Idioma:** {data['language']}  ",
        f"**Procesado con:** VozMeet",
        "",
        "---",
        "",
    ]
    for seg in data["segments"]:
        lines.append(f"**[{_fmt_ts(seg['start'])}] {seg['speaker']}**")
        lines.append(f"> {seg['text']}")
        lines.append("")

    lines += ["---", "", "## Resumen de participación", ""]
    total = data["duration"]
    for name, t in sorted(data["speaker_times"].items(), key=lambda x: -x[1]):
        pct = round(t / total * 100, 1) if total else 0
        m, s = divmod(int(t), 60)
        lines.append(f"- **{name}**: {m} min {s} seg ({pct}%)")

    return "\n".join(lines)


@router.get("/export/{recording_id}")
def export_transcript(
    recording_id: int,
    format: str = Query("txt", regex="^(txt|md|json)$"),
):
    data = _build_transcript_data(recording_id)
    stem = Path(data["filename"]).stem[:40]

    if format == "json":
        output = json.dumps(data, ensure_ascii=False, indent=2)
        filename = f"{stem}_vozmeet.json"
        content_type = "application/json"
    elif format == "md":
        output = _to_md(data)
        filename = f"{stem}_vozmeet.md"
        content_type = "text/markdown"
    else:
        output = _to_txt(data)
        filename = f"{stem}_vozmeet.txt"
        content_type = "text/plain"

    out_path = TRANSCRIPTS_DIR / filename
    out_path.write_text(output, encoding="utf-8")

    return FileResponse(
        path=str(out_path),
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
