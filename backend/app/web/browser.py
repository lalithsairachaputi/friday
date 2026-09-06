from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from backend.app.config.settings import Settings


class WebBrowserTool:
    """Fetches pages with robots awareness. Does not scrape authenticated private data."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http = http
        self._robots: dict[str, RobotFileParser] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = self._robots.get(robots_url)
        if rp is None:
            rp = RobotFileParser()
            try:
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                    resp = await client.get(robots_url)
                    if resp.status_code >= 400:
                        return True
                    rp.parse(resp.text.splitlines())
            except Exception:
                return True
            self._robots[robots_url] = rp
        return rp.can_fetch("FridayBot", url)

    async def retrieve(self, url: str, cancel: asyncio.Event) -> dict:
        if cancel.is_set():
            return {"ok": False, "cancelled": True, "url": url}
        if not await self.allowed(url):
            return {"ok": False, "error": "robots_disallowed", "url": url}
        if self.settings.web_page_delay_ms:
            await asyncio.sleep(self.settings.web_page_delay_ms / 1000)
            if cancel.is_set():
                return {"ok": False, "cancelled": True, "url": url}
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={"User-Agent": "FridayBot/0.1"}) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            return {"ok": False, "error": str(exc), "url": url}
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())[:6000]
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        return {"ok": True, "url": url, "title": title, "text": text}
