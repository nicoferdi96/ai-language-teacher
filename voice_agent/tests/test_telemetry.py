"""Deterministic tests for the Langfuse stamp and export filter (no network)."""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tutor.telemetry import LessonStamp, job_attributes, should_export, unpriced

from conftest import make_package


def test_job_attributes_put_the_lesson_in_its_user_session_and_trace():
    package = make_package("de")
    attributes = job_attributes(package.model_dump_json())
    assert attributes["user.id"] == package.user_id
    assert attributes["session.id"] == package.lesson_uuid
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
    livekit, http = exporter.get_finished_spans()
    assert should_export(livekit)
    assert not should_export(http)


def test_wrapper_span_copy_drops_the_model_so_langfuse_does_not_price_it():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    attributes = {"gen_ai.request.model": "openai/gpt-5.4-nano", "lk.response.ttft": 0.4}
    provider.get_tracer("livekit-agents").start_span("llm_node", attributes=attributes).end()
    [span] = exporter.get_finished_spans()
    copy = unpriced(span)
    assert "gen_ai.request.model" not in copy.attributes
    assert copy.attributes["langfuse.observation.type"] == "span"
    assert copy.attributes["lk.response.ttft"] == 0.4
    assert span.attributes["gen_ai.request.model"] == "openai/gpt-5.4-nano"
