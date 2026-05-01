from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Speaker:
    id: int
    name: str
    display_name: str
    embedding: bytes
    embedding_count: int = 1
    sample_audio_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    language_hint: str = "auto"


@dataclass
class Recording:
    id: int
    filename: str
    original_path: str
    processed_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    language_detected: Optional[str] = None
    speaker_count: Optional[int] = None
    status: str = "uploaded"
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class Segment:
    id: int
    recording_id: int
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[int] = None
    raw_speaker_label: Optional[str] = None
    confidence: Optional[float] = None


@dataclass
class RecordingSpeaker:
    recording_id: int
    raw_label: str
    speaker_id: Optional[int] = None
    match_confidence: Optional[float] = None
    confirmed_by_user: int = 0
