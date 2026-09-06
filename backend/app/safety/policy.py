from __future__ import annotations

from enum import StrEnum


class ToolSafetyClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"


def requires_confirmation(safety: ToolSafetyClass) -> bool:
    return safety == ToolSafetyClass.IRREVERSIBLE_WRITE
