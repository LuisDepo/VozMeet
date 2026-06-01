import subprocess
import shutil
import os
import wave
from pathlib import Path
from app.config import PROCESSED_DIR

# ffmpeg lookup: bundled binary first (installer drops it in INSTALL_DIR/bin),
# then Homebrew dirs. .app bundles don't inherit the shell PATH.
_BUNDLED_BIN = str(Path(__file__).resolve().parents[2] / "bin")
_EXTRA_PATHS = [
    _BUNDLED_BIN,          # ffmpeg instalado por el instalador de VozMeet
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
    # The extracted file is always 16 kHz mono WAV — read duration with the
    # stdlib `wave` module so we don't depend on ffprobe being installed.
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate:
                return frames / float(rate)
    except Exception:
        pass

    # Fallback: ffprobe if available (handles odd containers)
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
