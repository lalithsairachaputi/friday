from __future__ import annotations

from dataclasses import dataclass

from backend.app.observability.logging import logger
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.state.conversation import ConversationState


@dataclass(frozen=True)
class GenerationContext:
    user_id: str
    conversation_id: str
    turn_id: str | None
    generation_id: int
    task_id: str | None = None
    operation: str = ""


class GenerationFence:
    """Cancellation is not enough: every async result must match current generation."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def is_current(self, state: ConversationState, generation_id: int) -> bool:
        return generation_id == state.active_generation_id

    def discard_if_stale(
        self,
        state: ConversationState,
        ctx: GenerationContext,
        *,
        web: bool = False,
        extra: dict | None = None,
    ) -> bool:
        if self.is_current(state, ctx.generation_id):
            return False
        event_type = EventType.STALE_WEB_RESULT_DISCARDED if web else EventType.STALE_RESULT_DISCARDED
        reason = "generation_mismatch"
        payload = {
            "operation": ctx.operation,
            "reason": reason,
            "old_generation": ctx.generation_id,
            "current_generation": state.active_generation_id,
            **(extra or {}),
        }
        self.bus.emit(
            RealtimeEvent(
                type=event_type,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=ctx.turn_id,
                generation_id=state.active_generation_id,
                task_id=ctx.task_id,
                payload=payload,
            )
        )
        logger.info(
            "STALE_WEB_RESULT_DISCARDED" if web else "STALE_RESULT_DISCARDED",
            extra={
                "user_id": state.user_id,
                "conversation_id": state.conversation_id,
                "turn_id": ctx.turn_id,
                "task_id": ctx.task_id,
                "old_generation": ctx.generation_id,
                "current_generation": state.active_generation_id,
                "operation": ctx.operation,
                "reason": reason,
                "event": event_type.value,
            },
        )
        metrics.inc("stale_results_discarded")
        if web:
            metrics.inc("stale_web_results_discarded")
        return True
