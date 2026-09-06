from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TurnEndpoint:
    is_final: bool
    speech_started: bool


class TurnDetector:
    """Lightweight VAD/end-of-turn adapter used by tests and the REST path.

    LiveKit AgentSession owns production VAD / adaptive interruption.
    """

    def __init__(self, min_ms: int = 400) -> None:
        self.min_ms = min_ms

    def from_activity(self, *, speech_ms: int, silence_ms: int, interrupted: bool) -> TurnEndpoint:
        if interrupted:
            return TurnEndpoint(is_final=False, speech_started=True)
        if speech_ms > 0 and silence_ms >= self.min_ms:
            return TurnEndpoint(is_final=True, speech_started=False)
        return TurnEndpoint(is_final=False, speech_started=speech_ms > 0)
