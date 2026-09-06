from __future__ import annotations

from backend.app.observability.logging import logger
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.state.conversation import ConversationState, SpeechState


class InterruptionManager:
    """Barge-in is driven by speech activity, not keyword lists."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def on_user_speech_started(self, state: ConversationState, *, source: str = "vad") -> bool:
        speaking_or_working = state.speech_state in {
            SpeechState.SPEAKING,
            SpeechState.THINKING,
        } or state.task_is_active
        if not speaking_or_working:
            return False
        old_gen = state.active_generation_id
        state.mark_interrupted()
        self.bus.emit(
            RealtimeEvent(
                type=EventType.TURN_INTERRUPTED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=state.active_turn_id,
                generation_id=state.active_generation_id,
                payload={"source": source, "old_generation": old_gen},
            )
        )
        self.bus.emit(
            RealtimeEvent(
                type=EventType.GENERATION_INVALIDATED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=state.active_turn_id,
                generation_id=state.active_generation_id,
                payload={"old_generation": old_gen, "source": source},
            )
        )
        logger.info(
            "TURN_INTERRUPTED",
            extra={
                "user_id": state.user_id,
                "conversation_id": state.conversation_id,
                "turn_id": state.active_turn_id,
                "old_generation": old_gen,
                "generation_id": state.active_generation_id,
                "event": "TURN_INTERRUPTED",
            },
        )
        metrics.inc("interruptions")
        return True
