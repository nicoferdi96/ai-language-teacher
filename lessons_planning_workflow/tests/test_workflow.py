"""Deterministic workflow tests: fake agents, real Postgres."""

import pytest
from pydantic import ValidationError

from planner.models import (
    STEPS_PER_LESSON,
    LearnerProfile,
    LearningPlan,
    LearningPlanDraft,
    LessonCompletion,
    LessonGoal,
    LessonPlanDraft,
    LessonRecord,
    LessonStepDraft,
    PlanUnitDraft,
    VocabularyItem,
)
from planner.repository import StepNotFoundError
from planner.workflow import LessonPlanningWorkflow

STEP_TASKS = ["Say hello", "Say your name", "Say where you are from", "Ask how someone is", "Recap"]


def make_draft(unit_position: int = 1, steps: int = STEPS_PER_LESSON, recap: list[str] | None = None) -> LessonPlanDraft:
    """Return a lesson plan with ``steps`` steps."""
    return LessonPlanDraft(
        unit_position=unit_position,
        title="Lesson",
        goal=LessonGoal(aim="Introduce yourself", prompt="Be warm."),
        opening_line="¡Hola! ¿Cómo estás?",
        steps=[LessonStepDraft(task=f"Task {index}", prompt=f"Prompt {index}") for index in range(1, steps + 1)],
        vocabulary=[VocabularyItem(term="hola", meaning="hello")],
        recap_terms=recap or [],
    )


class FakeCurriculumAgent:
    """Returns a fixed three-unit plan and counts calls."""

    def __init__(self):
        self.calls: list[LearnerProfile] = []

    async def design(self, profile: LearnerProfile) -> LearningPlanDraft:
        """Record the call and return the plan."""
        self.calls.append(profile)
        return LearningPlanDraft(
            level="A1",
            goal_summary="Test goal",
            units=[
                PlanUnitDraft(title=f"Unit {index}", kind="conversation", description="d")
                for index in range(1, 5)
            ],
        )


class FakeLessonAgent:
    """Returns a plan for the focus unit and records the history it saw."""

    def __init__(self):
        self.histories: list[list[LessonRecord]] = []

    async def design(
        self, profile: LearnerProfile, plan: LearningPlan, recent_lessons: list[LessonRecord]
    ) -> LessonPlanDraft:
        """Record the history and return a plan."""
        self.histories.append(recent_lessons)
        focus = plan.next_unit()
        return make_draft(focus.position, recap=["gracias"] if recent_lessons else []).model_copy(
            update={
                "title": f"Lesson on {focus.title}",
                "steps": [LessonStepDraft(task=task, prompt=f"Coach: {task}") for task in STEP_TASKS],
            }
        )


@pytest.fixture
def fakes(repository):
    """Workflow wired to fake agents."""
    curriculum, lesson = FakeCurriculumAgent(), FakeLessonAgent()
    return LessonPlanningWorkflow(repository, curriculum, lesson), curriculum, lesson


async def finish_all(repository, package, status="completed"):
    """Tick every step and close the lesson."""
    lesson_uuid = package.lesson.lesson_uuid
    [await repository.complete_step(lesson_uuid, step.position, "said it") for step in package.lesson.steps]
    await repository.finish_lesson(
        lesson_uuid,
        LessonCompletion(
            status=status,
            summary="Went well",
            new_vocabulary=[VocabularyItem(term="gracias", meaning="thanks")],
        ),
    )


async def test_new_learner_gets_plan_and_first_lesson(fakes, learners, repository):
    workflow, curriculum, _ = fakes
    user_id = await learners.create(target="de", native="Italian")

    package = await workflow.run(user_id)

    assert len(curriculum.calls) == 1
    assert curriculum.calls[0].target_language == "de"
    assert package.lesson.target_language == "de"
    assert package.native_language == "Italian"
    assert [(step.position, step.task) for step in package.lesson.steps] == list(enumerate(STEP_TASKS, start=1))
    assert package.lesson.opening_line
    stored = await repository.get_lesson(package.lesson.lesson_uuid)
    assert [step.prompt for step in stored.steps] == [f"Coach: {task}" for task in STEP_TASKS]
    assert stored.goal == package.lesson.goal
    assert package.unit.position == 1
    plan = await repository.get_plan(user_id, "de")
    assert plan.units[0].status == "in_progress"


async def test_open_lesson_is_reused_not_regenerated(fakes, learners):
    workflow, curriculum, lesson_agent = fakes
    user_id = await learners.create()

    first = await workflow.run(user_id)
    second = await workflow.run(user_id)

    assert first.lesson.lesson_uuid == second.lesson.lesson_uuid
    assert len(curriculum.calls) == 1
    assert len(lesson_agent.histories) == 1


async def test_completed_lesson_advances_to_next_unit(fakes, learners, repository):
    workflow, curriculum, lesson_agent = fakes
    user_id = await learners.create()
    first = await workflow.run(user_id)

    await finish_all(repository, first)
    second = await workflow.run(user_id)

    assert second.lesson.lesson_uuid != first.lesson.lesson_uuid
    assert second.unit.position == 2
    assert len(curriculum.calls) == 1
    assert lesson_agent.histories[-1][0].status == "completed"
    assert "gracias" in second.lesson.goal.prompt
    plan = await repository.get_plan(user_id, "es")
    assert [unit.status for unit in plan.units][:2] == ["done", "in_progress"]


async def test_abandoned_lesson_keeps_unit_open(fakes, learners, repository):
    workflow, _, lesson_agent = fakes
    user_id = await learners.create()
    first = await workflow.run(user_id)
    await repository.complete_step(first.lesson.lesson_uuid, 1, "Hola!")

    await repository.finish_lesson(
        first.lesson.lesson_uuid, LessonCompletion(status="abandoned", summary="Had to leave")
    )
    second = await workflow.run(user_id)

    assert second.unit.position == 1
    history = lesson_agent.histories[-1][0]
    assert history.status == "abandoned"
    assert [step.done for step in history.steps] == [True, False, False, False, False]


async def test_completed_with_unmet_steps_does_not_close_unit(fakes, learners, repository):
    workflow, _, _ = fakes
    user_id = await learners.create()
    first = await workflow.run(user_id)

    await repository.finish_lesson(first.lesson.lesson_uuid, LessonCompletion(status="completed"))

    plan = await repository.get_plan(user_id, "es")
    assert plan.units[0].status == "in_progress"


async def test_missing_answers_fall_back_to_defaults(fakes, learners):
    workflow, curriculum, _ = fakes
    user_id = await learners.create(target=None, native=None, method=None)

    package = await workflow.run(user_id)

    assert curriculum.calls[0].target_language == "es"
    assert curriculum.calls[0].native_language == "English"
    assert len(package.lesson.steps) == STEPS_PER_LESSON


async def test_step_updates_are_idempotent_and_validated(fakes, learners, repository):
    workflow, _, _ = fakes
    user_id = await learners.create()
    package = await workflow.run(user_id)
    lesson_uuid = package.lesson.lesson_uuid

    await repository.complete_step(lesson_uuid, 2, "first evidence")
    updated = await repository.complete_step(lesson_uuid, 2, "second evidence")

    assert updated.steps[1].done
    assert updated.steps[1].evidence == "first evidence"
    assert not updated.steps[0].done
    with pytest.raises(StepNotFoundError):
        await repository.complete_step(lesson_uuid, 9, "x")


@pytest.mark.parametrize("steps", [STEPS_PER_LESSON - 1, STEPS_PER_LESSON + 1])
def test_lesson_plan_requires_exactly_five_steps(steps):
    with pytest.raises(ValidationError):
        make_draft(steps=steps)


async def test_switching_language_builds_a_separate_plan(fakes, learners, repository):
    workflow, curriculum, _ = fakes
    user_id = await learners.create(target="fr")
    await workflow.run(user_id)

    async with repository._connect() as conn:
        await conn.execute(
            "UPDATE answers SET answer = 'en' WHERE user_id = %s AND question_id = 1", (user_id,)
        )
    package = await workflow.run(user_id)

    assert package.lesson.target_language == "en"
    assert [call.target_language for call in curriculum.calls] == ["fr", "en"]
