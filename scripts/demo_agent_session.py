"""Reproduce the agent protocol and repair cycle without making an LLM request."""

from __future__ import annotations

import json
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from melampus.session import gate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="melampus-agent-demo-") as temporary:
        root = Path(temporary)
        shutil.copytree(
            ROOT / "examples" / "agent-session",
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", ".melampus"),
        )
        state = root / ".melampus/session.json"
        with (root / "session.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "melampus",
                    "session",
                    "--config",
                    str(root / "melampus.toml"),
                    "--state",
                    str(state),
                ],
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 15
                while not state.exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("supervisor did not start")
                    time.sleep(0.05)
                report, _ = gate(state, {})
                assert report["exit_code"] == 0, report
                print("1. HEALTHY: 15 evaluations across 3 required SDK checks.")
                source = root / "pricing.py"
                original = source.read_text()
                source.write_text(
                    original.replace("return min(10000, max(0, cents))", "return cents")
                )
                report, decision = gate(
                    state, {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
                )
                assert report["exit_code"] == 1
                assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
                print("2. DRIFT: " + json.dumps(report["findings"], sort_keys=True))
                print("3. BLOCK: next Bash denied; Stop also blocked.")
                assert gate(state, {"hook_event_name": "Stop"})[1]["decision"] == "block"
                _, decision = gate(
                    state,
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(source)},
                    },
                )
                assert "permissionDecision" not in decision["hookSpecificOutput"]
                print("4. REPAIR: Edit on pricing.py permitted, reviewed intent stays frozen.")
                source.write_text(original)
                report, decision = gate(state, {"hook_event_name": "Stop"})
                assert report["exit_code"] == 0 and decision == {}
                print("5. HEALTHY: fresh revision passed; completion permitted.")
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=12)
        assert gate(state, {})[0]["exit_code"] == 2
        print("6. OFFLINE: stopped supervisor returns incomplete, never cached success.")
    print("Local agent-session protocol demo passed (no model request was made).")


if __name__ == "__main__":
    main()
