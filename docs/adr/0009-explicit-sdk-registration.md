# ADR-0009: Explicit registration with native decorator compatibility

Status: accepted for 0.2.0 (2026-10-02), confirmed by the project owner.

## Context

TypeScript 0.2.0 alpha moves SDK setup to a selected-member registration map and
adds a measured pilot. Python has native decorators and different method binding,
module mutation and typing semantics. Port the workflow, not JavaScript mechanics.
See [official-source research](../SDK-UX-RESEARCH.md).

## Decision

Add `instrument(target, *, namespace, contracts, generator, policy, tracer)` for
ordinary instances, modules and SimpleNamespace boundaries. Return the same typed
object, wrap only selected functions and bound methods, preserve sync/async and
introspection, and never mutate shared classes. Validate the entire plan before
writing. Reject descriptors/dynamic or immutable objects explicitly. Retain
`instrumented` and `Contract.instrument`; allow optional stable `path=` on both.

Allow repeated matching declarations for shared reviewed paths; retain conflicts
and all failures. Sessions require each reviewed check to execute, not every
instance. Retain the 0.1.0 wire schema and API-only core dependency model.

Port the three-style demo and local, timed, resumable, counterbalanced pilot with
Markdown/CSV/JSON reports. Mark synthetic output separately. Human preference
and comfort remain unmeasured until actual participants supply feedback.

## Consequences

Class/grouped-function integration can leave business code plain. Captured raw
references, direct class calls, omitted members and unregistered instances bypass
registration. In-place changes are observable; register once before sharing.
Python typing preserves the target but cannot verify arbitrary string member
maps or predicate result types. Frozen/slot-only/framework models need a plain
adapter or existing decorators. Framework-wide and class-decorator APIs are
deferred pending feedback. The existing decorator agent demo and recorded 0.1.0
walkthrough remain reproducible compatibility examples.
