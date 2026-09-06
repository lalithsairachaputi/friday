from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from backend.app.config.settings import Settings
from backend.app.observability.logging import new_id
from backend.app.observability.metrics import metrics
from backend.app.realtime.events import EventBus, EventType, RealtimeEvent
from backend.app.state.conversation import ConversationState
from backend.app.state.generation import GenerationContext, GenerationFence
from backend.app.state.task_state import BrowseStatus
from backend.app.tools.base import BaseTool, ToolContext, ToolResult
from backend.app.safety.policy import ToolSafetyClass
from backend.app.web.browser import WebBrowserTool
from backend.app.web.ranking import rank_sources, to_source
from backend.app.web.search import SearchBackend, build_search_backend
from backend.app.web.source import WebSource, now_iso


TIME_SENSITIVE = re.compile(r"\b(latest|today|current|recent|this week|this month|new|updated)\b", re.I)


@dataclass
class BrowseTask:
    task_id: str
    user_id: str
    conversation_id: str
    turn_id: str
    generation_id: int
    query: str
    constraints: dict[str, Any]
    search_terms: list[str]
    domains: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    selected_sources: list[dict] = field(default_factory=list)
    status: BrowseStatus = BrowseStatus.CREATED
    search_timestamp: str | None = None
    timestamps: dict[str, str] = field(default_factory=dict)


class WebBrowsingOrchestrator:
    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        fence: GenerationFence,
        search: SearchBackend | None = None,
        browser: WebBrowserTool | None = None,
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.fence = fence
        self.search = search or build_search_backend(settings)
        self.browser = browser or WebBrowserTool(settings)
        self.tasks: dict[str, BrowseTask] = {}

    def _terms(self, query: str, constraints: dict[str, Any]) -> str:
        parts = [query]
        if constraints.get("category"):
            parts.append(str(constraints["category"]))
        if constraints.get("region") or constraints.get("availability"):
            parts.append(str(constraints.get("region") or constraints.get("availability")))
        if constraints.get("budget_max"):
            parts.append(f"under {constraints['budget_max']}")
        return " ".join(parts)

    async def research(self, state: ConversationState, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        task = BrowseTask(
            task_id=ctx.task_id or new_id("web"),
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
            generation_id=ctx.generation_id,
            query=ctx.input,
            constraints=dict(ctx.constraints),
            search_terms=[self._terms(ctx.input, ctx.constraints)],
        )
        self.tasks[task.task_id] = task
        gen = GenerationContext(
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
            generation_id=ctx.generation_id,
            task_id=task.task_id,
            operation="web_research",
        )
        task.status = BrowseStatus.SEARCHING
        task.search_timestamp = now_iso()
        task.timestamps["search_started"] = task.search_timestamp
        self.bus.emit(
            RealtimeEvent(
                type=EventType.WEB_SEARCH_STARTED,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                turn_id=ctx.turn_id,
                generation_id=ctx.generation_id,
                task_id=task.task_id,
                payload={"query": task.search_terms[0], "time_sensitive": bool(TIME_SENSITIVE.search(ctx.input))},
            )
        )
        if self.settings.web_search_delay_ms:
            await asyncio.sleep(self.settings.web_search_delay_ms / 1000)
        if cancel.is_set():
            task.status = BrowseStatus.CANCELLED
            return ToolResult(ok=False, cancelled=True, generation_id=ctx.generation_id)
        if self.fence.discard_if_stale(state, gen, web=True):
            task.status = BrowseStatus.STALE
            return ToolResult(ok=False, stale=True, generation_id=ctx.generation_id)

        start = asyncio.get_event_loop().time()
        try:
            hits = await self.search.search(task.search_terms[0], max_results=8)
        except Exception as exc:
            task.status = BrowseStatus.FAILED
            return ToolResult(ok=False, error=str(exc), generation_id=ctx.generation_id)
        metrics.observe("web_search_ms", (asyncio.get_event_loop().time() - start) * 1000, key="web-search")

        if self.fence.discard_if_stale(state, gen, web=True):
            task.status = BrowseStatus.STALE
            self.bus.emit(
                RealtimeEvent(
                    type=EventType.WEB_RESULT_STALE,
                    user_id=ctx.user_id,
                    conversation_id=ctx.conversation_id,
                    generation_id=state.active_generation_id,
                    task_id=task.task_id,
                    payload={"old_generation": ctx.generation_id},
                )
            )
            return ToolResult(ok=False, stale=True, generation_id=ctx.generation_id)

        sources: list[WebSource] = []
        for i, hit in enumerate(hits):
            src = to_source(hit, ctx.generation_id, relevance=1.0 - i * 0.08)
            if not src.retrieved_at:
                src.retrieved_at = now_iso()
            sources.append(src)
            self.bus.emit(
                RealtimeEvent(
                    type=EventType.WEB_RESULT_RECEIVED,
                    user_id=ctx.user_id,
                    conversation_id=ctx.conversation_id,
                    turn_id=ctx.turn_id,
                    generation_id=ctx.generation_id,
                    task_id=task.task_id,
                    payload=src.to_dict(),
                )
            )
        ranked = rank_sources(sources)
        task.results = [s.to_dict() for s in ranked]
        task.status = BrowseStatus.READING
        extracts: list[dict] = []
        for src in ranked[:3]:
            if cancel.is_set() or self.fence.discard_if_stale(state, gen, web=True):
                task.status = BrowseStatus.STALE
                return ToolResult(ok=False, stale=True, cancelled=cancel.is_set(), generation_id=ctx.generation_id)
            page = await self.browser.retrieve(src.url, cancel)
            if page.get("ok"):
                self.bus.emit(
                    RealtimeEvent(
                        type=EventType.WEB_PAGE_OPENED,
                        user_id=ctx.user_id,
                        conversation_id=ctx.conversation_id,
                        generation_id=ctx.generation_id,
                        task_id=task.task_id,
                        payload={"url": src.url, "title": page.get("title")},
                    )
                )
                extracts.append({"url": src.url, "title": page.get("title"), "text": page.get("text", "")[:2500]})
        task.status = BrowseStatus.ANALYZING
        if self.fence.discard_if_stale(state, gen, web=True):
            task.status = BrowseStatus.STALE
            return ToolResult(ok=False, stale=True, generation_id=ctx.generation_id)
        task.status = BrowseStatus.COMPLETED
        task.selected_sources = [s.to_dict() for s in ranked[:5]]
        summary_bits = [s.title for s in ranked[:3]]
        spoken = (
            "I found several current sources: " + "; ".join(summary_bits) + ". "
            + self._constraint_clause(task.constraints)
        )
        self.bus.emit(
            RealtimeEvent(
                type=EventType.WEB_RESEARCH_COMPLETED,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                turn_id=ctx.turn_id,
                generation_id=ctx.generation_id,
                task_id=task.task_id,
                payload={"sources": task.selected_sources, "search_timestamp": task.search_timestamp},
            )
        )
        return ToolResult(
            ok=True,
            data={
                "summary": spoken,
                "extracts": extracts,
                "search_timestamp": task.search_timestamp,
                "fresh_web": True,
            },
            sources=task.selected_sources,
            generation_id=ctx.generation_id,
        )

    def _constraint_clause(self, constraints: dict[str, Any]) -> str:
        bits = []
        if constraints.get("region") or constraints.get("availability"):
            bits.append(f"scope is {constraints.get('region') or constraints.get('availability')} only")
        if constraints.get("category"):
            bits.append(f"category {constraints['category']}")
        if constraints.get("budget_max"):
            bits.append(f"budget under {constraints['budget_max']}")
        if constraints.get("sort") == "price_asc":
            bits.append("sorted cheapest first")
        return ("Constraints: " + ", ".join(bits) + ".") if bits else ""


class WebResearchTool(BaseTool):
    name = "web_research"
    safety = ToolSafetyClass.READ_ONLY
    permission = "web_search"

    def __init__(self, orchestrator: WebBrowsingOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def run(self, ctx: ToolContext, cancel: asyncio.Event) -> ToolResult:
        # Uses conversation state via orchestrator.research caller; ToolOrchestrator wraps fencing.
        # Here we need the live ConversationState; the orchestrator stores last state on ctx.constraints.
        state: ConversationState = ctx.constraints["_state"]
        return await self.orchestrator.research(state, ctx, cancel)
