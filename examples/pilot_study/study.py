"""Local measurement harness; synthetic answers never count as human feedback."""

from __future__ import annotations

import csv
import json
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from melampus.session import Supervisor, hook_decision

from .fixtures import (
    ORDERS,
    STYLES,
    business,
    coverage_questions,
    entry,
    install_reviewed,
    reviewed,
    seed_drift,
)


def response(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError("Provide a nonempty response of at most 4000 characters.")
    return value.strip()


def changed_lines(before: str, after: str) -> dict[str, int]:
    """LCS additions/deletions; replacement = two lines, CRLF is normalized."""

    def lines(value: str) -> list[str]:
        return [] if not value else value.replace("\r\n", "\n").removesuffix("\n").split("\n")

    a, b = lines(before), lines(after)
    if max(len(a), len(b)) > 2000:
        raise ValueError("Pilot business file exceeds 2000 lines.")
    previous = [0] * (len(b) + 1)
    for line in a:
        current = [0]
        for j, other in enumerate(b, 1):
            current.append(previous[j - 1] + 1 if line == other else max(previous[j], current[-1]))
        previous = current
    common = previous[-1]
    return {
        "added": len(b) - common,
        "deleted": len(a) - common,
        "total": len(a) + len(b) - 2 * common,
    }


class PilotStudy:
    def __init__(
        self,
        directory: Path,
        *,
        participant: str,
        rotation: int = 0,
        mode: str = "participant",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", participant)
            or type(rotation) is not int
            or not 0 <= rotation < 6
            or mode not in {"participant", "synthetic"}
        ):
            raise ValueError("Use a pseudonymous ID, rotation 0–5 and participant/synthetic mode.")
        self.root = directory.resolve()
        self.file = self.root / "study.json"
        self.clock = clock
        self.last_tick: float | None = None
        self.lock = threading.RLock()
        if self.file.is_file():
            self.data = json.loads(self.file.read_text())
            if any(
                self.data.get(k) != v
                for k, v in {
                    "schema": 1,
                    "participant": participant,
                    "rotation": rotation,
                    "mode": mode,
                }.items()
            ):
                raise ValueError(
                    "Resume with the original identity, rotation and mode, or use a new directory."
                )
            if self.data.get("timer", {}) and self.data["timer"]["running"]:
                self.data["timer"]["running"] = False
                self.data["interruptions"] += 1
        else:
            if self.root.exists():
                raise ValueError("Refusing to overwrite a directory without study.json.")
            self.root.mkdir(parents=True)
            self.data: dict[str, Any] = {
                "schema": 1,
                "participant": participant,
                "rotation": rotation,
                "mode": mode,
                "created_at": datetime.now(UTC).isoformat(),
                "order": ORDERS[rotation],
                "index": 0,
                "stage": "setup",
                "timer": None,
                "interruptions": 0,
                "results": {},
                "preference": None,
            }
            for style in STYLES:
                folder = self.root / style
                folder.mkdir()
                (folder / "business.py").write_text(business(style))
                (folder / "entry.py").write_text(entry(style))
                install_reviewed(folder, style, False)
                self.data["results"][style] = {
                    **{
                        task: {"passed": False, "elapsed_ms": None, "attempts": []}
                        for task in ("setup", "second", "repair")
                    },
                    "integration_business_lines": None,
                    "second_business_lines": None,
                    "coverage": None,
                    "diagnosis": None,
                    "confusion": None,
                }
        self.write_reports()

    @property
    def style(self) -> str:
        return str(self.data["order"][self.data["index"]])

    @property
    def folder(self) -> Path:
        return self.root / self.style

    @property
    def result(self) -> dict[str, Any]:
        return dict_or_raise(self.data["results"][self.style])

    def expect(self, stage: str) -> None:
        if self.data["stage"] != stage:
            raise ValueError(f"Expected {stage}; study is at {self.data['stage']}.")

    def save(self) -> None:
        with self.lock:
            temporary = self.file.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, indent=2) + "\n")
            temporary.replace(self.file)

    def tick(self) -> None:
        with self.lock:
            timer = self.data["timer"]
            if self.last_tick is not None and timer and timer["running"]:
                now = self.clock()
                timer["elapsed_ms"] += max(0, now - self.last_tick) * 1000
                self.last_tick = now
            self.save()

    def start_timer(self) -> None:
        with self.lock:
            if self.data["stage"] not in {"setup", "second", "repair"}:
                raise ValueError("This task is not timed.")
            if self.data["timer"] is None:
                self.data["timer"] = {"task": self.data["stage"], "elapsed_ms": 0, "running": False}
            if not self.data["timer"]["running"]:
                self.last_tick = self.clock()
                self.data["timer"]["running"] = True
            self.save()

    def stop_timer(self) -> int:
        self.tick()
        elapsed = round(self.data["timer"]["elapsed_ms"])
        self.data["timer"] = None
        self.last_tick = None
        return elapsed

    def pause(self) -> None:
        with self.lock:
            self.tick()
            if self.data["timer"]:
                self.data["timer"]["running"] = False
            self.last_tick = None
            self.write_reports()

    def check(self) -> dict[str, Any]:
        stage = self.data["stage"]
        if (
            stage not in {"setup", "second", "repair"}
            or not self.data["timer"]
            or not self.data["timer"]["running"]
        ):
            raise ValueError("Start a timed task before checking.")
        second = stage != "setup"
        try:
            changed = [
                name
                for name, content in reviewed(self.style, second).items()
                if (self.folder / name).read_text() != content
            ]
            report = (
                {
                    "exit_code": 2,
                    "protected_changed": changed,
                    "message": "Restore the reviewed study files before checking.",
                }
                if changed
                else Supervisor(self.folder / "melampus.toml").check()
            )
        except (OSError, ValueError, TypeError):
            report = {"exit_code": 2, "message": "Unable to load study files."}
        if report["exit_code"] == 0 and report.get("checks", {}).get("passed") != (
            6 if second else 3
        ):
            report = {
                **report,
                "sdk_exit_code": 0,
                "exit_code": 2,
                "task_error": "unexpected_check_count",
                "message": "Register only price in setup; then price and discount. Leave label unconfigured and avoid duplicate wrappers.",
            }
        with self.lock:
            self.tick()
            self.result[stage]["attempts"].append(
                {
                    "exit_code": report["exit_code"],
                    "sdk_exit_code": report.get("sdk_exit_code", report["exit_code"]),
                    "elapsed_ms": round(self.data["timer"]["elapsed_ms"]),
                    "report": report,
                }
            )
            if report["exit_code"] == 0:
                submitted = (self.folder / "business.py").read_text()
                diff = changed_lines(
                    self.result["setup_business_snapshot"]
                    if stage == "second"
                    else business(self.style),
                    submitted,
                )
                self.result[stage].update(passed=True, elapsed_ms=self.stop_timer())
                if stage == "setup":
                    self.result["integration_business_lines"] = diff
                    self.result["setup_business_snapshot"] = submitted
                    install_reviewed(self.folder, self.style, True)
                    self.data["stage"] = "second"
                elif stage == "second":
                    self.result["second_business_lines"] = diff
                    self.data["stage"] = "coverage"
                else:
                    self.data["stage"] = "feedback"
            self.write_reports()
        return report

    def answer_coverage(self, answers: list[str]) -> None:
        with self.lock:
            self.expect("coverage")
            questions = coverage_questions(self.style)
            if len(answers) != len(questions) or any(
                a not in {"covered", "uncovered", "incomplete", "drift"} for a in answers
            ):
                raise ValueError(
                    "Answer all coverage questions with covered/uncovered/incomplete/drift."
                )
            items = [
                {**q, "answer": a, "correct": a == q["expected"]}
                for q, a in zip(questions, answers, strict=True)
            ]
            self.result["coverage"] = {
                "correct": sum(i["correct"] for i in items),
                "total": len(items),
                "items": items,
            }
            self.data["stage"] = "diagnosis"
            self.write_reports()

    def introduce_drift(self) -> dict[str, Any]:
        self.expect("diagnosis")
        if self.result.get("drift"):
            return dict_or_raise(self.result["drift"])
        if not self.result.get("drift_seeded"):
            seed_drift(self.folder)
            self.result["drift_seeded"] = True
            self.save()
        supervisor = Supervisor(self.folder / "melampus.toml")
        report = supervisor.check()
        if report["exit_code"] != 1:
            raise ValueError(
                "Drift must fail the price predicate; restore the original formula/integration and retry."
            )
        self.result["drift"] = {
            "report": report,
            "blocked": hook_decision({"hook_event_name": "Stop"}, report, supervisor).get(
                "decision"
            )
            == "block",
        }
        self.save()
        return dict_or_raise(self.result["drift"])

    def answer_diagnosis(self, cause: str, explanation: str) -> None:
        with self.lock:
            self.expect("diagnosis")
            if not self.result.get("drift") or cause not in {"result", "network", "missing"}:
                raise ValueError("Introduce drift first and choose result/network/missing.")
            self.result["diagnosis"] = {
                "cause": cause,
                "correct": cause == "result",
                "explanation": response(explanation),
            }
            self.data["stage"] = "repair"
            self.write_reports()

    def feedback(self, notes: dict[str, str]) -> None:
        with self.lock:
            self.expect("feedback")
            self.result["confusion"] = {
                key: response(notes[key]) for key in ("setup", "second", "errors")
            }
            self.data["index"] += 1
            self.data["stage"] = "preference" if self.data["index"] == len(STYLES) else "setup"
            self.write_reports()

    def finish(self, style: str, reason: str) -> None:
        with self.lock:
            self.expect("preference")
            if style not in (*STYLES, "no-preference"):
                raise ValueError("Choose wrapper/class/module/no-preference.")
            self.data["preference"] = {"style": style, "reason": response(reason)}
            self.data["stage"] = "done"
            self.data["completed_at"] = datetime.now(UTC).isoformat()
            self.write_reports()

    def write_reports(self) -> None:
        with self.lock:
            self.save()
            rows = []
            preference = self.data["preference"]
            for style in self.data["order"]:
                r = self.data["results"][style]

                def minutes(task: str, result: dict[str, Any] = r) -> str:
                    value = result[task]["elapsed_ms"]
                    return "" if value is None else f"{value / 60000:.3f}"

                rows.append(
                    {
                        "style": style,
                        "setup_minutes": minutes("setup"),
                        "business_lines_changed": (r["integration_business_lines"] or {}).get(
                            "total", ""
                        ),
                        "second_method_minutes": minutes("second"),
                        "coverage_correct": f"{r['coverage']['correct']}/{r['coverage']['total']}"
                        if r["coverage"]
                        else "",
                        "diagnosis_correct": (r["diagnosis"] or {}).get("correct", ""),
                        "repair_passed": r["repair"]["passed"]
                        if r["repair"]["elapsed_ms"] is not None
                        else "",
                        "repair_minutes": minutes("repair"),
                        "setup_confusion": (r["confusion"] or {}).get("setup", ""),
                        "second_method_confusion": (r["confusion"] or {}).get("second", ""),
                        "error_confusion": (r["confusion"] or {}).get("errors", ""),
                        "preferred": preference["style"] == style if preference else "",
                        "preference_style": preference["style"] if preference else "",
                        "preference_reason": preference["reason"] if preference else "",
                    }
                )
            title = (
                "SYNTHETIC WALKTHROUGH — not participant feedback"
                if self.data["mode"] == "synthetic"
                else "Participant pilot feedback"
            )

            def escape(value: Any) -> str:
                return str(value).replace("|", "\\|").replace("\n", "<br>").replace("\r", "")

            table = [
                "| Measure | " + " | ".join(self.data["order"]) + " |",
                "| --- | --- | --- | --- |",
            ]
            for key in rows[0]:
                if key != "style":
                    table.append(
                        "| "
                        + key.replace("_", " ")
                        + " | "
                        + " | ".join(escape(row[key]) for row in rows)
                        + " |"
                    )
            (self.root / "feedback.md").write_text(
                f"# {title}\n\nParticipant: {self.data['participant']}; rotation: {self.data['rotation']}; state: {self.data['stage']}.\n\n"
                + "\n".join(table)
                + "\n\nTask timers include reading, editing and gate execution. Explicit pauses exclude downtime. Unexpected interruptions resume at the last checkpoint (up to one second lost). Business-line changes count additions + deletions; registration-only entry.py edits are excluded. JSON contains attempts, submitted snapshots, quiz answers and explanations. Empty cells are pending. Preference is supplied, never inferred.\n"
            )
            with (self.root / "feedback.csv").open("w", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["participant", "mode", "rotation", "status", *rows[0]]
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            "participant": self.data["participant"],
                            "mode": self.data["mode"],
                            "rotation": self.data["rotation"],
                            "status": self.data["stage"],
                            **row,
                        }
                    )


def dict_or_raise(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid study state.")
    return value
