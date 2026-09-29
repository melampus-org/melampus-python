"""One healthy call or one seeded drift; flush before exiting."""

import argparse
import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from melampus import Check, instrumented


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drift", action="store_true")
    args = parser.parse_args()
    provider = TracerProvider(resource=Resource.create({"service.name": "melampus-demo"}))
    provider.add_span_processor(
        SimpleSpanProcessor(
            OTLPSpanExporter(
                endpoint=os.environ.get(
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces"
                )
            )
        )
    )

    @instrumented(
        intent="Return a nonnegative price in cents",
        checks=[
            Check("integer", lambda result: type(result) is int, "Result is an integer"),
            Check("nonnegative", lambda result: result >= 0, "Result is nonnegative"),
        ],
        tracer=provider.get_tracer("melampus-demo"),
    )
    def price(drift=False):
        return -1 if drift else 1200

    try:
        print(f"price={price(args.drift)}")
        if not provider.force_flush(timeout_millis=5000):
            raise SystemExit("telemetry flush timed out")
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
