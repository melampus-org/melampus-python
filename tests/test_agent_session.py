"""Exercise real edits, fresh interpreters and agent-protocol decisions."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from melampus.session import Supervisor, gate, hook_decision

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "agent-session"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__", ".melampus"))
    return root


def replace(root, old, new, file="pricing.py"):
    path = root / file
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def event(name, root, tool="Bash", path="pricing.py"):
    return {
        "hook_event_name": name,
        "cwd": str(root),
        "tool_name": tool,
        "tool_input": {"file_path": str(root / path)},
    }


def test_real_generation_drift_repair_and_fresh_imports(project):
    supervisor = Supervisor(project / "melampus.toml")
    healthy = supervisor.check()
    assert healthy["exit_code"] == 0, healthy
    assert healthy["checks"] == {"passed": 15}
    assert supervisor.check() is healthy
    replace(project, "return min(10000, max(0, cents))", "return cents")
    drift = supervisor.check()
    assert drift["exit_code"] == 1, drift
    assert {f["check_id"] for f in drift["findings"]} == {"nonnegative", "capped"}
    assert all(f["function"] == "pricing:price" for f in drift["findings"])
    replace(project, "return cents", "return min(10000, max(0, cents))")
    repaired = supervisor.check()
    assert repaired["exit_code"] == 0 and repaired["generation"] == 3


def test_unit_test_comparison_distinguishes_coverage_from_required_evidence(project):
    supervisor = Supervisor(project / "melampus.toml")
    assert supervisor.check()["exit_code"] == 0

    replace(project, "return min(10000, max(0, cents))", "return cents")
    smoke = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "unit_tests/test_pricing_smoke.py"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
    )
    complete = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "unit_tests"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert complete.returncode == 1, complete.stdout + complete.stderr
    assert supervisor.check()["exit_code"] == 1

    replace(project, "return cents", "return min(10000, max(0, cents))")
    replace(project, '@PRICE.instrument(generator="example")', "")
    complete = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "unit_tests"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert complete.returncode == 0, complete.stdout + complete.stderr
    assert supervisor.check()["exit_code"] == 2


@pytest.mark.parametrize(
    "edit", ["remove", "weaken", "rename", "suppress", "raise", "syntax", "empty"]
)
def test_bad_generation_cannot_report_healthy(project, edit):
    supervisor = Supervisor(project / "melampus.toml")
    assert supervisor.check()["exit_code"] == 0
    if edit == "remove":
        replace(project, '@PRICE.instrument(generator="example")', "")
    elif edit == "weaken":
        replace(
            project,
            "from intent import PRICE",
            "from melampus import Check, instrumented\nfrom intent import PRICE",
        )
        replace(
            project,
            '@PRICE.instrument(generator="example")',
            '@instrumented(intent=PRICE.intent, checks=[Check("nonnegative", lambda r: True, "Price is never negative.")])',
        )
    elif edit == "rename":
        replace(project, "def price(", "def renamed(")
        with (project / "pricing.py").open("a") as f:
            f.write("\nprice = renamed\n")
    elif edit == "suppress":
        replace(
            project,
            "from intent import PRICE",
            "from intent import PRICE\nfrom melampus import DEFAULT_POLICY\nDEFAULT_POLICY.configure(checks_per_second=0)",
        )
    elif edit == "raise":
        replace(project, "return min(10000, max(0, cents))", 'raise RuntimeError("SECRET")')
    elif edit == "syntax":
        replace(project, "return min", "invalid syntax min")
    else:
        (project / "pricing.py").write_text("")
    report = supervisor.check()
    assert report["exit_code"] == 2, report
    assert "SECRET" not in json.dumps(report)


@pytest.mark.parametrize(
    "file", ["intent.py", "exercise.py", "melampus.toml", ".claude/settings.json", "CLAUDE.md"]
)
def test_reviewed_inputs_frozen_until_owner_restarts(project, file):
    supervisor = Supervisor(project / "melampus.toml")
    path = project / file
    original = path.read_text()
    path.write_text(original + "\n")
    report = supervisor.check()
    assert report["exit_code"] == 2
    assert file in report["protected_changed"]
    path.write_text(original)
    assert supervisor.check()["exit_code"] == 0
    path.unlink()
    assert supervisor.check()["exit_code"] == 2


def test_missing_target_is_not_hidden_by_other_passes(project):
    with (project / "intent.py").open("a") as f:
        f.write('\nCONTRACTS["pricing:missing"] = PRICE\n')
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 2 and report["checks"]["passed"] == 15
    assert report["undeclared"] == ["pricing:missing"]
    assert "pricing:missing/nonnegative" in report["missing"]


def test_same_size_same_mtime_edit_uses_new_code(project):
    supervisor = Supervisor(project / "melampus.toml")
    assert supervisor.check()["exit_code"] == 0
    path = project / "pricing.py"
    original_stat = path.stat()
    replace(project, "max(0, cents)", "max(9, cents)")
    # Still healthy; create a different equal-length edit that violates the cap.
    replace(project, "min(10000,", "min(90000,")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert supervisor.check()["exit_code"] == 1


def test_hanging_code_times_out_and_source_change_during_run_is_stale(project):
    replace(project, "timeout = 5", "timeout = 1.5", "melampus.toml")
    supervisor = Supervisor(project / "melampus.toml")
    replace(project, "return min(10000, max(0, cents))", "while True: pass")
    assert "timed out" in supervisor.check()["message"]
    replace(project, "while True: pass", "return min(10000, max(0, cents))")
    assert supervisor.check()["exit_code"] == 0


def test_revision_changes_during_execution_require_a_new_run(project, monkeypatch):
    supervisor = Supervisor(project / "melampus.toml")
    original = supervisor.run_probe

    def change_during_run():
        result = original()
        replace(project, "return min(10000, max(0, cents))", "return cents")
        return result

    monkeypatch.setattr(supervisor, "run_probe", change_during_run)
    report = supervisor.check()
    assert report["exit_code"] == 2 and "changed during" in report["message"]
    monkeypatch.setattr(supervisor, "run_probe", original)
    assert supervisor.check()["exit_code"] == 1


def test_hook_decisions_require_repair_and_block_completion(project):
    supervisor = Supervisor(project / "melampus.toml")
    replace(project, "return min(10000, max(0, cents))", "return cents")
    report = supervisor.check()
    denied = hook_decision(event("PreToolUse", project), report, supervisor)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    for tool in ("Read", "Grep", "Glob", "AskUserQuestion"):
        assert hook_decision(event("PreToolUse", project, tool), report, supervisor) == {}
    repair = hook_decision(event("PreToolUse", project, "Edit"), report, supervisor)
    assert "permissionDecision" not in repair["hookSpecificOutput"]
    for file in ("intent.py", "../other.py", "unrelated.py"):
        denied = hook_decision(event("PreToolUse", project, "Write", file), report, supervisor)
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    for name in ("PostToolUse", "Stop"):
        assert hook_decision(event(name, project), report, supervisor)["decision"] == "block"
    assert (
        "additionalContext"
        in hook_decision(event("PostToolUseFailure", project), report, supervisor)[
            "hookSpecificOutput"
        ]
    )


@pytest.fixture
def running(project):
    state = project / ".melampus/session.json"
    log = (project / "supervisor.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "melampus",
            "session",
            "--config",
            str(project / "melampus.toml"),
            "--state",
            str(state),
            "--interval",
            "0.05",
        ],
        stdout=log,
        stderr=log,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if state.exists() and gate(state, {})[0]["exit_code"] == 0:
                break
            assert process.poll() is None, (project / "supervisor.log").read_text()
            time.sleep(0.05)
        else:
            pytest.fail("supervisor did not become healthy")
        yield state, process
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=12)
        log.close()


def test_live_daemon_detects_edits_without_hook_then_gates_and_recovers(project, running):
    state, process = running
    replace(project, "return min(10000, max(0, cents))", "return cents")
    deadline = time.monotonic() + 5
    while '"state": "drift"' not in (project / "supervisor.log").read_text():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    report, decision = gate(state, event("PreToolUse", project))
    assert (
        report["exit_code"] == 1 and decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    )
    hook = subprocess.run(
        [sys.executable, "-m", "melampus", "gate", "--claude", "--state", str(state)],
        input=json.dumps(event("Stop", project)),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert hook.returncode == 0 and json.loads(hook.stdout)["decision"] == "block"
    replace(project, "return cents", "return min(10000, max(0, cents))")
    assert gate(state, event("Stop", project)) == (gate(state, {})[0], {})
    generic = subprocess.run(
        [sys.executable, "-m", "melampus", "gate", "--state", str(state)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert generic.returncode == 0
    process.send_signal(signal.SIGINT)
    process.wait(timeout=5)
    assert not state.exists()
    report, decision = gate(state, event("PreToolUse", project))
    assert (
        report["exit_code"] == 2 and decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


def test_session_ownership_wrong_root_and_bad_token_fail_closed(project, running):
    state, _ = running
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "melampus",
            "session",
            "--config",
            str(project / "melampus.toml"),
            "--state",
            str(state),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert second.returncode == 2 and "already owns" in second.stderr
    assert gate(state, event("Stop", project.parent))[0]["exit_code"] == 2
    descriptor = json.loads(state.read_text())
    descriptor["token"] = "wrong"
    other = project / "wrong.json"
    other.write_text(json.dumps(descriptor))
    assert gate(other, event("Stop", project))[1]["decision"] == "block"


@pytest.mark.parametrize(
    "change",
    [
        "contracts = 1",
        'contracts = "../bad"',
        "watch = []",
        "timeout = 12",
        'protect = ["missing.py"]',
        'probe = "../escape.py"',
    ],
)
def test_invalid_configuration_rejected(project, change):
    name = change.split(" =")[0]
    config = project / "melampus.toml"
    config.write_text(
        "\n".join(
            line for line in config.read_text().splitlines() if not line.startswith(name + " =")
        )
        + "\n"
        + change
    )
    with pytest.raises((ValueError, TypeError)):
        Supervisor(config)


def test_directory_watch_detects_added_deleted_files_and_restricts_symlinks(project):
    (project / "src").mkdir()
    replace(project, 'watch = ["pricing.py"]', 'watch = ["src", "pricing.py"]', "melampus.toml")
    supervisor = Supervisor(project / "melampus.toml")
    original = supervisor.snapshot()
    path = project / "src" / "new.py"
    path.write_text("# new")
    assert supervisor.snapshot() != original and supervisor.repair_path(str(path))
    path.unlink()
    assert supervisor.snapshot() == original
    path.symlink_to(Path(__file__))
    assert supervisor.check()["exit_code"] == 2


def test_invalid_hook_input_fails_explicitly():
    process = subprocess.run(
        [sys.executable, "-m", "melampus", "gate", "--claude"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert process.returncode == 2 and "invalid hook" in process.stderr


def test_alias_paths_allow_repair_but_never_aliases_of_reviewed_files(project):
    alias = project.parent / "alias"
    alias.symlink_to(project, target_is_directory=True)
    supervisor = Supervisor(project / "melampus.toml")
    assert supervisor.repair_path(str(alias / "pricing.py"))
    assert not supervisor.repair_path(str(alias / "intent.py"))
    # Retargeting a protected symlink after startup changes the pinned input.
    original = (project / "intent.py").read_text()
    (project / "alternate.py").write_text(original + "\n# changed\n")
    (project / "intent.py").unlink()
    (project / "intent.py").symlink_to(project / "alternate.py")
    assert supervisor.check()["protected_changed"] == ["intent.py"]


@pytest.mark.parametrize(
    "mutation",
    [
        "no_contracts",
        "wrong_contract",
        "sampled",
        "empty_checks",
        "predicate_error",
        "exit",
        "duplicate",
    ],
)
def test_contract_and_execution_failures_are_incomplete(project, mutation):
    if mutation == "no_contracts":
        replace(project, 'CONTRACTS = {"pricing:price": PRICE}', "CONTRACTS = {}", "intent.py")
    elif mutation == "wrong_contract":
        replace(
            project,
            'CONTRACTS = {"pricing:price": PRICE}',
            'CONTRACTS = {"pricing:price": "invalid"}',
            "intent.py",
        )
    elif mutation == "sampled":
        replace(
            project,
            '"Price is never negative.")',
            '"Price is never negative.", sample=0.5)',
            "intent.py",
        )
    elif mutation == "empty_checks":
        with (project / "intent.py").open("a") as f:
            f.write('\nCONTRACTS = {"pricing:price": Contract("Empty", ())}\n')
    elif mutation == "predicate_error":
        replace(project, "lambda value: value >= 0", "lambda value: 1 / 0", "intent.py")
    elif mutation == "exit":
        replace(project, "return min(10000, max(0, cents))", "import os; os._exit(0)")
    else:
        with (project / "pricing.py").open("a") as f:
            f.write(
                '\nfrom melampus import instrumented\n@instrumented(intent="Changed intent", checks=PRICE.checks)\ndef price(cents):\n    return 0\n'
            )
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 2, report


def test_timeout_kills_scenario_children(project):
    replace(project, "timeout = 5", "timeout = 1.5", "melampus.toml")
    pid_file = project / "child.pid"
    replace(
        project,
        "return min(10000, max(0, cents))",
        'import subprocess, sys, time\n    from pathlib import Path\n    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n    Path("child.pid").write_text(str(child.pid))\n    time.sleep(60)',
    )
    assert "timed out" in Supervisor(project / "melampus.toml").check()["message"]
    assert pid_file.exists()
    pid = int(pid_file.read_text())
    # kill(0) also sees zombies; ps state distinguishes an exited child.
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    assert not result.stdout.strip() or result.stdout.strip().startswith("Z"), result.stdout
