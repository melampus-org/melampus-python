"""Build a portable visual walkthrough from a verified live Claude recording."""

from __future__ import annotations

import argparse
import base64
import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(recording: Path, output: Path) -> None:
    run = json.loads((recording / "run.json").read_text())
    if not run.get("verified") or not run.get("live_hooks_verified"):
        raise ValueError("This walkthrough requires a verified live Claude recording.")
    events = {event["phase"]: event for event in run["events"]}
    hooks = [json.loads(line) for line in (recording / "hooks.jsonl").read_text().splitlines()]
    messages = [
        json.loads(line) for line in (recording / "agent-transcript.jsonl").read_text().splitlines()
    ]
    edit_count = sum(
        block.get("type") == "tool_use" and block.get("name") == "Edit"
        for message in messages
        for block in message["content"]
    )
    epoch = datetime.fromisoformat(run["recorded_at"]).timestamp()

    def hook_time(event: str, tool: str | None) -> float:
        return next(h["time"] - epoch for h in hooks if h["event"] == event and h["tool"] == tool)

    stages = [
        (
            events["healthy_baseline"]["elapsed_seconds"],
            "healthy",
            "Baseline accepted",
            "Five inputs exercise three approved rules: 15 evaluations pass.",
        ),
        (
            events["drift_detected"]["elapsed_seconds"],
            "drift",
            "The harness removes both clamps",
            "The supervisor detects two failed evaluations before any gate query.",
        ),
        (
            hook_time("PreToolUse", "Bash"),
            "blocked",
            "Claude’s shell action is denied",
            "The real hook sends nonnegative and capped failures back to Claude.",
        ),
        (
            hook_time("PostToolUse", "Edit"),
            "healthy",
            "Claude repairs pricing.py",
            "One Edit restores the bounds. Fresh execution passes all 15 evaluations.",
        ),
        (
            hook_time("Stop", None),
            "healthy",
            "Completion is accepted",
            "The Stop hook accepts the result. Five reviewed files remain unchanged.",
        ),
    ]
    timeline = "".join(
        f'<li class="{state}"><span class="time">T+{t:.1f}s</span>'
        f'<div><span class="state">{state}</span><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(description)}</p></div></li>"
        for t, state, title, description in stages
    )
    fixtures = json.loads((recording / "fixture-results.json").read_text())
    rows = ""
    for index, value in enumerate(fixtures["inputs_cents"]):
        before, drift, after = (
            fixtures["outputs"][name][index] for name in ("before.py", "drift.py", "after.py")
        )
        marker = ' class="failed"' if drift != after else ""
        rows += (
            f"<tr><th>{value:,}</th><td>{before:,}</td><td{marker}>{drift:,}"
            f"{' · fails' if drift != after else ''}</td><td>{after:,}</td></tr>"
        )
    names = [
        "run.json",
        "hooks.jsonl",
        "agent-transcript.jsonl",
        "supervisor.log",
        "before.py",
        "drift.py",
        "after.py",
        "intent.py",
        "exercise.py",
        "fixture-results.json",
    ]
    downloads = "".join(
        f'<a download="{name}" href="data:application/octet-stream;base64,'
        f'{base64.b64encode((recording / name).read_bytes()).decode()}">{name}<span>↓</span></a>'
        for name in names
    )
    code = {
        name: (recording / name).read_text()
        for name in ("drift.py", "after.py", "intent.py", "exercise.py")
    }
    replacements = {
        "TIMELINE": timeline,
        "ROWS": rows,
        "DOWNLOADS": downloads,
        "CODE_DATA": json.dumps(code).replace("<", "\\u003c"),
        "EDIT_COUNT": str(edit_count),
        "DETECTION": f"{events['drift_detected']['detection_seconds']:.2f}",
        "DATE": html.escape(run["recorded_at"][:10]),
        "CLAUDE_VERSION": html.escape(run["claude_version"]),
        "PASSED": str(events["repair_verified"]["report"]["checks"]["passed"]),
    }
    page = (ROOT / "docs/demo-walkthrough.template.html").read_text()
    for key, value in replacements.items():
        page = page.replace("{{" + key + "}}", value)
    if "{{" in page:
        raise ValueError("Unresolved template marker")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page)
    print(f"Built {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.recording, args.output)
