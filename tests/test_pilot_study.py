import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Load examples as a package without putting the source SDK on sys.path. Installed
# wheel smoke tests use the same package with a separate working directory.
spec = importlib.util.spec_from_file_location(
    "pilot_study",
    ROOT / "examples/pilot_study/__init__.py",
    submodule_search_locations=[str(ROOT / "examples/pilot_study")],
)
package = importlib.util.module_from_spec(spec)
sys.modules["pilot_study"] = package
spec.loader.exec_module(package)

from pilot_study.cli import run_synthetic  # noqa: E402
from pilot_study.fixtures import ORDERS, STYLES, coverage_questions, solution  # noqa: E402
from pilot_study.study import PilotStudy, changed_lines  # noqa: E402


def test_synthetic_all_seven_measures_and_three_styles(tmp_path):
    study = PilotStudy(tmp_path / "demo", participant="demo", mode="synthetic")
    run_synthetic(study)
    assert study.data["stage"] == "done"
    assert "SYNTHETIC" in (study.root / "feedback.md").read_text()
    assert study.data["preference"]["style"] == "no-preference"
    for style in STYLES:
        r = study.data["results"][style]
        for task in ("setup", "second", "repair"):
            assert r[task]["passed"] and r[task]["elapsed_ms"] >= 0
            assert len(r[task]["attempts"]) == 2
        assert r["coverage"]["correct"] == 6
        assert r["diagnosis"]["correct"] and r["diagnosis"]["explanation"]
        assert r["drift"]["blocked"] and r["confusion"]["errors"]
        assert (
            r["integration_business_lines"]["total"] > 0
            if style == "wrapper"
            else r["integration_business_lines"]["total"] == 0
        )
        assert (
            r["second_business_lines"]["total"] > 0
            if style == "wrapper"
            else r["second_business_lines"]["total"] == 0
        )
    with (study.root / "feedback.csv").open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 3
    assert all(
        r["mode"] == "synthetic" and r["status"] == "done" and r["coverage_correct"] == "6/6"
        for r in rows
    )
    state = json.loads((study.root / "study.json").read_text())
    assert all(state["results"][s]["setup_business_snapshot"] for s in STYLES)


def test_pause_resume_and_interruption_exclude_downtime(tmp_path):
    clock = [0]
    kwargs = dict(participant="p01", clock=lambda: clock[0])
    study = PilotStudy(tmp_path / "p01", **kwargs)
    study.start_timer()
    clock[0] = 60
    study.pause()
    assert study.data["timer"]["elapsed_ms"] == 60000
    clock[0] = 500
    study = PilotStudy(tmp_path / "p01", **kwargs)
    study.start_timer()
    clock[0] = 510
    study.tick()  # emulate the last checkpoint before an unexpected termination
    clock[0] = 1000
    study = PilotStudy(tmp_path / "p01", **kwargs)
    assert study.data["interruptions"] == 1
    assert study.data["timer"]["elapsed_ms"] == 70000
    study.start_timer()
    solution(study.folder, study.style, False)
    assert study.check()["exit_code"] == 0
    assert study.data["results"]["wrapper"]["setup"]["elapsed_ms"] == 70000


@pytest.mark.parametrize(
    "mutation", ["protected", "missing", "early_second", "extra_label", "double_wrapper"]
)
def test_study_rejects_invalid_task_protocol(tmp_path, mutation):
    study = PilotStudy(tmp_path / "study", participant="p01", rotation=4)
    study.start_timer()
    solution(study.folder, "module", mutation == "early_second")
    if mutation == "protected":
        intent = study.folder / "intent.py"
        intent.write_text(intent.read_text() + "\n# changed\n")
    elif mutation == "missing":
        (study.folder / "intent.py").unlink()
    elif mutation == "extra_label":
        entry = study.folder / "entry.py"
        entry.write_text(
            entry.read_text()
            .replace(
                "from melampus import instrument",
                "from melampus import instrument, Contract, Check\nLABEL = Contract('label', (Check('present', lambda n: True, 'present'),))",
            )
            .replace("'price': PRICE", "'price': PRICE, 'label': LABEL")
        )
    elif mutation == "double_wrapper":
        entry = study.folder / "entry.py"
        entry.write_text(
            entry.read_text() + "\napi.price = PRICE.instrument(path='pilot:price')(api.price)\n"
        )
    report = study.check()
    assert report["exit_code"] == 2, report
    assert study.data["stage"] == "setup"
    if mutation in {"early_second", "extra_label", "double_wrapper"}:
        assert report["task_error"] == "unexpected_check_count" and report["sdk_exit_code"] == 0


def test_wrong_answers_and_no_preference_are_not_rewritten(tmp_path):
    study = PilotStudy(tmp_path / "study", participant="p01")
    for style in STYLES:
        study.start_timer()
        solution(study.folder, style, False)
        assert study.check()["exit_code"] == 0
        study.start_timer()
        solution(study.folder, style, True)
        assert study.check()["exit_code"] == 0
        answers = [q["expected"] for q in coverage_questions(style)]
        answers[0] = "uncovered"
        study.answer_coverage(answers)
        study.introduce_drift()
        study.answer_diagnosis("network", "I incorrectly thought this was transport.")
        study.start_timer()
        business = study.folder / "business.py"
        business.write_text(business.read_text().replace("min(0, cents)", "max(0, cents)", 1))
        assert study.check()["exit_code"] == 0
        assert not study.result["diagnosis"]["correct"]
        assert study.result["coverage"]["correct"] == 5
        study.feedback(dict.fromkeys(("setup", "second", "errors"), "none"))
    study.finish("no-preference", "All fit different use cases.")
    assert study.data["preference"]["style"] == "no-preference"


def test_rotations_identity_guard_and_completed_preservation(tmp_path):
    assert len({tuple(order) for order in ORDERS}) == 6
    for i, order in enumerate(ORDERS):
        study = PilotStudy(tmp_path / f"p{i}", participant=f"p{i}", rotation=i)
        assert tuple(study.data["order"]) == order
        with pytest.raises(ValueError, match="original identity"):
            PilotStudy(study.root, participant="different", rotation=i)
    with pytest.raises(ValueError, match="overwrite"):
        PilotStudy(tmp_path, participant="p01")
    for kwargs in (
        {"participant": "../escape"},
        {"participant": "p", "rotation": 6},
        {"participant": "p", "mode": "bad"},
    ):
        with pytest.raises(ValueError):
            PilotStudy(tmp_path / "invalid", **kwargs)


@pytest.mark.parametrize(
    "before,after,expected",
    [("a\nb\n", "a\nc\n", 2), ("a\r\n", "a\n", 0), ("", "a\n", 1), ("a\n", "", 1)],
)
def test_line_changes_have_defined_semantics(before, after, expected):
    assert changed_lines(before, after)["total"] == expected


def test_interactive_pause_resume_and_lock(tmp_path):
    directory = tmp_path / "study"
    command = [
        sys.executable,
        str(ROOT / "scripts/demo_pilot.py"),
        "--participant",
        "p01",
        "--dir",
        str(directory),
    ]
    first = subprocess.run(command, input="pause\n", capture_output=True, text=True, timeout=10)
    assert first.returncode == 0 and "Paused" in first.stdout, first.stderr
    state = json.loads((directory / "study.json").read_text())
    assert state["stage"] == "setup" and not state["timer"]["running"]
    solution(directory / "wrapper", "wrapper", False)
    resumed = subprocess.run(
        command, input="check\npause\n", capture_output=True, text=True, timeout=10
    )
    assert resumed.returncode == 0 and "Gate 0" in resumed.stdout, resumed.stderr
    assert json.loads((directory / "study.json").read_text())["stage"] == "second"
    lock = directory.with_name(directory.name + ".lock")
    lock.write_text("existing runner")
    locked = subprocess.run(command, input="pause\n", capture_output=True, text=True, timeout=10)
    assert locked.returncode != 0 and "runner lock" in locked.stderr
    assert lock.exists()
