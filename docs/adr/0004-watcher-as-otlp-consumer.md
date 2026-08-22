# ADR-0004: Watcher is a standalone OTLP consumer, not a collector processor

## Status

Accepted — 2026-08-22

## Context

The watcher compares runtime telemetry against declared contracts and raises
drift findings. Architecturally it could be (a) a **collector processor** — a
Go component compiled into an OTel Collector distribution, sitting inline in
the pipeline; or (b) a **standalone OTLP consumer** — its own process exposing
a standard OTLP receiver, fed by the user's existing collector through a stock
`otlp` exporter (fan-out alongside their real backend). The project's hardest
constraint is that *any OTLP collector must work unmodified*: users must not
be asked to build or run a custom collector distribution. The watcher is also
where the post-MVP LLM judge will live, meaning potentially slow,
openai-compatible network calls that must never sit in a telemetry hot path.

## Decision

The watcher is a standalone OTLP consumer: a Python process (`melampus watch`)
that listens on standard OTLP, evaluates deterministic rules over incoming
spans' `code_artifact.*` attributes, and reports findings (terminal output in
MVP). Users wire it in with three lines of stock collector config — an added
`otlp` exporter pointing at the watcher — or, in the zero-infra CI case, point
the app's OTLP endpoint directly at it. No collector forks, no custom
processors, no required collector at all.

## Consequences

- The "unmodified collector" constraint is honored by construction: adoption
  is config, not a rebuild, and works identically with vendor collector
  distributions users cannot recompile.
- The watcher stays out of the telemetry hot path. A slow rule — or, later, a
  slow LLM enrichment call — delays a finding, never a span reaching the
  user's real backend. This isolation is what makes the LLM path safely
  optional and air-gap-degradable.
- We stay in Python: one language across SDK and watcher, and the rules engine
  can share the semconv-generated constants from ADR-0001.
- Cost: one more deployable and one more OTLP hop; the watcher sees only what
  is exported to it, so head-sampling decisions upstream bound what drift it
  can observe (acceptable — ADR-0005 keeps declarations on every span).
- A processor could mutate or drop spans inline; the watcher deliberately
  cannot. Drift response stays advisory (findings), never enforcement in the
  pipe — consistent with the non-goals.
