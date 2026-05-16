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
        response = generate(model, tokenizer, prompt=text, max_tokens=1500, verbose=False)
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


def _build_prompt(transcript: str, language: str) -> str:
    if language == "es" or language.startswith("es"):
        return (
            "Eres un asistente experto en análisis de reuniones. "
            "Analiza la siguiente transcripción y genera un resumen estructurado en español con estas secciones:\n\n"
            "1. **Temas tratados**: Lista los principales temas discutidos\n"
            "2. **Decisiones y votaciones**: Cualquier decisión tomada o resultado de votaciones\n"
            "3. **Temas pendientes**: Asuntos que quedaron sin resolver o para próximas reuniones\n"
            "4. **Compromisos y fechas**: Tareas asignadas con responsables y fechas si se mencionan\n\n"
            "Transcripción:\n"
            f"{transcript[:6000]}\n\n"
            "Genera el resumen de forma concisa y clara."
        )
    else:
        return (
            "You are an expert meeting analyst. "
            "Analyze the following transcript and generate a structured summary with these sections:\n\n"
            "1. **Topics discussed**: List the main topics covered\n"
            "2. **Decisions and votes**: Any decisions made or voting outcomes\n"
            "3. **Pending items**: Unresolved issues or items for future meetings\n"
            "4. **Commitments and dates**: Assigned tasks with owners and dates if mentioned\n\n"
            "Transcript:\n"
            f"{transcript[:6000]}\n\n"
            "Generate the summary concisely and clearly."
        )
