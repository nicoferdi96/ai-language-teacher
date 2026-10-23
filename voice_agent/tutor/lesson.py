"""Lesson models: the planner's package, the running lesson state and what it reports."""

import time
from typing import Literal

from pydantic import BaseModel, Field


class Objective(BaseModel):
    """A checkable lesson goal."""

    id: str
    text: str
    done: bool = False
    evidence: str | None = None


class VocabularyItem(BaseModel):
    """A word or phrase with a short meaning."""

    term: str
    meaning: str


class PlannedLesson(BaseModel):
    """The lesson record inside the planner's ``/get_next_lesson/`` response."""

    lesson_uuid: str
    user_id: str
    target_language: str
    title: str
    lesson_script: str
    duration: int = 10
    objectives: list[Objective] = Field(default_factory=list)
    vocabulary: list[VocabularyItem] = Field(default_factory=list)


class PlannedUnit(BaseModel):
    """The plan unit a lesson belongs to."""

    title: str


class NextLessonResponse(BaseModel):
    """The planner's ``/get_next_lesson/`` response (extra fields are ignored)."""

    lesson: PlannedLesson
    native_language: str
    level: str
    learning_method: str | None = None
    unit: PlannedUnit | None = None


class LessonPackage(BaseModel):
    """The lesson as the tutor runs it; sent to the worker as dispatch metadata."""

    lesson_uuid: str
    user_id: str
    target_language: str
    native_language: str
    level: str
    title: str
    unit_title: str | None = None
    learning_method: str | None = None
    guidelines: str
    duration_minutes: int = 10
    objectives: list[Objective]
    vocabulary: list[VocabularyItem] = Field(default_factory=list)

    @classmethod
    def from_planner(cls, response: NextLessonResponse) -> "LessonPackage":
        """Build a package from the planner's next-lesson response."""
        lesson = response.lesson
        return cls(
            lesson_uuid=lesson.lesson_uuid,
            user_id=lesson.user_id,
            target_language=lesson.target_language,
            native_language=response.native_language,
            level=response.level,
            title=lesson.title,
            unit_title=response.unit.title if response.unit else None,
            learning_method=response.learning_method,
            guidelines=lesson.lesson_script,
            duration_minutes=lesson.duration,
            objectives=lesson.objectives,
            vocabulary=lesson.vocabulary,
        )


Outcome = Literal["completed", "abandoned"]


class ObjectiveRef(BaseModel):
    """An objective as the model sees it in status facts."""

    id: str
    text: str


class StatusFacts(BaseModel):
    """Compact progress facts returned to the model by the lesson tools."""

    remaining_objectives: list[ObjectiveRef]
    done_objectives: list[str]
    minutes_elapsed: float
    minutes_left: float


class ProgressEvent(BaseModel):
    """Payload published to the browser on every change."""

    lesson_uuid: str
    objectives: list[Objective]
    outcome: Outcome | None
    summary: str | None
    new_vocabulary: list[VocabularyItem]


class FinishLessonRequest(BaseModel):
    """Body of the planner's ``/lessons/{uuid}/complete`` call."""

    status: Outcome
    summary: str | None
    new_vocabulary: list[VocabularyItem]


class LessonState(BaseModel):
    """Authoritative state of the running lesson; tools read and change it here."""

    package: LessonPackage
    started_at: float = Field(default_factory=time.monotonic)
    outcome: Outcome | None = None
    summary: str | None = None
    new_vocabulary: list[VocabularyItem] = Field(default_factory=list)

    @property
    def objectives(self) -> list[Objective]:
        """The lesson objectives in order."""
        return self.package.objectives

    def remaining(self) -> list[Objective]:
        """Objectives not achieved yet."""
        return [objective for objective in self.objectives if not objective.done]

    def all_done(self) -> bool:
        """True when every objective is achieved."""
        return not self.remaining()

    def elapsed_minutes(self) -> float:
        """Minutes since the lesson started."""
        return (time.monotonic() - self.started_at) / 60

    def minutes_left(self) -> float:
        """Minutes left in the planned duration (never negative)."""
        return max(0.0, self.package.duration_minutes - self.elapsed_minutes())

    def can_complete(self) -> bool:
        """A lesson may be completed when all objectives are met or time is nearly up."""
        return self.all_done() or self.minutes_left() <= 1.5

    def mark_done(self, objective_id: str, evidence: str) -> Objective:
        """Mark an objective achieved; unknown ids raise KeyError, repeats are no-ops."""
        objective = next((o for o in self.objectives if o.id == objective_id), None)
        if objective is None:
            raise KeyError(objective_id)
        if not objective.done:
            objective.done = True
            objective.evidence = evidence
        return objective

    def finish(self, outcome: Outcome, summary: str | None, new_vocabulary: list[VocabularyItem]) -> bool:
        """Record the outcome once; returns False if the lesson was already finished."""
        if self.outcome is not None:
            return False
        self.outcome = outcome
        self.summary = summary
        self.new_vocabulary = new_vocabulary
        return True

    def status_facts(self) -> StatusFacts:
        """Compact facts about progress for the model."""
        return StatusFacts(
            remaining_objectives=[ObjectiveRef(id=o.id, text=o.text) for o in self.remaining()],
            done_objectives=[o.id for o in self.objectives if o.done],
            minutes_elapsed=round(self.elapsed_minutes(), 1),
            minutes_left=round(self.minutes_left(), 1),
        )

    def progress_event(self) -> ProgressEvent:
        """Snapshot published to the browser."""
        return ProgressEvent(
            lesson_uuid=self.package.lesson_uuid,
            objectives=self.objectives,
            outcome=self.outcome,
            summary=self.summary,
            new_vocabulary=self.new_vocabulary,
        )

    def finish_request(self) -> FinishLessonRequest:
        """The planner body that records the outcome."""
        assert self.outcome is not None, "finish() must run first"
        return FinishLessonRequest(status=self.outcome, summary=self.summary, new_vocabulary=self.new_vocabulary)
