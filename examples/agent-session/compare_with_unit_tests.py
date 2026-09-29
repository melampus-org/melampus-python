"""Run an honest unit-test versus Melampus comparison against real edits."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from melampus.session import gate

ROOT = Path(__file__).resolve().parent
PRICING = ROOT / "pricing.py"
STATE = ROOT / ".melampus" / "comparison.json"
LOG = ROOT / ".melampus" / "comparison.log"


def run_pytest(*paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )


def wait_for_state(expected: str, timeout: float = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        report, _ = gate(STATE, {})
        last = report
        if report.get("state") == expected:
            return report
        time.sleep(0.05)
    raise RuntimeError(f"expected Melampus state {expected!r}, last report was {last!r}")


def hook_blocks() -> bool:
    event = {
        "hook_event_name": "PreToolUse",
        "cwd": str(ROOT),
        "tool_name": "Bash",
        "tool_input": {"command": "continue with unrelated work"},
    }
    _, decision = gate(STATE, event)
    return bool(decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")


def status(result: subprocess.CompletedProcess[str]) -> str:
    return "PASS" if result.returncode == 0 else "FAIL"


def main() -> int:
    original = PRICING.read_text()
    STATE.parent.mkdir(exist_ok=True)
    with LOG.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "melampus",
                "session",
                "--config",
                str(ROOT / "melampus.toml"),
                "--state",
                str(STATE),
                "--interval",
                "0.05",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            text=True,
        )
        try:
            wait_for_state("healthy")

            PRICING.write_text(original.replace("return min(10000, max(0, cents))", "return cents"))
            smoke_drift = run_pytest("unit_tests/test_pricing_smoke.py")
            full_drift = run_pytest("unit_tests")
            drift = wait_for_state("drift")
            drift_blocked = hook_blocks()

            PRICING.write_text(original)
            wait_for_state("healthy")
            PRICING.write_text(original.replace('@PRICE.instrument(generator="example")\n', ""))
            smoke_unobserved = run_pytest("unit_tests/test_pricing_smoke.py")
            full_unobserved = run_pytest("unit_tests")
            incomplete = wait_for_state("incomplete")
            incomplete_blocked = hook_blocks()

            rows = [
                (
                    "return cents",
                    status(smoke_drift),
                    status(full_drift),
                    drift["state"].upper(),
                    "BLOCKED" if drift_blocked else "ALLOWED",
                ),
                (
                    "remove decorator",
                    status(smoke_unobserved),
                    status(full_unobserved),
                    incomplete["state"].upper(),
                    "BLOCKED" if incomplete_blocked else "ALLOWED",
                ),
            ]
            print("\nEDIT                 SMOKE UNIT  FULL UNIT  MELAMPUS    NEXT AGENT ACTION")
            print("-------------------  ----------  ---------  ----------  -----------------")
            for row in rows:
                print(f"{row[0]:19}  {row[1]:10}  {row[2]:9}  {row[3]:10}  {row[4]}")

            expected = [
                ("return cents", "PASS", "FAIL", "DRIFT", "BLOCKED"),
                ("remove decorator", "PASS", "PASS", "INCOMPLETE", "BLOCKED"),
            ]
            if rows != expected:
                print("\nUnexpected comparison result. See:", LOG, file=sys.stderr)
                return 1
            print(
                "\nFull boundary tests catch the behavioral defect when they run. "
                "Melampus adds change-triggered execution, required evidence, and an agent gate."
            )
            return 0
        finally:
            PRICING.write_text(original)
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
