"""Lumi, the voice tutor: the lesson agent, its speech pipeline and the LiveKit server that runs one lesson per job.

Run with ``uv run python agent.py dev`` locally, or ``start`` in production.
"""

import asyncio
import logging
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

import psycopg
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    JobContext,
    JobProcess,
    ModelSettings,
    ToolError,
    stt,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import gradium, openai, silero

from tutor.languages import LanguageProfile, get_language
from tutor.lesson import LessonDispatch, LessonState, LessonTimer
from tutor.planner import LessonRecorder, PlannerClient
from tutor.prompt import TutorPrompt
from tutor.settings import settings
from tutor.steps import LessonSteps, LessonTimeUp
from tutor.store import LessonNotFoundError, LessonStore
from tutor.telemetry import flush_tracing, setup_tracing
from tutor.turn import BALANCED, InterimJoiner, load_vad, log_turn_metrics, turn_handling, yield_to_caller

logger = logging.getLogger("tutor")

REASONING_MODEL_PREFIXES = ("openai/gpt-5", "openai/gpt-6", "openai/o")


class Lumi(Agent):
    """Runs one planned lesson: says the opening line, coaches each step, then wraps up and ends the call.

    The steps are ``AgentTask``s in a ``TaskGroup`` (``tutor/steps.py``); code, not the model,
    decides when the lesson is over and what its outcome is.
    """

    WRAP_UP = (
        "The lesson is over. In {language} only: give a two-sentence spoken recap of what the "
        "learner practised today, praise their effort{left}, then say a warm goodbye, "
        "for example: '{goodbye}'"
    )

    def __init__(self, state: LessonState, recorder: LessonRecorder | None = None):
        """Build the lesson prompt, its steps and the end-call tool; without a recorder, progress stays in memory."""
        self.state = state
        self.language = get_language(state.plan.target_language)
        self.recorder = recorder or LessonRecorder(state)
        end_call = EndCallTool(
            extra_description="Use only when the learner clearly says they want to stop or leave.",
            end_instructions=f"Say a short warm goodbye in {self.language.name} only, "
            f"for example: '{self.language.goodbye}'",
            ignore_on_enter=True,
            on_tool_called=self._on_end_call,
        )
        self.steps = LessonSteps(state, self.language, self.recorder, end_call.tools)
        super().__init__(instructions=TutorPrompt.agent(self.language, state.plan), tools=end_call.tools)

    async def on_enter(self) -> None:
        """Say the planned opening line, run the steps until done or time is up, then wrap up."""
        await self.session.say(self.state.plan.opening_line)
        try:
            await self.steps.run(self.chat_ctx.copy(exclude_function_call=True, exclude_instructions=True))
        except LessonTimeUp:
            logger.info("Lesson %s ran out of time", self.state.plan.lesson_uuid)
        except ToolError:
            # The session closed mid-step (the SDK cancels the running task); shutdown finalizes the lesson.
            logger.info("Lesson %s closed during a step", self.state.plan.lesson_uuid)
            return
        await self.wrap_up()

    async def wrap_up(self) -> None:
        """Record the outcome, give a spoken recap and goodbye, then end the session."""
        await self.finalize()
        left = "" if self.state.all_done() else ", and say you will continue next time"
        await self.session.generate_reply(
            instructions=self.WRAP_UP.format(language=self.language.name, left=left, goodbye=self.language.goodbye)
        )
        self.session.shutdown()

    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterator[stt.SpeechEvent]:
        """Default STT, with Gradium's per-word interims joined into the line so far."""
        joiner = InterimJoiner()
        async for event in Agent.default.stt_node(self, audio, model_settings):
            yield joiner.push(event)

    async def finalize(self, summary: str | None = None) -> None:
        """Finish the lesson if still open: completed when every step is done, else abandoned."""
        if self.state.finish(summary):
            await self.recorder.finished()

    async def _on_end_call(self, _: Any) -> None:
        """Close the lesson when the learner leaves before the steps are done."""
        await self.finalize()


def build_llm(model: str = settings.voice_llm_model) -> openai.LLM:
    """Return the OpenRouter LLM: minimal reasoning for reasoning models, else low temperature."""
    options: dict[str, Any] = (
        {"reasoning_effort": "minimal"}
        if model.startswith(REASONING_MODEL_PREFIXES)
        else {"temperature": settings.voice_llm_temperature}
    )
    return openai.LLM.with_openrouter(model=model, app_name="AI Language Teacher", **options)


def build_session(language: LanguageProfile, vad: silero.VAD) -> AgentSession:
    """Return the speech pipeline for one target language: Gradium STT/TTS, OpenRouter LLM, fast turns."""
    session = AgentSession(
        stt=gradium.STT(language=language.code),
        llm=build_llm(),
        tts=gradium.TTS(voice_id=language.voice_id),
        vad=vad,
        turn_handling=turn_handling(BALANCED),
        conn_options=SessionConnectOptions(llm_conn_options=APIConnectOptions(max_retry=1)),
        user_away_timeout=None,
    )
    yield_to_caller(session)
    log_turn_metrics(session)
    return session


def prewarm(proc: JobProcess) -> None:
    """Load the VAD and start Langfuse tracing once per worker process, before any lesson.

    The lesson's goal and steps are per job, so the entrypoint loads them, alongside ``ctx.connect()``.
    """
    proc.userdata["vad"] = load_vad()
    proc.userdata["tracer_provider"] = setup_tracing()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=settings.agent_name)
async def lesson_entrypoint(ctx: JobContext) -> None:
    """Run one lesson: load its goal and steps from Postgres while joining the room, then teach it."""
    dispatch = LessonDispatch.model_validate_json(ctx.job.metadata)
    ctx.log_context_fields = {"lesson_uuid": dispatch.lesson_uuid, "user_id": dispatch.user_id}
    try:
        plan, _ = await asyncio.gather(LessonStore().load(dispatch.lesson_uuid), ctx.connect())
    except (LessonNotFoundError, psycopg.Error):
        logger.exception("Could not load lesson %s; leaving", dispatch.lesson_uuid)
        ctx.shutdown(reason="lesson not loaded")
        return
    state = LessonState(plan=plan)
    recorder = LessonRecorder(state, PlannerClient(), ctx.room)
    tutor = Lumi(state, recorder)
    session = build_session(tutor.language, ctx.proc.userdata["vad"])

    try:
        await asyncio.wait_for(ctx.wait_for_participant(), timeout=settings.learner_join_timeout_s)
    except asyncio.TimeoutError:
        logger.warning("Learner never joined lesson %s; leaving", plan.lesson_uuid)
        await recorder.aclose()
        ctx.shutdown(reason="learner never joined")
        return

    async def on_shutdown() -> None:
        """Record the lesson as abandoned or completed if it is still open, then flush traces."""
        await tutor.finalize()
        await recorder.aclose()
        await flush_tracing(ctx.proc.userdata.get("tracer_provider"))

    ctx.add_shutdown_callback(on_shutdown)
    await recorder.start()
    await session.start(agent=tutor, room=ctx.room)
    timer = LessonTimer(state, on_time_up=tutor.steps.stop).start()

    def on_close(_: object) -> None:
        """Stop the timer and end the job so no Gradium session outlives the learner."""
        timer.cancel()
        ctx.shutdown(reason="session closed")

    session.on("close", on_close)


if __name__ == "__main__":
    agents.cli.run_app(server)
