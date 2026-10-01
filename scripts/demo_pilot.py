"""Entrypoint also usable outside this checkout with an installed Melampus wheel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from pilot_study.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
