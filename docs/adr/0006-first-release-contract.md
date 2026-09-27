# ADR-0006: First release execution and evidence contract

Status: Accepted for implementation — 2026-09-27

## Decision

The first release is **0.1.0 (alpha)**, distribution/import name `melampus`.
Python 3.11+; core depends on the OTel API, never configures a provider or exporter.
The application owns SDK configuration and flushing. `watch` and `demo` are extras.

This ADR resolves ambiguities in ADRs 0001–0005 and the founding spec:

- Freeze the wire contract and fixtures in a separate commit before implementing
  either producer or consumer. For this bootstrap, implementation may follow in
  the same review branch; the contract and its tests must land before any release.
  Subsequent wire changes require a schema version change and compatibility review.
- v0 uses fixed names, bounded parallel arrays (maximum 16 checks), with one
  result per check. IDs identify rules; SHA-256 identifies their declarations.
  These are private experimental conventions, not official OTel conventions.
- Checks are synchronous predicates over the successful return value, including
  awaited return values. Return exactly `bool`. Exceptions and non-bool results
  mean `error`; they do not replace the application's return value. Checks must
  be pure, fast, non-blocking, and must not mutate the result. Python cannot
  sandbox or forcibly time-limit arbitrary user predicates.
- Application exceptions/cancellation propagate unchanged. Checks then have
  `not_executed` results. Exception messages, stack traces, arguments, returned
  values and predicate errors are never captured by Melampus. The span has ERROR
  status without a description. Other installed instrumentation is outside this guarantee.
- Report `observed=false expected=true` for failed predicates, plus check ID,
  contract hash, function, trace ID, and span ID. Raw application values and
  human-readable contract prose are intentionally absent. Source code resolves hashes.
- `capture_content=True` raises `NotImplementedError` at decoration time; it must
  never silently enable an unimplemented privacy-sensitive capability.
- SHA-256 uses exact UTF-8 bytes without normalization; assumptions use compact
  UTF-8 JSON of the ordered list. Hashes are identifiers, not anonymization.
  Symbol names and check IDs are visible metadata; never embed secrets in them.
- Check sampling is deterministic from trace ID, span ID and check ID. Each check
  consumes one execution permit after passing sampling. Budget is a thread-safe
  **per-process fixed one-second window**, configured through a shared Policy.
  It limits execution count, not CPU time or aggregate service cost. Operators
  explicitly replace Policy configuration to disable paths without code changes.
- A non-recording OTel span skips checks. Declarations are offered to every
  recording span, subject to application sampling/export and attribute limits.
  Suppressed or missing checks are never interpreted as passes.
- The watcher accepts binary protobuf OTLP/HTTP POST `/v1/traces`, including gzip;
  other encodings/transports are explicitly unsupported in v0. It defaults to
  loopback and caps request size, socket wait and session deduplication memory.
- Findings deduplicate on (trace ID, span ID, check ID) within one session.
  This is bounded in-memory observation, not a durable exactly-once guarantee.
- `watch --duration N` is finite; `/healthz` signals readiness. The producer must
  flush and the collector must drain **before** the duration expires. SIGINT
  closes a continuous session. Exit 0 means at least one evaluated check and no
  findings/incompleteness; 1 means drift findings; 2 means invalid telemetry,
  errors, unknown schemas, check errors, no evaluated checks or capacity exhaustion.
  Exit 2 takes precedence over 1. Suppression counts always appear in the summary.

## Evidence and consequences

The separation between library API and application SDK follows
[OTel Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/).
Transport, success responses and retry expectations follow the
[OTLP specification](https://opentelemetry.io/docs/specs/otlp/).
The private namespace follows [OTel naming guidance](https://opentelemetry.io/docs/specs/semconv/general/naming/).
Publishing follows [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

The deterministic watcher reports the SDK's predicate evidence; it does not infer
arbitrary intent or reevaluate source code. Sampling can miss rare failures entirely.
The watcher is for local/CI use or a trusted network behind a secured collector;
it is not an authenticated, durable production tracing backend.
