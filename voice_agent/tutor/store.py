"""Read-only access to the planner's lesson tables: the worker loads a lesson's goal and steps here.

The planner stays the only writer; progress goes back through its HTTP API (``tutor/planner.py``).
"""

import psycopg
from psycopg.rows import dict_row

from tutor.lesson import LessonGoal, LessonPlan
from tutor.settings import settings


class LessonNotFoundError(LookupError):
    """Raised when the dispatched lesson is not in the database."""


class LessonStore:
    """Loads one planned lesson with its steps, learner profile and plan unit in a single query."""

    QUERY = """
        SELECT
            lessons.lesson_uuid::text AS lesson_uuid,
            lessons.user_id,
            lessons.target_language,
            lessons.title,
            lessons.goal_aim,
            lessons.goal_prompt,
            lessons.opening_line,
            lessons.duration AS duration_minutes,
            lessons.vocabulary,
            COALESCE(plans.native_language, 'English') AS native_language,
            COALESCE(plans.level, 'A1') AS level,
            units.title AS unit_title,
            method.answer AS learning_method,
            COALESCE((
                SELECT json_agg(json_build_object(
                    'position', steps.position, 'task', steps.task, 'prompt', steps.prompt,
                    'done', steps.done, 'evidence', steps.evidence
                ) ORDER BY steps.position)
                FROM lesson_steps steps WHERE steps.lesson_uuid = lessons.lesson_uuid
            ), '[]'::json) AS steps
        FROM lessons
        LEFT JOIN learning_plans plans ON plans.plan_id = lessons.plan_id
        LEFT JOIN plan_units units ON units.unit_id = lessons.unit_id
        LEFT JOIN answers method ON method.user_id = lessons.user_id AND method.question_id = 3
        WHERE lessons.lesson_uuid = %s
    """

    def __init__(self, database_url: str = settings.database_url):
        """Read from the given Postgres; one short-lived connection per load, opened on the job's loop."""
        self._database_url = database_url

    async def load(self, lesson_uuid: str) -> LessonPlan:
        """Return the lesson as the tutor runs it, or raise LessonNotFoundError."""
        async with await psycopg.AsyncConnection.connect(self._database_url, row_factory=dict_row) as conn:
            await conn.set_read_only(True)
            cur = await conn.execute(self.QUERY, (lesson_uuid,))
            row = await cur.fetchone()
        if row is None:
            raise LessonNotFoundError(lesson_uuid)
        goal = LessonGoal(aim=row.pop("goal_aim"), prompt=row.pop("goal_prompt"))
        return LessonPlan(**row, goal=goal)
