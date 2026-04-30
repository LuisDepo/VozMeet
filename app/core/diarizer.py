from pathlib import Path
from app.config import PYANNOTE_MODEL, HF_TOKEN

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        if not HF_TOKEN:
            raise RuntimeError(
                "Token de HuggingFace no configurado. "
                "Agrega HF_TOKEN=tu_token al archivo .env"
            )
        try:
            from pyannote.audio import Pipeline
            _pipeline = Pipeline.from_pretrained(
                PYANNOTE_MODEL,
                token=HF_TOKEN,
            )
        except Exception as e:
            msg = str(e)
            if "401" in msg or "credentials" in msg.lower() or "token" in msg.lower():
                raise RuntimeError(
                    "Token de HuggingFace inválido o expirado. "
                    "Obtén uno nuevo en: https://huggingface.co/settings/tokens"
                ) from e
            if "terms" in msg.lower() or "403" in msg or "gated" in msg.lower():
                raise RuntimeError(
                    "Debes aceptar los términos de uso de los modelos pyannote:\n"
                    "  1. https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                    "  2. https://huggingface.co/pyannote/segmentation-3.0\n"
                    "Ingresa con tu cuenta de HuggingFace y acepta en cada enlace."
                ) from e
            raise
    return _pipeline


def diarize(audio_path: str | Path) -> list[dict]:
    pipe = _get_pipeline()
    audio_path = str(audio_path)

    result = pipe(audio_path)

    # pyannote >= 3.3 wraps output in DiarizeOutput; older versions return Annotation directly
    annotation = getattr(result, 'diarization', result)

    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "speaker": speaker,
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
        })

    segments.sort(key=lambda x: x["start"])
    return segments
