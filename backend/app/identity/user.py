from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt

from backend.app.config.settings import Settings


PBKDF_ITERATIONS = 120_000


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


@dataclass
class UserRecord:
    user_id: str
    email: str
    display_name: str
    password_hash: str
    created_at: str
    preferences: dict = field(default_factory=dict)
    permissions: list[str] = field(default_factory=lambda: ["web_search", "calendar_read", "tasks_read", "tasks_write"])
    connected_services: list[str] = field(default_factory=list)


class UserStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    permissions TEXT NOT NULL DEFAULT '[]',
                    connected_services TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.commit()

    def create_user(self, *, email: str, password: str, display_name: str) -> UserRecord:
        import json
        import uuid

        user = UserRecord(
            user_id=str(uuid.uuid4()),
            email=email.lower().strip(),
            display_name=display_name.strip() or email.split("@")[0],
            password_hash=_hash_password(password),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO users (user_id, email, display_name, password_hash, created_at, preferences, permissions, connected_services)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user.user_id,
                    user.email,
                    user.display_name,
                    user.password_hash,
                    user.created_at,
                    json.dumps(user.preferences),
                    json.dumps(user.permissions),
                    json.dumps(user.connected_services),
                ),
            )
            conn.commit()
        return user

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._fetch("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return self._fetch("SELECT * FROM users WHERE user_id = ?", (user_id,))

    def _fetch(self, sql: str, args: tuple) -> UserRecord | None:
        import json

        with self._lock, self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        if not row:
            return None
        return UserRecord(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            preferences=json.loads(row["preferences"] or "{}"),
            permissions=json.loads(row["permissions"] or "[]"),
            connected_services=json.loads(row["connected_services"] or "[]"),
        )

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        user = self.get_by_email(email)
        if not user or not _verify_password(password, user.password_hash):
            return None
        return user


def issue_app_token(settings: Settings, user: UserRecord) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "email": user.email,
        "name": user.display_name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
        "iss": "friday",
    }
    return jwt.encode(payload, settings.friday_jwt_secret, algorithm="HS256")


def decode_app_token(settings: Settings, token: str) -> dict:
    try:
        return jwt.decode(token, settings.friday_jwt_secret, algorithms=["HS256"], issuer="friday")
    except JWTError as exc:
        raise PermissionError("invalid or expired session") from exc
