"""Shared Postgres connection-string resolution.

Single source of truth for the DSN so the read toolkit and the write class
do not duplicate connection logic.
"""

import os


def get_connection_string() -> str:
    """Build the Postgres DSN for the lessons-planning workflow.

    The workflow runs on the host (not inside the docker-compose network), so it
    reaches the database on the host-published port. The DSN is assembled from the
    ``POSTGRES_*`` variables in the root ``.env`` file (already loaded by
    ``load_dotenv()`` in ``main.py``).

    ``DATABASE_URL`` is intentionally ignored: the only ``DATABASE_URL`` in this
    project points at the docker-internal hostname ``postgres:5432``, which is not
    reachable from a host-side process.

    Returns:
        A ``postgresql://`` connection string usable by psycopg.
    """
    user = os.getenv("POSTGRES_USER", "teacher")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    db = os.getenv("POSTGRES_DB", "ai_language_teacher")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"
