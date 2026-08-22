# ADR-0001: Define the `code_artifact.*` semantic conventions before any code

## Status

Accepted — 2026-08-22

## Context

melampus's entire value is a wire contract: spans that carry provenance and
declared intent in a shape any OTLP consumer can rely on. Three components
(Python SDK, watcher, generation-side skill) must agree on that shape, and the
hard constraint "any unmodified OTLP collector must work" means the contract
*is* the product — the code is replaceable, the attribute names are not.
Building the SDK first would let its implementation details leak into the
conventions; building the watcher first would invent attributes the SDK never
emits. We also flagged an open question: does the semconv live in this repo or
a separate `melampus-semconv` repo?

## Decision

Sequence the work semconv-first: version 0 of the `code_artifact.*` extension
is authored, reviewed, and merged before any SDK or watcher code. It lives in
**this repo** under `semconv/` as YAML definitions plus generated markdown,
following the upstream OpenTelemetry semantic-conventions format so a future
upstream proposal is a copy, not a rewrite. The SDK and watcher are then built
*against* the merged v0 — attribute names in code are generated or validated
from the YAML, never hand-typed. A separate repo is deferred until a second
language SDK or an external consumer needs to pin the conventions
independently.

## Consequences

- The SDK and watcher can be developed in parallel once v0 merges, because the
  wire contract between them is already fixed.
- Wire-format changes become visible, reviewable diffs to `semconv/` — no
  silent attribute drift between emitter and consumer.
- Single-repo versioning means the hackathon phase has zero cross-repo
  coordination cost; the cost is a later extraction if/when other languages
  arrive (mechanical: the YAML is self-contained).
- Risk: designing conventions before usage invites over-modeling. Mitigation:
  v0 contains only what the MVP demo emits and reads; everything else waits
  for evidence.
