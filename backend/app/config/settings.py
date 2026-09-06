from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    friday_jwt_secret: str = "dev-only-change-me"
    friday_env: str = "development"
    friday_host: str = "0.0.0.0"
    friday_port: int = 8080
    friday_public_url: str = "http://localhost:8080"
    friday_cors_origins: str = (
        "http://localhost:8080,http://127.0.0.1:8080"
    )
    friday_database_path: str = "./data/friday.db"

    # ------------------------------------------------------------------
    # LiveKit
    # ------------------------------------------------------------------

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "friday-voice"

    # ------------------------------------------------------------------
    # Rime TTS
    # ------------------------------------------------------------------

    rime_api_key: str = ""
    rime_ws_url: str = "wss://users-ws.rime.ai"
    rime_http_url: str = "https://users.rime.ai/v1/rime-tts"

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-2.5-flash"

    # ------------------------------------------------------------------
    # Speech-to-Text
    # ------------------------------------------------------------------

    openai_stt_model: str = "gpt-4o-mini-transcribe"

    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-3"

    # ------------------------------------------------------------------
    # Web Search
    # ------------------------------------------------------------------

    tavily_api_key: str = ""
    brave_search_api_key: str = ""
    web_search_api_key: str = ""

    # ------------------------------------------------------------------
    # Fallback TTS
    # Telugu and Tamil currently use Edge TTS
    # ------------------------------------------------------------------

    fallback_tts_provider: str = "edge"

    # ------------------------------------------------------------------
    # Stress / testing delays
    # 0 = disabled
    # ------------------------------------------------------------------

    tool_delay_ms: int = 0
    web_search_delay_ms: int = 0
    web_page_delay_ms: int = 0
    llm_delay_ms: int = 0
    tts_delay_ms: int = 0
    interruption_delay_ms: int = 0

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------

    jwt_ttl_seconds: int = 60 * 60 * 12

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.friday_cors_origins.split(",")
            if item.strip()
        ]

    @property
    def database_path(self) -> Path:
        return Path(self.friday_database_path).resolve()

    def stress_flags(self) -> dict[str, int]:
        return {
            "TOOL_DELAY_MS": self.tool_delay_ms,
            "WEB_SEARCH_DELAY_MS": self.web_search_delay_ms,
            "WEB_PAGE_DELAY_MS": self.web_page_delay_ms,
            "LLM_DELAY_MS": self.llm_delay_ms,
            "TTS_DELAY_MS": self.tts_delay_ms,
            "INTERRUPTION_DELAY_MS": self.interruption_delay_ms,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


def stress_mode_active(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return any(value > 0 for value in s.stress_flags().values())