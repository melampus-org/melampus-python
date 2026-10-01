"""Run a participant pilot or an explicitly synthetic collection walkthrough."""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from .fixtures import coverage_questions, path_for, solution
from .study import PilotStudy


def run_synthetic(study: PilotStudy) -> None:
    if (
        study.data["mode"] != "synthetic"
        or study.data["stage"] != "setup"
        or study.data["index"] != 0
    ):
        raise ValueError("Synthetic walkthrough requires a new synthetic study.")
    while study.data["stage"] != "preference":
        style = study.style
        study.start_timer()
        assert study.check()["exit_code"] == 2
        solution(study.folder, style, False)
        assert study.check()["exit_code"] == 0
        study.start_timer()
        assert study.check()["exit_code"] == 2
        solution(study.folder, style, True)
        assert study.check()["exit_code"] == 0
        study.answer_coverage([q["expected"] for q in coverage_questions(style)])
        drift = study.introduce_drift()
        assert drift["report"]["exit_code"] == 1 and drift["blocked"]
        study.answer_diagnosis(
            "result", "Scripted: min returns a negative price for negative input."
        )
        study.start_timer()
        assert study.check()["exit_code"] == 1
        source = study.folder / "business.py"
        source.write_text(source.read_text().replace("min(0, cents)", "max(0, cents)", 1))
        assert study.check()["exit_code"] == 0
        study.feedback(
            dict.fromkeys(("setup", "second", "errors"), "Scripted walkthrough; no human feedback.")
        )
        print(
            f"{style}: setup, second method, coverage quiz, diagnosis, blocked drift, repair, notes recorded"
        )
    study.finish("no-preference", "Synthetic collection test; no human preference is measured.")


def run_participant(study: PilotStudy) -> None:
    stop = threading.Event()

    def checkpoint() -> None:
        while not stop.wait(1):
            study.tick()

    def ask(prompt: str, choices: tuple[str, ...] = ()) -> str:
        while True:
            answer = input(prompt + "\n> ").strip()
            if answer.lower() == "pause":
                raise EOFError
            if answer and len(answer) <= 4000 and (not choices or answer in choices):
                return answer
            print(
                "Choose " + " / ".join(choices)
                if choices
                else "Enter up to 4000 characters, or pause."
            )

    worker = threading.Thread(target=checkpoint, daemon=True)
    worker.start()
    try:
        print(f"Participant {study.data['participant']}; order: {' → '.join(study.data['order'])}.")
        print(
            "Use your usual editor. Type pause or Ctrl+C to save and exclude downtime. Preserve formulas/reviewed files. All results stay local."
        )
        while study.data["stage"] != "done":
            stage = study.data["stage"]
            if stage in {"setup", "second", "repair"}:
                print(f"\n{study.style}: {stage}. Edit {study.folder}")
                if stage == "setup":
                    print(
                        f"Register only price with PRICE from intent.py; path {path_for(study.style, 'price')}. For wrapper use @PRICE.instrument(path=...) in business.py. For class/module import instrument from melampus and register api in entry.py. Leave discount and label unregistered."
                    )
                elif stage == "second":
                    print(
                        f"Add DISCOUNT; both price and {path_for(study.style, 'discount')} are now required. Preserve formulas, leave label unconfigured."
                    )
                else:
                    print(
                        "Repair the failing price formula, keep both contracts/integrations, obtain a fresh gate 0."
                    )
                study.start_timer()
                ask("After editing, enter check to evaluate, or pause.", ("check",))
                report = study.check()
                print(f"Gate {report['exit_code']}: {json.dumps(report)}")
            elif stage == "coverage":
                print(
                    "Assume a recording tracer. covered/uncovered describe calls; incomplete/drift describe gates."
                )
                answers = [
                    ask(q["prompt"], ("covered", "uncovered", "incomplete", "drift"))
                    for q in coverage_questions(study.style)
                ]
                study.answer_coverage(answers)
                print("Answers saved; scores available after the study.")
            elif stage == "diagnosis":
                print(json.dumps(study.introduce_drift(), indent=2))
                cause = ask(
                    "Cause? result = predicate violated; network = transport problem; missing = method not exercised.",
                    ("result", "network", "missing"),
                )
                explanation = ask(
                    "Explain the failing behavior in your own words before repairing it."
                )
                study.answer_diagnosis(cause, explanation)
            elif stage == "feedback":
                notes = {
                    key: ask(prompt + " Enter none if nothing.")
                    for key, prompt in (
                        ("setup", "What confused you in setup?"),
                        ("second", "What confused you adding the second method?"),
                        ("errors", "Were failure messages understandable? Describe any confusion."),
                    )
                }
                study.feedback(notes)
            elif stage == "preference":
                style = ask(
                    "Which style would you use in your own project?",
                    ("wrapper", "class", "module", "no-preference"),
                )
                study.finish(style, ask("Why? Explain comfort, readability and setup tradeoffs."))
            else:
                raise ValueError("Unknown study stage.")
    except (KeyboardInterrupt, EOFError):
        print("\nPaused; repeat the same command to resume.")
    finally:
        stop.set()
        worker.join()
        study.pause()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", help="pseudonymous ID; repeat the same options to resume")
    parser.add_argument("--rotation", type=int, choices=range(6), default=0)
    parser.add_argument("--dir", type=Path)
    parser.add_argument(
        "--demo", action="store_true", help="synthetic collection test, not usability evidence"
    )
    args = parser.parse_args()
    participant = args.participant or (
        "demo-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") if args.demo else None
    )
    if participant is None:
        parser.error("provide --participant ID, or --demo")
    # Validate identity before using it in a filesystem path.
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", participant):
        parser.error("participant ID must be 1–64 letters/digits/_/-")
    directory = (args.dir or Path("pilot-results") / participant).resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    lock = directory.with_name(directory.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        parser.error(
            f"runner lock exists: {lock}; verify the earlier runner stopped before removing a stale lock"
        )
    try:
        os.close(descriptor)
        study = PilotStudy(
            directory,
            participant=participant,
            rotation=args.rotation,
            mode="synthetic" if args.demo else "participant",
        )
        if args.demo:
            print(
                "SYNTHETIC WALKTHROUGH: automated timings/answers are not human usability evidence."
            )
            run_synthetic(study)
        else:
            run_participant(study)
        study.write_reports()
        print(
            f"Study {study.data['stage']}. Reports: {directory}/feedback.md, feedback.csv, study.json"
        )
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
