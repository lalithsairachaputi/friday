from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.config.languages import LANGUAGE_PROFILES, LanguageProfile, get_profile

try:
    from langdetect import detect_langs
except Exception:  # pragma: no cover
    detect_langs = None  # type: ignore[assignment]


TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
TAMIL_RANGE = re.compile(r"[\u0B80-\u0BFF]")
DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")

EXPLICIT_LANGUAGE_REQUESTS = [
    (re.compile(r"\b(in english|english please|speak english)\b", re.I), "en"),
    (re.compile(r"(हिंदी में|hindi mein|in hindi|हिन्दी में)", re.I), "hi"),
    (re.compile(r"(తెలుగులో|telugu lo|in telugu)", re.I), "te"),
    (re.compile(r"(தமிழில்|tamil la|in tamil)", re.I), "ta"),
    (re.compile(r"(telugu lo cheppu)", re.I), "te"),
]


@dataclass
class LanguageSpan:
    language: str
    start: int
    end: int


@dataclass
class LanguageDecision:
    detected_language: str
    language_confidence: float
    response_language: str
    code_switched: bool
    explicit_request: bool
    language_spans: list[LanguageSpan] = field(default_factory=list)
    switched: bool = False
    profile: LanguageProfile = field(default_factory=lambda: LANGUAGE_PROFILES["en"])


class LanguageRouter:
    """Hysteresis + explicit request + script detection. Never resets conversation."""

    def detect(self, text: str, current_language: str = "en") -> LanguageDecision:
        raw = text or ""
        explicit = self._explicit(raw)
        spans = self._script_spans(raw)
        script_lang, script_conf = self._from_scripts(raw)
        statistical_lang, statistical_conf = self._statistical(raw)

        detected = script_lang or statistical_lang or current_language
        confidence = script_conf if script_lang else statistical_conf
        if explicit:
            detected = explicit
            confidence = 1.0

        code_switched = len({s.language for s in spans} | ({"en"} if re.search(r"[A-Za-z]{3,}", raw) else set())) > 1

        if explicit:
            response = explicit
            switched = explicit != current_language
        elif confidence < 0.55:
            response = current_language
            switched = False
            detected = current_language
        elif detected != current_language and confidence >= 0.8:
            response = detected
            switched = True
        else:
            response = current_language
            switched = False

        profile = get_profile(response)
        return LanguageDecision(
            detected_language=detected,
            language_confidence=round(confidence, 3),
            response_language=response,
            code_switched=code_switched,
            explicit_request=bool(explicit),
            language_spans=spans,
            switched=switched,
            profile=profile,
        )

    def _explicit(self, text: str) -> str | None:
        for pattern, lang in EXPLICIT_LANGUAGE_REQUESTS:
            if pattern.search(text):
                return lang
        return None

    def _script_spans(self, text: str) -> list[LanguageSpan]:
        spans: list[LanguageSpan] = []
        for regex, lang in (
            (TELUGU_RANGE, "te"),
            (TAMIL_RANGE, "ta"),
            (DEVANAGARI_RANGE, "hi"),
        ):
            for match in regex.finditer(text):
                spans.append(LanguageSpan(language=lang, start=match.start(), end=match.end()))
        return spans

    def _from_scripts(self, text: str) -> tuple[str | None, float]:
        te = len(TELUGU_RANGE.findall(text))
        ta = len(TAMIL_RANGE.findall(text))
        hi = len(DEVANAGARI_RANGE.findall(text))
        total = te + ta + hi
        if total == 0:
            return None, 0.0
        winner, count = max((("te", te), ("ta", ta), ("hi", hi)), key=lambda x: x[1])
        return winner, min(1.0, 0.7 + count / max(total, 1) * 0.3)

    def _statistical(self, text: str) -> tuple[str | None, float]:
        cleaned = text.strip()
        if len(cleaned) < 8 or detect_langs is None:
            if re.search(r"[A-Za-z]{4,}", cleaned):
                return "en", 0.4
            return None, 0.0
        try:
            langs = detect_langs(cleaned)
        except Exception:
            return None, 0.0
        mapping = {"en": "en", "hi": "hi", "ta": "ta", "te": "te"}
        for item in langs:
            code = item.lang.split("-")[0]
            if code in mapping:
                return mapping[code], float(item.prob)
        return None, 0.0
