import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from planner.repository import LearnerRepository  # noqa: E402
from utils.db_config import get_connection_string  # noqa: E402


class LearnerFactory:
    """Creates isolated learners with onboarding answers in the test database."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.created: list[str] = []

    async def create(
        self,
        target: str | None = "es",
        native: str | None = "English",
        method: str | None = "Conversation, please",
    ) -> str:
        """Insert answers for a new unique learner and return its user id."""
        user_id = f"test-{uuid.uuid4().hex[:10]}@example.com"
        rows = [
            (user_id, question_id, answer)
            for question_id, answer in ((1, target), (2, native), (3, method))
            if answer is not None
        ]
        async with await psycopg.AsyncConnection.connect(self.connection_string) as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO answers (user_id, question_id, answer) VALUES (%s, %s, %s)", rows
                )
        self.created.append(user_id)
        return user_id

    async def cleanup(self) -> None:
        """Delete every row created for the factory's learners."""
        async with await psycopg.AsyncConnection.connect(self.connection_string) as conn:
            for table in ("lessons", "learning_plans", "answers"):
                await conn.execute(f"DELETE FROM {table} WHERE user_id = ANY(%s)", (self.created,))


@pytest.fixture
async def learners():
    """Yield a LearnerFactory and delete its rows afterwards."""
    factory = LearnerFactory(get_connection_string())
    yield factory
    await factory.cleanup()


@pytest.fixture
def repository() -> LearnerRepository:
    """Repository against the compose Postgres published on localhost:5433."""
    return LearnerRepository()


def pytest_collection_modifyitems(config, items):
    """Skip live LLM tests unless RUN_LIVE=1."""
    if os.getenv("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE=1 to call OpenRouter")
    [item.add_marker(skip) for item in items if "live" in item.keywords]
