# ADR-0002: Small queryable facts as span attributes; large/PII content as span events

## Status

Accepted — 2026-08-22

## Context

An instrumented span must carry two very different kinds of data. First,
bounded, queryable facts: artifact IDs, content hashes, generator identity,
semconv version, which checks ran, whether they passed, why one was
suppressed. Second, unbounded and potentially sensitive prose: intent text,
assumption language, spec excerpts — content that may quote internal
requirements documents. Backends index span attributes, so putting prose there
bloats indexes and leaks PII into the most-replicated part of the pipeline.
OpenTelemetry's GenAI semantic conventions faced exactly this with prompts and
completions, and settled on a precedent: metadata as span attributes,
message *content* as events, gated by an explicit content-capture mode.

## Decision

Follow the GenAI precedent. `code_artifact.*` **span attributes** hold only
bounded, enumerable, queryable values — identifiers, sha256 hashes of intent
and contract text, versions, booleans/enums for check outcomes and suppression
reasons. Intent and assumption **text** travels only as span events (e.g.
`code_artifact.intent`), and only when the operator has explicitly opted into
content capture; the default mode is hash-only, in which those events are never
emitted at all. No prose ever appears in a span attribute.

## Consequences

- The queryable core stays cheap and safe: backends can index and alert on
  every attribute without cardinality or PII risk, and the hash still allows
  exact-match joins back to source artifacts.
- Standard collector processors (`filter`, `transform`) can drop or redact the
  content events without touching the attributes — privacy controls compose
  from stock OTel parts, honoring "unmodified collector" and air-gapped
  postures.
- The watcher's deterministic rules operate on attributes alone, so drift
  detection works fully in hash-only mode; only the post-MVP LLM explanation
  path benefits from content events.
- Cost: consumers wanting intent text must handle two shapes (attribute
  lookup + event scan), and hash-only deployments trade explanation richness
  for privacy — an explicit, per-deployment dial, mirroring GenAI capture
  modes.
