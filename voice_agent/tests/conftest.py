import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from tutor.lesson import LessonPlan, LessonState  # noqa: E402


def steps(*tasks: str) -> list[dict]:
    """Return numbered steps whose prompt asks the tutor to get the learner to do the task."""
    return [
        {"position": position, "task": task, "prompt": f"Model the phrase, then ask the learner to: {task}."}
        for position, task in enumerate(tasks, start=1)
    ]


LESSONS = {
    "es": dict(
        title="Hello and introductions",
        unit_title="Meeting people",
        opening_line="¡Hola! Soy Lumi. Hoy aprendemos a presentarnos. ¿Cómo te llamas?",
        steps=steps(
            "Say your name with 'Me llamo...'",
            "Say where you are from with 'Soy de...'",
            "Ask someone how they are with '¿Cómo estás?'",
            "Introduce yourself to a new neighbour in a short role-play",
            "Recap: say your name, where you are from, and ask how someone is",
        ),
        vocabulary=[{"term": "me llamo", "meaning": "mi chiamo"}, {"term": "soy de", "meaning": "sono di"}],
    ),
    "de": dict(
        title="Ordering at a café",
        unit_title="Café and food",
        opening_line="Hallo! Ich bin Lumi. Heute bestellen wir im Café. Trinkst du gern Kaffee?",
        steps=steps("Order a drink with 'Ich hätte gern...'", "Ask for the bill with 'Die Rechnung, bitte'"),
        vocabulary=[{"term": "ich hätte gern", "meaning": "I would like"}],
    ),
    "fr": dict(
        title="Talking about your weekend",
        unit_title="Past events",
        opening_line="Bonjour ! Je suis Lumi. Aujourd'hui, on parle du week-end. Tu as passé un bon week-end ?",
        steps=steps(
            "Say one thing you did with the passé composé, e.g. 'J'ai mangé...'",
            "Ask 'Qu'est-ce que tu as fait ce week-end ?'",
        ),
        vocabulary=[{"term": "le week-end", "meaning": "el fin de semana"}],
    ),
    "en": dict(
        title="Directions in the city",
        unit_title="Getting around",
        opening_line="Hi! I'm Lumi. Today we learn to ask for directions. Do you live in a big city?",
        steps=steps("Ask 'Where is the station?'", "Understand and repeat 'turn left / turn right'"),
        vocabulary=[{"term": "turn left", "meaning": "links abbiegen"}],
    ),
}
NATIVE = {"es": "Italian", "de": "English", "fr": "Spanish", "en": "German"}


def make_plan(language: str = "es", **overrides) -> LessonPlan:
    """Return a lesson plan for the given target language."""
    return LessonPlan(
        lesson_uuid="00000000-0000-0000-0000-000000000001",
        user_id="learner@example.com",
        target_language=language,
        native_language=NATIVE[language],
        level="A1",
        learning_method="Lots of conversation, a total beginner",
        goal={
            "aim": "Introduce yourself and talk to someone new",
            "prompt": "Warm up with a personal question, model each phrase, then a short role-play.",
        },
        **{**LESSONS[language], **overrides},
    )


@pytest.fixture
def state() -> LessonState:
    """Fresh Spanish lesson state."""
    return LessonState(plan=make_plan("es"))


def pytest_collection_modifyitems(config, items):
    """Skip live LLM tests unless RUN_LIVE=1."""
    if os.getenv("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE=1 to call Anthropic")
    [item.add_marker(skip) for item in items if "live" in item.keywords]
