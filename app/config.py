import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path.home() / "VozMeet"

DATA_DIR = PROJECT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
VOICE_SAMPLES_DIR = DATA_DIR / "voice_samples"
DB_PATH = DATA_DIR / "vozmeet.db"

WHISPER_MODEL = "large-v3-turbo"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_DEVICE = "auto"

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
