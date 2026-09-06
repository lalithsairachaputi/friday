from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    USER_SPEECH_STARTED = "USER_SPEECH_STARTED"
    USER_SPEECH_PARTIAL = "USER_SPEECH_PARTIAL"
    USER_SPEECH_FINAL = "USER_SPEECH_FINAL"
    LANGUAGE_DETECTED = "LANGUAGE_DETECTED"
    LANGUAGE_CHANGED = "LANGUAGE_CHANGED"
    AGENT_THINKING_STARTED = "AGENT_THINKING_STARTED"
    AGENT_RESPONSE_PARTIAL = "AGENT_RESPONSE_READY_PARTIAL"
    AGENT_RESPONSE_READY = "AGENT_RESPONSE_READY"
    TOOL_CREATED = "TOOL_CREATED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_PROGRESS = "TOOL_PROGRESS"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_FAILED = "TOOL_FAILED"
    TOOL_CANCELLED = "TOOL_CANCELLED"
    TOOL_STALE = "TOOL_STALE"
    WEB_SEARCH_STARTED = "WEB_SEARCH_STARTED"
    WEB_RESULT_RECEIVED = "WEB_RESULT_RECEIVED"
    WEB_PAGE_OPENED = "WEB_PAGE_OPENED"
    WEB_RESEARCH_COMPLETED = "WEB_RESEARCH_COMPLETED"
    WEB_RESULT_STALE = "WEB_RESULT_STALE"
    TTS_STARTED = "TTS_STARTED"
    TTS_FIRST_AUDIO = "TTS_FIRST_AUDIO"
    TTS_AUDIO_CHUNK = "TTS_AUDIO_CHUNK"
    TTS_INTERRUPTED = "TTS_INTERRUPTED"
    TTS_COMPLETED = "TTS_COMPLETED"
    TTS_CANCELLED = "TTS_CANCELLED"
    TURN_INTERRUPTED = "TURN_INTERRUPTED"
    GENERATION_INVALIDATED = "GENERATION_INVALIDATED"
    STALE_RESULT_DISCARDED = "STALE_RESULT_DISCARDED"
    STALE_WEB_RESULT_DISCARDED = "STALE_WEB_RESULT_DISCARDED"


@dataclass
class RealtimeEvent:
    type: EventType
    user_id: str
    conversation_id: str
    turn_id: str | None = None
    generation_id: int | None = None
    task_id: str | None = None
    response_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "generation_id": self.generation_id,
            "task_id": self.task_id,
            "response_id": self.response_id,
            "payload": self.payload,
            "ts": self.ts,
        }


class EventBus:
    def __init__(self) -> None:
        self._history: list[RealtimeEvent] = []
        self._subscribers: list = []

    def subscribe(self, callback) -> None:
        self._subscribers.append(callback)

    def emit(self, event: RealtimeEvent) -> RealtimeEvent:
        self._history.append(event)
        if len(self._history) > 2000:
            self._history = self._history[-1000:]
        for cb in list(self._subscribers):
            cb(event)
        return event

    def recent(self, conversation_id: str | None = None, limit: int = 100) -> list[dict]:
        items = self._history
        if conversation_id:
            items = [e for e in items if e.conversation_id == conversation_id]
        return [e.to_dict() for e in items[-limit:]]
