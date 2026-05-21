"""Agno toolkit for reading a user's saved onboarding answers from Postgres.

Read-only by design. The write side lives in ``utils.postgres_db.PostgresDB`` and
runs in the workflow's deterministic step, not as an agent tool.
"""

import json

import psycopg
from agno.tools import Toolkit
from agno.utils.log import log_error

from utils.db_config import get_connection_string

# question_id values, as seeded in db/init.sql.
_QUESTION_LEARNING_METHOD = 1  # "How would you like to learn Spanish?"
_QUESTION_DURATION = 2  # "What is your ideal duration per single lesson?"

# Parameterized so user_id is always bound as a value, never interpolated.
_SQL = "SELECT question_id, answer FROM answers WHERE user_id = %s"


class AnswersToolkit(Toolkit):
    """Reads the onboarding answers of a single user (identified by email).

    Exposes one logical tool, ``get_user_answers``, with a synchronous and an
    asynchronous implementation. Agno runs the async variant automatically when
    the agent is executed in an async context.
    """

    def __init__(self, connection_string: str | None = None, **kwargs):
        self.connection_string = connection_string or get_connection_string()
        super().__init__(
            name="answers_toolkit",
            tools=[self.get_user_answers],
            async_tools=[(self.aget_user_answers, "get_user_answers")],
            **kwargs,
        )

    def get_user_answers(self, user_id: str) -> str:
        """Read the saved Spanish-learning preferences for one user.

        Args:
            user_id: The user's email address. Only this user's rows are read.

        Returns:
            A JSON string with the user's ``learning_method`` and
            ``ideal_duration``. On failure, a JSON string with an ``error`` key.
        """
        try:
            with psycopg.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute(_SQL, (user_id,))
                    rows = cur.fetchall()
            return self._format(user_id, rows)
        except Exception as e:
            log_error(f"get_user_answers failed for {user_id}: {e}")
            return json.dumps({"error": str(e)})

    async def aget_user_answers(self, user_id: str) -> str:
        """Read the saved Spanish-learning preferences for one user (async).

        Args:
            user_id: The user's email address. Only this user's rows are read.

        Returns:
            A JSON string with the user's ``learning_method`` and
            ``ideal_duration``. On failure, a JSON string with an ``error`` key.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self.connection_string
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(_SQL, (user_id,))
                    rows = await cur.fetchall()
            return self._format(user_id, rows)
        except Exception as e:
            log_error(f"aget_user_answers failed for {user_id}: {e}")
            return json.dumps({"error": str(e)})

    @staticmethod
    def _format(user_id: str, rows: list[tuple[int, str]]) -> str:
        """Map ``(question_id, answer)`` rows to a stable JSON payload."""
        by_qid = {qid: answer for qid, answer in rows}
        return json.dumps(
            {
                "user_id": user_id,
                "learning_method": by_qid.get(_QUESTION_LEARNING_METHOD),
                "ideal_duration": by_qid.get(_QUESTION_DURATION),
            }
        )
