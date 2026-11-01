"""Target languages the tutor speaks (one Cartesia voice serves all; see ``settings.tts_voice``)."""

from pydantic import BaseModel, ConfigDict


class LanguageProfile(BaseModel):
    """Speech settings for one target language."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    native_name: str
    goodbye: str


LANGUAGES: dict[str, LanguageProfile] = {
    profile.code: profile
    for profile in [
        LanguageProfile(
            code="en",
            name="English",
            native_name="English",
            goodbye="Great job today. See you next time!",
        ),
        LanguageProfile(
            code="es",
            name="Spanish",
            native_name="español",
            goodbye="¡Muy bien hoy! ¡Hasta la próxima!",
        ),
        LanguageProfile(
            code="de",
            name="German",
            native_name="Deutsch",
            goodbye="Super gemacht heute! Bis zum nächsten Mal!",
        ),
        LanguageProfile(
            code="fr",
            name="French",
            native_name="français",
            goodbye="Très bien aujourd'hui ! À la prochaine !",
        ),
    ]
}


def get_language(code: str) -> LanguageProfile:
    """Return the profile for a language code, raising for unsupported ones."""
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"Unsupported target language {code!r}; supported: {sorted(LANGUAGES)}")
