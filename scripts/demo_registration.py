"""Compare decorator, class and module-boundary styles using fresh probes."""

import shutil
import tempfile
from pathlib import Path

from melampus.session import Supervisor, hook_decision

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="melampus-registration-") as temporary:
        root = Path(temporary)
        shutil.copytree(
            ROOT / "examples/sdk-registration",
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", ".melampus"),
        )
        supervisor = Supervisor(root / "melampus.toml")
        healthy = supervisor.check()
        assert healthy["exit_code"] == 0 and healthy["checks"] == {"passed": 9}, healthy
        for file, path in (
            ("wrapper.py", "wrapper:price"),
            ("service.py", "pricing:PricingService.price"),
            ("functions.py", "pricing:price"),
        ):
            source = root / file
            original = source.read_text()
            source.write_text(original.replace("max(0, cents)", "min(0, cents)"))
            report = supervisor.check()
            assert report["exit_code"] == 1, report
            assert {item["function"] for item in report["findings"]} == {path}, report
            assert (
                hook_decision({"hook_event_name": "Stop"}, report, supervisor)["decision"]
                == "block"
            )
            source.write_text(original)
            assert supervisor.check()["exit_code"] == 0
            print(f"{file}: healthy → drift at {path} → blocked completion → repaired")
        registration = root / "registration.py"
        original = registration.read_text()
        registration.write_text(original + "\npricing.price = price\n")
        report = supervisor.check()
        assert report["exit_code"] == 2 and "pricing:price/nonnegative" in report["missing"], report
        registration.write_text(original)
        assert supervisor.check()["exit_code"] == 0
        print("Removed module wrapper: incomplete required evidence, never healthy.")
    print("Registration comparison passed; no model request or network export.")


if __name__ == "__main__":
    main()
