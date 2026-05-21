"""Agno toolkit for reading a user's saved onboarding answers from Postgres.

Read-only. The write side lives in ``utils.postgres_db.PostgresDB``.
"""

import json

import psycopg
from agno.tools import Toolkit

from utils.db_config import get_connection_string

# question_id values, as seeded in db/init.sql.
_QUESTION_LEARNING_METHOD = 1  # "How would you like to learn Spanish?"
_QUESTION_DURATION = 2  # "What is your ideal duration per single lesson?"


class AnswersToolkit(Toolkit):
    """Reads the onboarding answers of a single user, identified by email."""

    def __init__(self, connection_string: str | None = None, **kwargs):
        self.connection_string = connection_string or get_connection_string()
        super().__init__(
            name="answers_toolkit",
            async_tools=[(self.get_user_answers, "get_user_answers")],
            **kwargs,
        )

    async def get_user_answers(self, user_id: str) -> str:
        """Return the user's saved learning_method and ideal_duration as JSON.

        Args:
            user_id: The user's email address. Only this user's rows are read.
        """
        async with await psycopg.AsyncConnection.connect(
            self.connection_string
        ) as conn:
            cur = await conn.execute(
                "SELECT question_id, answer FROM answers WHERE user_id = %s",
                (user_id,),
            )
            answers = {question_id: answer for question_id, answer in await cur.fetchall()}

        return json.dumps(
            {
                "user_id": user_id,
                "learning_method": answers.get(_QUESTION_LEARNING_METHOD),
                "ideal_duration": answers.get(_QUESTION_DURATION),
            }
        )
