"""Configuration for the voice tutor and the voice API, read once from the environment.

Importing this module loads the repository's ``.env`` (when there is one) into the
environment, so the LiveKit plugins see the same values as ``settings``. The speech and LLM
keys are also passed explicitly, because the Anthropic key lives in ``CLAUDE_API_KEY``.
"""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class TutorSettings(BaseSettings):
    """Every setting the worker and the API use; each field maps to the upper-case env var."""

    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore", frozen=True)

    agent_name: str = Field("language-tutor", description="Name the worker registers under for dispatch.")
    progress_topic: str = Field("lesson-progress", description="Data channel topic for lesson progress.")
    learner_join_timeout_s: float = Field(30, gt=0, description="How long the tutor waits for the learner.")

    voice_llm_model: str = "claude-haiku-5-5"
    voice_llm_effort: Literal["low", "medium", "high"] = Field("low", description="Claude effort level.")
    voice_llm_thinking: Literal["adaptive", "disabled"] = Field(
        "adaptive", description="disabled is ~0.5 s faster to first token but misses goal ticks."
    )
    voice_llm_max_tokens: int = Field(512, gt=0, description="Spoken replies are a few sentences.")
    anthropic_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("anthropic_api_key", "claude_api_key")
    )

    stt_model: str = "stt-rt-v5"
    stt_max_endpoint_delay_ms: int = Field(500, ge=500, le=3000, description="Soniox finalizes after this pause.")
    soniox_api_key: SecretStr | None = None

    tts_model: str = "sonic-3.6"
    tts_voice: str = Field("47c38ca4-5f35-497b-b1a3-415245fb35e1", description="Cartesia voice (Daniel), multilingual.")
    cartesia_api_key: SecretStr | None = None

    planner_base_url: str = "http://localhost:8000"

    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: SecretStr | None = None

    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = Field(
        "https://cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_base_url", "langfuse_host"),
    )


settings = TutorSettings()
