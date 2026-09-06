from __future__ import annotations

import os

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)

from livekit.plugins import google

from backend.app.config.settings import get_settings


settings = get_settings()

# LiveKit worker credentials
os.environ["LIVEKIT_URL"] = settings.livekit_url
os.environ["LIVEKIT_API_KEY"] = settings.livekit_api_key
os.environ["LIVEKIT_API_SECRET"] = settings.livekit_api_secret


class FridayAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are Friday, a personal AI voice assistant. "
                "Be intelligent, concise, natural, and conversational. "
                "Keep spoken responses short.\n\n"

                "LANGUAGE BEHAVIOR — THIS IS CRITICAL:\n"
                "Detect the language of the user's latest spoken message.\n"
                "Reply in EXACTLY the same language as that message.\n\n"

                "Examples:\n"
                "User speaks English -> reply in English.\n"
                "User speaks Hindi -> reply in Hindi.\n"
                "User speaks Telugu -> reply in Telugu.\n"
                "User speaks Tamil -> reply in Tamil.\n"
                "User speaks Malayalam -> reply in Malayalam.\n"
                "User speaks Kannada -> reply in Kannada.\n"
                "User speaks Punjabi -> reply in Punjabi.\n\n"

                "NEVER switch the response to Hindi automatically.\n"
                "NEVER switch the response to English automatically.\n"
                "Do not translate the user's language into another language.\n"
                "If the user changes language, immediately respond in the new language.\n"
                "For mixed-language speech, use the dominant language of the latest message."
            )
        )


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is required to run the Gemini voice agent."
        )

    session = AgentSession(
    llm=google.realtime.RealtimeModel(
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        api_key=settings.gemini_api_key,
        voice="Puck",
        temperature=0.7,
    ),

    # Start generating the response before the user's turn
    # is completely finalized.
    preemptive_generation=True,

    # Reduce the amount of silence required before
    # deciding that the user has finished speaking.
    min_endpointing_delay=0.3,
    max_endpointing_delay=1.0,

    # Keep interruption responsive.
    allow_interruptions=True,

    # Don't wait unnecessarily for multiple words before
    # processing an interruption.
    min_interruption_words=1,
)

    await session.start(
        room=ctx.room,
        agent=FridayAgent(),
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=settings.livekit_agent_name,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )