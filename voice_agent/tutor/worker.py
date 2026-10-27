"""LiveKit agent server: one tutor session per dispatched lesson.

Run with ``uv run python -m tutor.worker dev`` (or ``start`` in production).
"""

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentServer, JobContext, JobProcess

from tutor.agent import TutorAgent
from tutor.clock import LessonClock
from tutor.languages import get_language
from tutor.lesson import LessonPackage, LessonState, ProgressEvent
from tutor.planner_client import PlannerClient
from tutor.session import build_session, load_vad
from tutor.telemetry import flush_tracing, setup_tracing

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger("tutor")

AGENT_NAME = "language-tutor"
PROGRESS_TOPIC = "lesson-progress"
LEARNER_JOIN_TIMEOUT_S = 30

server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    """Load the VAD and start Langfuse tracing once per worker process, before any lesson."""
    proc.userdata["vad"] = load_vad()
    proc.userdata["tracer_provider"] = setup_tracing()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    """Run one lesson: metadata carries the planner's lesson package."""
    package = LessonPackage.model_validate_json(ctx.job.metadata)
    language = get_language(package.target_language)
    ctx.log_context_fields = {"lesson_uuid": package.lesson_uuid, "user_id": package.user_id}
    planner = PlannerClient()
    state = LessonState(package=package)

    async def publish(event: ProgressEvent) -> None:
        """Send lesson progress to the browser on the progress topic."""
        await ctx.room.local_participant.publish_data(
            event.model_dump_json(), reliable=True, topic=PROGRESS_TOPIC
        )

    agent = TutorAgent(language, state, planner, publish)
    session = build_session(language, ctx.proc.userdata["vad"])

    async def on_shutdown() -> None:
        """Record the lesson as abandoned or completed if it is still open."""
        await agent.finalize(summary="You stopped before the end of the lesson. We'll pick up from here.")
        await planner.aclose()
        if (provider := ctx.proc.userdata.get("tracer_provider")) is not None:
            await flush_tracing(provider)

    await ctx.connect()
    try:
        await asyncio.wait_for(ctx.wait_for_participant(), timeout=LEARNER_JOIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("Learner never joined lesson %s; leaving", package.lesson_uuid)
        await planner.aclose()
        ctx.shutdown(reason="learner never joined")
        return

    ctx.add_shutdown_callback(on_shutdown)
    await planner.start_lesson(package.lesson_uuid)
    await session.start(agent=agent, room=ctx.room)
    await publish(state.progress_event())
    clock = asyncio.create_task(LessonClock(session, state).run())

    def on_close(_: object) -> None:
        """Stop the clock and end the job so no Gradium session outlives the learner."""
        clock.cancel()
        ctx.shutdown(reason="session closed")

    session.on("close", on_close)


if __name__ == "__main__":
    agents.cli.run_app(server)
