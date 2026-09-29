# ADR-0008: Make the generation-time repair loop the first-release product

Status: Accepted for implementation — 2026-09-29

## Problem

The initial alpha implemented the telemetry foundation and positioned adoption
around CI/canaries. The product's primary problem is earlier: an agent can keep
generating behavior that diverges from intent faster than a human can review it.
A watcher alone reports drift but does not feed it into the active coding loop.

## Decision

0.1.0 includes a dedicated local supervisor, SDK Contract objects, a scenario
runner, an agent-neutral gate, and a Claude Code hook adapter. This supersedes
the founding spec's decision to defer live generation hooks. Existing wire
attributes and the optional OTLP watcher remain compatible foundations.

- Reviewed intent/predicates live outside the implementation being generated.
  `Contract.instrument()` uses the existing SDK. The disposable runner verifies
  exact check object identity and declarations for every required function.
- `melampus session` pins reviewed file hashes and observes scoped file contents.
  Each changed revision runs the reviewed scenario in a new interpreter with
  an always-on tracer. SDK evidence stays local; no collector/network export is
  needed. The runner is an application and owns its tracer; the core library
  remains OTel API-only as specified by ADR-0006.
- Every required function/check must execute. No evidence, suppressed checks,
  changed contracts, stale revisions, runner errors and timeouts are incomplete.
  Maximum 256 required checks and 10,000 observed spans per run; at most 32 drift
  examples are returned, with aggregate counts retained. Scenario timeout is
  at most ten seconds; normal completion/timeout cleans up its process group.
- Gates query a token-authenticated loopback supervisor. Saved state locates
  the process; saved status is never authority. One owner holds the state lock.
- Claude Code synchronous hooks check before/after tools and on Stop. Failed
  state restricts progression to inspection and scoped repair edits. Hooks feed
  evidence to the existing agent; Melampus neither launches nor pays for an LLM.
- macOS/Linux are the initial session platforms. Other agents integrate through
  the 0/1/2 gate contract. Native adapters beyond Claude Code are not claimed.

## Consequences and limitations

The operator still reviews executable claims and representative inputs. This is
an execution feedback system, not general semantic inference or a security
boundary. It does not interrupt unfinished model output, undo completed tools,
cancel arbitrary parallel agent work, or detect undeclared/unexercised slop.
Runtime/production monitoring is expansion, not the first-release adoption story.

As with tests, weak or wrong predicates remain weak or wrong. Contracts avoid
duplicating the same assertions across generated test files, but cannot eliminate
the oracle problem. A green session certifies only its exercised claims.

Hook behavior follows the [Claude Code reference](https://code.claude.com/docs/en/hooks).
The included command hooks use their own timeout shorter than the host timeout;
host-level hook cancellation can render no decision. Enabled hooks, a live
supervisor, reviewed scope, and cooperative agents are operating prerequisites.

## Required verification

Real subprocess tests must demonstrate healthy → edited drift → deny progression
and completion → allow repair → freshly healthy. They must also cover missing
instrumentation, omitted targets, predicate substitution, skipped execution,
same-size rapid edits, protected-file changes, stale runs, hangs, process death,
and local session ownership. Existing SDK/wire tests and distribution checks
continue to pass. Package artifacts must include the runner, supervisor, hooks,
and executable onboarding example.
