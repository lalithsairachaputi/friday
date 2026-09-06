from __future__ import annotations

from backend.app.config.languages import LanguageProfile, get_profile
from backend.app.voice.rime import VoiceOutputService


class ProviderManager:
    def __init__(self, voice: VoiceOutputService) -> None:
        self.voice = voice

    def describe(self, language_code: str) -> dict:
        profile: LanguageProfile = get_profile(language_code)
        backend, provider, reason = self.voice.get_provider(profile)
        return {
            "language": profile.language_code,
            "language_name": profile.language_name,
            "active_tts_provider": provider,
            "rime_model": profile.rime_model,
            "rime_speaker": profile.rime_speaker,
            "rime_language": profile.rime_language,
            "transport": profile.transport,
            "audio_format": profile.audio_format,
            "fallback_reason": reason,
            "enabled": profile.enabled,
            "backend": backend.name,
        }
