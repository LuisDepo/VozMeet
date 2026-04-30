import subprocess
import shutil
from pathlib import Path
from app.config import PROCESSED_DIR


def _check_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg no está instalado. Instálalo con: brew install ffmpeg"
        )


def extract_audio(input_path: str | Path, output_name: str | None = None) -> dict:
    _check_ffmpeg()
    input_path = Path(input_path)
    if output_name is None:
        output_name = input_path.stem + ".wav"
    output_path = PROCESSED_DIR / output_name

    cmd = [
        "ffmpeg", "-y",
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
    cmd = [
        "ffprobe", "-v", "quiet",
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
