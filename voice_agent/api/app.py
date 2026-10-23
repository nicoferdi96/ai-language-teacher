"""FastAPI front door for voice lessons: fetch the lesson, mint a room token."""

import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from livekit import api
from pydantic import BaseModel, EmailStr

from tutor.lesson import LessonPackage
from tutor.planner_client import PlannerClient
from tutor.worker import AGENT_NAME, PROGRESS_TOPIC

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
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
    lesson: LessonPackage


class RoomTokenIssuer:
    """Creates a unique room per lesson and a token that dispatches the tutor."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        self.api_key = api_key or os.environ["LIVEKIT_API_KEY"]
        self.api_secret = api_secret or os.environ["LIVEKIT_API_SECRET"]

    def issue(self, package: LessonPackage) -> tuple[str, str]:
        """Return ``(room_name, jwt)``; the agent is dispatched on room creation."""
        room_name = f"lesson-{package.lesson_uuid[:8]}-{uuid.uuid4().hex[:6]}"
        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(f"learner-{uuid.uuid4().hex[:8]}")
            .with_name(package.user_id)
            .with_ttl(timedelta(minutes=30))
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=AGENT_NAME, metadata=package.model_dump_json()
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
        package = LessonPackage.from_planner(await planner.next_lesson(str(request.user_id)))
    except httpx.HTTPError as error:
        logger.exception("Planner unavailable for %s", request.user_id)
        raise HTTPException(status_code=503, detail=f"Lesson planner unavailable: {error}")
    room_name, token = RoomTokenIssuer().issue(package)
    logger.info("Lesson %s room %s for %s", package.lesson_uuid, room_name, request.user_id)
    return SessionResponse(
        server_url=os.environ["LIVEKIT_URL"],
        participant_token=token,
        room_name=room_name,
        progress_topic=PROGRESS_TOPIC,
        lesson=package,
    )
