"""LiveKit agent server: one tutor session per dispatched lesson.

Run with ``uv run python -m tutor.worker dev`` (or ``start`` in production).
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess
from livekit.plugins import gradium, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from tutor.agent import TutorAgent
from tutor.languages import LanguageProfile, get_language
from tutor.lesson import LessonPackage, LessonState
from tutor.planner_client import PlannerClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger("tutor")

AGENT_NAME = "language-tutor"
PROGRESS_TOPIC = "lesson-progress"
LEARNER_JOIN_TIMEOUT_S = 30
VOICE_LLM_MODEL = os.getenv("VOICE_LLM_MODEL", "openai/gpt-5.4-nano")
VOICE_LLM_TEMPERATURE = float(os.getenv("VOICE_LLM_TEMPERATURE", "0.1"))
REASONING_MODEL_PREFIXES = ("openai/gpt-5", "openai/gpt-6", "openai/o")


class SessionFactory:
    """Builds the STT/LLM/TTS pipeline for a target language (all Gradium speech)."""

    @staticmethod
    def llm(model: str = VOICE_LLM_MODEL) -> openai.LLM:
        """Return the OpenRouter LLM: minimal reasoning for reasoning models, else low temperature."""
        options: dict[str, Any] = (
            {"reasoning_effort": "minimal"}
            if model.startswith(REASONING_MODEL_PREFIXES)
            else {"temperature": VOICE_LLM_TEMPERATURE}
        )
        return openai.LLM.with_openrouter(model=model, app_name="AI Language Teacher", **options)

    @classmethod
    def build(cls, language: LanguageProfile, vad: Any) -> AgentSession:
        """Return an AgentSession configured for one language."""
        return AgentSession(
            stt=gradium.STT(language=language.code),
            llm=cls.llm(),
            tts=gradium.TTS(voice_id=language.voice_id),
            vad=vad,
            turn_handling={"turn_detection": MultilingualModel()},
        )


class LessonClock:
    """Code-owned timer that tells the tutor when to wrap up and when to stop."""

    def __init__(self, session: AgentSession, agent: TutorAgent):
        self.session = session
        self.agent = agent

    async def run(self) -> None:
        """Nudge at 85% of the lesson and force the close at 120%."""
        duration = self.agent.state.package.duration_minutes * 60
        await asyncio.sleep(duration * 0.85)
        if self.agent.state.outcome is None:
            self.session.generate_reply(
                instructions="Time is almost up. Start the wrap-up now: a 2-sentence recap, "
                "call complete_lesson, then say goodbye and call end_call."
            )
        await asyncio.sleep(duration * 0.35)
        if self.agent.state.outcome is None:
            self.session.generate_reply(
                instructions="The lesson time is over. Call complete_lesson now, say goodbye "
                "in one sentence and call end_call."
            )


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    """Load the VAD once per worker process."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    """Run one lesson: metadata carries the planner's lesson package."""
    package = LessonPackage.model_validate(json.loads(ctx.job.metadata))
    language = get_language(package.target_language)
    ctx.log_context_fields = {"lesson_uuid": package.lesson_uuid, "user_id": package.user_id}
    planner = PlannerClient()
    state = LessonState(package=package)

    async def publish(event: dict[str, Any]) -> None:
        """Send lesson progress to the browser on the progress topic."""
        await ctx.room.local_participant.publish_data(
            json.dumps(event), reliable=True, topic=PROGRESS_TOPIC
        )

    agent = TutorAgent(language, state, planner, publish)
    session = SessionFactory.build(language, ctx.proc.userdata["vad"])

    async def on_shutdown() -> None:
        """Record the lesson as abandoned or completed if it is still open."""
        await agent.finalize(summary="You stopped before the end of the lesson. We'll pick up from here.")

    await ctx.connect()
    try:
        await asyncio.wait_for(ctx.wait_for_participant(), timeout=LEARNER_JOIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("Learner never joined lesson %s; leaving", package.lesson_uuid)
        ctx.shutdown(reason="learner never joined")
        return

    ctx.add_shutdown_callback(on_shutdown)
    await planner.start_lesson(package.lesson_uuid)
    await session.start(agent=agent, room=ctx.room)
    await publish(state.progress_event())
    clock = asyncio.create_task(LessonClock(session, agent).run())

    def on_close(_: Any) -> None:
        """Stop the clock and end the job so no Gradium session outlives the learner."""
        clock.cancel()
        ctx.shutdown(reason="session closed")

    session.on("close", on_close)


if __name__ == "__main__":
    agents.cli.run_app(server)
