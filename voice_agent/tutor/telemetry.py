"""Langfuse tracing for the worker: LiveKit's own OpenTelemetry spans, one trace per lesson.

LiveKit Agents already writes the GenAI conventions (``job_entrypoint`` > ``agent_session`` >
``agent_turn`` > ``llm_request`` with the prompt, tools and tokens, ``function_tool``, speech
spans), so this module only routes them to Langfuse, stamps the lesson on each, and keeps the
spans around a model request from being priced. Without ``LANGFUSE_PUBLIC_KEY`` and
``LANGFUSE_SECRET_KEY`` nothing is set up and the tutor runs the same.
"""

import asyncio
import base64
import logging
import os
from collections.abc import Sequence
from functools import lru_cache

from langfuse import Langfuse
from langfuse.span_filter import is_default_export_span
from livekit.agents import get_job_context
from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.util.types import AttributeValue
from pydantic import ValidationError

from tutor.lesson import LessonPackage

logger = logging.getLogger(__name__)

TRACE_NAME = "voice-lesson"
LIVEKIT_SCOPE = "livekit-agents"
DEFAULT_BASE_URL = "https://cloud.langfuse.com"
FLUSH_TIMEOUT_S = 5.0
WRAPPER_SPANS = frozenset({"llm_node", "llm_request_run"})
"""LiveKit spans around one ``llm_request``. They carry the model name, and Langfuse prices any
observation with a model, so each call would be counted two or three times."""
MODEL_ATTRIBUTES = frozenset({"gen_ai.request.model", "gen_ai.response.model"})


def lesson_attributes(package: LessonPackage) -> dict[str, AttributeValue]:
    """Return the Langfuse attributes that put a span in the lesson's trace, user and session.

    One lesson is one Langfuse session, so a learner who rejoins lands in the same one.
    """
    return {
        "user.id": package.user_id,
        "session.id": package.lesson_uuid,
        "langfuse.trace.name": TRACE_NAME,
        "langfuse.trace.tags": ["voice", package.target_language, package.level],
        "langfuse.trace.metadata.lesson_title": package.title,
        "langfuse.trace.metadata.native_language": package.native_language,
    }


@lru_cache(maxsize=8)
def job_attributes(metadata: str) -> dict[str, AttributeValue]:
    """Return the lesson attributes for a job's dispatch metadata, or none when it holds no lesson."""
    try:
        return lesson_attributes(LessonPackage.model_validate_json(metadata))
    except ValidationError:
        return {}


class LessonStamp(SpanProcessor):
    """Stamps the lesson of the running job on every span, LiveKit's included.

    It reads the job's dispatch metadata, as LiveKit's own stamp does, because the trace's
    root ``job_entrypoint`` starts before the entrypoint runs and a process may host several
    jobs. Langfuse's ``propagate_attributes`` would miss spans LiveKit starts in other tasks.
    """

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """Stamp the job's lesson on a span that just started."""
        ctx = get_job_context(required=False)
        if ctx is not None and (attributes := job_attributes(ctx.job.metadata)):
            span.set_attributes(attributes)


def unpriced(span: ReadableSpan) -> ReadableSpan:
    """Return a copy of a wrapper span without its model name, typed as a plain span.

    The span itself is not touched; the ``llm_request`` under it keeps the model and tokens.
    """
    attributes = {key: value for key, value in (span.attributes or {}).items() if key not in MODEL_ATTRIBUTES}
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes={**attributes, "langfuse.observation.type": "span"},
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class LangfuseExporter(SpanExporter):
    """Langfuse's OTLP endpoint on the v4 ingestion path, with wrapper spans left unpriced."""

    def __init__(self, public_key: str, secret_key: str, base_url: str):
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.otlp = OTLPSpanExporter(
            endpoint=f"{base_url.rstrip('/')}/api/public/otel/v1/traces",
            # Without the v4 ingestion header, traces show up minutes late.
            headers={"Authorization": f"Basic {auth}", "x-langfuse-ingestion-version": "4"},
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Send the spans, each wrapper span as its unpriced copy."""
        return self.otlp.export([unpriced(span) if span.name in WRAPPER_SPANS else span for span in spans])

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Flush the OTLP exporter."""
        return self.otlp.force_flush(timeout_millis)

    def shutdown(self) -> None:
        """Shut the OTLP exporter down."""
        self.otlp.shutdown()


def should_export(span: ReadableSpan) -> bool:
    """Export LiveKit's spans, including the non-GenAI parents that hold the turn tree together."""
    scope = span.instrumentation_scope
    return is_default_export_span(span) or (scope is not None and scope.name == LIVEKIT_SCOPE)


def setup_tracing() -> TracerProvider | None:
    """Send this process's LiveKit spans to Langfuse when its keys are set; return the provider."""
    public_key, secret_key = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        return None
    base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or DEFAULT_BASE_URL
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "voice-tutor"}))
    provider.add_span_processor(LessonStamp())
    Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        tracer_provider=provider,
        span_exporter=LangfuseExporter(public_key, secret_key, base_url),
        should_export_span=should_export,
    )
    set_tracer_provider(provider)
    return provider


async def flush_tracing(provider: TracerProvider) -> None:
    """Send the lesson's buffered spans, without blocking the event loop."""
    if not await asyncio.to_thread(provider.force_flush, int(FLUSH_TIMEOUT_S * 1000)):
        logger.warning("Langfuse did not flush within %.0f s; some lesson spans may be lost", FLUSH_TIMEOUT_S)
