import asyncio
import os
import uuid

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.workflow import StepInput, StepOutput, Workflow
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from tools.answers_toolkit import AnswersToolkit
from utils.postgres_db import PostgresDB

load_dotenv()

# Email of the learner to plan for. Injected at runtime via the USER_EMAIL env var.
USER_EMAIL = os.getenv("USER_EMAIL", "nicolacroon@test.com")


class LessonStructure(BaseModel):
    """Structured output produced by the lesson-planning agent."""

    user_id: str = Field(description="User ID (email) of the learner")
    lesson_plan: str = Field(
        description="The full Spanish lesson plan, tailored to the learner's "
        "preferred learning method and fitting the requested duration"
    )
    duration: int = Field(description="Lesson duration in minutes (integer)")


lesson_planning_agent = Agent(
    name="LessonPlanningAgent",
    model=OpenRouter(id="qwen/qwen3.5-flash-02-23"),
    tools=[AnswersToolkit()],
    instructions=(
        "You design a single Spanish lesson plan for one learner.\n"
        "1. Call the `get_user_answers` tool with the learner's email address to "
        "fetch their saved preferences: `learning_method` and `ideal_duration`.\n"
        "2. Produce a detailed Spanish lesson plan that follows the learner's "
        "preferred `learning_method` and fits within `ideal_duration` minutes. "
        "The `ideal_duration` answer is free text (e.g. '30 minutes') — parse it "
        "into an integer number of minutes. If it is missing, default to 30.\n"
        "3. Return the result as structured JSON with these fields: `user_id` "
        "(the learner's email), `lesson_plan` (the full plan text), and "
        "`duration` (the lesson duration in minutes as an integer)."
    ),
    markdown=False,
    debug_mode=True,
    output_schema=LessonStructure,
    # Forcing a response_format for structured output stops this model from
    # emitting tool calls. With a parser_model set, the main model runs without
    # a response_format (so it can call get_user_answers and write free text),
    # and the parser_model then converts that text into LessonStructure.
    parser_model=OpenRouter(id="qwen/qwen3.5-flash-02-23"),
    use_json_mode=True,
)


async def push_to_db(step_input: StepInput) -> StepOutput:
    """Deterministically persist the generated lesson to Postgres.

    The lesson UUID is generated here, at write time, as required.
    """
    lesson = step_input.previous_step_content
    if not isinstance(lesson, LessonStructure):
        # The agent step failed or returned no structured output — do not write.
        return StepOutput(
            content=f"Skipped DB write: agent produced no lesson "
            f"({type(lesson).__name__}).",
            success=False,
        )

    # Trust the runtime-injected email, not the value echoed by the model.
    additional_data = step_input.additional_data or {}
    user_id = additional_data.get("user_id", lesson.user_id)

    lesson_uuid = uuid.uuid4()
    await PostgresDB().insert_lesson(
        user_id=user_id,
        lesson_uuid=lesson_uuid,
        lesson_script=lesson.lesson_plan,
        duration=lesson.duration,
    )
    return StepOutput(
        content=f"Saved lesson {lesson_uuid} for {user_id} "
        f"({lesson.duration} min)."
    )


workflow = Workflow(
    name="Lesson Planning Pipeline",
    steps=[
        lesson_planning_agent,
        push_to_db,
    ],
)


if __name__ == "__main__":
    asyncio.run(
        workflow.aprint_response(
            input=f"Create a Spanish lesson for the learner with email {USER_EMAIL}.",
            additional_data={"user_id": USER_EMAIL},
            stream=True,
        )
    )
