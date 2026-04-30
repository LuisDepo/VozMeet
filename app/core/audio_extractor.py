import subprocess
import shutil
import os
from pathlib import Path
from app.config import PROCESSED_DIR

# Homebrew installs ffmpeg here depending on chip; .app bundles don't inherit PATH
_EXTRA_PATHS = [
    "/opt/homebrew/bin",   # Apple Silicon
    "/usr/local/bin",      # Intel
    "/usr/bin",
]


def _find_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for p in _EXTRA_PATHS:
        candidate = os.path.join(p, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        f"'{name}' no encontrado. Instálalo con: brew install ffmpeg\n"
        f"Buscado en: {os.environ.get('PATH', '')} + {_EXTRA_PATHS}"
    )


def extract_audio(input_path: str | Path, output_name: str | None = None) -> dict:
    ffmpeg = _find_bin("ffmpeg")
    input_path = Path(input_path)
    if output_name is None:
        output_name = input_path.stem + ".wav"
    output_path = PROCESSED_DIR / output_name

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-ac", "1",
        "-ar", "16000",
        "-af", "loudnorm",
        "-vn",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Error al extraer audio con ffmpeg:\n{result.stderr[-2000:]}"
        )

    duration = _get_duration(output_path)
    return {"output_path": str(output_path), "duration": duration, "sample_rate": 16000}


def _get_duration(wav_path: Path) -> float:
    try:
        ffprobe = _find_bin("ffprobe")
    except RuntimeError:
        return 0.0

    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    return 0.0
