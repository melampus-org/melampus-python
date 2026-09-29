"""Compare equivalent OTel work and also report the total declaration cost."""

from __future__ import annotations

import json
import platform
import statistics
import timeit

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from melampus import instrumented


def build_operation(tracer):
    @instrumented(intent="Return one", tracer=tracer)
    def operation():
        return 1

    return operation


def main():
    # Capture exactly the declaration that the decorated operation emits. The
    # capture provider is shut down before measurement; timed spans have no exporter.
    capture = TracerProvider()
    exporter = InMemorySpanExporter()
    capture.add_span_processor(SimpleSpanProcessor(exporter))
    build_operation(capture.get_tracer("capture"))()
    sample = exporter.get_finished_spans()[0]
    attributes, name = dict(sample.attributes), sample.name
    capture.shutdown()

    provider = TracerProvider()
    tracer = provider.get_tracer("benchmark")
    decorated = build_operation(tracer)

    def bare():
        with tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ):
            return 1

    def equivalent():
        with tracer.start_as_current_span(
            name, attributes=attributes, record_exception=False, set_status_on_exception=False
        ):
            return 1

    cases = [("bare", bare), ("equivalent", equivalent), ("instrumented", decorated)]
    samples = {name: [] for name, _ in cases}
    for round_number in range(15):
        # Rotate measurement order to reduce drift bias; retain all raw rounds.
        offset = round_number % len(cases)
        for label, function in cases[offset:] + cases[:offset]:
            samples[label].append(timeit.timeit(function, number=20_000) / 20_000 * 1e6)
    median = {name: statistics.median(values) for name, values in samples.items()}
    total_overhead = (median["instrumented"] / median["bare"] - 1) * 100
    wrapper_overhead = (median["instrumented"] / median["equivalent"] - 1) * 100
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "median_us": median,
                "rounds_us": samples,
                "total_overhead_percent": total_overhead,
                "wrapper_overhead_percent": wrapper_overhead,
                "original_bare_span_target_percent": 3.0,
                "original_bare_span_target_met": total_overhead < 3.0,
                "alpha_equivalent_span_target_percent": 3.0,
                "alpha_equivalent_span_target_met": wrapper_overhead < 3.0,
            },
            indent=2,
        )
    )
    provider.shutdown()


if __name__ == "__main__":
    main()
