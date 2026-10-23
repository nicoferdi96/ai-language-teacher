"""The speech pipeline: Gradium STT/TTS, an OpenRouter LLM and the turn-taking settings."""

import logging
import os
from typing import Any

from livekit.agents import AgentSession, APIConnectOptions, MetricsCollectedEvent, metrics
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import gradium, openai, silero

from tutor.languages import LanguageProfile
from tutor.turn import BALANCED, turn_handling, yield_to_caller

logger = logging.getLogger(__name__)

VOICE_LLM_MODEL = os.getenv("VOICE_LLM_MODEL", "openai/gpt-5.4-nano")
VOICE_LLM_TEMPERATURE = float(os.getenv("VOICE_LLM_TEMPERATURE", "0.1"))
REASONING_MODEL_PREFIXES = ("openai/gpt-5", "openai/gpt-6", "openai/o")


def load_vad() -> silero.VAD:
    """Load Silero with the turn window's silence floor (once per worker process)."""
    return silero.VAD.load(min_silence_duration=BALANCED.vad_silence)


def build_llm(model: str = VOICE_LLM_MODEL) -> openai.LLM:
    """Return the OpenRouter LLM: minimal reasoning for reasoning models, else low temperature."""
    options: dict[str, Any] = (
        {"reasoning_effort": "minimal"}
        if model.startswith(REASONING_MODEL_PREFIXES)
        else {"temperature": VOICE_LLM_TEMPERATURE}
    )
    return openai.LLM.with_openrouter(model=model, app_name="AI Language Teacher", **options)


def build_session(language: LanguageProfile, vad: silero.VAD) -> AgentSession:
    """Return a session for one target language, tuned for fast turn-taking."""
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


def log_turn_metrics(session: AgentSession) -> None:
    """Log the latency of each turn: end of utterance, LLM first token, TTS first audio."""

    def on_metrics(event: MetricsCollectedEvent) -> None:
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
