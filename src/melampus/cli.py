"""Command-line entry point; optional receiver dependencies load only for watch."""

from __future__ import annotations

import argparse
import math
import sys

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
    args = parser.parse_args()
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
