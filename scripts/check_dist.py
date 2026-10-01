"""Validate actual artifacts, rebuild the sdist, and smoke-test the installed wheel."""

from __future__ import annotations

import email
import os
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    version = (ROOT / "VERSION").read_text().strip()
    wheel = ROOT / "dist" / f"melampus-{version}-py3-none-any.whl"
    sdist = ROOT / "dist" / f"melampus-{version}.tar.gz"
    assert sorted(p.name for p in (ROOT / "dist").iterdir() if p.name != ".gitignore") == sorted(
        [wheel.name, sdist.name]
    ), "unexpected or stale distribution files"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for required in (
            "melampus/__init__.py",
            "melampus/py.typed",
            "melampus/sdk.py",
            "melampus/watcher.py",
            "melampus/session.py",
            "melampus/contracts.py",
            "melampus/registration.py",
            "melampus/_probe.py",
        ):
            assert required in names, required
        metadata = email.message_from_bytes(archive.read(f"melampus-{version}.dist-info/METADATA"))
        assert metadata["Name"] == "melampus" and metadata["Version"] == version
        assert metadata["License-Expression"] == "Apache-2.0"
        assert any(name.endswith("licenses/LICENSE") for name in names)
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
        for suffix in (
            "pyproject.toml",
            "VERSION",
            "LICENSE",
            "README.md",
            "tests/test_sdk.py",
            "semconv/code_artifact.yaml",
            "examples/agent-session/.claude/settings.json",
            "examples/agent-session/intent.py",
            "examples/agent-session/exercise.py",
            "docs/AGENT-SESSION.md",
            "scripts/demo_agent_session.py",
            "examples/sdk-registration/.claude/settings.json",
            "examples/sdk-registration/registration.py",
            "examples/pilot_study/study.py",
            "docs/SDK-REGISTRATION.md",
            "docs/SDK-UX-RESEARCH.md",
            "scripts/demo_registration.py",
            "scripts/demo_pilot.py",
        ):
            assert any(name.endswith("/" + suffix) for name in names), suffix
    with tempfile.TemporaryDirectory(prefix="melampus-dist-") as temporary:
        temp = Path(temporary)
        subprocess.run(
            [
                "uv",
                "build",
                "--no-build-isolation",
                "--wheel",
                str(sdist),
                "--out-dir",
                str(temp / "rebuilt"),
            ],
            check=True,
        )
        rebuilt = temp / "rebuilt" / wheel.name
        with zipfile.ZipFile(wheel) as original, zipfile.ZipFile(rebuilt) as rebuilt_archive:
            assert original.namelist() == rebuilt_archive.namelist()
            assert all(original.read(n) == rebuilt_archive.read(n) for n in original.namelist()), (
                "sdist rebuild differs from wheel"
            )
        env = {**os.environ, "UV_NO_PROGRESS": "1"}
        # --no-project and a separate cwd ensure the editable source cannot satisfy imports.
        subprocess.run(
            [
                "uv",
                "run",
                "--no-project",
                "--with",
                str(wheel),
                "python",
                "-c",
                "import melampus; from melampus import Check, Contract, Policy, instrument, instrumented; print(melampus.__version__)",
            ],
            cwd=temp,
            env=env,
            check=True,
        )
        subprocess.run(
            ["uv", "run", "--no-project", "--with", str(wheel), "melampus", "--version"],
            cwd=temp,
            env=env,
            check=True,
        )
        for script, arguments in (
            ("demo_registration.py", []),
            ("demo_pilot.py", ["--demo"]),
        ):
            subprocess.run(
                [
                    "uv",
                    "run",
                    "--no-project",
                    "--with",
                    f"melampus[session] @ {wheel.as_uri()}",
                    "python",
                    str(ROOT / "scripts" / script),
                    *arguments,
                ],
                cwd=temp,
                env=env,
                check=True,
            )
        subprocess.run(
            [
                "uv",
                "run",
                "--no-project",
                "--with",
                f"melampus[session] @ {wheel.as_uri()}",
                "python",
                str(ROOT / "scripts/demo_agent_session.py"),
            ],
            cwd=temp,
            env=env,
            check=True,
        )
    print(
        "Distribution metadata, license, typing marker, sdist rebuild and clean wheel import passed."
    )


if __name__ == "__main__":
    main()
