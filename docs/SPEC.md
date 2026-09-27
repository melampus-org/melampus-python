# melampus-python — Founding Spec

Status: Implementation baseline for 0.1.0 alpha · License: Apache-2.0 · Python 3.11+ · OTel API ≥ 1.25

The precise first-release contract is [ADR-0006](adr/0006-first-release-contract.md);
it takes precedence over aspirational pilot goals below.

## Problem

AI agents now write a large and growing share of production code. Human review
capacity does not scale with it, and every existing answer attacks the problem
*before* runtime: static analysis, code indexing, eval suites. Meanwhile the one
artifact that could make runtime observation meaningful — the intent, the
assumptions, and the contract the code was generated to satisfy — is discarded
at merge time. When the code's behavior drifts from what it was meant to do,
nothing in the telemetry can say so, because the telemetry never knew the
intent existed.

## Thesis

At generation time, the intent already exists in the prompt, spec, or plan.
Emitting it *with* the code costs approximately zero. Code should be **born
instrumented**: its telemetry carries provenance and a declared contract, so an
observer can compare runtime behavior against declared intent continuously.
This behavior-vs-intent signal is the missing L3 sensor of the autonomous SDLC.
Everything travels as pure OpenTelemetry — any unmodified OTLP collector works.

**Stop indexing the code. Listen to it.**

## Personas

**P1 — Agent-heavy platform team.** A platform lead whose org runs coding
agents that land dozens of PRs per day across many services. They cannot review
each change deeply and need a runtime signal that generated units behave as
declared, with per-service cost controls and an air-gapped deployment path.

**P2 — OSS maintainer drowning in AI PRs.** A solo maintainer receiving a flood
of AI-generated contributions. They want contributions to carry
machine-readable intent and runtime checks, so drift surfaces in CI or canary
runs instead of in downstream bug reports they must triage by hand.

## User stories

**US-1 — Declare intent on a function (P1, P2).**
As a developer or agent, I decorate a function with `@instrumented`, declaring
intent, assumptions, and contract checks.
*Given* a function decorated with `@instrumented(intent=..., checks=[...])` and
a configured OTel tracer, *when* the function is called, *then* the emitted
span carries `code_artifact.*` provenance and declaration attributes, adds no
network calls of its own, and is accepted by an unmodified OTLP collector.

**US-2 — Privacy by default (P1).**
*Given* the default hash-only mode, *when* a span is exported, *then* no intent
or assumption text appears on the wire — only content hashes and metadata.
In 0.1.0, requesting content capture fails at decoration time. Opted-in content
events remain post-MVP.

**US-3 — Checks are sampled; declarations are not (P1).**
*Given* a check configured with sample rate `r`, *when* the function is called
N times (N large), *then* the check body executes on ≈ r·N calls, while every recording
span is given declaration attributes and per-check results. OTel sampling,
attribute limits, and export failures still bound what the watcher receives.

**US-4 — Budget exhaustion degrades gracefully (P1).**
*Given* the per-process check execution budget is exhausted, *when* an instrumented
function is called, *then* check bodies are skipped, the span still carries all
declaration attributes, and it is marked check-suppressed with reason `budget`.

**US-5 — Watcher catches seeded drift (P1, P2).**
*Given* a service emitting instrumented spans through a standard collector and
the watcher consuming OTLP, *when* a seeded drift occurs (runtime value
violates a declared check), *then* the watcher reports a finding within 60
seconds naming the function, the declared contract, the observed predicate result, the
violated rule ID, and a span reference.

**US-6 — Zero-infrastructure drift report (P2).**
*Given* a repo with instrumented code and the provided docker-compose (stock
OTel Collector), *when* `melampus watch` runs during a test or canary session,
*then* a human-readable drift report prints to the terminal. A finite session
exits 0 for evaluated healthy checks, 1 for drift, and 2 for incomplete/error
evidence. Producers flush and collectors drain before the session deadline.

## MVP cut line — the 5-minute hackathon demo

The demo shows exactly this, in order:

1. **Teaser (30 s, not live):** one slide/screenshot of a Claude Code skill
   generating a function that is already decorated — establishing "born
   instrumented" without a live-generation risk.
2. A small pre-written Python service whose handlers are decorated with
   `@instrumented`, declaring intent (hash-only) and two deterministic checks.
3. `docker compose up`: a stock `otel-collector` (contrib image, stock components
   with the supplied fan-out configuration) receiving OTLP.
4. Healthy traffic → spans with `code_artifact.*` attributes shown landing.
5. **Seed the drift:** flip an input flag so runtime behavior violates a
   declared check.
6. `melampus watch` prints the drift finding in the terminal: function,
   declared contract, observed vs declared, rule violated, span reference —
   within seconds, rule-based, no LLM.

**In MVP:** `semconv/` v0 of `code_artifact.*` (in this repo); SDK core
(`@instrumented`, hash-only default, per-check sample rate, minimal budget
knob); watcher CLI (`melampus watch`) with deterministic rules over OTLP;
demo assets (service + docker-compose + drift seeder).

**Out of MVP (post-hackathon):** live generation-side skill/hook; LLM judge
enrichment (openai-compatible, optional, degrades gracefully); dashboard; VS
Code extension; full token-bucket budget accounting; metrics/logs signals
beyond spans; content-capture mode (the reserved flag rejects enablement).

## Non-goals

We do not build: static analysis; code indexing or graphing; a tracing
backend; an eval framework; an agent framework; auth or multi-tenancy;
anything requiring a SaaS. The wire protocol is OTLP, unmodified — no custom
protocol, no custom backend, no phone-home.

## Success metrics

- **Drift MTTD:** < 60 s from first drifted span export to watcher finding in
  the demo; pilot target p95 < 5 min.
- **% generated units instrumented:** ≥ 90% of functions produced via the
  (post-MVP) generation skill carry declarations — measured as decorated
  units / generated units per repo.
- **Watcher precision on seeded drift:** in the demo, 100% of seeded drifts
  detected with zero findings on healthy traffic; pilot target precision
  ≥ 0.95 on a seeded-drift corpus.
- **Overhead:** an instrumented call with checks off adds < 3% latency versus
  a plain OTel span (microbenchmark kept in CI).

## Verification

Each stage of MVP work ends with its verification command passing and shown in
output; the demo path itself is the integration test: seeded drift must produce
exactly one finding and healthy traffic must produce none.
