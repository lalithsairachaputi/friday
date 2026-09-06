"""LiveKit helpers: token minting and identity encoding.

The realtime conversation runs in a LiveKit room. REST is only used for
health, config, metrics, and short-lived session tokens.
"""

from __future__ import annotations

import json
from datetime import timedelta

from backend.app.config.settings import Settings


class LiveKitNotConfiguredError(RuntimeError):
    pass


def encode_participant_identity(user_id: str, conversation_id: str) -> str:
    return f"user:{user_id}:conv:{conversation_id}"


def decode_participant_identity(identity: str) -> tuple[str, str]:
    parts = identity.split(":")
    if len(parts) >= 4 and parts[0] == "user" and parts[2] == "conv":
        return parts[1], parts[3]
    raise ValueError("identity is not a Friday authenticated participant")


def mint_livekit_token(
    settings: Settings,
    *,
    user_id: str,
    conversation_id: str,
    display_name: str,
) -> tuple[str, str]:
    if not settings.livekit_api_key or not settings.livekit_api_secret or not settings.livekit_url:
        raise LiveKitNotConfiguredError("LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are required")
    from livekit import api

    room = f"friday-{conversation_id}"
    identity = encode_participant_identity(user_id, conversation_id)
    metadata = json.dumps(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "source": "friday-session-token",
        }
    )
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_metadata(metadata)
        .with_ttl(timedelta(hours=2))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=settings.livekit_agent_name,
                        metadata=metadata,
                    )
                ]
            )
        )
        .to_jwt()
    )
    return token, room
