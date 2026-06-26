import io
from typing import Optional
import numpy as np
from app.database.db import get_db
from app.database.models import Speaker


def _serialize(embedding: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, embedding.astype(np.float32))
    return buf.getvalue()


def _deserialize(blob: bytes) -> np.ndarray:
    buf = io.BytesIO(blob)
    return np.load(buf)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a).ravel()
    b = np.asarray(b).ravel()
    # Different embedding dimensions (e.g. a stored zero-dummy or a model change)
    # must not raise inside the identify loop — treat as "no match".
    if a.shape != b.shape or a.size == 0:
        return 0.0
    a = a / (np.linalg.norm(a) + 1e-8)
    b = b / (np.linalg.norm(b) + 1e-8)
    return float(np.dot(a, b))


def find_matching_speaker(embedding: np.ndarray) -> tuple[Optional[Speaker], float]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, display_name, embedding, embedding_count, "
            "sample_audio_path, created_at, updated_at, language_hint FROM speakers"
        ).fetchall()

    best_speaker: Optional[Speaker] = None
    best_score = 0.0

    for row in rows:
        stored = _deserialize(row["embedding"])
        score = _cosine_similarity(embedding, stored)
        if score > best_score:
            best_score = score
            best_speaker = Speaker(
                id=row["id"],
                name=row["name"],
                display_name=row["display_name"],
                embedding=row["embedding"],
                embedding_count=row["embedding_count"],
                sample_audio_path=row["sample_audio_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                language_hint=row["language_hint"],
            )

    from app.config import SIMILARITY_THRESHOLD
    if best_score < SIMILARITY_THRESHOLD:
        return None, best_score
    return best_speaker, best_score


def save_speaker(
    name: str,
    display_name: str,
    embedding: np.ndarray,
    sample_path: Optional[str] = None,
) -> int:
    blob = _serialize(embedding)
    with get_db() as conn:
        # INSERT OR IGNORE so duplicate names never raise UNIQUE constraint errors.
        # If the name already exists the INSERT is skipped and we return the existing id.
        conn.execute(
            "INSERT OR IGNORE INTO speakers (name, display_name, embedding, sample_audio_path) "
            "VALUES (?, ?, ?, ?)",
            (name, display_name, blob, sample_path),
        )
        row = conn.execute(
            "SELECT id FROM speakers WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]


def update_speaker_embedding(speaker_id: int, new_embedding: np.ndarray):
    with get_db() as conn:
        row = conn.execute(
            "SELECT embedding, embedding_count FROM speakers WHERE id = ?",
            (speaker_id,),
        ).fetchone()
        if not row:
            return
        old = np.asarray(_deserialize(row["embedding"])).ravel()
        new_v = np.asarray(new_embedding).ravel()
        count = row["embedding_count"] or 0
        # If the stored embedding is a placeholder (all-zeros, empty, count 0, or
        # a different dimension), replace it outright instead of averaging — that
        # would otherwise permanently bias the real voiceprint toward zero.
        if (count <= 0 or old.size != new_v.size
                or not np.any(old) or float(np.linalg.norm(old)) < 1e-6):
            averaged = new_v
            new_count = 1
        else:
            averaged = (old * count + new_v) / (count + 1)
            new_count = count + 1
        averaged = averaged / (np.linalg.norm(averaged) + 1e-8)
        conn.execute(
            "UPDATE speakers SET embedding = ?, embedding_count = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (_serialize(averaged), new_count, speaker_id),
        )


def get_all_speakers() -> list[Speaker]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, display_name, embedding, embedding_count, "
            "sample_audio_path, created_at, updated_at, language_hint FROM speakers "
            "ORDER BY display_name"
        ).fetchall()
    return [
        Speaker(
            id=r["id"],
            name=r["name"],
            display_name=r["display_name"],
            embedding=r["embedding"],
            embedding_count=r["embedding_count"],
            sample_audio_path=r["sample_audio_path"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            language_hint=r["language_hint"],
        )
        for r in rows
    ]


def get_speaker_by_id(speaker_id: int) -> Optional[Speaker]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, display_name, embedding, embedding_count, "
            "sample_audio_path, created_at, updated_at, language_hint "
            "FROM speakers WHERE id = ?",
            (speaker_id,),
        ).fetchone()
    if not row:
        return None
    return Speaker(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        embedding=row["embedding"],
        embedding_count=row["embedding_count"],
        sample_audio_path=row["sample_audio_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        language_hint=row["language_hint"],
    )


def delete_speaker(speaker_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM speakers WHERE id = ?", (speaker_id,))


def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    return _cosine_similarity(emb1, emb2)


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack(embeddings, axis=0)
    avg = np.mean(stacked, axis=0)
    return avg / (np.linalg.norm(avg) + 1e-8)
