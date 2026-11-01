"""Deterministic tests for lesson state, prompts, timer, recorder and the planner payload (no model)."""

import asyncio
from types import SimpleNamespace

import pytest

from tutor.languages import LANGUAGES, get_language
from tutor.lesson import LessonState, LessonTimer, NextLessonResponse, ProgressEvent, StepResult, VocabularyItem
from tutor.planner import LessonRecorder
from tutor.prompt import TutorPrompt

from conftest import make_plan


class FakePlanner:
    """Records planner calls; can be told to fail."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple] = []

    async def complete_step(self, lesson_uuid, position, evidence):
        """Record or fail."""
        self.calls.append(("step", position, evidence))
        if self.fail:
            raise RuntimeError("planner down")

    async def finish_lesson(self, state):
        """Record or fail."""
        self.calls.append(("finish", state.outcome))
        if self.fail:
            raise RuntimeError("planner down")


class FakeRoom:
    """Collects the progress events the recorder publishes."""

    def __init__(self):
        self.events: list[ProgressEvent] = []
        self.local_participant = SimpleNamespace(publish_data=self.publish_data)

    async def publish_data(self, payload, reliable, topic):
        """Record the payload sent on the progress topic."""
        assert topic == "lesson-progress"
        self.events.append(ProgressEvent.model_validate_json(payload))


def result(evidence: str, *terms: str) -> StepResult:
    """A step result with the given new words."""
    return StepResult(evidence=evidence, new_vocabulary=[VocabularyItem(term=term, meaning="m") for term in terms])


def test_mark_step_done_is_idempotent_and_keeps_first_evidence(state):
    state.mark_step_done(1, result("Me llamo Marco"))
    state.mark_step_done(1, result("something else"))

    assert state.steps[0].done
    assert state.steps[0].evidence == "Me llamo Marco"
    assert [step.position for step in state.remaining()] == [2, 3, 4, 5]


def test_step_results_collect_new_vocabulary_once(state):
    state.mark_step_done(1, result("Me llamo Marco", "me llamo", "hola"))
    state.mark_step_done(2, result("Soy de Roma", "Hola", "soy de"))

    assert [item.term for item in state.new_vocabulary] == ["me llamo", "hola", "soy de"]


def test_unknown_step_raises(state):
    with pytest.raises(KeyError):
        state.mark_step_done(9, result("x"))


def test_finish_is_completed_only_when_every_step_is_done(state):
    [state.mark_step_done(step.position, result("ok")) for step in state.steps]

    assert state.finish()
    assert state.outcome == "completed"
    assert state.summary.startswith("Practised:")


def test_finish_with_steps_left_is_abandoned_and_recaps_what_is_left(state):
    state.mark_step_done(1, result("Me llamo Marco"))

    assert state.finish()
    assert state.outcome == "abandoned"
    assert "Say your name" in state.summary
    assert "Next time: Say where you are from" in state.summary


def test_finish_only_once(state):
    assert state.finish("left early")
    assert not state.finish("again")
    assert state.summary == "left early"


def test_progress_event_hides_the_coaching_prompts(state):
    payload = state.progress_event().model_dump_json()

    assert "Model the phrase" not in payload
    assert all(step.task in payload for step in state.steps)


async def test_timer_calls_time_up_once_the_lesson_is_nearly_over(monkeypatch):
    monkeypatch.setattr(LessonTimer, "TIME_UP_AT", 0.001)
    state = LessonState(plan=make_plan("es", duration_minutes=1))
    fired = asyncio.Event()

    LessonTimer(state, on_time_up=fired.set).start()

    await asyncio.wait_for(fired.wait(), timeout=1)


def test_next_lesson_response_dispatches_ids_and_shows_tasks_only():
    payload = {
        "lesson": {
            "lesson_uuid": "abc",
            "user_id": "u@x.com",
            "target_language": "fr",
            "title": "T",
            "duration": 10,
            "goal": {"aim": "A", "prompt": "secret goal prompt"},
            "opening_line": "Bonjour !",
            "steps": [{"position": 1, "task": "x", "prompt": "secret step prompt", "done": True, "evidence": "e"}],
        },
        "native_language": "Spanish",
        "level": "A2",
        "learning_method": None,
        "unit": {"title": "Unit"},
    }
    response = NextLessonResponse.model_validate(payload)

    dispatch = response.dispatch()
    assert (dispatch.lesson_uuid, dispatch.level, dispatch.native_language) == ("abc", "A2", "Spanish")
    view = response.view().model_dump_json()
    assert "secret" not in view
    assert response.view().steps[0].done


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_prompts_name_language_and_never_list_native_meanings(code):
    plan = make_plan(code)
    language = get_language(code)
    prompts = [TutorPrompt.agent(language, plan), *(TutorPrompt.step(language, plan, step) for step in plan.steps)]

    assert all(f"Speak ONLY {language.name}" in prompt for prompt in prompts)
    assert all(item.meaning not in prompt for prompt in prompts for item in plan.vocabulary)
    assert all(step.task in prompts[0] for step in plan.steps)


def test_step_prompt_carries_only_its_own_coaching():
    plan = make_plan("es")
    prompt = TutorPrompt.step(get_language("es"), plan, plan.steps[1])

    assert "Current step 2 of 5: Say where you are from" in prompt
    assert plan.steps[1].prompt in prompt
    assert plan.steps[0].prompt not in prompt
    assert plan.goal.prompt in prompt


def test_revisited_step_prompt_discounts_earlier_answers():
    plan = make_plan("es")
    language = get_language("es")

    assert "does not count" not in TutorPrompt.step(language, plan, plan.steps[0])
    assert "does not count" in TutorPrompt.step(language, plan, plan.steps[0], revisit=True)


def test_unsupported_language_is_rejected():
    with pytest.raises(ValueError):
        get_language("it")


async def test_recorder_resends_steps_then_outcome(state):
    planner, room = FakePlanner(), FakeRoom()
    recorder = LessonRecorder(state, planner, room)
    state.mark_step_done(2, result("Soy de Roma", "hola"))
    recorder.step_done(2)
    state.finish()
    await recorder.finished()

    assert planner.calls == [
        ("step", 2, "Soy de Roma"),
        ("step", 2, "Soy de Roma"),
        ("finish", "abandoned"),
    ]
    assert room.events[-1].outcome == "abandoned"
    assert room.events[-1].steps[1].done


async def test_recorder_swallows_planner_failures(state):
    room = FakeRoom()
    recorder = LessonRecorder(state, FakePlanner(fail=True), room)
    state.finish()
    await recorder.finished()

    assert room.events and room.events[-1].outcome == "abandoned"
