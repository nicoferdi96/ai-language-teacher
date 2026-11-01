"""Langfuse tracing: one trace per lesson request, one agent observation per agent run.

The Anthropic SDK traces each API call itself (``anthropic.messages.create``, exported by
Langfuse's default filter) with the model, effort, max tokens and usage including cache
writes, so that span is the generation Langfuse prices. The agent observation around it holds
what the agent read and returned and the run's status, and carries no model: with one, every
call would be priced twice. Without ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` every
observation is a no-op.
"""

import os
from typing import Any

from agno.agent import Agent
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from langfuse import Langfuse, get_client
from opentelemetry import trace

TRACE_NAME = "lesson-planning"
INGESTION_V4 = {"x-langfuse-ingestion-version": "4"}
"""Langfuse v4 processes spans in real time only with this header."""
ANTHROPIC_TELEMETRY = {"traces": {"content_mode": "content"}}
"""The Anthropic client's ``open_telemetry`` option: its spans carry the prompt and reply, not only metadata."""


def setup_tracing() -> None:
    """Start the Langfuse client when its keys are set."""
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        Langfuse(additional_headers=INGESTION_V4)


def tag_lesson_session(lesson_uuid: str) -> None:
    """Put the current observation in the lesson's Langfuse session, the one the voice lesson uses.

    The lesson uuid is only known once the lesson is prepared, so ``propagate_attributes`` cannot
    reach the observations that already ended; the step and the run's root carry it instead.
    """
    trace.get_current_span().set_attribute("session.id", lesson_uuid)


def run_details(response: RunOutput) -> dict[str, Any]:
    """Return what the agent read and returned, with its run's status and timing, for its observation."""
    metrics = response.metrics
    details: dict[str, Any] = {
        "input": [
            {"role": message.role, "content": message.content}
            for message in response.messages or []
            if message.role in ("system", "user")
        ],
        "output": response.content,
        "metadata": {
            "run_id": response.run_id,
            "status": response.status.value,
            "duration": metrics.duration if metrics else None,
            "ttft": metrics.time_to_first_token if metrics else None,
        },
    }
    if response.status == RunStatus.error:
        details["level"] = "ERROR"
        details["status_message"] = str(response.content)
    return details


async def run_traced(agent: Agent, prompt: str) -> RunOutput:
    """Run an Agno agent inside a Langfuse agent observation named after it.

    An exception from the run marks the observation as an error through its span status.
    """
    with get_client().start_as_current_observation(
        as_type="agent",
        name=agent.name or "agent",
        metadata={
            "model": agent.model.id if agent.model else None,
            "output_schema": getattr(agent.output_schema, "__name__", None),
        },
    ) as observation:
        response = await agent.arun(prompt)
        observation.update(**run_details(response))
    return response
