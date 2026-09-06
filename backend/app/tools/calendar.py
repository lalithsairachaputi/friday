from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from backend.app.safety.policy import ToolSafetyClass
from backend.app.tools.base import BaseTool, ToolContext, ToolResult


class CalendarAdapter(BaseTool):
    name = "calendar"
    safety = ToolSafetyClass.READ_ONLY
    permission = "calendar_read"

    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = {}

    def seed(self, user_id: str, events: list[dict]) -> None:
        self._events[user_id] = events

    async def run(self, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        if cancel.is_set():
            return ToolResult(ok=False, cancelled=True)
        events = self._events.get(ctx.user_id, [])
        if not events:
            now = datetime.now(timezone.utc)
            events = [
                {
                    "title": "Team standup",
                    "start": (now + timedelta(hours=2)).isoformat(),
                    "calendar": "primary",
                    "source": "local_adapter",
                }
            ]
        return ToolResult(ok=True, data={"events": events, "personal": True})


class TaskReminderAdapter(BaseTool):
    name = "tasks"
    safety = ToolSafetyClass.REVERSIBLE_WRITE
    permission = "tasks_write"

    def __init__(self) -> None:
        self._tasks: dict[str, list[dict]] = {}

    async def run(self, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        if cancel.is_set():
            return ToolResult(ok=False, cancelled=True)
        bucket = self._tasks.setdefault(ctx.user_id, [])
        action = ctx.constraints.get("action", "list")
        if action == "add":
            item = {"title": ctx.input, "done": False}
            bucket.append(item)
            return ToolResult(ok=True, data={"task": item})
        return ToolResult(ok=True, data={"tasks": bucket})


class InformationRetrievalTool(BaseTool):
    name = "info"
    safety = ToolSafetyClass.READ_ONLY

    async def run(self, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        if cancel.is_set():
            return ToolResult(ok=False, cancelled=True)
        return ToolResult(
            ok=True,
            data={
                "kind": "model_knowledge",
                "note": "Not a live web result. Use web_research for current information.",
                "query": ctx.input,
            },
        )
