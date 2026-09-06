from __future__ import annotations

from enum import StrEnum


class ToolPermission(StrEnum):
    WEB_SEARCH = "web_search"
    CALENDAR_READ = "calendar_read"
    CALENDAR_WRITE = "calendar_write"
    TASKS_READ = "tasks_read"
    TASKS_WRITE = "tasks_write"
    EMAIL_READ = "email_read"
    FILES_READ = "files_read"


def has_permission(permissions: list[str], required: str) -> bool:
    return required in permissions
