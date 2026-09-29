"""Run real exporter → watcher sessions and assert the demo's release contract."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def session(
    drift: bool,
    endpoint: str | None = None,
    port: int = 0,
    duration: float = 3,
    host: str = "127.0.0.1",
) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "melampus",
            "watch",
            "--host",
            host,
            "--port",
            str(port),
            "--duration",
            str(duration),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready_lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(
        target=lambda: ready_lines.put(process.stdout.readline().strip()), daemon=True
    )
    reader.start()
    try:
        ready = ready_lines.get(timeout=10)
        if not ready.startswith("READY "):
            raise RuntimeError(f"watcher did not start: {ready}")
        env = {
            **os.environ,
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint
            or ready.removeprefix("READY ").replace("0.0.0.0", "127.0.0.1") + "/v1/traces",
        }
        command = [sys.executable, str(ROOT / "examples/demo/service.py")]
        if drift:
            command.append("--drift")
        subprocess.run(command, env=env, check=True, timeout=20)
        output, errors = process.communicate(timeout=duration + 10)
        print(output, end="")
        findings = [line for line in output.splitlines() if line.startswith("DRIFT ")]
        assert len(findings) == int(drift), (output, errors)
        assert process.returncode == int(drift), (output, errors)
        if drift:
            finding = json.loads(findings[0].removeprefix("DRIFT "))
            assert finding["check_id"] == "nonnegative"
            assert finding["observed"] is False and finding["expected"] is True
    finally:
        if process.poll() is None:
            process.kill()
        reader.join(timeout=2)
        process.communicate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--collector", help="collector trace endpoint, e.g. http://127.0.0.1:4319/v1/traces"
    )
    parser.add_argument("--watch-port", type=int, default=0)
    parser.add_argument("--watch-host", default="127.0.0.1")
    args = parser.parse_args()
    for drift in (False, True):
        session(drift, args.collector, args.watch_port, 8 if args.collector else 3, args.watch_host)
    print("PASS: healthy=0 findings; seeded drift=1 finding")


if __name__ == "__main__":
    main()
