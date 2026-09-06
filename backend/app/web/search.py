from __future__ import annotations

import asyncio
from typing import Any, Protocol

from backend.app.config.settings import Settings
from backend.app.web.source import now_iso


class SearchBackend(Protocol):
    async def search(self, query: str, *, max_results: int = 8) -> list[dict[str, Any]]:
        ...


class DuckDuckGoSearch:
    async def search(self, query: str, *, max_results: int = 8) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            from ddgs import DDGS

            rows = []
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=max_results):
                    rows.append(
                        {
                            "title": item.get("title"),
                            "href": item.get("href"),
                            "body": item.get("body"),
                            "retrieved_at": now_iso(),
                        }
                    )
            return rows

        return await asyncio.to_thread(_run)


class TavilySearch:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int = 8) -> list[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": r.get("title"),
                "href": r.get("url"),
                "body": r.get("content"),
                "retrieved_at": now_iso(),
            }
            for r in data.get("results", [])
        ]


def build_search_backend(settings: Settings) -> SearchBackend:
    if settings.tavily_api_key:
        return TavilySearch(settings.tavily_api_key)
    return DuckDuckGoSearch()
