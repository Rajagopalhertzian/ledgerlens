"""OpenTelemetry tracing initialization and utilities.

Provides console exporter for development and OTLP exporter for production.
"""

import os
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import SpanKind, Status, StatusCode
from structlog import get_logger

logger = get_logger(__name__)

# Global tracer provider
_tracer_provider: TracerProvider | None = None


def init_tracing(
    service_name: str = "ledgerlens",
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    console_export: bool = True,
) -> TracerProvider:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Service name for traces
        service_version: Service version
        otlp_endpoint: OTLP endpoint (e.g., http://localhost:4317)
        console_export: Whether to export to console (for development)

    Returns:
        Configured TracerProvider

    """
    global _tracer_provider

    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Add console exporter for development
    if console_export or os.getenv("OTEL_CONSOLE_EXPORT", "true").lower() == "true":
        console_exporter = ConsoleSpanExporter()
        _tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
        logger.info("OpenTelemetry console exporter enabled")

    # Add OTLP exporter if endpoint provided
    if otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info("OpenTelemetry OTLP exporter enabled", endpoint=endpoint)

    # Set as global tracer provider
    trace.set_tracer_provider(_tracer_provider)

    # Auto-instrument libraries
    try:
        FastAPIInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        logger.info("Auto-instrumentation enabled for FastAPI, HTTPX, Redis, SQLAlchemy")
    except Exception as e:
        logger.warning("Some auto-instrumentation failed", error=str(e))

    logger.info("OpenTelemetry tracing initialized", service=service_name, version=service_version)
    return _tracer_provider


def get_tracer(name: str = "ledgerlens") -> trace.Tracer:
    """Get tracer instance."""
    return trace.get_tracer(name)


def trace_function(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Callable:
    """Trace a function.

    Usage:
        @trace_function("my_operation")
        async def my_function():
            ...

        @trace_function(kind=SpanKind.CLIENT, attributes={"component": "llm"})
        async def call_llm():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer(func.__module__)
            span_name = name or f"{func.__module__}.{func.__qualname__}"

            with tracer.start_as_current_span(span_name, kind=kind) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                else:
                    span.set_status(Status(StatusCode.OK))
                    return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer(func.__module__)
            span_name = name or f"{func.__module__}.{func.__qualname__}"

            with tracer.start_as_current_span(span_name, kind=kind) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                else:
                    span.set_status(Status(StatusCode.OK))
                    return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def trace_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
):
    """Context manager for manual span creation.

    Usage:
        with trace_span("my_operation", attributes={"key": "value"}) as span:
            do_work()
            span.set_attribute("result", "success")
    """
    tracer = get_tracer("ledgerlens")
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(exception: Exception) -> None:
    """Record exception in current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


# Hello-world trace example
async def hello_world_trace() -> None:
    """Hello-world trace example demonstrating basic tracing.

    Run with: python -m ledgerlens.observability.tracing
    """
    # Initialize tracing with console export
    init_tracing(
        service_name="ledgerlens-hello-world",
        service_version="0.1.0",
        console_export=True,
    )

    tracer = get_tracer("hello-world")

    # Create a parent span
    with tracer.start_as_current_span("hello-world") as parent_span:
        parent_span.set_attribute("example", "hello-world")

        # Child span for LLM call simulation
        with tracer.start_as_current_span("llm.call", kind=SpanKind.CLIENT) as llm_span:
            llm_span.set_attribute("llm.model", "gpt-4o")
            llm_span.set_attribute("llm.role", "strong")
            llm_span.set_attribute("llm.temperature", 0.0)

            # Simulate work
            import asyncio
            await asyncio.sleep(0.1)

            llm_span.set_attribute("llm.tokens.prompt", 100)
            llm_span.set_attribute("llm.tokens.completion", 50)
            llm_span.set_attribute("llm.cost_usd", 0.0015)

        # Child span for validation
        with tracer.start_as_current_span("validation.gstin") as val_span:
            val_span.set_attribute("validator", "gstin_checksum")
            val_span.set_attribute("result", "valid")

            # Simulate work
            await asyncio.sleep(0.05)

        parent_span.set_attribute("status", "completed")



if __name__ == "__main__":
    import asyncio
    asyncio.run(hello_world_trace())
