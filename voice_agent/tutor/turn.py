"""Turn-taking: when the tutor decides the learner has finished, and what speech over it does.

The numbers are unmute-core's "balanced" LiveKit pace (``unmute_core.turn.TURN_WINDOWS``),
as its salon-concierge example applies them. Change them only with a measurement: the
worker logs each turn's end-of-utterance delay as ``turn:`` lines (see ``log_turn_metrics``).
"""

import logging
from typing import Literal

from livekit.agents import (
    AgentSession,
    AgentStateChangedEvent,
    InterruptionOptions,
    MetricsCollectedEvent,
    ToolExecutionUpdatedEvent,
    TurnHandlingOptions,
    UserStateChangedEvent,
    inference,
    metrics,
)
from livekit.plugins import silero
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TurnWindow(BaseModel):
    """The quiet the tutor waits before it takes its turn, in seconds."""

    model_config = ConfigDict(frozen=True)

    vad_silence: float = Field(ge=0.25, description="Silero silence before speech counts as stopped.")
    min_delay: float = Field(ge=0, description="Shortest endpointing wait.")
    max_delay: float = Field(gt=0, description="Longest wait for a learner the model thinks is not done.")
    mode: Literal["fixed", "dynamic"] = "dynamic"


BALANCED = TurnWindow(vad_silence=0.3, min_delay=0.3, max_delay=1.6, mode="dynamic")

INTERRUPTION: InterruptionOptions = {
    "enabled": True,
    "mode": "adaptive",
    "backchannel_boundary": (1.0, 3600.0),
}
"""Set explicitly: LiveKit picks adaptive detection itself only in dev mode and falls back
to plain VAD under ``start``, which is what Compose runs. The boundary keeps a "sí" said
over the tutor, so a short answer to its question is heard after the line, not lost."""


def load_vad(window: TurnWindow = BALANCED) -> silero.VAD:
    """Load Silero with the turn window's silence floor (once per worker process)."""
    return silero.VAD.load(min_silence_duration=window.vad_silence)


def turn_handling(window: TurnWindow = BALANCED) -> TurnHandlingOptions:
    """Return the session's turn handling: audio turn detector, endpointing, interruption."""
    return {
        "turn_detection": inference.TurnDetector(version="v1-mini"),
        "endpointing": {"mode": window.mode, "min_delay": window.min_delay, "max_delay": window.max_delay},
        "interruption": INTERRUPTION,
        "preemptive_generation": {"enabled": True},
    }


def yield_to_caller(session: AgentSession) -> None:
    """Drop a reply the tutor has not started saying when the learner speaks again.

    LiveKit 1.8 ends the turn at a pause and keeps the reply even if the learner goes on,
    so it would play over them. Their words are already in the history, so the next reply
    answers all of them. Audio that already plays is left to ``INTERRUPTION``; a reply that
    runs a tool, or one that must not be interrupted, is never cut.
    """
    tool_speech: dict[str, str] = {}

    def drop(why: str) -> None:
        """Interrupt the current reply unless it is finished, protected or running a tool."""
        speech = session.current_speech
        if speech is None or speech.done() or speech.interrupted or not speech.allow_interruptions:
            return
        if speech.id in tool_speech.values():
            return
        logger.info("Dropped a reply the learner spoke over: %s", why)
        speech.interrupt()

    def on_user_state(event: UserStateChangedEvent) -> None:
        """Drop the reply being prepared when the learner starts speaking again."""
        if event.new_state == "speaking" and session.agent_state == "thinking":
            drop("learner resumed while the tutor was thinking")

    def on_agent_state(event: AgentStateChangedEvent) -> None:
        """Drop a reply whose turn was committed while the learner was still speaking."""
        if event.new_state == "thinking" and session.user_state == "speaking":
            drop("turn committed while the learner was speaking")

    def on_tool(event: ToolExecutionUpdatedEvent) -> None:
        """Remember which reply runs which tool call, so those replies are never dropped."""
        update, speech = event.update, session.current_speech
        if update.type == "tool_call_started" and speech is not None:
            tool_speech[update.function_call.call_id] = speech.id
        elif update.type == "tool_call_ended":
            tool_speech.pop(update.call_id, None)

    session.on("user_state_changed", on_user_state)
    session.on("agent_state_changed", on_agent_state)
    session.on("tool_execution_updated", on_tool)


def log_turn_metrics(session: AgentSession) -> None:
    """Log the latency of each turn: end of utterance, LLM first token, TTS first audio."""

    def on_metrics(event: MetricsCollectedEvent) -> None:
        """Write one ``turn:`` log line per latency metric LiveKit reports."""
        match event.metrics:
            case metrics.EOUMetrics() as eou:
                logger.info(
                    "turn: end_of_utterance %.2fs, transcription %.2fs",
                    eou.end_of_utterance_delay,
                    eou.transcription_delay,
                )
            case metrics.LLMMetrics() as llm:
                logger.info("turn: llm ttft %.2fs", llm.ttft)
            case metrics.TTSMetrics() as tts:
                logger.info("turn: tts ttfb %.2fs", tts.ttfb)

    session.on("metrics_collected", on_metrics)

