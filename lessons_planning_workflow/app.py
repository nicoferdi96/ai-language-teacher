import json
import logging

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field

from main import lesson_workflow

# main.py's basicConfig already configured the root logger on import above.
logger = logging.getLogger(__name__)

app = FastAPI()


class UserData(BaseModel):
    user_id: EmailStr = Field(description="User email provided at log-in")


class LessonResponse(BaseModel):
    user_id: str
    lesson_uuid: str
    lesson_script: str
    duration: int


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/get_next_lesson/")
async def get_next_lesson(user_data: UserData) -> LessonResponse:
    logger.info("Received get_next_lesson request for %s", user_data.user_id)
    prompt = (
        f"Generate the Voice Agent lesson prompt for the learner with email "
        f"{user_data.user_id}."
    )
    logger.debug("Workflow prompt: %s", prompt)
    try:
        result = await lesson_workflow.arun(
            input=prompt,
            additional_data={"user_id": user_data.user_id},
            stream=False,
        )
        response = LessonResponse(**json.loads(result.content))
    except Exception:
        logger.exception("Lesson generation failed for %s", user_data.user_id)
        raise
    logger.info(
        "Lesson %s generated for %s, duration %dmin",
        response.lesson_uuid,
        response.user_id,
        response.duration,
    )
    return response
