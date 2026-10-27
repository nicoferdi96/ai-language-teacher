"""Langfuse tracing: one trace per lesson request, one generation per agent run.

Without ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` every observation is a no-op.
"""

import os
from typing import Any

from agno.agent import Agent
from agno.run.agent import RunOutput
from langfuse import Langfuse, get_client

TRACE_NAME = "lesson-planning"
INGESTION_V4 = {"x-langfuse-ingestion-version": "4"}
"""Langfuse v4 processes spans in real time only with this header."""


def setup_tracing() -> None:
    """Start the Langfuse client when its keys are set."""
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        Langfuse(additional_headers=INGESTION_V4)


def generation_details(response: RunOutput) -> dict[str, Any]:
    """Return what the model read and wrote, its tokens and OpenRouter's cost, for a generation."""
    metrics = response.metrics
    usage = {
        "input": metrics.input_tokens if metrics else 0,
        "output": metrics.output_tokens if metrics else 0,
    }
    return {
        "model": response.model,
        "input": [
            {"role": message.role, "content": message.content}
            for message in response.messages or []
            if message.role in ("system", "user")
        ],
        "output": response.content,
        "usage_details": usage,
        "cost_details": {"total": metrics.cost} if metrics and metrics.cost is not None else None,
    }


async def run_traced(agent: Agent, prompt: str) -> RunOutput:
    """Run an Agno agent inside a Langfuse generation named after it."""
    with get_client().start_as_current_observation(
        as_type="generation", name=agent.name or "agent", model=agent.model.id if agent.model else None
    ) as generation:
        response = await agent.arun(prompt)
        generation.update(**generation_details(response))
    return response
