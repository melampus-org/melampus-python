# Recorded local Claude repair

[Download the visual walkthrough](walkthrough.html) and open it in a browser.
The HTML contains its own evidence downloads; it does not connect to the author's AI session.
[Preview the recorded timeline](recording.png).

This run used Melampus 0.1.0, Claude Code 2.1.284, and the first-release implementation
at commit `58abe4981196d91398f9ef2e8d6a1fc85a969e57`, on 2026-09-29.
The recorder was added alongside this evidence.

## What actually happened

The harness copied `examples/agent-session` into a disposable project and deliberately
replaced the price clamp with `return cents`. The supervisor detected the defect
before the harness queried the gate. This is a seeded bug, not a claim that Claude
independently introduced it.

A real Claude Code model session then attempted a harmless shell command. Melampus's
PreToolUse hook denied it and returned the two failed claims. Claude read the source
and contract, performed one Edit, and completed after fresh evidence passed all
15 evaluations (five inputs × three rules). Five reviewed files retained their hashes.

The model added `int(cents)` when restoring the bounds. The integer scenarios do not
prove that coercion is appropriate for other types. The agent itself noted this
limitation. The report demonstrates the feedback loop, not universal correctness,
typical latency, or measured human-review savings.

After the live repair, scripted controls verified that removing instrumentation and
stopping the supervisor both produce incomplete evidence (exit 2).

## Reproduce

From the repository root, with Python 3.11+ and uv on macOS/Linux:

```sh
uv sync --locked --all-extras

# No model request; scripted restoration exercises the actual protocol.
uv run --locked python scripts/record_agent_demo.py --output demo-recordings/protocol

# Real model request using your installed, signed-in Claude Code account.
uv run --locked python scripts/record_agent_demo.py --live-claude --output demo-recordings/live

# Build a report from a successful live recording.
uv run --locked python scripts/build_demo_walkthrough.py demo-recordings/live --output demo-recordings/walkthrough.html
```

Use a new recording directory each time. Live runs require the CLI options supported
by Claude Code 2.1.284 and can vary in model behavior. The recorder asserts the expected
outcomes and fails rather than presenting an unsuccessful run as verified.
The original live recording preceded the addition of the fixture replay helper;
the helper was then run against these exact saved source files.

For a normal two-terminal coding session, follow
[the example setup](../../../examples/agent-session/README.md) and
[agent integration guide](../../AGENT-SESSION.md).

## Evidence

- `run.json`: configuration provenance, phase reports, expected-outcome assertions,
  agent conclusion, and hashes of reviewed files.
- `hooks.jsonl`: actual hook event/tool names, timestamps and decisions.
- `agent-transcript.jsonl`: visible messages and tool requests/results. Authentication,
  session initialization, hidden reasoning and account/usage records are omitted.
- `supervisor.log`: actual state transitions from the local supervisor.
- `before.py`, `drift.py`, `after.py`: original, deliberately broken, and actual repaired source.
- `intent.py`, `exercise.py`: the approved rules and public scenario.
- `fixture-results.json`: post-run replay of the five public input values against the
  saved source snapshots. Raw fixture values are printed by the demo harness, not
  captured by SDK telemetry.
- `recording.png`: screenshot of the walkthrough timeline, derived from these logs.

Temporary project paths were replaced with `<demo-project>`.
This fixture is intentionally public. Inspect recordings before sharing if you adapt
the harness to private code or business inputs.

The walkthrough narrative and downloads work offline. Fonts and the optional
@pierre/diffs syntax viewer load from public CDNs.
