"""Report recording-span overhead; a target is not a claim of achieved latency."""

import json
import statistics
import timeit

from opentelemetry.sdk.trace import TracerProvider

from melampus import instrumented

provider = TracerProvider()
tracer = provider.get_tracer("benchmark")


def plain():
    with tracer.start_as_current_span("benchmark"):
        return 1


@instrumented(intent="Return one", tracer=tracer)
def decorated():
    return 1


# Alternate order across rounds to reduce drift bias. No exporter/network, 20k calls.
plain_times, decorated_times = [], []
for round_number in range(9):
    pairs = [(plain, plain_times), (decorated, decorated_times)]
    for function, measurements in pairs[:: 1 if round_number % 2 else -1]:
        measurements.append(timeit.timeit(function, number=20_000) / 20_000)
a, b = statistics.median(plain_times), statistics.median(decorated_times)
print(
    json.dumps(
        {
            "plain_span_us": a * 1e6,
            "instrumented_us": b * 1e6,
            "overhead_percent": (b / a - 1) * 100,
            "target_percent": 3.0,
            "target_met": b / a < 1.03,
        },
        indent=2,
    )
)
provider.shutdown()
