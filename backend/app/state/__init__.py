from __future__ import annotations

import threading

from backend.app.state.conversation import ConversationState
from backend.app.state.generation import GenerationFence
from backend.app.state.output_ledger import OutputLedger


class ConversationRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ConversationState] = {}
        self.ledger = OutputLedger()

    def get_or_create(self, user_id: str, conversation_id: str) -> ConversationState:
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                state = ConversationState(user_id=user_id, conversation_id=conversation_id)
                self._states[conversation_id] = state
            if state.user_id != user_id:
                raise PermissionError("conversation does not belong to authenticated user")
            return state

    def get(self, conversation_id: str) -> ConversationState | None:
        return self._states.get(conversation_id)


registry = ConversationRegistry()


def bind_fence(bus) -> GenerationFence:
    return GenerationFence(bus)
