from typing import Optional


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def merge(
    transcript_segments: list[dict],
    diarization_segments: list[dict],
) -> list[dict]:
    merged = []

    for t_seg in transcript_segments:
        t_start = t_seg["start"]
        t_end = t_seg["end"]
        text = t_seg.get("text", "").strip()

        if not text:
            continue

        best_speaker: Optional[str] = None
        best_overlap = 0.0
        total_duration = t_end - t_start

        for d_seg in diarization_segments:
            ov = _overlap(t_start, t_end, d_seg["start"], d_seg["end"])
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = d_seg["speaker"]

        # A transcript segment falling in a gap between diarization turns has no
        # overlap → assign the nearest turn by midpoint distance instead of
        # leaving it "Desconocido", so every line gets a speaker.
        if best_speaker is None and diarization_segments:
            t_mid = (t_start + t_end) / 2.0
            best_speaker = min(
                diarization_segments,
                key=lambda d: abs(((d["start"] + d["end"]) / 2.0) - t_mid),
            )["speaker"]

        confidence = (best_overlap / total_duration) if total_duration > 0 else 0.0

        merged.append({
            "start": t_start,
            "end": t_end,
            "text": text,
            "speaker_label": best_speaker,
            "confidence": round(confidence, 3),
        })

    return merged
