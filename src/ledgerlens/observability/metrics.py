"""OpenTelemetry metrics initialization and utilities."""

import os

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import (
    PrometheusMetricReader,  # pyright: ignore[reportMissingImports]
    start_http_server,  # pyright: ignore[reportPrivateImportUsage]
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from structlog import get_logger

logger = get_logger(__name__)

# Global meter provider
_meter_provider: MeterProvider | None = None


def init_metrics(
    service_name: str = "ledgerlens",
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    prometheus_port: int | None = None,
) -> MeterProvider:
    """Initialize OpenTelemetry metrics.

    Args:
        service_name: Service name for metrics
        service_version: Service version
        otlp_endpoint: OTLP endpoint for metrics
        prometheus_port: Port for Prometheus exporter (if enabled)

    Returns:
        Configured MeterProvider

    """
    global _meter_provider

    resource = Resource.create({SERVICE_NAME: service_name, SERVICE_VERSION: service_version})

    readers = []

    # Add Prometheus exporter if port specified
    if prometheus_port or os.getenv("PROMETHEUS_PORT"):
        port = prometheus_port or int(os.getenv("PROMETHEUS_PORT", "9090"))
        start_http_server(port=port)
        prometheus_reader = PrometheusMetricReader()
        readers.append(prometheus_reader)
        logger.info("Prometheus metrics reader enabled", port=port)

    # Add OTLP exporter if endpoint provided
    if otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"):
        endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
        otlp_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        readers.append(PeriodicExportingMetricReader(otlp_exporter, export_interval_millis=30000))
        logger.info("OTLP metrics exporter enabled", endpoint=endpoint)

    # Create meter provider
    _meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(_meter_provider)

    logger.info("OpenTelemetry metrics initialized", service=service_name)
    return _meter_provider


def get_meter(name: str = "ledgerlens") -> metrics.Meter:
    """Get meter instance."""
    return metrics.get_meter(name)


# Common metric instruments
class Metrics:
    """Common metric instruments for LedgerLens."""

    def __init__(self, meter: metrics.Meter):
        self.meter = meter

        # Invoice processing metrics
        self.invoices_processed = meter.create_counter(
            "ledgerlens.invoices.processed", description="Total invoices processed", unit="1"
        )

        self.invoice_processing_duration = meter.create_histogram(
            "ledgerlens.invoice.processing.duration", description="Invoice processing duration", unit="s"
        )

        self.invoice_cost = meter.create_histogram(
            "ledgerlens.invoice.cost", description="Cost per invoice in USD", unit="USD"
        )

        # LLM metrics
        self.llm_tokens = meter.create_histogram("ledgerlens.llm.tokens", description="LLM token usage", unit="tokens")

        self.llm_cost = meter.create_histogram("ledgerlens.llm.cost", description="LLM cost in USD", unit="USD")

        self.llm_latency = meter.create_histogram("ledgerlens.llm.latency", description="LLM call latency", unit="ms")

        # Extraction metrics
        self.extraction_confidence = meter.create_histogram(
            "ledgerlens.extraction.confidence", description="Extraction confidence scores", unit="1"
        )

        self.extraction_field_accuracy = meter.create_gauge(
            "ledgerlens.extraction.field.accuracy", description="Field-level extraction accuracy", unit="1"
        )

        # Matching metrics
        self.matching_precision = meter.create_gauge(
            "ledgerlens.matching.precision", description="3-way matching precision", unit="1"
        )

        self.matching_recall = meter.create_gauge(
            "ledgerlens.matching.recall", description="3-way matching recall", unit="1"
        )

        # Agent metrics
        self.agent_tool_calls = meter.create_histogram(
            "ledgerlens.agent.tool_calls", description="Number of tool calls per agent run", unit="1"
        )

        self.agent_unsafe_actions = meter.create_counter(
            "ledgerlens.agent.unsafe_actions", description="Unsafe actions attempted (should be 0)", unit="1"
        )

        # Queue metrics
        self.queue_depth = meter.create_up_down_counter(
            "ledgerlens.queue.depth", description="Current queue depth", unit="1"
        )

        # Error metrics
        self.errors_total = meter.create_counter(
            "ledgerlens.errors.total", description="Total errors by type", unit="1"
        )


# Global metrics instance
_metrics: Metrics | None = None


def get_metrics() -> Metrics | None:
    """Get global metrics instance."""
    return _metrics


def set_metrics(metrics_instance: Metrics) -> None:
    """Set global metrics instance."""
    global _metrics
    _metrics = metrics_instance
