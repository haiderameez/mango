"""Process-local Prometheus metrics and OpenTelemetry setup for Mango."""
from contextlib import nullcontext
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings

REQUESTS = Counter(
    "mango_http_requests_total", "HTTP requests", ("method", "route", "status")
)
REQUEST_DURATION = Histogram(
    "mango_http_request_duration_seconds", "HTTP request duration", ("method", "route")
)
INVESTIGATIONS = Histogram(
    "mango_investigation_duration_seconds", "Investigation duration", ("status",)
)
PROVIDER_CALLS = Counter(
    "mango_provider_calls_total", "Provider calls attempted", ("provider", "result")
)
INGESTED_RECORDS = Counter("mango_ingest_records_total", "Accepted log records")
DETECTION_FIRINGS = Counter("mango_detection_firings_total", "Detection rule firings")
BUDGET_REMAINING = Gauge("mango_llm_budget_remaining", "LLM requests left today")
QUEUE_DEPTH = Gauge("mango_investigation_queue_depth", "Queued investigations")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        REQUEST_DURATION.labels(request.method, route).observe(perf_counter() - started)
        return response


def metrics_response() -> Response:
    from app.ai.quota import remaining
    from app.api.investigation import investigation_queue

    try:
        BUDGET_REMAINING.set(remaining())
    except Exception:  # noqa: BLE001 - metrics must not make the service unavailable
        pass
    try:
        QUEUE_DEPTH.set(investigation_queue.depth)
    except Exception:  # noqa: BLE001 - queue health is separately visible
        pass
    return Response(generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8")


def configure_tracing(app) -> None:
    """Instrument HTTP and export traces to the configured OTLP HTTP collector."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if settings.otel_endpoint:
        provider = TracerProvider(resource=Resource.create({"service.name": "mango-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    CeleryInstrumentor().instrument()


def configure_celery_tracing() -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if settings.otel_endpoint:
        provider = TracerProvider(resource=Resource.create({"service.name": "mango-worker"}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )
        trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument()


def tracer():
    try:
        from opentelemetry import trace

        return trace.get_tracer("mango")
    except ImportError:
        return None


def span(name: str):
    current = tracer()
    return current.start_as_current_span(name) if current else nullcontext()
