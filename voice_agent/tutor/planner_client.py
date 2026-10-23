"""HTTP client for the lesson-planner service, the single owner of lesson records."""

import os
from typing import Any

import httpx
from pydantic import BaseModel

from tutor.lesson import LessonState, NextLessonResponse

PLAN_TIMEOUT_S = 120.0
"""Building the next lesson may run the planner's agents."""
WRITE_TIMEOUT_S = 10.0
"""Progress writes are plain database updates."""


class NextLessonRequest(BaseModel):
    """Body of the planner's next-lesson call."""

    user_id: str


class ObjectiveEvidence(BaseModel):
    """Body of the planner's objective call."""

    evidence: str


class PlannerClient:
    """Reads and writes lesson progress through the planner's REST API over one connection pool."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("PLANNER_BASE_URL", "http://localhost:8000")).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """The shared HTTP client, created on first use."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=WRITE_TIMEOUT_S)
        return self._client

    async def aclose(self) -> None:
        """Close the connection pool."""
        if self._client is not None:
            await self._client.aclose()

    async def _post(self, path: str, body: BaseModel | None = None, timeout: float = WRITE_TIMEOUT_S) -> Any:
        """POST JSON to the planner and return the decoded response."""
        response = await self.client.post(
            path, json=body.model_dump(mode="json") if body else {}, timeout=timeout
        )
        response.raise_for_status()
        return response.json()

    async def next_lesson(self, user_id: str) -> NextLessonResponse:
        """Return the learner's next lesson (built on demand)."""
        payload = await self._post("/get_next_lesson/", NextLessonRequest(user_id=user_id), timeout=PLAN_TIMEOUT_S)
        return NextLessonResponse.model_validate(payload)

    async def start_lesson(self, lesson_uuid: str) -> None:
        """Mark the lesson as in progress."""
        await self._post(f"/lessons/{lesson_uuid}/start")

    async def complete_objective(self, lesson_uuid: str, objective_id: str, evidence: str) -> None:
        """Persist one achieved objective."""
        await self._post(f"/lessons/{lesson_uuid}/objectives/{objective_id}", ObjectiveEvidence(evidence=evidence))

    async def finish_lesson(self, state: LessonState) -> None:
        """Persist the lesson outcome."""
        await self._post(f"/lessons/{state.package.lesson_uuid}/complete", state.finish_request())
