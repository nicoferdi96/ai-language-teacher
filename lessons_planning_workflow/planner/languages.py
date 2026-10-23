"""Target languages the platform teaches (all backed by Gradium STT/TTS)."""

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
}

DEFAULT_TARGET_LANGUAGE = "es"


def language_name(code: str) -> str:
    """Return the English display name for a language code, or the code itself."""
    return SUPPORTED_LANGUAGES.get(code, code)
