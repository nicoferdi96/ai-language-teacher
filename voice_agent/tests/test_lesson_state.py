"""Deterministic tests for lesson state, prompt and recorder (no model)."""

import pytest

from tutor.agent import LessonRecorder
from tutor.languages import LANGUAGES, get_language
from tutor.lesson import LessonPackage, LessonState, NextLessonResponse, VocabularyItem
from tutor.prompt import TutorPrompt

from conftest import make_package


class FakePlanner:
    """Records planner calls; can be told to fail."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple] = []

    async def complete_objective(self, lesson_uuid, objective_id, evidence):
        """Record or fail."""
        self.calls.append(("objective", objective_id, evidence))
        if self.fail:
            raise RuntimeError("planner down")

    async def finish_lesson(self, state):
        """Record or fail."""
        self.calls.append(("finish", state.outcome))
        if self.fail:
            raise RuntimeError("planner down")


def test_mark_done_is_idempotent_and_keeps_first_evidence(state):
    state.mark_done("o1", "Me llamo Marco")
    state.mark_done("o1", "something else")

    assert state.objectives[0].done
    assert state.objectives[0].evidence == "Me llamo Marco"
    assert [o.id for o in state.remaining()] == ["o2", "o3"]


def test_unknown_objective_raises(state):
    with pytest.raises(KeyError):
        state.mark_done("o9", "x")


def test_cannot_complete_early_with_objectives_left(state):
    assert not state.can_complete()


def test_can_complete_when_all_done(state):
    [state.mark_done(o.id, "ok") for o in state.objectives]
    assert state.can_complete()


def test_can_complete_when_time_is_up(state):
    state.started_at -= 9 * 60
    assert state.can_complete()


def test_finish_only_once(state):
    assert state.finish("abandoned", "left", [])
    assert not state.finish("completed", "again", [])
    assert state.outcome == "abandoned"


def test_package_from_planner_payload():
    payload = {
        "lesson": {
            "lesson_uuid": "abc",
            "user_id": "u@x.com",
            "target_language": "fr",
            "title": "T",
            "lesson_script": "G",
            "duration": 10,
            "objectives": [{"id": "o1", "text": "x", "done": True, "evidence": "e"}],
            "vocabulary": [{"term": "a", "meaning": "b"}],
        },
        "native_language": "Spanish",
        "level": "A2",
        "learning_method": None,
        "unit": {"title": "Unit"},
    }
    package = LessonPackage.from_planner(NextLessonResponse.model_validate(payload))

    assert package.unit_title == "Unit"
    assert package.objectives[0].done


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_prompt_names_language_and_never_lists_native_meanings(code):
    package = make_package(code)
    prompt = TutorPrompt.build(get_language(code), package)

    assert f"Speak ONLY {get_language(code).name}" in prompt
    assert all(item.meaning not in prompt for item in package.vocabulary)
    assert all(o.id in prompt for o in package.objectives)


def test_unsupported_language_is_rejected():
    with pytest.raises(ValueError):
        get_language("it")


async def test_recorder_resends_objectives_then_outcome(state):
    planner, events = FakePlanner(), []

    async def publish(event):
        events.append(event)

    recorder = LessonRecorder(state, planner, publish)
    state.mark_done("o2", "Soy de Roma")
    recorder.objective_done("o2", "Soy de Roma")
    state.finish("abandoned", "left", [VocabularyItem(term="hola", meaning="ciao")])
    await recorder.finished()

    assert planner.calls == [
        ("objective", "o2", "Soy de Roma"),
        ("objective", "o2", "Soy de Roma"),
        ("finish", "abandoned"),
    ]
    assert events[-1].outcome == "abandoned"


async def test_recorder_swallows_planner_failures(state):
    events = []

    async def publish(event):
        events.append(event)

    recorder = LessonRecorder(state, FakePlanner(fail=True), publish)
    state.finish("completed", "ok", [])
    await recorder.finished()

    assert events and events[-1].outcome == "completed"
