"""Lumi, the voice tutor: the lesson agent, its speech pipeline and the LiveKit server that runs one lesson per job.

Run with ``uv run python agent.py dev`` locally, or ``start`` in production.
"""

import asyncio
import logging
from typing import Any

import psycopg
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    JobContext,
    JobProcess,
    NotGivenOr,
    ToolError,
    llm,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN
from livekit.agents.utils import is_given
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import anthropic, cartesia, silero, soniox

from pydantic import SecretStr

from tutor.languages import LanguageProfile, get_language
from tutor.lesson import LessonDispatch, LessonState, LessonTimer
from tutor.planner import LessonRecorder, PlannerClient
from tutor.prompt import TutorPrompt
from tutor.settings import settings
from tutor.steps import LessonSteps, LessonTimeUp
from tutor.store import LessonNotFoundError, LessonStore
from tutor.telemetry import flush_tracing, record_stt_usage, setup_tracing
from tutor.turn import BALANCED, load_vad, log_turn_metrics, turn_handling, yield_to_caller

logger = logging.getLogger("tutor")


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

    async def finalize(self, summary: str | None = None) -> None:
        """Finish the lesson if still open: completed when every step is done, else abandoned."""
        if self.state.finish(summary):
            await self.recorder.finished()

    async def _on_end_call(self, _: Any) -> None:
        """Close the lesson when the learner leaves before the steps are done."""
        await self.finalize()


def secret(value: SecretStr | None) -> str | None:
    """Return a configured key, or None so the plugin falls back to its own env var."""
    return value.get_secret_value() if value else None


class TutorLLM(anthropic.LLM):
    """Claude with a fixed effort and thinking mode on every request.

    ``AgentSession`` calls ``chat`` without ``extra_kwargs``, so the plugin has no other place for
    these. Adaptive thinking at low effort costs about 0.5 s of first token over thinking off,
    but with thinking off Haiku 5.5 skipped ticking a goal on a correct answer.
    Claude 5 models reject ``temperature``, so it is dropped even when a caller such as
    LiveKit's ``judge`` adds one.
    """

    def __init__(
        self,
        *,
        effort: str = settings.voice_llm_effort,
        thinking: str = settings.voice_llm_thinking,
        **kwargs: Any,
    ):
        """Build the Anthropic LLM and remember the effort and thinking mode to send."""
        super().__init__(**kwargs)
        self.effort, self.thinking = effort, thinking

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> anthropic.LLMStream:
        """Start a request with the configured thinking mode and effort."""
        extra = {
            "thinking": {"type": self.thinking},
            "output_config": {"effort": self.effort},
            **(extra_kwargs if is_given(extra_kwargs) else {}),
        }
        extra.pop("temperature", None)
        return super().chat(
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
            extra_kwargs=extra,
        )


def build_llm(model: str = settings.voice_llm_model) -> TutorLLM:
    """Return Claude for the tutor, caching the lesson prompt and tools across turns."""
    return TutorLLM(
        model=model,
        api_key=secret(settings.anthropic_api_key) or NOT_GIVEN,
        max_tokens=settings.voice_llm_max_tokens,
        caching="ephemeral",
    )


def build_stt(language: LanguageProfile) -> soniox.STT:
    """Return Soniox STT hinted (not locked) to the target language, so native-language slips still transcribe."""
    return soniox.STT(
        api_key=secret(settings.soniox_api_key),
        params=soniox.STTOptions(
            model=settings.stt_model,
            language_hints=[language.code],
            max_endpoint_delay_ms=settings.stt_max_endpoint_delay_ms,
        ),
    )


def build_tts(language: LanguageProfile) -> cartesia.TTS:
    """Return Cartesia TTS speaking the target language in the tutor's voice."""
    return cartesia.TTS(
        api_key=secret(settings.cartesia_api_key),
        model=settings.tts_model,
        voice=settings.tts_voice,
        language=language.code,
    )


def build_session(language: LanguageProfile, vad: silero.VAD) -> AgentSession:
    """Return the speech pipeline for one target language: Soniox STT, Claude, Cartesia TTS, fast turns."""
    session = AgentSession(
        stt=build_stt(language),
        llm=build_llm(),
        tts=build_tts(language),
        vad=vad,
        turn_handling=turn_handling(BALANCED),
        conn_options=SessionConnectOptions(llm_conn_options=APIConnectOptions(max_retry=1)),
        user_away_timeout=None,
        use_tts_aligned_transcript=True,
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
        """Record the lesson as abandoned or completed if it is still open, then its STT usage, then flush traces."""
        await tutor.finalize()
        await recorder.aclose()
        tracer_provider = ctx.proc.userdata.get("tracer_provider")
        record_stt_usage(tracer_provider, session.usage)
        await flush_tracing(tracer_provider)

    ctx.add_shutdown_callback(on_shutdown)
    await recorder.start()
    await session.start(agent=tutor, room=ctx.room)
    timer = LessonTimer(state, on_time_up=tutor.steps.stop).start()

    def on_close(_: object) -> None:
        """Stop the timer and end the job so no speech session outlives the learner."""
        timer.cancel()
        ctx.shutdown(reason="session closed")

    session.on("close", on_close)


if __name__ == "__main__":
    agents.cli.run_app(server)
