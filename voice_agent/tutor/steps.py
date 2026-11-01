"""The lesson's planned steps as LiveKit tasks: one ``AgentTask`` per step, run in order by a ``TaskGroup``.

The group shares the whole conversation with every step, so the learner can go back to an
earlier one (the group's ``out_of_scope`` tool). Each step drops tool calls from the history it
inherits: the steps see what was said, not how earlier steps were ticked off.
"""

import logging

from livekit.agents import AgentTask, RunContext, function_tool, llm
from livekit.agents.beta.workflows import TaskCompletedEvent, TaskGroup

from tutor.languages import LanguageProfile
from tutor.lesson import LessonState, LessonStep, StepResult, VocabularyItem
from tutor.planner import LessonRecorder
from tutor.prompt import TutorPrompt

logger = logging.getLogger(__name__)


class LessonTimeUp(Exception):
    """Ends the running step, and with it the step group, when the lesson clock runs out."""


class LessonStepTask(AgentTask[StepResult]):
    """Coaches the learner through one planned step and returns what they produced."""

    INTRODUCE = "Lead into this step in one or two short sentences, following its instructions."

    def __init__(self, step: LessonStep, instructions: str, tools: list[llm.Tool], introduce: bool):
        """Run ``step`` with its own prompt; ``introduce`` makes the tutor speak first on entry."""
        super().__init__(instructions=instructions, tools=tools)
        self.step = step
        self._introduce = introduce

    async def on_enter(self) -> None:
        """Keep the shared history without tool calls, then lead into the step unless the learner speaks first."""
        await self.update_chat_ctx(self.chat_ctx.copy(exclude_function_call=True))
        if self._introduce:
            self.session.generate_reply(instructions=self.INTRODUCE)

    @function_tool()
    async def complete_step(self, context: RunContext, evidence: str, new_vocabulary: list[VocabularyItem]) -> None:
        """Mark the current step as done and move on to the next one.

        Call only after the learner has said this step's target language themselves
        (at least once correctly, possibly after a correction).

        Args:
            evidence: The learner's own words that show the step is done.
            new_vocabulary: Words or phrases that came up in this step, each with a very
                short meaning in the learner's native language. Empty if none.
        """
        if not self.done():
            self.complete(StepResult(evidence=evidence, new_vocabulary=new_vocabulary))


class LessonSteps:
    """Runs the lesson's remaining steps as one TaskGroup and reports each finished step."""

    def __init__(
        self, state: LessonState, language: LanguageProfile, recorder: LessonRecorder, tools: list[llm.Tool]
    ):
        """Build steps for this lesson; ``tools`` (end_call) are offered in every step."""
        self._state = state
        self._language = language
        self._recorder = recorder
        self._tools = tools
        self._current: LessonStepTask | None = None
        self._entered: set[int] = set()
        self._opening_step: int | None = None

    async def run(self, chat_ctx: llm.ChatContext) -> None:
        """Run every step not done yet, in order; raises LessonTimeUp when ``stop`` cuts the lesson short."""
        remaining = self._state.remaining()
        if not remaining:
            return
        self._opening_step = remaining[0].position
        group = TaskGroup(chat_ctx=chat_ctx, summarize_chat_ctx=False, on_task_completed=self._on_step_done)
        for step in remaining:
            group.add(lambda step=step: self._enter(step), id=self.task_id(step), description=step.task)
        await group

    def stop(self) -> None:
        """End the running step with LessonTimeUp, so the group stops and the lesson can wrap up."""
        if self._current is not None and not self._current.done():
            self._current.complete(LessonTimeUp())

    @staticmethod
    def task_id(step: LessonStep) -> str:
        """The group's id for a step, also what ``out_of_scope`` takes."""
        return f"step_{step.position}"

    def _enter(self, step: LessonStep) -> LessonStepTask:
        """Create the task for a step; the group calls this again when the learner goes back to it.

        The opening step stays quiet on its first entry: the learner is answering the opening line.
        A revisited step is told that earlier answers don't count, so it practises before ticking.
        """
        revisit = step.position in self._entered
        task = LessonStepTask(
            step,
            instructions=TutorPrompt.step(self._language, self._state.plan, step, revisit=revisit),
            tools=list(self._tools),
            introduce=step.position != self._opening_step or revisit,
        )
        self._entered.add(step.position)
        self._current = task
        return task

    async def _on_step_done(self, event: TaskCompletedEvent) -> None:
        """Record the finished step in the lesson state, then persist and publish it."""
        step = event.agent_task.step
        self._state.mark_step_done(step.position, event.result)
        self._recorder.step_done(step.position)
        logger.info("Step %d of lesson %s done", step.position, self._state.plan.lesson_uuid)
