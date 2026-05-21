import json

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field

from main import lesson_workflow

app = FastAPI()


class UserData(BaseModel):
    user_id: EmailStr = Field(description="User email provided at log-in")
    duration: int = Field(gt=0, description="Duration of the lesson in minutes")


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
    prompt = (
        f"Create a Spanish lesson for the learner with email {user_data.user_id} "
        f"for a duration of {user_data.duration} minutes"
    )
    result = await lesson_workflow.arun(
        input=prompt,
        additional_data={"user_id": user_data.user_id},
        stream=False,
    )
    return LessonResponse(**json.loads(result.content))
