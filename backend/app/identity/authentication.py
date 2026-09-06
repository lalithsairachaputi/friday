from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from backend.app.config.settings import Settings, get_settings
from backend.app.identity.user import UserRecord, UserStore, decode_app_token


_store: UserStore | None = None


def get_user_store(settings: Settings = Depends(get_settings)) -> UserStore:
    global _store
    if _store is None:
        _store = UserStore(settings.database_path)
    return _store


def reset_user_store_for_tests(store: UserStore | None = None) -> None:
    global _store
    _store = store


def extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    store: UserStore = Depends(get_user_store),
) -> UserRecord:
    token = extract_bearer(authorization)
    claims = decode_app_token(settings, token)
    user = store.get_by_id(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user
