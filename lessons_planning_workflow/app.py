import logging
import sys
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

from planner.models import (
    LearningPlan,
    LessonCompletion,
    LessonPackage,
    LessonRecord,
    ObjectiveUpdate,
)
from planner.repository import LearnerRepository, LessonNotFoundError, ObjectiveNotFoundError
from planner.workflow import LessonPlanningWorkflow

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lesson planner")
repository = LearnerRepository()
planning_workflow = LessonPlanningWorkflow(repository=repository)


class UserData(BaseModel):
    """Request body identifying a learner."""

    user_id: EmailStr = Field(description="User email provided at log-in")


class ProgressResponse(BaseModel):
    """Plan and lesson history shown on the learner's home screen."""

    plan: LearningPlan | None
    lessons: list[LessonRecord]


@app.get("/")
def read_root() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@app.post("/get_next_lesson/")
async def get_next_lesson(user_data: UserData) -> LessonPackage:
    """Review progress, build the plan if missing, and return the next lesson."""
    logger.info("Next lesson requested for %s", user_data.user_id)
    package = await planning_workflow.run(str(user_data.user_id))
    logger.info("Lesson %s ready for %s", package.lesson.lesson_uuid, user_data.user_id)
    return package


@app.get("/progress/{user_id}")
async def get_progress(user_id: str) -> ProgressResponse:
    """Return the learner's plan with unit statuses and recent lessons."""
    snapshot = await repository.snapshot(user_id)
    return ProgressResponse(plan=snapshot.plan, lessons=snapshot.recent_lessons)


@app.get("/lessons/{lesson_uuid}")
async def get_lesson(lesson_uuid: uuid.UUID) -> LessonRecord:
    """Return one lesson."""
    try:
        return await repository.get_lesson(lesson_uuid)
    except LessonNotFoundError:
        raise HTTPException(status_code=404, detail="Lesson not found")


@app.post("/lessons/{lesson_uuid}/start")
async def start_lesson(lesson_uuid: uuid.UUID) -> LessonRecord:
    """Mark a lesson as in progress."""
    try:
        return await repository.start_lesson(lesson_uuid)
    except LessonNotFoundError:
        raise HTTPException(status_code=404, detail="Lesson not found")


@app.post("/lessons/{lesson_uuid}/objectives/{objective_id}")
async def complete_objective(
    lesson_uuid: uuid.UUID, objective_id: str, update: ObjectiveUpdate
) -> LessonRecord:
    """Mark one lesson objective as achieved."""
    try:
        return await repository.complete_objective(lesson_uuid, objective_id, update.evidence)
    except (LessonNotFoundError, ObjectiveNotFoundError) as error:
        raise HTTPException(status_code=404, detail=f"Not found: {error}")


@app.post("/lessons/{lesson_uuid}/complete")
async def complete_lesson(lesson_uuid: uuid.UUID, completion: LessonCompletion) -> LessonRecord:
    """Close a lesson as completed or abandoned and update plan progress."""
    try:
        return await repository.finish_lesson(lesson_uuid, completion)
    except LessonNotFoundError:
        raise HTTPException(status_code=404, detail="Lesson not found")
