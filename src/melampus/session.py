"""Local file-change supervisor and synchronous agent gate (macOS/Linux)."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import tomllib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any

IGNORED = {
    "__pycache__",
    ".git",
    ".venv",
    ".melampus",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
READ_TOOLS = {"Read", "Glob", "Grep", "AskUserQuestion"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Supervisor:
    def __init__(self, config: Path) -> None:
        self.config = config.resolve()
        self.root = self.config.parent
        data = tomllib.loads(self.config.read_text())
        self.contracts = data["contracts"]
        if not isinstance(self.contracts, str) or not self.contracts.isidentifier():
            raise ValueError("contracts must name a Python module in the project root")
        self.probe = self.local(data["probe"])
        self.watch = self.paths(data["watch"])
        self.protected = {self.config, self.local(self.contracts + ".py"), self.probe}
        self.protected.update(self.paths(data.get("protect", [])))
        if any(not p.is_file() for p in self.protected):
            raise ValueError("protected paths must be existing files")
        self.baseline = {p: digest(p) for p in self.protected}
        self.python_paths = self.paths(data.get("python_paths", ["."]))
        self.timeout = data.get("timeout", 5)
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 10
        ):
            raise ValueError("timeout must be between 0 and 10 seconds")
        if not self.watch:
            raise ValueError("watch must list source files or directories")
        self.revision = ""
        self.generation = 0
        self.report: dict[str, Any] = {"exit_code": 2, "message": "Not evaluated."}

    def local(self, name: str) -> Path:
        if not isinstance(name, str):
            raise ValueError("paths must be strings")
        path = Path(os.path.abspath(self.root / name))
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("paths must stay inside the project root")
        return path

    def paths(self, names: Any) -> list[Path]:
        if not isinstance(names, list):
            raise ValueError("paths must be a list")
        return [self.local(name) for name in names]

    def snapshot(self) -> str:
        files = set(self.protected)
        for source in self.watch:
            if source.is_dir():
                files.update(
                    p
                    for p in source.rglob("*")
                    if p.is_file() and not set(p.relative_to(self.root).parts) & IGNORED
                )
            else:
                files.add(source)
        entries = []
        for path in sorted(files):
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("watched symlink escapes project root")
            entries.append(
                (str(path.relative_to(self.root)), digest(path) if path.is_file() else "missing")
            )
        return hashlib.sha256(json.dumps(entries).encode()).hexdigest()

    def repair_path(self, name: str) -> bool:
        path = self.local(name).resolve()
        return path not in {p.resolve() for p in self.protected} and any(
            path == source.resolve() or (source.is_dir() and path.is_relative_to(source.resolve()))
            for source in self.watch
        )

    def run_probe(self) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="melampus-probe-") as directory:
            temporary = Path(directory)
            config, output = temporary / "input.json", temporary / "report.json"
            config.write_text(
                json.dumps(
                    {
                        "contracts": self.contracts,
                        "probe": str(self.probe),
                        "python_paths": [str(p) for p in self.python_paths],
                    }
                )
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    f"pycache_prefix={temporary / 'pycache'}",
                    "-m",
                    "melampus._probe",
                    str(config),
                    str(output),
                ],
                cwd=self.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                return {
                    "exit_code": 2,
                    "message": "Scenario timed out. Repair blocking code or ask the owner to review the scenario.",
                }
            finally:
                # Also reap background descendants after a successful scenario.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            if process.returncode or not output.is_file() or output.stat().st_size > 128_000:
                return {"exit_code": 2, "message": "Scenario exited without valid evidence."}
            return dict(json.loads(output.read_text()))

    def check(self) -> dict[str, Any]:
        try:
            revision = self.snapshot()
            if revision == self.revision:
                return self.report
            self.generation += 1
            changed = [
                str(p.relative_to(self.root))
                for p, value in self.baseline.items()
                if not p.is_file() or digest(p) != value
            ]
            if changed:
                report: dict[str, Any] = {
                    "exit_code": 2,
                    "protected_changed": sorted(changed),
                    "message": "Reviewed contract/configuration changed. Restore it or ask the owner to review and restart.",
                }
            else:
                report = self.run_probe()
            if self.snapshot() != revision:
                report = {
                    "exit_code": 2,
                    "message": "Source changed during evaluation; fresh evidence is required.",
                }
                self.revision = ""
            else:
                self.revision = revision
            self.report = {
                **report,
                "revision": revision,
                "generation": self.generation,
                "state": {0: "healthy", 1: "drift", 2: "incomplete"}[report["exit_code"]],
            }
        except (OSError, ValueError, KeyError, TypeError):
            self.revision = ""
            self.report = {
                "exit_code": 2,
                "state": "incomplete",
                "message": "Unable to evaluate current source/configuration.",
            }
        return self.report


def hook_decision(
    event: dict[str, Any], report: dict[str, Any], supervisor: Supervisor | None = None
) -> dict[str, Any]:
    """Deny progression while preserving reads and narrowly scoped repair edits."""
    name = event.get("hook_event_name")
    broken = report["exit_code"] != 0
    reason = (
        "Melampus: "
        + json.dumps(report, sort_keys=True)
        + "\nRepair the implementation using Edit/Write, then wait for fresh healthy evidence. Do not weaken contracts or continue unrelated work. If intent must change, ask the owner."
    )
    if name == "PreToolUse":
        tool = event.get("tool_name")
        if not isinstance(tool, str):
            tool = "unknown"
        if tool in READ_TOOLS:
            return {}
        can_edit = False
        if supervisor and tool in {"Edit", "Write"}:
            try:
                can_edit = supervisor.repair_path(event.get("tool_input", {}).get("file_path", ""))
            except (ValueError, TypeError, OSError):
                pass
        if (broken and not can_edit) or (tool in {"Edit", "Write"} and not can_edit):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        if broken:
            return {
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reason}
            }
    elif broken and name in {"PostToolUse", "Stop"}:
        return {"decision": "block", "reason": reason}
    elif broken and name == "PostToolUseFailure":
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": reason}}
    return {}


def serve(config: Path, state: Path, interval: float) -> int:
    # flock prevents a second supervisor from replacing a live session's state.
    # The first alpha targets the same Linux/macOS platforms as the CI matrix.
    import fcntl

    supervisor = Supervisor(config)
    state = state.resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    with state.with_suffix(".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("a supervisor already owns this state path") from exc

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(1)

            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                if self.path != "/gate" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16_384:
                        raise ValueError("invalid input size")
                    event = json.loads(self.rfile.read(length))
                    if not isinstance(event, dict):
                        raise ValueError("invalid event")
                    report = supervisor.check()
                    result = {
                        "report": report,
                        "decision": hook_decision(event, report, supervisor),
                    }
                    body = json.dumps(result).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                except (ValueError, OSError, TypeError):
                    self.close_connection = True

        class LocalServer(HTTPServer):
            def server_bind(self) -> None:
                TCPServer.server_bind(self)
                self.server_name = "localhost"
                self.server_port = self.server_address[1]

        with LocalServer(("127.0.0.1", 0), Handler) as server:
            server.timeout = interval
            with open(state, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                os.chmod(state, 0o600)
                json.dump(
                    {"port": server.server_port, "token": token, "root": str(supervisor.root)},
                    output,
                )
            print(f"READY melampus session; state={state}", flush=True)
            last = ""
            try:
                while True:
                    report = supervisor.check()
                    serialized = json.dumps(report, sort_keys=True)
                    if serialized != last:
                        print("SESSION " + serialized, flush=True)
                        last = serialized
                    server.handle_request()
            except KeyboardInterrupt:
                return 0
            finally:
                state.unlink(missing_ok=True)


def gate(state: Path, event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        descriptor = json.loads(state.read_text())
        if not isinstance(event.get("tool_input", {}), dict):
            raise ValueError("invalid tool input")
        if "cwd" in event and not Path(event["cwd"]).resolve().is_relative_to(
            Path(descriptor["root"])
        ):
            raise ValueError("hook belongs to a different project")
        # Never forward file contents, shell commands or tool output.
        minimal = {
            "hook_event_name": event.get("hook_event_name"),
            "tool_name": event.get("tool_name"),
            "tool_input": {"file_path": event.get("tool_input", {}).get("file_path", "")},
        }
        conn = http.client.HTTPConnection("127.0.0.1", descriptor["port"], timeout=25)
        try:
            conn.request(
                "POST",
                "/gate",
                json.dumps(minimal),
                {
                    "Authorization": "Bearer " + descriptor["token"],
                    "Content-Type": "application/json",
                },
            )
            response = conn.getresponse()
            body = response.read(128_001)
            if response.status != 200 or len(body) > 128_000:
                raise ValueError("invalid supervisor response")
            result = json.loads(body)
            return result["report"], result["decision"]
        finally:
            conn.close()
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        report = {
            "exit_code": 2,
            "state": "incomplete",
            "message": "Local supervisor unavailable. Start melampus session in its dedicated terminal; do not claim success.",
        }
        return report, hook_decision(event, report)
