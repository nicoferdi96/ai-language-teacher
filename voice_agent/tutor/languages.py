"""Target languages and the Gradium voice used for each."""

from pydantic import BaseModel, ConfigDict


class LanguageProfile(BaseModel):
    """Speech settings for one target language."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    native_name: str
    voice_id: str
    goodbye: str


LANGUAGES: dict[str, LanguageProfile] = {
    profile.code: profile
    for profile in [
        LanguageProfile(
            code="en",
            name="English",
            native_name="English",
            voice_id="4SZHfMpw-p46Ywgs",
            goodbye="Great job today. See you next time!",
        ),
        LanguageProfile(
            code="es",
            name="Spanish",
            native_name="español",
            voice_id="iTQW2xFICXk8riV4",
            goodbye="¡Muy bien hoy! ¡Hasta la próxima!",
        ),
        LanguageProfile(
            code="de",
            name="German",
            native_name="Deutsch",
            voice_id="aBNlTApBeOlVKa23",
            goodbye="Super gemacht heute! Bis zum nächsten Mal!",
        ),
        LanguageProfile(
            code="fr",
            name="French",
            native_name="français",
            voice_id="YhIHaAfQ0cQPDV9R",
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
