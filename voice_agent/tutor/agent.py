"""The voice tutor agent and its lesson-tracking tools."""

import asyncio
import logging
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import Agent, ModelSettings, RunContext, ToolError, function_tool, stt
from livekit.agents.beta.tools import EndCallTool

from tutor.languages import LanguageProfile
from tutor.lesson import LessonState, ProgressEvent, VocabularyItem
from tutor.planner_client import PlannerClient
from tutor.prompt import TutorPrompt
from tutor.transcript import InterimJoiner

logger = logging.getLogger(__name__)

Publisher = Callable[[ProgressEvent], Awaitable[None]]


async def _no_publish(_: ProgressEvent) -> None:
    """Default publisher used outside a room (tests, console)."""


class LessonRecorder:
    """Persists lesson progress to the planner and mirrors it to the browser.

    Objective writes run in the background so a tool returns to the model at once;
    ``finished`` waits for them, then re-sends every achieved objective and the outcome.
    Planner and publish failures are logged, never raised to the model: the in-session
    state stays authoritative, and the room may already be closed for the final event.
    """

    def __init__(self, state: LessonState, planner: PlannerClient | None, publish: Publisher):
        self.state = state
        self.planner = planner
        self.publish = publish
        self._pending: set[asyncio.Task[None]] = set()

    def objective_done(self, objective_id: str, evidence: str) -> None:
        """Persist and publish one achieved objective without blocking the caller."""
        task = asyncio.create_task(self._record_objective(objective_id, evidence))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def finished(self) -> None:
        """Wait for pending writes, re-send each achieved objective and the outcome, then publish."""
        await asyncio.gather(*self._pending)
        if self.planner is not None:
            for objective in self.state.objectives:
                if objective.done:
                    await self._safely(self.planner.complete_objective(
                        self.state.package.lesson_uuid, objective.id, objective.evidence or ""
                    ))
            await self._safely(self.planner.finish_lesson(self.state))
        await self._safely(self.publish(self.state.progress_event()))

    async def _record_objective(self, objective_id: str, evidence: str) -> None:
        if self.planner is not None:
            await self._safely(self.planner.complete_objective(
                self.state.package.lesson_uuid, objective_id, evidence
            ))
        await self._safely(self.publish(self.state.progress_event()))

    @staticmethod
    async def _safely(call: Awaitable[None]) -> None:
        """Await a planner or publish call, logging instead of raising on failure."""
        try:
            await call
        except Exception:
            logger.warning("Planner/publish call failed; lesson state kept in session", exc_info=True)


class TutorAgent(Agent):
    """Single-prompt tutor that runs one planned lesson in one language."""

    def __init__(
        self,
        language: LanguageProfile,
        state: LessonState,
        planner: PlannerClient | None = None,
        publish: Publisher = _no_publish,
    ):
        self.language = language
        self.state = state
        self.recorder = LessonRecorder(state, planner, publish)
        end_call = EndCallTool(
            extra_description="Use when the lesson has been completed with complete_lesson, "
            "or when the learner clearly says they want to stop or leave.",
            end_instructions=f"Say a short warm goodbye in {language.name} only, "
            f"for example: '{language.goodbye}'",
            ignore_on_enter=True,
            on_tool_called=self._on_end_call,
        )
        super().__init__(instructions=TutorPrompt.build(language, state.package), tools=end_call.tools)

    async def on_enter(self) -> None:
        """Greet the learner as soon as the tutor joins."""
        self.session.generate_reply(
            instructions=f"Greet the learner warmly in {self.language.name}, say in one simple "
            "sentence what today's lesson is about, and ask one easy personal question."
        )

    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterator[stt.SpeechEvent]:
        """Default STT, with Gradium's per-word interims joined into the line so far."""
        joiner = InterimJoiner()
        async for event in Agent.default.stt_node(self, audio, model_settings):
            yield joiner.push(event)

    @function_tool()
    async def mark_objective_done(self, context: RunContext, objective_id: str, evidence: str) -> dict[str, Any]:
        """Mark a lesson objective as achieved.

        Call only after the learner has said the target language for this objective
        themselves (at least once correctly, possibly after a correction).

        Args:
            objective_id: The objective id from the lesson plan, e.g. "o2".
            evidence: The learner's own words that show the objective is met.
        """
        try:
            self.state.mark_done(objective_id, evidence)
        except KeyError:
            raise ToolError(
                f"Unknown objective id {objective_id!r}. Valid ids: {[o.id for o in self.state.objectives]}"
            )
        self.recorder.objective_done(objective_id, evidence)
        return self.state.status_facts().model_dump()

    @function_tool()
    async def lesson_status(self, context: RunContext) -> dict[str, Any]:
        """Return the remaining objectives and the minutes elapsed and left."""
        return self.state.status_facts().model_dump()

    @function_tool()
    async def complete_lesson(
        self, context: RunContext, summary: str, new_vocabulary: list[VocabularyItem]
    ) -> dict[str, Any]:
        """Record the lesson as completed, right before saying goodbye.

        Allowed only when all objectives are done or time is up.

        Args:
            summary: Two sentences in English: what the learner practised and what to review.
            new_vocabulary: Words or phrases that came up today, each with a very short
                meaning in the learner's native language.
        """
        if not self.state.can_complete():
            raise ToolError(
                "Lesson not finished yet: keep teaching. "
                f"Status: {self.state.status_facts().model_dump_json()}"
            )
        if self.state.finish("completed", summary, new_vocabulary):
            await self.recorder.finished()
        return {"recorded": True, "next": "Give a 2-sentence recap, say goodbye, then call end_call."}

    async def _on_end_call(self, _: Any) -> None:
        """Close the lesson when the call ends without complete_lesson."""
        await self.finalize(summary="The learner ended the lesson early.")

    async def finalize(self, summary: str) -> None:
        """Finish the lesson if still open: completed when all objectives are met."""
        outcome = "completed" if self.state.all_done() else "abandoned"
        if self.state.finish(outcome, summary, []):
            await self.recorder.finished()
