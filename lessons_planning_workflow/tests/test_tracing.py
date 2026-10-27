"""Deterministic tests for what a planner generation records (no model, no network)."""

from agno.models.message import Message
from agno.models.metrics import Metrics
from agno.run.agent import RunOutput

from planner.tracing import generation_details


def test_generation_records_prompt_tokens_and_cost():
    response = RunOutput(
        model="openai/gpt-5.4-nano",
        content={"level": "A1"},
        messages=[
            Message(role="system", content="You are a Curriculum Designer."),
            Message(role="user", content='{"target_language": "Spanish"}'),
            Message(role="assistant", content='{"level": "A1"}'),
        ],
        metrics=Metrics(input_tokens=569, output_tokens=528, cost=0.0007),
    )
    details = generation_details(response)
    assert details["model"] == "openai/gpt-5.4-nano"
    assert [message["role"] for message in details["input"]] == ["system", "user"]
    assert details["usage_details"] == {"input": 569, "output": 528}
    assert details["cost_details"] == {"total": 0.0007}


def test_generation_without_metrics_records_no_cost():
    details = generation_details(RunOutput(content="x"))
    assert details["usage_details"] == {"input": 0, "output": 0}
    assert details["cost_details"] is None
