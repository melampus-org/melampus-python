# Stock collector demo

The direct `make demo` route requires no Docker. This variant proves the same
contract through an unmodified OpenTelemetry Collector Contrib 0.161.0, using
stock `otlp`, `batch`, `otlp_http`, and `debug` components.

```sh
uv sync --locked --all-extras
docker compose -f examples/demo/compose.yaml up -d
uv run --locked python scripts/demo_session.py \
  --collector http://127.0.0.1:4319/v1/traces \
  --watch-host 0.0.0.0 --watch-port 4318
docker compose -f examples/demo/compose.yaml down
```

The watcher binds to all interfaces for container-to-host access; run this on a
trusted development machine. The collector's published receiver port is bound
to host loopback. The debug exporter shows declaration attributes; the second
exporter fans out to the watcher. Use your existing backend exporter in place
of debug outside the demo.

For a native collector (same config, loopback-only watcher):

```sh
MELAMPUS_WATCH_ENDPOINT=http://127.0.0.1:4318 \
  otelcol-contrib --config=examples/demo/collector.yaml
# In another terminal:
uv run --locked python scripts/demo_session.py \
  --collector http://127.0.0.1:4319/v1/traces --watch-port 4318
```

The healthy session must return 0; the seeded session must return 1 and report
only the `nonnegative` check. Each runs for 8 seconds to allow the collector's
200 ms batch to drain. A timeout or export loss produces an incomplete session,
not a healthy result. The demo driver itself returns 0 only when both assertions pass.
