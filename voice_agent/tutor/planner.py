"""Talking to the lesson planner, the single owner of lesson records, and mirroring progress to the browser."""

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

import httpx
from livekit import rtc
from pydantic import BaseModel

from tutor.lesson import LessonState, NextLessonResponse
from tutor.settings import settings

logger = logging.getLogger(__name__)

PLAN_TIMEOUT_S = 120.0
"""Building the next lesson may run the planner's agents."""
WRITE_TIMEOUT_S = 10.0
"""Progress writes are plain database updates."""


class NextLessonRequest(BaseModel):
    """Body of the planner's next-lesson call."""

    user_id: str


class StepEvidence(BaseModel):
    """Body of the planner's step call."""

    evidence: str


class PlannerClient:
    """Reads and writes lesson progress through the planner's REST API over one connection pool."""

    def __init__(self, base_url: str = settings.planner_base_url):
        """Point the client at the planner; the HTTP pool opens on the first request."""
        self.base_url = base_url.rstrip("/")
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

    async def next_lesson(self, user_id: str) -> NextLessonResponse:
        """Return the learner's next lesson (built on demand)."""
        payload = await self._post("/get_next_lesson/", NextLessonRequest(user_id=user_id), timeout=PLAN_TIMEOUT_S)
        return NextLessonResponse.model_validate(payload)

    async def start_lesson(self, lesson_uuid: str) -> None:
        """Mark the lesson as in progress."""
        await self._post(f"/lessons/{lesson_uuid}/start")

    async def complete_step(self, lesson_uuid: str, position: int, evidence: str) -> None:
        """Persist one finished step."""
        await self._post(f"/lessons/{lesson_uuid}/steps/{position}", StepEvidence(evidence=evidence))

    async def finish_lesson(self, state: LessonState) -> None:
        """Persist the lesson outcome."""
        await self._post(f"/lessons/{state.plan.lesson_uuid}/complete", state.finish_request())

    async def _post(self, path: str, body: BaseModel | None = None, timeout: float = WRITE_TIMEOUT_S) -> Any:
        """POST JSON to the planner and return the decoded response."""
        response = await self.client.post(path, json=body.model_dump(mode="json") if body else {}, timeout=timeout)
        response.raise_for_status()
        return response.json()


class LessonRecorder:
    """Persists lesson progress to the planner and mirrors it to the browser.

    Step writes run in the background so the next step starts at once; ``finished``
    waits for them, then re-sends every finished step and the outcome.
    Planner and publish failures are logged, never raised to the model: the in-session
    state stays authoritative, and the room may already be closed for the final event.
    Without a planner or a room (tests, console) the matching side is skipped.
    """

    def __init__(self, state: LessonState, planner: PlannerClient | None = None, room: rtc.Room | None = None):
        """Record progress for this lesson to the planner and the room, when given."""
        self.state = state
        self.planner = planner
        self.room = room
        self._pending: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Mark the lesson in progress with the planner and show its steps in the browser."""
        if self.planner is not None:
            await self.planner.start_lesson(self.state.plan.lesson_uuid)
        await self._safely(self.publish())

    async def publish(self) -> None:
        """Send the current lesson progress to the browser on the progress topic."""
        if self.room is not None:
            await self.room.local_participant.publish_data(
                self.state.progress_event().model_dump_json(), reliable=True, topic=settings.progress_topic
            )

    def step_done(self, position: int) -> None:
        """Persist and publish one finished step without blocking the caller."""
        task = asyncio.create_task(self._record_step(position))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def finished(self) -> None:
        """Wait for pending writes, re-send each finished step and the outcome, then publish."""
        await asyncio.gather(*self._pending)
        if self.planner is not None:
            for step in self.state.steps:
                if step.done:
                    await self._safely(self._complete_step(step.position))
            await self._safely(self.planner.finish_lesson(self.state))
        await self._safely(self.publish())

    async def aclose(self) -> None:
        """Release the planner connection pool."""
        if self.planner is not None:
            await self.planner.aclose()

    async def _record_step(self, position: int) -> None:
        """Persist one step with the planner, then publish the new progress."""
        if self.planner is not None:
            await self._safely(self._complete_step(position))
        await self._safely(self.publish())

    async def _complete_step(self, position: int) -> None:
        """Send one step's evidence to the planner."""
        step = self.state.step(position)
        await self.planner.complete_step(self.state.plan.lesson_uuid, position, step.evidence or "")

    @staticmethod
    async def _safely(call: Awaitable[None]) -> None:
        """Await a planner or publish call, logging instead of raising on failure."""
        try:
            await call
        except Exception:
            logger.warning("Planner/publish call failed; lesson state kept in session", exc_info=True)
