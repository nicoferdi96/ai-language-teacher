"""Deterministic workflow tests: fake agents, real Postgres."""

from planner.models import (
    LearnerProfile,
    LearningPlan,
    LearningPlanDraft,
    LessonBriefDraft,
    LessonCompletion,
    LessonRecord,
    PlanUnitDraft,
    VocabularyItem,
)
from planner.workflow import LessonPlanningWorkflow
from planner.repository import ObjectiveNotFoundError

import pytest


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
    """Returns a brief for the plan's focus unit and records the history it saw."""

    def __init__(self):
        self.histories: list[list[LessonRecord]] = []

    async def design(
        self, profile: LearnerProfile, plan: LearningPlan, recent_lessons: list[LessonRecord]
    ) -> LessonBriefDraft:
        """Record the history and return a brief."""
        self.histories.append(recent_lessons)
        focus = plan.next_unit()
        return LessonBriefDraft(
            unit_position=focus.position,
            title=f"Lesson on {focus.title}",
            objectives=["Say hello", "Say your name", "Ask how someone is"],
            vocabulary=[VocabularyItem(term="hola", meaning="hello")],
            recap_terms=["gracias"] if recent_lessons else [],
            tutor_guidelines="Be warm.",
        )


@pytest.fixture
def fakes(repository):
    """Workflow wired to fake agents."""
    curriculum, lesson = FakeCurriculumAgent(), FakeLessonAgent()
    return LessonPlanningWorkflow(repository, curriculum, lesson), curriculum, lesson


async def finish_all(repository, package, status="completed"):
    """Tick every objective and close the lesson."""
    lesson_uuid = package.lesson.lesson_uuid
    [
        await repository.complete_objective(lesson_uuid, objective.id, "said it")
        for objective in package.lesson.objectives
    ]
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
    assert [o.id for o in package.lesson.objectives] == ["o1", "o2", "o3"]
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
    assert "gracias" in second.lesson.lesson_script
    plan = await repository.get_plan(user_id, "es")
    assert [unit.status for unit in plan.units][:2] == ["done", "in_progress"]


async def test_abandoned_lesson_keeps_unit_open(fakes, learners, repository):
    workflow, _, lesson_agent = fakes
    user_id = await learners.create()
    first = await workflow.run(user_id)
    await repository.complete_objective(first.lesson.lesson_uuid, "o1", "Hola!")

    await repository.finish_lesson(
        first.lesson.lesson_uuid, LessonCompletion(status="abandoned", summary="Had to leave")
    )
    second = await workflow.run(user_id)

    assert second.unit.position == 1
    history = lesson_agent.histories[-1][0]
    assert history.status == "abandoned"
    assert [o.done for o in history.objectives] == [True, False, False]


async def test_completed_with_unmet_objectives_does_not_close_unit(fakes, learners, repository):
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
    assert package.lesson.objectives


async def test_objective_updates_are_idempotent_and_validated(fakes, learners, repository):
    workflow, _, _ = fakes
    user_id = await learners.create()
    package = await workflow.run(user_id)
    lesson_uuid = package.lesson.lesson_uuid

    await repository.complete_objective(lesson_uuid, "o2", "first evidence")
    updated = await repository.complete_objective(lesson_uuid, "o2", "second evidence")

    assert updated.objectives[1].evidence == "first evidence"
    with pytest.raises(ObjectiveNotFoundError):
        await repository.complete_objective(lesson_uuid, "o99", "x")


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
