"""Deterministic tests for what a planner agent run records (no model, no network)."""

from contextlib import contextmanager

from agno.agent import Agent
from agno.metrics import RunMetrics
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus

from planner import tracing
from planner.agents import CurriculumAgent, planner_model
from planner.tracing import ANTHROPIC_TELEMETRY, run_details


def test_run_records_prompt_reply_and_timing():
    response = RunOutput(
        content={"level": "A1"},
        messages=[
            Message(role="system", content="You are a Curriculum Designer."),
            Message(role="user", content='{"target_language": "Spanish"}'),
            Message(role="assistant", content='{"level": "A1"}'),
        ],
        metrics=RunMetrics(duration=4.9, time_to_first_token=1.2),
        status=RunStatus.completed,
    )
    details = run_details(response)
    assert [message["role"] for message in details["input"]] == ["system", "user"]
    assert details["output"] == {"level": "A1"}
    assert details["metadata"]["status"] == "COMPLETED"
    assert details["metadata"]["duration"] == 4.9
    assert details["metadata"]["ttft"] == 1.2
    assert "level" not in details


def test_failed_run_is_an_error():
    details = run_details(RunOutput(content="Overloaded", status=RunStatus.error))
    assert details["level"] == "ERROR"
    assert details["status_message"] == "Overloaded"


def test_planner_model_sends_its_prompts_to_the_sdk_spans_and_writes_no_prompt_cache():
    model = planner_model()
    assert model.client_params == {"open_telemetry": ANTHROPIC_TELEMETRY}
    assert not model.cache_system_prompt


class RecordingClient:
    """Stands in for the Langfuse client and keeps what one observation was opened and updated with."""

    def __init__(self):
        self.opened: dict = {}
        self.updates: dict = {}

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.opened = kwargs
        yield self

    def update(self, **kwargs):
        self.updates.update(kwargs)


async def test_agent_observation_carries_no_model_so_only_the_sdk_generation_is_priced(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(tracing, "get_client", lambda: client)
    agent: Agent = CurriculumAgent().agent

    async def run(prompt: str) -> RunOutput:
        return RunOutput(content={"level": "A1"}, status=RunStatus.completed)

    monkeypatch.setattr(agent, "arun", run)
    await tracing.run_traced(agent, "{}")
    assert client.opened["as_type"] == "agent"
    assert "model" not in client.opened
    assert client.opened["metadata"] == {"model": "claude-haiku-5-5", "output_schema": "LearningPlanDraft"}
    assert client.updates["output"] == {"level": "A1"}
