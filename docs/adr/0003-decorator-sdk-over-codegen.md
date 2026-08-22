# ADR-0003: Decorator-based SDK ergonomics over a codegen step

## Status

Accepted — 2026-08-22

## Context

The SDK must let a human or an agent attach intent, assumptions, and checks to
a unit of code. Two shapes were considered. A **codegen** approach: a build or
commit step reads sidecar metadata (or specially formatted comments) and
generates instrumented wrappers. A **decorator** approach: a plain Python
decorator, `@instrumented(...)`, wraps the function at runtime using the OTel
API directly. The primary author of this code is a coding agent editing source
files in place; the primary constraint is that adoption must cost nothing —
no new build toolchain, no generated files to keep in sync, nothing that
breaks when a user's project has no build step at all (scripts, notebooks,
plain services).

## Decision

The SDK is decorator-based. `@instrumented` is an ordinary decorator on the
public API surface (`from melampus import instrumented`), taking intent text,
assumptions, and check declarations as arguments, and emitting spans via the
standard OTel tracer. There is no codegen step, no sidecar files, and no
import-time magic beyond the decorator itself. The declaration lives in the
source, adjacent to the code it describes, and travels through diffs and
reviews like any other line.

## Consequences

- Zero toolchain: `pip install melampus` and decorate — works in any project,
  which is precisely the OSS-maintainer persona's bar, and agents can emit it
  inline during generation with no post-processing hook.
- Declarations are code-reviewed by default, and refactors move them with the
  function; codegen's sync-drift failure mode (source changed, generated
  wrapper stale) cannot occur.
- Cost: per-call runtime overhead lands on us to control. The no-op/checks-off
  fast path must stay under the spec's <3% overhead budget, enforced by a
  CI microbenchmark.
- Granularity is function-shaped. Module- or block-level declarations are
  awkward as decorators; we accept this for MVP and will revisit only with
  concrete demand.
- Decorators execute at import, so declaration attributes (including hashes)
  can be computed once per process, keeping the hot path to attribute copies.
