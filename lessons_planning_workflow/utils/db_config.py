"""Shared Postgres connection-string resolution.

Single source of truth for the DSN so the read toolkit and the write class
do not duplicate connection logic.
"""

import logging
import os

logger = logging.getLogger(__name__)


def get_connection_string() -> str:
    """Build the Postgres DSN for the lessons-planning workflow.

    The DSN is assembled from the ``POSTGRES_*`` environment variables. Inside
    the docker-compose network the service reaches the database at
    ``postgres:5432`` (``POSTGRES_HOST``/``POSTGRES_PORT`` are set in compose); a
    host-side run falls back to ``localhost:5433``, the host-published port.

    ``DATABASE_URL`` is intentionally ignored: this workflow composes its DSN
    solely from the ``POSTGRES_*`` variables.

    Returns:
        A ``postgresql://`` connection string usable by psycopg.
    """
    user = os.getenv("POSTGRES_USER", "teacher")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    db = os.getenv("POSTGRES_DB", "ai_language_teacher")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    # Log the target only — never the password or the full DSN.
    logger.debug("Resolved Postgres DSN target: %s@%s:%s/%s", user, host, port, db)
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"
