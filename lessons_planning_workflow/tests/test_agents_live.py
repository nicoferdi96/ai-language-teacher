"""Live persona tests: real OpenRouter agents, judged by an LLM where needed."""

import json
import os

import pytest
from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from pydantic import BaseModel

from planner.models import LessonCompletion, VocabularyItem
from planner.workflow import LessonPlanningWorkflow

pytestmark = pytest.mark.live

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4.1-mini")


class Verdict(BaseModel):
    """Judge output; the reason comes first so the verdict follows the reasoning."""

    reason: str
    passed: bool


class Judge:
    """Asks an LLM whether a planner output satisfies an expectation."""

    def __init__(self):
        self.agent = Agent(
            model=OpenRouter(id=JUDGE_MODEL),
            instructions="You grade outputs of a lesson planner. Be strict but fair. "
            "Answer whether the OUTPUT satisfies the EXPECTATION.",
            output_schema=Verdict,
        )

    async def check(self, expectation: str, output: object) -> Verdict:
        """Return the verdict for one expectation."""
        response = await self.agent.arun(
            f"EXPECTATION: {expectation}\n\nOUTPUT:\n{json.dumps(output, ensure_ascii=False, default=str)}"
        )
        return Verdict.model_validate(response.content)


@pytest.fixture
def workflow(repository):
    """Workflow with the real Agno agents."""
    return LessonPlanningWorkflow(repository)


@pytest.fixture
def judge():
    """LLM judge."""
    return Judge()


async def test_beginner_conversation_spanish_native_italian(workflow, learners, judge):
    user_id = await learners.create(
        "es", "Italian", "Lots of conversation about travel and food, I'm a total beginner"
    )
    package = await workflow.run(user_id)
    plan = await workflow.repository.get_plan(user_id, "es")

    assert plan.level == "A1"
    assert 8 <= len(plan.units) <= 12
    assert sum(unit.kind == "conversation" for unit in plan.units) >= len(plan.units) // 2
    assert 3 <= len(package.lesson.objectives) <= 5
    verdict = await judge.check(
        "Every 'meaning' is written in Italian (not English), and every 'term' is Spanish.",
        [item.model_dump() for item in package.lesson.vocabulary],
    )
    assert verdict.passed, verdict.reason
    verdict = await judge.check(
        "The title and every objective are written in English (they may quote Spanish phrases), "
        "not in Italian.",
        {"title": package.lesson.title, "objectives": [o.text for o in package.lesson.objectives]},
    )
    assert verdict.passed, verdict.reason


async def test_grammar_first_german_native_english(workflow, learners):
    user_id = await learners.create(
        "de", "English", "I like structure: grammar rules first, then practice. Beginner."
    )
    await workflow.run(user_id)
    plan = await workflow.repository.get_plan(user_id, "de")

    assert sum(unit.kind == "grammar" for unit in plan.units) >= 3


async def test_prior_knowledge_french_not_a1(workflow, learners, judge):
    user_id = await learners.create(
        "fr",
        "Spanish",
        "I studied French for 4 years at school and can hold simple conversations, "
        "but I want to sound natural at work meetings.",
    )
    package = await workflow.run(user_id)
    plan = await workflow.repository.get_plan(user_id, "fr")

    assert plan.level not in ("A1",)
    verdict = await judge.check(
        "The plan is pitched above absolute-beginner level (A2 or higher) and is built around "
        "work/professional situations.",
        plan.model_dump(include={"level", "goal_summary", "units"}),
    )
    assert verdict.passed, verdict.reason
    assert package.lesson.objectives


async def test_returning_learner_gets_next_unit_with_recap(workflow, learners, judge):
    user_id = await learners.create("en", "German", "Practical everyday English, beginner")
    first = await workflow.run(user_id)
    [
        await workflow.repository.complete_objective(first.lesson.lesson_uuid, o.id, "done")
        for o in first.lesson.objectives
    ]
    await workflow.repository.finish_lesson(
        first.lesson.lesson_uuid,
        LessonCompletion(
            status="completed",
            summary="Learner greeted well, struggled with 'th' sound.",
            new_vocabulary=[
                VocabularyItem(term="nice to meet you", meaning="freut mich"),
                VocabularyItem(term="neighbour", meaning="Nachbar"),
            ],
        ),
    )

    second = await workflow.run(user_id)

    assert second.lesson.lesson_uuid != first.lesson.lesson_uuid
    assert second.unit.position > first.unit.position
    verdict = await judge.check(
        "The new lesson has a different main topic from the previous lesson title, and its "
        "tutor guidance mentions reviewing at least one previous word ('nice to meet you' or "
        "'neighbour'). A short review of old words is desired and is NOT repetition.",
        {"previous_title": first.lesson.title, "new": second.lesson.model_dump(include={"title", "lesson_script", "objectives"})},
    )
    assert verdict.passed, verdict.reason


async def test_abandoned_lesson_carries_unmet_objectives(workflow, learners, judge):
    user_id = await learners.create("es", "English", None)
    first = await workflow.run(user_id)
    await workflow.repository.finish_lesson(
        first.lesson.lesson_uuid, LessonCompletion(status="abandoned", summary="Learner had to leave")
    )

    second = await workflow.run(user_id)

    assert second.unit.position == first.unit.position
    verdict = await judge.check(
        "Every objective is written in English (quoted Spanish phrases are fine).",
        [o.text for o in second.lesson.objectives],
    )
    assert verdict.passed, verdict.reason
    verdict = await judge.check(
        "The NEW lesson's objectives substantially cover the PREVIOUS unmet objectives.",
        {
            "previous_unmet": [o.text for o in first.lesson.objectives],
            "new_objectives": [o.text for o in second.lesson.objectives],
        },
    )
    assert verdict.passed, verdict.reason
