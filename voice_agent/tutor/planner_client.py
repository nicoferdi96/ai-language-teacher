"""HTTP client for the lesson-planner service, the single owner of lesson records."""

import logging
import os
from typing import Any

import httpx

from tutor.lesson import LessonState

logger = logging.getLogger(__name__)


class PlannerClient:
    """Reads and writes lesson progress through the planner's REST API."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        self.base_url = (base_url or os.getenv("PLANNER_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST JSON to the planner and return the decoded response."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(path, json=payload or {})
            response.raise_for_status()
            return response.json()

    async def next_lesson(self, user_id: str) -> dict[str, Any]:
        """Return the learner's next lesson package (built on demand)."""
        return await self._post("/get_next_lesson/", {"user_id": user_id})

    async def start_lesson(self, lesson_uuid: str) -> None:
        """Mark the lesson as in progress."""
        await self._post(f"/lessons/{lesson_uuid}/start")

    async def complete_objective(self, lesson_uuid: str, objective_id: str, evidence: str) -> None:
        """Persist one achieved objective."""
        await self._post(f"/lessons/{lesson_uuid}/objectives/{objective_id}", {"evidence": evidence})

    async def finish_lesson(self, state: LessonState) -> None:
        """Persist the lesson outcome."""
        await self._post(
            f"/lessons/{state.package.lesson_uuid}/complete",
            {
                "status": state.outcome,
                "summary": state.summary,
                "new_vocabulary": [item.model_dump() for item in state.new_vocabulary],
            },
        )
