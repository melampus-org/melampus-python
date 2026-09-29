# Contributing

Use Python 3.11+ and uv. Work on a branch in a dedicated worktree; see CLAUDE.md.

```sh
uv sync --locked --all-extras
uv run --locked pre-commit install
make ci
```

`make format` changes formatting; `make lint` is read-only. `uv.lock` pins developer
tools; CI runs the same Make targets. Run `make test` for a focused functional check,
`make cov` for coverage, and `make benchmark` for overhead measurements.
`make demo` exercises the local coding-session protocol and repair cycle without
an LLM request; `make demo-otlp` exercises the optional tracing foundation.
Subprocess coverage is enabled so disposable scenario runners are measured too.

Wire names originate in `semconv/code_artifact.yaml`. After a reviewed wire change:

```sh
uv run --locked python scripts/generate_semconv.py
make semconv
```

The generator validates against the vendored upstream Weaver JSON Schema and
checks generated names/docs. Update fixtures and both producer/consumer tests.
Do not add raw data to telemetry or interpret suppressed checks as passes.

Pull requests should explain the behavior change and show relevant verification.
Add regression tests for bugs and exercise the installed wheel for packaging changes.
Keep source compatibility for sync/async calls and avoid configuring global OTel
providers or exporters inside the library. Licensing follows Apache-2.0.

Version changes go through VERSION and CHANGELOG.md. Never create release tags
manually; see [release operations](docs/RELEASE.md).
