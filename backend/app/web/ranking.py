from __future__ import annotations

from urllib.parse import urlparse

from backend.app.web.source import SourceType, WebSource, classify_source


def rank_sources(sources: list[WebSource]) -> list[WebSource]:
    weight = {
        SourceType.GOVERNMENT: 1.0,
        SourceType.OFFICIAL: 0.95,
        SourceType.DOCUMENTATION: 0.9,
        SourceType.RESEARCH: 0.85,
        SourceType.COMPANY: 0.8,
        SourceType.NEWS: 0.7,
        SourceType.OTHER: 0.4,
    }
    seen: set[str] = set()
    unique: list[WebSource] = []
    for src in sources:
        key = f"{src.domain}:{src.title.lower()}"
        if key in seen:
            continue
        seen.add(key)
        src.relevance = min(1.0, src.relevance * weight.get(src.source_type, 0.4))
        unique.append(src)
    return sorted(unique, key=lambda s: s.relevance, reverse=True)


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def to_source(hit: dict, generation_id: int, relevance: float) -> WebSource:
    url = hit.get("href") or hit.get("url") or ""
    title = hit.get("title") or url
    domain = domain_of(url)
    return WebSource(
        title=title,
        url=url,
        domain=domain,
        source_type=classify_source(url, title),
        published_at=hit.get("published_at"),
        retrieved_at=hit.get("retrieved_at") or "",
        relevance=relevance,
        generation_id=generation_id,
        snippet=hit.get("body") or hit.get("snippet") or "",
    )
