from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.app.config.settings import Settings
from backend.app.observability.logging import new_id
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.safety.policy import requires_confirmation
from backend.app.state.conversation import ConversationState
from backend.app.state.generation import GenerationContext, GenerationFence
from backend.app.tools.base import BaseTool, ToolContext, ToolResult


class ToolOrchestrator:
    def __init__(self, settings: Settings, bus: EventBus, fence: GenerationFence) -> None:
        self.settings = settings
        self.bus = bus
        self.fence = fence
        self.tools: dict[str, BaseTool] = {}
        self._cancels: dict[str, asyncio.Event] = {}

    def register(self, tool: BaseTool) -> None:
        self.tools[tool.name] = tool

    def cancel_task(self, task_id: str) -> None:
        ev = self._cancels.get(task_id)
        if ev:
            ev.set()

    def cancel_conversation(self, conversation_id: str) -> None:
        for key, ev in list(self._cancels.items()):
            if key.startswith(conversation_id):
                ev.set()

    async def execute(self, state: ConversationState, tool_name: str, ctx: ToolContext) -> ToolResult:
        tool = self.tools[tool_name]
        if tool.permission and tool.permission not in ctx.permissions:
            return ToolResult(ok=False, error="permission_denied", generation_id=ctx.generation_id)
        if requires_confirmation(tool.safety) and not ctx.constraints.get("confirmed"):
            return ToolResult(ok=False, error="confirmation_required", generation_id=ctx.generation_id)

        ctx.task_id = ctx.task_id or new_id("task")
        cancel = asyncio.Event()
        self._cancels[f"{state.conversation_id}:{ctx.task_id}"] = cancel
        gen = GenerationContext(
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
            generation_id=ctx.generation_id,
            task_id=ctx.task_id,
            operation=tool_name,
        )
        self.bus.emit(
            RealtimeEvent(
                type=EventType.TOOL_CREATED,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                turn_id=ctx.turn_id,
                generation_id=ctx.generation_id,
                task_id=ctx.task_id,
                payload={"tool": tool_name},
            )
        )
        self.bus.emit(
            RealtimeEvent(
                type=EventType.TOOL_STARTED,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                turn_id=ctx.turn_id,
                generation_id=ctx.generation_id,
                task_id=ctx.task_id,
                payload={"tool": tool_name},
            )
        )
        start = time.perf_counter()
        try:
            if self.settings.tool_delay_ms:
                await asyncio.sleep(self.settings.tool_delay_ms / 1000)
            result = await tool.run(ctx, cancel)
            result.generation_id = ctx.generation_id
            if cancel.is_set() and not result.cancelled:
                result.cancelled = True
            if self.fence.discard_if_stale(state, gen, web=tool_name.startswith("web")):
                result.stale = True
                self.bus.emit(
                    RealtimeEvent(
                        type=EventType.TOOL_STALE,
                        user_id=ctx.user_id,
                        conversation_id=ctx.conversation_id,
                        turn_id=ctx.turn_id,
                        generation_id=state.active_generation_id,
                        task_id=ctx.task_id,
                        payload={"tool": tool_name, "old_generation": ctx.generation_id},
                    )
                )
                return result
            event = EventType.TOOL_CANCELLED if result.cancelled else EventType.TOOL_COMPLETED if result.ok else EventType.TOOL_FAILED
            self.bus.emit(
                RealtimeEvent(
                    type=event,
                    user_id=ctx.user_id,
                    conversation_id=ctx.conversation_id,
                    turn_id=ctx.turn_id,
                    generation_id=ctx.generation_id,
                    task_id=ctx.task_id,
                    payload={"tool": tool_name, "ok": result.ok, "error": result.error},
                )
            )
            return result
        finally:
            metrics.observe("tool_latency_ms", (time.perf_counter() - start) * 1000, key=f"tool:{tool_name}")
            self._cancels.pop(f"{state.conversation_id}:{ctx.task_id}", None)
