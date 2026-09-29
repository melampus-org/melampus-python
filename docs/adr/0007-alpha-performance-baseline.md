# ADR-0007: Separate SDK overhead from declaration telemetry cost

Status: Accepted for 0.1.0 alpha — 2026-09-28

## Evidence

The original spec asks for <3% extra latency versus a plain OTel span, without
specifying whether the reference span carries the same declaration attributes.
The first bare-span benchmark on macOS ARM64 / Python 3.11 measured ~4.74 μs
versus ~8.02 μs (+69%). The Linux GitHub runner measured ~13.46 μs versus
~25.19 μs (+87%). The original bare-span target is **not met**.

An equivalent-work experiment uses identical span names, privacy settings and
all nine declaration attributes, with no exporter on any timed path. Fifteen
rotating rounds of 20,000 calls measured medians of 4.82 μs (bare), 8.09 μs
(manual OTel with declarations), and 8.05 μs (Melampus). The difference between
manual equivalent work and Melampus is within measurement noise, not evidence
of a speedup. Most measured added time is the cost of carrying declarations. A subsequent
run of the checked-in benchmark measured 4.80 / 7.98 / 8.06 μs respectively
(~1.0% wrapper overhead, ~68% total overhead), consistent with this conclusion.

## Decision

For the experimental 0.1.0 release, distinguish two metrics:

1. **SDK wrapper overhead:** target <3% against a manual OTel span carrying the
   exact same declarations and privacy settings. This compares equivalent work.
2. **Total adoption overhead:** always report absolute microseconds and relative
   overhead against a bare span. Keep the original <3% ambition visible as unmet;
   do not advertise the alpha as adding <3% total tracing latency.

This explicitly revises the first-release performance criterion; it does not
reclassify the original measurement as a pass. The alpha accepts the documented
cost of carrying declarations. Production adopters must benchmark their actual
workload, sampling policy, Python/OTel versions and exporter configuration.

`make benchmark` emits platform/version, raw rounds, medians, both overheads and
both target results. Shared-runner timing is reported, not used as a flaky CI gate.
Negative deltas are noise, not guaranteed performance improvements. Functional
checks, schema compatibility, privacy and package validity remain hard release gates.

## Consequences

The SDK does not bypass OTel attribute validation, drop declarations or install a
custom tracer to force a favorable measurement. Future optimization work can target
telemetry construction with the full adoption cost still visible. This decision
supersedes the bare-span interpretation of SPEC's first-release overhead goal and
the corresponding release blocker recorded during initial preparation.
