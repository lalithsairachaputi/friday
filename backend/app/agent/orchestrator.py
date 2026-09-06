from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.response_stream import iter_segments
from backend.app.agent.turn_manager import TurnManager
from backend.app.config.languages import get_profile
from backend.app.config.settings import Settings
from backend.app.observability.logging import logger
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.realtime.interruption import InterruptionManager
from backend.app.state.conversation import ActiveTask, ConversationState, SpeechState, TaskRuntimeState
from backend.app.state.generation import GenerationFence
from backend.app.tools.base import ToolContext
from backend.app.tools.orchestrator import ToolOrchestrator
from backend.app.tools.reconciler import ReconciliationKind, TaskReconciler
from backend.app.voice.language_router import LanguageRouter
from backend.app.voice.rime import VoiceOutputService


WEB_HINTS = (
    "search the web",
    "search for",
    "look up",
    "browse",
    "latest",
    "today",
    "current",
    "research",
    "compare",
    "best laptop",
    "news",
    "weather",
    "documentation",
)


class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        fence: GenerationFence,
        tools: ToolOrchestrator,
        voice: VoiceOutputService,
        language: LanguageRouter,
        interruptions: InterruptionManager,
        turns: TurnManager | None = None,
        reconciler: TaskReconciler | None = None,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.fence = fence
        self.tools = tools
        self.voice = voice
        self.language = language
        self.interruptions = interruptions
        self.turns = turns or TurnManager()
        self.reconciler = reconciler or TaskReconciler()

    async def apply_interruption(self, state: ConversationState) -> int:
        self.interruptions.on_user_speech_started(state, source="vad")
        await self.voice.stop_current_audio(state)
        self.tools.cancel_conversation(state.conversation_id)
        if state.active_task:
            state.active_task.generation_id = state.active_generation_id
        return state.active_generation_id

    async def handle_utterance(
        self,
        state: ConversationState,
        raw_transcript: str,
        *,
        permissions: list[str],
        barge_in: bool = False,
        on_audio_chunk=None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        if barge_in:
            await self.apply_interruption(state)
            if self.settings.interruption_delay_ms:
                await asyncio.sleep(self.settings.interruption_delay_ms / 1000)

        decision = self.language.detect(raw_transcript, state.current_language)
        self.bus.emit(
            RealtimeEvent(
                type=EventType.LANGUAGE_DETECTED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=state.active_turn_id,
                generation_id=state.active_generation_id,
                payload={
                    "detected_language": decision.detected_language,
                    "language_confidence": decision.language_confidence,
                    "code_switched": decision.code_switched,
                    "raw_transcript": raw_transcript,
                },
            )
        )
        if decision.switched:
            state.current_language = decision.response_language
            state.language_confidence = decision.language_confidence
            self.bus.emit(
                RealtimeEvent(
                    type=EventType.LANGUAGE_CHANGED,
                    user_id=state.user_id,
                    conversation_id=state.conversation_id,
                    generation_id=state.active_generation_id,
                    payload={"response_language": decision.response_language},
                )
            )

        rec = self.reconciler.classify(
            state,
            raw_transcript,
            language_changed=decision.switched or decision.explicit_request,
            explicit_language=decision.explicit_request,
        )
        turn_id = self.turns.start_user_turn(state, raw_transcript)
        generation_id = state.active_generation_id
        if rec.kind == ReconciliationKind.CANCELLATION:
            state.task_state = TaskRuntimeState.CANCELLED
            if state.active_task:
                state.active_task.status = TaskRuntimeState.CANCELLED
            text = self._cancel_speech(decision.response_language)
            await self._speak(state, text, decision.response_language, turn_id, generation_id, on_audio_chunk)
            return self._result(state, rec.kind.value, text, decision)

        if rec.kind == ReconciliationKind.STATUS_REQUEST:
            text = self._status_speech(state, decision.response_language)
            await self._speak(state, text, decision.response_language, turn_id, generation_id, on_audio_chunk)
            return self._result(state, rec.kind.value, text, decision)

        if rec.kind in {
            ReconciliationKind.TASK_MODIFICATION,
            ReconciliationKind.LANGUAGE_CHANGE_AND_TASK_MODIFICATION,
        }:
            state.current_constraints.update(rec.constraints_delta)
            if state.active_task:
                state.active_task.constraints.update(rec.constraints_delta)
                state.active_task.generation_id = generation_id
                state.active_task.status = TaskRuntimeState.RUNNING
            state.task_state = TaskRuntimeState.RUNNING

        if rec.kind == ReconciliationKind.LANGUAGE_CHANGE and not state.task_is_active:
            text = self._language_ack(decision.response_language)
            await self._speak(state, text, decision.response_language, turn_id, generation_id, on_audio_chunk)
            return self._result(state, rec.kind.value, text, decision)

        needs_web = self._needs_web(raw_transcript, rec.kind, state)
        needs_calendar = "calendar" in raw_transcript.lower() or "meeting" in raw_transcript.lower()
        state.speech_state = SpeechState.THINKING
        self.bus.emit(
            RealtimeEvent(
                type=EventType.AGENT_THINKING_STARTED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=turn_id,
                generation_id=generation_id,
            )
        )

        tool_result = None
        if needs_web:
            if rec.kind == ReconciliationKind.NEW_REQUEST or state.active_task is None:
                state.active_task = ActiveTask(
                    task_id=f"task_{turn_id}",
                    kind="web_research",
                    query=raw_transcript,
                    constraints=dict(state.current_constraints),
                    status=TaskRuntimeState.RUNNING,
                    generation_id=generation_id,
                )
            state.task_state = TaskRuntimeState.RUNNING
            state.active_tool = "web_research"
            status_line = self._checking_speech(decision.response_language)
            speak_task = asyncio.create_task(
                self._speak(state, status_line, decision.response_language, turn_id, generation_id, on_audio_chunk)
            )
            ctx = ToolContext(
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=turn_id,
                generation_id=generation_id,
                language=decision.response_language,
                input=state.active_task.query if state.active_task else raw_transcript,
                constraints={**state.current_constraints, "_state": state},
                task_id=state.active_task.task_id if state.active_task else "",
                permissions=permissions,
            )
            tool_result = await self.tools.execute(state, "web_research", ctx)
            await speak_task
            if tool_result.stale or tool_result.cancelled:
                return self._result(state, rec.kind.value, None, decision, stale=True)
            if tool_result.ok:
                state.active_task.sources = tool_result.sources
                state.active_task.status = TaskRuntimeState.COMPLETED
                state.task_state = TaskRuntimeState.COMPLETED
                answer = await self._compose_answer(state, raw_transcript, tool_result.data, decision.response_language)
            else:
                answer = "I could not finish that web search. Ask me to try again."
        elif needs_calendar:
            ctx = ToolContext(
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=turn_id,
                generation_id=generation_id,
                language=decision.response_language,
                input=raw_transcript,
                permissions=permissions,
            )
            tool_result = await self.tools.execute(state, "calendar", ctx)
            if tool_result.ok and not tool_result.stale:
                events = tool_result.data.get("events", [])
                answer = "Your next calendar item is " + (events[0]["title"] if events else "empty") + "."
            else:
                answer = "I could not read the calendar for this account."
        else:
            answer = await self._compose_answer(state, raw_transcript, None, decision.response_language)

        if not self.fence.is_current(state, generation_id):
            logger.info("STALE_RESULT_DISCARDED", extra={"operation": "final_answer", "reason": "generation_mismatch"})
            return self._result(state, rec.kind.value, None, decision, stale=True)

        profile = get_profile(decision.response_language)
        record = await self.voice.speak(
            state,
            answer,
            profile,
            turn_id=turn_id,
            generation_id=generation_id,
            on_chunk=on_audio_chunk,
        )
        self.turns.append_agent(state, answer, interrupted=record.tts_interrupted)
        metrics.observe("end_of_turn_to_first_audio_ms", (time.perf_counter() - t0) * 1000, key="e2e")
        return self._result(state, rec.kind.value, answer, decision, sources=(tool_result.sources if tool_result else []))

    async def _speak(self, state, text, lang, turn_id, generation_id, on_audio_chunk):
        if not self.fence.is_current(state, generation_id):
            return
        await self.voice.speak(
            state,
            text,
            get_profile(lang),
            turn_id=turn_id,
            generation_id=generation_id,
            on_chunk=on_audio_chunk,
        )

    def _needs_web(self, text: str, kind: ReconciliationKind, state: ConversationState) -> bool:
        lower = text.lower()
        if kind in {
            ReconciliationKind.TASK_MODIFICATION,
            ReconciliationKind.LANGUAGE_CHANGE_AND_TASK_MODIFICATION,
        } and state.active_task and state.active_task.kind == "web_research":
            return True
        return any(h in lower for h in WEB_HINTS)

    async def _compose_answer(self, state: ConversationState, user_text: str, tool_data: dict | None, lang: str) -> str:
        if self.settings.llm_delay_ms:
            await asyncio.sleep(self.settings.llm_delay_ms / 1000)
        if not self.settings.openai_api_key:
            if tool_data and tool_data.get("summary"):
                return self._localize_fallback(tool_data["summary"], lang)
            return self._localize_fallback("I heard you. Tell me if you want me to search the web or check your calendar.", lang)
        payload = {
            "model": self.settings.openai_llm_model,
            "stream": True,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "utterance": user_text,
                            "language": lang,
                            "constraints": state.current_constraints,
                            "web": tool_data,
                            "heard_so_far": [
                                r.get("heard_text")
                                for r in []
                            ],
                        }
                    ),
                },
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        text = ""
        start = time.perf_counter()
        first = True
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", "https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                    except Exception:
                        continue
                    if first and delta:
                        metrics.observe("llm_first_token_ms", (time.perf_counter() - start) * 1000, key="llm")
                        first = False
                    text += delta
        spoken = []
        async for piece in iter_segments([text]):
            spoken.append(piece)
        return " ".join(spoken) if spoken else text.strip()

    def _checking_speech(self, lang: str) -> str:
        return {
            "en": "I'm checking current options.",
            "hi": "मैं अभी मौजूदा विकल्प देख रही हूँ।",
            "ta": "தற்போதைய விருப்பங்களை பார்க்கிறேன்.",
            "te": "ప్రస్తుత ఎంపికలు చూస్తున్నాను.",
        }.get(lang, "I'm checking current options.")

    def _cancel_speech(self, lang: str) -> str:
        return {
            "en": "Okay, I stopped.",
            "hi": "ठीक है, मैं रुक गई।",
            "ta": "சரி, நிறுத்திவிட்டேன்.",
            "te": "సరే, ఆపేశాను.",
        }.get(lang, "Okay, I stopped.")

    def _status_speech(self, state: ConversationState, lang: str) -> str:
        status = state.task_state.value
        return {
            "en": f"The current task is {status.lower()}.",
            "hi": f"अभी कार्य की स्थिति {status} है।",
            "ta": f"தற்போதைய பணி நிலை {status}.",
            "te": f"ప్రస్తుత పని స్థితి {status}.",
        }.get(lang, f"The current task is {status.lower()}.")

    def _language_ack(self, lang: str) -> str:
        return {
            "en": "I'll continue in English.",
            "hi": "अब मैं हिंदी में बात करूँगी।",
            "ta": "இப்போது தமிழில் தொடர்கிறேன்.",
            "te": "ఇప్పుడు తెలుగులో కొనసాగిస్తాను.",
        }.get(lang, "Okay.")

    def _localize_fallback(self, english: str, lang: str) -> str:
        if lang == "en":
            return english
        return english

    def _result(self, state, kind, text, decision, stale: bool = False, sources=None) -> dict[str, Any]:
        profile = get_profile(decision.response_language)
        return {
            "kind": kind,
            "text": text,
            "stale": stale,
            "language": decision.response_language,
            "detected_language": decision.detected_language,
            "language_confidence": decision.language_confidence,
            "code_switched": decision.code_switched,
            "raw_transcript": state.last_user_utterance_raw,
            "generation_id": state.active_generation_id,
            "conversation_id": state.conversation_id,
            "user_id": state.user_id,
            "sources": sources or [],
            "tts": {
                "active_tts_provider": "rime" if profile.rime_enabled else profile.fallback_provider,
                "rime_model": profile.rime_model,
                "rime_speaker": profile.rime_speaker,
                "language": profile.language_code,
                "transport": profile.transport,
                "fallback_reason": profile.fallback_reason,
            },
            "state": state.to_public_dict(),
        }
