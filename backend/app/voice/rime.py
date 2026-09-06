from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol

import httpx

from backend.app.config.languages import LanguageProfile
from backend.app.config.settings import Settings
from backend.app.observability.logging import logger, new_id
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.state.generation import GenerationContext, GenerationFence
from backend.app.state.conversation import ConversationState, SpeechState
from backend.app.state.output_ledger import OutputLedger, OutputRecord


class TtsCancelled(Exception):
    pass


@dataclass
class VoiceHandle:
    response_id: str
    provider: str
    model: str | None
    speaker: str | None
    language: str
    transport: str
    fallback_reason: str | None
    generation_id: int
    cancel_event: asyncio.Event


class TtsBackend(Protocol):
    name: str

    async def stream(self, text: str, profile: LanguageProfile, handle: VoiceHandle) -> AsyncIterator[bytes]:
        ...

    async def cancel(self, handle: VoiceHandle) -> None:
        ...


class RimeTtsBackend:
    name = "rime"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream(self, text: str, profile: LanguageProfile, handle: VoiceHandle) -> AsyncIterator[bytes]:
        if not self.settings.rime_api_key:
            raise RuntimeError("RIME_API_KEY is not configured")
        delay = self.settings.tts_delay_ms / 1000
        if delay:
            await asyncio.sleep(delay)
        url = (
            f"{self.settings.rime_ws_url.rstrip('/')}/ws3"
            f"?speaker={profile.rime_speaker}"
            f"&modelId={profile.rime_model}"
            f"&lang={profile.rime_language}"
            f"&audioFormat=pcm"
            f"&samplingRate=24000"
            f"&segment=bySentence"
        )
        headers = {"Authorization": f"Bearer {self.settings.rime_api_key}"}
        first = True
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self.settings.rime_http_url,
                headers={**headers, "Accept": "audio/pcm", "Content-Type": "application/json"},
                json={
                    "text": text,
                    "speaker": profile.rime_speaker,
                    "modelId": profile.rime_model,
                    "lang": profile.rime_language,
                    "samplingRate": 24000,
                    "audioFormat": "pcm",
                },
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if handle.cancel_event.is_set():
                        raise TtsCancelled()
                    if first:
                        metrics.observe(
                            "rime_first_audio_ms",
                            (time.perf_counter() - start) * 1000,
                            key=f"rime:{profile.language_code}",
                        )
                        first = False
                    yield chunk
        _ = url  # WebSocket URL is the production transport; HTTP used when WS client unavailable.

    async def cancel(self, handle: VoiceHandle) -> None:
        handle.cancel_event.set()


class EdgeFallbackBackend:
    name = "edge"

    async def stream(self, text: str, profile: LanguageProfile, handle: VoiceHandle) -> AsyncIterator[bytes]:
        import edge_tts

        voices = {"ta": "ta-IN-PallaviNeural", "te": "te-IN-ShrutiNeural", "hi": "hi-IN-SwaraNeural", "en": "en-US-JennyNeural"}
        communicate = edge_tts.Communicate(text, voices.get(profile.language_code, "en-US-JennyNeural"))
        async for chunk in communicate.stream():
            if handle.cancel_event.is_set():
                raise TtsCancelled()
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def cancel(self, handle: VoiceHandle) -> None:
        handle.cancel_event.set()


class VoiceOutputService:
    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        fence: GenerationFence,
        ledger: OutputLedger,
        rime: TtsBackend | None = None,
        fallback: TtsBackend | None = None,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.fence = fence
        self.ledger = ledger
        self.rime = rime or RimeTtsBackend(settings)
        self.fallback = fallback or EdgeFallbackBackend()
        self._active: dict[str, VoiceHandle] = {}

    def get_provider(self, profile: LanguageProfile) -> tuple[TtsBackend, str, str | None]:
        if profile.rime_enabled:
            return self.rime, "rime", None
        return self.fallback, profile.fallback_provider or "fallback", profile.fallback_reason

    def get_active_response(self, conversation_id: str) -> VoiceHandle | None:
        return self._active.get(conversation_id)

    def get_voice(self, profile: LanguageProfile) -> str | None:
        return profile.rime_speaker if profile.rime_enabled else None

    def get_model(self, profile: LanguageProfile) -> str | None:
        return profile.rime_model if profile.rime_enabled else None

    async def stop_current_audio(self, state: ConversationState) -> None:
        handle = self._active.get(state.conversation_id)
        if not handle:
            return
        start = time.perf_counter()
        handle.cancel_event.set()
        rec = self.ledger.interrupt(state.conversation_id)
        self.bus.emit(
            RealtimeEvent(
                type=EventType.TTS_INTERRUPTED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=state.active_turn_id,
                generation_id=state.active_generation_id,
                response_id=handle.response_id,
            )
        )
        metrics.observe("rime_cancel_ms", (time.perf_counter() - start) * 1000, key="tts-cancel")
        if rec:
            rec.tts_cancelled = True

    async def cancel(self, state: ConversationState) -> None:
        await self.stop_current_audio(state)

    async def speak(
        self,
        state: ConversationState,
        text: str,
        profile: LanguageProfile,
        *,
        turn_id: str,
        generation_id: int,
        on_chunk=None,
    ) -> OutputRecord:
        backend, provider, fallback_reason = self.get_provider(profile)
        response_id = new_id("resp")
        handle = VoiceHandle(
            response_id=response_id,
            provider=provider,
            model=profile.rime_model if provider == "rime" else None,
            speaker=profile.rime_speaker if provider == "rime" else None,
            language=profile.language_code,
            transport=profile.transport,
            fallback_reason=fallback_reason,
            generation_id=generation_id,
            cancel_event=asyncio.Event(),
        )
        self._active[state.conversation_id] = handle
        record = OutputRecord(
            response_id=response_id,
            user_id=state.user_id,
            conversation_id=state.conversation_id,
            turn_id=turn_id,
            generation_id=generation_id,
            text=text,
            language=profile.language_code,
            provider=provider,
            model=handle.model,
            speaker=handle.speaker,
        )
        self.ledger.start(record)
        ctx = GenerationContext(
            user_id=state.user_id,
            conversation_id=state.conversation_id,
            turn_id=turn_id,
            generation_id=generation_id,
            operation="tts",
        )
        self.bus.emit(
            RealtimeEvent(
                type=EventType.TTS_STARTED,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                turn_id=turn_id,
                generation_id=generation_id,
                response_id=response_id,
                payload={
                    "provider": provider,
                    "model": handle.model,
                    "speaker": handle.speaker,
                    "language": profile.language_code,
                    "transport": profile.transport,
                    "fallback_reason": fallback_reason,
                    "active_tts_provider": provider,
                    "rime_model": handle.model,
                    "rime_speaker": handle.speaker,
                },
            )
        )
        state.speech_state = SpeechState.SPEAKING
        first = True
        try:
            async for chunk in backend.stream(text, profile, handle):
                if self.fence.discard_if_stale(state, ctx):
                    handle.cancel_event.set()
                    self.bus.emit(
                        RealtimeEvent(
                            type=EventType.TTS_CANCELLED,
                            user_id=state.user_id,
                            conversation_id=state.conversation_id,
                            turn_id=turn_id,
                            generation_id=state.active_generation_id,
                            response_id=response_id,
                        )
                    )
                    break
                record.tts_audio_chunks += 1
                if first:
                    first = False
                    record.tts_first_audio = True
                    record.audio_first_byte_at = datetime.now(timezone.utc).isoformat()
                    self.bus.emit(
                        RealtimeEvent(
                            type=EventType.TTS_FIRST_AUDIO,
                            user_id=state.user_id,
                            conversation_id=state.conversation_id,
                            turn_id=turn_id,
                            generation_id=generation_id,
                            response_id=response_id,
                        )
                    )
                self.bus.emit(
                    RealtimeEvent(
                        type=EventType.TTS_AUDIO_CHUNK,
                        user_id=state.user_id,
                        conversation_id=state.conversation_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        response_id=response_id,
                        payload={"bytes": len(chunk)},
                    )
                )
                if on_chunk:
                    await on_chunk(chunk)
            else:
                if self.fence.is_current(state, generation_id):
                    self.ledger.complete(state.conversation_id)
                    self.bus.emit(
                        RealtimeEvent(
                            type=EventType.TTS_COMPLETED,
                            user_id=state.user_id,
                            conversation_id=state.conversation_id,
                            turn_id=turn_id,
                            generation_id=generation_id,
                            response_id=response_id,
                            payload={"provider": provider},
                        )
                    )
        except TtsCancelled:
            record.tts_cancelled = True
        finally:
            if self._active.get(state.conversation_id) is handle:
                self._active.pop(state.conversation_id, None)
        return record

    async def stream(self, *args, **kwargs) -> OutputRecord:
        return await self.speak(*args, **kwargs)
