"""Langfuse tracing for the worker: LiveKit's own OpenTelemetry spans, one trace per lesson.

LiveKit Agents already writes the GenAI conventions (``job_entrypoint`` > ``agent_session`` >
``agent_turn`` > ``llm_request`` with the prompt, tools and tokens, ``function_tool``, speech
spans), so this module routes them to Langfuse, stamps the lesson on each, and keeps the spans
around a model request from being priced. LiveKit keeps the STT transcript, the TTS text and
their timings in its own ``lk.*`` attributes, which Langfuse files away as raw metadata, so the
exporter maps them onto Langfuse's input, output, usage and metadata fields (see ``rewrite``).
The root ``job_entrypoint`` gets the lesson's goal in and outcome out (``record_lesson_outcome``),
and the trace is flushed the moment LiveKit ends that root (``FlushOnJobEnd``).
Without ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` (see ``tutor.settings``) nothing is
set up and the tutor runs the same.
"""

import asyncio
import base64
import json
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import lru_cache

from langfuse import Langfuse
from langfuse.span_filter import is_default_export_span
from livekit.agents import get_job_context
from livekit.agents.metrics import AgentSessionUsage, STTModelUsage
from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.util.types import AttributeValue
from pydantic import ValidationError

from tutor.lesson import LessonDispatch, LessonState
from tutor.settings import settings

logger = logging.getLogger(__name__)

TRACE_NAME = "voice-lesson"
LIVEKIT_SCOPE = "livekit-agents"
TUTOR_SCOPE = "voice-tutor"
ANTHROPIC_SCOPE = "com.anthropic.sdk.python"
FLUSH_TIMEOUT_S = 5.0
JOB_ROOT = "job_entrypoint"
"""LiveKit's root span for a job, the lesson trace's root observation; it ends after the shutdown callbacks."""
WRAPPER_SPANS = frozenset({"llm_node", "llm_request_run", "tts_node", "tts_request_run"})
"""LiveKit spans around one ``llm_request`` or ``tts_request``. They carry the model name, and
Langfuse prices any observation with a model, so each call would be counted two or three times."""
MODEL_ATTRIBUTES = frozenset({"gen_ai.request.model", "gen_ai.response.model"})
AGENT_SPANS = frozenset({"start_agent_activity"})
"""LiveKit spans that name the agent's LLM without calling it; they stay agents, without the model."""
APP_ROOT = "langfuse.internal.is_app_root"
"""Langfuse's marker for a trace's root observation. Its processor also sets it on each ``on_enter``,
whose parent ``start_agent_activity`` has already ended, so only ``job_entrypoint`` keeps it."""
METADATA = "langfuse.observation.metadata."


def lesson_attributes(lesson: LessonDispatch) -> dict[str, AttributeValue]:
    """Return the Langfuse attributes that put a span in the lesson's trace, user and session.

    One lesson is one Langfuse session, so a learner who rejoins lands in the same one.
    """
    return {
        "user.id": lesson.user_id,
        "session.id": lesson.lesson_uuid,
        "langfuse.trace.name": TRACE_NAME,
        "langfuse.trace.tags": ["voice", lesson.target_language, lesson.level],
        "langfuse.trace.metadata.lesson_title": lesson.title,
        "langfuse.trace.metadata.native_language": lesson.native_language,
    }


@lru_cache(maxsize=8)
def job_attributes(metadata: str) -> dict[str, AttributeValue]:
    """Return the lesson attributes for a job's dispatch metadata, or none when it holds no lesson."""
    try:
        return lesson_attributes(LessonDispatch.model_validate_json(metadata))
    except ValidationError:
        return {}


job_roots: dict[str, Span] = {}
"""Each running job's ``job_entrypoint`` span by job id, kept by ``LessonStamp`` so the lesson
outcome can be written on the trace's root observation before LiveKit ends it."""


class LessonStamp(SpanProcessor):
    """Stamps the lesson of the running job on every span, LiveKit's included, and keeps its root.

    It reads the job's dispatch metadata, as LiveKit's own stamp does, because the trace's
    root ``job_entrypoint`` starts before the entrypoint runs and a process may host several
    jobs. Langfuse's ``propagate_attributes`` would miss spans LiveKit starts in other tasks.
    """

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """Stamp the job's lesson on a span that just started; remember the job's root span."""
        ctx = get_job_context(required=False)
        if ctx is None:
            return
        if attributes := job_attributes(ctx.job.metadata):
            span.set_attributes(attributes)
        if span.name == JOB_ROOT:
            job_roots[ctx.job.id] = span

    def on_end(self, span: ReadableSpan) -> None:
        """Forget a job's root span once it ends."""
        if span.name == JOB_ROOT:
            ended = span.get_span_context()
            for job_id in [job_id for job_id, root in job_roots.items() if root.get_span_context() == ended]:
                del job_roots[job_id]


class FlushOnJobEnd(SpanProcessor):
    """Sends the lesson's last spans as soon as LiveKit ends the job's root span.

    LiveKit ends ``job_shutdown`` and ``job_entrypoint`` after the shutdown callbacks, so a flush
    there cannot include them; without this they wait for the batch exporter's next tick and are
    lost if the process exits first. Registered after Langfuse's processor, which has queued the
    root by the time this runs; the flush runs in a thread so the event loop never waits on it.
    """

    def __init__(self, provider: TracerProvider):
        """Flush ``provider`` whenever a job's root span ends."""
        self.provider = provider

    def on_end(self, span: ReadableSpan) -> None:
        """Start a background flush when the span is a job's root."""
        if span.name == JOB_ROOT:
            threading.Thread(target=self.flush, name="langfuse-flush", daemon=True).start()

    def flush(self) -> None:
        """Flush the provider, warning when Langfuse does not answer in time."""
        if not self.provider.force_flush(int(FLUSH_TIMEOUT_S * 1000)):
            logger.warning("Langfuse did not flush within %.0f s; the lesson trace may be incomplete", FLUSH_TIMEOUT_S)


def with_attributes(span: ReadableSpan, attributes: Mapping[str, AttributeValue]) -> ReadableSpan:
    """Return a copy of a finished span with other attributes; the span itself is not touched."""
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=dict(attributes),
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def unpriced(span: ReadableSpan) -> ReadableSpan:
    """Return a copy of a wrapper span without its model name, typed as a plain span.

    The ``llm_request`` or ``tts_request`` under it keeps the model and usage.
    """
    attributes = {key: value for key, value in (span.attributes or {}).items() if key not in MODEL_ATTRIBUTES}
    return with_attributes(span, {**attributes, "langfuse.observation.type": "span"})


def observation_metadata(values: Mapping[str, AttributeValue | None]) -> dict[str, AttributeValue]:
    """Return the values as top-level Langfuse metadata, which can be filtered on; ``None`` is left out."""
    return {f"{METADATA}{key}": value for key, value in values.items() if value is not None}


def tts_generation(span: ReadableSpan) -> dict[str, AttributeValue]:
    """Map one synthesized sentence: its text in, characters as usage, time to first audio.

    ``lk.tts_metrics`` is LiveKit's ``TTSMetrics`` as JSON; Cartesia bills per character. The
    model (``gen_ai.request.model``) is LiveKit's own.
    """
    attributes = span.attributes or {}
    metrics = json.loads(str(attributes.get("lk.tts_metrics", "{}")))
    ttfb = metrics.get("ttfb")
    audio_duration = metrics.get("audio_duration")
    mapped: dict[str, AttributeValue] = {
        "langfuse.observation.type": "generation",
        **observation_metadata(
            {
                "ttfb": ttfb,
                "audio_duration": audio_duration,
                "streamed": metrics.get("streamed"),
                "cancelled": metrics.get("cancelled"),
            }
        ),
    }
    if (text := attributes.get("lk.pii.input_text")) is not None:
        mapped["langfuse.observation.input"] = text
    if audio_duration is not None:
        mapped["langfuse.observation.output"] = json.dumps({"audio_seconds": round(audio_duration, 2)})
    if (characters := metrics.get("characters_count")) is not None:
        mapped["langfuse.observation.usage_details"] = json.dumps({"input": characters})
    if isinstance(ttfb, int | float) and ttfb >= 0 and span.start_time is not None:
        first_audio = datetime.fromtimestamp(span.start_time / 1e9 + ttfb, tz=UTC)
        mapped["langfuse.observation.completion_start_time"] = first_audio.isoformat()
    return mapped


def span_seconds(span: ReadableSpan) -> float | None:
    """Return how long a finished span ran, in seconds."""
    if span.start_time is None or span.end_time is None:
        return None
    return round((span.end_time - span.start_time) / 1e9, 2)


def stt_event_counts(attributes: Mapping[str, AttributeValue]) -> dict[str, int]:
    """Count the STT events of one turn by type, from LiveKit's ``lk.stt.events`` JSON list."""
    events = json.loads(str(attributes.get("lk.stt.events", "[]")))
    types = [event.get("type") for event in events]
    return {f"{kind}_count": types.count(kind) for kind in ("interim_transcript", "final_transcript")}


def stt_generation(span: ReadableSpan) -> dict[str, AttributeValue]:
    """Map one learner turn: the transcript out, with its length, confidence, delays and STT events.

    Usage stays off: Soniox bills the whole open stream, recorded once per lesson by
    ``record_stt_usage``, not the seconds of each turn.
    """
    attributes = span.attributes or {}
    mapped: dict[str, AttributeValue] = {
        "langfuse.observation.type": "generation",
        **observation_metadata(
            {
                "turn_seconds": span_seconds(span),
                "transcript_confidence": attributes.get("lk.transcript_confidence"),
                "transcription_delay": attributes.get("lk.transcription_delay"),
                "end_of_turn_delay": attributes.get("lk.end_of_turn_delay"),
                **stt_event_counts(attributes),
            }
        ),
    }
    if (transcript := attributes.get("lk.pii.user_transcript")) is not None:
        mapped["langfuse.observation.output"] = transcript
    return mapped


def agent_turn(span: ReadableSpan) -> dict[str, AttributeValue]:
    """Map one tutor reply: what the learner said in, what Lumi said out, end-to-end latency."""
    attributes = span.attributes or {}
    mapped = observation_metadata(
        {
            "e2e_latency": attributes.get("lk.e2e_latency"),
            "interrupted": attributes.get("lk.interrupted"),
            "generation_count": attributes.get("lk.generation_count"),
        }
    )
    if (said := attributes.get("lk.pii.user_input")) is not None:
        mapped["langfuse.observation.input"] = said
    if (reply := attributes.get("lk.pii.response.text")) is not None:
        mapped["langfuse.observation.output"] = reply
    return mapped


def llm_generation(span: ReadableSpan) -> dict[str, AttributeValue]:
    """Lift the time to first token into filterable metadata; LiveKit maps the rest itself."""
    return observation_metadata({"ttft": (span.attributes or {}).get("gen_ai.response.time_to_first_chunk")})


REWRITES: dict[str, Callable[[ReadableSpan], dict[str, AttributeValue]]] = {
    "tts_request": tts_generation,
    "user_turn": stt_generation,
    "agent_turn": agent_turn,
    "llm_request": llm_generation,
}


def without(span: ReadableSpan) -> ReadableSpan:
    """Return the span without a stray app-root marker or, on an agent span, the model; else the span itself."""
    drop = (MODEL_ATTRIBUTES if span.name in AGENT_SPANS else set()) | ({APP_ROOT} if span.name != JOB_ROOT else set())
    attributes = span.attributes or {}
    if not drop & attributes.keys():
        return span
    return with_attributes(span, {key: value for key, value in attributes.items() if key not in drop})


def rewrite(span: ReadableSpan) -> ReadableSpan:
    """Return the span as Langfuse should see it; on a malformed attribute, the span without stray markers."""
    span = without(span)
    if span.name in WRAPPER_SPANS:
        return unpriced(span)
    if (mapping := REWRITES.get(span.name)) is None:
        return span
    try:
        mapped = mapping(span)
    except (ValueError, TypeError, AttributeError):
        logger.debug("Could not map %s span for Langfuse; exporting it as is", span.name, exc_info=True)
        return span
    return with_attributes(span, {**(span.attributes or {}), **mapped})


class LangfuseExporter(SpanExporter):
    """Langfuse's OTLP endpoint on the v4 ingestion path, with LiveKit's spans mapped by ``rewrite``."""

    def __init__(self, public_key: str, secret_key: str, base_url: str):
        """Build the OTLP exporter with Basic auth and the v4 ingestion header."""
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.otlp = OTLPSpanExporter(
            endpoint=f"{base_url.rstrip('/')}/api/public/otel/v1/traces",
            # Without the v4 ingestion header, traces show up minutes late.
            headers={"Authorization": f"Basic {auth}", "x-langfuse-ingestion-version": "4"},
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Send the spans as ``rewrite`` maps them."""
        return self.otlp.export([rewrite(span) for span in spans])

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Flush the OTLP exporter."""
        return self.otlp.force_flush(timeout_millis)

    def shutdown(self) -> None:
        """Shut the OTLP exporter down."""
        self.otlp.shutdown()


def should_export(span: ReadableSpan) -> bool:
    """Export LiveKit's and the tutor's spans, including the non-GenAI parents of the turn tree.

    The Anthropic SDK's own call spans are left out: LiveKit's ``llm_request`` already is the
    priced generation for each call, with the prompt and the same usage.
    """
    scope = span.instrumentation_scope
    if scope is not None and scope.name == ANTHROPIC_SCOPE:
        return False
    return is_default_export_span(span) or (scope is not None and scope.name in (LIVEKIT_SCOPE, TUTOR_SCOPE))


def stt_usage_attributes(usage: STTModelUsage) -> dict[str, AttributeValue]:
    """Return a generation's attributes for the seconds of audio the STT heard in one lesson."""
    return {
        "langfuse.observation.type": "generation",
        "langfuse.observation.model.name": usage.model,
        "langfuse.observation.usage_details": json.dumps({"input": round(usage.audio_duration)}),
        "langfuse.observation.output": json.dumps({"audio_seconds": round(usage.audio_duration, 1)}),
        **observation_metadata({"unit": "seconds", "provider": usage.provider}),
    }


def record_stt_usage(provider: TracerProvider | None, usage: AgentSessionUsage) -> None:
    """Add one ``stt_usage`` generation per STT model under the current span; no-op when tracing is off.

    Streaming STT has no request span, so its audio seconds are only known for the whole session.
    Called from a shutdown callback, the current span is LiveKit's ``job_shutdown`` in the lesson trace.
    """
    if provider is None:
        return
    tracer = provider.get_tracer(TUTOR_SCOPE)
    for model_usage in usage.model_usage:
        if isinstance(model_usage, STTModelUsage):
            tracer.start_span("stt_usage", attributes=stt_usage_attributes(model_usage)).end()


def lesson_input(state: LessonState) -> dict[str, object]:
    """Return what the lesson set out to do: its title, goal and steps."""
    plan = state.plan
    return {"lesson_uuid": plan.lesson_uuid, "title": plan.title, "goal": plan.goal.aim, "steps": [step.task for step in state.steps]}


def lesson_output(state: LessonState, reason: str) -> dict[str, object]:
    """Return how the lesson ended: outcome, steps done with the learner's evidence, summary, why it closed."""
    return {
        "outcome": state.outcome,
        "steps_done": len(state.steps) - len(state.remaining()),
        "steps": [{"task": step.task, "done": step.done, "evidence": step.evidence} for step in state.steps],
        "summary": state.summary,
        "close_reason": reason,
        "minutes": round(state.elapsed_minutes(), 1),
    }


def record_lesson_outcome(provider: TracerProvider | None, state: LessonState, reason: str) -> None:
    """Write the lesson's goal in and its outcome out on the trace's root observation; no-op when tracing is off.

    Langfuse v4 reads a trace's input and output from its root observation, LiveKit's
    ``job_entrypoint``, which is still open while the shutdown callbacks run.
    """
    ctx = get_job_context(required=False)
    if provider is None or ctx is None or (root := job_roots.get(ctx.job.id)) is None:
        return
    steps_done = len(state.steps) - len(state.remaining())
    root.set_attributes(
        {
            "langfuse.observation.input": json.dumps(lesson_input(state), ensure_ascii=False),
            "langfuse.observation.output": json.dumps(lesson_output(state, reason), ensure_ascii=False),
            **observation_metadata({"outcome": state.outcome, "steps_done": steps_done, "close_reason": reason}),
        }
    )


def setup_tracing() -> TracerProvider | None:
    """Send this process's LiveKit spans to Langfuse when its keys are set; return the provider."""
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        return None
    public_key, secret_key = settings.langfuse_public_key, settings.langfuse_secret_key.get_secret_value()
    base_url = settings.langfuse_base_url
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
    provider.add_span_processor(FlushOnJobEnd(provider))
    set_tracer_provider(provider)
    return provider


async def flush_tracing(provider: TracerProvider | None) -> None:
    """Send the lesson's buffered spans, without blocking the event loop; no-op when tracing is off."""
    if provider is None:
        return
    if not await asyncio.to_thread(provider.force_flush, int(FLUSH_TIMEOUT_S * 1000)):
        logger.warning("Langfuse did not flush within %.0f s; some lesson spans may be lost", FLUSH_TIMEOUT_S)
