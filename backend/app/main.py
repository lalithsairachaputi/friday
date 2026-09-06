from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config.settings import get_settings
from backend.app.realtime.livekit import mint_livekit_token


settings = get_settings()

app = FastAPI(
    title="Friday Voice Backend",
    version="0.1.0",
    description="Multilingual agentic voice assistant backend",
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------
# Development frontend is running on port 5500.
# Keep this explicit so a malformed .env value cannot break
# the browser preflight request.
DEV_CORS_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "friday-voice-backend",
        "environment": settings.friday_env,
    }


# ---------------------------------------------------------
# Root
# ---------------------------------------------------------
@app.get("/")
async def root() -> dict:
    return {
        "name": "Friday Voice Backend",
        "status": "running",
    }


# ---------------------------------------------------------
# LiveKit voice session
# ---------------------------------------------------------
@app.post("/api/voice/session")
async def create_voice_session(payload: dict) -> dict:
    user_id = payload.get("user_id", "local-user")
    conversation_id = payload.get("conversation_id", "main")
    display_name = payload.get("display_name", "User")

    token, room = mint_livekit_token(
        settings,
        user_id=user_id,
        conversation_id=conversation_id,
        display_name=display_name,
    )

    return {
        "token": token,
        "room": room,
        "livekit_url": settings.livekit_url,
    }