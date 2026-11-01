"""Deterministic tests for the Langfuse stamp, export filter and span mapping (no network)."""

import json
import threading

from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage, STTModelUsage
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import tutor.telemetry as telemetry
from tutor.telemetry import (
    FlushOnJobEnd,
    LessonStamp,
    job_attributes,
    record_lesson_outcome,
    record_stt_usage,
    rewrite,
    should_export,
    unpriced,
)

from tutor.lesson import LessonDispatch, LessonGoal, LessonPlan, LessonState, LessonStep, StepResult


def test_job_attributes_put_the_lesson_in_its_user_session_and_trace():
    dispatch = LessonDispatch(
        lesson_uuid="00000000-0000-0000-0000-000000000001",
        user_id="learner@example.com",
        target_language="de",
        native_language="English",
        level="A1",
        title="Ordering at a café",
    )
    attributes = job_attributes(dispatch.model_dump_json())
    assert attributes["user.id"] == dispatch.user_id
    assert attributes["session.id"] == dispatch.lesson_uuid
    assert attributes["langfuse.trace.name"] == "voice-lesson"
    assert attributes["langfuse.trace.tags"] == ["voice", "de", "A1"]


def test_job_without_a_lesson_gets_no_attributes():
    assert job_attributes("") == {}
    assert job_attributes('{"not": "a lesson"}') == {}


def test_spans_outside_a_job_are_not_stamped():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(LessonStamp())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("livekit-agents").start_span("agent_session").end()
    [span] = exporter.get_finished_spans()
    assert "session.id" not in span.attributes


def test_exports_livekit_spans_and_drops_other_infrastructure():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("livekit-agents").start_span("session_start").end()
    provider.get_tracer("opentelemetry.instrumentation.httpx").start_span("POST").end()
    attributes = {"gen_ai.operation.name": "chat", "gen_ai.request.model": "claude-haiku-5-5"}
    provider.get_tracer("com.anthropic.sdk.python").start_span("anthropic.messages.create", attributes=attributes).end()
    livekit, http, anthropic_call = exporter.get_finished_spans()
    assert should_export(livekit)
    assert not should_export(http)
    assert not should_export(anthropic_call)


def test_wrapper_span_copy_drops_the_model_so_langfuse_does_not_price_it():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    attributes = {"gen_ai.request.model": "claude-haiku-5-5", "lk.response.ttft": 0.4}
    provider.get_tracer("livekit-agents").start_span("llm_node", attributes=attributes).end()
    [span] = exporter.get_finished_spans()
    copy = unpriced(span)
    assert "gen_ai.request.model" not in copy.attributes
    assert copy.attributes["langfuse.observation.type"] == "span"
    assert copy.attributes["lk.response.ttft"] == 0.4
    assert span.attributes["gen_ai.request.model"] == "claude-haiku-5-5"


def finished_span(name: str, attributes: dict, start_time: int = 1_700_000_000 * 10**9) -> ReadableSpan:
    """Return one finished LiveKit span with the given attributes."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("livekit-agents").start_span(name, attributes=attributes, start_time=start_time).end()
    [span] = exporter.get_finished_spans()
    return span


def test_tts_request_becomes_a_generation_with_text_characters_and_first_audio():
    metrics = {"ttfb": 0.25, "audio_duration": 1.8, "characters_count": 22, "streamed": True, "cancelled": False}
    span = finished_span(
        "tts_request",
        {"gen_ai.request.model": "sonic-3.6", "lk.pii.input_text": "Hola, ¿cómo estás hoy?", "lk.tts_metrics": json.dumps(metrics)},
    )
    attributes = rewrite(span).attributes
    assert attributes["langfuse.observation.type"] == "generation"
    assert attributes["gen_ai.request.model"] == "sonic-3.6"
    assert attributes["langfuse.observation.input"] == "Hola, ¿cómo estás hoy?"
    assert json.loads(attributes["langfuse.observation.usage_details"]) == {"input": 22}
    assert attributes["langfuse.observation.completion_start_time"] == "2023-11-14T22:13:20.250000+00:00"
    assert attributes["langfuse.observation.metadata.ttfb"] == 0.25
    assert attributes["langfuse.observation.metadata.audio_duration"] == 1.8


def test_tts_attempt_span_is_unpriced_so_each_sentence_is_one_generation():
    attributes = rewrite(finished_span("tts_request_run", {"gen_ai.request.model": "sonic-3.6"})).attributes
    assert "gen_ai.request.model" not in attributes
    assert attributes["langfuse.observation.type"] == "span"


def test_tts_node_is_unpriced_so_each_sentence_is_one_generation():
    attributes = rewrite(finished_span("tts_node", {"gen_ai.request.model": "sonic-3.6"})).attributes
    assert "gen_ai.request.model" not in attributes
    assert attributes["langfuse.observation.type"] == "span"


def test_tts_request_output_is_the_seconds_of_audio_it_made():
    span = finished_span("tts_request", {"lk.tts_metrics": json.dumps({"audio_duration": 12.239, "characters_count": 179})})
    assert json.loads(rewrite(span).attributes["langfuse.observation.output"]) == {"audio_seconds": 12.24}


def test_malformed_tts_metrics_exports_the_span_unchanged():
    span = finished_span("tts_request", {"lk.tts_metrics": "not json"})
    assert rewrite(span) is span


def test_user_turn_becomes_an_stt_generation_with_the_transcript_as_output():
    span = finished_span(
        "user_turn",
        {"gen_ai.request.model": "stt-rt-v5", "lk.pii.user_transcript": "Ich hätte gern einen Kaffee", "lk.transcript_confidence": 0.9, "lk.transcription_delay": 0.3},
    )
    attributes = rewrite(span).attributes
    assert attributes["gen_ai.request.model"] == "stt-rt-v5"
    assert attributes["langfuse.observation.output"] == "Ich hätte gern einen Kaffee"
    assert attributes["langfuse.observation.metadata.transcript_confidence"] == 0.9
    assert attributes["langfuse.observation.metadata.transcription_delay"] == 0.3
    assert "langfuse.observation.usage_details" not in attributes


def test_user_turn_counts_its_stt_events_and_how_long_it_lasted():
    events = [
        {"received_at": 1.0, "type": "interim_transcript", "transcript_length": 3},
        {"received_at": 1.2, "type": "interim_transcript", "transcript_length": 7},
        {"received_at": 1.4, "type": "preflight_transcript", "transcript_length": 7},
        {"received_at": 1.5, "type": "final_transcript", "transcript_length": 15},
    ]
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    start = 1_700_000_000 * 10**9
    span = provider.get_tracer("livekit-agents").start_span("user_turn", start_time=start)
    span.set_attribute("lk.stt.events", json.dumps(events))
    span.end(end_time=start + 1_560_000_000)
    attributes = rewrite(exporter.get_finished_spans()[0]).attributes
    assert attributes["langfuse.observation.metadata.turn_seconds"] == 1.56
    assert attributes["langfuse.observation.metadata.interim_transcript_count"] == 2
    assert attributes["langfuse.observation.metadata.final_transcript_count"] == 1


def test_malformed_stt_events_export_the_user_turn_unchanged():
    span = finished_span("user_turn", {"lk.stt.events": "not json"})
    assert rewrite(span) is span


def test_agent_turn_shows_what_the_learner_said_and_what_lumi_replied():
    span = finished_span(
        "agent_turn", {"lk.pii.user_input": "Bonjour", "lk.pii.response.text": "Bonjour ! Ça va ?", "lk.e2e_latency": 1.1}
    )
    attributes = rewrite(span).attributes
    assert attributes["langfuse.observation.input"] == "Bonjour"
    assert attributes["langfuse.observation.output"] == "Bonjour ! Ça va ?"
    assert attributes["langfuse.observation.metadata.e2e_latency"] == 1.1
    assert "langfuse.observation.type" not in attributes


def test_llm_request_keeps_its_model_and_lifts_ttft_into_metadata():
    span = finished_span("llm_request", {"gen_ai.request.model": "claude-haiku-5-5", "gen_ai.response.time_to_first_chunk": 0.4})
    attributes = rewrite(span).attributes
    assert attributes["gen_ai.request.model"] == "claude-haiku-5-5"
    assert attributes["langfuse.observation.metadata.ttft"] == 0.4


def test_other_spans_are_exported_as_they_are():
    span = finished_span("eou_detection", {"lk.eou.probability": 0.8})
    assert rewrite(span) is span


def test_lesson_stt_usage_is_one_exported_generation_with_audio_seconds():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    usage = AgentSessionUsage(
        model_usage=[
            STTModelUsage(provider="Soniox", model="stt-rt-v5", audio_duration=312.6),
            LLMModelUsage(provider="openrouter", model="claude-haiku-5-5", input_tokens=900),
        ]
    )
    record_stt_usage(provider, usage)
    [span] = exporter.get_finished_spans()
    assert span.name == "stt_usage"
    assert should_export(span)
    assert span.attributes["langfuse.observation.model.name"] == "stt-rt-v5"
    assert json.loads(span.attributes["langfuse.observation.usage_details"]) == {"input": 313}


def test_stt_usage_is_skipped_without_tracing():
    record_stt_usage(None, AgentSessionUsage(model_usage=[]))


def test_lesson_stt_usage_output_is_its_audio_seconds():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    record_stt_usage(provider, AgentSessionUsage(model_usage=[STTModelUsage(provider="Soniox", model="stt-rt-v5", audio_duration=125.66)]))
    [span] = exporter.get_finished_spans()
    assert json.loads(span.attributes["langfuse.observation.output"]) == {"audio_seconds": 125.7}


class FakeJob:
    """The parts of a LiveKit job context the telemetry reads."""

    def __init__(self, job_id: str, metadata: str = ""):
        self.job = type("Job", (), {"id": job_id, "metadata": metadata})()


def lesson_state() -> LessonState:
    """Return a running two-step lesson with the first step done."""
    plan = LessonPlan(
        lesson_uuid="00000000-0000-0000-0000-000000000002",
        user_id="learner@example.com",
        target_language="es",
        native_language="Italian",
        level="A1",
        title="Introducing yourself",
        goal=LessonGoal(aim="Say your name and where you are from", prompt="..."),
        opening_line="¡Hola!",
        steps=[LessonStep(position=1, task="Say your name", prompt="..."), LessonStep(position=2, task="Say where you are from", prompt="...")],
    )
    state = LessonState(plan=plan)
    state.mark_step_done(1, StepResult(evidence="Me llamo Nicola"))
    return state


def test_lesson_outcome_is_the_root_observations_input_and_output(monkeypatch):
    monkeypatch.setattr(telemetry, "get_job_context", lambda required=False: FakeJob("AJ_1"))
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(LessonStamp())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    root = provider.get_tracer("livekit-agents").start_span("job_entrypoint")
    state = lesson_state()
    state.finish()
    record_lesson_outcome(provider, state, "session closed")
    root.end()
    [span] = exporter.get_finished_spans()
    assert json.loads(span.attributes["langfuse.observation.input"])["steps"] == ["Say your name", "Say where you are from"]
    output = json.loads(span.attributes["langfuse.observation.output"])
    assert output["outcome"] == "abandoned"
    assert output["steps_done"] == 1
    assert output["steps"][0]["evidence"] == "Me llamo Nicola"
    assert output["close_reason"] == "session closed"
    assert span.attributes["langfuse.observation.metadata.outcome"] == "abandoned"
    assert span.attributes["langfuse.observation.metadata.steps_done"] == 1
    assert "AJ_1" not in telemetry.job_roots


def test_lesson_outcome_is_skipped_without_tracing_or_a_root(monkeypatch):
    record_lesson_outcome(None, lesson_state(), "session closed")
    monkeypatch.setattr(telemetry, "get_job_context", lambda required=False: FakeJob("AJ_unknown"))
    record_lesson_outcome(TracerProvider(), lesson_state(), "session closed")


class FlushedProvider(TracerProvider):
    """A tracer provider that notes when it is flushed."""

    def __init__(self):
        super().__init__()
        self.flushed = threading.Event()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self.flushed.set()
        return True


def test_trace_is_flushed_when_the_job_root_ends_and_not_before():
    provider = FlushedProvider()
    provider.add_span_processor(FlushOnJobEnd(provider))
    tracer = provider.get_tracer("livekit-agents")
    root = tracer.start_span("job_entrypoint")
    tracer.start_span("job_shutdown").end()
    assert not provider.flushed.wait(0.2)
    root.end()
    assert provider.flushed.wait(2)
