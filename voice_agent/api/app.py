"""FastAPI front door for voice lessons: fetch the lesson, mint a room token."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI, HTTPException
from livekit import api
from pydantic import BaseModel, EmailStr

from tutor.lesson import LessonDispatch, LessonView
from tutor.planner import PlannerClient
from tutor.settings import settings

logger = logging.getLogger(__name__)

planner = PlannerClient()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Close the planner connection pool on shutdown."""
    yield
    await planner.aclose()


app = FastAPI(title="Voice lesson API", lifespan=lifespan)


class SessionRequest(BaseModel):
    """Request to start a voice lesson."""

    user_id: EmailStr


class SessionResponse(BaseModel):
    """Everything the browser needs to join the lesson room."""

    server_url: str
    participant_token: str
    room_name: str
    progress_topic: str
    lesson: LessonView


class RoomTokenIssuer:
    """Creates a unique room per lesson and a token that dispatches the tutor."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        """Use the given LiveKit key pair, or the one from the settings; fail fast when any is missing."""
        secret = settings.livekit_api_secret.get_secret_value() if settings.livekit_api_secret else None
        self.api_key = api_key or settings.livekit_api_key
        self.api_secret = api_secret or secret
        self.server_url = settings.livekit_url
        if not (self.server_url and self.api_key and self.api_secret):
            raise RuntimeError("LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set")

    def issue(self, dispatch: LessonDispatch) -> tuple[str, str]:
        """Return ``(room_name, jwt)``; the agent is dispatched on room creation with the lesson to load."""
        room_name = f"lesson-{dispatch.lesson_uuid[:8]}-{uuid.uuid4().hex[:6]}"
        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(f"learner-{uuid.uuid4().hex[:8]}")
            .with_name(dispatch.user_id)
            .with_ttl(timedelta(minutes=30))
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=settings.agent_name, metadata=dispatch.model_dump_json()
                        )
                    ]
                )
            )
            .to_jwt()
        )
        return room_name, token


@app.get("/health")
def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(request: SessionRequest) -> SessionResponse:
    """Prepare (or reuse) the learner's next lesson and return room credentials."""
    try:
        next_lesson = await planner.next_lesson(str(request.user_id))
    except httpx.HTTPError as error:
        logger.exception("Planner unavailable for %s", request.user_id)
        raise HTTPException(status_code=503, detail=f"Lesson planner unavailable: {error}")
    issuer = RoomTokenIssuer()
    room_name, token = issuer.issue(next_lesson.dispatch())
    logger.info("Lesson %s room %s for %s", next_lesson.lesson.lesson_uuid, room_name, request.user_id)
    return SessionResponse(
        server_url=issuer.server_url,
        participant_token=token,
        room_name=room_name,
        progress_topic=settings.progress_topic,
        lesson=next_lesson.view(),
    )
