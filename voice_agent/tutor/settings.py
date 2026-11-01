"""Configuration for the voice tutor and the voice API, read once from the environment.

Importing this module loads the repository's ``.env`` (when there is one) into the
environment, so the LiveKit, Gradium and OpenRouter plugins, which read their own keys,
see the same values as ``settings``.
"""

from pathlib import Path

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

    voice_llm_model: str = "openai/gpt-5.4-nano"
    voice_llm_temperature: float = Field(0.1, ge=0, le=2, description="Used only by non-reasoning models.")

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
