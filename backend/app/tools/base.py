from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.app.safety.policy import ToolSafetyClass


@dataclass
class ToolContext:
    user_id: str
    conversation_id: str
    turn_id: str
    generation_id: int
    language: str
    input: str
    constraints: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    permissions: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    stale: bool = False
    cancelled: bool = False
    generation_id: int = 0
    sources: list[dict] = field(default_factory=list)
    finished_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseTool(ABC):
    name: str
    safety: ToolSafetyClass = ToolSafetyClass.READ_ONLY
    permission: str | None = None

    @abstractmethod
    async def run(self, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        ...
