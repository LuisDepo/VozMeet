import os
from pathlib import Path
from dotenv import load_dotenv

# ── Runtime environment hardening (must run before torch / mlx / ffmpeg use) ──
# 1. OpenMP duplicate-runtime guard: torch + ctranslate2 each bundle their own
#    OpenMP runtime; two in one process => OpenMP abort() (SIGABRT) and the app
#    dies silently. This downgrades that fatal abort to a harmless warning.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 2. PATH: a macOS .app bundle does NOT inherit the shell PATH. Third-party
#    libraries that call the bare `ffmpeg` binary via subprocess (e.g.
#    mlx_whisper.load_audio) fail with FileNotFoundError unless ffmpeg is on
#    PATH. Prepend the installer's bundled bin/ plus the usual Homebrew/Intel
#    locations so every subprocess can find ffmpeg/ffprobe.
_BUNDLED_BIN = Path(__file__).resolve().parent.parent / "bin"
_PATH_DIRS = [str(_BUNDLED_BIN), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
_cur_path = os.environ.get("PATH", "")
_cur_parts = _cur_path.split(os.pathsep) if _cur_path else []
os.environ["PATH"] = os.pathsep.join(
    [p for p in _PATH_DIRS if p not in _cur_parts] + _cur_parts
)

# Always load .env from ~/VozMeet/.env so it works both in dev and as a bundled .app
_env_path = Path.home() / "VozMeet" / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

PROJECT_DIR = Path.home() / "VozMeet"

# Install dir = where the app code lives (…/VozMeet-…-EOB7u/). The accelerator
# disable-flags and bundled bin/ live here, separate from the user data dir.
INSTALL_DIR = Path(__file__).resolve().parent.parent
MLX_DISABLED_FLAG = INSTALL_DIR / ".mlx_disabled"
MPS_DISABLED_FLAG = INSTALL_DIR / ".mps_disabled"


def mlx_disabled() -> bool:
    """True if mlx (Apple Neural Engine) must be skipped on this machine.

    Set either by a per-process override (the CPU-only fallback retry) or by a
    persistent flag written when mlx's Metal init/compute crashed here."""
    if os.environ.get("VOZMEET_FORCE_CPU") == "1":
        return True
    return MLX_DISABLED_FLAG.exists()


def mps_disabled() -> bool:
    """True if torch MPS (Metal) must be skipped for diarization on this machine."""
    if os.environ.get("VOZMEET_FORCE_CPU") == "1":
        return True
    return MPS_DISABLED_FLAG.exists()


DATA_DIR = PROJECT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
VOICE_SAMPLES_DIR = DATA_DIR / "voice_samples"
DB_PATH = DATA_DIR / "vozmeet.db"

WHISPER_MODEL = "medium"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_DEVICE = "auto"
MLX_WHISPER_REPO = "mlx-community/whisper-medium-mlx"

PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"
HF_TOKEN = os.getenv("HF_TOKEN", "")

SPEECHBRAIN_MODEL = "speechbrain/spkrec-ecapa-voxceleb"

SIMILARITY_THRESHOLD = 0.75
AUTO_CONFIRM_THRESHOLD = 0.85

MAX_FILE_SIZE_MB = 500
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
SAMPLE_DURATION_SECONDS = 8
MIN_AUDIO_DURATION_SECONDS = 10
MAX_SPEAKERS_WARNING = 10

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav"}

for d in [UPLOADS_DIR, PROCESSED_DIR, TRANSCRIPTS_DIR, VOICE_SAMPLES_DIR]:
    d.mkdir(parents=True, exist_ok=True)
