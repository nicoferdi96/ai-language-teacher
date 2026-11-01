"""Lumi, the voice tutor: the agent, its speech pipeline and the LiveKit server that runs one lesson per job.

Run with ``uv run python agent.py dev`` locally, or ``start`` in production.
"""

import asyncio
import logging
from typing import Any

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    JobContext,
    JobProcess,
    NotGivenOr,
    RunContext,
    ToolError,
    function_tool,
    llm,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN
from livekit.agents.utils import is_given
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import anthropic, cartesia, silero, soniox

from pydantic import SecretStr

from tutor.languages import LanguageProfile, get_language
from tutor.lesson import LessonPackage, LessonState, LessonTimer, VocabularyItem
from tutor.planner import LessonRecorder, PlannerClient
from tutor.prompt import TutorPrompt
from tutor.settings import settings
from tutor.telemetry import flush_tracing, record_stt_usage, setup_tracing
from tutor.turn import BALANCED, load_vad, log_turn_metrics, turn_handling, yield_to_caller

logger = logging.getLogger("tutor")


class Lumi(Agent):
    """Single-prompt tutor that runs one planned lesson in one language and ticks off its objectives."""

    def __init__(self, state: LessonState, recorder: LessonRecorder | None = None):
        """Build the lesson prompt and tools; without a recorder, progress stays in memory."""
        self.state = state
        self.language = get_language(state.package.target_language)
        self.recorder = recorder or LessonRecorder(state)
        end_call = EndCallTool(
            extra_description="Use when the lesson has been completed with complete_lesson, "
            "or when the learner clearly says they want to stop or leave.",
            end_instructions=f"Say a short warm goodbye in {self.language.name} only, "
            f"for example: '{self.language.goodbye}'",
            ignore_on_enter=True,
            on_tool_called=self._on_end_call,
        )
        super().__init__(instructions=TutorPrompt.build(self.language, state.package), tools=end_call.tools)

    async def on_enter(self) -> None:
        """Greet the learner as soon as the tutor joins."""
        self.session.generate_reply(
            instructions=f"Greet the learner warmly in {self.language.name}, say in one simple "
            "sentence what today's lesson is about, and ask one easy personal question."
        )

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

    async def finalize(self, summary: str) -> None:
        """Finish the lesson if still open: completed when all objectives are met, else abandoned."""
        outcome = "completed" if self.state.all_done() else "abandoned"
        if self.state.finish(outcome, summary, []):
            await self.recorder.finished()

    async def _on_end_call(self, _: Any) -> None:
        """Close the lesson when the call ends without complete_lesson."""
        await self.finalize(summary="The learner ended the lesson early.")


def secret(value: SecretStr | None) -> str | None:
    """Return a configured key, or None so the plugin falls back to its own env var."""
    return value.get_secret_value() if value else None


class TutorLLM(anthropic.LLM):
    """Claude with a fixed effort and thinking mode on every request.

    ``AgentSession`` calls ``chat`` without ``extra_kwargs``, so the plugin has no other place for
    these. Adaptive thinking at low effort costs about 0.5 s of first token over thinking off,
    but with thinking off Haiku 5.5 skipped ``mark_objective_done`` on a correct answer.
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
    """Load the VAD and start Langfuse tracing once per worker process, before any lesson."""
    proc.userdata["vad"] = load_vad()
    proc.userdata["tracer_provider"] = setup_tracing()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=settings.agent_name)
async def lesson_entrypoint(ctx: JobContext) -> None:
    """Run one lesson: the dispatch metadata carries the planner's lesson package."""
    package = LessonPackage.model_validate_json(ctx.job.metadata)
    ctx.log_context_fields = {"lesson_uuid": package.lesson_uuid, "user_id": package.user_id}
    state = LessonState(package=package)
    recorder = LessonRecorder(state, PlannerClient(), ctx.room)
    tutor = Lumi(state, recorder)
    session = build_session(tutor.language, ctx.proc.userdata["vad"])

    await ctx.connect()
    try:
        await asyncio.wait_for(ctx.wait_for_participant(), timeout=settings.learner_join_timeout_s)
    except asyncio.TimeoutError:
        logger.warning("Learner never joined lesson %s; leaving", package.lesson_uuid)
        await recorder.aclose()
        ctx.shutdown(reason="learner never joined")
        return

    async def on_shutdown() -> None:
        """Record the lesson as abandoned or completed if it is still open, then its STT usage, then flush traces."""
        await tutor.finalize(summary="You stopped before the end of the lesson. We'll pick up from here.")
        await recorder.aclose()
        tracer_provider = ctx.proc.userdata.get("tracer_provider")
        record_stt_usage(tracer_provider, session.usage)
        await flush_tracing(tracer_provider)

    ctx.add_shutdown_callback(on_shutdown)
    await recorder.start()
    await session.start(agent=tutor, room=ctx.room)
    timer = LessonTimer(session, state).start()

    def on_close(_: object) -> None:
        """Stop the timer and end the job so no speech session outlives the learner."""
        timer.cancel()
        ctx.shutdown(reason="session closed")

    session.on("close", on_close)


if __name__ == "__main__":
    agents.cli.run_app(server)
