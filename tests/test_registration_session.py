import shutil
from pathlib import Path

import pytest

from melampus.session import Supervisor, hook_decision

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sdk-registration"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__", ".melampus"))
    return root


def change(root, file, before, after):
    path = root / file
    original = path.read_text()
    assert before in original
    path.write_text(original.replace(before, after))


def test_three_styles_drift_gate_and_repair(project):
    supervisor = Supervisor(project / "melampus.toml")
    healthy = supervisor.check()
    assert healthy["exit_code"] == 0 and healthy["checks"] == {"passed": 9}, healthy
    change(project, "service.py", "max(0, cents)", "min(0, cents)")
    report = supervisor.check()
    assert report["exit_code"] == 1
    assert {f["function"] for f in report["findings"]} == {"pricing:PricingService.price"}
    assert hook_decision({"hook_event_name": "Stop"}, report, supervisor)["decision"] == "block"
    change(project, "service.py", "min(0, cents)", "max(0, cents)")
    assert supervisor.check()["exit_code"] == 0


def test_multiple_instances_share_reviewed_path_without_erasing_drift(project):
    with (project / "exercise.py").open("a") as file:
        file.write("""
from melampus import instrument
from service import PricingService
from intent import PRICE

second = instrument(PricingService(fee=-10), namespace="pricing:PricingService", contracts={"price": PRICE})
second.price(0)
service.price(0)
""")
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 1 and not report["contract_mismatch"], report
    change(project, "exercise.py", "fee=-10", "fee=5")
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 0, report


@pytest.mark.parametrize("bad_first", [True, False])
def test_conflicting_declaration_stays_incomplete_after_valid_instances(project, bad_first):
    conflict = """
from melampus import Check, Contract, instrument
from service import PricingService

weakened = Contract("Return a nonnegative price in cents", (Check("nonnegative", lambda n: True, "Price is a nonnegative integer."),))
instrument(PricingService(), namespace="pricing:PricingService", contracts={"price": weakened}).price(0)
"""
    exercise = project / "exercise.py"
    original = exercise.read_text()
    exercise.write_text(conflict + original if bad_first else original + conflict)
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 2 and report["contract_mismatch"] == [
        "pricing:PricingService.price"
    ], report


@pytest.mark.parametrize(
    "mutation", ["unregistered", "raw_reference", "missing_call", "suppressed"]
)
def test_registration_bypass_or_suppression_is_incomplete(project, mutation):
    if mutation == "unregistered":
        change(
            project,
            "registration.py",
            'PricingService(), namespace="pricing:PricingService", contracts={"price": PRICE}',
            'PricingService(), namespace="other:PricingService", contracts={"price": PRICE}',
        )
    elif mutation == "raw_reference":
        change(
            project,
            "exercise.py",
            "from registration import pricing, service",
            "from registration import pricing, service\nfrom functions import price as raw",
        )
        change(project, "exercise.py", "pricing.price(cents)", "raw(cents)")
    elif mutation == "missing_call":
        change(project, "exercise.py", "    service.price(cents)", "    pass")
    else:
        change(
            project,
            "registration.py",
            "from melampus import instrument",
            "from melampus import instrument, DEFAULT_POLICY\nDEFAULT_POLICY.configure(disabled_paths=['pricing:PricingService.price'])",
        )
    report = Supervisor(project / "melampus.toml").check()
    assert report["exit_code"] == 2 and report["missing"], report
