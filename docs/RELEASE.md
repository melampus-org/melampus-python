# First release: 0.1.0 alpha

## Next alpha: registration and onboarding

The 0.2.0 development branch mirrors TypeScript 0.2.0's explicit class/module
registration and measured pilot, adapted to Python method binding and native
decorators. The package version remains 0.1.0 until a reviewed release bump.
The wire schema remains 0.1.0 independently of the SDK version.

Run `make ci`, `make demo`, `make demo-registration` and `make demo-pilot`.
The distribution check installs the built wheel in a separate environment and
executes the original session plus registration and synthetic pilot demos.
CI verifies the same behavior across its Python/macOS/Linux matrix. Research
and API boundaries are in [SDK-UX-RESEARCH.md](SDK-UX-RESEARCH.md) and
[SDK-REGISTRATION.md](SDK-REGISTRATION.md). Human comfort/preference remains
unmeasured; synthetic output verifies collection rather than adoption benefits.

## Scope and evidence

The primary product is a local AI coding-session supervisor: reviewed SDK
contracts, fresh execution after edits, required-check evidence, and synchronous
Claude Code hooks that restrict progression until the implementation is repaired.
See [ADR-0008](adr/0008-local-agent-session-first.md) and the
[setup guide](AGENT-SESSION.md). Service monitoring is later expansion.

The implementation also covers the frozen schema, synchronous/async decorator,
privacy rules, sampled checks, per-process execution limits, OTLP/HTTP watcher,
finite CI sessions, and direct/stock-collector demos. It does not implement raw-content capture,
LLM judges, distributed budgets, gRPC/JSON OTLP reception, or a production backend.

Verification commands:

```sh
make ci
make demo
make demo-otlp
make benchmark
# With a stock collector running:
uv run --locked python scripts/demo_session.py \
  --collector http://127.0.0.1:4319/v1/traces --watch-port 4318
```

The initial 60-test suite also passed against the declared OTel 1.25.0 minimum using
the built wheel in an isolated Python 3.11 environment.

The earlier SDK/watcher baseline had 61 tests and 93.6% coverage. The agent-session
revision adds real-process integration checks for drift/repair, hook decisions,
missing instrumentation, predicate substitution, omitted targets, suppression,
rapid edits, stale runs, protected files, timeouts, process death and session
ownership. Coverage includes disposable subprocesses. Current validation results
are recorded in the PR; the earlier baseline's green CI is not evidence for a
new revision. `make ci` also exercises the local session from an externally
installed wheel.

Local integration passed both healthy (zero findings, exit 0) and drift (one finding,
exit 1) with the real OTel Python HTTP exporter, directly and through the official
Collector Contrib 0.161.0 native binary. The binary SHA-256 was verified against
its upstream release checksum. Docker was not running locally; the GitHub CI collector job passed the Compose demo.
All eight checks passed on the earlier implementation commit, including Linux Python
3.11–3.14, macOS Python 3.11/3.14, the version guard, and the collector integration.

**Performance limitation:** an initial macOS ARM64 / Python 3.11 recording-span
benchmark measured 4.74 μs for a bare OTel span and 8.02 μs for an instrumented
call with no checks (~3.28 μs / 69% extra). This is a local microbenchmark, not a
production SLA. The founding spec's <3% target remains **unmet**. The benchmark
reports it explicitly; CI does not hide the failure behind a noisy timing gate.
The alpha accepts this documented declaration cost under
[ADR-0007](adr/0007-alpha-performance-baseline.md), which revises the SDK-overhead
comparison to equivalent manual OTel work while retaining the total-cost metric.
The equivalent-work experiment measured 8.09 μs manually versus 8.05 μs with
Melampus (indistinguishable within noise). No claim of satisfying the original
bare-span target should appear in release announcements.

The first release review must confirm the name `melampus` and its PyPI ownership.
Both `melampus` and `melampus-python` returned 404 from PyPI during preparation;
that does not reserve either name. The import name and documented distribution
are `melampus`.

## Version and GitHub release

`VERSION` is the single package version source, consumed by Hatchling. Prepare a
reviewed change with its matching CHANGELOG entry. Main merges affecting VERSION
or CHANGELOG invoke release.yml, which runs `make ci` **before** creating an
annotated tag and GitHub alpha release containing wheel and sdist artifacts.
Do not create tags manually. A manual rerun repairs a missing release only if the
existing tag identifies the current build. Already published releases are left alone.

PyPI publication is a separate manual workflow because bot-created GitHub release
events do not automatically trigger another workflow with the default token.

## One-time registry setup (project owner)

Configure a pending trusted publisher in **each** registry you intend to use:

| Field | Value |
| --- | --- |
| Project name | `melampus` |
| Owner | `melampus-org` |
| Repository | `melampus-python` |
| Workflow filename | `publish.yml` |
| Environment | `testpypi` on TestPyPI; `pypi` on PyPI |

No long-lived PyPI token is required. Restrict the GitHub `pypi` environment to
main and maintainers who may publish. See [PyPI's publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
These settings must exist before the first registry upload; the workflow cannot
create ownership on your behalf.

## Publish

1. Resolve review blockers, merge the version PR, and inspect the validated GitHub artifacts.
2. Dispatch **Publish Python package** from `main`, with the existing tag and
   `registry=testpypi`. It validates tag ancestry/version, rebuilds and tests, and
   uploads from a separate job with only OIDC permission.
3. Install the TestPyPI artifact with its `session` extra into a fresh environment
   and rerun the local agent-session demo and enabled Claude hook walkthrough.
   Download the exact project/version from TestPyPI without dependencies, then
   install that wheel with dependencies from the normal PyPI index; avoid combining
   indexes for general dependency resolution.
4. Dispatch the same workflow with `registry=pypi`, then verify install, CLI and
   import from the real index. Update README's preparation notice after publication.

Uploads are immutable. Fix a bad published package with a new patch release;
never attempt to overwrite an existing distribution filename.
