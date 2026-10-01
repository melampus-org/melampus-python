# Melampus

Keep an AI coding session aligned with reviewed intent. Give the agent a small
set of SDK contracts, run a local supervisor beside it, and feed execution
failures back into repair before the agent continues building.

**0.2.0 alpha. GitHub releases include validated wheels and sdists; PyPI
publication is separate.** The SDK and
wire schema are experimental. The supervisor needs no SaaS, LLM judge, tracing
backend, collector, or unit-test framework. Python 3.11+, macOS/Linux.

For a one-command demonstration of detection, agent hook decisions, and recovery:
`uv sync --locked --all-extras && make demo` (no model request is made).

See the [recorded Claude Code repair](docs/demos/pricing-session/README.md) for a
visual walkthrough, actual hook logs, source comparison, and commands to record
the same example with your own agent account.

## Start beside your coding agent

```text
Reviewed intent + SDK checks + executable scenario
                        ↓
Agent writes instrumented code → local supervisor executes fresh code
             ↑                                  ↓
             └──── repair ← drift / missing evidence
                                                ↓
                          healthy → continue the next change
```

From this checkout, install the session dependencies and activate the same
environment in both terminals:

```sh
uv sync --locked --all-extras
source .venv/bin/activate
cd examples/agent-session
melampus session
```

In another terminal, activate that environment, enter `examples/agent-session`,
and start `claude`. The example includes reviewed contracts, an input scenario,
agent instructions, and synchronous hooks. Review/enable the project hooks in
Claude Code before using them. Ask it to change `pricing.py`; it must preserve
the imported SDK contract. The supervisor polls source changes every 0.5 seconds
and checks the current revision again at each hook boundary.

Drift blocks shell/other progression tools and completion while leaving reads
and scoped Edit/Write repairs available. The gate reopens after fresh healthy
evidence. Removed instrumentation, skipped required checks, timeouts, crashes,
changed contracts, and a dead supervisor cannot count as a pass.

**Start here:** [setup and repair walkthrough](examples/agent-session/README.md) ·
[agent integration, limits, and test/CI comparison](docs/AGENT-SESSION.md).

This detects violations of **reviewed executable claims on exercised inputs**.
It cannot infer arbitrary intent from prose, inspect unfinished model tokens,
prove unexecuted behavior, or guarantee the absence of all AI-generated slop.
Review the claims and scenarios before asking the agent to implement them.

## Register reviewed contracts at the application boundary

Keep the reviewed definition in `intent.py`:

```python
from melampus import Check, Contract

PRICE = Contract(
    intent="Return a nonnegative price in cents",
    checks=(Check("nonnegative", lambda value: value >= 0, "Price is nonnegative."),),
)
CONTRACTS = {"pricing:price": PRICE}
```

Keep business functions plain in `pricing.py`:

```python
def price(cents: int) -> int:
    return max(0, cents)
```

Register once in `registration.py`, then call through that object:

```python
from types import SimpleNamespace
from melampus import instrument
from intent import PRICE
from pricing import price

pricing = instrument(
    SimpleNamespace(price=price),
    namespace="pricing",
    contracts={"price": PRICE},
    generator="claude-code",
)
pricing.price(-100)
```

For an existing service use
`instrument(PricingService(), namespace="pricing:PricingService", contracts={"price": PRICE})`
and review `pricing:PricingService.price` in `CONTRACTS`. Registration returns
the same typed object, preserves bound state and sync/async behavior, and never
changes the shared class. Register each instance before sharing it. Original
imports and captured references bypass registration; omitted methods are unconfigured.

For a few functions, the existing `@PRICE.instrument()` and `@instrumented(...)`
decorators remain supported. The original agent example/recording demonstrates
that approach; [the registration example](examples/sdk-registration/README.md)
shows all three styles beside an agent.

The session runner owns local OTel setup automatically. It verifies that the
function used the reviewed check objects and that every required check actually
ran. No network export is needed for this local path. The plain `@instrumented`
API remains available for applications that own their tracing configuration.
Multiple instances can share reviewed paths; conflicts remain incomplete and
a passing call cannot erase drift. The wire schema remains at **0.1.0**.

```sh
make demo-registration  # compare decorator, class and module-boundary repair
make demo-pilot         # synthetic measurement walkthrough, no human claims
make pilot ARGS='--participant p01 --rotation 0'  # local, resumable participant study
```

[API boundaries](docs/SDK-REGISTRATION.md) ·
[Official-source SDK/decorator research](docs/SDK-UX-RESEARCH.md) ·
[Pilot tasks and reports](examples/pilot_study/README.md).

## Optional OTLP foundation demo

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From this repository:

```sh
uv sync --locked --all-extras
make demo-otlp
```

This lower-level demo starts a finite watcher session, sends real OTLP from a healthy call,
then repeats with a seeded failure. It verifies zero healthy findings, exactly
one drift finding, and the corresponding exit codes. The watcher prints the
function, rule ID, contract hash, predicate result, and trace/span references.

To install from source without uv:

```sh
python -m pip install '.[watch,demo]'
python scripts/demo_session.py
```

## Instrument a function

```python
from melampus import Check, instrumented


@instrumented(
    intent="Return a nonnegative price in cents",
    checks=[Check("nonnegative", lambda result: result >= 0, contract="Result is nonnegative")],
)
def price():
    return 1200
```

Configure your application's OTel tracer provider and exporter as usual; the
library only uses the OTel API. See [the executable demo](https://github.com/melampus-org/melampus-python/blob/main/examples/demo/service.py)
for a complete configuration. Without a recording tracer, no checks run.
Ordinary and async functions are supported; generators are rejected.

A check receives the successful return value and must return exactly `bool`.
Use pure, fast synchronous predicates. Failed checks and ordinary check exceptions
do not alter the application's return value. Application exceptions and async
cancellation propagate unchanged. Python predicates are not sandboxed.

## Watch a test or canary session

```sh
melampus watch --duration 30
# In another terminal, send and flush OTLP/HTTP traces to:
# http://127.0.0.1:4318/v1/traces
```

The optional `watch` extra provides the protobuf receiver. `/healthz` indicates
readiness. The default interface is loopback; `--port 0` chooses a free port.
The duration starts at readiness. Producers must flush and collectors must drain
before it expires. Without a duration, Ctrl-C ends the session and prints its summary.

| Exit | Meaning |
| --- | --- |
| 0 | At least one evaluated check; no failures or incomplete evidence |
| 1 | One or more failed checks |
| 2 | No evaluated checks, check errors, invalid/unknown telemetry, capacity exhaustion, or other incomplete evidence |

Exit 2 takes precedence over drift. Suppressed checks never count as passes.
A healthy summary only describes the checks that were actually observed; it does
not prove all paths ran. Duplicate span deliveries are ignored within one session.

For the stock collector route, see [the collector demo](https://github.com/melampus-org/melampus-python/blob/main/examples/demo/README.md).

## Privacy and cost controls

Melampus exports SHA-256 declarations and bounded identifiers/results. It never
captures arguments, raw return values, intent prose, or exception messages.
`capture_content=True` is unsupported and raises immediately. Hashes are
identifiers, **not anonymization**; function/check names are visible metadata.
Other instrumentation and application exporters remain your responsibility.

```python
from melampus import Check, Policy, instrumented

policy = Policy(checks_per_second=100)


@instrumented(
    intent="Return a valid result",
    policy=policy,
    checks=[Check("valid", lambda result: result >= 0, "Result is nonnegative", sample=0.1)],
)
def compute():
    return 1


# Runtime operator control; use the emitted module:qualified_name exactly.
policy.configure(checks_per_second=100, disabled_paths=["my_app:compute"])
```

Share one Policy across functions to share a **per-process**, one-second fixed-window
execution limit. By default all functions share `DEFAULT_POLICY` with no limit.
This limits check counts, not CPU time or aggregate cost across worker processes.
Sampling can miss rare failures. OTel sampling and attribute limits also affect visibility.

## Status and development

The original **<3% checks-off overhead target is not yet met** against a bare
recording OTel span. The alpha distinguishes wrapper overhead from the cost of
carrying declarations, using an equivalent manual span as the wrapper baseline.
See [release evidence and limitations](https://github.com/melampus-org/melampus-python/blob/main/docs/RELEASE.md).
There is no claim that this alpha is ready for unrestricted production exposure.

```sh
make ci         # locked dependencies, semconv, lint, typing, coverage, package checks
make benchmark  # report actual latency; not a noise-sensitive CI pass/fail gate
```

[Contributing](https://github.com/melampus-org/melampus-python/blob/main/CONTRIBUTING.md) · [Security](https://github.com/melampus-org/melampus-python/blob/main/SECURITY.md) ·
[Wire attributes](https://github.com/melampus-org/melampus-python/blob/main/semconv/README.md) · [First-release contract](https://github.com/melampus-org/melampus-python/blob/main/docs/adr/0006-first-release-contract.md) ·
[Founding spec](https://github.com/melampus-org/melampus-python/blob/main/docs/SPEC.md)

Licensed under [Apache-2.0](https://github.com/melampus-org/melampus-python/blob/main/LICENSE).
