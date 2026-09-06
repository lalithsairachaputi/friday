from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class SourceType(StrEnum):
    OFFICIAL = "official"
    GOVERNMENT = "government"
    DOCUMENTATION = "documentation"
    NEWS = "news"
    RESEARCH = "research"
    COMPANY = "company"
    OTHER = "other"


OFFICIAL_HINTS = (
    ".gov",
    ".gov.in",
    "wikipedia.org",
    "docs.",
    "developer.",
    "nvidia.com",
    "apple.com",
    "microsoft.com",
    "openai.com",
)


@dataclass
class WebSource:
    title: str
    url: str
    domain: str
    source_type: SourceType
    published_at: str | None
    retrieved_at: str
    relevance: float
    generation_id: int
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "source_type": self.source_type.value,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "relevance": self.relevance,
            "generation_id": self.generation_id,
            "snippet": self.snippet,
        }


def classify_source(url: str, title: str = "") -> SourceType:
    u = url.lower()
    if ".gov" in u:
        return SourceType.GOVERNMENT
    if "docs." in u or "developer." in u or "documentation" in u:
        return SourceType.DOCUMENTATION
    if any(h in u for h in OFFICIAL_HINTS):
        return SourceType.OFFICIAL
    if any(n in u for n in ("bbc.", "reuters.", "nytimes.", "thehindu.", "indianexpress.")):
        return SourceType.NEWS
    if "arxiv.org" in u:
        return SourceType.RESEARCH
    return SourceType.OTHER


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
