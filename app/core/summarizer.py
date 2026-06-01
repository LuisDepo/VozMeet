"""
Meeting summary generator using local mlx-lm (Apple Silicon).
Falls back gracefully when mlx-lm is not installed.
"""
from typing import Optional
from app.logger import get_logger

log = get_logger("summarizer")

MLX_LM_REPO = "mlx-community/Qwen2.5-3B-Instruct-4bit"

_model = None
_tokenizer = None
_backend = None


def is_available() -> bool:
    try:
        import mlx_lm  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model():
    global _model, _tokenizer, _backend
    if _model is None:
        try:
            from mlx_lm import load
            log.info("Loading summary model: %s", MLX_LM_REPO)
            _model, _tokenizer = load(MLX_LM_REPO)
            _backend = "mlx_lm"
            log.info("Summary model loaded")
        except ImportError:
            log.warning("mlx-lm not installed — meeting summary unavailable")
            _backend = "unavailable"
    return _model, _tokenizer


def summarize(segments: list[dict], language: str = "es") -> Optional[str]:
    model, tokenizer = _get_model()
    if _backend != "mlx_lm" or model is None:
        return None

    try:
        from mlx_lm import generate

        transcript_text = _format_transcript(segments)
        if not transcript_text.strip():
            return None

        prompt = _build_prompt(transcript_text, language)
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        response = generate(model, tokenizer, prompt=text, max_tokens=2500, verbose=False)
        return response.strip()
    except Exception:
        log.exception("Summary generation failed")
        return None


def _format_transcript(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "Desconocido")
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _smart_truncate(transcript: str, max_chars: int = 12000) -> str:
    """For long meetings, keep the first 2/3 and last 1/3 of the transcript so
    the model sees both the opening context and the closing decisions/actions."""
    if len(transcript) <= max_chars:
        return transcript
    head = int(max_chars * 0.67)
    tail = max_chars - head
    return transcript[:head] + "\n[...]\n" + transcript[-tail:]


def _build_prompt(transcript: str, language: str) -> str:
    body = _smart_truncate(transcript)
    if language == "es" or language.startswith("es"):
        return (
            "Eres un asistente experto en análisis de reuniones. "
            "Analiza la siguiente transcripción y genera un resumen estructurado en español. "
            "Sé específico: usa nombres propios, cifras y fechas que aparezcan en la transcripción.\n\n"
            "Formato requerido (usa exactamente estos encabezados):\n\n"
            "## Puntos clave\n"
            "- Lista de 3-6 puntos clave más importantes de la reunión\n\n"
            "## Temas tratados\n"
            "- Principales temas discutidos con contexto suficiente\n\n"
            "## Decisiones tomadas\n"
            "- Decisiones concretas, acuerdos y resultados de votaciones (si no hubo, indicarlo)\n\n"
            "## Compromisos y próximos pasos\n"
            "- Tareas asignadas, responsables y fechas mencionadas (si no hubo, indicarlo)\n\n"
            "## Temas pendientes\n"
            "- Asuntos sin resolver o para próximas reuniones (si no hubo, indicarlo)\n\n"
            "Transcripción:\n"
            f"{body}\n\n"
            "Genera el resumen ahora:"
        )
    else:
        return (
            "You are an expert meeting analyst. "
            "Analyze the following transcript and generate a structured summary. "
            "Be specific: use names, numbers, and dates from the transcript.\n\n"
            "Required format (use exactly these headings):\n\n"
            "## Key Points\n"
            "- 3-6 most important takeaways from the meeting\n\n"
            "## Topics Discussed\n"
            "- Main topics with enough context\n\n"
            "## Decisions Made\n"
            "- Concrete decisions, agreements, and votes (if none, say so)\n\n"
            "## Commitments and Next Steps\n"
            "- Assigned tasks, owners, and dates mentioned (if none, say so)\n\n"
            "## Pending Items\n"
            "- Unresolved issues for future meetings (if none, say so)\n\n"
            "Transcript:\n"
            f"{body}\n\n"
            "Generate the summary now:"
        )
