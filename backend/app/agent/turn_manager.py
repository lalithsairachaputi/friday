from __future__ import annotations

from backend.app.observability.logging import new_id
from backend.app.state.conversation import ConversationState


class TurnManager:
    def start_user_turn(self, state: ConversationState, raw: str, normalized: str | None = None) -> str:
        turn_id = new_id("turn")
        state.active_turn_id = turn_id
        state.last_user_utterance_raw = raw
        state.last_user_utterance = normalized or raw
        state.turns.append(
            {
                "turn_id": turn_id,
                "generation_id": state.active_generation_id,
                "raw_transcript": raw,
                "normalized_transcript": normalized or raw,
                "role": "user",
            }
        )
        return turn_id

    def append_agent(self, state: ConversationState, text: str, *, interrupted: bool = False) -> None:
        state.last_agent_utterance = text
        state.turns.append(
            {
                "turn_id": state.active_turn_id,
                "generation_id": state.active_generation_id,
                "text": text,
                "role": "agent",
                "interrupted": interrupted,
            }
        )
