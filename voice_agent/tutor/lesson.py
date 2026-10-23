"""In-session lesson state: objectives, clock and outcome."""

import time
from dataclasses import dataclass, field
from typing import Any, Literal

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


class LessonPackage(BaseModel):
    """The lesson as prepared by the planner service."""

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
    def from_planner(cls, payload: dict[str, Any]) -> "LessonPackage":
        """Build a package from the planner's ``/get_next_lesson/`` response."""
        lesson = payload["lesson"]
        return cls(
            lesson_uuid=str(lesson["lesson_uuid"]),
            user_id=lesson["user_id"],
            target_language=lesson["target_language"],
            native_language=payload["native_language"],
            level=payload["level"],
            title=lesson["title"],
            unit_title=(payload.get("unit") or {}).get("title"),
            learning_method=payload.get("learning_method"),
            guidelines=lesson["lesson_script"],
            duration_minutes=lesson.get("duration", 10),
            objectives=lesson["objectives"],
            vocabulary=lesson.get("vocabulary", []),
        )


Outcome = Literal["completed", "abandoned"]


@dataclass
class LessonState:
    """Authoritative state of the running lesson; tools read and change it here."""

    package: LessonPackage
    started_at: float = field(default_factory=time.monotonic)
    outcome: Outcome | None = None
    summary: str | None = None
    new_vocabulary: list[VocabularyItem] = field(default_factory=list)

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

    def status_facts(self) -> dict[str, Any]:
        """Compact facts about progress for the model."""
        return {
            "remaining_objectives": [o.model_dump(include={"id", "text"}) for o in self.remaining()],
            "done_objectives": [o.id for o in self.objectives if o.done],
            "minutes_elapsed": round(self.elapsed_minutes(), 1),
            "minutes_left": round(self.minutes_left(), 1),
        }

    def progress_event(self) -> dict[str, Any]:
        """Payload published to the browser on every change."""
        return {
            "lesson_uuid": self.package.lesson_uuid,
            "objectives": [o.model_dump() for o in self.objectives],
            "outcome": self.outcome,
            "summary": self.summary,
            "new_vocabulary": [item.model_dump() for item in self.new_vocabulary],
        }
