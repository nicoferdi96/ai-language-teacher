"""Async Postgres writer for generated lessons."""

import logging
import uuid

import psycopg

from utils.db_config import get_connection_string

logger = logging.getLogger(__name__)


class PostgresDB:
    """Writes generated lesson plans to the ``lessons`` table."""

    def __init__(self, connection_string: str | None = None):
        self.connection_string = connection_string or get_connection_string()

    async def insert_lesson(
        self,
        user_id: str,
        lesson_uuid: uuid.UUID,
        lesson_script: str,
        duration: int,
    ) -> None:
        """Insert one lesson. created_at/updated_at default to now() in the DB."""
        logger.info(
            "Inserting lesson %s for %s (%dmin, %d chars)",
            lesson_uuid,
            user_id,
            duration,
            len(lesson_script),
        )
        try:
            async with await psycopg.AsyncConnection.connect(
                self.connection_string
            ) as conn:
                await conn.execute(
                    "INSERT INTO lessons (user_id, lesson_uuid, lesson_script, duration) VALUES (%s, %s, %s, %s)",
                    (user_id, lesson_uuid, lesson_script, duration),
                )
        except Exception:
            logger.exception("Failed to insert lesson %s for %s", lesson_uuid, user_id)
            raise
        logger.info("Lesson %s inserted for %s", lesson_uuid, user_id)
