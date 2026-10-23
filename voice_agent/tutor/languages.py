"""Target languages and the Gradium voice used for each."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    """Speech settings for one target language."""

    code: str
    name: str
    native_name: str
    voice_id: str
    goodbye: str


LANGUAGES: dict[str, LanguageProfile] = {
    profile.code: profile
    for profile in [
        LanguageProfile("en", "English", "English", "4SZHfMpw-p46Ywgs", "Great job today. See you next time!"),
        LanguageProfile("es", "Spanish", "español", "iTQW2xFICXk8riV4", "¡Muy bien hoy! ¡Hasta la próxima!"),
        LanguageProfile("de", "German", "Deutsch", "aBNlTApBeOlVKa23", "Super gemacht heute! Bis zum nächsten Mal!"),
        LanguageProfile("fr", "French", "français", "YhIHaAfQ0cQPDV9R", "Très bien aujourd'hui ! À la prochaine !"),
    ]
}


def get_language(code: str) -> LanguageProfile:
    """Return the profile for a language code, raising for unsupported ones."""
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"Unsupported target language {code!r}; supported: {sorted(LANGUAGES)}")
