from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config.settings import get_settings


settings = get_settings()

app = FastAPI(
    title="Friday Voice Backend",
    version="0.1.0",
    description="Multilingual agentic voice assistant backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "friday-voice-backend",
        "environment": settings.friday_env,
    }


@app.get("/")
async def root() -> dict:
    return {
        "name": "Friday Voice Backend",
        "status": "running",
    }