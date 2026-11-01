"""Lesson models: the planner's step-by-step lesson, the running lesson state, what it reports, and its timer."""

import asyncio
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field


class VocabularyItem(BaseModel):
    """A word or phrase with a short meaning."""

    term: str
    meaning: str


class LessonGoal(BaseModel):
    """What the whole lesson aims at, and the planner's guidance for running it."""

    aim: str
    prompt: str


class StepProgress(BaseModel):
    """A lesson step as the browser sees it: no coaching prompt."""

    position: int
    task: str
    done: bool = False


class LessonStep(StepProgress):
    """One planned step: the learner's task and how the tutor coaches it."""

    prompt: str
    evidence: str | None = None

    def progress(self) -> StepProgress:
        """The step without its prompt and evidence."""
        return StepProgress(position=self.position, task=self.task, done=self.done)


class StepResult(BaseModel):
    """What a finished step task returns: the learner's words and the words that came up."""

    evidence: str
    new_vocabulary: list[VocabularyItem] = Field(default_factory=list)


class LessonDispatch(BaseModel):
    """Dispatch metadata: which lesson the worker runs, plus the fields its traces are tagged with."""

    lesson_uuid: str
    user_id: str
    target_language: str
    native_language: str
    level: str
    title: str


class LessonPlan(BaseModel):
    """The lesson as the tutor runs it, read from Postgres when the job starts."""

    lesson_uuid: str
    user_id: str
    target_language: str
    native_language: str
    level: str
    title: str
    unit_title: str | None = None
    learning_method: str | None = None
    goal: LessonGoal
    opening_line: str
    duration_minutes: int = 10
    steps: list[LessonStep] = Field(min_length=1)
    vocabulary: list[VocabularyItem] = Field(default_factory=list)


class LessonView(BaseModel):
    """The lesson as the browser shows it before the first progress event."""

    lesson_uuid: str
    target_language: str
    title: str
    duration_minutes: int
    steps: list[StepProgress]


class PlannedLesson(BaseModel):
    """The lesson record inside the planner's ``/get_next_lesson/`` response (extra fields are ignored)."""

    lesson_uuid: str
    user_id: str
    target_language: str
    title: str
    duration: int = 10
    steps: list[StepProgress]


class NextLessonResponse(BaseModel):
    """The planner's ``/get_next_lesson/`` response, as far as the voice API needs it."""

    lesson: PlannedLesson
    native_language: str
    level: str

    def dispatch(self) -> LessonDispatch:
        """The metadata that dispatches the tutor for this lesson."""
        return LessonDispatch(
            lesson_uuid=self.lesson.lesson_uuid,
            user_id=self.lesson.user_id,
            target_language=self.lesson.target_language,
            native_language=self.native_language,
            level=self.level,
            title=self.lesson.title,
        )

    def view(self) -> LessonView:
        """The lesson for the browser."""
        lesson = self.lesson
        return LessonView(
            lesson_uuid=lesson.lesson_uuid,
            target_language=lesson.target_language,
            title=lesson.title,
            duration_minutes=lesson.duration,
            steps=lesson.steps,
        )


Outcome = Literal["completed", "abandoned"]


class ProgressEvent(BaseModel):
    """Payload published to the browser on every change."""

    lesson_uuid: str
    steps: list[StepProgress]
    outcome: Outcome | None
    summary: str | None
    new_vocabulary: list[VocabularyItem]


class FinishLessonRequest(BaseModel):
    """Body of the planner's ``/lessons/{uuid}/complete`` call."""

    status: Outcome
    summary: str | None
    new_vocabulary: list[VocabularyItem]


class LessonState(BaseModel):
    """Authoritative state of the running lesson; step tasks report into it, code closes it."""

    plan: LessonPlan
    started_at: float = Field(default_factory=time.monotonic)
    outcome: Outcome | None = None
    summary: str | None = None
    new_vocabulary: list[VocabularyItem] = Field(default_factory=list)

    @property
    def steps(self) -> list[LessonStep]:
        """The lesson steps in order."""
        return self.plan.steps

    def step(self, position: int) -> LessonStep:
        """Return the step at ``position``; unknown positions raise KeyError."""
        step = next((step for step in self.steps if step.position == position), None)
        if step is None:
            raise KeyError(position)
        return step

    def remaining(self) -> list[LessonStep]:
        """Steps not done yet."""
        return [step for step in self.steps if not step.done]

    def all_done(self) -> bool:
        """True when every step is done."""
        return not self.remaining()

    def elapsed_minutes(self) -> float:
        """Minutes since the lesson started."""
        return (time.monotonic() - self.started_at) / 60

    def minutes_left(self) -> float:
        """Minutes left in the planned duration (never negative)."""
        return max(0.0, self.plan.duration_minutes - self.elapsed_minutes())

    def mark_step_done(self, position: int, result: StepResult) -> LessonStep:
        """Mark a step done and collect its new words; a step already done keeps its first evidence."""
        step = self.step(position)
        if not step.done:
            step.done = True
            step.evidence = result.evidence
        known = {item.term.casefold() for item in self.new_vocabulary}
        self.new_vocabulary += [item for item in result.new_vocabulary if item.term.casefold() not in known]
        return step

    def finish(self, summary: str | None = None) -> bool:
        """Record the outcome once, from the steps; returns False if the lesson was already finished."""
        if self.outcome is not None:
            return False
        self.outcome = "completed" if self.all_done() else "abandoned"
        self.summary = summary or self.recap()
        return True

    def recap(self) -> str:
        """A short English summary of what was practised and what is left."""
        done = "; ".join(step.task for step in self.steps if step.done)
        left = "; ".join(step.task for step in self.remaining())
        practised = f"Practised: {done}." if done else "We only got started."
        return f"{practised} Next time: {left}." if left else practised

    def progress_event(self) -> ProgressEvent:
        """Snapshot published to the browser."""
        return ProgressEvent(
            lesson_uuid=self.plan.lesson_uuid,
            steps=[step.progress() for step in self.steps],
            outcome=self.outcome,
            summary=self.summary,
            new_vocabulary=self.new_vocabulary,
        )

    def finish_request(self) -> FinishLessonRequest:
        """The planner body that records the outcome."""
        assert self.outcome is not None, "finish() must run first"
        return FinishLessonRequest(status=self.outcome, summary=self.summary, new_vocabulary=self.new_vocabulary)


class LessonTimer:
    """Code-owned lesson clock: calls ``on_time_up`` once the planned duration is nearly over."""

    TIME_UP_AT = 0.95
    """Share of the planned duration after which the steps stop and the tutor wraps up."""

    def __init__(self, state: LessonState, on_time_up: Callable[[], None]):
        """Prepare a timer for this lesson; ``start`` runs it."""
        self.state = state
        self.on_time_up = on_time_up
        self._task: asyncio.Task[None] | None = None

    def start(self) -> "LessonTimer":
        """Start the clock in the background and return the timer."""
        self._task = asyncio.create_task(self._run())
        return self

    def cancel(self) -> None:
        """Stop the clock, for example when the session closes."""
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        """Wait out the lesson, then stop it unless it already ended."""
        await asyncio.sleep(self.state.plan.duration_minutes * 60 * self.TIME_UP_AT)
        if self.state.outcome is None:
            self.on_time_up()
