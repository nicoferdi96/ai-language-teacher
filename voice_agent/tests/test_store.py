"""LessonStore against the compose Postgres: the worker's one read of a planned lesson."""

import uuid

import psycopg
import pytest

from tutor.settings import settings
from tutor.store import LessonNotFoundError, LessonStore


@pytest.fixture
async def lesson_uuid():
    """Insert a learner, plan, unit and a two-step lesson; delete them afterwards."""
    user_id = f"store-{uuid.uuid4().hex[:8]}@example.com"
    plan_id, unit_id, lesson_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        conn = await psycopg.AsyncConnection.connect(settings.database_url)
    except psycopg.OperationalError:
        pytest.skip("Postgres is not reachable")
    async with conn:
        await conn.execute(
            "INSERT INTO answers (user_id, question_id, answer) VALUES (%s, 3, 'Conversation')", (user_id,)
        )
        await conn.execute(
            "INSERT INTO learning_plans (plan_id, user_id, target_language, native_language, level, goal_summary) "
            "VALUES (%s, %s, 'es', 'Italian', 'A2', 'g')",
            (plan_id, user_id),
        )
        await conn.execute(
            "INSERT INTO plan_units (unit_id, plan_id, position, title, kind, description) "
            "VALUES (%s, %s, 1, 'Meeting people', 'conversation', 'd')",
            (unit_id, plan_id),
        )
        await conn.execute(
            "INSERT INTO lessons (lesson_uuid, user_id, plan_id, unit_id, target_language, title, goal_aim, "
            "goal_prompt, opening_line, vocabulary) VALUES (%s, %s, %s, %s, 'es', 'Hola', 'Aim', 'Prompt', "
            "'¡Hola!', '[{\"term\": \"hola\", \"meaning\": \"ciao\"}]')",
            (lesson_id, user_id, plan_id, unit_id),
        )
        await conn.execute(
            "INSERT INTO lesson_steps (lesson_uuid, position, task, prompt, done, evidence) VALUES "
            "(%s, 2, 'Say where you are from', 'P2', false, NULL), (%s, 1, 'Say your name', 'P1', true, 'Me llamo')",
            (lesson_id, lesson_id),
        )
    yield str(lesson_id)
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await conn.execute("DELETE FROM learning_plans WHERE user_id = %s", (user_id,))
        await conn.execute("DELETE FROM lessons WHERE user_id = %s", (user_id,))
        await conn.execute("DELETE FROM answers WHERE user_id = %s", (user_id,))


async def test_loads_goal_steps_and_learner_in_order(lesson_uuid):
    plan = await LessonStore().load(lesson_uuid)

    assert (plan.goal.aim, plan.goal.prompt, plan.opening_line) == ("Aim", "Prompt", "¡Hola!")
    assert [(step.position, step.task, step.done) for step in plan.steps] == [
        (1, "Say your name", True),
        (2, "Say where you are from", False),
    ]
    assert plan.steps[0].evidence == "Me llamo"
    assert (plan.native_language, plan.level, plan.unit_title) == ("Italian", "A2", "Meeting people")
    assert plan.learning_method == "Conversation"
    assert plan.vocabulary[0].term == "hola"


async def test_unknown_lesson_raises(lesson_uuid):
    with pytest.raises(LessonNotFoundError):
        await LessonStore().load(str(uuid.uuid4()))
