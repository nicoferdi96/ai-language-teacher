import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from tutor.lesson import LessonPackage, LessonState  # noqa: E402

LESSONS = {
    "es": dict(
        title="Hello and introductions",
        unit_title="Meeting people",
        objectives=[
            {"id": "o1", "text": "Say your name with 'Me llamo...'"},
            {"id": "o2", "text": "Say where you are from with 'Soy de...'"},
            {"id": "o3", "text": "Ask someone how they are with '¿Cómo estás?'"},
        ],
        vocabulary=[{"term": "me llamo", "meaning": "mi chiamo"}, {"term": "soy de", "meaning": "sono di"}],
    ),
    "de": dict(
        title="Ordering at a café",
        unit_title="Café and food",
        objectives=[
            {"id": "o1", "text": "Order a drink with 'Ich hätte gern...'"},
            {"id": "o2", "text": "Ask for the bill with 'Die Rechnung, bitte'"},
        ],
        vocabulary=[{"term": "ich hätte gern", "meaning": "I would like"}],
    ),
    "fr": dict(
        title="Talking about your weekend",
        unit_title="Past events",
        objectives=[
            {"id": "o1", "text": "Say one thing you did with the passé composé, e.g. 'J'ai mangé...'"},
            {"id": "o2", "text": "Ask 'Qu est-ce que tu as fait ce week-end ?'"},
        ],
        vocabulary=[{"term": "le week-end", "meaning": "el fin de semana"}],
    ),
    "en": dict(
        title="Directions in the city",
        unit_title="Getting around",
        objectives=[
            {"id": "o1", "text": "Ask 'Where is the station?'"},
            {"id": "o2", "text": "Understand and repeat 'turn left / turn right'"},
        ],
        vocabulary=[{"term": "turn left", "meaning": "links abbiegen"}],
    ),
}
NATIVE = {"es": "Italian", "de": "English", "fr": "Spanish", "en": "German"}


def make_package(language: str = "es", **overrides) -> LessonPackage:
    """Return a lesson package for the given target language."""
    return LessonPackage(
        lesson_uuid="00000000-0000-0000-0000-000000000001",
        user_id="learner@example.com",
        target_language=language,
        native_language=NATIVE[language],
        level="A1",
        learning_method="Lots of conversation, a total beginner",
        guidelines="Warm up with a personal question, model each phrase, then a short role-play.",
        **{**LESSONS[language], **overrides},
    )


@pytest.fixture
def state() -> LessonState:
    """Fresh Spanish lesson state."""
    return LessonState(package=make_package("es"))


def pytest_collection_modifyitems(config, items):
    """Skip live LLM tests unless RUN_LIVE=1."""
    if os.getenv("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE=1 to call OpenRouter")
    [item.add_marker(skip) for item in items if "live" in item.keywords]
