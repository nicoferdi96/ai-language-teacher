"""Pydantic models shared by the planner agents, repository and API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

UnitKind = Literal["vocabulary", "grammar", "conversation"]
UnitStatus = Literal["pending", "in_progress", "done"]
LessonStatus = Literal["planned", "in_progress", "completed", "abandoned"]


class LearnerProfile(BaseModel):
    """Onboarding answers of one learner."""

    user_id: str
    target_language: str
    native_language: str
    learning_method: str | None = None


class PlanUnitDraft(BaseModel):
    """One unit of a learning plan as proposed by the curriculum agent."""

    title: str = Field(description="Short learner-facing title in English, e.g. 'Ordering at a café'")
    kind: UnitKind = Field(description="Main skill the unit trains")
    description: str = Field(description="One or two sentences: what the learner will be able to say")


class LearningPlanDraft(BaseModel):
    """Structured output of the curriculum agent."""

    level: str = Field(description="Starting CEFR level: A1, A2, B1, B2, C1 or C2")
    goal_summary: str = Field(description="One sentence summarising the learner's goal and preferred style")
    units: list[PlanUnitDraft] = Field(description="8 to 12 ordered units, easiest first", min_length=4)


class PlanUnit(PlanUnitDraft):
    """A persisted plan unit with its progress status."""

    unit_id: uuid.UUID
    position: int
    status: UnitStatus = "pending"


class LearningPlan(BaseModel):
    """A persisted learning plan with its units."""

    plan_id: uuid.UUID
    user_id: str
    target_language: str
    native_language: str
    level: str
    goal_summary: str
    units: list[PlanUnit]

    def next_unit(self) -> PlanUnit | None:
        """Return the first unit that is not done yet."""
        return next((unit for unit in self.units if unit.status != "done"), None)


class VocabularyItem(BaseModel):
    """A word or phrase with a simple meaning."""

    term: str = Field(description="The word or short phrase in the target language")
    meaning: str = Field(description="Very short meaning in the learner's native language")


class LessonObjective(BaseModel):
    """A checkable goal of a lesson."""

    id: str
    text: str
    done: bool = False
    evidence: str | None = None


class LessonBriefDraft(BaseModel):
    """Structured output of the lesson agent for the next ~10-minute lesson."""

    unit_position: int = Field(description="Position of the plan unit this lesson works on")
    title: str = Field(description="Short learner-facing lesson title in English")
    objectives: list[str] = Field(
        description="3 to 5 concrete, speakable goals, each checkable in conversation, "
        "e.g. 'Order a drink using \"quisiera\"'",
        min_length=2,
        max_length=6,
    )
    vocabulary: list[VocabularyItem] = Field(description="5 to 8 key words or phrases for this lesson")
    recap_terms: list[str] = Field(
        default_factory=list,
        description="Up to 4 terms from previous lessons to quickly review; empty if none",
    )
    tutor_guidelines: str = Field(
        description="Guidance for the voice tutor: warm-up idea, how to introduce and drill "
        "the objectives, a role-play scenario, and how to adapt to the learner's style"
    )


class LessonRecord(BaseModel):
    """A persisted lesson as stored in the ``lessons`` table."""

    lesson_uuid: uuid.UUID
    user_id: str
    plan_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    target_language: str
    title: str
    lesson_script: str
    duration: int = 10
    status: LessonStatus = "planned"
    objectives: list[LessonObjective] = Field(default_factory=list)
    vocabulary: list[VocabularyItem] = Field(default_factory=list)
    summary: str | None = None
    new_vocabulary: list[VocabularyItem] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


class LessonPackage(BaseModel):
    """Everything the voice tutor needs to run a lesson."""

    lesson: LessonRecord
    native_language: str
    learning_method: str | None = None
    level: str
    unit: PlanUnit | None = None


class ProgressSnapshot(BaseModel):
    """Where a learner stands: profile, plan and recent lessons."""

    profile: LearnerProfile
    plan: LearningPlan | None = None
    recent_lessons: list[LessonRecord] = Field(default_factory=list)
    open_lesson: LessonRecord | None = None


class LessonCompletion(BaseModel):
    """Payload the voice tutor sends when a lesson ends."""

    status: Literal["completed", "abandoned"]
    summary: str | None = None
    new_vocabulary: list[VocabularyItem] = Field(default_factory=list)


class ObjectiveUpdate(BaseModel):
    """Payload the voice tutor sends when an objective is achieved."""

    evidence: str = Field(description="What the learner said that shows the objective is met")
