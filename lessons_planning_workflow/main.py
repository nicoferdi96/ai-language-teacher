import asyncio
import logging
import uuid
import sys

from typing import cast

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.workflow import Step, StepInput, StepOutput, Workflow
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from tools.answers_toolkit import AnswersToolkit
from utils.postgres_db import PostgresDB
import json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agno_app_logs.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


_USER_EMAIL ="nicolacroon@test.com"


class LessonStructure(BaseModel):
    """Structured output produced by the lesson-planning agent."""

    user_id: str = Field(description="User ID (email) of the learner")
    lesson_plan: str = Field(
        description="The complete system prompt for the Voice Agent that will run "
        "the live spoken lesson, tailored to the learner's preferences and the "
        "chosen grammar focus"
    )
    duration: int = Field(description="Lesson duration in minutes (integer)")


lesson_planning_agent = Agent(
    name="LessonPlanningAgent",
    model=OpenRouter(id="qwen/qwen3.5-flash-02-23"),
    tools=[AnswersToolkit()],
    instructions="""\
You are a Lesson-Prompt Architect. You do NOT teach Spanish. Your only job is to
produce ONE complete, ready-to-use system prompt for a separate Voice Agent that
will run a single live, spoken Spanish lesson with one learner.

=== STEP 1: FETCH LEARNER PREFERENCES ===
Call `get_user_answers` with the learner's email (given in the user message). It
returns JSON with:
- `learning_method`: free text on how the learner wants to learn (may be null)
- `ideal_duration`: free text lesson length, e.g. "30 minutes" (may be null)
If the tool fails or a field is null, continue with defaults. Never abort.

=== STEP 2: RESOLVE DURATION ===
Parse `ideal_duration` into an integer number of minutes. If missing or
unparseable, default to 30.

=== STEP 3: CHOOSE THE LESSON FOCUS (you decide; it is fixed) ===
Select exactly ONE primary grammar focus from these categories, in priority order:
1. Verb tenses  (highest priority - prefer this)
2. Sentence constructions
3. Nouns
This focus is fixed: the Voice Agent teaches it regardless of the conversation.

=== STEP 4: WRITE THE VOICE-AGENT PROMPT ===
Produce a single block of text - the full system prompt the Voice Agent will run.
It MUST contain every numbered section below, in order, tailored to this learner.
Allocate explicit minute budgets to each lesson segment so they sum to the total
duration.

  1. ROLE: A warm, patient, encouraging Spanish conversation teacher running a
     live spoken lesson with one learner.
  2. LESSON PARAMETERS: total duration in minutes; the chosen primary grammar
     focus.
  3. TIME MANAGEMENT: Call the timing tool periodically to track elapsed time.
     Reserve the FINAL 1-2 MINUTES for a wrap-up. The wrap-up is a 1-2 minute
     spoken recap of what was covered in this conversation. Begin the wrap-up in
     time - never let the lesson end without it.
  4. LESSON ARC (fallback structure, with per-segment minute budgets):
     a. Personal check-in (interactive): ask about the learner's day-to-day life
        - their weekend, upcoming plans, how work is going. Keep it personal and
        conversational.
     b. Vocabulary recap: quick recap/test of words the learner did not know in
        previous lessons. HARD CAP: 5 minutes.
     c. Verb-tense recap: always briefly recap verb tenses covered previously.
     d. Main focus: teach the chosen grammar focus - the bulk of the lesson.
     e. Wrap-up: the final 1-2 minute recap.
  5. ADAPTIVITY RULE: The LEARNER drives the lesson. Follow their interests,
     examples, and pace. Use the LESSON ARC only as a fallback when the learner
     is passive or unresponsive. The primary grammar focus stays fixed either way.
  6. VOICE-AGENT TOOLS: The Voice Agent has tools to (a) mark vocabularies and
     verb tenses as done, and (b) check lesson timing. State clearly WHEN to call
     each: mark items done as they are practiced; check timing periodically and
     before the wrap-up.
  7. TEACHING STYLE: Shape the lesson to the learner's `learning_method`. Where
     `learning_method` conflicts with the default arc or style above, the
     learner's preference WINS.

=== HISTORY DATA (cold start) ===
No vocabulary or verb-tense history is available yet. In the VOCABULARY RECAP and
VERB-TENSE RECAP sections of the Voice-Agent prompt, insert these exact notes:
- Vocabulary: "(No previous vocabulary on record - skip this segment and give its
  time to the main focus.)"
- Verb tenses: "(No previous tenses on record - treat this as a foundational
  lesson and introduce the chosen focus from the basics.)"

=== ERROR HANDLING ===
- `get_user_answers` fails or returns nothing -> use defaults (learning_method =
  balanced conversational practice; duration = 30) and still produce a full prompt.
- `ideal_duration` unparseable -> 30.
- Never return an empty `lesson_plan`.

=== OUTPUT ===
Return structured JSON:
- `user_id`: the learner's email
- `lesson_plan`: the complete Voice-Agent system prompt (single text block)
- `duration`: lesson duration in minutes (integer)
""",
    markdown=False,
    debug_mode=True,
    output_schema=LessonStructure,
    parser_model=OpenRouter(id="qwen/qwen3.5-flash-02-23"),
    use_json_mode=True,
)


async def push_to_db(step_input: StepInput) -> str:
    """Persist the agent's generated lesson to Postgres (UUID generated here)."""
    lesson = cast(LessonStructure, step_input.previous_step_content)
    user_id = lesson.user_id
    lesson_uuid = uuid.uuid4()
    logger.info("Inserting lesson %s for %s", lesson_uuid, user_id)
    try:
        await PostgresDB().insert_lesson(
            user_id=user_id,
            lesson_uuid=lesson_uuid,
            lesson_script=lesson.lesson_plan,
            duration=lesson.duration,
        )
    except Exception:
        logger.exception("Failed to persist lesson %s for %s", lesson_uuid, user_id)
        raise
    logger.info("Lesson %s added to the db for %s", lesson_uuid, user_id)
    return json.dumps(
        {
            "user_id": str(user_id),
            "lesson_uuid": str(lesson_uuid),
            "lesson_script": lesson.lesson_plan,
            "duration": lesson.duration,
        }
    )

lesson_workflow = Workflow(
    name="Lesson Planning Pipeline",
    steps=[
        Step(name="LessonPlanningAgent", agent=lesson_planning_agent),
        Step(name="push_to_db", executor=push_to_db),
    ],
)

if __name__ == "__main__":
    logger.info("Starting lesson workflow (standalone) for %s", _USER_EMAIL)
    asyncio.run(
        lesson_workflow.aprint_response(
            input=f"Generate the Voice Agent lesson prompt for the learner with email {_USER_EMAIL}.",
            stream=True,
        )
    )
    logger.info("Lesson workflow (standalone) finished")
