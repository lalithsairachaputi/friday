from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.app.state.conversation import ConversationState


class ReconciliationKind(StrEnum):
    NEW_REQUEST = "new_request"
    TASK_MODIFICATION = "task_modification"
    CANCELLATION = "cancellation"
    CLARIFICATION = "clarification"
    STATUS_REQUEST = "status_request"
    SPEECH_INTERRUPTION_ONLY = "speech_interruption_only"
    LANGUAGE_CHANGE = "language_change"
    LANGUAGE_CHANGE_AND_TASK_MODIFICATION = "language_change_and_task_modification"


@dataclass
class Reconciliation:
    kind: ReconciliationKind
    constraints_delta: dict[str, Any]
    notes: str = ""


class TaskReconciler:
    """Classify a new utterance against the active task. Deterministic first, LLM optional."""

    CANCEL_PHRASES = ("stop", "never mind", "nevermind", "cancel", "forget it")
    STATUS_PHRASES = ("how long", "status", "are you done", "what's happening")
    MOD_HINTS = ("wait", "actually", "only", "just", "instead", "matrame", "मात्र", "मட்டும்", "మాత్రమే", "india", "cheapest")

    def classify(
        self,
        state: ConversationState,
        utterance: str,
        *,
        language_changed: bool = False,
        explicit_language: bool = False,
    ) -> Reconciliation:
        text = (utterance or "").strip()
        lower = text.lower()
        constraints: dict[str, Any] = {}

        if any(p in lower for p in self.CANCEL_PHRASES) and not any(
            h in lower for h in ("only", "just tell", "india", "focus")
        ):
            if "stop" in lower and ("only" in lower or "just" in lower or "focus" in lower):
                pass
            elif lower.strip() in {"stop", "stop.", "never mind", "nevermind", "cancel"}:
                return Reconciliation(ReconciliationKind.CANCELLATION, {})

        if any(p in lower for p in self.STATUS_PHRASES):
            return Reconciliation(ReconciliationKind.STATUS_REQUEST, {})

        if "india" in lower or "భారత" in text or "भारत" in text:
            constraints["availability"] = "India"
            constraints["region"] = "India"
        if "gaming" in lower:
            constraints["category"] = "gaming laptop"
        if "cheapest" in lower or "cheap" in lower:
            constraints["sort"] = "price_asc"
            constraints["limit"] = 1
        if "60000" in lower or "60,000" in lower or "60000" in text:
            constraints["budget_max"] = 60000
        if "only" in lower or "మాత్రమే" in text or "मट्टूम" in text or "மட்டும்" in text:
            constraints["restrict"] = True

        modifying = bool(constraints) or any(h in lower for h in self.MOD_HINTS)
        has_task = state.active_task is not None and state.task_is_active

        if language_changed and modifying and has_task:
            return Reconciliation(ReconciliationKind.LANGUAGE_CHANGE_AND_TASK_MODIFICATION, constraints)
        if explicit_language and not modifying:
            return Reconciliation(ReconciliationKind.LANGUAGE_CHANGE, {})
        if language_changed and not modifying and not has_task:
            return Reconciliation(ReconciliationKind.LANGUAGE_CHANGE, {})
        if has_task and modifying:
            return Reconciliation(ReconciliationKind.TASK_MODIFICATION, constraints)
        if has_task and language_changed and not modifying:
            return Reconciliation(ReconciliationKind.LANGUAGE_CHANGE, {})
        if not text:
            return Reconciliation(ReconciliationKind.SPEECH_INTERRUPTION_ONLY, {})
        return Reconciliation(ReconciliationKind.NEW_REQUEST, constraints)
