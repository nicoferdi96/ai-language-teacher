"""Agno agents that design the learning plan and the next lesson."""

import json
import os

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from planner.languages import language_name
from planner.models import (
    LearnerProfile,
    LearningPlan,
    LearningPlanDraft,
    LessonBriefDraft,
    LessonRecord,
)
from planner.tracing import run_traced

PLANNER_MODEL = os.getenv("PLANNER_MODEL", "openai/gpt-5.4-nano")
PLANNER_TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.1"))
REASONING_MODEL_PREFIXES = ("openai/gpt-5", "openai/gpt-6", "openai/o")


def planner_model(model_id: str = PLANNER_MODEL) -> OpenRouter:
    """Return the OpenRouter model: minimal reasoning for reasoning models, else low temperature.

    GPT-5/6 reasoning models reject ``temperature``; OpenRouter would silently drop it.
    """
    if model_id.startswith(REASONING_MODEL_PREFIXES):
        return OpenRouter(id=model_id, reasoning_effort="minimal")
    return OpenRouter(id=model_id, temperature=PLANNER_TEMPERATURE)

CURRICULUM_INSTRUCTIONS = """\
You are a Curriculum Designer for a voice-first language-learning app.
Lessons are short spoken conversations of about 10 minutes with an AI tutor.

Design ONE long-term learning plan for the learner described in the input.
- Infer the starting CEFR level from the learner's own words. If they give no
  hint of prior knowledge, start at A1. Use these anchors:
  A1 = knows a few words or nothing; A2 = handles short routine exchanges;
  B1 = several years of study or can keep a simple conversation going on
  familiar topics; B2 = discusses work or abstract topics with some effort;
  C1+ = fluent, wants polish.
- Produce 8 to 12 ordered units, easiest first. Each unit must be teachable
  across one or two 10-minute spoken lessons.
- Mix kinds: vocabulary, grammar, conversation. Prefer practical, everyday
  situations. Respect the learner's preferred style: if they want lots of
  conversation, most units should be conversation; if they want grammar,
  give grammar more weight; if they mention a goal (travel, work, family),
  build the units around it.
- Titles are short and in English. Descriptions say what the learner will be
  able to SAY at the end of the unit.
- goal_summary is one sentence in English.
"""

LESSON_INSTRUCTIONS = """\
You are a Lesson Planner for a voice-first language-learning app. A separate
voice tutor will run the lesson you design, live, in about 10 minutes.

You receive the learner profile, the learning plan with the status of each
unit, the focus unit, and the most recent lessons (newest first) with which
objectives were met and which new words came up.

Design the NEXT lesson:
- Work on the focus unit given in the input; return its position as
  unit_position.
- If the most recent lesson on that unit was abandoned or left objectives
  unmet, carry those unmet objectives forward first.
- 3 to 5 objectives. Each must be small, concrete and checkable from what the
  learner SAYS, e.g. "Introduce yourself with your name and city" or
  "Ask for the price using 'combien'". Ten minutes is short: stay realistic
  for the learner's level.
- 5 to 8 vocabulary items in the target language. Each meaning MUST be
  written in the language named in "write_meanings_in" (the learner's native
  language), never in English unless that is the native language.
- recap_terms: up to 4 terms from previous lessons' new vocabulary or unmet
  objectives worth a quick review. Empty for a first lesson.
- tutor_guidelines (in English, 120-250 words): a quick personal warm-up idea,
  how to introduce each objective with simple examples, one short role-play
  scenario, and how to adapt to the learner's style and level. Mention 1-2
  typical mistakes speakers of the learner's native language make with this
  topic (false friends, word order, gender, pronunciation).
- title: short, friendly, English.

Language of your output: title, objectives and tutor_guidelines are ALWAYS in
English (the app's interface language), quoting target-language phrases inside
them, e.g. 'Ask for the bill with "La cuenta, por favor"'. Only the vocabulary
meanings use the language in "write_meanings_in".
"""


class CurriculumAgent:
    """Wraps the Agno agent that turns a learner profile into a learning plan."""

    def __init__(self, model_id: str = PLANNER_MODEL):
        self.agent = Agent(
            name="CurriculumAgent",
            model=planner_model(model_id),
            instructions=CURRICULUM_INSTRUCTIONS,
            output_schema=LearningPlanDraft,
            markdown=False,
        )

    @staticmethod
    def build_prompt(profile: LearnerProfile) -> str:
        """Render the learner profile as the agent input."""
        return json.dumps(
            {
                "target_language": language_name(profile.target_language),
                "native_language": profile.native_language,
                "how_they_want_to_learn": profile.learning_method
                or "No preference given: use balanced conversational practice.",
            },
            ensure_ascii=False,
        )

    async def design(self, profile: LearnerProfile) -> LearningPlanDraft:
        """Return a structured plan draft for the learner."""
        response = await run_traced(self.agent, self.build_prompt(profile))
        return LearningPlanDraft.model_validate(response.content)


class LessonAgent:
    """Wraps the Agno agent that reviews progress and designs the next lesson."""

    def __init__(self, model_id: str = PLANNER_MODEL):
        self.agent = Agent(
            name="LessonAgent",
            model=planner_model(model_id),
            instructions=LESSON_INSTRUCTIONS,
            output_schema=LessonBriefDraft,
            markdown=False,
        )

    @staticmethod
    def build_prompt(
        profile: LearnerProfile, plan: LearningPlan, recent_lessons: list[LessonRecord]
    ) -> str:
        """Render profile, plan progress and lesson history as the agent input."""
        focus = plan.next_unit() or plan.units[-1]
        return json.dumps(
            {
                "learner": {
                    "target_language": language_name(profile.target_language),
                    "native_language": profile.native_language,
                    "how_they_want_to_learn": profile.learning_method,
                    "level": plan.level,
                    "goal": plan.goal_summary,
                },
                "plan": [
                    unit.model_dump(include={"position", "title", "kind", "description", "status"})
                    for unit in plan.units
                ],
                "focus_unit_position": focus.position,
                "write_meanings_in": profile.native_language,
                "recent_lessons": [
                    {
                        "title": lesson.title,
                        "unit_position": next(
                            (unit.position for unit in plan.units if unit.unit_id == lesson.unit_id),
                            None,
                        ),
                        "status": lesson.status,
                        "objectives_met": [o.text for o in lesson.objectives if o.done],
                        "objectives_unmet": [o.text for o in lesson.objectives if not o.done],
                        "new_vocabulary": [item.term for item in lesson.new_vocabulary],
                        "summary": lesson.summary,
                    }
                    for lesson in recent_lessons
                ],
            },
            ensure_ascii=False,
            default=str,
        )

    async def design(
        self, profile: LearnerProfile, plan: LearningPlan, recent_lessons: list[LessonRecord]
    ) -> LessonBriefDraft:
        """Return a structured brief for the next lesson."""
        response = await run_traced(self.agent, self.build_prompt(profile, plan, recent_lessons))
        return LessonBriefDraft.model_validate(response.content)
