"""Agno workflow: review progress, ensure a plan exists, prepare the next lesson."""

import asyncio
import logging
from collections import defaultdict

from agno.workflow import Step, StepInput, StepOutput, Workflow
from langfuse import get_client, observe, propagate_attributes

from planner.agents import CurriculumAgent, LessonAgent
from planner.models import LessonPackage, LessonRecord, ProgressSnapshot
from planner.repository import LearnerRepository
from planner.tracing import TRACE_NAME

logger = logging.getLogger(__name__)


class LessonPlanningWorkflow:
    """Owns the three workflow steps and the shared repository and agents."""

    def __init__(
        self,
        repository: LearnerRepository | None = None,
        curriculum_agent: CurriculumAgent | None = None,
        lesson_agent: LessonAgent | None = None,
    ):
        self.repository = repository or LearnerRepository()
        self.curriculum_agent = curriculum_agent or CurriculumAgent()
        self.lesson_agent = lesson_agent or LessonAgent()
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.workflow = Workflow(
            name="Lesson Planning Pipeline",
            steps=[
                Step(name="review_progress", executor=self.review_progress),
                Step(name="ensure_plan", executor=self.ensure_plan),
                Step(name="prepare_lesson", executor=self.prepare_lesson),
            ],
        )

    @observe(name="review-progress", capture_input=False, capture_output=False)
    async def review_progress(self, step_input: StepInput) -> StepOutput:
        """Load where the learner stands from Postgres."""
        user_id = step_input.additional_data["user_id"]
        snapshot = await self.repository.snapshot(user_id)
        get_client().update_current_span(
            output={
                "target_language": snapshot.profile.target_language,
                "has_plan": snapshot.plan is not None,
                "recent_lessons": len(snapshot.recent_lessons),
                "open_lesson": str(snapshot.open_lesson.lesson_uuid) if snapshot.open_lesson else None,
            }
        )
        logger.info(
            "Progress for %s: plan=%s, recent lessons=%d, open lesson=%s",
            user_id,
            snapshot.plan.plan_id if snapshot.plan else None,
            len(snapshot.recent_lessons),
            snapshot.open_lesson.lesson_uuid if snapshot.open_lesson else None,
        )
        return StepOutput(content=snapshot)

    @observe(name="ensure-plan", capture_input=False, capture_output=False)
    async def ensure_plan(self, step_input: StepInput) -> StepOutput:
        """Build and store a learning plan when the learner has none."""
        snapshot: ProgressSnapshot = step_input.previous_step_content
        if snapshot.plan is not None:
            get_client().update_current_span(output={"plan_id": str(snapshot.plan.plan_id), "created": False})
            return StepOutput(content=snapshot)
        draft = await self.curriculum_agent.design(snapshot.profile)
        plan = await self.repository.create_plan(snapshot.profile, draft)
        get_client().update_current_span(output={"plan_id": str(plan.plan_id), "created": True})
        return StepOutput(content=snapshot.model_copy(update={"plan": plan}))

    @observe(name="prepare-lesson", capture_input=False, capture_output=False)
    async def prepare_lesson(self, step_input: StepInput) -> StepOutput:
        """Reuse the open lesson or design and store the next one."""
        snapshot: ProgressSnapshot = step_input.previous_step_content
        plan = snapshot.plan
        if snapshot.open_lesson is not None:
            lesson = snapshot.open_lesson
            logger.info("Reusing open lesson %s", lesson.lesson_uuid)
        else:
            brief = await self.lesson_agent.design(snapshot.profile, plan, snapshot.recent_lessons)
            focus = plan.next_unit() or plan.units[-1]
            unit = next(
                (candidate for candidate in plan.units if candidate.position == brief.unit_position),
                focus,
            )
            recap = self.recap_terms(snapshot.recent_lessons, brief.recap_terms)
            lesson = await self.repository.create_lesson(
                plan, unit, brief.model_copy(update={"recap_terms": recap})
            )
        unit = next((candidate for candidate in plan.units if candidate.unit_id == lesson.unit_id), None)
        package = LessonPackage(
            lesson=lesson,
            native_language=snapshot.profile.native_language,
            learning_method=snapshot.profile.learning_method,
            level=plan.level,
            unit=unit,
        )
        get_client().update_current_span(
            output={
                "lesson_uuid": str(lesson.lesson_uuid),
                "title": lesson.title,
                "reused_open_lesson": snapshot.open_lesson is not None,
            }
        )
        return StepOutput(content=package)

    @staticmethod
    def recap_terms(recent_lessons: list[LessonRecord], suggested: list[str], limit: int = 4) -> list[str]:
        """Return up to ``limit`` review terms: recent new vocabulary first, then suggestions."""
        recent = [item.term for lesson in recent_lessons[:2] for item in lesson.new_vocabulary]
        return list(dict.fromkeys([*recent, *suggested]))[:limit]

    async def run(self, user_id: str) -> LessonPackage:
        """Run the full workflow for a learner and return the lesson package.

        A per-learner lock keeps concurrent requests from creating two lessons. The run is
        one Langfuse trace, tagged with the learner's id.
        """
        with (
            get_client().start_as_current_observation(
                as_type="chain", name=TRACE_NAME, input={"user_id": user_id}
            ) as root,
            propagate_attributes(user_id=user_id, trace_name=TRACE_NAME, tags=["planner"]),
        ):
            async with self.locks[user_id]:
                result = await self.workflow.arun(
                    input=f"Prepare the next lesson for {user_id}",
                    additional_data={"user_id": user_id},
                    stream=False,
                )
            package = LessonPackage.model_validate(result.content)
            root.update(
                output={
                    "lesson_uuid": str(package.lesson.lesson_uuid),
                    "title": package.lesson.title,
                    "level": package.level,
                }
            )
        return package
