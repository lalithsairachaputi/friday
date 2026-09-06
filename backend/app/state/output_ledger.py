from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class OutputRecord:
    response_id: str
    user_id: str
    conversation_id: str
    turn_id: str
    generation_id: int
    text: str
    language: str
    provider: str
    model: str | None
    speaker: str | None
    tts_started: bool = False
    tts_first_audio: bool = False
    tts_audio_chunks: int = 0
    tts_interrupted: bool = False
    tts_completed: bool = False
    tts_cancelled: bool = False
    audio_started_at: str | None = None
    audio_first_byte_at: str | None = None
    audio_finished_at: str | None = None
    audio_cancelled_at: str | None = None
    segments_emitted: list[str] = field(default_factory=list)
    heard_text: str = ""

    def mark_partial_heard(self) -> None:
        self.heard_text = " ".join(self.segments_emitted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "turn_id": self.turn_id,
            "generation_id": self.generation_id,
            "text": self.text,
            "heard_text": self.heard_text,
            "language": self.language,
            "provider": self.provider,
            "model": self.model,
            "speaker": self.speaker,
            "tts_interrupted": self.tts_interrupted,
            "tts_completed": self.tts_completed,
            "tts_cancelled": self.tts_cancelled,
            "audio_started_at": self.audio_started_at,
            "audio_first_byte_at": self.audio_first_byte_at,
            "audio_finished_at": self.audio_finished_at,
            "audio_cancelled_at": self.audio_cancelled_at,
            "segments_emitted": self.segments_emitted,
        }


class OutputLedger:
    """Tracks what the user actually received, including partial interrupted speech."""

    def __init__(self) -> None:
        self._by_conversation: dict[str, list[OutputRecord]] = {}
        self._active: dict[str, OutputRecord] = {}

    def start(self, record: OutputRecord) -> OutputRecord:
        self._by_conversation.setdefault(record.conversation_id, []).append(record)
        self._active[record.conversation_id] = record
        record.tts_started = True
        record.audio_started_at = datetime.now(timezone.utc).isoformat()
        return record

    def get_active(self, conversation_id: str) -> OutputRecord | None:
        return self._active.get(conversation_id)

    def interrupt(self, conversation_id: str) -> OutputRecord | None:
        rec = self._active.get(conversation_id)
        if not rec:
            return None
        rec.tts_interrupted = True
        rec.audio_cancelled_at = datetime.now(timezone.utc).isoformat()
        rec.mark_partial_heard()
        return rec

    def complete(self, conversation_id: str) -> OutputRecord | None:
        rec = self._active.get(conversation_id)
        if not rec:
            return None
        rec.tts_completed = True
        rec.audio_finished_at = datetime.now(timezone.utc).isoformat()
        rec.heard_text = rec.text
        return rec

    def history(self, conversation_id: str) -> list[dict]:
        return [r.to_dict() for r in self._by_conversation.get(conversation_id, [])]
