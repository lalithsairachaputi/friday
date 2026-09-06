from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SpeechState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


class TaskRuntimeState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    STALE = "STALE"


@dataclass
class ActiveTask:
    task_id: str
    kind: str
    query: str
    constraints: dict[str, Any] = field(default_factory=dict)
    status: TaskRuntimeState = TaskRuntimeState.IDLE
    generation_id: int = 0
    sources: list[dict[str, Any]] = field(default_factory=list)
    spoken_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "query": self.query,
            "constraints": self.constraints,
            "status": self.status.value,
            "generation_id": self.generation_id,
            "sources": self.sources,
            "spoken_summary": self.spoken_summary,
        }


@dataclass
class ConversationState:
    user_id: str
    conversation_id: str
    active_turn_id: str | None = None
    active_generation_id: int = 0
    current_language: str = "en"
    preferred_language: str = "en"
    language_confidence: float = 1.0
    active_task: ActiveTask | None = None
    active_tool: str | None = None
    active_tool_status: str | None = None
    last_user_utterance: str | None = None
    last_user_utterance_raw: str | None = None
    last_agent_utterance: str | None = None
    current_intent: str | None = None
    current_constraints: dict[str, Any] = field(default_factory=dict)
    speech_state: SpeechState = SpeechState.IDLE
    task_state: TaskRuntimeState = TaskRuntimeState.IDLE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def task_is_active(self) -> bool:
        return self.task_state in {TaskRuntimeState.RUNNING, TaskRuntimeState.WAITING}

    def bump_generation(self) -> int:
        self.active_generation_id += 1
        return self.active_generation_id

    def mark_interrupted(self) -> int:
        self.speech_state = SpeechState.INTERRUPTED
        if self.task_state == TaskRuntimeState.RUNNING:
            self.task_state = TaskRuntimeState.WAITING
        return self.bump_generation()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "active_turn_id": self.active_turn_id,
            "active_generation_id": self.active_generation_id,
            "current_language": self.current_language,
            "preferred_language": self.preferred_language,
            "language_confidence": self.language_confidence,
            "active_task": self.active_task.to_dict() if self.active_task else None,
            "active_tool": self.active_tool,
            "active_tool_status": self.active_tool_status,
            "last_user_utterance": self.last_user_utterance,
            "last_agent_utterance": self.last_agent_utterance,
            "current_intent": self.current_intent,
            "current_constraints": self.current_constraints,
            "speech_state": self.speech_state.value,
            "task_state": self.task_state.value,
        }
