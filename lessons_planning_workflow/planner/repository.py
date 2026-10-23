"""Async Postgres access for learner profiles, plans and lessons."""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from planner.languages import DEFAULT_TARGET_LANGUAGE, SUPPORTED_LANGUAGES
from planner.models import (
    LearnerProfile,
    LearningPlan,
    LearningPlanDraft,
    LessonBriefDraft,
    LessonCompletion,
    LessonRecord,
    PlanUnit,
    ProgressSnapshot,
)
from utils.db_config import get_connection_string

logger = logging.getLogger(__name__)


class LessonNotFoundError(LookupError):
    """Raised when a lesson uuid does not exist."""


class ObjectiveNotFoundError(LookupError):
    """Raised when an objective id does not exist on a lesson."""


class LearnerRepository:
    """Single owner of reads and writes for plans, units and lessons."""

    QUESTION_TARGET_LANGUAGE = 1
    QUESTION_NATIVE_LANGUAGE = 2
    QUESTION_LEARNING_METHOD = 3
    RECENT_LESSONS = 5

    def __init__(self, connection_string: str | None = None):
        self.connection_string = connection_string or get_connection_string()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[psycopg.AsyncConnection]:
        """Open one connection that returns dict rows and commits on exit."""
        async with await psycopg.AsyncConnection.connect(
            self.connection_string, row_factory=dict_row
        ) as conn:
            yield conn

    async def get_profile(self, user_id: str) -> LearnerProfile:
        """Return the learner's onboarding answers, with safe defaults."""
        async with self._connect() as conn:
            cur = await conn.execute(
                "SELECT question_id, answer FROM answers WHERE user_id = %s", (user_id,)
            )
            answers = {row["question_id"]: row["answer"] for row in await cur.fetchall()}
        target = answers.get(self.QUESTION_TARGET_LANGUAGE)
        return LearnerProfile(
            user_id=user_id,
            target_language=target if target in SUPPORTED_LANGUAGES else DEFAULT_TARGET_LANGUAGE,
            native_language=answers.get(self.QUESTION_NATIVE_LANGUAGE) or "English",
            learning_method=answers.get(self.QUESTION_LEARNING_METHOD),
        )

    async def get_plan(self, user_id: str, target_language: str) -> LearningPlan | None:
        """Return the learner's plan for a language, or None if not built yet."""
        async with self._connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM learning_plans WHERE user_id = %s AND target_language = %s",
                (user_id, target_language),
            )
            plan_row = await cur.fetchone()
            if plan_row is None:
                return None
            cur = await conn.execute(
                "SELECT unit_id, position, title, kind, description, status FROM plan_units "
                "WHERE plan_id = %s ORDER BY position",
                (plan_row["plan_id"],),
            )
            units = [PlanUnit(**row) for row in await cur.fetchall()]
        return LearningPlan(**plan_row, units=units)

    async def create_plan(self, profile: LearnerProfile, draft: LearningPlanDraft) -> LearningPlan:
        """Persist a new plan and its units; return the stored plan."""
        plan_id = uuid.uuid4()
        units = [
            PlanUnit(unit_id=uuid.uuid4(), position=position, **unit.model_dump())
            for position, unit in enumerate(draft.units, start=1)
        ]
        async with self._connect() as conn:
            await conn.execute(
                "INSERT INTO learning_plans (plan_id, user_id, target_language, native_language, "
                "level, goal_summary) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    plan_id,
                    profile.user_id,
                    profile.target_language,
                    profile.native_language,
                    draft.level,
                    draft.goal_summary,
                ),
            )
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO plan_units (unit_id, plan_id, position, title, kind, description) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        (unit.unit_id, plan_id, unit.position, unit.title, unit.kind, unit.description)
                        for unit in units
                    ],
                )
        logger.info("Created plan %s with %d units for %s", plan_id, len(units), profile.user_id)
        return LearningPlan(
            plan_id=plan_id,
            user_id=profile.user_id,
            target_language=profile.target_language,
            native_language=profile.native_language,
            level=draft.level,
            goal_summary=draft.goal_summary,
            units=units,
        )

    async def recent_lessons(self, user_id: str, target_language: str) -> list[LessonRecord]:
        """Return the most recent lessons for a language, newest first."""
        async with self._connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM lessons WHERE user_id = %s AND target_language = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, target_language, self.RECENT_LESSONS),
            )
            return [LessonRecord(**row) for row in await cur.fetchall()]

    async def snapshot(self, user_id: str) -> ProgressSnapshot:
        """Return profile, plan, recent lessons and any still-open lesson."""
        profile = await self.get_profile(user_id)
        plan = await self.get_plan(user_id, profile.target_language)
        lessons = await self.recent_lessons(user_id, profile.target_language)
        open_lesson = next(
            (lesson for lesson in lessons if lesson.status in ("planned", "in_progress")), None
        )
        return ProgressSnapshot(
            profile=profile, plan=plan, recent_lessons=lessons, open_lesson=open_lesson
        )

    async def create_lesson(
        self, plan: LearningPlan, unit: PlanUnit, brief: LessonBriefDraft
    ) -> LessonRecord:
        """Persist a planned lesson built from the lesson agent's brief."""
        lesson = LessonRecord(
            lesson_uuid=uuid.uuid4(),
            user_id=plan.user_id,
            plan_id=plan.plan_id,
            unit_id=unit.unit_id,
            target_language=plan.target_language,
            title=brief.title,
            lesson_script=self._tutor_script(brief),
            objectives=[
                {"id": f"o{index}", "text": text}
                for index, text in enumerate(brief.objectives, start=1)
            ],
            vocabulary=brief.vocabulary,
        )
        async with self._connect() as conn:
            await conn.execute(
                "INSERT INTO lessons (lesson_uuid, user_id, plan_id, unit_id, target_language, "
                "title, lesson_script, duration, objectives, vocabulary) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    lesson.lesson_uuid,
                    lesson.user_id,
                    lesson.plan_id,
                    lesson.unit_id,
                    lesson.target_language,
                    lesson.title,
                    lesson.lesson_script,
                    lesson.duration,
                    Jsonb([objective.model_dump() for objective in lesson.objectives]),
                    Jsonb([item.model_dump() for item in lesson.vocabulary]),
                ),
            )
            await conn.execute(
                "UPDATE plan_units SET status = 'in_progress' WHERE unit_id = %s AND status = 'pending'",
                (unit.unit_id,),
            )
        logger.info("Created lesson %s (%s) for %s", lesson.lesson_uuid, lesson.title, plan.user_id)
        return lesson

    @staticmethod
    def _tutor_script(brief: LessonBriefDraft) -> str:
        """Return the tutor guidelines with the recap terms appended."""
        recap = (
            f"\n\nQuick recap from earlier lessons: {', '.join(brief.recap_terms)}."
            if brief.recap_terms
            else ""
        )
        return f"{brief.tutor_guidelines.strip()}{recap}"

    async def get_lesson(self, lesson_uuid: uuid.UUID) -> LessonRecord:
        """Return one lesson or raise LessonNotFoundError."""
        async with self._connect() as conn:
            cur = await conn.execute("SELECT * FROM lessons WHERE lesson_uuid = %s", (lesson_uuid,))
            row = await cur.fetchone()
        if row is None:
            raise LessonNotFoundError(str(lesson_uuid))
        return LessonRecord(**row)

    async def start_lesson(self, lesson_uuid: uuid.UUID) -> LessonRecord:
        """Move a planned lesson to in_progress (idempotent) and return it."""
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE lessons SET status = 'in_progress', started_at = COALESCE(started_at, now()), "
                "updated_at = now() WHERE lesson_uuid = %s AND status IN ('planned', 'in_progress')",
                (lesson_uuid,),
            )
        return await self.get_lesson(lesson_uuid)

    async def complete_objective(
        self, lesson_uuid: uuid.UUID, objective_id: str, evidence: str
    ) -> LessonRecord:
        """Mark one objective done with evidence; unchanged if already done."""
        lesson = await self.get_lesson(lesson_uuid)
        if objective_id not in {objective.id for objective in lesson.objectives}:
            raise ObjectiveNotFoundError(objective_id)
        objectives = [
            objective.model_copy(update={"done": True, "evidence": evidence})
            if objective.id == objective_id and not objective.done
            else objective
            for objective in lesson.objectives
        ]
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE lessons SET objectives = %s, updated_at = now() WHERE lesson_uuid = %s",
                (Jsonb([objective.model_dump() for objective in objectives]), lesson_uuid),
            )
        return lesson.model_copy(update={"objectives": objectives})

    async def finish_lesson(
        self, lesson_uuid: uuid.UUID, completion: LessonCompletion
    ) -> LessonRecord:
        """Close a lesson and, when every objective is met, mark its unit done."""
        lesson = await self.get_lesson(lesson_uuid)
        all_done = all(objective.done for objective in lesson.objectives)
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE lessons SET status = %s, summary = %s, new_vocabulary = %s, "
                "completed_at = now(), updated_at = now() WHERE lesson_uuid = %s",
                (
                    completion.status,
                    completion.summary,
                    Jsonb([item.model_dump() for item in completion.new_vocabulary]),
                    lesson_uuid,
                ),
            )
            if completion.status == "completed" and all_done and lesson.unit_id:
                await conn.execute(
                    "UPDATE plan_units SET status = 'done', completed_at = now() WHERE unit_id = %s",
                    (lesson.unit_id,),
                )
        logger.info(
            "Lesson %s finished as %s (all objectives done: %s)",
            lesson_uuid,
            completion.status,
            all_done,
        )
        return await self.get_lesson(lesson_uuid)
