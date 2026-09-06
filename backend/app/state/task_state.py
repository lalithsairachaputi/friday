from __future__ import annotations

from enum import StrEnum


class BrowseStatus(StrEnum):
    CREATED = "CREATED"
    SEARCHING = "SEARCHING"
    READING = "READING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    STALE = "STALE"
