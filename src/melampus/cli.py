"""Command-line entry point; optional receiver dependencies load only for watch."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="melampus")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    watch = commands.add_parser("watch", help="receive OTLP/HTTP predicate evidence")
    watch.add_argument("--host", default="127.0.0.1")
    watch.add_argument("--port", type=int, default=4318)
    watch.add_argument("--duration", type=float, default=0, help="seconds; 0 waits for Ctrl-C")
    watch.add_argument("--max-spans", type=int, default=100_000)
    session = commands.add_parser("session", help="supervise an AI coding session locally")
    session.add_argument("--config", type=Path, default=Path("melampus.toml"))
    session.add_argument("--state", type=Path, default=Path(".melampus/session.json"))
    session.add_argument("--interval", type=float, default=0.5)
    gate = commands.add_parser(
        "gate", help="require fresh session evidence; adapt Claude Code hooks"
    )
    gate.add_argument("--state", type=Path, default=Path(".melampus/session.json"))
    gate.add_argument("--claude", action="store_true", help="read a Claude hook event from stdin")
    args = parser.parse_args()
    if args.command != "watch":
        raise SystemExit(session_command(args, parser))
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("duration must be finite and nonnegative")
    if not 0 <= args.port <= 65535 or args.max_spans < 1:
        parser.error("port must be 0–65535 and max-spans must be positive")
    try:
        from .watcher import run
    except ImportError:
        parser.error("watch requires: pip install 'melampus[watch]'")
    try:
        code = run(args.host, args.port, args.duration, args.max_spans)
    except OSError as exc:
        print(f"melampus: receiver could not start: {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


def session_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .session import gate, serve

    if args.command == "gate":
        event = {}
        if args.claude:
            try:
                raw = sys.stdin.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("oversized hook input")
                event = json.loads(raw)
                if not isinstance(event, dict) or event.get("hook_event_name") not in {
                    "PreToolUse",
                    "PostToolUse",
                    "PostToolUseFailure",
                    "Stop",
                }:
                    raise ValueError("unknown hook event")
            except (ValueError, TypeError):
                print(
                    "Melampus: invalid hook input; cannot establish fresh evidence.",
                    file=sys.stderr,
                )
                return 2
        report, decision = gate(args.state, event)
        print(json.dumps(decision if args.claude else report, sort_keys=True))
        return 0 if args.claude else int(report["exit_code"])
    if not math.isfinite(args.interval) or not 0.05 <= args.interval <= 10:
        parser.error("interval must be between 0.05 and 10 seconds")
    if sys.platform == "win32":
        parser.error("local sessions currently support macOS and Linux")
    try:
        # Check before publishing READY: the runner must be usable in this interpreter.
        from . import _probe  # noqa: F401

        return serve(args.config, args.state, args.interval)
    except ImportError:
        parser.error("session requires: pip install 'melampus[session]'")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"melampus: session could not start: {exc}", file=sys.stderr)
    return 2
