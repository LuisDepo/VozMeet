from pathlib import Path
from typing import Optional
import numpy as np
from app.config import SPEECHBRAIN_MODEL, VOICE_SAMPLES_DIR, SAMPLE_DURATION_SECONDS

_classifier = None


def _get_classifier():
    global _classifier
    if _classifier is None:
        from speechbrain.pretrained import EncoderClassifier
        _classifier = EncoderClassifier.from_hparams(
            source=SPEECHBRAIN_MODEL,
            savedir=str(Path.home() / ".cache" / "speechbrain" / "ecapa-tdnn"),
            run_opts={"device": "cpu"},
        )
    return _classifier


def get_embedding(audio_path: str | Path, start: float = 0.0, end: Optional[float] = None) -> np.ndarray:
    import torchaudio
    import torch

    audio_path = str(audio_path)
    waveform, sr = torchaudio.load(audio_path)

    start_frame = int(start * sr)
    end_frame = int(end * sr) if end is not None else waveform.shape[1]
    end_frame = min(end_frame, waveform.shape[1])
    segment = waveform[:, start_frame:end_frame]

    if sr != 16000:
        resampler = torchaudio.transforms.Resample(sr, 16000)
        segment = resampler(segment)

    if segment.shape[0] > 1:
        segment = segment.mean(dim=0, keepdim=True)

    classifier = _get_classifier()
    with torch.no_grad():
        embedding = classifier.encode_batch(segment)

    emb = embedding.squeeze().numpy()
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb.astype(np.float32)


def extract_sample(
    audio_path: str | Path,
    start: float,
    end: float,
    output_name: str,
) -> str:
    import subprocess
    duration = min(end - start, SAMPLE_DURATION_SECONDS)
    output_path = VOICE_SAMPLES_DIR / output_name
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-ss", str(start),
        "-t", str(duration),
        "-ac", "1",
        "-ar", "16000",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return str(output_path)


def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    a = emb1 / (np.linalg.norm(emb1) + 1e-8)
    b = emb2 / (np.linalg.norm(emb2) + 1e-8)
    return float(np.dot(a, b))


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack(embeddings, axis=0)
    avg = np.mean(stacked, axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm).astype(np.float32) if norm > 0 else avg.astype(np.float32)
