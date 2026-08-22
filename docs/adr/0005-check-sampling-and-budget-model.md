# ADR-0005: Two-layer cost control — per-check sampling under a per-service budget

## Status

Accepted — 2026-08-22

## Context

Runtime cost is a first-class dial. Declaration attributes are near-free
(computed once at import, copied onto spans), but *check bodies* execute user
code on the request path and can be arbitrarily expensive. Platform teams need
a hard ceiling per service, developers need per-call-site tuning, and
operators need a kill switch per path — while the core promise must survive
all of it: **the declaration is emitted even when the check is off**, because
the watcher and any future consumer reason over declarations, not over check
execution.

## Decision

Cost control has two layers plus an override:

1. **Per-check sample rate** (`sample=0.01` on the check declaration): a
   deterministic head decision at the call site — cheap, local, no
   coordination. MVP ships this.
2. **Per-service check budget**: a process-wide token bucket (checks/second,
   configured via env/config per service). A check only runs if it passes its
   sample rate *and* acquires budget. MVP ships a minimal fixed-rate version;
   full token-bucket accounting is post-MVP.
3. **Per-path disable**: configuration can force checks off for a module/
   function path — an operator kill switch that needs no redeploy of code.

In every suppressed case the span still carries the full declaration plus a
suppression marker with its reason (`sampled_out` | `budget` | `disabled`), so
suppression itself is observable.

## Consequences

- Worst-case check cost per service is bounded and configurable — the
  platform persona gets a single number to reason about, independent of how
  many decorated functions ship in a release.
- The watcher's declaration-based rules keep working at any sampling level;
  what sampling changes is *detection latency* (fewer executed checks →
  longer time-to-first-violating-sample), which is a visible, tunable
  trade-off rather than a silent gap.
- Suppression markers make the dial auditable: "how often are checks actually
  running in prod" is a standard attribute query, and a service quietly
  running at budget exhaustion is detectable rather than invisible.
- Head-based decisions mean no dependency on tail sampling or any collector
  feature — consistent with the unmodified-collector constraint.
- Cost: two knobs interact (a call must pass both), which needs crisp
  documentation; deterministic per-call sampling can under-sample rare code
  paths — accepted for MVP, revisit with evidence.
